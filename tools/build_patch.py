"""生成汉化后的 resources.assets：写回翻译好的本地化表 + 重建字体图集。

    python tools/build_patch.py               # 完整构建（文本 + 字体），约 6 分钟
    python tools/build_patch.py --text-only   # 只重写文本，约 30 秒

``--text-only`` 会读 dist/ 里已有的补丁再改文本，所以可以「先建一次字体，
之后反复调翻译」，不用每次重算 2400 个字形。

输出写到 dist/resources.assets；``resources.assets.resS`` 不用改，
两个原本外挂的图集在补丁里改成了内联存储（旧数据留在 .resS 里，不影响加载）。
"""
import csv, io, json, os, sys, time

import numpy as np
import UnityPy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mmcore import (EXTRACT, BUILD, DIST, SHEETS,
                    LANG_COLS, DISPLAY_NAME, pristine_assets, setup_console)
from tmpfont import TMP_FontAsset
from cjkfont import TARGETS, build_one
from translate import load_cache, ckey
import glossary

OUT = DIST


def read_rows(path):
    with open(path, encoding='utf-8', newline='') as f:
        raw = f.read()
    r = csv.reader(io.StringIO(raw))
    hdr = next(r)
    return hdr, list(r)


def build_sheets(cache):
    """返回 {表名: CSV 文本}，其中所有语言列都换成了中文。

    游戏按 Steam 客户端语言选列，所以全部覆盖才能让补丁与用户的 Steam 设置无关。
    """
    out = {}
    missing = set()
    for name in SHEETS:
        path = os.path.join(EXTRACT, name + '.csv')
        if not os.path.exists(path):
            print('  !! 缺少表文件 %s' % path)
            continue
        hdr, rows = read_rows(path)
        if 'English' not in hdr:
            print('  !! %s 没有 English 列' % name)
            continue
        ei = hdr.index('English')
        cols = [hdr.index(c) for c in LANG_COLS if c in hdr]
        n, untranslated = 0, 0
        for row in rows:
            if len(row) != len(hdr):
                continue
            en = row[ei]
            if not en.strip():
                for c in cols:
                    row[c] = ''
                continue
            # 优先级：术语表整句覆盖 -> 翻译缓存 -> 短语修正
            zh = glossary.lookup(en)
            if zh is not None:
                n += 1
            else:
                zh = cache.get(ckey(en))
                if zh is None:
                    zh = en            # 实在没有译文时保留英文，不留空
                    untranslated += 1
                    missing.add(en)
                else:
                    zh = glossary.apply_fixes(zh)
                    n += 1
            for c in cols:
                row[c] = zh
        # 按 ID 覆盖（设置界面的语言列表等）
        if 'ID' in hdr:
            k = hdr.index('ID')
            for row in rows:
                if len(row) != len(hdr):
                    continue
                ov = glossary.ID_MAP.get(row[k])
                if ov is not None:
                    for c in cols:
                        row[c] = ov
        buf = io.StringIO()
        w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator='\n')
        w.writerow(hdr)
        for row in rows:
            w.writerow(row)
        out[name] = buf.getvalue()
        print('  %-16s 已翻译 %5d 行，%d 行保留英文' % (name, n, untranslated))
    if missing:
        with open(os.path.join(BUILD, 'untranslated.txt'), 'w', encoding='utf-8') as f:
            for s in sorted(missing):
                f.write(s.replace('\n', '\\n') + '\n')
        print('  %d 条落到英文，见 build/untranslated.txt' % len(missing))
    return out


def patch_textassets(sf, sheets):
    """就地替换本地化 TextAsset。"""
    done = {}
    for pid, o in sf.objects.items():
        if o.type.name != 'TextAsset':
            continue
        d = o.read()
        if d.m_Name in sheets and d.m_Name not in done:
            d.m_Script = sheets[d.m_Name]
            o.save_typetree(d)
            done[d.m_Name] = pid
    return done


def collect_chars(cache):
    """收集译文里用到的全部非 ASCII 字符，再加上中文标点和基本拉丁字母。"""
    chars = set()
    for v in cache.values():
        for ch in v:
            if ord(ch) > 0x7f:
                chars.add(ch)
    # 即使当前译文没用到，也把常用中文标点先放进去，避免以后改文案缺字
    chars.update('\u3002\uff0c\uff01\uff1f\uff1b\uff1a\u201c\u201d\u2018\u2019\uff08\uff09'
                 '\u3001\u2014\u2026\u00b7\uff05\uff0b\uff0d\uff0f\uff1d\uff1c\uff1e')
    chars.update('0123456789')
    chars.update('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')
    return chars


