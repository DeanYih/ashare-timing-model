---
name: ashare-timing-model
slug: ashare-timing-model
displayName: A股择时模型
version: 1.0.0
summary: 六大经济指标 × 四大择时模型 × 四层逐级确认，每天自动抓数、算出综合评分与建议仓位，并输出单文件 HTML 仪表盘
tags: [a-share, timing, macro, valuation, erp, rsi, merrill-clock, dashboard, finance]
license: MIT
description: 'Run a complete A-share market-timing pipeline from six macro indicators (PMI / CPI / PPI / GDP / M2 / social financing) and four timing models (Merrill-clock economic cycle, monetary cycle, ERP equity risk premium, RSI6), then emit a composite score, a suggested position size and a self-contained HTML dashboard. Use this skill whenever the user asks 现在能不能加仓 / 该买什么 / 仓位建议 / 择时信号 / 市场贵不贵 / 经济周期在哪 / 沪深300估值 / ERP 或风险溢价 / RSI 超买超卖 / 更新择时仪表盘, or asks to explain what a timing score means. Also use it to re-verify whether a macro threshold (PMI 50, CPI 3%, PPI 3%) actually has statistical power. 触发场景：A股择时、仓位建议、加仓判断、经济周期定位、市场估值、宏观数据时效核查、阈值有效性验证。'
agent_created: true
---

# A 股择时模型

把「六大经济指标 + 四大择时模型 + 四层逐级确认」这套框架做成可执行的量化实现。
一条命令走完 **采集 → 加工 → 建模 → 决策 → 出仪表盘**，全程约 10 秒。

## 何时使用

- 用户问「现在能不能加仓 / 该买什么 / 仓位多少」——先跑模型，再回答，不要凭印象
- 用户问「市场贵不贵 / 经济周期在哪 / 风险溢价多少 / 是不是超卖」
- 用户要更新或查看择时仪表盘、要一份可以转发到手机的市场快照
- 用户质疑某条宏观阈值（如「PMI 50 到底有没有用」）——用 `verify_refs.py` 给逐段实测证据
- 用户问「这个评分怎么理解」——读 `references/reporting.md`，按里面的口径解释，不要自行发挥

**不适用**：个股或行业筛选、短线交易信号、任何需要回测证明的策略。本模型只判**宽基指数**的位置，不具备选股能力。

## 快速开始

```bash
python <SKILL_DIR>/scripts/run_timing.py            # 完整流水线 + 中文快照
python <SKILL_DIR>/scripts/run_timing.py --json     # 末尾追加机器可读摘要
python <SKILL_DIR>/scripts/run_timing.py --quiet --json   # 只要摘要
```

- 纯标准库（Python ≥ 3.10），无第三方依赖，无 API Key
- 任意工作目录可运行，脚本自己处理 `sys.path`；**不要**依赖 `cd scripts`
- **首次运行会联网抓全量历史**（六指标 + 沪深300 行情与 PE + 10Y 国债，约 10~30 秒），
  之后走 `scripts/data/timing.db` 缓存增量更新；抓取失败的指标会回落到缓存并在
  `fetch.macro[].status` 标成 `cached`，汇报时要说明数据可能不是最新
- 产物：`<SKILL_DIR>/scripts/output/dashboard.html`（单文件，无外链，可直接转发）与 `latest.json`
- 用 `TIMING_HOME=<dir>` 把 `data/`、`output/` 挪出技能目录（多项目共用缓存时用）

交付时用 `present_files` 打开 `output/dashboard.html`，并附一段文字结论——不要把 HTML 当成回答本身。

辅助脚本：

```bash
python <SKILL_DIR>/scripts/verify_refs.py        # 九条参考线的逐段区分力实测
python <SKILL_DIR>/scripts/verify_pe_monthly.py  # 模型③ 的 PE 口径自检（月末 + TTM）
```

## 输出怎么读

跑完会打印一份快照，结构是：四个模型得分 → 综合评分与仓位 → 四层共振 → 关键读数 → 数据时效。

**综合评分不是上涨概率。** 它是「当前位置在框架里的分数」，由四项加权：

