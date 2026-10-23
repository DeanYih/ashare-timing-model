# -*- coding: utf-8 -*-
"""曲线层：模型①②的双线走势图 + 模型③的 ERP 单线曲线。

四象限只回答「现在站在哪一格」，看不出「从哪一格走过来的」。
而择时真正要的是拐点——两条线的斜率变化、交叉、背离，这些只在时序曲线上看得见。

本模块把两个输入指标对齐到同一时间轴画成双线，并把历史上每个月的周期阶段
涂成底部色带，于是「阶段是刚刚切换，还是已经持续了半年」也能一眼读出。

坐标与配色约定：
  左轴 = 主指标（模型① GDP 增速 / 模型② 社融同比）
  右轴 = 副指标（模型① CPI 同比 / 模型② PPI 同比）
  色带 = 该月所处的周期阶段，越暖越利于股票
"""
from __future__ import annotations

import datetime as dt
import math
from collections import Counter

from .indicators import trend
from .models import CYCLE_MAP, MONEY_MAP, _infl_key

# 阶段 → 色带底色。按四个阶段拉开色相，9px 高的细条上也分得清；
# 配色跟随「该阶段最受益的资产」：红=股票、黄=商品、灰蓝=现金、绿=债券。
PHASE_COLOR = {
    "复苏": "#e9a79c", "过热": "#f2c887", "衰退": "#a9d5bf", "滞胀": "#c2cddc",
    "转向复苏": "#e9a79c", "趋于过热": "#f2c887", "步入衰退": "#a9d5bf",
    "增长趋缓": "#c2cddc",
}

COLOR_A = "#2f5f8f"   # 主指标：深蓝
COLOR_B = "#d97706"   # 副指标：橙


def _abs_month(p: str) -> int:
    """'2026-09-01' → 绝对月序号（用于跨年比较与等距排布）"""
    d = dt.date.fromisoformat(str(p)[:10])
    return d.year * 12 + d.month - 1


def _label(m: int) -> str:
    return f"{m // 12}-{m % 12 + 1:02d}"


def _ordinal(d: str) -> int:
    """'2026-10-22' → 日序号。日频序列必须按天排布：
    用月序号会把同月的 20 多个交易日压成同一个 x，曲线变成一条竖线。"""
    try:
        return dt.date.fromisoformat(str(d)[:10]).toordinal()
    except ValueError:
        return 0


def _tag(x: float, y: float, text: str, color: str, fs: float = 8.5,
         anchor: str = "start") -> str:
    """一行小标签 + 白色底板。

    只给文字加 stroke 白描边是不够的：描边只有 2.6px，曲线从字中间穿过时
    照样糊。必须铺一块半透明白底，把底下的线压掉——阈值线的标签要是看不清，
    这条线画了等于没画。
    """
    w = sum(fs if ord(ch) > 127 else fs * 0.56 for ch in text) + 5
    h = fs + 3.4
    rx = x - 2 if anchor == "start" else x - w + 2
    return (f'<rect x="{rx:.1f}" y="{y - h + 2.2:.1f}" width="{w:.1f}" '
            f'height="{h:.1f}" rx="2.5" fill="#fff" opacity=".88"/>'
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
            f'font-size="{fs}" fill="{color}">{text}</text>')


def _span(vals: list[float], pad: float = 0.14) -> tuple[float, float]:
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:               # 全平的序列也要能画
        lo, hi = lo - 0.5, hi + 0.5
    r = hi - lo
    return lo - r * pad, hi + r * pad


def _align(series_a, series_b, months: int):
    """把两组序列铺到同一组「月」上，缺失月份前向填充。

    前向填充是刻意的：GDP 是季度值，其余是月度值。季度值在三个月内
    只有一个真实观测，铺满才好在同一条轴上比较；用 step 折线画出来，
    读的人一眼就知道那是「季度台阶」而不是真实月度波动。
    """
    ma = {_abs_month(p): v for p, v in series_a if v is not None}
    mb = {_abs_month(p): v for p, v in series_b if v is not None}
    if len(ma) < 3 or len(mb) < 3:
        return [], {}, {}

    end = max(max(ma), max(mb))
    # 起点取「窗口起点」与「两条线都已有数据的月份」的较大者。
    # 否则社融从 2019 起、GDP 从 2018 起时，左端会空出一段没有蓝线的区域，
    # 看起来像数据断了，其实只是窗口开得更早。
    start = max(end - months + 1, max(min(ma), min(mb)))

    prev_a = [ma[k] for k in sorted(ma) if k < start]
    prev_b = [mb[k] for k in sorted(mb) if k < start]
    la = prev_a[-1] if prev_a else None
    lb = prev_b[-1] if prev_b else None

    rows = []
    for k in range(start, end + 1):
        if k in ma:
            la = ma[k]
        if k in mb:
            lb = mb[k]
        rows.append((k, la, lb))
    return rows, ma, mb


