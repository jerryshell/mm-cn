"""研究用：把 resources.assets 里的 MonoBehaviour 映射回它引用的脚本类名。

Unity 的 MonoBehaviour 在 assets 里只存一个指向 MonoScript 的引用（fileID + pathID），
脚本类名在 globalgamemanagers.assets 里。这个小工具就是建这张映射表，
用来查清「哪个对象是 TMP_FontAsset」「哪些组件引用了哪个字体」这类问题。

用法：
    python tools/scan_assets.py MM_Data/resources.assets
"""
import collections, os, struct, sys

import UnityPy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mmcore import setup_console

# 默认游戏目录，可用 MM_GAME 环境变量覆盖
GAME = os.environ.get('MM_GAME', r'D:\SteamLibrary\steamapps\common\Motorsport Manager')


def load_scripts():
    """从 globalgamemanagers.assets 读出 path_id -> 脚本类名 的映射。"""
    env = UnityPy.load(os.path.join(GAME, 'MM_Data', 'globalgamemanagers.assets'))
    table = {}
    for pid, o in env.file.objects.items():
        if o.type.name != 'MonoScript':
            continue
        try:
            d = o.read()
            table[pid] = (d.m_ClassName, getattr(d, 'm_Namespace', ''),
                          getattr(d, 'm_AssemblyName', ''))
        except Exception:                                # noqa: BLE001
            pass
    return table


def scan(path, script_table):
    """统计目标文件里每种脚本类出现了多少个。"""
    env = UnityPy.load(path)
    sf = env.file
    counter = collections.Counter()
    by_script = collections.defaultdict(list)
    unresolved = 0
    for pid, o in sf.objects.items():
        if o.type.name != 'MonoBehaviour':
            continue
        # m_GameObject(12 字节) + m_Enabled(1 字节 + 3 字节填充) + m_Script(12 字节)
        raw = o.get_raw_data()
        fid = struct.unpack('<i', raw[16:20])[0]
        spid = struct.unpack('<q', raw[20:28])[0]
        info = None
        if fid == 1:            # 指向外部的 globalgamemanagers.assets
            info = script_table.get(spid)
        elif fid == 0:          # 指向本文件
            try:
                info = (sf.objects[spid].read().m_ClassName, '', '')
            except Exception:                            # noqa: BLE001
                info = None
        if info is None:
            unresolved += 1
            continue
        key = '%s.%s' % (info[1], info[0]) if info[1] else info[0]
        counter[key] += 1
        by_script[key].append(pid)
    return sf, counter, by_script, unresolved


if __name__ == '__main__':
    setup_console()
    table = load_scripts()
    print('脚本表条目数：%d' % len(table))
    for path in sys.argv[1:]:
        sf, counter, by_script, unresolved = scan(path, table)
        print('\n===== %s  未解析=%d' % (path, unresolved))
        for name, count in counter.most_common(60):
            print('  %6d  %s' % (count, name))
