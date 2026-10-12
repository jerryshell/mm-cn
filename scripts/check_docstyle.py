"""按 docstyle 规范扫描仓库里的中文文档与代码注释。

    python scripts/check_docstyle.py

检查范围只包括「可见正文」：

* Markdown 文档全文（代码块跳过）
* Python 文件的 `#` 注释与三引号字符串（文档字符串、批处理模板）
* 批处理脚本里的提示文案

标点方面要求：中文用直角引号，不用破折号，不用 emoji 与箭头，不用感叹号。
句式方面提示「不是……而是……」这类否定对举，便于人工判断是否要改写。

不检查代码字面量，JSON 键名、路径、表名、游戏原文与译文都不在范围内，
规范里也明确要求不对这些内容做改写。

退出码非 0 表示存在需要修改的项；中危词只做提示，不影响退出码。
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from mmcore import setup_console

# ---------------------------------------------------------------- 检查规则

# 第二人称。规范要求改成无主句，或点名具体角色
SECOND_PERSON = re.compile(r'[你您]')

# 中文正文使用直角引号，不用中文双引号
CURLY_QUOTE = re.compile(r'[“”]')

# 正文不使用感叹号
EXCLAIM = re.compile(r'！')

# 正文不使用破折号（—— 与各种横线变体）
DASH = re.compile('[—–―‒−]')

# 正文不使用 emoji 与箭头符号
EMOJI = re.compile('['
                   '🌀-🫿'      # 各类 emoji
                   '☀-➿'      # 杂项符号与装饰符号
                   '🀀-🋿'      # 麻将、扑克、方块
                   '︀-️'      # 变体选择符（把字符变成 emoji 样式）
                   '←-⇿'      # 箭头
                   '⬀-⯿'      # 杂项符号与箭头
                   ']')

# 高危黑话：命中即失败
BLACKLIST = ['赋能', '抓手', '闭环', '沉淀', '对齐', '对标', '拉通', '打通', '协同',
             '联动', '洞察', '心智', '调性', '战役', '链路', '势能', '兜底', '落盘',
             '收口', '透传', '串起来']

# 中危词：语义明确时可用，只提示不判失败
AMBER = ['场景', '生态', '体系', '路径', '触点', '卡点', '布局', '矩阵', '颗粒度',
         '复盘', '梳理', '输出', '提炼']

# 术语大小写归一。只作用于正文，不作用于代码与路径
TERM_CASE = [(_canon, re.compile(r'(?<![A-Za-z0-9_./\-])' + _canon + r'(?![A-Za-z0-9_])', re.I))
             for _canon in ('JSON', 'API', 'URL', 'HTTP', 'GitHub', 'Python',
                            'Steam', 'Unity', 'MD5', 'CSV', 'GBK', 'SDF', 'TMP')]

# 命令行示例保持原样，不做大小写归一
COMMAND_LINE = re.compile(r'^\s*(python|py|pip|set |export |WORKERS=|\$|>)', re.I)

# 技术语境下有固定含义的黑话，允许保留
TECH_ALLOWED = [
    # 「对齐」在内存布局语境里属于精确术语，列入白名单
    ('对齐', ('字节对齐', '内存对齐', '对齐到', '对齐方式')),
    # 「路径」指文件系统路径时语义明确
    ('路径', ('安装路径', '完整路径', '文件路径', '保存路径')),
    # 「输出」指进程 stdout 时是标准术语
    ('输出', ('标准输出', '输出写到', '输出目录')),
]

# 「不是……而是……」这类否定对举句式。中文写作里容易读出一股翻译腔，
# 列为提示级：偶尔它确实是最清楚的写法，交由人工判断。
# 用 chr(10) 拼出换行符，避免正则里的反斜杠被外层字符串二次转义。
_NL = chr(10)
NEGATIVE_PARALLEL = re.compile(
    r'不是[^。；' + _NL + r']{0,40}?而是'
    r'|并非[^。；' + _NL + r']{0,40}?而是'
    r'|是[^，。；' + _NL + r']{0,30}?而不是'
    r'|是[^，。；' + _NL + r']{2,26}?，不是'
    r'|与其[^。；' + _NL + r']{0,40}?不如'
    r'|[^，。；' + _NL + r']{2,26}?而非')

# 中西文留白。规范针对的是「中文与可读的半角英文、数字之间」，
# 所以只判汉字，全角标点（，。「」（））紧邻英文不算问题。
HAN = '\\u4e00-\\u9fff'
NO_SPACE = re.compile('([' + HAN + '])([A-Za-z0-9])')      # 汉字后紧跟英文或数字
NO_SPACE2 = re.compile('([A-Za-z0-9])([' + HAN + '])')     # 英文或数字后紧跟汉字

# 行内代码、链接、代码块内容不参与检查
SKIP_SPAN = re.compile(
    r'``[^`]*``|`[^`]*`|\[[^\]]*\]\([^)]*\)|https?://\S+|\{[^}]*\}|<[^>]*>'
    r'|(?<![A-Za-z0-9])[\w./\-]+\.(?:json|csv|py|bat|md|jsonl|txt|assets)')


def strip_inline(text):
    return SKIP_SPAN.sub(lambda m: '\x00' * len(m.group(0)), text)


def prose_lines(path, text):
    """挑出需要检查的行，返回 [(行号, 内容)]。

    Markdown 跳过代码块；Python 只取注释与三引号字符串里的内容。
    """
    out = []
    if path.endswith('.md'):
        in_block = False
        for n, line in enumerate(text.split('\n'), 1):
            if line.strip().startswith('```'):
                in_block = not in_block
                continue
            if not in_block:
                out.append((n, line))
        return out

    if path.endswith('.py'):
        in_doc = False
        for n, line in enumerate(text.split('\n'), 1):
            stripped = line.strip()
            if stripped.count("'''") == 1 or stripped.count('"""') == 1:
                in_doc = not in_doc
                out.append((n, line))
                continue
            if in_doc or stripped.startswith('#'):
                out.append((n, line))
        return out

    return list(enumerate(text.split('\n'), 1))


