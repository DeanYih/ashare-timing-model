# -*- coding: utf-8 -*-
"""渲染层：把一次运行结果渲染成单文件 HTML 仪表盘（离线可看，无外部依赖）。

信息架构（2026-10 重构）：
  ① 结论条      —— 一眼看完：评分 / 仓位 / 四层共振 / 关键读数
  ② 四大模型    —— 每个模型一行：结论在左、证据（曲线带参考线）在中、落点在右
  ③ 六大指标    —— 每个指标一张小卡：2018 年至今的曲线 + 参考线 + 现值/时滞
  ④ 参考线核验  —— 每条参考线的依据等级与实测区分力
  ⑤ 数据源头    —— 折叠，需要溯源时才展开

重构前的毛病：同一个模型在「评分卡」和「图表」里各出现一次，模型③ 的统计又单独占一节；
口径说明是一大段 800 字文本压在最下面，谁都不会读。现在每个模型只有一处，说明按需展开。
"""
from __future__ import annotations

import html
import re

from . import curves as cv
from . import refs as rf
from .config import INDICATORS, MARKET

CSS = """
:root{
  --bg:#f4f6f8; --card:#fff; --ink:#16202c; --sub:#6b7a8d; --line:#e3e8ee;
  --bull:#c0392b; --bear:#1a7f5a; --warn:#c88a00; --neutral:#8494a8;
  --shadow:0 1px 2px rgba(16,32,48,.05),0 8px 22px -14px rgba(16,32,48,.18);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
  -webkit-font-smoothing:antialiased;line-height:1.55}
.wrap{max-width:1200px;margin:0 auto;padding:28px 22px 56px}
h1{font-size:22px;margin:0 0 4px;letter-spacing:-.3px}
.sub{color:var(--sub);font-size:12.5px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;
  box-shadow:var(--shadow)}
.sec{margin-top:24px}
.sec>h2{font-size:13px;font-weight:650;color:var(--sub);margin:0 0 10px;
  letter-spacing:.06em;display:flex;align-items:baseline;gap:8px}
.sec>h2 em{font-style:normal;font-weight:400;font-size:11.5px;color:#a3b0c0;
  letter-spacing:0}

/* ── 结论条 ── */
.verdict{display:grid;grid-template-columns:196px minmax(0,1fr);gap:22px;
  padding:20px 24px;margin-top:18px;border-left:5px solid var(--bull)}
.verdict.mid{border-left-color:var(--warn)}
.verdict.low{border-left-color:var(--bear)}
.score{display:flex;align-items:baseline;gap:4px}
.score b{font-size:48px;line-height:1;letter-spacing:-2px}
.score span{font-size:13px;color:var(--sub)}
.vtag{display:inline-block;margin-top:7px;padding:3px 11px;border-radius:20px;
  font-size:12.5px;font-weight:600;background:#fdecea;color:var(--bull)}
.vtag.mid{background:#fff7e3;color:var(--warn)}
.vtag.low{background:#e8f5ef;color:var(--bear)}
.pos{font-size:16px;font-weight:650}
.pos i{font-style:normal;color:var(--sub);font-weight:400;font-size:12.5px}
.posbar{margin-top:9px;height:6px;border-radius:5px;background:#eef1f5;overflow:hidden}
.posbar i{display:block;height:100%;border-radius:5px;
  background:linear-gradient(90deg,#e8b0a8,var(--bull))}
.readings{display:flex;gap:16px;flex-wrap:wrap;margin-top:10px;font-size:11.5px;
  color:var(--sub)}
.readings b{color:var(--ink);font-weight:650;font-variant-numeric:tabular-nums}
.gates{display:flex;gap:7px;flex-wrap:wrap;margin-top:11px}
.gpill{display:inline-flex;align-items:center;gap:4px;padding:2.5px 9px;
  border-radius:20px;font-size:11px;background:#f6f8fa;color:var(--sub);
  border:1px solid var(--line)}
.gpill.on{background:#fdecea;color:var(--bull);border-color:#f6d3cc}
.gpill i{font-style:normal;font-size:9.5px;opacity:.75}

/* ── 模型行 ── */
.mrow{padding:15px 18px 13px;margin-bottom:12px}
.mh{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.mh .nm{font-size:14px;font-weight:680}
.mh .ty{font-size:10px;color:var(--sub);border:1px solid var(--line);
  border-radius:5px;padding:0 5px}
.mh .deg{background:#fff7e3;color:var(--warn);font-size:10px;padding:0 6px;
  border-radius:5px;font-weight:600}
.mh .right{margin-left:auto;display:flex;align-items:baseline;gap:10px}
.msc{font-size:25px;font-weight:700;letter-spacing:-1px;
  font-variant-numeric:tabular-nums}
.msc i{font-size:10.5px;font-weight:500;color:var(--sub);font-style:normal;
  letter-spacing:0;margin-left:2px}
.mst{font-size:13px;font-weight:650}
.mst.bear{color:var(--bear)}.mst.mid{color:var(--warn)}
.mhint{font-size:11.5px;color:var(--sub);margin-top:2px}
.panel{display:grid;grid-template-columns:minmax(0,1fr) 336px;gap:20px;
  align-items:start;margin-top:9px}
.curvebox{min-width:0}
.curvebox svg{max-width:100%}
.cap{font-size:10.5px;color:var(--sub);margin-top:5px;line-height:1.62}
.cap .lgrow{margin-top:2px}
.cap .lg{white-space:nowrap;margin-right:8px}
.cap .lg i{display:inline-block;width:9px;height:9px;border-radius:2px;
  vertical-align:-1px;margin-right:3px;box-shadow:inset 0 0 0 1px rgba(16,32,48,.13)}
.clock svg{width:100%;height:auto}
.side{border-left:1px dashed var(--line);padding-left:18px}
.side h4{font-size:11px;color:var(--sub);margin:0 0 6px;font-weight:650;
  letter-spacing:.04em}
.krow{display:flex;justify-content:space-between;gap:8px;padding:4px 0;
  border-bottom:1px dashed var(--line);font-size:11.5px}
.krow:last-child{border-bottom:0}
.krow span{color:var(--sub)}
.krow b{font-weight:650;font-variant-numeric:tabular-nums}

/* ── 仪表 ── */
.gwrap{position:relative;height:14px;border-radius:9px;margin:26px 0 4px}
.gmark{position:absolute;top:-5px;width:3px;height:24px;border-radius:2px;
  background:#16202c;box-shadow:0 0 0 3px #fff,0 1px 4px rgba(0,0,0,.25)}
.glab{position:relative;height:13px;font-size:10px;color:var(--sub)}
.glab span{position:absolute;top:0;transform:translateX(-50%)}

/* ── 六大指标 ──
   卡片的字号是四层递降的，靠这个建立阅读顺序，而不是靠加框加线：
     中文全称 11.5 → 英文全称 9.5（最淡，只作对照）
     → 作用 10.5（中灰）→ 数据元信息 10（浅灰）
   加释义的代价是每卡多两行，如果四行都用同一个灰度，六张卡会糊成一片灰。 */
.igrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
/* 六张卡的参考线数量不等（CPI 有 3 条、M2 只有 1 条），chips 换行行数就不同；
   grid 会把整行拉到最高那张的高度，短卡下面于是留一截空白。
   用 flex 列 + margin-top:auto 把 chips 压到同一条基线上，空白就跑到图上方去了。 */
.icard{padding:13px 15px 9px;display:flex;flex-direction:column}
.ih{display:flex;align-items:baseline;gap:6px}
.ih .code{font-size:13px;font-weight:680;letter-spacing:.02em}
.ih .cn{font-size:11.5px;color:#4d5f73;font-weight:500}
.ih .role{font-size:9.5px;color:var(--sub);border:1px solid var(--line);
  border-radius:4px;padding:0 4px}
.ih .val{margin-left:auto;font-size:19px;font-weight:700;
  font-variant-numeric:tabular-nums;letter-spacing:-.5px}
.ien{font-size:9.5px;color:#a9b6c5;letter-spacing:.15px;margin:0 0 2px}
.iuse{font-size:10.5px;color:#55677b;line-height:1.5;margin:0 0 3px}
.imeta{font-size:10px;color:var(--sub);margin:0 0 5px;
  font-variant-numeric:tabular-nums}
.imeta b{color:var(--ink);font-weight:600}
.imeta .up{color:var(--bull)}.imeta .down{color:var(--bear)}
.imeta .flat{color:var(--neutral)}
.rchips{display:flex;gap:5px;flex-wrap:wrap;margin:0 0 2px;
  margin-top:auto;padding-top:6px}
.rchip{font-size:9.5px;padding:1px 6px;border-radius:10px;background:#f4f6f8;
  color:#8b98a8;border:1px solid #eceff3}
/* 已触发时才上色，且颜色跟随这条线的角色（利空红/利好绿/描述灰蓝）。
   曾经一律用红色：结果「PPI≤0 工业通缩」这种利好线一触发就变红，
   与它右侧的绿色圆点自相矛盾。 */
.rchip.on{font-weight:600}
.rchip.on.r-warn{background:#fdf0ee;color:#b3392b;border-color:#f4d6d0}
.rchip.on.r-good{background:#eaf4ee;color:#1a7f5a;border-color:#cfe6da}
.rchip.on.r-state{background:#eef2f7;color:#4f6275;border-color:#dbe3ec}
.rchip i{display:inline-block;width:6px;height:6px;border-radius:1px;
  margin-right:4px;vertical-align:0;opacity:.55}
.rchip.on i{opacity:1}

/* ── 参考线核验 ── */
table{width:100%;border-collapse:collapse;table-layout:fixed}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line);
  vertical-align:top}
th{font-size:10px;color:var(--sub);font-weight:600;letter-spacing:.05em;
  background:#fafbfc;white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
td{font-size:11.5px}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.lv{display:inline-block;padding:0 5px;border-radius:4px;font-size:10px;
  font-weight:600;white-space:nowrap}
.lv-定义性{background:#fdecea;color:#b3392b}
.lv-政策目标{background:#fff7e3;color:#a37400}
.lv-经验值{background:#eef1f5;color:#5b6b7f}
.vd{font-weight:600}
.vd.good{color:var(--bear)}.vd.mid{color:var(--warn)}.vd.warn{color:var(--warn)}
.vd.muted{color:var(--neutral)}
.basis{color:var(--sub);font-size:10.5px;line-height:1.5}
/* 逐段差值：段内数字用等宽字体右对齐不现实（一行两元素），
   只把数字加粗上色，区间用小字——一眼看出「两段是不是一个方向」 */
td.segcell{padding-top:6px;padding-bottom:6px;overflow:hidden}
.segline{display:flex;align-items:baseline;gap:5px;white-space:nowrap;
  line-height:1.5}
.seg{font-size:11px;font-weight:700;font-variant-numeric:tabular-nums;
  min-width:33px;text-align:right;flex:0 0 auto}
.seg.pos{color:var(--bull)}.seg.neg{color:var(--bear)}
.segd{color:var(--sub);font-size:10px;font-variant-numeric:tabular-nums}
.segnote{color:var(--warn);font-size:10px;font-weight:600;margin-top:1px}
.chip{display:inline-block;padding:1px 7px;border-radius:5px;font-size:10.5px;
  font-weight:600}
.chip.up{background:#fdecea;color:var(--bull)}
.chip.down{background:#e8f5ef;color:var(--bear)}
.chip.flat{background:#eef1f5;color:var(--neutral)}
.chip.fresh{background:#eef1f5;color:#5b6b7f}
.chip.wait{background:#fff7e3;color:var(--warn)}
.chip.lag{background:#fff7e3;color:var(--warn)}
.chip.bad{background:#fdecea;color:var(--bear)}
.src{font-size:11px;color:var(--sub)}
.note{background:#fafbfc;border:1px solid var(--line);border-radius:12px;
  padding:13px 16px;font-size:11.5px;color:var(--sub);margin-top:12px;
  line-height:1.72}
.note b{color:var(--ink)}

/* ── 折叠区 ── */
details{background:var(--card);border:1px solid var(--line);border-radius:14px;
  box-shadow:var(--shadow);overflow:hidden}
details summary{cursor:pointer;padding:14px 18px;font-size:12.5px;font-weight:650;
  color:var(--sub);list-style:none;display:flex;align-items:center;gap:8px}
details summary::-webkit-details-marker{display:none}
details summary:after{content:"展开 ▾";margin-left:auto;font-size:11px;
  color:var(--neutral);font-weight:400}
details[open] summary:after{content:"收起 ▴"}
details .dbody{padding:2px 18px 16px}

/* 曲线图外层：桌面端宽度够，不出现滚动；窄屏才靠 min-width 触发横向滑动 */
.svscroll{overflow-x:auto;-webkit-overflow-scrolling:touch;overscroll-behavior-x:contain}
.svscroll svg{max-width:100%}
.svwrap{position:relative}
.svhint{display:none}
.svscroll::-webkit-scrollbar,.dscroll::-webkit-scrollbar{height:3px}
.svscroll::-webkit-scrollbar-thumb,.dscroll::-webkit-scrollbar-thumb{
  background:#d8e0e8;border-radius:3px}
.svscroll::-webkit-scrollbar-track,.dscroll::-webkit-scrollbar-track{
  background:transparent}
.dscroll{overflow-x:auto;-webkit-overflow-scrolling:touch}

@media(max-width:980px){
  .verdict{grid-template-columns:1fr}
  .panel{grid-template-columns:1fr}
  .side{border-left:0;padding-left:0;border-top:1px dashed var(--line);padding-top:12px}
  .igrid{grid-template-columns:1fr 1fr}
}
@media(max-width:1023px){
  /* ── 核验表转卡片 ──
     7 列在 375px 下被 table-layout:fixed 硬压，每列只剩几十像素，
     整张表变成一竖条（实测完全没法读）。这里把每个 <tr> 变成一张卡：
     指标代码作标题（tr[data-code]），每个 <td> 用 data-label 生成左侧字段名。
     桌面端保持表格不变。
     断点定 1024 而不是 680：表格固定列宽合计 720px，容器一窄就按比例压缩，
     900px 时结论列只剩 130px、文字被竖排（实测），700~880 更是直接崩成一条缝。 */
  #rt{background:none;border:0;box-shadow:none}
  #rt table,#rt thead,#rt tbody,#rt tr,#rt td{display:block}
  #rt thead{display:none}
  #rt tr{background:var(--card);border:1px solid var(--line);border-radius:12px;
    padding:12px 14px 8px;margin-bottom:10px;box-shadow:var(--shadow)}
  #rt tr::before{content:attr(data-code) " · " attr(data-name);
    display:block;font-size:13px;font-weight:680;
    padding-bottom:6px;margin-bottom:5px;
    border-bottom:1px solid var(--line)}
  #rt td{position:relative;padding:3px 0 3px 56px;border:0;
    font-size:11.5px;text-align:left;min-height:19px}
  #rt td::before{content:attr(data-label);position:absolute;left:0;top:4px;
    width:50px;font-size:10px;color:var(--sub);white-space:nowrap}
  /* 第一列是指标代码，手机端已由 tr::before 显示 */
  #rt td:first-child{display:none}
  #rt .basis{font-size:10.5px;line-height:1.55}
  #rt td.vd{font-weight:650}
  #rt td.vd .basis{font-weight:400}
  #rt td > b{font-size:13px}
  #rt .seg{font-size:12px}
  #rt .segline{gap:6px}
}
@media(max-width:680px){
  .igrid{grid-template-columns:1fr}
  .wrap{padding:20px 14px 40px}
  .sec>h2{display:block;line-height:1.5}
  .sec>h2 em{display:block;margin-top:3px;font-size:10.5px;line-height:1.55}


  /* 模型曲线 viewBox 宽 640，缩到 300px 后字号只剩 3~4px，参考线标签完全看不清。
     给个下限宽度让它能横向滑，宁可滑也不能把字压没。 */
  .svscroll svg{min-width:520px;max-width:none}
  .svhint{display:block;font-size:9px;text-align:right;color:#b6c1cd;
    margin:2px 0 5px;letter-spacing:.02em}
  /* 右侧渐隐：曲线被 520px 下限撑出横向滚动，硬切一刀会让读者以为图就到这里 */
  .svwrap::after{content:"";position:absolute;top:0;right:0;bottom:0;width:26px;
    background:linear-gradient(90deg,rgba(255,255,255,0),#fff 82%);
    pointer-events:none}
  .dscroll table{min-width:620px}
  .cap{font-size:10px;line-height:1.55}
  .msc{font-size:21px}
  .note{font-size:11px;line-height:1.65}
}
"""


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def _rich(s) -> str:
    """数据层习惯用 **加粗** 强调，直接塞进 HTML 会把星号原样露在页面上
    （参考线核验表的 caveat 就这么漏过一轮）。转成 <b> 再输出。"""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\g<1></b>", _esc(s))


