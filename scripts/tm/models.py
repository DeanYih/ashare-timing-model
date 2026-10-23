# -*- coding: utf-8 -*-
"""模型层：四大择时模型 + 综合决策。

严格对应笔记框架：
  模型① 经济周期（定性）—— GDP × CPI，美林时钟四象限
  模型② 货币周期（定性）—— 社融 × PPI，四阶段
  模型③ 情绪周期（定量）—— 风险溢价 = 1/PE − 十年期国债收益率
  模型④ 技术指标（定量）—— RSI 超买超卖
最后按笔记的流程图做「四层逐级确认」。
"""
from __future__ import annotations

from .config import (ERP_BUY, ERP_SELL, RSI_GATE, RSI_MARGIN,
                     RSI_OVERBOUGHT, RSI_OVERSOLD, RSI_WINDOW, WEIGHTS)


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


# ── 模型① 经济周期（美林时钟）────────────────────────────────────────
# 四象限 → 阶段 → 资产排序 → 对「股票」的友好度
CYCLE_MAP = {
    ("up", "down"): dict(stage="复苏", rank="股票 > 债券 > 现金 > 商品",
                         score=100, hint="增长回升 + 通胀回落，股票最优"),
    ("up", "up"): dict(stage="过热", rank="商品 > 股票 > 现金 > 债券",
                       score=60, hint="增长与通胀同升，商品最好，股票次之"),
    ("down", "up"): dict(stage="滞胀", rank="现金 > 商品 > 债券 > 股票",
                         score=15, hint="增长回落 + 通胀高企，现金为王，股票最差"),
    ("down", "down"): dict(stage="衰退", rank="债券 > 现金 > 股票 > 商品",
                           score=35, hint="增长与通胀同落，债券最优，股票待右侧"),
}


def _infl_key(cpi_value: float, c_dir: str) -> str:
    """通胀象限判定：方向 + 绝对水平双确认。

    只有方向不够——CPI 0.9% 就算短期反弹也谈不上「通胀高企」，
    否则美林时钟会把低通胀误判成滞胀。所以：
      <1%   一律视为低通胀（通缩压力，归 down）
      >3%   一律视为高通胀（归 up）
      1~3%  才看方向
    """
    if cpi_value < 1.0:
        return "down"
    if cpi_value > 3.0:
        return "up"
    return "up" if c_dir == "up" else "down"


def model_cycle(gdp: dict, cpi: dict) -> dict:
    if not gdp.get("ok") or not cpi.get("ok"):
        return {"ok": False, "key": "cycle", "name": "模型① 经济周期",
                "score": 50, "stage": "数据不足", "degraded": True,
                "hint": "GDP 或 CPI 数据缺失，按中性处理"}

    g_dir = gdp["trend"]["dir"]
    c_dir = cpi["trend"]["dir"]
    g_key = "up" if g_dir == "up" else "down"
    c_key = _infl_key(cpi["value"], c_dir)
    info = CYCLE_MAP[(g_key, c_key)]

    c_note = {("down", "down"): "低通胀压制（CPI<1%）",
              ("up", "up"): "高通胀确认（CPI>3%）"}.get((c_key, c_dir))
    if c_note is None and c_key != ("up" if c_dir == "up" else "down"):
        c_note = f"CPI {cpi['value']}% 未达通胀阈值，按低通胀处理"

    return {
        "ok": True, "key": "cycle", "name": "模型① 经济周期", "type": "定性",
        "score": info["score"], "stage": info["stage"], "rank": info["rank"],
        "hint": info["hint"], "degraded": False, "note": c_note,
        "axes": {
            "增长(GDP)": {"value": gdp["value"], "dir": g_dir,
                        "label": {"up": "上行", "down": "下行", "flat": "走平"}[g_dir],
                        "delta": gdp["trend"]["delta"]},
            "通胀(CPI)": {"value": cpi["value"], "dir": c_dir, "quadrant": c_key,
                        "label": {"up": "上行", "down": "下行", "flat": "走平"}[c_dir],
                        "delta": cpi["trend"]["delta"]},
        },
    }


