"""终验收：直接读**已安装到游戏目录**的 resources.assets 逐项检查。

    python tools/accept.py

这是发布前的最后一道关，42 项检查全绿才算通过。检查内容：

* 14 张本地化表都在，且每一行的所有语言列内容一致；
* 每一行的英文原文都对应了中文（只保留拉丁字母的词条走 KEEP_LATIN 白名单）；
* 没有 `{n}` 占位符漏进成品（漏了游戏就会把 "{12}" 原样显示出来）；
* 11 个字体图集的中文字形数、图集尺寸、字形是否都在界内。
"""
import csv, io, os, re, sys

import UnityPy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mmcore import GAME, SHEETS, LANG_COLS, setup_console
from tmpfont import TMP_FontAsset
from cjkfont import TARGETS
import glossary

# 中日韩统一表意文字 + 中日韩标点 + 全角字符。只匹配汉字不够：
# 「{Stat}：+20」这种只有全角冒号的词条也是正确翻译过的
CJK = re.compile(r'[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]')
LEAK = re.compile(r'(?<![A-Za-z0-9_])\{\d{1,4}\}')

PASS, FAIL = [], []


def check(ok, msg):
    (PASS if ok else FAIL).append(msg)
    print(('  [OK]   ' if ok else '  [FAIL] ') + msg)


def main():
    setup_console()
    path = os.path.join(GAME, 'MM_Data', 'resources.assets')
    print('检查 %s' % path)
    env = UnityPy.load(path)
    sf = env.file

    sheets, fonts = {}, {}
    for pid, o in sf.objects.items():
        if o.type.name == 'TextAsset':
            d = o.read()
            if d.m_Name in SHEETS and d.m_Name not in sheets:
                s = d.m_Script
                sheets[d.m_Name] = s.decode('utf-8') if isinstance(s, bytes) else s
        elif o.type.name == 'MonoBehaviour':
            raw = o.get_raw_data()
            if len(raw) < 60:
                continue
            try:
                fa = TMP_FontAsset().read_bytes(raw)
            except Exception:                        # noqa: BLE001
                continue
            if fa.name:
                fonts[pid] = fa

    print('\n== 本地化表 ==')
    check(len(sheets) == len(SHEETS),
          '14 张本地化表齐全（实际 %d 张）' % len(sheets))
    rows_total = 0
    for name in SHEETS:
        if name not in sheets:
            continue
        r = csv.reader(io.StringIO(sheets[name]))
        hdr = next(r)
        rows = [x for x in r if len(x) == len(hdr)]
        cols = [hdr.index(c) for c in LANG_COLS if c in hdr]
        ei = hdr.index('English')
        keep = set(glossary.KEEP_LATIN)
        n_en = sum(1 for x in rows if x[ei].strip())
        # 有中文，或者属于「本来就该保留拉丁字母」的白名单
        n_cjk = sum(1 for x in rows if CJK.search(x[ei]) or x[ei] in keep)
        rows_total += n_en
        check(n_cjk == n_en,
              '%-14s %d/%d 行中文，%d 个语言列' % (name, n_cjk, n_en, len(cols)))
        same = all(len({x[c] for c in cols}) == 1 for x in rows)
        check(same, '%-14s 各语言列内容一致' % name)

    print('\n== 文本完整性 ==')
    leaks = 0
    for name, text in sheets.items():
        r = csv.reader(io.StringIO(text))
        hdr = next(r)
        if 'English' not in hdr:
            continue
        ei = hdr.index('English')
        for row in r:
            if len(row) != len(hdr):
                continue
            if LEAK.search(row[ei]):
                leaks += 1
    check(leaks == 0, '成品里没有 {n} 占位符泄漏（%d 处）' % leaks)

    print('\n== 字体 ==')
    ok_fonts = 0
    for pid, _cfg in TARGETS.items():
        fa = fonts.get(pid)
        if fa is None:
            check(False, '字体 %d 缺失' % pid)
            continue
        t = sf.objects[fa.atlas[1]].read()
        cjk = sum(1 for g in fa.m_glyphInfoList if g.id > 0x2e80)
        pad = fa.m_fontInfo.Padding
        inside = all(0 <= g.x and 0 <= g.y and
                     g.x + g.width + pad <= t.m_Width and
                     g.y + g.height + pad <= t.m_Height
                     for g in fa.m_glyphInfoList)
        ok = cjk > 2400 and inside
        ok_fonts += 1 if ok else 0
        check(ok, '%-28s %d 个字形，图集 %dx%d，pad %.1f，界内 %s'
              % (fa.name, cjk, t.m_Width, t.m_Height, pad, inside))
    check(ok_fonts == len(TARGETS), '%d 个字体图集全部可用' % len(TARGETS))

    print('\n== 汇总 ==')
    print('  英文原文行数：%d' % rows_total)
    print('  通过：%d   失败：%d' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