def _today_short(res: dict) -> str:
    """日历的 describe() 返回「2026-10-22 交易日」，而副标题前面已经写了
    「数据截至 2026-10-22」，直接拼会念成「数据截至 X · X 交易日」。
    把日期前缀剥掉，只留判断（交易日 / 休市原因）。"""
    d = (res.get("today") or {}).get("desc", "")
    return re.sub(r"^\d{4}-\d{2}-\d{2}\s*", "", d)


def _per(d) -> str:
    return str(d)[:7] if d else "—"


def _md(d) -> str:
    return str(d)[5:10] if d else "—"


def _tone(score: float) -> str:
    return "high" if score >= 60 else ("mid" if score >= 40 else "low")


def _cls(tone: str) -> str:
    return "" if tone == "high" else tone


def _clock_svg(kind: str, dir_a: str, dir_b: str) -> str:
    """四象限：只画落点，不再画「从哪来」（那是曲线的活）。

    **两张图必须用同一套顺时针顺序**，否则并排看会互相干扰：
      模型①  左上复苏 → 右上过热 → 右下滞胀 → 左下衰退
      模型②  左上转向复苏 → 右上趋于过热 → 右下增长趋缓 → 左下步入衰退

    所以模型② 的轴分配是「横轴放价格 PPI、纵轴放信用 社融」，
    与模型① 的「横轴通胀、纵轴增长」同构。这不是随意摆的：
    周期演化本身是「衰退 → 复苏 → 过热 → 滞胀」的顺时针循环，
    而社融（信用）充当模型② 里的「量」、PPI 充当「价」，
    价放横轴、量放纵轴，时针才转得对。此前把社融放在横轴，
    顺时针排出来是「趋缓→过热→复苏→衰退」——一个逆着周期走的顺序，
    图上看着没坏，读起来全是反的。
    """
    def cell(cx, cy, w, h, label, assets, on, no):
        fill = "#fdf0ee" if on else "#fbfcfd"
        stroke = "#e6b8b0" if on else "#eef1f5"
        # 序号 1→2→3→4 就是顺时针步进，省掉读者自己在脑子里排顺序
        return (f'<rect x="{cx}" y="{cy}" width="{w}" height="{h}" rx="9" fill="{fill}" '
                f'stroke="{stroke}" stroke-width="{1.6 if on else 1}"/>'
                f'<circle cx="{cx + 13}" cy="{cy + 15}" r="7" fill="none" '
                f'stroke="{"#e5a89e" if on else "#d3dce6"}" stroke-width="1.1"/>'
                f'<text x="{cx + 13}" y="{cy + 18.2}" text-anchor="middle" '
                f'font-size="8.5" font-weight="700" '
                f'fill="{"#c0392b" if on else "#9dafc1"}">{no}</text>'
                f'<text x="{cx + w/2}" y="{cy + h/2 - 3}" text-anchor="middle" '
                f'font-size="12" font-weight="650" '
                f'fill="{"#c0392b" if on else "#5b6b7f"}">{label}</text>'
                f'<text x="{cx + w/2}" y="{cy + h/2 + 12}" text-anchor="middle" '
                f'font-size="9.5" fill="#9aa8b8">{assets}</text>')

    def axes(top, bottom, left, right, active=()):
        """active = 当前方向所在的两侧，如 ("bottom", "left")。

        四个轴标签原来一律浅灰，读者得自己在脑子里做「增长↓ 且 通胀↓ → 衰退」
        这一步推理；把命中的两侧加重后，落点就是自解释的：
        眼睛沿着加粗的两根轴走，交点必然是高亮格。
        用深灰不用红色——格子里已经有一处红，轴上再来两处红就分不清谁在说话。
        """
        def t(x, y, text, side, rot=""):
            on = side in active
            # 只靠 font-weight 680 在 9.5px 下几乎看不出差别（实测截图对比失败），
            # 所以同时放大字号并把未选中的再调淡一档，靠「大小 + 深浅」双重反差。
            return (f'<text x="{x}" y="{y}" text-anchor="middle" '
                    f'font-size="{11 if on else 9.5}" '
                    f'font-weight="{700 if on else 400}" '
                    f'fill="{"#2c3b4a" if on else "#a6b2c1"}"{rot}>{text}</text>')
        return (t("200", "10", top, "top")
                + t("200", "234", bottom, "bottom")
                + t("9", "120", left, "left", ' transform="rotate(-90 9,120)"')
                + t("391", "120", right, "right", ' transform="rotate(-90 391,120)"'))

    s = ['<svg viewBox="0 0 400 242" role="img">']
    # 纵轴看 dir_a、横轴看 dir_b，命中的那一侧加重
    v_side = "top" if dir_a == "up" else "bottom"
    h_side = "right" if dir_b == "up" else "left"
    if kind == "cycle":
        on = ("复苏" if (dir_a == "up" and dir_b == "down") else
              "过热" if (dir_a == "up" and dir_b == "up") else
              "滞胀" if (dir_a == "down" and dir_b == "up") else "衰退")
        s.append(axes("增长 ↑", "增长 ↓", "通胀 ↓", "通胀 ↑", (v_side, h_side)))
        s.append(cell(34, 20, 162, 94, "复苏", "股票 > 债券 > 现金", on == "复苏", 1))
        s.append(cell(204, 20, 162, 94, "过热", "商品 > 股票 > 现金", on == "过热", 2))
        s.append(cell(204, 122, 162, 94, "滞胀", "现金 > 商品 > 债券", on == "滞胀", 3))
        s.append(cell(34, 122, 162, 94, "衰退", "债券 > 现金 > 股票", on == "衰退", 4))
    else:
        on = ("转向复苏" if (dir_a == "up" and dir_b == "down") else
              "趋于过热" if (dir_a == "up" and dir_b == "up") else
              "增长趋缓" if (dir_a == "down" and dir_b == "up") else "步入衰退")
        # 轴顺序与模型① 一一对应：横轴=价格（通胀 / PPI），纵轴=量（增长 / 社融）
        s.append(axes("社融 ↑", "社融 ↓", "PPI ↓", "PPI ↑", (v_side, h_side)))
        s.append(cell(34, 20, 162, 94, "转向复苏", "股票最优", on == "转向复苏", 1))
        s.append(cell(204, 20, 162, 94, "趋于过热", "商品最优", on == "趋于过热", 2))
        s.append(cell(204, 122, 162, 94, "增长趋缓", "现金最优", on == "增长趋缓", 3))
        s.append(cell(34, 122, 162, 94, "步入衰退", "债券最优", on == "步入衰退", 4))
    s.append("</svg>")
    return "".join(s)


