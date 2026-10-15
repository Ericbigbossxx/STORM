# STORM — Weekly Business Cockpit

NA E-commerce 周会看板，覆盖 THD、Lowe’s、Walmart，按 Badger / Sunseeker 展示。

**线上地址**：https://ericbigbossxx.github.io/STORM/dashboard/

## 当前版本

当前发布版本为 **W42**：源文件 `STORM V2 RAW DATA 10.13.xlsx`，订单及 THD sell-out 均截至 **2026-10-12**。本次修正发布日期为 2026-10-15；GitHub Pages 从 main 分支发布。

- 保留原看板布局、品牌及渠道划分；Walmart / Sunseeker 仍未设 BP。
- 本批次复核记录和审计产物存于仓库外的本机 `%LOCALAPPDATA%/STORM/releases/w42-2026-10-12-cm-fix-2026-10-15/`，绑定源文件 SHA256；原始 Excel 保留。
- 本批次没有归月、空白费用或同键费用冲突，仅合并完全重复的业务记录。Filter 标记不单独决定取舍。
- 已确认发生但未分摊到订单的月度费用按渠道 / 品牌独立补计，不伪造订单或分配到 SKU；汇总页差异保留披露。
- 上期比较读取 W41 的已复核源表及已确认费用，避免重新引入原始表中的旧副本或归月问题。
- 本次补入 1、2、5 月已确认且未分摊到订单的费用；沿用源表整数精度，与现有当月补费一致。原 CM 工作簿只读，不修改。
- 1 月至截止月的收入、全部费用项目和 Warehouse + Shipping 均需校验。订单去重费用单列桥接；已核实的导出取整差异逐项披露，未解释的差额、缺失月度汇总或补费来源不符会阻止生成。
- 六个期间为 Oct MTD、Sep、Q4、Q3、Q2、YTD；WoW 使用完整的两段 7 天。
- 保留 W42 原发布及此前全部快照；本次修正快照为 `snapshots/storm_dashboard_cdn_2026-10-12_w42_cm_fix_2026-10-15.html`。

## 本地生成与验收

原 Amazon Quick Skill 已缺失；当前入口使用 Python 3.12+ 和 openpyxl 3.1（依赖已声明在 `pyproject.toml`），不依赖该 Skill。
在项目根目录运行：

```powershell
$stormRelease = Join-Path $env:LOCALAPPDATA "STORM/releases/w42-2026-10-12-cm-fix-2026-10-15"
python -B scripts/reproduce_weekly_dashboard.py --mode weekly --na-cost-zero-approved --source "STORM V2 RAW DATA 10.13.xlsx" --previous-source "STORM V2 RAW DATA 10.9.xlsx" --source-review "$stormRelease/source_review_policy.json" --previous-source-review outputs/w41-2026-10-07/source_review_policy.json --output-dir "$stormRelease/w42"
python -B tests/test_weekly_dashboard_reproduction.py
```

打开上述本机目录的 `w42/index.html` 预览。`weekly_data.json` 为计算数据，`source_audit.json` 保留来源摘要、重复行、BP 排除依据、利润复核与前期修订；本次私有产物保存在仓库外；已有忽略目录仅保留历史证据。审计 JSON、复核记录和 Excel 均不提交。

默认模板固定使用 `snapshots/storm_dashboard_cdn_2026-09-21_w39.html`。模板仅提供布局，指标从源表计算；不要将已生成的 W40 页面作为输入模板，否则会重复套用页面结构。`--baseline` 可显式指定兼容的历史模板。

本批次已核对 1—10 月全部月份。新的月份及不同结构源文件仍需核对期间、表头与口径后验收，不能把程序成功运行视为新批次已获确认。`--source-review` 只接受与该工作簿哈希一致的复核记录；下一批次不能直接沿用。没有复核记录时，费用冲突与未认可的成本值仍会阻止生成。上期源表需要修正时，通过 `--previous-source-review` 显式读取该批次已确认的复核记录，不把上期例外应用到当前源表。

## 数据口径

- 范围：US / 2026，THD DS、THD DFC、Lowe’s DS、Walmart MP、Walmart DSV；排除 AMZ、DTC、Costco。
- Revenue 与 COGS：`actual order` 的 Ordered Revenue 与 Cost/ALL。Cost/ALL 已是整行成本，不再乘数量。
- GM = Revenue − COGS。CM 再扣 Fixed cost、Marketing、Return + Warranty、Funding；为列明费用后的贡献利润，不是公司净利润。全部已核月份 Warehouse + Shipping 为零，任何历史月份非零或未知时需新增口径映射，不能忽略。
- 已确认发生、尚未分摊到订单的月度费用通过复核记录按渠道 / 品牌独立补计。费用汇总与保留订单不相等时，明确拆出重复行扣除、独立补费、取整及已复核源表差异，不直接把源表总额覆盖到订单。补计记录的来源单元格、月份、渠道、品牌、费用类型、月度金额和已分摊金额均须与源表一致，且不得重复。补计金额为月度来源金额减已分摊金额；不伪造订单，不改变收入、销量和订单数。无收入但有费用时保留贡献亏损，利润率显示不适用。
- 成本 `#N/A` 按用户 2026-09-29 确认作为 0；`-` 沿用零费用标记。其他错误值阻止生成；零 COGS 对应收入单独披露。
- 订单键：Date + SKU + Order Number + Channel + Cost Type。周更只合并完全相同行，Filter 仅为辅助标记，不参与业务字段相同的判定；同键业务字段冲突时停止，不静默选首行或末行。已确认或有来源证据的批次修正通过本地复核记录显式处理；源表不删除记录。
- BP：读取 `KPI Rawdata`，但用户确认的范围优先。Walmart / Sunseeker 原始计划明细不等于有效目标；其销售保留，BP 及达成率排除。
- 部分月平台/品牌 BP 达成率按 actual × 月天数 ÷ 已过天数外推；SKU 达成率不外推，跨平台汇总仅计入有目标的同范围实际收入。
- WoW：当期源文件内期末 7 天与前 7 天；月初允许跨到上月，销售总额仍按所选期间汇总。MoM 若比较整月与部分月，表头明确 MTD；Q3 延续此前两个完整月的比较。前后源文件修订单独披露。
- THD sell-out 来自 `THD- robot Sell out`，与订单收入分开；库存读取 I:J，对应文件快照，不随历史月份重建。
- 使用工作簿已保存值，不重算 Excel 公式。汇总页与明细不一致时保留差异，采用已交叉核对的订单明细，不混用。

## 费用遗漏复盘与长期规则

2026-10-15 调查发现两类独立问题：STORM 曾只依赖订单费用分摊，遗漏无销售月份的已发生费用；旧验收主要检查当前月，未覆盖历史月份，因此内部计算一致仍可能漏费。原 CM 的费用明细曾存在 PV 筛选公式缺失及外部 Config 引用，使渠道 CM 视图漏扣台账中已有的费用，不能直接把该视图的 CM 当作费用真值。

以后每周更新必须核对本月及全部历史月份费用，包含无销售范围，并独立复核季度 / YTD。每批重新绑定源表 SHA256，逐项保留分摊、补费、去重和取整证据；有未解释差额，即使已获发布授权也先不发布。原 CM 继续只读，不改值、不补公式、不保存重算或更新外链。完整执行规则见 [AGENTS.md](AGENTS.md#storm-周更费用校验与发布门槛)。

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
