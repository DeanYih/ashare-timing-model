# -*- coding: utf-8 -*-
"""参考水平线：定义、依据等级、以及「这条线到底有没有用」的实测。

用户提出三条参考线：PMI 50、CPI 1%/3%、PPI 3%。本模块做两件事：

  ① 给每条线标注依据等级，而不是笼统说「常用」：
       定义性  —— 官方定义直接给出（PMI 50）
       政策目标 —— 政府工作报告年度目标（CPI 2% / 3%），会逐年调整
       经验值  —— 无官方口径，只能靠统计区分力说话（PPI 3%）
  ② 用 2018 年以来的真实数据算两个数：
       触发频率（这条线把样本切成多大的两半）
       未来 12 个月沪深 300 的收益差（触发组 − 未触发组）

## 为什么必须看「触发月数」和「连续段数」，而不只看收益差

月度样本 105 个，但「未来 12 个月收益」的窗口高度重叠，相邻月份共享 11 个月，
有效独立样本远少于 105。更麻烦的是：如果某条线的触发月份是连着的 13 个月，
那不是 13 个独立观测，而是**一段行情**。

所以这里额外数「连续段数」（runs），并且**逐段**算收益差：段数少、又恰好跨着
一次大涨，那个收益差就是行情的记忆，不是规律。更狠的一条是「多段但方向相反」——
整体收益差可以靠一段极强行情撑起来，拆开却是第一次 +15.5、第二次 −10.1，
这种阈值在两个独立时段给出相反结论，等于没有结论。

本项目据此把 CPI≥2、M2<8%、社融<10% 这类「看着很有效」的线判为不可用：
它们只是 2023—2025 那一段的影子，或者方向自相矛盾。
"""
from __future__ import annotations

REF_LINES: dict[str, dict] = {
    "PMI": {
        "lines": [{
            "v": 50.0, "label": "荣枯线", "level": "定义性", "role": "state", "above": False,
            "basis": "国家统计局对 PMI 的定义：50% 是扩张与收缩的临界点，"
                     "高于 50% 反映经济扩张，低于 50% 反映收缩。不是经验值，是定义。",
            "caveat": "但它只有描述意义，没有买入卖出含义：实测跌破 50 的月份，"
                      "未来 12 个月沪深 300 反而更好（见下方核验）。跌破 50 时，"
                      "市场通常已经跌过一轮了。",
        }],
    },
    "CPI": {
        "lines": [
            {"v": 2.0, "label": "当前目标", "level": "政策目标", "role": "state", "above": True,
             "basis": "2025、2026 年政府工作报告的居民消费价格涨幅目标均为「2% 左右」，"
                      "较 2018—2024 年的「3% 左右」下调。",
             "caveat": "政策目标随年份调整，所以它是一条**会移动**的参考线，"
                       "不能当作跨年份固定阈值。更要紧的是实测两段反向："
                       "2018—2020 差 +15.5pct、2021—2023 差 −10.1pct，"
                       "整体 +8.7 是被前一段撑起来的假象。"},
            {"v": 3.0, "label": "历史上限", "level": "政策目标", "role": "state", "above": True,
             "basis": "2018—2024 年政府工作报告的 CPI 目标为「3% 左右」（2020 年为 3.5%），"
                      "长期被视为通胀容忍上限。",
             "caveat": "2025 年目标已下调至 2%，3% 现在更像「历史经验上限」而非现行红线。"
                       "样本里触发月份只有 8 个、且全部落在 2019—2020 一轮猪肉周期内，"
                       "是单段行情，+26.9pct 不能外推。"},
            {"v": 1.0, "label": "通缩警戒", "level": "经验值", "role": "warn", "above": False,
             "basis": "无官方口径。市场习惯把 1% 以下视为「事实上的低通胀/通缩压力」，"
                      "参考日本 1990 年代经验。",
             "caveat": "实测 1% 两侧的未来收益差不到 4 个百分点，没有区分力，"
                       "只能当「价格环境偏冷」的描述，不能当买卖信号。"},
        ],
    },
    "PPI": {
        "lines": [
            {"v": 3.0, "label": "成本压力", "level": "经验值", "role": "warn", "above": True,
             "basis": "无官方口径，来源是产业逻辑：PPI 同比超过 3% 意味着上游涨价开始"
                      "实质侵蚀中下游毛利，同时往往伴随货币政策边际收紧。",
             "caveat": "九条线里只有 PPI 的两条通过检验。这一条尤其扎实："
                       "2018 与 2021 两个独立周期都给负值（−6.8 / −24.3），"
                       "且把阈值从 0% 逐级抬到 5%，收益差单调放大（−14% → −24%），"
                       "说明不是从数据里挑出来的点位。"},
            {"v": 0.0, "label": "工业通缩", "level": "经验值", "role": "good", "above": False,
             "basis": "PPI 同比为负 = 工业品出厂价整体下跌，通常对应需求不足，"
                      "但也对应成本压力解除、中下游毛利改善。",
             "caveat": "实测 PPI<0 时未来 12 个月收益明显更好，与「通缩=坏事」的直觉相反。"},
        ],
    },
    "GDP": {
        "lines": [{
            "v": 5.0, "label": "政策目标", "level": "政策目标", "role": "state", "above": False,
            "basis": "近年政府工作报告的经济增长目标：2023 年 5%、2024 年 5%、"
                     "2025 年 5%、2026 年 4.5%—5%。",
            "caveat": "不建议画成固定线：① 目标逐年调整（2021 年 6%、2022 年 5.5%）；"
                      "② GDP 是累计同比，存在基数效应，2021Q1 因低基数高达 18.9%，"
                      "任何固定水平线都会在基数切换处失真。只作背景标注。",
        }],
    },
    "M2": {
        "lines": [{
            "v": 8.0, "label": "名义增速锚", "level": "经验值", "role": "state", "above": False,
            "basis": "经验口径：M2 增速大体应匹配「实际 GDP + 通胀」，"
                     "近年名义增速约 5%~7%，故 8% 常被当作「货币不紧不松」的中枢。",
            "caveat": "2017 年后政府工作报告不再设 M2 目标，无官方依据。"
                      "实测「M2<8% 后市场更好」看着很有效，但触发月份全挤在 2023 年以后的"
                      "一段行情里，是那段记忆而非规律。",
        }],
    },
    "SHRZ": {
        "lines": [{
            "v": 10.0, "label": "宽信用", "level": "经验值", "role": "state", "above": False,
            "basis": "经验口径：社融存量同比 10% 以上通常对应信用扩张期。",
            "caveat": "无官方依据，且 2019-12 央行把国债与地方一般债纳入社融，"
                      "口径断点前后的存量不可直接比。同日「社融<10% 后市场更好」"
                      "也是单段行情的产物，不建议当阈值。",
        }],
    },
}

