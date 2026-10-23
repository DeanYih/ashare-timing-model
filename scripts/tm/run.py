# -*- coding: utf-8 -*-
"""主流程：采集 → 加工 → 建模 → 决策 → 落盘"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import sqlite3
import sys

from . import indicators as ind
from . import models as md
from . import refs as rf
from . import sources as src
from . import calendar as cal
from .config import (DB_PATH, DATA_DIR, INDICATORS, OUT_DIR, RELEASE_RULE,
                     RSI_REF_WINDOW, RSI_WINDOW, STALE_DAYS)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MACRO_FETCHERS = {
    "PMI": src.fetch_pmi,
    "CPI": src.fetch_cpi,
    "PPI": src.fetch_ppi,
    "SHRZ": src.fetch_shrz,
    "M2": src.fetch_m2,
    "GDP": src.fetch_gdp,
}


# ── 缓存 ────────────────────────────────────────────────────────────
def _db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS series_cache(
        code TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS snapshot(
        ts TEXT PRIMARY KEY, payload TEXT NOT NULL)""")
    conn.commit()
    return conn


def _cache_get(conn, code: str):
    row = conn.execute("SELECT payload, fetched_at FROM series_cache WHERE code=?",
                       (code,)).fetchone()
    return (json.loads(row[0]), row[1]) if row else (None, None)


