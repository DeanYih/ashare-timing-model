# 实现踩坑

只在需要修改 `scripts/tm/` 时才读这份。每条都是实测撞出来的，不是推测。

---

## 一、改文件前先看行尾

**本项目各文件行尾不统一**，用脚本改文件必踩：

- CRLF：`render.py`、`curves.py`、`refs.py`、`run.py`、`indicators.py`
- LF：`config.py`、`models.py`、`sources.py`、`calendar.py`、`verify_*.py`

用 `\n` 拼的多行字符串在 CRLF 文件里**永远匹配不上**，`assert a in s` 会静默失败或直接报错，
而报错位置指向的是一句看起来毫无问题的话。

正确写法：

```python
raw = io.open(p, encoding="utf-8", newline="").read()
crlf = "\r\n" in raw
s = raw.replace("\r\n", "\n") if crlf else raw
# ... 改 s ...
io.open(p, "w", encoding="utf-8",
        newline="").write(s.replace("\n", "\r\n") if crlf else s)
```

另：在 shell heredoc 里写正则替换组（反斜杠 + `1`）会被 JSON 转义成**控制字符 U+0001**，
落到文件里变成 `r"<b>\x01</b>"`，替换出来是空串。改用 `\g<1>`，或用 `chr(92)` 拼接。

## 二、SVG 没有 z-index，绘制顺序就是层级

- 参考线必须画在曲线**之后**，否则标签被曲线压住
- 只给文字加白描边不够，得铺一块半透明底板
- 双轴图的参考线标签要**按轴分边**：左轴贴 `L+3`，右轴贴 `R−44`
  （避开末点数值标签占的 `R−26 ~ R−6`）。两轴必须**合并**做防重叠推挤，
  社融 10% 与 PPI 3% 分属左右轴，实测在同一画布上只差 8px

## 三、日频序列的横轴必须用日序号

用「年×12 + 月」会把同月 20 多个交易日压成同一个 x，RSI 曲线变成一条竖线。
用 `date.toordinal()`。

同理：跨度 ≤14 个月时标 `MM月`（只标偶数月）+ 右端补年份，
否则「近 6 个月」的图会退化成一个「26」，读者看不出是哪几个月。

## 四、图表层的通用判据

1. **同一个数字不要在页面出现两次**。卡片头部已有大字号现值，图上就不要再标末点
   （`single(end_label=False)`）；「45/94」已含百分比，不必再写一行「48%」
2. **状态色跟 role 走，不要一律用警示红**。曾经 chips 的「已触发」全染红，
   结果「PPI≤0 工业通缩」这种偏利好的线一触发就变红，与左边的绿色圆点自相矛盾
3. **四行同一灰度 = 糊成一片灰**。给卡片加说明文字时必须同时把原有各层**降级**，
   靠字号与深浅递降建立阅读顺序（13 粗 → 11.5 → 9.5 最淡 → 10 元信息）
4. **grid 等高会让短卡片留白**。用 `flex column` + `margin-top:auto` + `padding-top`：
   纯 `margin-top:auto` 在无余量时会退化成 0，chips 会紧贴图表
5. **一个字段被两处消费且需求不同时，拆在消费端拼**。参考线的 `label` 数据层只存名字
   （"成本压力"），绘图层拼成「成本压力 3%」，chips 用 `{sign}{v} {label}`——
   在数据层兼容会让两边都别扭
6. **季度数据前向填充必须画阶梯**。折线会把台阶变成斜坡，等于伪造变化率
7. **色带画「逐月回溯状态」必须 3 点滚动众数 + 末端锚定结论**，否则周期月月变
8. **曲线 viewBox 缩到 300px 时字号只剩 3~4px** → 用 `min-width` + 横向滚动 +
   右侧白渐变暗示「还有内容」（硬切一刀读者会以为图就到这里），桌面端隐藏提示

## 五、移动端：`table-layout:fixed` 不是出滚动条，是按比例压缩

核验表固定列宽合计 720px，容器一窄浏览器**压缩每一列**而不是出滚动条：

- 375px 下整表塌成一条细缝，页面被撑到 31488px 高
- **700px 和 768px 同样崩**
- 900px 时结论列只剩 130px、文字竖排

所以卡片化断点定 **1023px**（不是 680）。差 1px 是为了让 iPad 横屏（1024）仍用表格，那时结论列 260px 够用。

卡片化只用 CSS，不改 HTML 语义：

```css
tr::before{content:attr(data-code) " · " attr(data-name)}   /* 行标题 */
td::before{content:attr(data-label);position:absolute;left:0} /* 字段名 */
td{padding-left:56px}                                       /* 值整体右移 */
td:first-child{display:none}                                /* 代码已进标题 */
```

⚠ **不能用 grid**：`td` 里除 `<b>值</b>` 还有 `.basis` div，grid 会把第二个子元素挤到下一格首列。

## 六、页面上最容易漏的两处

- **Markdown 加粗漏到界面**：数据层习惯用 `**强调**`，塞进 HTML 就直接显示星号。
  用 `_rich()` 转 `<b>`。注意别和已有的「取 MM-DD」函数重名（曾覆盖后差点搞坏日期显示）
- **页头日期重复**：`as_of` 与日历 `describe()` 都带日期，拼出来是「数据截至 X · X 交易日」。
  用 `_today_short()` 剥掉日期前缀只留判断

## 七、验证方式

```bash
# 完整流水线（约 10 秒）
python scripts/run_timing.py

# 页面渲染后肉眼确认布局，需要 playwright + PIL：
# 系统 python 没装，用 WorkBuddy 托管解释器
C:/Users/yiech/.workbuddy/binaries/python/envs/default/Scripts/python.exe <截图脚本>
```

改渲染后至少验四档宽度：**375 / 768 / 1023 / 1180**，检查 `document.documentElement.scrollWidth`
是否超出视口，以及核验表在 1023 与 1024 两侧是否切换正确。

**合成单测全绿 ≠ 真机有效**：涉及文件系统与渲染的改动，必须真跑一遍看截图。
