"""按 TextMesh Pro 的排版算法把中文渲染成图片，用来验证字体数据。

    python tools/verify.py     # 先确认 dist/ 里的产物结构正常
    python tools/preview.py    # 出图

这是对「字形表 + 图集 + alpha 编码」三者的端到端验证：这里复刻了 TMP_Text 的
四边形摆放、UV 计算和距离场解码，所以图上看到的就是游戏里画出来的效果。
不启动游戏就能确认中文的字形、基线、字距是否正常。
"""
import os, sys

import numpy as np
import UnityPy
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mmcore import DIST, BUILD, DOCS, setup_console
from tmpfont import TMP_FontAsset

PATCHED = os.path.join(DIST, 'resources.assets')

# (字体 path_id, 显示名, 字号, 样例文本)
SAMPLES = [
    (141966, 'CooperHewitt-Medium SDF', 24, '车手已经完成设计 Design'),
    (141966, 'CooperHewitt-Medium SDF', 18, '轮胎磨损严重，请进站更换轮胎！'),
    (141964, 'CooperHewitt-Bold', 22, '中国大奖赛 排位赛 Q2'),
    (141969, 'Mission Gothic Regular SDF', 28, '赛季冠军：车队积分榜'),
    (141987, 'LiberationSans SDF', 18, '模拟结果已保存 Simulation 12345'),
]


def load_fonts(env):
    """把 assets 里所有 TMP 字体资产抓出来，返回 {path_id: 字体对象}。"""
    fonts = {}
    for pid, o in env.file.objects.items():
        if o.type.name != 'MonoBehaviour':
            continue
        raw = o.get_raw_data()
        if len(raw) < 60:
            continue
        try:
            fa = TMP_FontAsset().read_bytes(raw)
        except Exception:                            # noqa: BLE001
            continue
        if fa.name and fa.atlas[1]:
            fonts[pid] = fa
    return fonts


def render(env, fa, text, font_size=24.0, spacing=0.0):
    """把一行文本渲染成灰度数组（0=背景，1=最亮）。

    对照 TMP_Text.SaveGlyphVertexInfo 与 FillCharacterVertexBuffers：

    * 四边形宽高 = 字形表里的 width / height，位置由 xOffset / yOffset 相对基线定；
    * UV 采样范围是 [x-pad, x+width+pad] × [y-pad, y+height+pad]；
    * 图集里的 alpha 已经就是「距离场解码后的覆盖率」，直接采样即可。
    """
    fi = fa.m_fontInfo
    t = env.file.objects[fa.atlas[1]].read()
    arr = np.asarray(t.image)
    atlas = arr[:, :, 3].astype(np.float32) / 255.0   # t.image 是上到下
    H, W = atlas.shape
    glyphs = {int(g.id): g for g in fa.m_glyphInfoList}
    scale = font_size / fi.PointSize * fi.Scale

    pad = fi.Padding
    adv = [g.xAdvance * scale + spacing for c in text
           if (g := glyphs.get(ord(c))) is not None]
    width = int(sum(adv)) + 8
    height = int(fi.LineHeight * scale) + 8
    out = np.zeros((height, width), np.float32)

    x = 4.0
    baseline = int(4 + fi.Ascender * scale)
    for ch in text:
        g = glyphs.get(ord(ch))
        if g is None:                                # 缺字：留半个字宽的空位
            x += font_size * 0.5
            continue
        gw = g.width * scale
        gh = g.height * scale
        if gw >= 1 and gh >= 1:
            u0 = (g.x - pad) / W
            u1 = (g.x + g.width + pad) / W
            v0 = 1.0 - (g.y + g.height + pad) / H
            v1 = 1.0 - (g.y - pad) / H
            px0 = int(round(x + g.xOffset * scale))
            py0 = int(round(baseline - g.yOffset * scale))
            iw = max(1, int(round(gw)))
            ih = max(1, int(round(gh)))
            xs = np.clip((u0 + (np.arange(iw) + 0.5) / iw * (u1 - u0)) * W,
                         0, W - 1).astype(int)
            # Unity 的 v 是从下往上，而图集数组是从上往下，这里要翻过来取行
            v = v1 - (np.arange(ih) + 0.5) / ih * (v1 - v0)
            ys = np.clip((1.0 - v) * H, 0, H - 1).astype(int)
            patch = atlas[np.ix_(ys, xs)]
            dx0, dy0 = max(0, px0), max(0, py0)
            dx1, dy1 = min(width, px0 + iw), min(height, py0 + ih)
            if dx1 > dx0 and dy1 > dy0:
                out[dy0:dy1, dx0:dx1] = np.maximum(
                    out[dy0:dy1, dx0:dx1],
                    patch[dy0 - py0:dy1 - py0, dx0 - px0:dx1 - px0])
        x += g.xAdvance * scale + spacing
    return out


def main():
    setup_console()
    env = UnityPy.load(PATCHED)
    fonts = load_fonts(env)
    rows = []
    for pid, name, size, text in SAMPLES:
        fa = fonts.get(pid)
        if fa is None:
            print('!! 找不到字体 %d (%s)' % (pid, name))
            continue
        rows.append(render(env, fa, text, size))
        print('%-30s 共 %d 个字形' % (name, len(fa.m_glyphInfoList)))
    if not rows:
        sys.exit('没有可用的字体')

    wid = max(r.shape[1] for r in rows)
    tot = sum(r.shape[0] + 6 for r in rows)
    canvas = np.zeros((tot, wid), np.float32)
    y = 0
    for r in rows:
        canvas[y:y + r.shape[0], :r.shape[1]] = r
        y += r.shape[0] + 6
    out = (255 - np.clip(canvas, 0, 1) * 255).astype(np.uint8)
    img = Image.fromarray(out).resize((out.shape[1] * 2, out.shape[0] * 2),
                                      Image.NEAREST)
    for p in (os.path.join(BUILD, 'font_preview.png'),
              os.path.join(DOCS, '字体效果预览.png')):
        img.save(p)
        print('已生成 %s' % p)


if __name__ == '__main__':
    main()
