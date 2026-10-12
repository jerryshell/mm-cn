"""给《Motorsport Manager》的 TMP 字体图集补上中文字形。

每个目标字体资产的处理方式一样：

1. 原图集内容（必要时先按 ``k`` 缩放）**像素级保留**在画布左上角；
2. 剩余空间用货架装箱算法（``Shelf``）排入中文和全角标点的字形；
3. 重写字形表，追加新字形的度量。

``TARGETS`` 里的 ``k`` 是为了控制显存：PointSize 越大，同样的字号需要的字形尺寸越大，
图集也越大。对几个超大字号的标题字体做了缩比，缩比后 PointSize 同步变小，
显示尺寸不变，只是源分辨率低一些。
"""
import os, sys

import numpy as np
from PIL import Image, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tmpfont import Glyph
from sdf import glyph as sdf_glyph, to_alpha

# 中文字形来源。优先用系统装的思源黑体可变字体，也可以放在 assets/ 里
if os.path.exists(r'C:\Windows\Fonts\NotoSansSC-VF.ttf'):
    CJK_VF = r'C:\Windows\Fonts\NotoSansSC-VF.ttf'
else:
    from mmcore import ASSETS
    CJK_VF = os.path.join(ASSETS, 'NotoSansSC-VF.ttf')

# 距离场超采样倍数。实测 4 倍与 12 倍相比，和游戏自带字形的误差几乎一样，
# 但快 10 倍（2400 个字形从几分钟降到二十秒）
SS = 4

# 字体资产 path_id -> 图集尺寸 / 缩放系数 / 中文字重 / 中文相对西文的字号比例
#   k      : 原图集与全部度量一起缩小的系数
#   em     : 中文字形相对西文 em 的比例，让中文不超出西文的行高
TARGETS = {
    141966: dict(size=(4096, 4096), k=1.00, weight='Medium',  em=0.95),
    141964: dict(size=(4096, 4096), k=1.00, weight='Bold',    em=0.95),
    141965: dict(size=(4096, 4096), k=1.00, weight='Regular', em=0.95),
    141967: dict(size=(4096, 4096), k=1.00, weight='Bold',    em=0.95),
    141992: dict(size=(4096, 4096), k=1.00, weight='Bold',    em=0.95),
    141993: dict(size=(4096, 4096), k=1.00, weight='Regular', em=0.95),
    141994: dict(size=(4096, 4096), k=1.00, weight='Medium',  em=0.95),
    141969: dict(size=(4096, 4096), k=0.60, weight='Regular', em=0.95),
    141987: dict(size=(4096, 4096), k=0.60, weight='Regular', em=0.95),
    141968: dict(size=(4096, 4096), k=0.25, weight='Light',   em=0.95),
    141970: dict(size=(4096, 4096), k=0.25, weight='Thin',    em=0.95),
}


class Shelf:
    """最简单的货架装箱：从左往右排，排满一行就往下开一行。"""

    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.cx, self.cy, self.rh = x0, y0, 0      # 当前 x、当前行 y、当前行高

    def place(self, w, h):
        """放一块 w×h 的区域，放不下返回 None。"""
        if self.cx + w > self.x1:
            self.cx = self.x0
            self.cy += self.rh
            self.rh = 0
        if self.cy + h > self.y1:
            return None
        p = (self.cx, self.cy)
        self.cx += w
        self.rh = max(self.rh, h)
        return p


def resample_font(fa, atlas, k):
    """把字体资产（图集 + 字形表 + 全局度量）整体缩小 k 倍，就地修改。"""
    if k == 1.0:
        return atlas
    img = Image.fromarray(atlas, 'L')
    nw = max(1, int(round(img.width * k)))
    nh = max(1, int(round(img.height * k)))
    img = img.resize((nw, nh), Image.BOX)
    for g in fa.m_glyphInfoList:
        g.x = round(g.x * k)
        g.y = round(g.y * k)
        g.width *= k
        g.height *= k
        g.xOffset *= k
        g.yOffset *= k
        g.xAdvance *= k
    fi = fa.m_fontInfo
    for f in ('PointSize', 'LineHeight', 'Baseline', 'Ascender', 'CapHeight',
              'Descender', 'CenterLine', 'SuperscriptOffset', 'SubscriptOffset',
              'SubSize', 'Underline', 'UnderlineThickness', 'strikethrough',
              'strikethroughThickness', 'TabWidth', 'Padding'):
        setattr(fi, f, getattr(fi, f) * k)
    fi.AtlasWidth = nw
    fi.AtlasHeight = nh
    return np.asarray(img).copy()