def _gauge(minv, maxv, val, zones, unit="%"):
    """横向刻度条 + 游标；zones=[(起,止,颜色,名)]"""
    span = maxv - minv
    grad = []
    for a, b, c, _ in zones:
        # 每个色标必须是「颜色 位置%, 颜色 位置%」——漏了逗号整条 gradient 会被判无效，
        # 浏览器直接不画背景（曾因此让仪表条整体消失）
        grad.append(f"{c} {(a-minv)/span*100:.2f}%, {c} {(b-minv)/span*100:.2f}%")
    pos = max(0.0, min(1.0, (val - minv) / span)) * 100
    ticks = "".join(
        f'<span style="left:{(z-minv)/span*100:.2f}%">{z:g}</span>'
        for z in ([minv] + [b for a, b, c, n in zones]))
    return (f'<div class="gwrap" style="background:linear-gradient(90deg,{",".join(grad)})">'
            f'<div class="gmark" style="left:calc({pos:.2f}% - 1.5px)"></div></div>'
            f'<div class="glab">{ticks}</div>')


def _erp_stats(hist) -> dict:
    pts = [(str(d)[:10], float(v)) for d, v in (hist or []) if v is not None]
    if len(pts) < 3:
        return {}
    vals = [v for _, v in pts]
    n = len(vals)
    cur = vals[-1]
    lo_v, hi_v = min(vals), max(vals)
    return {
        "n": n, "span": f"{pts[0][0][:7]} ~ {pts[-1][0][:7]}",
        "lo": lo_v, "lo_at": next(d for d, v in pts if v == lo_v)[:7],
        "hi": hi_v, "hi_at": next(d for d, v in pts if v == hi_v)[:7],
        "cur": cur,
        "pct": round(sum(1 for v in vals if v <= cur) / n * 100, 1),
        "n_buy": sum(1 for v in vals if v >= 6.0),
        "n_sell": sum(1 for v in vals if v < 3.0),
        "mean": round(sum(vals) / n, 2),
    }