| 模型 | 权重 | 输入 | 判什么 |
|---|---|---|---|
| ② 货币周期 | 30% | 社融 × PPI | 信用扩张还是收缩 |
| ① 经济周期 | 25% | GDP × CPI | 美林时钟四象限 |
| ③ 情绪周期 | 25% | ERP = 1/PE − 10Y | 股票相对债券的赔率 |
| ④ RSI6 | 20% | 近 6 个月日频 | 短期超买超卖 |

**仓位 = 连续评分 × 0.7 + 共振层数/4 × 100 × 0.3**，共振层数来自四个布尔门（经济周期底部 / 货币周期底部 / 情绪周期高位 / RSI 超卖）。
3 层 = 「接近买点，可分批建仓」，4 层才是全仓级别的信号。

**目标仓位 ≠ 现在就该买入。** 左侧信号里「便宜 + 超卖」可以同时成立，而基本面仍在恶化。
汇报时必须把这一点讲清楚，具体话术与拆解方法见 `references/reporting.md`。

## 汇报纪律

1. **先报数据时效**。快照末尾会标每个指标是 `✅ 正常 / ⏳ 待发 / ❌ 滞后 / ⚠ 陈旧`，以及市场数据是 `T` 还是 `T-1`。
   有 `❌` 或 `⚠` 时，先说可信度受影响，再讲结论。
2. **拆开讲，不要只念总分**。基本面两项（①②）与估值情绪两项（③④）贡献差得远时，必须点出来——
   60 分可能全部由「便宜 + 超卖」撑起来，那是左侧，不是转强。
3. **区分资产类别排序与股票择时**。模型① 给的是「债券 > 现金 > 股票 > 商品」这类排序，
   模型③④ 说的是股票自己的赔率。两者可以背离，不要混成一句话。
4. **不做投资建议**。给框架结论、触发条件、风险点，最后一句留给用户自己判断。
5. 数值一律引用程序输出，不要四舍五入到失真，也不要凭记忆补数。

## 目录结构

```
scripts/
├── run_timing.py       单一入口（路径无关，推荐只用这个）
├── verify_refs.py      参考线核验 CLI
├── verify_pe_monthly.py PE 口径自检
├── tm/
│   ├── config.py       指标元数据、模型参数、权重、发布日程
│   ├── sources.py      9 个采集器（含降级与缓存）
│   ├── indicators.py   方向 / Z 值 / 分位 / RSI
│   ├── models.py       四大模型 + 综合决策
│   ├── refs.py         参考线定义与逐段区分力检验
│   ├── calendar.py     A 股休市日历
│   ├── curves.py       纯 SVG 曲线（双线 / 单指标 / ERP）
│   ├── render.py       HTML 仪表盘（内联 SVG，无外部依赖）
│   └── run.py          主流程
references/             方法论、数据源口径、汇报模板、实现踩坑
README.md               项目全景：框架、数据源、页面设计决策、已知限制
```

## 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| 某指标显示「降级」 | 采集失败，回落到 sqlite 缓存 | 看 `fetch.macro` 里的 status，如实汇报数据可能不是最新 |
| 社融样本 < 90 期 | 央行栏目分页改版 | 提示采集退化，不要用残缺样本算出的分位下结论 |
| 参考线核验结果与历史不同 | 数据形态变了 | 见 `references/methodology.md` 的判定顺序，重新判断而不是忽略 |
| 仪表盘没生成 | `_html_error` 非空 | 数据仍有效（`latest.json` 在），报告时说明交付物缺失 |
| 市场数据长期 T-1 | 非交易日，或中证 PE 未更新（18:00 后） | 正常现象，如实说明，不要当成故障 |

## 边界

- 只输出宽基指数择时，不构成投资建议
- 未做历史回测，评分是框架的机械实现，不是胜率
- 九条参考线里只有 PPI 的两条通过逐段检验，其余仅作背景标注——这个结论是实测出来的，不要为了「看起来更严谨」而把它们说成有效
- 休市日历只覆盖 2026 年，次年安排发布后需在 `tm/calendar.py` 补条目

细节全部在 `references/`：
`methodology.md`（框架与判据）、`data-sources.md`（端点与口径）、`reporting.md`（解读与话术）、`pitfalls.md`（改代码时才需要读）。
