# -*- coding: utf-8 -*-
"""参考水平线核验报告（命令行）。

用法：python verify_refs.py
逻辑全在 tm/refs.py 里，这里只负责取数、排版、打印，
保证仪表盘上展示的核验数字与命令行输出是**同一份计算**，不会两边不一致。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 不依赖 cwd：从技能根目录、scripts/、或任意目录调用都能找到 tm 包
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tm import refs as rf
from tm import sources as src

START = "2018-01"


def main() -> None:
    print("采集中（6 个宏观指标 + 中证沪深300）…", file=sys.stderr)
    raw = {
        "PMI": src.fetch_pmi(), "CPI": src.fetch_cpi(), "PPI": src.fetch_ppi(),
        "M2": src.fetch_m2(), "GDP": src.fetch_gdp(), "SHRZ": src.fetch_shrz(),
    }
    px = rf.month_end_px(src.fetch_csic_hs300()["series"])
    ser = {k: {d[:7]: v for d, v in vs if d[:7] >= START} for k, vs in raw.items()}

    print(f"\n样本区间：{START} 至今　｜　沪深300 月末点位来自中证指数公司官方日线")
    for k, v in ser.items():
        ks = sorted(v)
        print(f"  {k:4} {len(ks):>3} 期  {ks[0]} ~ {ks[-1]}")

    res = rf.evaluate(ser, px, START)

    for code, rows in res.items():
        print(f"\n{'=' * 82}\n{code}")
        for r in rows:
            arrow = "≥" if r["above"] else "≤"
            print(f"  参考线 {arrow} {r['v']:g}　{r['label']}　［{r['level']}］")
            print(f"    触发 {r['n_on']}/{r['n_all']} 月（{r['share']}%）　"
                  f"连续 {r['runs']} 段")
            print(f"    未来 12 个月沪深300：触发组 {r['ret_on']}%　"
                  f"未触发组 {r['ret_off']}%　差 {r['gap']:+}pct")
            # 逐段差值：这是判定的主依据，必须打出来，否则结论像是拍脑袋
            segs = r.get("segs") or []
            for s2 in segs:
                print(f"      · {s2['start']}~{s2['end']}  {s2['n']:>2} 月  "
                      f"差 {s2['gap']:+6.1f}pct")
            if len(segs) >= 2 and not r.get("same_sign"):
                print("      ⚠ 各段方向相反：整体差值被其中一段撑起来，不能当信号")
            print(f"    → 结论：{r['verdict']}")
            print(f"    依据：{r['basis']}")
            print(f"    注意：{r['caveat']}")

    # 阈值敏感性：证明「3%」不是挑出来的点位
    print(f"\n{'=' * 82}\n阈值敏感性（换成别的阈值，区分力还在不在？）")
    print("  若只在某一个点位有效，说明是从数据里拟合出来的；若单调变化，说明是真实梯度。")
    for code, ths in (("PPI", (0, 1, 2, 3, 4, 5)), ("CPI", (0, 1, 2, 3)), ("PMI", (48, 49, 50, 51, 52))):
        print(f"  {code}:")
        for th in ths:
            for above in (False, True):
                n_on, on, off = 0, [], []
                for ym, v in sorted(ser[code].items()):
                    r = rf._fwd(px, ym, 12)
                    if r is None:
                        continue
                    hit = (v >= th) if above else (v <= th)
                    if hit:
                        n_on += 1
                        on.append(r)
                    else:
                        off.append(r)
                if len(on) < 3 or len(off) < 3:
                    continue
                gap = sum(on) / len(on) - sum(off) / len(off)
                print(f"    {'≥' if above else '≤'} {th:>3}%  差 {gap:+6.1f}pct   (n={n_on:>3})")


if __name__ == "__main__":
    main()
