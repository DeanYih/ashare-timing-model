#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""智能择时模型 · 单一入口。

任意工作目录都能直接跑：脚本自己把所在目录放进 sys.path，
不依赖 `cd scripts && python -m tm.run` 这种对 cwd 的假设。

用法：
    python run_timing.py                # 跑完整流水线，打印中文快照
    python run_timing.py --json         # 末尾追加机器可读摘要
    python run_timing.py --quiet --json # 只要摘要，不要快照（好解析）

产物：
    <TIMING_HOME or scripts>/output/dashboard.html   单文件仪表盘，无外部依赖
    <TIMING_HOME or scripts>/output/latest.json      全量结果快照
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from tm.config import OUT_DIR                      # noqa: E402
from tm.run import run, _fmt                       # noqa: E402


def _summary(res: dict) -> dict:
    """只挑汇报要用的字段。

    全量 latest.json 有几百 KB（含逐月 ERP 曲线、参考线逐段明细），
    丢给下游解析既慢又容易淹掉重点。这里给一份「够汇报、够判断」的窄视图。
    """
    d = res["decision"]
    models = {}
    for k in ("cycle", "money", "erp", "rsi"):
        m = res["models"][k]
        models[k] = {
            "name": m.get("name"),
            "score": m.get("score"),
            "stage": m.get("stage") or m.get("zone"),
            "hint": m.get("hint"),
            "degraded": bool(m.get("degraded")),
        }
    # market 在 run.py 里是嵌套结构（hs300: {date, close}），不是平铺的
    # hs300_close。早先这里按平铺取值，结果 --json 里点位恒为 null，
    # 下游（automation 汇报）就报了空值。取嵌套，另附数据日期便于判 T/T-1。
    mk = res.get("market") or {}
    hs = mk.get("hs300") or {}
    return {
        "as_of": res.get("as_of"),
        "generated_at": res.get("generated_at"),
        "composite": d.get("composite"),
        "position": d.get("position"),
        "hits": d.get("hits"),
        "verdict": d.get("verdict"),
        "tone": d.get("tone"),
        "models": models,
        "gates": [{"layer": g.get("layer"), "pass": g.get("pass"),
                   "detail": g.get("detail")} for g in d.get("gates", [])],
        "market": {
            "hs300_date": hs.get("date"),
            "hs300_close": hs.get("close"),
            "hs300_pe": mk.get("hs300_pe"),
            "bond10y": mk.get("bond10y"),
            "rsi6": mk.get("rsi6"),
            "rsi14": mk.get("rsi14"),
        },
        "market_asof": res.get("market_asof"),
        "today": (res.get("today") or {}).get("desc"),
        "html": res.get("_html"),
        "html_error": res.get("_html_error"),
        "output_dir": str(OUT_DIR),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="A 股择时模型 · 六指标四模型四层确认")
    ap.add_argument("--json", action="store_true", help="追加机器可读摘要")
    ap.add_argument("--quiet", action="store_true", help="不打印中文快照")
    args = ap.parse_args()

    res = run()                 # 采集 → 加工 → 建模 → 决策 → 落盘
    if not args.quiet:
        print(_fmt(res))
    if args.json:
        print(json.dumps(_summary(res), ensure_ascii=False, indent=2))

    # 仪表盘渲染失败不该让整件事算成功——数据有了但交付物没有
    return 1 if res.get("_html_error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
