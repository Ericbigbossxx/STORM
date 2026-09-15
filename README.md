# STORM V2 — Weekly Local Business Cockpit

NA E-commerce 周会数据看板，基于 Amazon Quick AI + GitHub Pages 自动化方案。

## 工作流程

```
每周更新 xlsx → Amazon Quick 生成 dashboard → 预览确认 → push 到 GitHub Pages
```

### 1. 数据准备
- 更新 `STORM V2 RAW DATA  {date}.xlsx`（actual order 当月全量 + 其他sheets）
- 更新 `cost detail {date}.xlsx`（per-order 成本明细）

### 2. 生成看板
在 Amazon Quick 中说：**"storm dashboard"** 或 **"refresh weekly data"**

Skill 自动：
- 读取 xlsx 数据（当月从新文件，历史月份从上周文件）
- 计算 6 个时间维度（Aug MTD / Jul / Q3 / Q2 / Q1 / YTD）
- 生成 Highcharts 交互式 HTML 看板
- 保存快照到 `snapshots/`

### 3. 部署
```powershell
.\push_w35.ps1   # 推送到 GitHub Pages
```

**线上地址**：https://ericbigbossxx.github.io/STORM/dashboard/

---

## 目录结构

```
STORM V2/
├── README.md                          ← 本文件
├── STORM V2 RAW DATA  8.25.xlsx       ← 本周数据（actual order 仅当月）
├── STORM V2 RAW DATA  8.19.xlsx       ← 上周数据（含历史月份）
├── cost detail 8.19.xlsx              ← 成本明细（per-order）
├── push_w35.ps1                       ← GitHub Pages 推送脚本
├── snapshots/                         ← 每周 dashboard HTML 快照
├── THD_Data/                          ← THD DataConnection 导出数据
├── rithum_data/                       ← Rithum 渠道数据
└── _legacy/                           ← 旧 Python web app（已废弃，仅存档）
```

## 看板功能

| Tab | 内容 |
|-----|------|
| Overview | 日营收趋势、渠道占比、WoW 7天对比 |
| Platform BP | 平台/品牌 BP 达成率（红绿灯） |
| Profit Waterfall | GMV → COGS → GM → 费用 → CM 瀑布图 |
| Brand & Power | 品牌/动力源 CM% vs 5% target |
| SKU Analysis | Top 10 SKU + WoW 涨跌榜 |
| THD DFC | DFC 消费者销售 + 库存 |
| Conclusions | 各平台 Risk / Opportunity / Track |

**全局时间筛选器**（右上角）：Aug MTD / Jul / Q3 / Q2 / Q1 / YTD

## 技术架构

- **生成引擎**：Amazon Quick skill (`storm-weekly-local-business-cockpit`)
- **前端**：单文件 HTML + Highcharts CDN，数据以 JSON 内嵌
- **部署**：GitHub Pages（静态托管，无需服务器）
- **仓库**：https://github.com/Ericbigbossxx/STORM

## 数据规则

- **渠道**：仅 NA E-commerce（THD, Lowe's, Walmart），排除 AMZ/DTC/COSTCO
- **WoW**：严格 7 天 vs 7 天等长窗口
- **BP Pacing**：部分月 = actual × (月天数 / 已过天数)
- **CM%**：基于 cost detail per-order 明细计算
- **品牌**：Badger / Sunseeker
- **动力源**：Robot / Gas / Lithium / ACC

## Git 配置

```
user.email = eric.lv@sunseekerpower.cn
user.name  = Ericbigbossxx
remote     = https://github.com/Ericbigbossxx/STORM.git
```
