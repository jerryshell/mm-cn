"""Unity 序列化结构里用到的二进制读写小工具。

Unity 的 assets 文件是大端/小端混合的二进制流，TypeTree 里每个字段按自身大小对齐，
字符串是「4 字节长度 + UTF-8 内容 + 补齐到 4 字节」。这里只实现改写字体资产需要的那几种。
"""
import struct


class Reader:
    """顺序读取字节流，带 Unity 风格的 4 字节对齐。"""

    def __init__(self, data, pos=0):
        self.d = data
        self.p = pos

    def align(self, n=4):
        """把读取位置推进到 n 的整数倍。"""
        r = self.p % n
        if r:
            self.p += n - r

    def u8(self):
        v = self.d[self.p]; self.p += 1; return v

    def i32(self):
        v = struct.unpack_from('<i', self.d, self.p)[0]; self.p += 4; return v

    def u32(self):
        v = struct.unpack_from('<I', self.d, self.p)[0]; self.p += 4; return v

    def i64(self):
        v = struct.unpack_from('<q', self.d, self.p)[0]; self.p += 8; return v

    def f32(self):
        v = struct.unpack_from('<f', self.d, self.p)[0]; self.p += 4; return v

    def boolean(self):
        v = self.d[self.p]; self.p += 1; return v != 0

    def pptr(self):
        """PPtr：4 字节 fileID + 8 字节 pathID，fileID=0 表示指向本文件。"""
        f = self.i32(); p = self.i64(); return (f, p)

    def string(self):
        n = self.i32()
        s = self.d[self.p:self.p + n]
        self.p += n
        self.align(4)
        return s.decode('utf-8', 'replace')

    def take(self, n):
        v = self.d[self.p:self.p + n]; self.p += n; return v


# ---------------------------------------------------------------- 写入辅助
# 这些函数都往一个 bytearray 里追加内容，方便按顺序拼出对象

def w_align(buf, n=4):
    while len(buf) % n:
        buf.append(0)


def w_i32(buf, v):
    buf += struct.pack('<i', v)


def w_i64(buf, v):
    buf += struct.pack('<q', v)


def w_u32(buf, v):
    buf += struct.pack('<I', v)


def w_f32(buf, v):
    buf += struct.pack('<f', v)


def w_str(buf, s):
    b = s.encode('utf-8')
    w_i32(buf, len(b))
    buf += b
    w_align(buf, 4)


def w_pptr(buf, f, p):
    w_i32(buf, f)
    w_i64(buf, p)
