# STORM project instructions

1. Default to one main agent.
2. Read and inspect before editing.
3. Make the minimum sufficient change.
4. Do not scan unrelated directories or other Codex projects.
5. Never edit global Codex or Hermes configuration unless explicitly instructed.
6. Do not touch existing Feishu Bases; STORM may only use its separately approved Base.
7. Do not make platform-side business changes.
8. Treat STORM IDs, table names, field names, and schema names as contracts.
9. Preserve source evidence and provenance.
10. `UNKNOWN` is valid; never fabricate missing metrics or convert unknown data to `GREEN`.
11. Human-reviewed status overrides AI suggestions. AI output is advisory only.
12. Future integrations go through adapters; never add platform-specific logic to domain models.
13. Run focused tests first. Run broader validation only for phase acceptance or explicit requests.
14. Stop and report if required external permission is missing.
15. Do not place secrets, credentials, tokens, webhook URLs, live exports, or business data in this repository.
16. Do not implement Streamlit, live ingestion, scheduling, notifications, or autonomous write-back in v0.1.
17. Do not advance to a later build phase without explicit authorization.

## STORM 周更费用校验与发布门槛

以下为用户于 2026-10-15 确认的长期规则，适用于每次周更：

1. 必须同时核对本月和源表覆盖的全部历史月份，至少包括当年 1 月至源表数据截止月；不能只验收本月。缺月或跨年口径未确认时先停止。
2. 按月份、渠道、品牌逐项核对固定费用、站内营销、站外种草、渠道营销、退货 / 质保、Funding 和 Warehouse + Shipping。无销售、无订单的范围也必须核对，不能把未分摊费用当作零费用。
3. 每项差额明确拆为保留订单分摊、已确认的独立补费、重复行费用扣除、可验证的取整差异或有来源证据的其他差异。不得为对齐汇总而强行调账、泛称取整、扩大误差范围或伪造订单 / SKU 分摊。
4. 每批源表重新核对并绑定 SHA256，记录来源单元格、月份、范围、月度金额、已分摊金额、补费金额和解释证据。沿用已确认费用时仍须重核新源表；不得机械复制旧行号、旧金额或旧豁免。
5. 有解释不清的差额、未知 / 缺失费用、归属不明、冲突重复记录或补费证据不符时，停止生成 / 发布并报告问题及解决建议。即使已经获得发布授权也不得绕过此门槛；不能靠新增“已复核”标签放行尚无证据的差额。
6. 独立复算受影响月份和季度 / YTD，并核对渠道、品牌、动力源及页面显示；费用补计不得改变收入、销量、订单数或商品成本。程序成功运行、内部勾稽通过、固定数量的测试通过，均不能代替费用来源验收。发布后核对实际线上内容。
7. 原 CM 工作簿始终只读：不得改值、补公式、保存重算结果或更新外部链接。修改原表须另获明确授权。保留原始源表与已发布旧快照，修订另留证据；私有费用复核记录和审计明细保存在仓库外。