def check_file(path):
    with io.open(path, encoding='utf-8') as f:
        text = f.read()
    fails, hints = [], []
    for n, raw in prose_lines(path, text):
        line = strip_inline(raw)
        shown = raw.strip()[:78]
        if SECOND_PERSON.search(line):
            fails.append((n, '第二人称', shown))
        if CURLY_QUOTE.search(line):
            fails.append((n, '中文双引号（应改直角引号）', shown))
        if EXCLAIM.search(line):
            fails.append((n, '感叹号', shown))
        m = DASH.search(line)
        if m:
            fails.append((n, '破折号（%r）' % m.group(0), shown))
        m = EMOJI.search(line)
        if m:
            fails.append((n, 'emoji 或箭头（%r）' % m.group(0), shown))
        for w in BLACKLIST:
            if w not in line:
                continue
            allow = next((ctx for word, ctx in TECH_ALLOWED if word == w), ())
            if any(c in line for c in allow):
                continue
            fails.append((n, '高危黑话「%s」' % w, shown))
            break
        for w in AMBER:
            if w not in line:
                continue
            allow = next((ctx for word, ctx in TECH_ALLOWED if word == w), ())
            if any(c in line for c in allow):
                continue
            hints.append((n, '中危词「%s」' % w, shown))
            break
        if not COMMAND_LINE.match(raw):
            for want, rx in TERM_CASE:
                m = rx.search(line)
                if m and m.group(0) != want:
                    fails.append((n, '大小写 %s -> %s' % (m.group(0), want), shown))
                    break
        if NO_SPACE.search(line) or NO_SPACE2.search(line):
            fails.append((n, '中西文缺空格', shown))
        m = NEGATIVE_PARALLEL.search(line)
        if m:
            hints.append((n, '否定对举「%s」' % m.group(0)[:12], shown))
    return fails, hints


def gather():
    files = sorted(glob_md(ROOT))
    for d in ('docs', 'installer'):
        files += sorted(glob_md(os.path.join(ROOT, d)))
    for d in ('tools', 'scripts'):
        files += sorted(os.path.join(ROOT, d, f)
                        for f in os.listdir(os.path.join(ROOT, d))
                        if f.endswith('.py'))
    return files


def glob_md(d):
    return (os.path.join(d, f) for f in sorted(os.listdir(d))
            if f.endswith('.md') and os.path.isfile(os.path.join(d, f)))


# 数据文件：正文是游戏原文与译文，属于机器可读内容，规范不适用
EXCLUDE = {'tools/glossary.py', 'scripts/check_docstyle.py'}


def main():
    setup_console()
    total_fail = total_hint = 0
    for path in gather():
        rel = os.path.relpath(path, ROOT).replace('\\', '/')
        if rel in EXCLUDE:
            continue
        fails, hints = check_file(path)
        if fails or hints:
            print('\n%s' % rel)
            for n, rule, content in fails:
                print('  %4d  [必须]  %-24s %s' % (n, rule, content))
            for n, rule, content in hints:
                print('  %4d  [提示]  %-24s %s' % (n, rule, content))
        total_fail += len(fails)
        total_hint += len(hints)
    print('\n必须修改 %d 处，提示 %d 处' % (total_fail, total_hint))
    return 1 if total_fail else 0


if __name__ == '__main__':
    sys.exit(main())