def _stage_at(kind: str, a: list[float], b: list[float]) -> str | None:
    """用「截至该月的全部历史」判定阶段，与模型层口径完全一致。

    注意传入的是完整前缀而非固定窗口——模型层算 trend 时用的是整条序列，
    这里若改用滑动窗口，色带末端就可能与卡片上的阶段结论打架。
    """
    if len(a) < 8 or len(b) < 8:
        return None
    da = trend([(str(i), v) for i, v in enumerate(a)])
    db = trend([(str(i), v) for i, v in enumerate(b)])
    ka = "up" if da["dir"] == "up" else "down"
    kb = "up" if db["dir"] == "up" else "down"
    if kind == "cycle":              # a=增长(GDP)，b=通胀(CPI)
        return CYCLE_MAP[(ka, _infl_key(b[-1], db["dir"]))]["stage"]
    return MONEY_MAP[(ka, kb)]["stage"]   # a=社融，b=PPI


def _band(rows, ma, mb, kind, start, current: str | None = None) -> dict[int, str]:
    """每个月 → 当时的阶段名。

    原始回溯序列会高频抖动（模型② 实测 30 个月内翻了 12 次），原因是
    trend 的「短期动量优先」在月度粒度上对身体很小的 CPI / PPI 极其敏感，
    而 GDP 是季度值、三个月内只有一个真实观测。把抖动原样画出来，
    读者会误以为周期每月都在翻转——比不画更糟。

    所以做两层处理：
      ① 3 点滚动众数：单点抖动（A-B-A）被吃掉，真实切换（A-A-B-B）的
         边界位置仍准确保留；
      ② 末端锚定：色带最后一格强制等于模型层结论。模型用的是完整序列，
         是权威口径，色带不能和同一张仪表盘上的卡片结论打架。
    """
    a_seq = [v for k, v in sorted(ma.items()) if k < start]
    b_seq = [v for k, v in sorted(mb.items()) if k < start]
    keys, raw = [], []
    for k, av, bv in rows:
        hit = False
        if k in ma and av is not None:
            a_seq.append(av)
            hit = True
        if k in mb and bv is not None:
            b_seq.append(bv)
            hit = True
        if hit:
            st = _stage_at(kind, a_seq, b_seq)
            if st:
                keys.append(k)
                raw.append(st)
    if not raw:
        return {}

    # 前向填充开头那段「样本还不够」的空白
    seq, cur = [], raw[0]
    for st in raw:
        cur = st
        seq.append(cur)

    sm = []
    for i in range(len(seq)):
        w = seq[max(0, i - 1): i + 2]
        top = Counter(w).most_common()
        # 三值各异的平票局面：保留原判，避免随机跳色
        sm.append(seq[i] if len(top) > 1 and top[0][1] == top[1][1] else top[0][0])
    if current:
        sm[-1] = current
    return dict(zip(keys, sm))


def _step_round(pts: list[tuple[float, float]], r: float = 4.2) -> str:
    """阶梯路径，转角倒圆角。

    只磨掉直角，不移动任何水平段 / 垂直段的位置——数据仍然是
    「一个季度内数值不变、到季度点跳变」的语义，只是看着不那么硬。
    """
    d = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dy = y1 - y0
        if abs(dy) < 0.8:                       # 几乎等高，不必倒角
            d.append(f" L{x1:.1f},{y1:.1f}")
            continue
        rr = min(r, abs(dy) / 2, max(1.0, abs(x1 - x0) / 2))
        sgn = 1.0 if dy > 0 else -1.0
        d.append(f" L{x1 - rr:.1f},{y0:.1f}")
        d.append(f" Q{x1:.1f},{y0:.1f} {x1:.1f},{y0 + sgn * rr:.1f}")
        d.append(f" L{x1:.1f},{y1:.1f}")
    return "".join(d)


