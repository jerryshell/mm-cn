"""按 TextMesh Pro 1.0 的编码生成有符号距离场（SDF）字形。

对着游戏自带的图集做过校准：

    alpha = 0.5 + distance_px / (2 * _GradientScale)      其中 _GradientScale = padding + 1

字形表里的 ``width`` / ``height`` 是**墨迹**包围盒（不是包含外扩的距离场范围）。
这里所有度量（宽、高、左偏移、基线偏移、步进）都取自同一次 FreeType 光栅化结果，
所以图集内容与字形表不会出现偏差，这是中文能与西文基线保持一致的前提。

渲染只在字形自身的包围盒里进行，距离变换的成本从整张画布降到几十像素见方，
这是把 2400 多个字形的生成时间从几小时压到几十秒的关键。
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage


def glyph(font, ch, ss=12, pad_px=6):
    """生成一个字形，返回 ``(cell, metrics)``，失败时返回 ``(None, None)``。

    参数
    ----
    font    : PIL FreeType 字体，创建时字号是 ``目标字号 * ss``
    ss      : 超采样倍数，距离在放大图上算完再降采样回目标像素
    pad_px  : 距离场向墨迹外扩的像素数（= 字体的 padding，必须与 TMP 采样窗口一致）

    返回
    ----
    cell    : float32 数组，墨迹框四周各外扩 pad_px；``cell[pad, pad]`` 是墨迹左上角，
              零等值线正好落在 cell 的边界上
    metrics : 以目标像素为单位、相对基线的度量字典
    """
    size = font.size
    try:
        bbox = font.getbbox(ch)
    except Exception:                                # noqa: BLE001
        bbox = None
    if bbox is None:
        return None, None
    x0, y0, x1, y1 = bbox
    if x1 <= x0 or y1 <= y0:
        return None, None

    pad_hi = int(round(pad_px * ss))
    m = 2                                   # 防止光栅化边界与 bbox 差一两像素
    W = (x1 - x0) + 2 * pad_hi + 2 * m
    H = (y1 - y0) + 2 * pad_hi + 2 * m
    img = Image.new('L', (W, H), 0)
    ImageDraw.Draw(img).text((pad_hi + m - x0, pad_hi + m - y0), ch, font=font, fill=255)
    alpha = np.asarray(img, dtype=np.float32) / 255.0

    inside = alpha > 0.5
    nz = np.argwhere(inside)
    if not len(nz):
        return None, None
    iy0, ix0 = nz.min(0)
    iy1, ix1 = nz.max(0) + 1

    # 到字形的最短距离 / 到背景的最短距离，相减得到有符号距离（内部为正）
    d_out = ndimage.distance_transform_edt(~inside)
    d_in = ndimage.distance_transform_edt(inside)
    dist = (d_in - d_out) / ss              # 单位换回目标像素
    del alpha, inside, d_out, d_in

    # 裁到「墨迹框 + pad」
    X0 = max(0, ix0 - pad_hi)
    Y0 = max(0, iy0 - pad_hi)
    X1 = min(dist.shape[1], ix1 + pad_hi)
    Y1 = min(dist.shape[0], iy1 + pad_hi)
    sub = dist[Y0:Y1, X0:X1]
    Ht = sub.shape[0] // ss
    Wt = sub.shape[1] // ss
    cell = sub[:Ht * ss, :Wt * ss].reshape(Ht, ss, Wt, ss).mean(axis=(1, 3))

    ascent, _descent = font.getmetrics()
    baseline = pad_hi + m - y0 + ascent      # 基线在画布里的 y 坐标
    metrics = dict(
        width=(ix1 - ix0) / ss,
        height=(iy1 - iy0) / ss,
        xOffset=(ix0 - (pad_hi + m - x0)) / ss,
        # TMP 的 yOffset 是「从基线往上到墨迹顶部」的距离
        yOffset=(baseline - iy0) / ss,
        xAdvance=font.getlength(ch) / ss,
        # 墨迹在 cell 内的偏移（正常就是 pad_px，裁剪被边界夹住时会更小）
        ink_left=(ix0 - X0) / ss,
        ink_top=(iy0 - Y0) / ss,
    )
    return cell, metrics


def to_alpha(dist_px, gradient_scale):
    """把有符号距离（目标像素）编码成图集里的 8 位 alpha。"""
    a = 0.5 + dist_px / (2.0 * gradient_scale)
    return np.clip(a * 255.0 + 0.5, 0, 255).astype(np.uint8)
