"""构建产物结构校验：读 dist/resources.assets，检查表、字体、图集。

    python tools/verify.py

和 accept.py 的区别：这个查的是**构建产物**，accept.py 查的是**已经装进游戏的文件**。
构建完先跑这个，装完再跑那个。
"""
import csv, io, os, re, sys

import numpy as np
import UnityPy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mmcore import DIST, SHEETS, LANG_COLS, setup_console
from tmpfont import TMP_FontAsset
from cjkfont import TARGETS

PATCHED = os.path.join(DIST, 'resources.assets')


def main():
    setup_console()
    print('读取 %s' % PATCHED)
    env = UnityPy.load(PATCHED)
    sf = env.file

    # ---- 本地化表 -------------------------------------------------------------
    want = set(SHEETS)
    seen = {}
    for pid, o in sf.objects.items():
        if o.type.name != 'TextAsset':
            continue
        d = o.read()
        if d.m_Name in want and d.m_Name not in seen:
            s = d.m_Script
            if isinstance(s, bytes):
                s = s.decode('utf-8')
            seen[d.m_Name] = (pid, s)

    print('\n== 本地化表 ==')
    for name in SHEETS:
        if name not in seen:
            print('  %-14s 缺失' % name)
            continue
        pid, text = seen[name]
        r = csv.reader(io.StringIO(text))
        hdr = next(r)
        rows = [x for x in r if len(x) == len(hdr)]
        cols = [hdr.index(c) for c in LANG_COLS if c in hdr]
        cjk = 0
        for row in rows:
            if any('\u4e00' <= ch <= '\u9fff' for c in cols for ch in row[c]):
                cjk += 1
        print('  %-14s 行数=%-5d 语言列=%-2d 含中文=%-5d 样例=%s' %
              (name, len(rows), len(cols), cjk, rows[0][cols[0]][:24]))
        # 所有语言列内容必须完全一致
        for row in rows[:200]:
            vals = {row[c] for c in cols}
            if len(vals) != 1:
                print('     !! 第 %s 行列不一致：%s' %
                      (row[hdr.index('ID')] if 'ID' in hdr else '?', vals))
                break
        # 不能有 {n} 占位符漏到成品里
        for row in rows:
            for c in cols:
                if re.search(r'(?<![A-Za-z0-9_])\{\d{1,4}\}', row[c]):
                    print('     !! %s 里有占位符泄漏：%r' % (name, row[c][:80]))
                    break

    # ---- 字体 -----------------------------------------------------------------
    print('\n== 字体图集 ==')
    fonts = {}
    for pid, o in sf.objects.items():
        if o.type.name != 'MonoBehaviour':
            continue
        raw = o.get_raw_data()
        if len(raw) < 60:
            continue
        try:
            fa = TMP_FontAsset().read_bytes(raw)
        except Exception:                            # noqa: BLE001
            continue
        if fa.name:
            fonts[pid] = fa
    ok = 0
    for pid, _cfg in TARGETS.items():
        fa = fonts.get(pid)
        if fa is None:
            print('  %-8d 缺失' % pid)
            continue
        atlas_pid = fa.atlas[1]
        t = sf.objects[atlas_pid].read()
        arr = np.asarray(t.image)
        alpha = arr[:, :, 3] if arr.ndim == 3 else arr
        cjk = sum(1 for g in fa.m_glyphInfoList if g.id > 0x2e80)
        pad = fa.m_fontInfo.Padding
        # 所有字形（含 TMP 采样窗口）都必须落在图集内
        inside = all(0 <= g.x and 0 <= g.y and
                     g.x + g.width + pad <= t.m_Width and
                     g.y + g.height + pad <= t.m_Height
                     for g in fa.m_glyphInfoList)
        # 原图集左上角应该还有内容（说明原字形没被覆盖）
        ink = int(np.count_nonzero(alpha[:64, :64]))
        print('  %-8d %-30s 字形=%-5d 中文=%-5d 图集=%dx%d 界内=%s 原图角落像素=%d' %
              (pid, fa.name, len(fa.m_glyphInfoList), cjk, t.m_Width, t.m_Height,
               inside, ink))
        if cjk > 2400 and inside:
            ok += 1
    print('\n  %d/%d 个字体图集通过' % (ok, len(TARGETS)))


if __name__ == '__main__':
    main()
