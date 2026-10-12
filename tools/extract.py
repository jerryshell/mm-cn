"""把流水线需要的游戏资源从 resources.assets 里导出来。

产出（都在 .gitignore 忽略的目录里）：

* ``extract/<表名>.csv``          14 张本地化表，内容原样不动
* ``build/textasset_map.json``    表名 -> TextAsset path id
* ``assets/atlas/<pid>.png``      游戏自带的 TMP 字体图集（字形校准用）
* ``assets/ttf/<pid>_<名字>.ttf`` 旧版 Unity Font 里内嵌的 TTF

这些文件都不进仓库：它们可以从任意一份正版游戏里重新生成，
只在本地用于构建和校验补丁。

**注意**：装过汉化之后游戏目录里的 resources.assets 已经是中文的了，
所以这里会优先使用安装脚本留下的原版备份 resources.assets.orig；
两个文件都是汉化版时会直接报错退出，避免把中文当成英文原文导出。
"""
import json, os, sys

import UnityPy
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mmcore import EXTRACT, ASSETS, BUILD, SHEETS, pristine_assets, setup_console

def dump_sheets(sf):
    """导出 14 张本地化表，同时记下每张表来自哪个 TextAsset。

    注意 assets 里有两个都叫 "Challenges" 的 TextAsset：一个是本地化表，
    另一个是挑战模式的数据表。靠「表头里有 English 列」来区分，
    比按文件大小猜可靠。
    """
    wanted = set(SHEETS)
    found = {}
    for pid, o in sf.objects.items():
        if o.type.name != 'TextAsset':
            continue
        d = o.read()
        if d.m_Name not in wanted:
            continue
        s = d.m_Script
        if isinstance(s, bytes):
            s = s.decode('utf-8')
        if 'English' not in s.split('\n', 1)[0]:
            continue                       # 不是本地化表
        found[d.m_Name] = (pid, s)
    os.makedirs(EXTRACT, exist_ok=True)
    mapping = {}
    for name, (pid, text) in sorted(found.items()):
        path = os.path.join(EXTRACT, name + '.csv')
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
        mapping[name] = pid
        print('  %-14s pid=%-6d %8d bytes' % (name, pid, len(text)))
    os.makedirs(BUILD, exist_ok=True)
    with open(os.path.join(BUILD, 'textasset_map.json'), 'w') as f:
        json.dump(mapping, f, indent=1)
    return mapping


def dump_atlases(sf):
    """导出游戏自带的 TMP 字体图集，用作字形校准的参照。"""
    out = os.path.join(ASSETS, 'atlas')
    os.makedirs(out, exist_ok=True)
    meta = {}
    for pid, o in sf.objects.items():
        if o.type.name != 'Texture2D':
            continue
        d = o.read()
        if 'Atlas' not in (d.m_Name or ''):
            continue
        try:
            img = d.image
        except Exception as e:                       # noqa: BLE001
            print('  !! atlas %s decode failed: %s' % (d.m_Name, e))
            continue
        if img is None:
            continue
        img.save(os.path.join(out, '%d.png' % pid))
        meta[pid] = {'name': d.m_Name, 'w': img.width, 'h': img.height,
                     'format': int(d.m_TextureFormat)}
        print('  atlas pid=%-6d %-34s %dx%d' % (pid, d.m_Name, img.width, img.height))
    with open(os.path.join(ASSETS, 'atlas_meta.json'), 'w') as f:
        json.dump(meta, f, indent=1)


def dump_ttf(sf):
    """导出旧版 Unity Font 里内嵌的 TTF（校准字体度量时要用）。"""
    out = os.path.join(ASSETS, 'ttf')
    os.makedirs(out, exist_ok=True)
    for pid, o in sf.objects.items():
        if o.type.name != 'Font':
            continue
        d = o.read()
        data = bytes(d.m_FontData)
        name = '%d_%s.ttf' % (pid, d.m_Name.replace(' ', '_'))
        with open(os.path.join(out, name), 'wb') as f:
            f.write(data)
        print('  ttf   pid=%-6d %-28s %7d bytes  %s'
              % (pid, d.m_Name, len(data), d.m_FontNames))


def main():
    setup_console()
    src = pristine_assets()
    print('读取 %s' % src)
    sf = UnityPy.load(src).file
    print('\n== 本地化表 ==')
    dump_sheets(sf)
    print('\n== TMP 字体图集 ==')
    dump_atlases(sf)
    print('\n== 内嵌 TrueType 字体 ==')
    dump_ttf(sf)


if __name__ == '__main__':
    main()
