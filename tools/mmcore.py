"""汉化流水线的公共配置。

目录结构（带 `*` 的是生成物，已加入 .gitignore）：

    mm-cn/
      tools/          流水线脚本
      docs/           文档
      installer/      随 release 发布的安装脚本
      scripts/        流水线外围的辅助脚本
      trans/          翻译记忆（入库，这就是补丁的核心产物）
      extract/     *  从游戏导出的 14 张 CSV
      assets/      *  从游戏导出的字体图集 / 内嵌 TTF
      build/       *  中间产物 + textasset_map.json
      dist/        *  补丁成品 resources.assets 与 release 包
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 想对非 Steam 默认库的安装做构建时，设置 MM_GAME 指向游戏目录
GAME = os.environ.get('MM_GAME', r'D:\SteamLibrary\steamapps\common\Motorsport Manager')

# 未打补丁的 resources.assets。原版约 214 MiB，汉化后约 373 MiB，用大小粗判
GAME_ASSETS = os.path.join(GAME, 'MM_Data', 'resources.assets')
PRISTINE_ASSETS = os.path.join(GAME, 'MM_Data', 'resources.assets.orig')
PATCHED_SIZE = 300 * 1024 * 1024


def pristine_assets():
    """返回**未打补丁**的 resources.assets 路径。

    构建和导出都必须拿原版做输入：装过汉化之后游戏目录里的 resources.assets
    已经是中文的了，再拿它当源会得到双重处理的垃圾——图集被缩比两次、
    中文字形被当成原有的、导出表里“英文原文”变成中文。

    优先用安装脚本留下的 ``resources.assets.orig``，其次是确认没打过补丁的游戏文件。
    """
    if os.path.exists(PRISTINE_ASSETS) and os.path.getsize(PRISTINE_ASSETS) < PATCHED_SIZE:
        return PRISTINE_ASSETS
    if os.path.exists(GAME_ASSETS) and os.path.getsize(GAME_ASSETS) >= PATCHED_SIZE:
        raise SystemExit(
            '!! %s 看起来已经是汉化过的文件（%.0f MiB）。\n'
            '   拿汉化版当输入会把中文当成原文、把图集重复缩比，产物不可用。\n'
            '   请先用 Steam 的“验证游戏文件完整性”还原英文版，\n'
            '   或者把原版备份放到 %s 再重试。'
            % (GAME_ASSETS, os.path.getsize(GAME_ASSETS) / 1048576, PRISTINE_ASSETS))
    return GAME_ASSETS

EXTRACT = os.path.join(ROOT, 'extract')
TRANS = os.path.join(ROOT, 'trans')
BUILD = os.path.join(ROOT, 'build')
ASSETS = os.path.join(ROOT, 'assets')
DIST = os.path.join(ROOT, 'dist')
INSTALLER = os.path.join(ROOT, 'installer')
DOCS = os.path.join(ROOT, 'docs')

for _d in (EXTRACT, TRANS, BUILD, ASSETS, DIST, INSTALLER, DOCS):
    os.makedirs(_d, exist_ok=True)

# 游戏从 Data/Localisation/* 读取的 14 张本地化表
SHEETS = ['Dilemmas', 'Frontend', 'MediaReports', 'Interviews', 'Tweets', 'Messages',
          'PreRaceTalk', 'RaceEvent', 'Shared', 'Simulation', 'TeamRadio', 'Tutorials',
          'Nationalities', 'Challenges']

# 全部语言列都会被写中文：游戏是按 Steam 客户端语言选列的，
# 只覆盖其中一列会让大部分玩家看到的还是英文
LANG_COLS = ['English', 'French', 'Italian', 'German', 'Spanish', 'Brasilian',
             'Dutch', 'Hungarian', 'Polish', 'Russian']

# 设置界面里语言下拉框显示的名字
DISPLAY_NAME = '简体中文'


def setup_console():
    """把标准输出切成 UTF-8。

    中文 Windows 的控制台默认是 GBK(936)，脚本打印一个非 GBK 字符（比如波兰语人名里的 ś）
    就会抛 UnicodeEncodeError 直接崩掉。这里统一改成 UTF-8，并允许替换无法编码的字符。
    """
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:                                  # noqa: BLE001
            pass