# ── 模型② 货币周期（社融 × PPI）──────────────────────────────────────
MONEY_MAP = {
    ("up", "down"): dict(stage="转向复苏", asset="股票最优", score=100,
                         hint="社融↑ PPI↓：宽信用已启动，股票最优"),
    ("up", "up"): dict(stage="趋于过热", asset="商品最优", score=55,
                       hint="社融↑ PPI↑：宽信用 + 涨价，商品最优"),
    ("down", "up"): dict(stage="增长趋缓", asset="现金最优", score=25,
                         hint="社融↓ PPI↑：信用收缩但物价仍高，现金最优"),
    ("down", "down"): dict(stage="步入衰退", asset="债券最优", score=40,
                           hint="社融↓ PPI↓：信用与物价双降，债券最优，政策放松在即"),
}


def model_money(shrz: dict, ppi: dict) -> dict:
    if not shrz.get("ok") or not ppi.get("ok"):
        return {"ok": False, "key": "money", "name": "模型② 货币周期",
                "score": 50, "stage": "数据不足", "degraded": True,
                "hint": "社融或 PPI 数据缺失，按中性处理"}

    s_dir, p_dir = shrz["trend"]["dir"], ppi["trend"]["dir"]
    s_key = "up" if s_dir == "up" else "down"
    p_key = "up" if p_dir == "up" else "down"
    info = MONEY_MAP[(s_key, p_key)]

    return {
        "ok": True, "key": "money", "name": "模型② 货币周期", "type": "定性",
        "score": info["score"], "stage": info["stage"], "asset": info["asset"],
        "hint": info["hint"], "degraded": False,
        "axes": {
            "社融": {"value": shrz["value"], "dir": s_dir,
                    "label": {"up": "上行", "down": "下行", "flat": "走平"}[s_dir],
                    "delta": shrz["trend"]["delta"]},
            "PPI": {"value": ppi["value"], "dir": p_dir,
                    "label": {"up": "上行", "down": "下行", "flat": "走平"}[p_dir],
                    "delta": ppi["trend"]["delta"]},
        },
    }


# ── 模型③ 情绪周期（风险溢价 ERP）────────────────────────────────────
def model_erp(pe: float | None, bond10y: float | None) -> dict:
    if not pe or not bond10y:
        return {"ok": False, "key": "erp", "name": "模型③ 情绪周期（ERP）",
                "score": 50, "degraded": True, "hint": "PE 或国债收益率缺失，按中性处理"}

    earnings_yield = 100.0 / pe
    erp = earnings_yield - bond10y
    score = _clamp((erp - ERP_SELL) / (ERP_BUY - ERP_SELL) * 100)

    if erp >= ERP_BUY:
        zone, advice = "极度低估（买入区）", "风险溢价高于 6%，是框架里的买点"
    elif erp >= 4.5:
        zone, advice = "偏低估", "股票相对债券有吸引力，可逐步加仓"
    elif erp > ERP_SELL:
        zone, advice = "中性", "盈亏比一般，维持中性仓位"
    else:
        zone, advice = "高估（卖出区）", "风险溢价低于 3%，股票性价比差"

    return {
        "ok": True, "key": "erp", "name": "模型③ 情绪周期（ERP）", "type": "定量",
        "score": round(score, 1), "erp": round(erp, 2),
        "pe": pe, "bond10y": bond10y, "earnings_yield": round(earnings_yield, 2),
        "zone": zone, "hint": advice, "degraded": False,
    }


# ── 模型④ 技术指标 RSI ──────────────────────────────────────────────
def _rsi_score(v: float) -> float:
    """RSI 越低越买：分四段线性映射到 0~100 的「买入友好度」"""
    if v <= RSI_OVERSOLD:
        return _clamp(100 - v * 0.5, 90, 100)      # 0→100, 20→90
    if v <= 50:
        return 90 - (v - RSI_OVERSOLD) / (50 - RSI_OVERSOLD) * 35   # 20→90, 50→55
    if v <= RSI_OVERBOUGHT:
        return 55 - (v - 50) / (RSI_OVERBOUGHT - 50) * 45           # 50→55, 80→10
    return _clamp(10 - (v - RSI_OVERBOUGHT) * 0.5, 0, 10)


