# -*- coding: utf-8 -*-
"""数据采集层：每个采集器只负责把「一个指标」的时间序列拿回来。

约定：所有返回都是 [(date_str, value), ...]，按时间升序，date_str 形如 2026-09-01。
任何采集器失败都抛 SourceError，由上层降级（用缓存），绝不静默返回空。
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .config import UA, TIMEOUT, RETRY


class SourceError(RuntimeError):
    pass


_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

EM_DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def _http(url: str, headers: dict | None = None, data: bytes | None = None,
          method: str | None = None, timeout: int = TIMEOUT) -> bytes:
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    last = None
    for attempt in range(RETRY):
        try:
            req = urllib.request.Request(url, headers=h, data=data, method=method)
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.8 * (attempt + 1))
    raise SourceError(f"{url[:90]} → {type(last).__name__}: {last}")


def _em_report(report: str, sort_col: str | None = "REPORT_DATE", page_size: int = 200,
               flt: str | None = None, page: int = 1) -> list[dict]:
    """东方财富数据中心通用取数。sort_col=None 时不排序（部分报表无时间列）。"""
    q = {
        "reportName": report,
        "columns": "ALL",
        "pageNumber": str(page),
        "pageSize": str(page_size),
    }
    if sort_col:
        q["sortColumns"] = sort_col
        q["sortTypes"] = "-1"
    if flt:
        q["filter"] = flt
    url = f"{EM_DC}?{urllib.parse.urlencode(q)}"
    raw = _http(url, {"Referer": "https://data.eastmoney.com/"})
    try:
        j = json.loads(raw.decode("utf-8", "ignore"))
    except json.JSONDecodeError as e:
        raise SourceError(f"{report} 返回非 JSON") from e
    if not j.get("success") or not j.get("result"):
        raise SourceError(f"{report} 报表异常：{j.get('message')}")
    return j["result"]["data"]


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    if s in ("", "-", "--", "None", "null"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _norm_date(s: str) -> str:
    s = str(s)
    if len(s) >= 10 and s[4] == "-":
        return s[:10]
    if len(s) == 6 and s.isdigit():          # 202604
        return f"{s[:4]}-{s[4:6]}-01"
    if len(s) == 8 and s.isdigit():          # 20260430
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


def month_end(series: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """日频 → 月频：取每月**最后一个交易日**的值。

    序列须已按日期升序；逐条覆盖同一 YYYY-MM 键，最终留下的就是该月最后一条
    日频记录，日期原样保留（不改成月末日、不插值），可追溯到具体交易日。
    """
    last: dict[str, tuple[str, float]] = {}
    for d, v in series:
        if d and v is not None:
            last[d[:7]] = (d, v)
    return [last[k] for k in sorted(last)]


# ── 六个宏观指标 ────────────────────────────────────────────────────

def fetch_pmi() -> list[tuple[str, float]]:
    rows = _em_report("RPT_ECONOMY_PMI")
    out = [( _norm_date(r["REPORT_DATE"]), _num(r.get("MAKE_INDEX"))) for r in rows]
    return sorted([(d, v) for d, v in out if v is not None])


def fetch_cpi() -> list[tuple[str, float]]:
    rows = _em_report("RPT_ECONOMY_CPI")
    out = [(_norm_date(r["REPORT_DATE"]), _num(r.get("NATIONAL_SAME"))) for r in rows]
    return sorted([(d, v) for d, v in out if v is not None])


def fetch_ppi() -> list[tuple[str, float]]:
    rows = _em_report("RPT_ECONOMY_PPI")
    out = [(_norm_date(r["REPORT_DATE"]), _num(r.get("BASE_SAME"))) for r in rows]
    return sorted([(d, v) for d, v in out if v is not None])


def fetch_gdp() -> list[tuple[str, float]]:
    """SUM_SAME = 累计同比（如「第1-3季度」4.6 表示前三季度累计增速）"""
    rows = _em_report("RPT_ECONOMY_GDP")
    out = [(_norm_date(r["REPORT_DATE"]), _num(r.get("SUM_SAME"))) for r in rows]
    return sorted([(d, v) for d, v in out if v is not None])


def fetch_m2() -> list[tuple[str, float]]:
    """东财字段：BASIC_CURRENCY=M2 余额，CURRENCY=M1，FREE_CASH=M0"""
    rows = _em_report("RPT_ECONOMY_CURRENCY_SUPPLY")
    out = [(_norm_date(r["REPORT_DATE"]), _num(r.get("BASIC_CURRENCY_SAME"))) for r in rows]
    return sorted([(d, v) for d, v in out if v is not None])


def fetch_m1() -> list[tuple[str, float]]:
    rows = _em_report("RPT_ECONOMY_CURRENCY_SUPPLY")
    out = [(_norm_date(r["REPORT_DATE"]), _num(r.get("CURRENCY_SAME"))) for r in rows]
    return sorted([(d, v) for d, v in out if v is not None])


PBC_BASE = "http://www.pbc.gov.cn"
PBC_COLUMN = PBC_BASE + "/diaochatongjisi/116219/116225"
PBC_LIST = PBC_COLUMN + "/index.html"

# 栏目列表分页：模块号 11871，第 N 页 = /11871-N.html（第 1 页是 index.html）
PBC_MODULE = "11871"
SHRZ_MAX_PAGE = 38          # 38 页 = 栏目全部，覆盖 2009 年至今
SHRZ_MIN_PERIOD = "2019-01"  # 序列起点。2018 年月度存量报告在央行公开栏目中缺失，不补
SHRZ_MIN_SERIES = 60         # 少于该期数视为采集失败，交由上层降级缓存

# 2019-12 起央行把「国债」「地方政府一般债券」纳入社融统计，存量口径改变
# （2019-11 为 221.28 万亿，2019-12 跳到 251.31 万亿）。
# 这意味着 2020 年各期用 2019 年同期存量回算同比会算出高出十几个点的假偏差，
# 与本模块「回算校验」的用意相反（它是用来抓解析错误的，不该抓央行自己改口径）。
# 故这段直接跳过校验，而不是放宽容差——放宽容差会让真正的脏数据漏网。
SHRZ_CALIBER_SKIP = ("2020-01-01", "2020-12-01")

# 正文联立句式：社会融资规模存量为468.17万亿元，同比增长7.1%
# 用「同一句内联立」而不是两条独立正则，避免把 M2 的同比错配到社融的存量上
_V_SHRZ = re.compile(
    r"社会融资规模存量为\s*([\d.]+)\s*万亿元[^。]{0,40}?同比增长\s*(-?[\d.]+)\s*%")

# 社融口径在 2025-09 前后换了发布载体：
#   之前 → 《XXXX年X月社会融资规模存量统计数据报告》（专项报告）
#   之后 → 并入《XXXX年X月金融统计数据报告》（新模板，首段即含存量同比）
_T_STOCK = re.compile(r"^(\d{4})年(?:(\d{1,2})月)?社会融资规模存量统计数据报告$")
_T_FIN = re.compile(r"^(\d{4})年(?:(\d{1,2})月|(一季度|上半年|前三季度))?金融统计数据报告$")
_QUARTER_MONTH = {"一季度": 3, "上半年": 6, "前三季度": 9}


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def _strip_html(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = txt.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", txt)


def _shrz_key_of(title: str) -> tuple[str, str] | None:
    """报告标题 → (报告期, 来源类型)。来源类型 stock=存量专项报告，fin=金融统计数据报告。"""
    m = _T_STOCK.match(title)
    if m:
        mo = int(m.group(2)) if m.group(2) else 12
        return f"{m.group(1)}-{mo:02d}-01", "stock"
    m = _T_FIN.match(title)
    if m:
        if m.group(2):
            mo = int(m.group(2))
        else:
            mo = _QUARTER_MONTH.get(m.group(3) or "", 12)
        return f"{m.group(1)}-{mo:02d}-01", "fin"
    return None


def _pbc_get(url: str, timeout: int = 25) -> bytes | None:
    """央行站点单次取数，失败返回 None（不重试，由调用方决定是否放弃）"""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Referer": PBC_COLUMN + "/index.html"})
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            return r.read()
    except Exception:  # noqa: BLE001
        return None


def _shrz_scan_index() -> dict[str, tuple[str, str]]:
    """翻栏目分页，收集所有社融相关报告的 (期次 → (URL, 来源类型))。

    同一期次若同时存在存量专项报告与新模板金融统计报告，优先存量专项报告
    （它的正文主体就是社融，句式最稳定）。
    """
    pages = [PBC_LIST if p == 1 else f"{PBC_COLUMN}/{PBC_MODULE}-{p}.html"
             for p in range(1, SHRZ_MAX_PAGE + 1)]
    found: dict[str, tuple[str, str]] = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        for raw in ex.map(_pbc_get, pages):
            if not raw:
                continue
            for href, title in re.findall(
                    r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', _decode(raw)):
                hit = _shrz_key_of(title.strip())
                if not hit:
                    continue
                key, kind = hit
                if key < SHRZ_MIN_PERIOD:
                    continue
                url = href if href.startswith("http") else PBC_BASE + href
                prev = found.get(key)
                if prev is None or (prev[1] == "fin" and kind == "stock"):
                    found[key] = (url, kind)
    return found


def _shrz_parse_one(item: tuple[str, tuple[str, str]]) -> tuple[str, float, float] | None:
    """抓单篇报告，返回 (期次, 存量同比, 存量万亿)。"""
    key, (url, _kind) = item
    raw = _pbc_get(url)
    if not raw:
        return None
    m = _V_SHRZ.search(_strip_html(_decode(raw)))
    if not m:
        return None
    return key, float(m.group(2)), float(m.group(1))


def fetch_shrz() -> list[tuple[str, float]]:
    """社融存量同比 —— 中国人民银行官网原文（权威一手源）

    口径：全国社会融资规模存量同比（%），与笔记「社融增速变高 = 借钱意愿强」一致。

    采集路径（2026-10 重建，样本由 12 期扩至 80+ 期）：
      ① 翻「调查统计司 / 数据解读」栏目分页（模块 11871，共 38 页），
         按标题识别两类报告：
           - 《XXXX年X月社会融资规模存量统计数据报告》（2025-09 之前的主力载体）
           - 《XXXX年X月金融统计数据报告》（2025-09 起央行改版，社融并入首段）
      ② 并发抓正文，用联立正则取「社会融资规模存量为 X 万亿元，同比增长 Y%」，
         保证存量与同比来自同一句，避免把 M2 的同比错配过来。
      ③ 用存量绝对值回算同比（本期 / 去年同期 − 1）交叉校验，偏差 >1.0 个百分点的
         期次剔除——这条规则自动滤掉了 2018~2019 旧模板的脏解析（实测偏差 5~14 个百分点）。
         阈值取 1.0 而非 0.3：央行每年会对社融存量做基数修订，2023 年多期公布的同比
         比回算值低 0.3 个百分点，属正常修订，不应误删。

    为什么不沿用「社融增量滚动合计」：增量 TTM ≠ 存量同比，且商务数据中心口径滞后
    200 天以上，实测算出 −3.21% 而官方为 7.8%，相差 11 个百分点，已废弃。
    """
    index = _shrz_scan_index()
    if not index:
        raise SourceError("央行社融栏目未解析到任何报告链接")

    with ThreadPoolExecutor(max_workers=5) as ex:
        rows = [r for r in ex.map(_shrz_parse_one, index.items()) if r]

    yoy = {k: y for k, y, _ in rows}
    stock = {k: s for k, _, s in rows}

    def _prior_year(k: str) -> str:
        return f"{int(k[:4]) - 1}{k[4:]}"

    series, dropped = {}, []
    for k, y in yoy.items():
        py = _prior_year(k)
        # 口径断点：2020 年各期的上年同期还是旧口径存量，回算必然失真，跳过不判
        if not (SHRZ_CALIBER_SKIP[0] <= k < SHRZ_CALIBER_SKIP[1]):
            if py in stock and stock[k] > 0:
                calc = (stock[k] / stock[py] - 1) * 100
                if abs(y - calc) > 1.0:
                    dropped.append(f"{k[:7]}(公布{y}% vs 回算{calc:.1f}%)")
                    continue
        series[k] = y

    if len(series) < SHRZ_MIN_SERIES:
        raise SourceError(
            f"央行社融有效期数不足（{len(series)}/{len(index)}，已剔除 {len(dropped)} 条口径异常）")

    out = sorted(series.items())
    fetch_shrz.last_audit = {           # 供仪表盘展示采集质量
        "periods": len(out),
        "candidates": len(index),
        "parsed": len(rows),
        "dropped": dropped,
        "span": f"{out[0][0]} ~ {out[-1][0]}",
    }
    return out


fetch_shrz.last_audit = {}


# ── 市场数据 ────────────────────────────────────────────────────────

BOND_MIN_DATE = "2018-01-01"   # 模型③曲线回溯起点
CSIC_MIN_DATE = "20180101"


def fetch_bond10y() -> list[tuple[str, float]]:
    """中债 10 年期国债到期收益率（东财镜像，EMM00166466 已经利差自洽校验）

    东财单页上限 500 条（约 2 年），模型③要回算 2018 年以来的月度 ERP，
    故按页翻到 2018 年为止（实测 5 页即覆盖 2017-06 起）。
    """
    rows: list[dict] = []
    for page in range(1, 8):
        batch = _em_report("RPTA_WEB_TREASURYYIELD", sort_col="SOLAR_DATE",
                           page_size=500, page=page)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 500:
            break
        oldest = min((str(r.get("SOLAR_DATE") or ""))[:10] for r in batch)
        if oldest and oldest <= BOND_MIN_DATE:
            break
    out = [(_norm_date(r["SOLAR_DATE"]), _num(r.get("EMM00166466"))) for r in rows]
    return sorted([(d, v) for d, v in out if v is not None])


def fetch_hs300(limit: int = 500) -> list[dict]:
    """沪深 300 日线：主用东财 push2his，失败回落到新浪。返回 [{date, close}] 升序"""
    try:
        url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.000300"
               "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
               f"&klt=101&fqt=1&end=20500101&lmt={limit}")
        raw = _http(url, {"Referer": "https://quote.eastmoney.com/"})
        j = json.loads(raw.decode("utf-8", "ignore"))
        klines = (j.get("data") or {}).get("klines") or []
        if klines:
            out = []
            for line in klines:
                p = line.split(",")
                out.append({"date": p[0], "close": _num(p[2])})
            return sorted(out, key=lambda x: x["date"])
    except Exception:  # noqa: BLE001
        pass
    return _fetch_hs300_sina(limit)


def _fetch_hs300_sina(limit: int) -> list[dict]:
    """新浪日线兜底：https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/..."""
    url = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           "CN_MarketData.getKLineData?symbol=sh000300&scale=240&ma=no&datalen=" + str(min(limit, 1023)))
    raw = _http(url, {"Referer": "https://finance.sina.com.cn/"})
    rows = json.loads(raw.decode("utf-8", "ignore"))
    if not rows:
        raise SourceError("沪深300 K线为空（新浪兜底也失败）")
    out = [{"date": r["day"][:10], "close": _num(r["close"])} for r in rows]
    return sorted([x for x in out if x["close"]], key=lambda x: x["date"])


CSIC_PERF = "https://www.csindex.com.cn/csindex-home/perf/index-perf"


def fetch_csic_hs300(start: str = CSIC_MIN_DATE) -> dict:
    """中证指数公司官方行情 + 估值（沪深300 的编制方，一手数据）

    一次请求同时给出收盘点位与市盈率，取 2018 年以来全部日线（实测 2134 条），
    既够 RSI(6) 计算，也够模型③回溯 8 年多的月度估值曲线。

    字段口径（已实测验证）：
      `peg` 实为「市盈率（TTM / 滚动）」，并非 PEG —— 中证字段命名如此。
      证据：用 close/peg 反推指数每股收益，该值在每年 5 月初、9 月初、11 月初
      三次阶梯跳变，对应年报+一季报（4 月底）、中报（8 月底）、三季报（10 月底）
      的披露节奏；静态 PE 一年只会跳一次。
      最新值 12.77 与东财 PE(TTM) 12.86 相差 0.7%，属计算时点差异。

    已知接口行为：当 `startDate` 落在休市日时，接口会把下一个交易日的数据
      回填成该日（实测 20180101 与 20180102 的 close/vol/peg 完全相同）。
      这里显式剔除首条重复，避免「月初跑」时把休市日当成交易日。
    """
    end = time.strftime("%Y%m%d")
    url = f"{CSIC_PERF}?indexCode=000300&startDate={start}&endDate={end}"
    raw = _http(url, {"Referer": "https://www.csindex.com.cn/",
                      "Accept": "application/json, text/plain, */*"}, timeout=40)
    try:
        j = json.loads(raw.decode("utf-8", "ignore"))
    except json.JSONDecodeError as e:
        raise SourceError("中证 index-perf 返回非 JSON") from e
    rows = j.get("data") or []
    if len(rows) < 400:
        raise SourceError(f"中证沪深300日线不足（{len(rows)}）")

    rows = sorted(rows, key=lambda r: str(r.get("tradeDate") or ""))
    # 剔除 startDate 回填条：与下一条 close/vol/peg 完全一致即为休市日填充
    if len(rows) >= 2:
        a, b = rows[0], rows[1]
        if (a.get("close") == b.get("close") and a.get("tradingVol") == b.get("tradingVol")
                and a.get("peg") == b.get("peg")):
            rows = rows[1:]

    closes, pes = [], []
    for r in rows:
        d = str(r.get("tradeDate") or "")
        if len(d) != 8 or not d.isdigit():
            continue
        date = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        c = _num(r.get("close"))
        if c and c > 0:
            closes.append({"date": date, "close": c})
        pe = _num(r.get("peg"))
        if pe and pe > 0:
            pes.append((date, pe))
    if len(closes) < 400 or not pes:
        raise SourceError("中证行情/估值解析失败")
    closes.sort(key=lambda x: x["date"])
    pes.sort(key=lambda x: x[0])
    return {"series": closes, "pe_history": pes,
            "pe_monthly": month_end(pes),
            "pe": pes[-1][1], "pe_date": pes[-1][0]}


def fetch_hs300_pe() -> float:
    """沪深 300 市盈率 —— 优先中证官方，失败再用成分股自算兜底

    官方口径（中证）12.77 与东财 PE(TTM) 12.86 相差 0.7%，属计算时点差异；
    早期自算版本为 13.13，偏高约 2.8%，根因是新浪 `per` 字段口径
    （静态 PE）与 TTM 不一致，故仅作兜底保留。
    """
    try:
        return round(fetch_csic_hs300()["pe"], 4)
    except Exception:  # noqa: BLE001
        return fetch_hs300_pe_sina()


def fetch_hs300_pe_sina() -> float:
    """兜底：整体法自算。PE = Σ总市值 / Σ净利润，净利润_i = 市值_i / PE_i。

    数据源：新浪 node=hs300（每只股票带 per 与 mktcap，3 次请求拿全 300 只）。
    已知口径偏差：新浪 per 更接近静态 PE，结果通常高于官方 TTM 约 2~3%。
    """
    url = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           "Market_Center.getHQNodeData?page={page}&num=100&sort=symbol&asc=1"
           "&node=hs300&symbol=&_s_r_a=page")
    cap_sum, profit_sum, ok, seen = 0.0, 0.0, 0, 0
    for page in range(1, 5):
        raw = _http(url.format(page=page), {"Referer": "https://finance.sina.com.cn/"},
                    timeout=30)
        rows = json.loads(raw.decode("gbk", "ignore"))
        if not rows:
            break
        for r in rows:
            seen += 1
            cap = _num(r.get("mktcap"))          # 单位：万元
            pe = _num(r.get("per"))
            if not cap or cap <= 0:
                continue
            cap_sum += cap
            if pe and pe > 0:
                profit_sum += cap / pe
                ok += 1
        if len(rows) < 100:
            break
        time.sleep(0.25)

    if seen < 250:
        raise SourceError(f"沪深300成分获取不足（{seen}）")
    if cap_sum <= 0 or profit_sum <= 0 or ok < 180:
        raise SourceError(f"有效 PE 样本不足（{ok}/{seen}）")
    return round(cap_sum / profit_sum, 4)