def set_alpha8_texture(t, canvas):
    """把 uint8 图集写回 Alpha8 的 Texture2D（Unity 内部是上下翻转存的）。

    这里直接改字段，没有走 ``t.image = ...``：UnityPy 把 Alpha8 映射成 PIL 的 'A' 模式，
    而 numpy/ImageDraw 生成的图像没法转成 'A'。
    """
    t.m_Width = int(canvas.shape[1])
    t.m_Height = int(canvas.shape[0])
    data = np.ascontiguousarray(canvas[::-1]).tobytes()
    t.image_data = data
    t.m_CompleteImageSize = len(data)
    t.m_TextureFormat = 1              # TextureFormat.Alpha8
    if getattr(t, 'm_MipMap', None) is not None:
        t.m_MipMap = False
    if getattr(t, 'm_MipCount', None) is not None:
        t.m_MipCount = 1
    sd = getattr(t, 'm_StreamData', None)
    if sd is not None:
        # 原本外挂到 .resS 的图集改成内联，否则会去读旧数据
        sd.path = ''
        sd.offset = 0
        sd.size = 0


def patch_fonts(sf, chars, verbose=True):
    """给每个 UI 字体资产补上中文字形，返回统计信息。"""
    # 先建 path_id -> 字体资产 的索引
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
        # fileID == 1 表示脚本引用指向外部的 Assembly-CSharp-firstpass
        if fa.name and int.from_bytes(raw[16:20], 'little') == 1:
            fonts[pid] = (o, fa, raw)

    stats = {}
    for pid, cfg in TARGETS.items():
        if pid not in fonts:
            continue
        o, fa, _raw = fonts[pid]
        atlas_pid = fa.atlas[1]
        tex = sf.objects.get(atlas_pid)
        if tex is None or tex.type.name != 'Texture2D':
            print('  !! 字体 %d 的图集 %s 不存在' % (pid, atlas_pid))
            continue
        t = tex.read()
        if verbose:
            print('  字体 %-30s 图集 %d %s' % (fa.name, atlas_pid, t.m_Name))
        arr = np.array(t.image)
        if arr.ndim == 3:
            arr = arr[:, :, 3] if arr.shape[2] == 4 else arr[:, :, 0]
        arr = arr.astype(np.uint8)

        t0 = time.time()
        canvas, added, skipped = build_one(pid, fa, arr, cfg, chars, verbose=verbose)
        o.set_raw_data(fa.write_bytes())
        set_alpha8_texture(t, canvas)
        tex.save_typetree(t)
        stats[pid] = dict(name=fa.name, added=added, skipped=len(skipped),
                          size=(fa.m_fontInfo.AtlasWidth, fa.m_fontInfo.AtlasHeight),
                          secs=round(time.time() - t0, 1))
        if verbose:
            print('      %.1fs' % (time.time() - t0))
    return stats


def main():
    setup_console()
    text_only = '--text-only' in sys.argv
    cache = load_cache()
    print('翻译缓存：%d 条' % len(cache))
    os.makedirs(OUT, exist_ok=True)

    print('构建本地化表 ...')
    sheets = build_sheets(cache)
    chars = collect_chars(cache)
    print('需要的中文字符数：%d' % len(chars))

    # --text-only 时以上一次的补丁为输入，这样字体不用重算
    previous = os.path.join(OUT, 'resources.assets')
    src = previous if text_only and os.path.exists(previous) else pristine_assets()
    print('读取 %s ...' % src)
    env = UnityPy.load(src)
    sf = env.file

    print('写入本地化表 ...')
    done = patch_textassets(sf, sheets)
    print('  已替换：%s' % '、'.join('%s(%d)' % (k, v) for k, v in done.items()))

    if text_only:
        print('--text-only：跳过字体重建')
    else:
        print('重建字体图集 ...')
        stats = patch_fonts(sf, chars)
        with open(os.path.join(BUILD, 'font_stats.json'), 'w') as f:
            json.dump(stats, f, indent=1)

    print('保存 ...')
    sf_ = env.file
    data = sf_.save()
    # 不能直接用 sf_.name：输入可能是 resources.assets.orig，
    # 照搬名字会生成 dist/resources.assets.orig，安装脚本就找不到补丁了
    name = 'resources.assets'
    with open(os.path.join(OUT, name), 'wb') as f:
        f.write(data)
    print('  %s  %.1f MB' % (name, len(data) / 1048576))
    # UnityPy 会把加载进来的依赖文件一起写出去，删掉，它们没有变化
    for extra in ('globalgamemanagers.assets', 'unity_builtin_extra',
                  'sharedassets0.assets'):
        p = os.path.join(OUT, extra)
        if os.path.exists(p):
            os.remove(p)


if __name__ == '__main__':
    main()
