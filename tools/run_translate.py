"""收集本地化表里所有需要翻译的英文，交给翻译引擎。

这是翻译流水线的入口，可以反复运行（已有缓存时几乎瞬间完成）：

    python tools/run_translate.py
    WORKERS=8 python tools/run_translate.py     # 提高并发
"""
import csv, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mmcore import EXTRACT, SHEETS, setup_console
from translate import translate_many, _key

# 游戏实际加载的 14 张表，文件名就是表名 + .csv
FILES = ['%s.csv' % s for s in SHEETS]


def rows_of(path):
    with open(path, encoding='utf-8', newline='') as fh:
        r = csv.reader(fh)
        hdr = next(r)
        return hdr, list(r)


def collect():
    """把 14 张表里非空的 English 列汇总成一个列表（含重复）。"""
    out = []
    for f in sorted(FILES):
        p = os.path.join(EXTRACT, f)
        if not os.path.exists(p):
            continue
        hdr, rows = rows_of(p)
        i = hdr.index('English')
        for row in rows:
            if len(row) != len(hdr):
                continue
            s = row[i]
            if s.strip():
                out.append(s)
    return out


def main():
    setup_console()
    texts = collect()
    print('收集到 %d 行（去重后 %d 条）' % (len(texts), len(set(texts))))
    cache = translate_many(texts, workers=int(os.environ.get('WORKERS', '5')))
    have = sum(1 for t in set(texts) if t + '|' + _key(t) in cache)
    print('已翻译 %d/%d 条' % (have, len(set(texts))))
    print('设置界面的语言项 PSG_10010788 会在 build_patch 阶段固定为「简体中文」')


if __name__ == '__main__':
    main()
