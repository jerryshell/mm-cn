"""英文 -> 中文机器翻译（腾讯 Transmart，不需要 API Key）。

标记和换行先被换成 `{n}` 占位符再送出去，译文回来后逐条校验占位符是否完整，
结果落到 trans/zh_cache.jsonl，所以运行可以随时中断续跑。

翻译分三轮降级：

1. **整句**：大多数词条一次就过（实测约 98.6%）；
2. **按行**：整句被引擎拒绝（原样回显）时，按含换行的占位符切成单元分别翻；
3. **按片段**：按行仍失败时，把单元再切成「占位符之间的纯文本片段」逐个翻，
   短标签（`Reliability:` 这类）在这一轮基本都能命中。

三轮都过不去的会写进 trans/zh_failed.jsonl。
"""
import hashlib, json, os, re, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from markup import protect, restore, token_problems, unit_split, has_text, TOKEN_RE
from mmcore import TRANS

CACHE = os.path.join(TRANS, 'zh_cache.jsonl')
FAILED = os.path.join(TRANS, 'zh_failed.jsonl')

# 单次请求的条数与字符数上限（实测腾讯接口总长约 4500 字符就会返回 outOfLimit）
MAX_ITEMS = 60
MAX_TOTAL = 4200
# 第二轮里单个翻译单元的最大长度
MAX_UNIT = 1600

# 网页版 Transmart 用的固定 client_key，无需注册
CLIENT_KEY = 'browser-chrome-110.0.0-Mac OS-df4bd4c5-a65d-44b2-9fb0-9ee1a74c3b6d'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36')
URL = 'https://transmart.qq.com/api/imt'