def _cache_put(conn, code: str, series):
    conn.execute("INSERT OR REPLACE INTO series_cache(code,payload,fetched_at) VALUES(?,?,?)",
                 (code, json.dumps(series, ensure_ascii=False),
                  dt.datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def collect(conn) -> tuple[dict, list]:
    """采集六个宏观指标，失败降级到缓存"""
    series_map, notes = {}, []
    for code, fn in MACRO_FETCHERS.items():
        try:
            s = fn()
            if len(s) < 3:
                raise src.SourceError(f"样本过少({len(s)})")

            # 社融是跨 20 个栏目页拼装的，任一篇超时都会让本次序列变短。
            # 直接覆盖缓存会永久丢掉历史，故与缓存做「按期次合并」，新值覆盖旧值。
            if code == "SHRZ":
                cached, _ = _cache_get(conn, code)
                if cached:
                    merged = {d: v for d, v in cached}
                    merged.update({d: v for d, v in s})
                    before = len(s)
                    s = sorted(merged.items())
                    if len(s) > before:
                        notes.append({"code": code, "status": "merged",
                                      "fetched": before, "total": len(s),
                                      "latest": s[-1][0]})

            series_map[code] = s
            _cache_put(conn, code, s)
            notes.append({"code": code, "status": "live", "n": len(s),
                          "latest": s[-1][0]})
        except Exception as e:  # noqa: BLE001
            cached, fetched_at = _cache_get(conn, code)
            if cached:
                series_map[code] = [tuple(x) for x in cached]
                notes.append({"code": code, "status": "cache", "error": str(e)[:160],
                              "cached_at": fetched_at})
            else:
                series_map[code] = []
                notes.append({"code": code, "status": "fail", "error": str(e)[:160]})
    return series_map, notes


def collect_market(conn) -> dict:
    market, notes = {}, {}

    def _one(key, fn):
        try:
            v = fn()
            market[key] = v
            notes[key] = {"status": "live"}
            _cache_put(conn, f"MK_{key}", v if isinstance(v, (int, float)) else v)
        except Exception as e:  # noqa: BLE001
            cached, fetched_at = _cache_get(conn, f"MK_{key}")
            if cached is not None:
                market[key] = cached
                notes[key] = {"status": "cache", "cached_at": fetched_at,
                              "error": str(e)[:160]}
            else:
                market[key] = None
                notes[key] = {"status": "fail", "error": str(e)[:160]}

    _one("BOND10Y", src.fetch_bond10y)

    # 中证官方一次请求同时给出收盘点位与市盈率，优先走这条路
    try:
        csic = src.fetch_csic_hs300()
        market["HS300"] = csic["series"]
        market["HS300_PE"] = round(csic["pe"], 4)
        market["HS300_PE_MONTHLY"] = csic["pe_monthly"]
        notes["HS300"] = {"status": "live", "authority": "中证指数公司"}
        notes["HS300_PE"] = {"status": "live", "authority": "中证指数公司",
                             "as_of": csic["pe_date"], "official": True,
                             "monthly": len(csic["pe_monthly"])}
        _cache_put(conn, "MK_HS300", csic["series"])
        _cache_put(conn, "MK_HS300_PE", market["HS300_PE"])
        _cache_put(conn, "MK_HS300_PE_MONTHLY", csic["pe_monthly"])
    except Exception as e:  # noqa: BLE001
        notes["_csic_error"] = str(e)[:160]
        _one("HS300", src.fetch_hs300)
        _one("HS300_PE", src.fetch_hs300_pe)
        # 中证整体失败时，模型③的历史曲线不能跟着消失——用缓存接上
        cached_m, cached_at = _cache_get(conn, "MK_HS300_PE_MONTHLY")
        if cached_m:
            market["HS300_PE_MONTHLY"] = cached_m
            notes["HS300_PE_MONTHLY"] = {"status": "cache", "cached_at": cached_at,
                                         "n": len(cached_m)}
    return {"data": market, "notes": notes}


def _freshness(as_of: str | None, today: dt.date | None = None) -> dict:
    """市场数据的时点校验：区分「当日已更新」「今日休市」「交易日但数据未更新」。

    早期版本只按 weekday 判断，法定节假日（如国庆）会被误报成「数据源延迟」；
    现改为查交易所休市日历，并把两种情况分开说明。
    """
    today = today or dt.date.today()
    if not as_of:
        return {"as_of": None, "lag_days": None, "state": "无数据",
                "same_day": False, "note": "未取到数据"}
    d = dt.date.fromisoformat(as_of[:10])
    lag = (today - d).days
    reason = cal.closed_reason(today)
    if lag == 0:
        state, note = "T", "当日数据"
    elif reason:
        state, note = "T-1", f"今日休市（{reason}），取上一交易日 {d}"
    elif not cal.covered(today):
        state, note = "T-1", f"当日数据未更新，取 {d}（{today.year} 年休市表未收录，可能是节假日）"
    elif lag == 1:
        state, note = "T-1", f"当日数据尚未更新，取 {d}"
    else:
        state, note = "T-1", f"连续 {lag} 日无新数据，取 {d}，建议核对数据源"
    return {"as_of": as_of, "lag_days": lag, "state": state,
            "same_day": lag == 0, "note": note, "today_closed": bool(reason)}


def _erp_history(pe_monthly, bond) -> list[tuple[str, float]]:
    """ERP 月度序列 = 每月末的 100/PE − 同月最近一日的 10Y 国债。

    PE 取中证官方 TTM 的**该月最后一个交易日**值（日期原样保留，不改成月末日）；
    国债按「不晚于 PE 日期」的最近交易日取值——两者同为收盘/日终口径，
    且利率的日间漂移远小于 PE 分位差，错开一两天不影响档位判断。
    """
    if not pe_monthly or not bond:
        return []
    bond_m = src.month_end(bond)
    bmap = dict(bond_m)
    bdates = sorted(bmap)
    out: list[tuple[str, float]] = []
    for d, pe in pe_monthly:
        if not pe:
            continue
        i = bisect.bisect_right(bdates, d) - 1
        if i < 0:
            continue
        y = bmap[bdates[i]]
        if y is None:
            continue
        out.append((d, round(100.0 / pe - y, 2)))
    return out


def compute(series_map: dict, market: dict) -> dict:
    today = dt.date.today()
    macro = ind.build(series_map, STALE_DAYS, RELEASE_RULE, today)

    bond10y, bond_as_of = None, None
    if market.get("BOND10Y"):
        bond_as_of, bond10y = market["BOND10Y"][-1]

    closes = [x["close"] for x in (market.get("HS300") or []) if x["close"]]
    r6 = ind.rsi_now(closes, RSI_WINDOW)        # 主判定（RSI6）
    r14 = ind.rsi_now(closes, RSI_REF_WINDOW)   # 参考（RSI14）

    cycle = md.model_cycle(macro.get("GDP", {}), macro.get("CPI", {}))
    money = md.model_money(macro.get("SHRZ", {}), macro.get("PPI", {}))
    erp = md.model_erp(market.get("HS300_PE"), bond10y)
    rsi = md.model_rsi(r6, r14)

    decision = md.decide(cycle, money, erp, rsi)

    # 模型③ 的历史曲线：2018 年至今的月度 ERP
    erp_hist = _erp_history(market.get("HS300_PE_MONTHLY"), market.get("BOND10Y"))

    # 模型④ 的 RSI 历史（日频，只留最后 400 个交易日）
    # 不能按周抽稀：RSI6 是 6 日窗口的快振荡器，隔 5 个交易日取一点，
    # 相邻两点能差出 50 个点（实测 100 → 43），画出来是锯齿——那是混叠，不是行情。
    # 也不能把整段 2000 多天塞进 JSON：曲线上只画半年，多存的都是死重量。
    hs_rows = [x for x in (market.get("HS300") or []) if x.get("close")]
    hs_closes = [x["close"] for x in hs_rows]
    hs_dates = [x["date"] for x in hs_rows]
    rsi_hist = [(hs_dates[i], v) for i, v in ind.rsi(hs_closes, RSI_WINDOW)][-400:]

    # 参考水平线的实测核验：与 verify_refs.py 同一份计算，两边不会打架
    px = rf.month_end_px(market.get("HS300") or [])
    ref_stats = rf.evaluate(
        {code: {d[:7]: v for d, v in (m.get("history_all") or [])}
         for code, m in macro.items() if m.get("ok")}, px)

    hs300_last = market["HS300"][-1] if market.get("HS300") else None
    hs_as_of = hs300_last["date"] if hs300_last else None
    return {
        "as_of": today.isoformat(),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "today": {"date": today.isoformat(),
                  "trading": cal.is_trading_day(today),
                  "closed_reason": cal.closed_reason(today),
                  "desc": cal.describe(today)},
        "macro": macro,
        "market": {
            "hs300": hs300_last,
            "bond10y": bond10y,
            "hs300_pe": market.get("HS300_PE"),
            "rsi6": r6,
            "rsi14": r14,
            "rsi_window": RSI_WINDOW,
        },
        # 市场数据时点（点位与 PE 同源于中证一行，故共用 hs300 的日期）
        "market_asof": {
            "HS300": _freshness(hs_as_of, today),
            "HS300_PE": _freshness(hs_as_of, today),
            "BOND10Y": _freshness(bond_as_of, today),
        },
        "erp_history": erp_hist,
        "rsi_history": rsi_hist,
        "ref_stats": ref_stats,
        "models": {"cycle": cycle, "money": money, "erp": erp, "rsi": rsi},
        "decision": decision,
        "meta": {"indicators": INDICATORS, "release_rule": RELEASE_RULE},
    }


def run() -> dict:
    conn = _db()
    series_map, fetch_notes = collect(conn)
    mkt = collect_market(conn)
    result = compute(series_map, mkt["data"])
    result["fetch"] = {"macro": fetch_notes, "market": mkt["notes"]}
    # 社融多源采集的自检结果（样本跨度、候选/解析/剔除明细），供仪表盘展示可追溯性
    audit = getattr(src.fetch_shrz, "last_audit", None)
    if audit:
        result["shrz_audit"] = audit

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "latest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        from .render import render
        html_doc = render(result)
        (OUT_DIR / "dashboard.html").write_text(html_doc, encoding="utf-8")
        result["_html"] = str(OUT_DIR / "dashboard.html")
    except Exception as e:  # noqa: BLE001
        result["_html_error"] = f"{type(e).__name__}: {e}"

    conn.execute("INSERT OR REPLACE INTO snapshot(ts,payload) VALUES(?,?)",
                 (result["generated_at"], json.dumps(result, ensure_ascii=False)))
    conn.commit()
    conn.close()
    return result


def _fmt(r: dict) -> str:
    d = r["decision"]
    L = []
    L.append(f"择时快照 · {r['as_of']}")
    L.append("=" * 58)
    for k in ("cycle", "money", "erp", "rsi"):
        m = r["models"][k]
        flag = "⚠降级" if m.get("degraded") else ""
        stage = m.get("stage") or m.get("zone") or ""
        L.append(f"  {m['name']:<18} {m['score']:>5.1f} 分  {stage} {flag}")
        L.append(f"     {m['hint']}")
    L.append("-" * 58)
    L.append(f"  综合评分 {d['composite']} / 建议仓位 {d['position']}%")
    L.append(f"  共振层数 {d['hits']}/4 → {d['verdict']}")
    for g in d["gates"]:
        L.append(f"    {'✅' if g['pass'] else '⬜'} {g['layer']}  ({g['detail']})")
    L.append("-" * 58)
    m = r["market"]
    L.append(f"  沪深300 {m['hs300']['close'] if m['hs300'] else '—'}  "
             f"PE(中证官方) {m['hs300_pe']}  10Y {m['bond10y']}%  "
             f"RSI6 {m['rsi6']}（主）  RSI14 {m['rsi14']}（参考）")
    eh = r.get("erp_history") or []
    if len(eh) >= 12:
        ev = [v for _d, v in eh]
        L.append(f"  ERP 月度曲线 {len(eh)} 期（{eh[0][0][:7]} ~ {eh[-1][0][:7]}）｜"
                 f"区间 {min(ev):.2f}% ~ {max(ev):.2f}%  "
                 f"最贵 {next(d for d, v in eh if v == min(ev))[:7]}  "
                 f"最便宜 {next(d for d, v in eh if v == max(ev))[:7]}")
    rs = r.get("ref_stats") or {}
    if rs:
        # 标记：无标记=可作阈值；△=弱区分力仅作背景；✗=不能当信号用
        mark = {"good": "", "mid": "△", "warn": "✗", "muted": "✗"}
        bits = []
        for code, rows in rs.items():
            for x in rows:
                bits.append(f"{code}{'≥' if x['above'] else '≤'}{x['v']:g}:{x['gap']:+.1f}pct"
                            + mark.get(x["tone"], ""))
        L.append("  参考线核验(未来12M差)： " + "  ".join(bits))
        ok = [f"{c}{'≥' if x['above'] else '≤'}{x['v']:g}"
              for c, rows in rs.items() for x in rows if x["tone"] == "good"]
        L.append("  可作阈值： " + ("、".join(ok) if ok else "无（全部只作背景）"))
    bad = [f"{n['code']}:{n['status']}" for n in r["fetch"]["macro"] if n["status"] != "live"]
    bad += [f"{k}:{v['status']}" for k, v in r["fetch"]["market"].items() if v["status"] != "live"]
    if bad:
        L.append(f"  ⚠ 非实时数据：{', '.join(bad)}")

    # 数据新鲜度：宏观看「期末滞后 + 是否该发未发」，市场看「T / T-1」
    mac = []
    for k, v in r["macro"].items():
        if not v.get("ok"):
            continue
        if v["late"]:
            tag = " ❌滞后"
        elif v["awaiting"]:
            tag = " ⏳待发"
        elif v["stale"]:
            tag = " ⚠陈旧"
        else:
            tag = " ✅"
        mac.append(f"{k} {v['age_days']}d{tag}")
    mkt = []
    for k, v in (r.get("market_asof") or {}).items():
        mkt.append(f"{k} {v['state']}")
    L.append("-" * 58)
    L.append("  宏观时滞(期末至今)： " + "  ".join(mac))
    L.append("  市场时点：           " + "  ".join(mkt))
    t = r.get("today") or {}
    if t:
        L.append("  今日：               " + t.get("desc", "—"))
    a = r.get("shrz_audit") or {}
    if a.get("periods"):
        tail = f"，剔除 {len(a['dropped'])} 条口径异常" if a.get("dropped") else ""
        L.append(f"  社融样本：           {a['periods']} 期（{a['span']}）"
                 f"｜候选 {a['candidates']} 篇、解析 {a['parsed']} 篇{tail}")
    return "\n".join(L)


if __name__ == "__main__":
    res = run()
    print(_fmt(res))