def _macro_series(v: dict) -> list[tuple[str, float]]:
    return [(d, x) for d, x in (v.get("history_all") or v.get("history") or [])]


def render(res: dict) -> str:
    d = res["decision"]
    models = res["models"]
    macro = res["macro"]
    mkt = res["market"]
    tone = _tone(d["composite"])
    c = _cls(tone)

    cycle, money, erp, rsi = (models["cycle"], models["money"],
                              models["erp"], models["rsi"])

    # ── 四大模型：曲线（带参考线） ──
    def _ser(code):
        return _macro_series(macro.get(code, {}))

    ref_cycle = rf.flat_lines("CPI")
    ref_money_a = rf.flat_lines("SHRZ")
    ref_money_b = rf.flat_lines("PPI")

    curve_cycle = cv.dual(_ser("GDP"), _ser("CPI"), name_a="GDP 增速", name_b="CPI 同比",
                          kind="cycle", months=104, step_a=True,
                          current=cycle.get("stage"), refs_b=ref_cycle)
    curve_money = cv.dual(_ser("SHRZ"), _ser("PPI"), name_a="社融存量同比",
                          name_b="PPI 同比", kind="money", months=104,
                          current=money.get("stage"),
                          refs_a=ref_money_a, refs_b=ref_money_b)

    erp_hist = res.get("erp_history") or []
    curve_erp = cv.erp_curve(erp_hist) if len(erp_hist) >= 12 else ""
    es = _erp_stats(erp_hist)

    rsi_hist = res.get("rsi_history") or []
    # 只看近 6 个月的**日频**数据。RSI6 是快振荡器：
    # 画三年 → 2000 多个点压进 700 像素，糊成噪声；按周抽稀 → 混叠成锯齿。
    # 半年日频约 120 个点，既有足够上下文，读数又连续。
    _y, _m = int(res["as_of"][:4]), int(res["as_of"][5:7])
    _mm = _m - 6
    _y2, _m2 = _y + (_mm - 1) // 12, (_mm - 1) % 12 + 1
    since_rsi = f"{_y2}-{_m2:02d}"
    curve_rsi = cv.single(rsi_hist, unit="", refs=[
        (20, "超卖 20", "#b3392b"), (80, "超买 80", "#1a7f5a"),
    ], since=since_rsi, W=640, H=250, decimals=1, vmin=0, vmax=100) if rsi_hist else ""

    # 色带图例：方块直接取色带真色，避免「图例深红、色带浅粉」对不上号
    LEGEND = "".join(
        f'<span class="lg"><i style="background:{col}"></i>{k}</span>'
        for k, col in (("股票", cv.PHASE_COLOR["复苏"]),
                       ("商品", cv.PHASE_COLOR["过热"]),
                       ("现金", cv.PHASE_COLOR["滞胀"]),
                       ("债券", cv.PHASE_COLOR["衰退"])))

    # ── 四层确认（压成一行药丸，不再占一整节） ──
    gate_pills = "".join(
        f'<span class="gpill{" on" if g["pass"] else ""}" title="{_esc(g["detail"])}">'
        f'{"●" if g["pass"] else "○"} 第{i}层 {_esc(g["layer"][2:])}</span>'
        for i, g in enumerate(d["gates"], 1))

    def model_row(name, typ, m, stage_key, curve, side, cap):
        sc = m["score"]
        st = m.get(stage_key) or m.get("zone") or "—"
        stcls = "mst" if sc >= 60 else ("mst mid" if sc >= 40 else "mst bear")
        color = ("var(--bull)" if sc >= 60 else
                 ("var(--warn)" if sc >= 40 else "var(--bear)"))
        deg = '<span class="deg">降级</span>' if m.get("degraded") else ""
        return f'''
    <div class="card mrow">
      <div class="mh">
        <span class="nm">{_esc(name)}</span><span class="ty">{_esc(typ)}</span>{deg}
        <span class="right">
          <span class="msc" style="color:{color}">{sc:.1f}<i>/100</i></span>
          <span class="{stcls}">{_esc(st)}</span>
        </span>
      </div>
      <div class="mhint">{_esc(m.get("hint", ""))}</div>
      <div class="panel">
        <div class="curvebox"><div class="svwrap"><div class="svscroll">{curve}</div></div>
          <div class="svhint">左右滑动 →</div>
          <div class="cap">{cap}</div></div>
        <div class="side">{side}</div>
      </div>
    </div>'''

    # 模型①侧栏：象限
    cyc_a = cycle.get("axes", {}).get("增长(GDP)", {})
    cyc_b = cycle.get("axes", {}).get("通胀(CPI)", {})
    # 横轴方向必须用 quadrant 而不是原始 trend.dir：CPI 低于 1% 时会被
    # _infl_key 强制归到「低通胀」一侧，若照搬 dir，轴标签高亮会落在反侧，
    # 与高亮格自相矛盾。
    cyc_c = cyc_b.get("quadrant") or cyc_b.get("dir", "down")
    side_cycle = (
        f'<h4>当前落点</h4>{_clock_svg("cycle", cyc_a.get("dir", "down"), cyc_c)}'
        f'<div class="krow"><span>GDP 增速</span><b>{cyc_a.get("value", "—")}%</b></div>'
        f'<div class="krow"><span>CPI 同比</span><b>{cyc_b.get("value", "—")}%</b></div>'
        f'<div class="krow"><span>最受益资产</span><b>{_esc(cycle.get("rank", "—"))}</b></div>')

    mon_a = money.get("axes", {}).get("社融", {})
    mon_b = money.get("axes", {}).get("PPI", {})
    side_money = (
        f'<h4>当前落点</h4>{_clock_svg("money", mon_a.get("dir", "down"), mon_b.get("dir", "down"))}'
        f'<div class="krow"><span>社融存量同比</span><b>{mon_a.get("value", "—")}%</b></div>'
        f'<div class="krow"><span>PPI 同比</span><b>{mon_b.get("value", "—")}%</b></div>'
        f'<div class="krow"><span>最优资产</span><b>{_esc(money.get("asset", "—"))}</b></div>')

    erp_html = _gauge(1.5, 7.5, erp.get("erp") or 3.0, [
        (1.5, 3.0, "#cfe8dd", "卖出"), (3.0, 4.5, "#eef1f5", "中性"),
        (4.5, 6.0, "#f7ddd8", "偏低估"), (6.0, 7.5, "#e8b0a8", "买入")])
    stat_rows = "".join(
        f'<div class="krow"><span>{_esc(k)}</span><b>{_esc(v)}</b></div>'
        for k, v in ((("八年区间", f'{es["lo"]:.2f}% ~ {es["hi"]:.2f}%'),
                      ("最贵", f'{es["lo_at"]} · {es["lo"]:.2f}%'),
                      ("最便宜", f'{es["hi_at"]} · {es["hi"]:.2f}%'),
                      ("当前分位", f'高于 {es["pct"]:.0f}% 的月份'),
                      ("八年均值", f'{es["mean"]:.2f}%'))
                     if es else ())) or \
        '<div class="src">ERP 历史序列不足</div>'

    side_erp = (
        f'<h4>ERP ＝ 1/PE − 10Y 国债</h4>'
        f'<div class="src" style="font-size:11.5px">'
        f'{erp.get("earnings_yield", "—")}% − {erp.get("bond10y", "—")}% ＝ '
        f'<b style="color:var(--ink);font-size:13.5px">{erp.get("erp", "—")}%</b>'
        f'　（{_esc(erp.get("zone", "—"))}）</div>'
        f'{erp_html}<div style="height:10px"></div>{stat_rows}')

    rsi_html = _gauge(0, 100, rsi.get("rsi6") or 50, [
        (0, 20, "#e8b0a8", "超卖"), (20, 50, "#f7ddd8", "偏弱"),
        (50, 80, "#eef1f5", "偏强"), (80, 100, "#cfe8dd", "超买")])
    side_rsi = (
        f'<h4>RSI6（判定窗口）</h4>'
        f'<div class="src" style="font-size:11.5px">'
        f'RSI6 ＝ <b style="color:var(--ink);font-size:13.5px">{rsi.get("rsi6", "—")}</b>'
        f'　RSI14 ＝ {rsi.get("rsi14", "—")}（参考）　（{_esc(rsi.get("zone", "—"))}）</div>'
        f'{rsi_html}'
        f'<div class="krow" style="margin-top:10px"><span>第④层门槛</span>'
        f'<b>RSI6 ≤ 35</b></div>'
        f'<div class="krow"><span>是否满足</span>'
        f'<b style="color:{"var(--bull)" if (rsi.get("rsi6") or 100) <= 35 else "var(--sub)"}">'
        f'{"满足" if (rsi.get("rsi6") or 100) <= 35 else "不满足"}</b></div>')

    rows_html = ""
    rows_html += model_row(
        "模型① 经济周期", "美林时钟 · 定性", cycle, "stage", curve_cycle, side_cycle,
        f'蓝线 GDP 增速（季度值，画成阶梯）· 橙线 CPI 同比（月度）· '
        f'右轴 CPI 参考线：<b>1% 通缩警戒 / 2% 当前政策目标 / 3% 历史目标上限</b>'
        f'<div class="lgrow">底部色带 = 该月所处阶段，按最受益资产着色：{LEGEND}</div>')
    rows_html += model_row(
        "模型② 货币周期", "社融 × PPI · 定性", money, "stage", curve_money, side_money,
        f'蓝线 社融存量同比（宽信用先行指标）· 橙线 PPI 同比（价格滞后指标）· '
        f'右轴参考线：<b>PPI 0% 工业通缩 / 3% 成本压力</b>；'
        f'左轴 <b>社融 10% 宽信用</b>'
        f'<div class="lgrow">两条线的交叉与背离，就是信用→物价的传导时差 · {LEGEND}</div>')
    rows_html += model_row(
        "模型③ 情绪周期", "ERP 风险溢价 · 定量", erp, "zone", curve_erp, side_erp,
        f'蓝线 = 每月<b>最后一个交易日</b>的 ERP ＝ 中证官方沪深 300 滚动市盈率（TTM）'
        f'的倒数 − 当日 10 年期国债收益率'
        f'<div class="lgrow">背景分区 = 估值档位（红 = 便宜 / 该买，绿 = 贵 / 该卖）；'
        f'阈值线固定 6% / 4.5% / 3%，八年不需要随利率调整——因为利率已经减掉了</div>')
    rows_html += model_row(
        "模型④ 技术指标", "RSI 相对强弱 · 定量", rsi, "zone", curve_rsi, side_rsi,
        f'沪深 300 · RSI6（近 6 个月，日频，值域固定 0~100）'
        f'<div class="lgrow">参考线：<b>20 超卖 / 80 超买</b>；'
        f'判定窗口用 RSI6 而非 RSI14——RSI14 在近两年只触发 5 次，信号几乎不发声</div>')

    # ── 六大指标卡 ──
    refs_by_code = res.get("ref_stats") or {}
    icards = []
    for code, meta in INDICATORS.items():
        v = macro.get(code, {})
        if not v.get("ok"):
            icards.append(f'<div class="card icard"><div class="ih">'
                          f'<span class="code">{code}</span></div>'
                          f'<div class="src">无数据</div></div>')
            continue
        td = v["trend"]["dir"]
        arrow = {"up": "↑ 上行", "down": "↓ 下行", "flat": "→ 走平"}[td]
        # 走平原来落在空字符串上，显示成黑色加粗，与 ↑红 / ↓绿 不成体系
        acls = {"up": "up", "down": "down", "flat": "flat"}[td]
        if v.get("late"):
            age, atone = f'{v["age_days"]}天', "bad"
        elif v.get("awaiting"):
            age, atone = f'{v["age_days"]}天 ⏳', "wait"
        elif v.get("stale"):
            age, atone = f'{v["age_days"]}天 ⚠', "lag"
        else:
            age, atone = f'{v["age_days"]}天', "fresh"

        # 参考线命中状态：一眼看出「现在在线内还是线外」
        chips = []
        for line in refs_by_code.get(code) or []:
            hit = (v["value"] >= line["v"]) if line["above"] else (v["value"] <= line["v"])
            sign = "≥" if line["above"] else "≤"
            col = rf.ROLE_COLOR.get(line["role"], "#8494a8")
            chips.append(f'<span class="rchip{" on" if hit else ""} r-{line["role"]}" '
                         f'title="{_esc(line["basis"])}">'
                         f'<i style="background:{col}"></i>'
                         f'{sign}{line["v"]:g} {_esc(line["label"])}'
                         f'{" · 已触发" if hit else ""}</span>')

        chart = cv.single(_macro_series(v), unit=meta["unit"], since="2018-01",
                          refs=rf.flat_lines(code), step=(code == "GDP"),
                          decimals=1, ref_labels=False, end_label=False)
        icards.append(f'''
    <div class="card icard">
      <div class="ih"><span class="code">{code}</span>
        <span class="cn">{_esc(meta["meaning"])}</span>
        <span class="role">{_esc(meta["role"])}</span>
        <span class="val">{v["value"]}{_esc(meta["unit"])}</span></div>
      <div class="ien">{_esc(meta["en"])}</div>
      <div class="iuse" title="{_esc(meta["how"])}">{_esc(meta["usage"])}</div>
      <div class="imeta">{v["date"][:7]} · <b class="{acls}">{arrow}</b> ·
        <span title="Z 值＝当前值偏离 2018 年以来均值的标准差数，0 即均值">Z {v["z"] if v["z"] is not None else "—"}</span> ·
        <span title="分位＝当前值在 2018 年以来所有月份中的位置，越高越接近历史高位">分位 {f'{v["pct"]:.0f}' if v["pct"] is not None else "—"}%</span> ·
        <span class="chip {atone}" style="font-size:9.5px">{age}</span></div>
      {chart}
      <div class="rchips">{''.join(chips)}</div>
    </div>''')

    # ── 参考线核验表 ──
    # 列的设计意图：先给「依据有多硬」，再给「拆成几段、每段各自多少」，
    # 最后才是整体收益差与结论。顺序反过来，读者就会先被整体差值带跑。
    rt_rows = []
    for code, lines in refs_by_code.items():
        for i, x in enumerate(lines):
            gap = "—" if x["gap"] is None else f'{x["gap"]:+.1f}'
            gcls = "" if x["gap"] is None else ("ar-down" if x["gap"] < 0 else "ar-up")
            segs = x.get("segs") or []
            seg_html = []
            for s2 in segs:
                g2 = "—" if s2["gap"] is None else f'{s2["gap"]:+.1f}'
                c2 = "" if s2["gap"] is None else ("neg" if s2["gap"] < 0 else "pos")
                # 区间缩成「18-11→20-02」：年份前两位在同一张表里没有信息量，
                # 完整写 2018-11~2020-02 会把这一列顶到 150px 以上，挤掉结论列
                a2, b2 = s2["start"][2:7], s2["end"][2:7]
                # 只有一段时，这个数就是「整体差」，再写一遍纯属重复
                val = ('<span class="segd">单段</span>' if len(segs) == 1
                       else f'<span class="seg {c2}">{g2}</span>')
                seg_html.append(
                    f'<div class="segline">{val}'
                    f'<span class="segd">{a2}→{b2} · {s2["n"]}月</span></div>')
            mixed = (len(segs) >= 2 and not x.get("same_sign"))
            rt_rows.append(
                f'<tr data-code="{code}" data-name="{_esc(INDICATORS[code]["meaning"])}">'
                f'<td>{"<b>" + code + "</b>" if i == 0 else ""}</td>'
                f'<td data-label="参考线"><b>{"≥" if x["above"] else "≤"} {x["v"]:g}</b>'
                f'<div class="basis">{_esc(x["label"])}</div></td>'
                f'<td data-label="依据"><span class="lv lv-{_esc(x["level"])}">{_esc(x["level"])}</span>'
                f'<div class="basis">{_esc(x["basis"])}</div></td>'
                f'<td class="num" data-label="触发">{x["n_on"]}/{x["n_all"]}'
                f'<div class="basis">{len(segs)}段·最大{x["top_share"]:.0%}</div></td>'
                f'<td class="segcell" data-label="逐段">{"".join(seg_html)}'
                f'{"<div class=segnote>段间方向相反</div>" if mixed else ""}</td>'
                f'<td class="num" data-label="整体差"><span class="{gcls}">{gap}</span>'
                f'<div class="basis">{x["ret_on"]}% vs {x["ret_off"]}%</div></td>'
                f'<td class="vd {x["tone"]}" data-label="结论">{_esc(x["verdict"])}'
                f'<div class="basis">{_rich(x["caveat"])}</div></td></tr>')

    # ── 数据源头表 ──
    src_rows = []
    live = {n["code"]: n for n in res["fetch"]["macro"]}
    mklive = res["fetch"]["market"]
    audit = res.get("shrz_audit") or {}
    for code, meta in INDICATORS.items():
        st = live.get(code, {}).get("status", "—")
        badge = {"live": "#e8f5ef:#1a7f5a:实时", "cache": "#fff7e3:#c88a00:缓存",
                 "merged": "#eef1f5:#5b6b7f:合并"}.get(st, "#fdecea:#c0392b:失败")
        bg, fg, txt = badge.split(":")
        rel = _esc(meta["release"])
        if code == "SHRZ" and audit.get("periods"):
            rel += (f'<div class="basis">本库样本 {audit["periods"]} 期 · '
                    f'{_esc(audit["span"])} · 候选 {audit.get("candidates", "—")} 篇</div>')
        src_rows.append(
            f'<tr><td><b>{code}</b></td><td>{_esc(meta["authority"])}</td>'
            f'<td class="basis" style="word-break:break-all">{_esc(meta["endpoint"])}</td>'
            f'<td class="basis">{rel}</td>'
            f'<td><span class="chip" style="background:{bg};color:{fg}">{txt}</span></td></tr>')
    for key, meta in MARKET.items():
        st = mklive.get(key, {}).get("status", "—")
        badge = {"live": "#e8f5ef:#1a7f5a:实时", "cache": "#fff7e3:#c88a00:缓存"}.get(
            st, "#fdecea:#c0392b:失败")
        bg, fg, txt = badge.split(":")
        asf = (res.get("market_asof") or {}).get(key, {})
        tone2 = "fresh" if asf.get("same_day") else "wait"
        src_rows.append(
            f'<tr><td><b>{_esc(key)}</b></td><td>{_esc(meta["authority"])}</td>'
            f'<td class="basis" style="word-break:break-all">{_esc(meta["endpoint"])}</td>'
            f'<td><span class="chip {tone2}">{_esc(asf.get("state", "—"))}</span> '
            f'<span class="basis">{_esc(asf.get("note", ""))}</span></td>'
            f'<td><span class="chip" style="background:{bg};color:{fg}">{txt}</span></td></tr>')

    hs = mkt.get("hs300") or {}
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>智能择时识别模型 · {_esc(res['as_of'])}</title><style>{CSS}</style></head>
<body><div class="wrap">