# 每根线在图上是否画：GDP 5% 因基数效应只画淡虚线、且标注「政策目标」，
# 其余按 role 决定颜色（warn 红 / good 绿 / state 灰蓝）。
ROLE_COLOR = {
    "warn": "#b3392b",
    "good": "#1a7f5a",
    "state": "#8494a8",
}


def month_end_px(rows: list[dict]) -> dict[str, float]:
    """日线 → {YYYY-MM: 该月最后收盘}"""
    out: dict[str, float] = {}
    for r in sorted(rows, key=lambda x: x.get("date", "")):
        d = str(r.get("date") or "")
        if d and r.get("close"):
            out[d[:7]] = r["close"]
    return out


def _fwd(px: dict[str, float], ym: str, months: int) -> float | None:
    y, m = int(ym[:4]), int(ym[5:7])
    y2, m2 = y + (m - 1 + months) // 12, (m - 1 + months) % 12 + 1
    k = f"{y2}-{m2:02d}"
    if k not in px or ym not in px:
        return None
    return (px[k] / px[ym] - 1) * 100


def _avg(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 1) if xs else None


def evaluate(series: dict[str, float], px: dict[str, float],
             start: str = "2018-01", horizon: int = 12) -> dict:
    """逐条参考线算触发频率、连续段数、未来收益差，并给出可用性结论。

    series 是 {YYYY-MM: 指标值}；只用 2018 至今的月末样本。
    """
    out: dict[str, list[dict]] = {}
    for code, spec in REF_LINES.items():
        ser = {k: v for k, v in (series.get(code) or {}).items() if k >= start}
        if not ser:
            continue
        rows = []
        keys = sorted(ser)
        for line in spec["lines"]:
            thr = line["v"]
            on, off, hit_keys = [], [], []
            for ym in keys:
                r = _fwd(px, ym, horizon)
                if r is None:
                    continue
                hit = (ser[ym] >= thr) if line.get("above") else (ser[ym] <= thr)
                if hit:
                    on.append(r)
                    hit_keys.append((ym, r))
                else:
                    off.append(r)
            # 时点集中度：把命中月份切成「聚类」（间隔 ≤12 个月算同一段），
            # 取最大聚类的占比。为什么不用「连续段数」：PPI>3% 的两段分属
            # 2018 与 2021 两次独立周期，段数=2 但那是两次独立验证；
            # 而 M2<8% 的 18 个月散在 4 段里、却全挤在 2023—2026 一个窗口内，
            # 段数掩盖了「其实只有一段行情」这个事实。占比才看得穿。
            clusters: list[list[tuple[str, float]]] = []
            for ym, r in hit_keys:
                cur = int(ym[:4]) * 12 + int(ym[5:7])
                prev = int(clusters[-1][-1][0][:4]) * 12 + int(clusters[-1][-1][0][5:7]) if clusters else None
                if clusters and cur - prev <= 12:
                    clusters[-1].append((ym, r))
                else:
                    clusters.append([(ym, r)])
            runs = len(clusters)
            top_share = (max(len(c) for c in clusters) / len(hit_keys)) if hit_keys else 0.0
            a, b = _avg(on), _avg(off)
            gap = round(a - b, 1) if (a is not None and b is not None) else None
            n_all = len(on) + len(off)

            # 逐段收益差（相对未触发组的基线）。
            # 这是整套核验里最关键的一步：整体收益差会被「一段大行情」拉出来，
            # 拆成段就立刻现形——CPI≥2 整体 +8.7pct 看着很棒，
            # 拆开却是 2018—2020 的 +15.5 与 2021—2023 的 −10.1，方向相反。
            # 一个在两个独立时段给出相反结论的阈值，不能当信号用。
            segs = []
            for c in clusters:
                m = round(sum(x[1] for x in c) / len(c), 1)
                segs.append({"start": c[0][0], "end": c[-1][0], "n": len(c),
                             "ret": m, "gap": round(m - b, 1) if b is not None else None})
            seg_gaps = [s["gap"] for s in segs if s["gap"] is not None]
            same_sign = (len(seg_gaps) >= 2
                         and all((g > 0) == (seg_gaps[0] > 0) for g in seg_gaps))

            # 可用性判定。顺序有讲究：
            #   先排除「差太小」（信息量不足）→ 再排除「只有一段」（无独立验证）
            #   → 再看「多段但方向相反」（自相矛盾）→ 再看「高度集中」
            #   → 最后才允许说「可作阈值」。宁可说没用，也不要给假信号。
            if n_all < 24 or len(on) < 6:
                verdict, tone = "样本不足，不作阈值", "muted"
            elif len(on) / n_all > 0.92 or len(on) / n_all < 0.08:
                verdict, tone = "几乎恒成立/极少触发，无区分力", "muted"
            elif gap is not None and abs(gap) < 4:
                verdict, tone = "两侧收益差 <4pct，无区分力", "muted"
            elif len(segs) == 1:
                verdict, tone = f"只有一段行情（{segs[0]['n']} 个月），不可当规律", "warn"
            elif not same_sign:
                verdict = f"{len(segs)} 段方向相反，不可作阈值"
                tone = "warn"
            elif top_share > 0.75:
                verdict = f"命中月份 {top_share:.0%} 集中在一段行情里，不可当规律"
                tone = "warn"
            elif gap is not None and abs(gap) >= 8 and len(on) >= 12:
                verdict, tone = f"{len(segs)} 段独立验证同向，可作阈值", "good"
            else:
                verdict, tone = "有弱区分力，仅作背景", "mid"

            rows.append({
                **{k: line[k] for k in ("v", "label", "level", "role", "basis", "caveat")},
                "above": line.get("above", False),
                "n_on": len(on), "n_all": n_all, "runs": runs, "top_share": round(top_share, 2),
                "share": round(len(on) / n_all * 100) if n_all else 0,
                "ret_on": a, "ret_off": b, "gap": gap,
                "segs": segs, "same_sign": same_sign,
                "horizon": horizon, "verdict": verdict, "tone": tone,
            })
        out[code] = rows
    return out


def flat_lines(code: str, unit: str | None = None) -> list[tuple[float, str, str]]:
    """给绘图用：(数值, 标签, 颜色)。

    数据层只存线名（"成本压力"），数字在这里拼回去——图上要的是
    「成本压力 3%」这种能直接对位的文字。而卡片 chips 用的是
    `{sign}{v} {label}`，数字已经在前半截，不能再来一遍。
    """
    if unit is None:
        from .config import INDICATORS
        unit = INDICATORS.get(code, {}).get("unit", "%")
    return [(l["v"], f'{l["label"]} {l["v"]:g}{unit}',
             ROLE_COLOR.get(l["role"], "#8494a8"))
            for l in REF_LINES.get(code, {}).get("lines", [])]