def _monotone(pts: list[tuple[float, float]]) -> str:
    """Fritsch–Carlson 单调三次插值 → SVG path。

    为什么不用普通的 Catmull-Rom 样条：那玩意儿会在相邻数据点之间
    **overshoot**，凭空造出数据里并不存在的波峰波谷。这个模型靠极值判断
    拐点，伪造极值等于伪造信号。单调插值保证曲线通过每一个数据点、
    且在每个区间内不越界，只把折角磨圆——视觉柔和，读数不变。
    """
    n = len(pts)
    if n < 3:
        return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    dx = [xs[i + 1] - xs[i] for i in range(n - 1)]
    dy = [ys[i + 1] - ys[i] for i in range(n - 1)]
    m = [dy[i] / dx[i] if dx[i] else 0.0 for i in range(n - 1)]

    # 各点切线：单调区间用加权调和平均，极值点压成水平（这是不 overshoot 的关键）
    t = [0.0] * n
    t[0], t[-1] = m[0], m[-1]
    for i in range(1, n - 1):
        if m[i - 1] * m[i] <= 0:
            t[i] = 0.0
        else:
            w1, w2 = 2 * dx[i] + dx[i - 1], dx[i] + 2 * dx[i - 1]
            t[i] = (w1 + w2) / (w1 / m[i - 1] + w2 / m[i])

    d = [f"M{xs[0]:.1f},{ys[0]:.1f}"]
    for i in range(n - 1):
        h = dx[i]
        d.append(
            f" C{xs[i] + h / 3:.1f},{ys[i] + t[i] * h / 3:.1f}"
            f" {xs[i + 1] - h / 3:.1f},{ys[i + 1] - t[i + 1] * h / 3:.1f}"
            f" {xs[i + 1]:.1f},{ys[i + 1]:.1f}")
    return "".join(d)


