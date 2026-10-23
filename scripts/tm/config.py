# -*- coding: utf-8 -*-
"""智能择时模型 · 全局配置与指标元数据

框架出处：《六大经济指标与四大择时模型》
  择时模型 ① 经济周期（定性）② 货币周期（定性）
  择时模型 ③ 情绪周期（定量）④ 技术指标 RSI（定量）
"""
import os
from pathlib import Path

# 默认把 data/ 与 output/ 放在 scripts/ 下（技能自带一份缓存，开箱即用）。
# TIMING_HOME 可以把它们指到技能目录之外——装在只读路径、或想让多个项目
# 共用同一份缓存时用：TIMING_HOME=D:/timing-data
ROOT = Path(os.environ.get("TIMING_HOME") or
            Path(__file__).resolve().parent.parent).expanduser()
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"
DB_PATH = DATA_DIR / "timing.db"

# ── 网络 ────────────────────────────────────────────────────────────
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
TIMEOUT = 25
RETRY = 3

# ── 六大经济指标元数据 ──────────────────────────────────────────────
# role: leading 领先 / coincident 同步 / lagging 滞后
INDICATORS = {
    "PMI": {
        "name": "PMI 采购经理指数",
        "role": "领先指标",
        "meaning": "采购经理指数",
        "en": "Purchasing Managers' Index",
        "usage": "反映企业扩张意愿，敢不敢加大投资",
        "how": "直接看数值，50 为荣枯线：>50 扩张、<50 收缩",
        "freq": "每月一次",
        "release": "当月最后一天 09:30",
        "authority": "国家统计局",
        "endpoint": "datacenter-web.eastmoney.com · RPT_ECONOMY_PMI",
        "url": "https://data.stats.gov.cn/easyquery.htm?cn=A01",
        "unit": "",
        "signed": False,
    },
    "CPI": {
        "name": "CPI 居民消费价格指数",
        "role": "滞后指标",
        "meaning": "居民消费价格指数",
        "en": "Consumer Price Index",
        "usage": "反映居民生活成本，买菜贵不贵",
        "how": "同比 1%~3% 为正常；<1% 通缩、>3% 通胀压力",
        "freq": "每月一次",
        "release": "次月 9 日 09:30（节假日顺延）",
        "authority": "国家统计局",
        "endpoint": "datacenter-web.eastmoney.com · RPT_ECONOMY_CPI",
        "url": "https://data.stats.gov.cn/easyquery.htm?cn=A01",
        "unit": "%",
        "signed": True,
    },
    "PPI": {
        "name": "PPI 生产价格指数",
        "role": "领先指标",
        "meaning": "生产价格指数",
        "en": "Producer Price Index",
        "usage": "反映企业生产成本，原材料贵不贵",
        "how": "同比 >3% 说明成本高、利润受损；PPI 触底回升常是企业盈利拐点",
        "freq": "每月一次",
        "release": "次月 9 日 09:30（节假日顺延）",
        "authority": "国家统计局",
        "endpoint": "datacenter-web.eastmoney.com · RPT_ECONOMY_PPI",
        "url": "https://data.stats.gov.cn/easyquery.htm?cn=A01",
        "unit": "%",
        "signed": True,
    },
    "SHRZ": {
        "name": "社融 社会融资规模",
        "role": "领先指标",
        "meaning": "社会融资规模",
        "en": "Total Social Financing",
        "usage": "反映企业和个人对融资的需求，敢不敢借钱",
        "how": "社融增速变高，表示企业或个人借钱意愿强，预示未来经济向好",
        "freq": "每月一次",
        "release": "次月 12～15 日 17:00",
        "authority": "中国人民银行",
        "endpoint": "pbc.gov.cn · 《金融统计数据报告》原文（存量同比）",
        "url": "http://www.pbc.gov.cn/diaochatongjisi/116219/116225/index.html",
        "unit": "%",
        "signed": True,
    },
    "M2": {
        "name": "M2 货币供应量",
        "role": "领先指标",
        "meaning": "货币供应量",
        "en": "Broad Money Supply",
        "usage": "反映国家货币发行总量多少",
        "how": "发行总量越大，代表货币贬值速度越快；M2 与 M1 剪刀差看资金活化",
        "freq": "每月一次",
        "release": "次月 12～15 日 17:00",
        "authority": "中国人民银行",
        "endpoint": "datacenter-web.eastmoney.com · RPT_ECONOMY_CURRENCY_SUPPLY",
        "url": "http://www.pbc.gov.cn/diaochatongjisi/",
        "unit": "%",
        "signed": True,
    },
    "GDP": {
        "name": "GDP 国内生产总值",
        "role": "同步指标",
        "meaning": "国内生产总值",
        "en": "Gross Domestic Product",
        "usage": "反映国家经济发展增速，经济行不行",
        "how": "同比增速上行则经济看好，反之经济不好",
        "freq": "每季度一次",
        "release": "季后 15～20 日 10:00",
        "authority": "国家统计局",
        "endpoint": "datacenter-web.eastmoney.com · RPT_ECONOMY_GDP",
        "url": "https://data.stats.gov.cn/easyquery.htm?cn=B01",
        "unit": "%",
        "signed": True,
    },
}