def build_one(pid, fa, atlas, cfg, chars, verbose=True):
    """给一个字体资产补上 ``chars`` 里缺失的字形。

    返回 ``(新图集数组, 新增字形数, 跳过的字符列表)``；``fa`` 会被就地修改。
    """
    atlas = resample_font(fa, atlas, cfg['k'])
    pad = fa.m_fontInfo.Padding
    gscale = pad + 1.0                # 与材质的 _GradientScale 对应
    size = fa.m_fontInfo.PointSize
    em = cfg.get('em', 1.0)
    # 距离场外扩量必须**正好**等于 padding：TMP 采样窗口是 [x-pad, x+w+pad]，
    # 多出来的一像素会把相邻字形采样进来
    inkpad = pad

    W, H = cfg['size']
    canvas = np.zeros((H, W), np.uint8)
    if atlas.shape[0] > H or atlas.shape[1] > W:
        raise ValueError('目标图集 %dx%d 比源图集 %s 还小' % (W, H, atlas.shape))
    canvas[:atlas.shape[0], :atlas.shape[1]] = atlas
    ow, oh = atlas.shape[1], atlas.shape[0]
    # 原图集右方与下方各留一个货架，先把右侧填满再填下方
    shelves = [Shelf(ow + 2, 0, W, H), Shelf(0, oh + 2, W, H)]

    existing = {int(g.id) for g in fa.m_glyphInfoList}

    mfont = ImageFont.truetype(CJK_VF, int(round(size * SS)))
    try:
        mfont.set_variation_by_name(cfg['weight'])
    except Exception as e:                           # noqa: BLE001
        print('    !! 字重 %s 设置失败：%s' % (cfg['weight'], e))

    added, skipped = 0, []
    for ch in sorted(set(chars)):
        if ord(ch) in existing:                      # 原有字形不动
            continue
        cell, m = sdf_glyph(mfont, ch, ss=SS, pad_px=inkpad)
        if cell is None:
            skipped.append(ch)
            continue
        if em != 1.0:
            # 注意必须用 'F' 模式缩放浮点距离场；用 'L' 会把距离当亮度重映射，字形直接糊掉
            tw = max(1, int(round(cell.shape[1] * em)))
            th = max(1, int(round(cell.shape[0] * em)))
            cell = np.asarray(
                Image.fromarray(cell.astype(np.float32), 'F').resize((tw, th), Image.BOX),
                dtype=np.float32)
            for k2 in ('width', 'height', 'xOffset', 'yOffset', 'xAdvance',
                       'ink_left', 'ink_top'):
                m[k2] *= em
        cw, chh = cell.shape[1], cell.shape[0]
        pos = None
        for s in shelves:
            # 留 3 像素间隙：字形宽度是浮点数，x + width 可能比格子末端多出零点几像素
            pos = s.place(cw + 3, chh + 3)
            if pos:
                break
        if pos is None:
            skipped.append(ch)
            continue
        x, y = pos
        canvas[y:y + chh, x:x + cw] = to_alpha(cell, gscale)
        fa.m_glyphInfoList.append(Glyph(
            id=ord(ch),
            x=float(x) + m['ink_left'],
            y=float(y) + m['ink_top'],
            width=m['width'], height=m['height'],
            xOffset=m['xOffset'], yOffset=m['yOffset'],
            xAdvance=m['xAdvance'], scale=1.0))
        added += 1

    fa.m_fontInfo.AtlasWidth = W
    fa.m_fontInfo.AtlasHeight = H
    fa.m_fontInfo.CharacterCount = len(fa.m_glyphInfoList)
    if verbose:
        print('    +%d 个字形（跳过 %d），图集 %dx%d，pt=%.2f pad=%.2f' %
              (added, len(skipped), W, H, fa.m_fontInfo.PointSize, pad))
    return canvas, added, skipped