def dual(series_a, series_b, *, name_a: str, name_b: str, kind: str,
         months: int = 30, step_a: bool = False, smooth: bool = True,
         current: str | None = None, refs_a: list = (), refs_b: list = ()) -> str:
    """双线走势图（SVG 字符串）。

    kind: "cycle"（美林时钟）/ "money"（货币周期），决定色带按哪套阶段命名。
    step_a: 主指标是否季度数据（True 时画成阶梯，避免把台阶读成斜坡）。
    smooth: 折线是否做单调三次平滑（默认开；关掉可看原始折线）。
    current: 模型层当前阶段，用于锚定色带末端。
    refs_a / refs_b: 参考水平线 [(数值, 标签, 颜色)]，分别画在左轴 / 右轴上。
                     参考值会并入该轴的取值域，保证线一定可见——
                     否则阈值落在数据范围外时，那条线会凭空消失，
                     读者会以为"这条线不重要"，恰恰相反。
    """
    rows, ma, mb = _align(series_a, series_b, months)
    if len(rows) < 8:
        return '<div class="src" style="padding:20px 0">历史序列不足，暂无法绘制走势曲线</div>'

    W, H = 640, 250
    L, R, T, B = 48, 576, 26, 168
    n = len(rows)
    a_sel = [r[1] for r in rows]
    b_sel = [r[2] for r in rows]

    def _span_with_refs(sel, refs):
        vals = [v for v in sel if v is not None]
        vals += [r[0] for r in refs]
        return _span(vals)

    alo, ahi = _span_with_refs(a_sel, refs_a)
    blo, bhi = _span_with_refs(b_sel, refs_b)

    step = (R - L) / (n - 1)

    def X(i: float) -> float:
        return L + i * step

    def YA(v: float) -> float:
        return B - (v - alo) / (ahi - alo) * (B - T)

    def YB(v: float) -> float:
        return B - (v - blo) / (bhi - blo) * (B - T)

    s: list[str] = [f'<svg viewBox="0 0 {W} {H}" width="100%" '
                    f'style="display:block;overflow:visible" role="img">']

    # ── 网格 + 双轴刻度 ──
    for t in (0.0, 1 / 3, 2 / 3, 1.0):
        y = B - t * (B - T)
        dash = "" if t in (0.0, 1.0) else ' stroke-dasharray="3 4"'
        s.append(f'<line x1="{L}" y1="{y:.1f}" x2="{R}" y2="{y:.1f}" '
                 f'stroke="#eef1f5" stroke-width="1"{dash}/>')
        va, vb = alo + t * (ahi - alo), blo + t * (bhi - blo)
        s.append(f'<text x="{L - 7}" y="{y + 3.4:.1f}" text-anchor="end" '
                 f'font-size="9.5" fill="{COLOR_A}" opacity=".85">{va:.1f}</text>')
        s.append(f'<text x="{R + 7}" y="{y + 3.4:.1f}" text-anchor="start" '
                 f'font-size="9.5" fill="{COLOR_B}" opacity=".85">{vb:.1f}</text>')

    # ── 参考水平线 ──
    def ref_lines(pairs):
        """pairs = [(refs, ymap, side), ...]，side 决定标签贴在左边界还是右边界。

        为什么不统一贴左边：左右两轴的线落在同一块画布里可能只差几像素
        （社融 10% 与 PPI 3% 实测相差 8px），挤在一起时分不清哪条属于哪个轴，
        更糟的是标签会被另一条线穿过。按轴分边放，既分开又能标明归属。
        同一边上的多条线仍要做推挤。
        """
        groups = {"L": [], "R": []}
        for refs, ymap, side in pairs:
            for val, label, color in refs:
                y = ymap(val)
                if T - 1 <= y <= B + 1:
                    groups[side].append([y, label, color])
        out = []
        for side, items in groups.items():
            items.sort(key=lambda x: x[0])
            prev_ty = -1e9
            for y, label, color in items:
                ty = max(y - 3.4, prev_ty + 10.5)
                ty = min(ty, B + 7)
                prev_ty = ty
                out.append(f'<line x1="{L}" y1="{y:.1f}" x2="{R}" y2="{y:.1f}" '
                           f'stroke="{color}" stroke-width="1" stroke-dasharray="4 4" '
                           f'opacity=".55"/>')
                # 右侧标签不贴到边界：末点数值标签就占着 R-26 ~ R-6 那一小块，
                # 往里让 44px 两边才不相撞
                out.append(_tag(L + 3, ty, label, color) if side == "L"
                           else _tag(R - 44, ty, label, color, anchor="end"))
        return out

    # ── 阶段色带（底部） ──
    band = _band(rows, ma, mb, kind, rows[0][0], current)
    band_y, band_h = 174, 9
    for i, (k, _, _) in enumerate(rows):
        st = band.get(k)
        if not st:
            continue
        x0 = max(L, X(i) - step / 2)
        x1 = min(R, X(i) + step / 2)
        s.append(f'<rect x="{x0:.1f}" y="{band_y}" width="{max(0.8, x1 - x0):.1f}" '
                 f'height="{band_h}" fill="{PHASE_COLOR.get(st, "#eef1f5")}">'
                 f'<title>{_label(k)}　{st}</title></rect>')
    s.append(f'<text x="{L - 7}" y="{band_y + 6.6}" text-anchor="end" '
             f'font-size="8.5" fill="#8494a8">阶段</text>')

    # ── 时间轴 ──
    tick_idx = sorted({0, n // 3, n // 3 * 2, n - 1})
    for i in tick_idx:
        s.append(f'<text x="{X(i):.1f}" y="{band_y + band_h + 13}" text-anchor="middle" '
                 f'font-size="9" fill="#8494a8">{_label(rows[i][0])}</text>')

    # ── 两条曲线 ──
    def draw(sel, ymap, color, is_step):
        pts = [(X(i), ymap(v)) for i, v in enumerate(sel) if v is not None]
        if len(pts) < 2:
            return "", None, None
        if is_step:
            d = _step_round(pts)
        elif smooth:
            d = _monotone(pts)
        else:
            d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        s.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.1" '
                 f'stroke-linejoin="round" stroke-linecap="round" opacity=".92"/>')
        return d, pts[-1][0], pts[-1][1]

    _, xa, ya = draw(a_sel, YA, COLOR_A, step_a)
    _, xb, yb = draw(b_sel, YB, COLOR_B, False)

    # 参考线必须画在曲线**之后**：SVG 没有 z-index，先画的在下层。
    # 之前放在网格后面，结果标签的白色底板被曲线整个盖住，等于没画。
    s.extend(ref_lines([(refs_a, YA, "L"), (refs_b, YB, "R")]))

    # ── 末点：实心点 + 数值标签（两条线贴太近时上下错开） ──
    if None not in (xa, xb, ya, yb) and abs(ya - yb) < 13:
        ya, yb = ya - 7, yb + 7

    last_a = next((v for v in reversed(a_sel) if v is not None), None)
    last_b = next((v for v in reversed(b_sel) if v is not None), None)
    for x, y, color, val in ((xa, ya, COLOR_A, last_a),
                             (xb, yb, COLOR_B, last_b)):
        if x is None or val is None:
            continue
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.4" fill="#fff" '
                 f'stroke="{color}" stroke-width="2.2"/>')
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.6" fill="{color}"/>')
        # 标签放点的左上方：右侧要留给坐标轴刻度，正上方可能压住曲线本身；
        # 再描一圈白边，两条线末点重合时也不至于糊成一团
        ty = y - 11 if y - 11 > T + 5 else y + 16
        s.append(f'<text x="{x - 7:.1f}" y="{ty:.1f}" text-anchor="end" '
                 f'font-size="10.5" font-weight="700" fill="{color}" '
                 f'stroke="#fff" stroke-width="3" stroke-linejoin="round" '
                 f'paint-order="stroke">{val:.1f}</text>')

    # ── 图例 ──
    leg_y = H - 10
    # 期次取该指标真实最新报告期，不能用「最后一个有值的月份」——
    # GDP 是季度值，前向填充后每个月都有值，会误显示成最新月
    latest_a = _label(max(ma))
    s.append(f'<line x1="{L}" y1="{leg_y - 3.4}" x2="{L + 16}" y2="{leg_y - 3.4}" '
             f'stroke="{COLOR_A}" stroke-width="2.1"/>')
    s.append(f'<text x="{L + 21}" y="{leg_y}" font-size="10" fill="#4a5a6c">'
             f'{name_a} <tspan fill="#8494a8">{latest_a}</tspan></text>')
    s.append(f'<line x1="{L + 168}" y1="{leg_y - 3.4}" x2="{L + 184}" y2="{leg_y - 3.4}" '
             f'stroke="{COLOR_B}" stroke-width="2.1"/>')
    s.append(f'<text x="{L + 189}" y="{leg_y}" font-size="10" fill="#4a5a6c">'
             f'{name_b}</text>')

    # ── 阶段切换点：在色带上补竖线，标出「这一格是什么时候换的」 ──
    prev = None
    for i, (k, _, _) in enumerate(rows):
        st = band.get(k)
        if st and prev and st != prev:
            s.append(f'<line x1="{X(i) - step / 2:.1f}" y1="{band_y - 1}" '
                     f'x2="{X(i) - step / 2:.1f}" y2="{band_y + band_h + 1}" '
                     f'stroke="#fff" stroke-width="1.4"/>')
        if st:
            prev = st

    s.append("</svg>")
    return "".join(s)