# ── 市场数据元数据 ──────────────────────────────────────────────────
MARKET = {
    "BOND10Y": {
        "name": "10 年期国债收益率",
        "authority": "中央结算公司（中债）· 东财镜像",
        "endpoint": "RPTA_WEB_TREASURYYIELD · EMM00166466",
        "unit": "%",
    },
    "HS300": {
        "name": "沪深 300 指数",
        "authority": "中证指数公司（官方发布）",
        "endpoint": "csindex.com.cn · index-perf（000300）",
        "unit": "点",
    },
    "HS300_PE": {
        "name": "沪深 300 市盈率（官方 TTM）",
        "authority": "中证指数公司（指数编制方）",
        "endpoint": "csindex.com.cn · index-perf 字段 peg（实为 PE）",
        "unit": "倍",
    },
}

# ── 模型参数 ────────────────────────────────────────────────────────
ERP_BUY = 6.0      # 风险溢价 ≥6% → 买入区（笔记原阈值）
ERP_SELL = 3.0     # 风险溢价 ≤3% → 卖出区
RSI_OVERBOUGHT = 80
RSI_OVERSOLD = 20

# 主判定窗口取 RSI6（短期动量），RSI14 降为参考。
# 依据：沪深300 近 2 年 486 个交易日实测，RSI14 配 20/80 只触发 5 次
#（≤20 仅 1 天 0.2%、≥80 仅 4 天 0.8%），信号几乎不发声；
# RSI6 配同样阈值触发 45 次（3.6% / 5.5%），频率回到可用区间。
RSI_WINDOW = 6        # 主判定窗口
RSI_REF_WINDOW = 14   # 参考窗口（仅展示，不参与评分）
# 超买/超卖两侧的「临界带」宽度。RSI6 标准差约为 RSI14 的 1.5 倍，
# 故由 5 放宽到 8，保持「临界」的触发概率与原先等价。
RSI_MARGIN = 8
# 四层确认中第④层的门槛：RSI6 ≤35（实测约 15% 分位，即约每 7 个交易日出现 1 天）
RSI_GATE = 35

# 四模型权重（货币周期对 A 股最敏感，给最高权重）
WEIGHTS = {"cycle": 0.25, "money": 0.30, "erp": 0.25, "rsi": 0.20}

# ── 官方发布日程（用于推算「应发布日」，判断数据源是否该更新却没更新）────
# 依据：国家统计局《2026年主要统计信息发布日程表》、央行《金融统计数据报告》
#       栏目页 14 期原文实证发布日期（2025-08 ~ 2026-Q3）。
#
# freq : M 月度 / Q 季度（决定报告期如何递进）
# day  : "EOM" = 报告期当月最后一天（PMI 当月发布当月值）；
#        整数 = 报告期次月的第 N 日
# time : 官方发布时点（北京时间）
RELEASE_RULE = {
    "PMI": {
        "freq": "M", "day": "EOM", "time": "09:30", "tolerance": 3,
        "basis": "统计局日程表：当月最后一天发当月值。2月因春节延至 3 月 4 日。",
    },
    "CPI": {
        "freq": "M", "day": 9, "time": "09:30", "tolerance": 3,
        "basis": "统计局日程表：次月 9 日。遇节假日顺延，10 月因国庆移至 14 日。",
    },
    "PPI": {
        "freq": "M", "day": 9, "time": "09:30", "tolerance": 3,
        "basis": "与 CPI 同日同时发布（同一场发布会）。",
    },
    "SHRZ": {
        "freq": "M", "day": 12, "time": "17:00", "tolerance": 4,
        "basis": "央行栏目 14 期实证：发布日落在次月 12/13/14/15 日，众数 14 日，期后 40~45 天。",
    },
    "M2": {
        "freq": "M", "day": 12, "time": "17:00", "tolerance": 4,
        "basis": "与社融同处一份《金融统计数据报告》，同时发布。",
    },
    "GDP": {
        "freq": "Q", "day": 15, "time": "10:00", "tolerance": 6,
        "basis": "统计局日程表：季后 15~20 日 10:00。2026 年 Q1=4/16、Q2=7/15、Q3=10/19。",
    },
}

# 数据时效兜底阈值（天）：以**报告期末**为基准，防止发布规则误判时彻底失守。
# 正常值 = 期末到下次发布前的最大跨度 + 缓冲。
STALE_DAYS = {"PMI": 45, "CPI": 45, "PPI": 45, "SHRZ": 50, "M2": 50, "GDP": 115}
