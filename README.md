# STORM — Weekly Business Cockpit

NA E-commerce 周会看板，覆盖 THD、Lowe’s、Walmart，按 Badger / Sunseeker 展示。

**线上地址**：https://ericbigbossxx.github.io/STORM/dashboard/

## 当前发布版本

W40，数据截至 **2026-09-28**，源文件为 `STORM V2 RAW DATA  9.29.xlsx`。
本次整理日期为 2026-10-08；并非已更新至 10 月数据。

- Walmart / Sunseeker 未设 BP，不计算该组合的目标达成率。
- 首页展示 GM → CM 费用拆解，利润定义、零成本影响及源表差异见“数据口径”。
- Conclusions 每个平台一个模块，左侧 Badger、右侧 Sunseeker。
- 保留 W39 及此前快照；W40 发布快照位于 `snapshots/storm_dashboard_cdn_2026-09-28_w40.html`。

## 本地生成与验收

原 Amazon Quick Skill 已缺失；当前入口使用 Python 3.12+ 和 openpyxl 3.1（依赖已声明在 `pyproject.toml`），不依赖该 Skill。
在项目根目录运行：

```powershell
python -B scripts/reproduce_weekly_dashboard.py --mode weekly --na-cost-zero-approved --source "STORM V2 RAW DATA  9.29.xlsx" --previous-source "STORM V2 RAW DATA  9.22.xlsx" --output-dir outputs/w40-2026-09-28
python -B tests/test_weekly_dashboard_reproduction.py
```

打开 `outputs/w40-2026-09-28/index.html` 预览。`weekly_data.json` 为计算数据，`source_audit.json` 保留来源摘要、重复行、BP 排除依据、利润复核与前期修订；这些本地产物和 Excel 保持忽略，不提交。

默认模板固定使用 `snapshots/storm_dashboard_cdn_2026-09-21_w39.html`。模板仅提供布局，指标从源表计算；不要将已生成的 W40 页面作为输入模板，否则会重复套用页面结构。`--baseline` 可显式指定兼容的历史模板。

本入口已验收 9 月批次。新的月份及不同结构源文件仍需核对期间、表头与口径后验收，不能把程序成功运行视为新批次已获确认。

## 数据口径

- 范围：US / 2026，THD DS、THD DFC、Lowe’s DS、Walmart MP、Walmart DSV；排除 AMZ、DTC、Costco。
- Revenue 与 COGS：`actual order` 的 Ordered Revenue 与 Cost/ALL。Cost/ALL 已是整行成本，不再乘数量。
- GM = Revenue − COGS。CM 再扣 Fixed cost、Marketing、Return + Warranty、Funding；为列明费用后的贡献利润，不是公司净利润。当前月 Warehouse + Shipping 为零，非零或未知时需新增口径映射，不能忽略。
- 成本 `#N/A` 按用户 2026-09-29 确认作为 0；`-` 沿用零费用标记。其他错误值阻止生成；零 COGS 对应收入单独披露。
- 订单键：Date + SKU + Order Number + Channel + Cost Type。周更只合并完全相同行，同键字段冲突时停止，不静默选首行或末行。源表不删除记录。
- BP：读取 `KPI Rawdata`，但用户确认的范围优先。Walmart / Sunseeker 原始计划明细不等于有效目标；其销售保留，BP 及达成率排除。
- 部分月平台/品牌 BP 达成率按 actual × 月天数 ÷ 已过天数外推；SKU 达成率不外推，跨平台汇总仅计入有目标的同范围实际收入。
- WoW：当期源文件内期末 7 天与前 7 天。MoM 若比较整月与部分月，表头明确 MTD；Q3 延续此前两个完整月的比较。前后源文件修订单独披露。
- THD sell-out 来自 `THD- robot Sell out`，与订单收入分开；库存读取 I:J，对应文件快照，不随历史月份重建。
- 使用工作簿已保存值，不重算 Excel 公式。汇总页与明细不一致时保留差异，采用已交叉核对的订单明细，不混用。

## 发布

人工确认后，将验收页面更新至 `dashboard/index.html` 并新增同内容周快照。发布页应将“本地预览、尚未发布”说明调整为本次发布信息。
只逐项暂存本次页面、快照、生成器、测试及说明；**不要使用 `git add -A`**。Excel、订单导出、审计 JSON、凭据、令牌及本地运行产物不得上传。只有经用户明确授权的看板展示内容可作为发布产物。

推送 `main` 后，GitHub Pages 从仓库根目录构建。验收应同时检查构建成功及线上页面内容与本次文件一致。历史 `push_w35.ps1` 等脚本含旧路径和全量暂存，仅作历史证据，不用于本次流程。

页面使用 Highcharts CDN，需要网络。无自动采集、定时执行、通知、飞书写回或平台业务修改。

## W39 历史复现

```powershell
python -B scripts/reproduce_weekly_dashboard.py --source "STORM V2 RAW DATA  9.22.xlsx" --output-dir outputs/w39-reproduction
```

历史入口重现当时的处理并记录差异，其 UNKNOWN 成本及 BP 假设仅保留为证据，不代表现行周更口径。