# ── 模型③ ERP 曲线 ─────────────────────────────────────────────────

# 估值档位 → 背景分区底色。与仪表条、四象限、评分数字保持同一套语言：
# 红 = 便宜 / 该买，绿 = 贵 / 该卖。早先这里是「绿便宜红贵」，结果同一页上
# ERP 曲线说绿是好、旁边的仪表条说红是好，两种相反的读法，比不涂色更糟。
ERP_ZONE = [
    (6.0, 99.0, "#fbe3dd", "买入区"),
    (4.5, 6.0, "#fdf1ee", "偏低估"),
    (3.0, 4.5, "#f7f8fa", "中性"),
    (-99.0, 3.0, "#e7f1ea", "高估区"),
]


def erp_curve(rows, *, buy: float = 6.0, mid: float = 4.5, sell: float = 3.0) -> str:
    """ERP（股权风险溢价）月度曲线。

    与模型①②的双线图有一个关键差别：这条线的阈值是**固定水平线**。
    因为 10Y 国债收益率已经在 ERP 公式里被减掉了，不需要像 PE 那样随利率
    调整临界值。这正是 ERP 比 PE 更适合跨年份比较的原因 ——
    2018 年 PE 16.3 倍算贵、2026 年 PE 13 倍算便宜，中间隔着几个百分点的
    无风险利率；ERP 把利率剥掉之后，6% / 3% 这两条线八年都不用动。
    """
    pts_in = [(str(d)[:10], float(v)) for d, v in rows if v is not None]
    if len(pts_in) < 12:
        return ('<div class="src" style="padding:24px 0">'
                'ERP 历史序列不足，暂无法绘制曲线</div>')

    W, H = 720, 258
    L, R, T, B = 46, 646, 24, 216
    n = len(pts_in)
    vals = [v for _, v in pts_in]

    lo = math.floor(min(min(vals), sell - 0.4) * 2) / 2
    hi = math.ceil((max(max(vals), buy) + 0.32) * 2) / 2
    step = (R - L) / (n - 1)

    def X(i: float) -> float:
        return L + i * step

    def Y(v: float) -> float:
        return B - (v - lo) / (hi - lo) * (B - T)

    s: list[str] = [f'<svg viewBox="0 0 {W} {H}" width="100%" '
                    f'style="display:block;overflow:visible" role="img">']

    # ── 估值档位背景分区 ──
    for zlo, zhi, color, name in ERP_ZONE:
        y0, y1 = Y(min(zhi, hi)), Y(max(zlo, lo))
        if y1 - y0 < 0.6:
            continue
        s.append(f'<rect x="{L}" y="{y0:.1f}" width="{R - L}" '
                 f'height="{y1 - y0:.1f}" fill="{color}"><title>{name}</title></rect>')

    # ── 水平网格 + 左轴刻度（0.5% 一格，整数标数字） ──
    v = lo
    while v <= hi + 1e-9:
        y = Y(v)
        s.append(f'<line x1="{L}" y1="{y:.1f}" x2="{R}" y2="{y:.1f}" '
                 f'stroke="#ffffff" stroke-width="1" opacity=".85"/>')
        if abs(v - round(v)) < 1e-9:
            s.append(f'<text x="{L - 7}" y="{y + 3.4:.1f}" text-anchor="end" '
                     f'font-size="9.5" fill="#8494a8">{v:.0f}%</text>')
        v += 0.5
    for xe in (T, B):
        s.append(f'<line x1="{L}" y1="{xe}" x2="{R}" y2="{xe}" '
                 f'stroke="#dde4ec" stroke-width="1"/>')

    # ── 三条阈值线 ──
    for yv, color, dash, label in (
            (buy, "#1a7f5a", "5 4", "买入 6%"),
            (mid, "#a7b4c4", "2 4", "中性 4.5%"),
            (sell, "#c0392b", "5 4", "卖出 3%")):
        if not lo < yv < hi:
            continue
        y = Y(yv)
        s.append(f'<line x1="{L}" y1="{y:.1f}" x2="{R}" y2="{y:.1f}" '
                 f'stroke="{color}" stroke-width="1.3" stroke-dasharray="{dash}" '
                 f'opacity=".7"/>')
        s.append(f'<text x="{R + 7}" y="{y + 3.4:.1f}" font-size="9" '
                 f'fill="{color}" opacity=".95">{label}</text>')

    # ── 年份分隔（竖向淡线 + 底部标签） ──
    for i, (d, _v) in enumerate(pts_in):
        if d[5:7] == "01" and (i == 0 or pts_in[i - 1][0][:4] != d[:4]):
            s.append(f'<line x1="{X(i):.1f}" y1="{T}" x2="{X(i):.1f}" y2="{B}" '
                     f'stroke="#e7edf3" stroke-width="1"/>')
            s.append(f'<text x="{X(i):.1f}" y="{B + 15}" text-anchor="middle" '
                     f'font-size="9" fill="#8494a8">{d[:4]}</text>')

    # ── 主曲线 ──
    pix = [(X(i), Y(v)) for i, (_d, v) in enumerate(pts_in)]
    s.append(f'<path d="{_monotone(pix)}" fill="none" stroke="{COLOR_A}" '
             f'stroke-width="2.1" stroke-linejoin="round" stroke-linecap="round"/>')

    # ── 历史极值标注（最有说服力的两个锚点） ──
    # 最低点贴近 X 轴，标签放到点的右侧偏上（曲线此时已爬升，右侧同高处是空白）；
    # 最高点靠近顶部，标签放在点上方。
    hi_i = max(range(n), key=lambda i: pts_in[i][1])
    lo_i = min(range(n), key=lambda i: pts_in[i][1])
    for idx, tone, tag, below in ((lo_i, "#c0392b", "最贵", True),
                                  (hi_i, "#1a7f5a", "最便宜", False)):
        x, y = X(idx), Y(pts_in[idx][1])
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#fff" '
                 f'stroke="{tone}" stroke-width="1.8"/>')
        if x < L + 46:
            anchor, dx, dy = "start", 9, (-3 if below else -11)
        elif x > R - 46:
            anchor, dx, dy = "end", -9, (16 if below else -11)
        else:
            anchor, dx, dy = "middle", 0, (16 if below else -11)
        s.append(f'<text x="{x + dx:.1f}" y="{y + dy:.1f}" '
                 f'text-anchor="{anchor}" font-size="9" font-weight="600" '
                 f'fill="{tone}">{pts_in[idx][1]:.2f}% {tag}</text>')

    # ── 当前点 ──
    cx, cy = X(n - 1), Y(pts_in[-1][1])
    s.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{R}" y2="{cy:.1f}" '
             f'stroke="{COLOR_A}" stroke-width="1" stroke-dasharray="2 3" opacity=".5"/>')
    s.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4.4" fill="#fff" '
             f'stroke="{COLOR_A}" stroke-width="2.2"/>')
    s.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="1.6" fill="{COLOR_A}"/>')
    s.append(f'<text x="{cx - 2:.1f}" y="{cy - 10:.1f}" text-anchor="end" '
             f'font-size="10.5" font-weight="700" fill="{COLOR_A}" '
             f'stroke="#fff" stroke-width="3" paint-order="stroke">'
             f'{pts_in[-1][1]:.2f}%</text>')

    # ── 每月悬浮明细 ──
    for i, (d, v) in enumerate(pts_in):
        s.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="4" fill="transparent">'
                 f'<title>{d[:7]}　ERP {v:.2f}%</title></circle>')

    s.append("</svg>")
    return "".join(s)