<h1>智能择时识别模型</h1>
<div class="sub">六大经济指标 × 四大择时模型　·　数据截至 {_esc(res['as_of'])}
　·　{_esc(_today_short(res))}
　·　生成于 {_esc(res['generated_at'][11:19])}</div>

<div class="card verdict {c}">
  <div>
    <div class="score"><b>{d['composite']:.1f}</b><span>/ 100 综合评分</span></div>
    <div class="vtag {c}">{_esc(d['verdict'])}</div>
  </div>
  <div>
    <div class="pos">建议仓位 {d['position']:.0f}%　<i>四层共振 {d['hits']}/4</i></div>
    <div class="posbar"><i style="width:{d['position']:.0f}%"></i></div>
    <div class="readings">
      <span>沪深300 <b>{hs.get('close', '—')}</b></span>
      <span>PE <b>{mkt.get('hs300_pe', '—')}</b>（中证官方 TTM）</span>
      <span>10Y <b>{mkt.get('bond10y', '—')}%</b></span>
      <span>ERP <b>{erp.get('erp', '—')}%</b></span>
      <span>RSI6 <b>{mkt.get('rsi6', '—')}</b></span>
    </div>
    <div class="gates">{gate_pills}</div>
  </div>
</div>

<div class="sec"><h2>四大择时模型 <em>左边曲线看「怎么走过来的」，右边落点看「现在在哪」</em></h2>
{rows_html}
</div>

