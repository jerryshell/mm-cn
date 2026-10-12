"""检查仓库与发布包里的文件是否存在编码问题。

    python scripts/check_encoding.py

文本文件必须能用 UTF-8 解码（不含 BOM），批处理还额外要求 CRLF。
同时扫描常见的乱码特征 —— 一段字节能被 GBK 解码却不能被 UTF-8 解码，
说明它多半是遗留的本地编码；已经出现替换字符或乱码词则说明转换时出了问题。

退出码非 0 表示存在需要修改的项。
"""
import io
import os
import re
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from mmcore import setup_console

# 二进制文件不做文本检查
BINARY_EXT = {'.png', '.jpg', '.ico', '.zip', '.ttf', '.assets', '.resS', '.pyc'}

# 已知的乱码特征：替换字符、UTF-8 被当 GBK 解出来的典型字、GBK 被当 UTF-8 解出来的典型字
MOJIBAKE = ['\ufffd', '锟斤拷', '锘', '鈥', 'Ã¤', 'Ã¥', 'â€', 'Â¡', 'ï»¿']

# 允许用旧编码保存的文件（目前没有，保留成空集合以便日后例外）
LEGACY_ALLOWED = set()


def walk_zip(path):
    """把 zip 里的文件当成待检文件列出来。"""
    items = []
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            items.append((os.path.basename(info.filename),
                          z.read(info.filename)))
    return items


def check_bytes(name, data, expect_crlf=False):
    """返回问题列表。"""
    issues = []
    ext = os.path.splitext(name)[1].lower()
    if ext in BINARY_EXT:
        return issues

    if data.startswith(b'\xef\xbb\xbf'):
        issues.append('带 UTF-8 BOM（cmd 会把 BOM 当成命令的一部分）')
    if data.startswith(b'\xff\xfe') or data.startswith(b'\xfe\xff'):
        issues.append('带 UTF-16 BOM')

    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError as e:
        issues.append('不是合法 UTF-8：%s' % e)
        if _decodes(data, 'gbk'):
            issues.append('但能用 GBK 解码，属于遗留本地编码')
        return issues

    # 文档里可能会引用乱码样本作为反例，用 encoding-ok 标记跳过
    if 'encoding-ok' not in text:
        for pat in MOJIBAKE:
            if pat in text:
                issues.append('出现乱码特征 %r' % pat)
                break

    if expect_crlf:
        lf_only = data.count(b'\n') - data.count(b'\r\n')
        if lf_only:
            issues.append('有 %d 处裸 LF（批处理需要 CRLF）' % lf_only)
    return issues


def _decodes(data, enc):
    try:
        data.decode(enc)
        return True
    except UnicodeDecodeError:
        return False


def git_files():
    out = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT)
    return [f for f in out.decode('utf-8').split('\0') if f]


def main():
    setup_console()
    bad = 0

    print('=== 仓库内文件（git 已跟踪）===')
    for rel in sorted(git_files()):
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            print('  %-42s 文件缺失' % rel)
            bad += 1
            continue
        data = open(path, 'rb').read()
        issues = check_bytes(rel, data, expect_crlf=rel.lower().endswith('.bat'))
        state = '正常' if not issues else '; '.join(issues)
        if issues:
            bad += 1
        print('  %-42s %8d 字节  %s' % (rel, len(data), state))

    # 版本控制忽略但会影响发布的工作目录
    print('\n=== 发布相关（git 已忽略）===')
    extra = [os.path.join(ROOT, 'dist', '补丁信息.json')]
    for p in extra:
        if not os.path.exists(p):
            continue
        data = open(p, 'rb').read()
        issues = check_bytes(os.path.basename(p), data)
        state = '正常' if not issues else '; '.join(issues)
        if issues:
            bad += 1
        print('  %-42s %8d 字节  %s' % (os.path.basename(p), len(data), state))

    zips = [p for p in os.listdir(os.path.join(ROOT, 'dist'))
            if p.endswith('.zip')] if os.path.isdir(os.path.join(ROOT, 'dist')) else []
    for z in zips:
        print('\n=== release 包 %s ===' % z)
        for name, data in walk_zip(os.path.join(ROOT, 'dist', z)):
            issues = check_bytes(name, data, expect_crlf=name.lower().endswith('.bat'))
            state = '正常' if not issues else '; '.join(issues)
            if issues:
                bad += 1
            print('  %-42s %8d 字节  %s' % (name, len(data), state))

    print('\n合计 %d 处问题' % bad)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
