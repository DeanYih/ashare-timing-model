# -*- coding: utf-8 -*-
"""指标加工层：把时间序列变成「当前值 / 方向 / 位置」三个人能读懂的判断。"""
from __future__ import annotations

import datetime as dt
import statistics

TODAY = dt.date.today()


def latest(series: list[tuple[str, float]]) -> tuple[str, float]:
    return series[-1]


def _eom(d: dt.date) -> dt.date:
    """该月最后一天"""
    nxt = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return nxt - dt.timedelta(days=1)


def _next_period(d: dt.date, freq: str) -> dt.date:
    """下一个报告期首日。freq: M 月度 / Q 季度"""
    step = 3 if freq == "Q" else 1
    m = d.month + step
    y = d.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    return dt.date(y, m, 1)


def period_end(report_date: str) -> dt.date:
    """报告期（各口径统一标为该期首日）→ 该期最后一天。

    东财与央行都把月度报告期标成 `YYYY-MM-01`、季度标成季末月 01 日，
    直接用它会多算近 30 天，导致「时滞」系统性虚高。
    """
    return _eom(dt.date.fromisoformat(report_date[:10]))


def ago_days(date_str: str, today: dt.date | None = None) -> int:
    """数据期滞后：报告期末 → 指定日期（默认今天）。"""
    try:
        d = period_end(date_str)
    except ValueError:
        return 9999
    return ((today or TODAY) - d).days


def due_date(report_date: str, rule: dict) -> dt.date:
    """按官方发布规则推算某报告期的「应发布日」。"""
    d = dt.date.fromisoformat(report_date[:10])
    if rule.get("day") == "EOM":
        return _eom(d)                       # PMI：当月最后一天发当月值
    nxt = _next_period(d, "M")               # 其余：次月第 N 日
    return nxt.replace(day=min(int(rule["day"]), _eom(nxt).day))


def expected_period(report_date: str, rule: dict, today: dt.date | None = None) -> dt.date:
    """截至今天，按官方日程「应已发布」的最新报告期。

    拿它和实际最新报告期比对，才能区分「数据源该更新没更新」和「还没到发布日」。
    """
    today = today or TODAY
    cur = dt.date.fromisoformat(report_date[:10])
    for _ in range(6):
        nxt = _next_period(cur, rule.get("freq", "M"))
        if due_date(nxt.isoformat(), rule) <= today:
            cur = nxt
        else:
            break
    return cur


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def trend(series: list[tuple[str, float]], smooth: int = 3,
          min_delta: float | None = None) -> dict:
    """方向判定：短期动量优先，中期趋势兜底。

    择时模型要的是「拐点识别」，所以以最近两期的变化为主；
    若短期变化落在噪声区间内，才退回「近 smooth 期均值 vs 前 smooth 期均值」。
    """
    vals = [v for _, v in series]
    if len(vals) < 4:
        return {"dir": "flat", "delta": 0.0, "note": "样本不足"}

    if min_delta is None:
        sd = statistics.pstdev(vals[-36:]) if len(vals) >= 12 else statistics.pstdev(vals)
        min_delta = max(sd * 0.12, 0.02)

    short = vals[-1] - vals[-2]
    mid = 0.0
    if len(vals) >= smooth * 2:
        mid = mean(vals[-smooth:]) - mean(vals[-smooth * 2:-smooth])

    if abs(short) > min_delta:
        used, delta = "短期", short
    else:
        used, delta = "中期", mid

    if delta > min_delta:
        d = "up"
    elif delta < -min_delta:
        d = "down"
    else:
        d = "flat"
    return {"dir": d, "delta": round(delta, 3), "basis": used,
            "short": round(short, 3), "mid": round(mid, 3),
            "threshold": round(min_delta, 3)}


def zscore(series: list[tuple[str, float]], window: int = 36) -> float | None:
    vals = [v for _, v in series][-window:]
    if len(vals) < 8:
        return None
    sd = statistics.pstdev(vals)
    if sd == 0:
        return 0.0
    return round((vals[-1] - mean(vals)) / sd, 2)


def percentile(series: list[tuple[str, float]], window: int = 60) -> float | None:
    """当前值在最近 window 期中的分位（0~100）"""
    vals = [v for _, v in series][-window:]
    if len(vals) < 10:
        return None
    cur = vals[-1]
    below = sum(1 for v in vals if v < cur)
    equal = sum(1 for v in vals if v == cur)
    return round((below + 0.5 * equal) / len(vals) * 100, 1)


def build(series_map: dict[str, list[tuple[str, float]]],
          stale_days: dict[str, int],
          rules: dict[str, dict] | None = None,
          today: dt.date | None = None) -> dict:
    """把六个宏观指标统一加工成卡片数据。

    时效判定分两轨，互相兜底：
      ① late  —— 按官方日程，更新的那一期「早该发了」却没拿到（精判，首选）
      ② stale —— 数据期滞后超兜底阈值（粗筛，防规则失效时彻底失守）
    """
    rules = rules or {}
    today = today or TODAY
    out = {}
    for code, series in series_map.items():
        if not series:
            out[code] = {"ok": False, "error": "无数据"}
            continue
        d, v = latest(series)
        days = ago_days(d, today)
        limit = stale_days.get(code, 60)
        rule = rules.get(code)

        late, awaiting, overdue, due, expect = False, False, 0, None, None
        if rule:
            try:
                rep = dt.date.fromisoformat(d[:10])
                expect = expected_period(d, rule, today)
                due = due_date(expect.isoformat(), rule)
                overdue = (today - due).days
                awaiting = expect > rep          # 该发的期次还没拿到
                # 容错：刚过发布日就判定异常太苛刻，数据源同步本身要时间
                late = awaiting and overdue > rule.get("tolerance", 3)
            except (ValueError, KeyError):
                pass

        out[code] = {
            "ok": True,
            "date": d,
            "period_end": period_end(d).isoformat(),
            "value": round(v, 2),
            "prev": round(series[-2][1], 2) if len(series) > 1 else None,
            "trend": trend(series),
            "z": zscore(series),
            "pct": percentile(series),
            "age_days": days,
            "stale": days > limit or late,
            "stale_reason": ("数据源未更新" if late else
                             ("数据期过旧" if days > limit else "")),
            "late": late,
            "awaiting": awaiting,
            "overdue_days": max(0, overdue),
            "tolerance": rule.get("tolerance") if rule else None,
            "due_date": due.isoformat() if due else None,
            "expected_period": expect.isoformat() if expect else None,
            "release_rule": rule.get("basis") if rule else None,
            "release_time": rule.get("time") if rule else None,
            "stale_limit": limit,
            "history": series[-36:],      # 表格/回退用
            "history_all": series,        # 2018 年以来的长序列（曲线用）
        }
    return out


def rsi(closes: list[float], window: int = 14) -> list[tuple[int, float]]:
    """Wilder RSI，返回 [(索引, 值)]"""
    if len(closes) <= window:
        return []
    gains, losses = [], []
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))

    avg_g = mean(gains[:window])
    avg_l = mean(losses[:window])
    out = []
    for i in range(window, len(closes)):
        if i > window:
            avg_g = (avg_g * (window - 1) + gains[i - 1]) / window
            avg_l = (avg_l * (window - 1) + losses[i - 1]) / window
        if avg_l == 0:
            val = 100.0
        else:
            rs = avg_g / avg_l
            val = 100 - 100 / (1 + rs)
        out.append((i, round(val, 2)))
    return out


def rsi_now(closes: list[float], window: int = 14) -> float | None:
    s = rsi(closes, window)
    return s[-1][1] if s else None
