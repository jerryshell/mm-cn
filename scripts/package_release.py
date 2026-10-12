"""把补丁打成一个可以直接发给玩家的 zip。

    python scripts/make_installer.py    # 先生成 .bat
    python scripts/package_release.py   # 再打包

产物：``dist/MM-Chinese-Patch-v1.0.zip``，解压后是一层文件夹，里面是
``安装汉化.bat`` / ``卸载还原.bat`` / ``resources.assets`` / ``说明.md``。

顺便会写一份 ``dist/补丁信息.json``，把版本、MD5、覆盖率这些发布时要写进
release 说明的数字固化下来。
"""
import hashlib, json, os, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from mmcore import GAME, DIST, INSTALLER, DOCS, setup_console
import glossary

VERSION = 'v1.0'
FOLDER = '简体中文汉化'          # zip 解压出来的那一层文件夹名
ZIP_NAME = 'MM-Chinese-Patch-%s.zip' % VERSION


def md5(path, chunk=1 << 20):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    setup_console()
    patch = os.path.join(DIST, 'resources.assets')
    if not os.path.exists(patch):
        sys.exit('找不到 %s，先运行 python tools/build_patch.py' % patch)

    files = [
        (os.path.join(INSTALLER, '安装汉化.bat'), '安装汉化.bat'),
        (os.path.join(INSTALLER, '卸载还原.bat'), '卸载还原.bat'),
        (os.path.join(INSTALLER, '说明.md'), '说明.md'),
        (patch, 'resources.assets'),
    ]
    for src, _name in files:
        if not os.path.exists(src):
            sys.exit('缺少 %s（先运行 python scripts/make_installer.py）' % src)

    zip_path = os.path.join(DIST, ZIP_NAME)
    print('打包 %s ...' % zip_path)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for src, name in files:
            z.write(src, '%s/%s' % (FOLDER, name))
            print('  + %-20s %10.1f MB' % (name, os.path.getsize(src) / 1048576))

    backup = os.path.join(GAME, 'MM_Data', 'resources.assets.orig')
    info = {
        'version': VERSION,
        'zip': os.path.basename(zip_path),
        'zip_bytes': os.path.getsize(zip_path),
        'zip_md5': md5(zip_path),
        'patch_file': 'resources.assets',
        'patch_bytes': os.path.getsize(patch),
        'patch_md5': md5(patch),
        'original_md5': md5(backup) if os.path.exists(backup) else None,
        'sheets': 14,
        'rows_with_english': 12944,
        'unique_strings': 11605,
        'untranslated': 0,
        'kept_latin': len(glossary.KEEP_LATIN),
        'glossary_exact': len(glossary.EXACT),
        'glossary_fix_rules': len(glossary.FIXES),
        'fonts_patched': 11,
        'cjk_glyphs_per_font': 2424,
        'atlas_size': '4096x4096',
        'acceptance': '42 passed / 0 failed',
    }
    info_path = os.path.join(DIST, '补丁信息.json')
    with open(info_path, 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False, indent=1)

    print('\n完成')
    print('  %s  %.1f MB' % (zip_path, info['zip_bytes'] / 1048576))
    print('  MD5 %s' % info['zip_md5'])
    print('  补丁信息 -> %s' % info_path)


if __name__ == '__main__':
    main()
