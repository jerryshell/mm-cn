"""TextMesh Pro 1.0.x 的 ``TMP_FontAsset`` 序列化（针对 Unity 5.3 的 assets 格式）。

游戏里的字体资产是 MonoBehaviour，没有可用的 TypeTree，所以这里按 C# 类的字段顺序
手工读写。**读写必须严格对称**，否则后面所有字段都会错位。校验方法是拿原文件
读一遍再写一遍，二进制的 MD5 必须完全一致（`tools/verify.py` 会检查）。

两个容易踩的点：

* ``FontCreationSetting`` 末尾的 ``bool`` 后面**没有** 4 字节对齐；
* 数据结构之后还有一小段未知的尾部字节（``trailing``），必须原样带回去。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unitybin import (Reader, w_align, w_i32, w_i64, w_u32, w_f32, w_str, w_pptr)


class FaceInfo:
    """字体的全局度量。PointSize 是生成图集时的字号，Padding 是距离场外扩量。"""

    FIELDS = ['Name', 'PointSize', 'Scale', 'CharacterCount', 'LineHeight', 'Baseline',
              'Ascender', 'CapHeight', 'Descender', 'CenterLine', 'SuperscriptOffset',
              'SubscriptOffset', 'SubSize', 'Underline', 'UnderlineThickness',
              'strikethrough', 'strikethroughThickness', 'TabWidth', 'Padding',
              'AtlasWidth', 'AtlasHeight']

    def __init__(self):
        for f in self.FIELDS:
            setattr(self, f, 0)

    @classmethod
    def read(cls, r):
        s = cls()
        s.Name = r.string()
        for f in cls.FIELDS[1:]:
            setattr(s, f, r.f32())
        return s

    def write(self, buf):
        w_str(buf, self.Name)
        for f in self.FIELDS[1:]:
            w_f32(buf, getattr(self, f))


class Glyph:
    """字形表里的一项：id 是 Unicode 码点，其余是目标像素单位的度量。"""

    FLOAT_FIELDS = ['x', 'y', 'width', 'height', 'xOffset', 'yOffset', 'xAdvance', 'scale']

    def __init__(self, **kw):
        self.id = kw.get('id', 0)
        for f in self.FLOAT_FIELDS:
            setattr(self, f, kw.get(f, 0))

    @classmethod
    def read(cls, r):
        s = cls()
        s.id = r.i32()
        for f in cls.FLOAT_FIELDS:
            setattr(s, f, r.f32())
        return s

    def write(self, buf):
        w_i32(buf, self.id)
        for f in self.FLOAT_FIELDS:
            w_f32(buf, getattr(self, f))

    def __repr__(self):
        return 'G(%d)' % self.id


class KerningPair:
    """一对字距调整（本例中游戏未使用，读到什么写回什么）。"""

    def __init__(self, l, r, o):
        self.AscII_Left = l
        self.AscII_Right = r
        self.XadvanceOffset = o

    @classmethod
    def read(cls, r):
        return cls(r.i32(), r.i32(), r.f32())

    def write(self, buf):
        w_i32(buf, self.AscII_Left)
        w_i32(buf, self.AscII_Right)
        w_f32(buf, self.XadvanceOffset)


class FontCreationSetting:
    """TMP 记录「这个字体是怎么生成的」的参数，改写图集时保持原值。"""

    def __init__(self, **kw):
        self.fontSourcePath = kw.get('fontSourcePath', '')
        for f in ['fontSizingMode', 'fontSize', 'fontPadding', 'fontPackingMode',
                  'fontAtlasWidth', 'fontAtlasHeight', 'fontCharacterSet', 'fontStyle',
                  'fontRenderMode']:
            setattr(self, f, kw.get(f, 0))
        self.fontStlyeModifier = kw.get('fontStlyeModifier', 0.0)
        self.fontKerning = kw.get('fontKerning', False)

    @classmethod
    def read(cls, r):
        s = cls()
        s.fontSourcePath = r.string()
        for f in ['fontSizingMode', 'fontSize', 'fontPadding', 'fontPackingMode',
                  'fontAtlasWidth', 'fontAtlasHeight', 'fontCharacterSet', 'fontStyle']:
            setattr(s, f, r.i32())
        s.fontStlyeModifier = r.f32()
        s.fontRenderMode = r.i32()
        s.fontKerning = r.boolean()
        return s

    def write(self, buf):
        w_str(buf, self.fontSourcePath)
        for f in ['fontSizingMode', 'fontSize', 'fontPadding', 'fontPackingMode',
                  'fontAtlasWidth', 'fontAtlasHeight', 'fontCharacterSet', 'fontStyle']:
            w_i32(buf, getattr(self, f))
        w_f32(buf, self.fontStlyeModifier)
        w_i32(buf, self.fontRenderMode)
        buf.append(1 if self.fontKerning else 0)


class FontWeight:
    """粗体 / 斜体映射表的一项，指向另外的字体资产（本例中都是空引用）。"""

    def __init__(self, reg=None, ital=None):
        self.regularTypeface = reg or (0, 0)
        self.italicTypeface = ital or (0, 0)

    @classmethod
    def read(cls, r):
        return cls(r.pptr(), r.pptr())

    def write(self, buf):
        w_pptr(buf, *self.regularTypeface)
        w_pptr(buf, *self.italicTypeface)


class TMP_FontAsset:
    """一个完整的字体资产：字形表 + 图集引用 + 材质 + 生成参数。"""

    def __init__(self):
        self.game_object = (0, 0)
        self.enabled = 1
        self.script = (0, 0)
        self.name = ''
        # TMP_Asset
        self.hashCode = 0
        self.material = (0, 0)
        self.materialHashCode = 0
        # TMP_FontAsset
        self.fontAssetType = 1
        self.m_fontInfo = FaceInfo()
        self.atlas = (0, 0)
        self.m_glyphInfoList = []
        self.m_kerningInfo = []
        self.m_kerningPair = KerningPair(0, 0, 0.0)
        self.fallbackFontAssets = []
        self.fontCreationSettings = FontCreationSetting()
        self.fontWeights = [FontWeight() for _ in range(10)]
        self.normalStyle = 0.0
        self.normalSpacingOffset = 0.0
        self.boldStyle = 0.75
        self.boldSpacing = 7.0
        self.italicStyle = 35
        self.tabSize = 10
        self.m_oldTabSize = 0

    def read_bytes(self, data):
        """从 MonoBehaviour 的原始字节里解析出全部字段。"""
        r = Reader(data)
        self.game_object = r.pptr()
        self.enabled = r.u8()
        r.align(4)
        self.script = r.pptr()
        self.name = r.string()
        self.hashCode = r.i32()
        self.material = r.pptr()
        self.materialHashCode = r.i32()
        self.fontAssetType = r.i32()
        self.m_fontInfo = FaceInfo.read(r)
        self.atlas = r.pptr()
        n = r.i32()
        self.m_glyphInfoList = [Glyph.read(r) for _ in range(n)]
        n = r.i32()
        self.m_kerningInfo = [KerningPair.read(r) for _ in range(n)]
        self.m_kerningPair = KerningPair.read(r)
        n = r.i32()
        self.fallbackFontAssets = [r.pptr() for _ in range(n)]
        self.fontCreationSettings = FontCreationSetting.read(r)
        self.fontWeights = [FontWeight.read(r) for _ in range(10)]
        self.normalStyle = r.f32()
        self.normalSpacingOffset = r.f32()
        self.boldStyle = r.f32()
        self.boldSpacing = r.f32()
        self.italicStyle = r.u8()
        self.tabSize = r.u8()
        self.m_oldTabSize = r.u8()
        r.align(4)
        # 后面还有一段用途未知的字节，原样保存以便写回
        self.trailing = r.take(len(data) - r.p)
        return self

    def write_bytes(self):
        """按同样的顺序写回去。字段顺序必须与 read_bytes 完全一致。"""
        buf = bytearray()
        w_pptr(buf, *self.game_object)
        buf.append(self.enabled)
        w_align(buf, 4)
        w_pptr(buf, *self.script)
        w_str(buf, self.name)
        w_i32(buf, self.hashCode)
        w_pptr(buf, *self.material)
        w_i32(buf, self.materialHashCode)
        w_i32(buf, self.fontAssetType)
        self.m_fontInfo.write(buf)
        w_pptr(buf, *self.atlas)
        w_i32(buf, len(self.m_glyphInfoList))
        for g in self.m_glyphInfoList:
            g.write(buf)
        w_i32(buf, len(self.m_kerningInfo))
        for k in self.m_kerningInfo:
            k.write(buf)
        self.m_kerningPair.write(buf)
        w_i32(buf, len(self.fallbackFontAssets))
        for f in self.fallbackFontAssets:
            w_pptr(buf, *f)
        self.fontCreationSettings.write(buf)
        for f in self.fontWeights:
            f.write(buf)
        w_f32(buf, self.normalStyle)
        w_f32(buf, self.normalSpacingOffset)
        w_f32(buf, self.boldStyle)
        w_f32(buf, self.boldSpacing)
        buf.append(self.italicStyle)
        buf.append(self.tabSize)
        buf.append(self.m_oldTabSize)
        w_align(buf, 4)
        buf += self.trailing
        return bytes(buf)