def model_rsi(r6: float | None, r14: float | None) -> dict:
    """模型④：以 RSI6 为主判定，RSI14 仅作参考展示。

    改用 RSI6 的原因：A 股波动大，RSI14 很难跌到 20 以下或升到 80 以上，
    「20/80 超买超卖」在 RSI14 上两年只响过 5 次，形同虚设。
    """
    if r6 is None:
        return {"ok": False, "key": "rsi", "name": "模型④ RSI 技术指标",
                "score": 50, "degraded": True, "hint": "行情数据不足，按中性处理"}

    score = _rsi_score(r6)
    # 阈值两侧留临界带，避免 RSI=20.05 被说成弱势、评分却接近满分
    if r6 <= RSI_OVERSOLD:
        zone, advice = "超卖区", f"RSI6={r6} ≤{RSI_OVERSOLD}，短期杀跌过度，反弹机会增加，可加仓"
    elif r6 <= RSI_OVERSOLD + RSI_MARGIN:
        zone, advice = "超卖临界", f"RSI6={r6} 逼近 {RSI_OVERSOLD}，反弹条件正在形成"
    elif r6 >= RSI_OVERBOUGHT:
        zone, advice = "超买区", f"RSI6={r6} ≥{RSI_OVERBOUGHT}，短期涨势过热，回挡机会增加，宜减仓"
    elif r6 >= RSI_OVERBOUGHT - RSI_MARGIN:
        zone, advice = "超买临界", f"RSI6={r6} 逼近 {RSI_OVERBOUGHT}，注意回挡风险"
    elif r6 >= 50:
        zone, advice = "强势区", f"RSI6={r6} 在 50 上方，短期趋势偏强"
    else:
        zone, advice = "弱势区", f"RSI6={r6} 在 50 下方，短期趋势偏弱"

    return {
        "ok": True, "key": "rsi", "name": "模型④ RSI 技术指标", "type": "定量",
        "score": round(score, 1), "window": RSI_WINDOW,
        "rsi6": r6, "rsi14": r14,
        "zone": zone, "hint": advice, "degraded": False,
    }


# ── 综合决策：四层逐级确认 ──────────────────────────────────────────
def decide(cycle: dict, money: dict, erp: dict, rsi: dict) -> dict:
    composite = (WEIGHTS["cycle"] * cycle["score"] +
                 WEIGHTS["money"] * money["score"] +
                 WEIGHTS["erp"] * erp["score"] +
                 WEIGHTS["rsi"] * rsi["score"])

    # 笔记流程图：① 经济周期底部 → ② 货币周期底部 → ③ 情绪高位 → ④ RSI 超卖
    gates = [
        {"layer": "① 经济周期底部", "pass": cycle.get("stage") in ("衰退", "复苏"),
         "detail": f"当前阶段：{cycle.get('stage')}"},
        {"layer": "② 货币周期底部", "pass": money.get("stage") in ("步入衰退", "转向复苏"),
         "detail": f"当前阶段：{money.get('stage')}"},
        {"layer": "③ 情绪周期高位（便宜）", "pass": (erp.get("erp") or 0) >= 5.0,
         "detail": f"风险溢价 {erp.get('erp', '—')}%"},
        {"layer": "④ RSI 超卖", "pass": (rsi.get("rsi6") or 100) <= RSI_GATE,
         "detail": f"RSI6 = {rsi.get('rsi6', '—')}（门槛 ≤{RSI_GATE}）"},
    ]
    hits = sum(1 for g in gates if g["pass"])

    # 仓位 = 连续评分打底 + 四层共振加分
    position = _clamp(composite * 0.7 + hits / 4 * 100 * 0.3)

    if hits == 4:
        verdict, tone = "钻石买点：四层全部确认", "strong-buy"
    elif hits == 3:
        verdict, tone = "接近买点：三层确认，可分批建仓", "buy"
    elif hits == 2:
        verdict, tone = "观察区：两层确认，小仓位试探", "watch"
    elif hits == 1:
        verdict, tone = "等待区：仅一层确认，多看少动", "wait"
    else:
        verdict, tone = "空仓区：无一层确认，防守为主", "avoid"

    return {
        "composite": round(composite, 1),
        "position": round(position, 1),
        "hits": hits,
        "gates": gates,
        "verdict": verdict,
        "tone": tone,
    }
