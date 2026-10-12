"""保护 / 还原游戏标记，避免被机器翻译破坏。

每个 `<标签>`、`{变量}` 和换行都会换成一个 `{n}` 占位符。用花括号数字是实测的结果：
`{n}` 在句首、句尾、连续出现等所有位置都能稳定保留，而 `[[Vn]]` 有时会被引擎
直接删掉，或被改写成 `[2019-01-15]` 这样的日期。

另外还会做两件事：

* 连续的标记会合并成一个占位符 —— 引擎在「占位符占比过高」的字符串上会直接
  原样返回不翻译，合并能显著降低占位符密度；
* 紧贴占位符的「无字母串」（例如 `+30%` 里的 `+30%`）会被并入该占位符 ——
  否则引擎会把 `%{`、`${`、`0{` 当成货币 / 日期 / printf 格式，吃掉左花括号。
"""
import re

# 标记：<...> 标签 或 {...} 变量
MARKUP_RE = re.compile(r'<[^<>\n]{0,200}>|\{[^{}\n]{0,200}\}')
TOKEN_RE = re.compile(r'\{\s*(\d{1,4})\s*\}')
# 这些字符紧挨在占位符前面是安全的（逐个实测过）
SAFE_BEFORE = set('!?:;}-+=/|*~"\'}])')


def protect(text):
    """返回 (保护后的文本, tokens)。tokens[i] 是一段标记原文，可能含换行。

    ``+30%{2}`` 这种「无字母串紧贴占位符」的情况，会把 `+30%` 一起并进 tokens[2]。
    """
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    tokens = []
    out = []
    kind = []          # 与 out 一一对应：'t' 是占位符，'x' 是普通文本
    pending = []

    def flush():
        """把攒下来的连续标记合并成一个占位符。"""
        if pending:
            tokens.append(''.join(pending))
            out.append('{%d}' % (len(tokens) - 1))
            kind.append('t')
            pending.clear()

    def add_text(chunk):
        """喂入一段普通文本，顺带把其中的换行也变成标记。"""
        if not chunk:
            return
        for k, seg in enumerate(chunk.split('\n')):
            if k:
                pending.append('\n')
            if seg:
                flush()
                out.append(seg)
                kind.append('x')

    pos = 0
    for m in MARKUP_RE.finditer(text):
        add_text(text[pos:m.start()])
        pending.append(m.group(0))
        pos = m.end()
    add_text(text[pos:])
    flush()

    # 把危险的「无字母串」并进后面的占位符
    for i in range(1, len(out)):
        if kind[i] != 't' or kind[i - 1] != 'x':
            continue
        prev = out[i - 1]
        if not prev or prev[-1].isspace() or prev[-1] in SAFE_BEFORE:
            continue
        j = len(prev)
        while j > 0 and not prev[j - 1].isspace():
            j -= 1
        run = prev[j:]
        if run and not any(c.isalpha() for c in run):
            idx = int(out[i][1:-1])
            tokens[idx] = run + tokens[idx]
            out[i - 1] = prev[:j]
    return ''.join(out), tokens


def restore(text, tokens):
    """把译文里的占位符换回原始标记，返回 (还原后的文本, 用到的下标集合)。"""
    used = set()

    def repl(m):
        i = int(m.group(1))
        if i < len(tokens):
            used.add(i)
            return tokens[i]
        return m.group(0)

    return TOKEN_RE.sub(repl, text), used


def token_counts(text):
    """统计每个占位符出现次数：{下标: 次数}。"""
    c = {}
    for m in TOKEN_RE.finditer(text):
        i = int(m.group(1))
        c[i] = c.get(i, 0) + 1
    return c


def token_problems(out_text, tokens, protected):
    """比较译文与原文的占位符，返回不一致的项：[(下标, 标记内容, 实际次数, 应有次数)]。"""
    exp = token_counts(protected)
    got = token_counts(out_text)
    bad = []
    for i in sorted(exp):
        if got.get(i, 0) != exp[i]:
            bad.append((i, tokens[i] if i < len(tokens) else '?', got.get(i, 0), exp[i]))
    for i in sorted(got):
        if i not in exp:
            bad.append((i, '<unexpected>', got[i], 0))
    return bad


def unit_split(protected, tokens, max_len=240, min_len=0):
    """按「含换行的占位符」把文本切成若干单元。

    每个单元都带着自己的换行占位符，所以把它们首尾相接能精确还原原串。
    整句翻译失败时会退化成逐单元翻译。
    """
    units = []
    cur = ''
    i = 0
    while i < len(protected):
        m = TOKEN_RE.match(protected, i)
        if m:
            i = m.end()
            tok = tokens[int(m.group(1))]
            cur += m.group(0)
            if '\n' in tok and len(cur) >= min_len:
                units.append(cur)
                cur = ''
            continue
        j = protected.find('{', i)
        if j < 0:
            j = len(protected)
        cur += protected[i:j]
        i = j
    if cur:
        units.append(cur)
    # 太短的单元向前合并，让短行也能带上一点上下文
    merged = []
    for u in units:
        if merged and len(u) + len(merged[-1]) <= max_len and len(merged[-1]) < min_len:
            merged[-1] += u
        else:
            merged.append(u)
    return merged


def has_text(unit):
    """判断这个单元里有没有真正需要翻译的内容（至少两个连续字母）。"""
    return bool(re.search(r'[A-Za-z]{2,}', TOKEN_RE.sub('', unit)))
