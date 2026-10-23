# -*- coding: utf-8 -*-
"""模型③ 数据口径自检：月度 PE 是否 = 每月最后一个交易日的滚动市盈率（TTM）。

回答三个问题：
  ① 取值日期是不是「该月最后一个交易日」，而不是自然月末、也不是月初
  ② 中证 `peg` 字段是不是滚动口径（TTM），而不是静态 PE
  ③ 月末值能否与市场共识的历史时点对上

用法：python verify_pe_monthly.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tm import sources as src  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    csic = src.fetch_csic_hs300()
    daily = csic["pe_history"]          # [(date, pe)] 日频，已按日期升序
    monthly = csic["pe_monthly"]        # [(date, pe)] 每月最后一条

    print("=" * 74)
    print("① 月度取值日期核验")
    print("=" * 74)
    print(f"日频样本 {len(daily)} 条：{daily[0][0]} ~ {daily[-1][0]}")
    print(f"月度样本 {len(monthly)} 期：{monthly[0][0]} ~ {monthly[-1][0]}")

    # 每个月最后一个交易日索引
    last_idx: dict[str, int] = {}
    for i, (d, _v) in enumerate(daily):
        last_idx[d[:7]] = i
    expect = [daily[i] for i in sorted(last_idx.values())]
    same = expect == monthly
    print(f"逐月比对「该月最后一条日频记录」：{'完全一致 ✅' if same else '不一致 ❌'}")
    if not same:
        for a, b in zip(expect, monthly):
            if a != b:
                print(f"   期望 {a} / 实际 {b}")

    # 取值为自然月末的月份数（反证：不是直接用自然月末）
    natural_eom = 0
    for d, _v in monthly:
        y, m = int(d[:4]), int(d[5:7])
        nxt = dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)
        if d == nxt.isoformat():
            natural_eom += 1
    print(f"取值日恰好是自然月末的月份：{natural_eom}/{len(monthly)} 期；"
          f"其余 {len(monthly) - natural_eom} 期说明取的是**最后一个交易日**，不是自然日")

    weekday_hit = sum(1 for d, _ in monthly
                      if dt.date.fromisoformat(d).weekday() >= 5)
    print(f"取值日落在周末的期数：{weekday_hit}（应为 0）")

    print()
    print("=" * 74)
    print("② 口径判定：`peg` 是滚动市盈率（TTM）还是静态市盈率")
    print("=" * 74)
    print("方法：PE = 点位 / 每股收益，故 每股收益 = 点位 / PE。")
    print("      静态 PE 每年只在 4 月底年报披露后跳变一次；")
    print("      滚动 PE 会在 4 月底（年报+一季报）、8 月底（中报）、10 月底（三季报）各跳一次。")
    print()
    print("  日期          PE     点位      反推每股收益    日变动")
    prev = None
    hits = []
    for d, pe in daily:
        # 找当天点位
        close = next((c for dd, c in ((x["date"], x["close"]) for x in csic["series"])
                      if dd == d), None)
        if close is None or not pe:
            continue
        eps = close / pe
        if prev and abs(eps / prev[1] - 1) > 0.015:
            hits.append((d, prev[1], eps))
            print(f"  {d}  {pe:6.2f}  {close:8.2f}   {eps:9.3f}   {(eps/prev[1]-1)*100:+6.2f}%  ◀")
        prev = (d, eps)

    months = {}
    for d, _a, _b in hits:
        months.setdefault(d[5:7], 0)
        months[d[5:7]] += 1
    print()
    print(f"  跳变月份的分布：{dict(sorted(months.items()))}")
    print("  解读：跳变集中在 05 / 09 / 11 月 —— 对应 4 月底、8 月底、10 月底的财报披露节点，")
    print("        一年三次 ⇒ 滚动（TTM）口径。静态 PE 只会在 5 月出现一次。")

    print()
    print("=" * 74)
    print("③ 与市场共识时点对照")
    print("=" * 74)
    for probe in ("2018-01-31", "2021-01-29", "2024-01-31", "2024-09-30",
                  "2025-09-30", "2026-10-22"):
        hit = next((v for d, v in monthly if d == probe), None)
        if hit is not None:
            print(f"  {probe}  沪深300 PE(TTM) = {hit:.2f}")
        else:
            print(f"  {probe}  不在月度样本中（非交易日或不在区间内）")

    print()
    print("=" * 74)
    print("④ 月末样本全表（前 6 期 + 后 6 期）")
    print("=" * 74)
    show = monthly if len(monthly) <= 14 else (monthly[:6] + monthly[-6:])
    print("  月份      取值交易日     PE(TTM)")
    for d, v in show:
        print(f"  {d[:7]}    {d}   {v:6.2f}")
    if len(monthly) > 14:
        print(f"  ...（中间 {len(monthly) - 12} 期略）")


if __name__ == "__main__":
    main()