<div class="sec"><h2>六大经济指标 <em>2018 年至今 · 虚线为参考水平线，圆点为当前值</em></h2>
  <div class="igrid">{''.join(icards)}</div>
</div>

<div class="sec"><h2>参考水平线：依据与实测核验
  <em>「触发」= 该线被触发的月数；「逐段差值」= 把命中的月份拆成若干独立时段，每段各自差多少</em></h2>
  <div class="card rtwrap" id="rt" style="overflow:hidden">
  <table>
    <colgroup><col style="width:48px"><col style="width:110px"><col style="width:236px">
      <col style="width:92px"><col style="width:158px"><col style="width:76px">
      <col style="width:auto"></colgroup>
    <thead><tr><th>指标</th><th>参考线</th><th>依据</th><th class="num">触发</th>
      <th>逐段差值</th><th class="num">整体差</th><th>结论</th></tr></thead>
    <tbody>{''.join(rt_rows)}</tbody>
  </table></div>
  <div class="note">
    <b>怎么读这张表</b>：「整体差」= 触发该线的月份、之后 12 个月沪深 300 平均收益，
    减去未触发月份的平均收益。差值大说明这条线有区分力；接近 0 说明它只是个数字。
    「逐段差值」才是照妖镜——把命中的月份按时间切成若干独立时段，看每段各自差多少。
    它抓两种假象：<b>① 全部命中其实就是同一段行情</b>（社融 10% 的 37 个月里 95% 挤在 2022 年以后）；
    <b>② 几段方向相反</b>（CPI 2% 整体 +8.7 看着不错，拆开是 2018—2020 的 +15.5
    和 2021—2023 的 −10.1）。这两种情况整体差再大，都不能当信号用。<br>
    <b>结论</b>：九条线里只有 <b>PPI 3% 与 PPI 0%</b> 通过——两个独立时段同向，
    且把阈值从 0% 逐级抬到 5%，收益差单调放大（−14% → −24%），不是挑出来的点位。
    <b>PMI 50 是定义不是信号</b>：跌破 50 之后市场反而更好，因为跌破时通常已经跌过一轮。
    <b>CPI 3% 已过时</b>：2025、2026 年政府工作报告目标已下调至「2% 左右」，
    而 3% 以上在样本里只有 8 个月、全在 2019—2020 猪肉周期里。
    <b>CPI 2% 两段反向</b>，虽整体 +8.7 但不能作阈值。
    <b>CPI 1%、GDP 5%、M2 8%、社融 10%</b>：整体差 <4pct、只有单段，
    或几乎全挤在一个时段里，均无区分力，故只作背景标注、不参与判定。
  </div>