def _request(texts, lang='en', tgt='zh', tries=7):
    """调用一次接口。

    成功返回译文列表；批量超限返回 None（由调用方拆分后重试）；
    其余错误重试若干次后抛异常。
    """
    body = json.dumps({
        "header": {"fn": "auto_translation", "client_key": CLIENT_KEY},
        "type": "plain", "model_category": "normal", "text_domain": "",
        "source": {"lang": lang, "text_list": texts},
        "target": {"lang": tgt},
    }).encode()
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(URL, data=body, headers={
                'Content-Type': 'application/json', 'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read())
            ret = d['header'].get('ret_code')
            if ret == 'succ':
                return d['auto_translation']
            last = ret
            if ret == 'outOfLimit':
                return None
            time.sleep(1.0 + attempt)
        except Exception as e:                       # noqa: BLE001
            last = repr(e)[:140]
            time.sleep(1.5 + attempt * 1.5)
    raise RuntimeError('翻译请求失败：%s' % last)


def _batch(items, _depth=0):
    """把 items 打包成尽量少的请求，返回等长的译文列表（失败的项为 None）。"""
    out = [None] * len(items)
    batch = []
    size = 0

    def do(sub):
        texts = [t for _, t in sub]
        try:
            res = _request(texts)
        except Exception as e:                       # noqa: BLE001
            print('   !! 请求出错：%s' % e, flush=True)
            return
        if res is None:
            # 超限：拆成两半重试；只剩一条还超限就只能放弃
            if len(sub) == 1:
                print('   !! 单条仍超限（%d 字符）' % len(texts[0]), flush=True)
                return
            mid = len(sub) // 2
            do(sub[:mid])
            do(sub[mid:])
            return
        if len(res) != len(texts):
            print('   !! 返回条数不匹配 %d != %d' % (len(res), len(texts)), flush=True)
            return
        for (i, _), v in zip(sub, res):
            out[i] = v

    def flush():
        nonlocal batch, size
        if batch:
            do(batch)
            batch, size = [], 0

    for i, it in enumerate(items):
        n = len(it)
        if n >= MAX_TOTAL:                 # 单条就超长，单独发
            flush()
            do([(i, it)])
            continue
        if batch and (size + n > MAX_TOTAL or len(batch) >= MAX_ITEMS):
            flush()
        batch.append((i, it))
        size += n
    flush()
    return out


def _key(t):
    return hashlib.md5(t.encode('utf-8')).hexdigest()


def ckey(t):
    """缓存键：原文 + 原文长度哈希（防止不同原文碰撞）。"""
    return t + '|' + _key(t)


def load_cache():
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                    cache[o['k']] = o['v']
                except Exception:                    # noqa: BLE001
                    continue
    return cache


def save_cache(cache):
    tmp = CACHE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for k, v in cache.items():
            f.write(json.dumps({'k': k, 'v': v}, ensure_ascii=False) + '\n')
    os.replace(tmp, CACHE)


def _refused(src, out):
    """判断引擎是不是「拒绝翻译」了 —— 它的表现是把原文原样回显。

    这类结果占位符是完整的，只靠 token_problems 查不出来，必须单独判。
    """
    if not has_text(src):
        return False
    a = re.sub(r'\s+', ' ', src).strip()
    b = re.sub(r'\s+', ' ', out).strip()
    return a == b


def _split_runs(s):
    """把保护后的单元切成 [(是否占位符, 文本), ...]，供第三轮逐片段翻译用。"""
    pieces = []
    pos = 0
    for m in TOKEN_RE.finditer(s):
        if m.start() > pos:
            pieces.append((False, s[pos:m.start()]))
        pieces.append((True, m.group(0)))
        pos = m.end()
    if pos < len(s):
        pieces.append((False, s[pos:]))
    return pieces


def _post(raw, out):
    """收拾译文：引擎爱在行首加空格，原文没有的话去掉。"""
    if raw.count('\n') == out.count('\n'):
        fixed = []
        for s, d in zip(raw.split('\n'), out.split('\n')):
            if s[:1] not in (' ', '\t') and d[:1] in (' ', '\t'):
                d = d.lstrip(' \t')
            fixed.append(d)
        out = '\n'.join(fixed)
    return out


def translate_many(texts, workers=5, verbose=True):
    """翻译一批原文，返回整个缓存字典（键是 ckey(原文)）。

    只翻译缓存里没有的条目，所以重复运行很便宜。
    """
    cache = load_cache()
    uniq = list(dict.fromkeys(t for t in texts if t and t.strip()))
    todo = [t for t in uniq if ckey(t) not in cache]
    if verbose:
        print('翻译：去重后 %d 条，已缓存 %d 条，待翻译 %d 条'
              % (len(uniq), len(cache), len(todo)), flush=True)
    if not todo:
        return cache

    prepared = [(t, protect(t)) for t in todo]

    # ---- 第一轮：整句 ---------------------------------------------------------
    pieces = [p for _, (p, _) in prepared]
    n = len(pieces)
    per = max(1, (n + workers - 1) // workers)
    spans = [(lo, min(n, lo + per)) for lo in range(0, n, per)]
    lock = threading.Lock()
    prog = [0]

    def work(sp):
        lo, hi = sp
        res = _batch(pieces[lo:hi])
        with lock:
            for j, v in enumerate(res):
                pieces[lo + j] = v
            prog[0] += hi - lo
            print('  ... %d/%d' % (prog[0], n), flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, spans))

    retry = []
    for i, (raw, (p, toks)) in enumerate(prepared):
        v = pieces[i]
        if isinstance(v, str) and not _refused(p, v) and not token_problems(v, toks, p):
            restored, _ = restore(v, toks)
            cache[ckey(raw)] = _post(raw, restored)
        else:
            retry.append(raw)

    # ---- 第二轮：按行 ---------------------------------------------------------
    if retry and verbose:
        print('  第二轮（按行）处理 %d 条' % len(retry), flush=True)

    groups = []
    for raw in retry:
        p, toks = protect(raw)
        groups.append(unit_split(p, toks, max_len=MAX_UNIT, min_len=0))

    flat, where = [], []
    for gi, units in enumerate(groups):
        for ui, u in enumerate(units):
            if has_text(u):
                where.append((gi, ui))
                flat.append(u)

    res = _batch(flat)
    fixed = {key: v for key, v in zip(where, res)}

    still = []
    for gi, raw in enumerate(retry):
        p, toks = protect(raw)
        joined = ''
        ok = True
        for ui, u in enumerate(groups[gi]):
            if not has_text(u):
                joined += u
                continue
            v = fixed.get((gi, ui))
            if v is None or _refused(u, v):
                ok = False
                break
            joined += v
        if not ok:
            still.append((raw, '单元翻译失败'))
            continue
        probs = token_problems(joined, toks, p)
        if probs:
            still.append((raw, probs[:3]))
            continue
        restored, _ = restore(joined, toks)
        cache[ckey(raw)] = _post(raw, restored)

    # ---- 第三轮：按文本片段 ---------------------------------------------------
    if still and verbose:
        print('  第三轮（按片段）处理 %d 条' % len(still), flush=True)

    run_jobs = []
    run_todo = []
    for raw, _why in still:
        p, toks = protect(raw)
        units = unit_split(p, toks, max_len=MAX_UNIT, min_len=0)
        pieces = []
        for u in units:
            pieces.extend(_split_runs(u))
        run_jobs.append(pieces)
        for is_tok, text in pieces:
            if is_tok:
                continue
            t = text.strip()
            if t and has_text(t) and ckey(t) not in cache:
                run_todo.append(t)

    if run_todo:
        vals = _batch(run_todo)
        for t, v in zip(run_todo, vals):
            if v is not None and not _refused(t, v):
                cache.setdefault(ckey(t), v)

    still2 = []
    for si, (raw, _why) in enumerate(still):
        p, toks = protect(raw)
        built = ''
        for is_tok, text in run_jobs[si]:
            if is_tok:
                built += text
                continue
            t = text.strip()
            if not t or not has_text(t):
                built += text
                continue
            v = cache.get(ckey(t))
            if v is None:
                built += text                 # 片段也没译出来，先保留英文
                continue
            lead = text[:len(text) - len(text.lstrip())]
            trail = text[len(text.rstrip()):]
            built += lead + v + trail
        probs = token_problems(built, toks, p)
        if probs:
            still2.append((raw, '第三轮 ' + str(probs[:3])))
            continue
        restored, _ = restore(built, toks)
        cache[ckey(raw)] = _post(raw, restored)

    still = still2

    save_cache(cache)
    if still:
        with open(FAILED, 'w', encoding='utf-8') as f:
            for raw, why in still:
                f.write(json.dumps({'raw': raw, 'why': str(why)}, ensure_ascii=False) + '\n')
        if verbose:
            print('仍失败 %d 条 -> %s' % (len(still), FAILED), flush=True)
    elif os.path.exists(FAILED):
        os.remove(FAILED)
    return cache