# ── 单指标曲线（六大指标 + RSI） ────────────────────────────────────

_SEQ = [0]


def single(series, *, unit: str = "%", refs: list = (), since: str | None = None,
           step: bool = False, decimals: int = 1, W: int = 400, H: int = 186,
           vmin: float | None = None, vmax: float | None = None,
           ref_labels: bool = True, end_label: bool = True) -> str:
    """单条序列 + 参考水平线的小图（用于六大指标卡、RSI 卡）。

    与 dual() 的差别：只有一条线，所以不必双轴，参考线直接压在数据上。
    横轴用**真实月份**而非等距序号——社融缺 2 期、GDP 只按季度出点，
    等距排布会把「3 个月没数据」和「数据没变化」画成同一件事。

    refs: [(数值, 标签, 颜色)]
    vmin / vmax: 强制取值域上下限。RSI 是有界振荡器（0~100），
                 不夹住的话自动 padding 会画出 -1.2 ~ 108.8 这种莫明其妙的刻度。
    ref_labels: 是否在线上写文字。小卡片（三列布局）里坐标刻度离左边界只有 30px，
                 参考线标签必然和刻度数字打架——那种场合交给卡片下方的彩色 chips，
                 图上只留虚线。
    end_label: 是否在末点旁写数值。卡片头部已用大字号显示现值，
                 图上再写一遍就是同一个数字出现两次，纯噪声。
    """
    pts_in = [(str(d)[:10], float(v)) for d, v in (series or []) if v is not None]
    if since:
        pts_in = [x for x in pts_in if x[0] >= since]
    if len(pts_in) < 6:
        return '<div class="src" style="padding:18px 0">历史序列不足，暂无法绘制</div>'

    _SEQ[0] += 1
    L, R, T, B = 34, W - 12, 14, H - 42
    ms = [_ordinal(d) for d, _ in pts_in]
    m0, m1 = ms[0], ms[-1]
    span = max(1, m1 - m0)
    vals = [v for _, v in pts_in]
    if vmin is not None and vmax is not None:
        lo, hi = vmin, vmax
    else:
        lo, hi = _span(vals + [r[0] for r in refs], pad=0.16)

    def X(m: float) -> float:
        return L + (m - m0) / span * (R - L)

    def Y(v: float) -> float:
        return B - (v - lo) / (hi - lo) * (B - T)

    s: list[str] = [f'<svg viewBox="0 0 {W} {H}" width="100%" '
                    f'style="display:block;overflow:visible" role="img">']

    # 网格 + 左轴刻度（3 条）
    for t in (0.0, 0.5, 1.0):
        v = lo + t * (hi - lo)
        y = Y(v)
        s.append(f'<line x1="{L}" y1="{y:.1f}" x2="{R}" y2="{y:.1f}" '
                 f'stroke="#eef1f5" stroke-width="1"/>')
        s.append(f'<text x="{L - 5}" y="{y + 3.2:.1f}" text-anchor="end" '
                 f'font-size="8.5" fill="#9aa8b8">{v:.1f}</text>')

    # 横轴刻度：跨度 ≥14 个月标年份，否则标月份。
    # 只标年份在近半年的图上会退化成一个「26」——读者根本看不出这几个月是哪几个月，
    # 而 RSI 这类日频图讲的正是「最近这段发生了什么」。
    _months = sorted({d[:7] for d, _v in pts_in})
    by_month = len(_months) <= 14
    prev_lab = None
    for d, _v in pts_in:
        lab = d[5:7] if by_month else d[:4]
        if lab == prev_lab:
            continue
        if by_month and prev_lab is not None and int(lab) % 2:
            # 月份模式只标偶数月，否则 6 个刻度挤在 400px 里糊成一片
            prev_lab = lab
            continue
        if prev_lab is not None:
            x = X(_ordinal(d))
            s.append(f'<line x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{B}" '
                     f'stroke="#f0f3f7" stroke-width="1"/>')
        _x = X(_ordinal(d))
        # 末点落在 x=R 上，居中的文字会溢到图外 → 靠边的刻度改为向内对齐
        _anchor = "end" if _x > R - 8 else ("start" if _x < L + 8 else "middle")
        s.append(f'<text x="{_x:.1f}" y="{B + 13}" '
                 f'text-anchor="{_anchor}" font-size="8.5" fill="#9aa8b8">'
                 f'{lab + "月" if by_month else lab}</text>')
        prev_lab = lab

    # 月份模式下把年份补在右端，避免「06月 08月 10月」看不出是哪一年
    if by_month and len(_months) > 1:
        _y0, _y1 = _months[0][:4], _months[-1][:4]
        tag = _y0[2:] if _y0 == _y1 else f"{_y0[2:]}/{_y1[2:]}"
        s.append(f'<text x="{R:.1f}" y="{B + 22}" text-anchor="end" '
                 f'font-size="8.5" fill="#9aa8b8">{tag} 年</text>')

    # 面积 + 曲线
    pix = [(X(m), Y(v)) for m, (_d, v) in zip(ms, pts_in)]
    d_path = _step_round(pix) if step else _monotone(pix)
    s.append(f'<path d="{d_path} L{pix[-1][0]:.1f},{B} L{pix[0][0]:.1f},{B} Z" '
             f'fill="{COLOR_A}" opacity=".055" stroke="none"/>')
    s.append(f'<path d="{d_path}" fill="none" stroke="{COLOR_A}" stroke-width="1.9" '
             f'stroke-linejoin="round" stroke-linecap="round"/>')

    # 参考线画在曲线之后（SVG 后画的在上层），标签才不会被线压住
    items = sorted(([Y(val), label, color] for val, label, color in refs),
                   key=lambda x: x[0])
    prev_ty = -1e9
    for y, label, color in items:
        ty = min(max(y - 3.2, prev_ty + 9.8), B + 6)
        prev_ty = ty
        s.append(f'<line x1="{L}" y1="{y:.1f}" x2="{R}" y2="{y:.1f}" '
                 f'stroke="{color}" stroke-width="1" stroke-dasharray="4 4" '
                 f'opacity=".6"/>')
        if ref_labels:
            s.append(_tag(L + 3, ty, label, color, fs=8.0))

    # 末点
    cx, cy = pix[-1]
    s.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.6" fill="#fff" '
             f'stroke="{COLOR_A}" stroke-width="2"/>')
    if end_label:
        ty = cy - 7 if cy - 7 > T + 6 else cy + 13
        s.append(f'<text x="{cx - 6:.1f}" y="{ty:.1f}" text-anchor="end" '
                 f'font-size="9.5" font-weight="700" fill="{COLOR_A}" '
                 f'stroke="#fff" stroke-width="2.8" stroke-linejoin="round" '
                 f'paint-order="stroke">{pts_in[-1][1]:.{decimals}f}{unit}</text>')

    # 悬浮明细每 3 期一个即可，几十个 title 只会把 DOM 撑大
    for i in range(0, len(pts_in), 3):
        d, v = pts_in[i]
        s.append(f'<circle cx="{X(ms[i]):.1f}" cy="{Y(v):.1f}" r="5" fill="transparent">'
                 f'<title>{d[:7]}　{v:.{decimals}f}{unit}</title></circle>')

    s.append("</svg>")
    return "".join(s)