</div>

<div class="sec">
<details>
  <summary>数据源头、发布节奏与口径说明</summary>
  <div class="dbody">
    <div class="dscroll"><table style="table-layout:auto">
      <thead><tr><th>代码</th><th>权威源头</th><th>采集端点</th><th>发布节奏 / 本次时点</th>
        <th>状态</th></tr></thead>
      <tbody>{''.join(src_rows)}</tbody>
    </table></div>
    <div class="note" style="margin-top:14px">
      <b>口径</b>：PMI 取制造业 PMI 主指数（50 为荣枯线）；CPI/PPI 取全国同比；
      GDP 取累计同比；M2 取同比增速。<br>
      <b>社融</b>取央行官网原文的「社会融资规模存量同比」，按发布载体分两条链拼接：
      2025-09 之前来自《XXXX年X月社会融资规模存量统计数据报告》，之后来自改版后的
      《XXXX年X月金融统计数据报告》。翻栏目 38 页回溯，<b>现为 90 期（2019-01 起）</b>；
      并用存量绝对值回算同比做交叉校验（本期/去年同期 − 1），偏差超 1 个百分点的期次剔除。
      <b>2018 年的月度存量报告未在央行公开栏目中保留</b>（只剩年度存量报告），
      故序列起点为 2019-01，不做任何插补；2019-12 央行把国债与地方一般债纳入社融，
      该断点前后的存量不可直接比，回算校验在此处跳过。<br>
      <b>10Y 国债</b>取中债到期收益率（东财镜像，字段 EMM00166466，已用利差自洽校验）；
      <b>沪深 300 点位与市盈率</b>均取中证指数公司官方发布，同源于一行记录，
      不存在点位与估值时点错配。<b>RSI 以 6 日为判定窗口</b>（阈值 20/80），
      14 日仅作参考——沪深 300 近两年实测，RSI14 触及 20/80 仅 5 个交易日，
      RSI6 则为 45 个交易日。<br>
      <b>时滞</b> = 报告期末 → 今天，衡量数据本身多旧；<b>应发</b> = 按官方发布日程
      推算该期的应发布日期，用于判断「数据源该更新却没更新」。
      依据国家统计局《2026 年主要统计信息发布日程表》与央行社融栏目原文实证：
      PMI 当月最后一天 09:30（2 月因春节延至 3 月 4 日）、CPI/PPI 次月 9 日 09:30
      （节假日顺延）、社融与 M2 次月 12～15 日 17:00、GDP 季后 15～20 日 10:00。
      统计局数据发布库会在发布后 3 个工作日左右才更新，故本项目抓东财镜像以抢时效。<br>
      <b>T / T-1</b> 按交易所休市日历判断（周末 + 法定休市日，依据上证公告〔2025〕45 号），
      已能区分「今日休市」与「交易日但数据未更新」；定时任务<b>每天</b> 19:30 运行，
      避免周末/月末落休市日时漏抓。
    </div>
  </div>
</details>
</div>

<div class="note" style="margin-top:18px">
  <b>免责</b>：本模型是对《六大经济指标与四大择时模型》框架的量化实现，
  输出为框架结论，不构成投资建议。宏观数据存在发布时滞与修订，
  请结合时效标记与参考线核验结论判断信号可信度。
</div>

</div></body></html>"""
