from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(relative_path: str) -> dict:
    return yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))


def test_dimensions_keep_market_platform_and_channel_separate() -> None:
    dimensions = _load_yaml("config/dimensions.yaml")
    assert dimensions["identity_order"][:3] == ["market", "platform", "channel"]
    assert set(dimensions["channels"]["walmart"]) == {"3P", "WFS", "1P", "DSV"}
    assert dimensions["channels"]["lowes"] == ["Drop Ship"]
    assert {item["id"]: item["storm_code"] for item in dimensions["platforms"][:3]} == {
        "walmart": "WMT",
        "thd": "THD",
        "lowes": "LOWES",
    }
    assert dimensions["business_health_levels"]["v0_1_active"] == ["PLATFORM"]
    assert dimensions["currency"]["v0_1_market"] == "US"
    assert dimensions["currency"]["v0_1_currency"] == "USD"
    assert dimensions["currency"]["active_input_field"] is False


def test_feishu_manifest_has_exactly_four_operational_tables() -> None:
    manifest = _load_yaml("config/feishu_schema.yaml")
    assert manifest["base"]["name"] == "STORM | Business Control"
    assert [table["name"] for table in manifest["tables"]] == [
        "01 Business Health",
        "02 Core SKU Performance",
        "03 Action & Validation",
        "04 Signal Register",
    ]


def test_every_table_has_identity_and_provenance_contract() -> None:
    manifest = _load_yaml("config/feishu_schema.yaml")
    for table in manifest["tables"]:
        fields = {field["name"] for field in table["fields"]}
        assert {"Market", "Platform", "Channel"} <= fields
        assert fields & {"Week", "Week Created", "Week Opened"}
        assert any(name.endswith(" ID") for name in fields)
        assert "Created At" in fields
        assert "Updated At" in fields


def _tables_by_name() -> dict[str, dict]:
    manifest = _load_yaml("config/feishu_schema.yaml")
    return {table["name"]: table for table in manifest["tables"]}


def _fields_by_name(table: dict) -> dict[str, dict]:
    return {field["name"]: field for field in table["fields"]}


def test_manifest_has_exactly_thirteen_weekly_pilot_views() -> None:
    tables = _tables_by_name()
    expected = {
        "01 Business Health": ["本周总览", "红黄灯"],
        "02 Core SKU Performance": ["本周核心SKU", "异常SKU"],
        "03 Action & Validation": ["本周动作", "等待验证", "逾期", "P0-P1", "无效或不确定"],
        "04 Signal Register": ["未决Signal", "P0-P1", "风险", "机会"],
    }
    assert {name: table["views"] for name, table in tables.items()} == expected
    assert sum(len(table["views"]) for table in tables.values()) == 13


def test_v0_1_1_manifest_has_exactly_125_fields_and_live_review_ids() -> None:
    manifest = _load_yaml("config/feishu_schema.yaml")
    assert manifest["schema_version"] == "0.1.1"
    assert sum(len(table["fields"]) for table in manifest["tables"]) == 125
    live_tables = manifest["live_identifiers"]["tables"]
    assert live_tables["03 Action & Validation"]["fields"]["Human Reviewed"] == "fldEkYL4yI"
    assert live_tables["04 Signal Register"]["fields"]["Human Reviewed"] == "fldjj5yFif"


def test_human_reviewed_is_human_only_on_every_table() -> None:
    tables = _tables_by_name()
    for table in tables.values():
        field = _fields_by_name(table)["Human Reviewed"]
        assert field["type"] == "checkbox"
        assert field["default"] is False
        assert field["purpose"] == "record_level_human_approval"
        assert field["authority"] == "human_only"
        assert field["ai_may_set_true"] is False

    governance = _load_yaml("config/feishu_schema.yaml")["governance"]["human_reviewed"]
    assert governance["ai_may_set_true"] is False
    assert governance["true_authority"] == "human_review_workflow_only"


def test_specialized_view_filters_match_v0_1_1_semantics() -> None:
    tables = _tables_by_name()
    health = tables["01 Business Health"]["view_filter_contracts"]["红黄灯"]
    assert health["status"] == "ACTIVE"
    assert health["conditions"][-1] == {
        "field": "Overall Health",
        "operator": "is_not",
        "values": ["GREEN"],
    }

    core = tables["02 Core SKU Performance"]["view_filter_contracts"]["异常SKU"]
    assert core["unknown_is_anomaly"] is False
    assert {condition["field"] for condition in core["conditions"]} == {
        "Status",
        "Buyability",
        "Listing Status",
    }
    assert {tuple(condition["values"]) for condition in core["conditions"]} >= {
        ("YELLOW",),
        ("RED",),
        ("NO",),
        ("ISSUE",),
        ("DOWN",),
    }

    action = tables["03 Action & Validation"]["view_filter_contracts"]
    assert action["等待验证"]["conditions"][0]["values"] == [
        "EXECUTED_WAITING_VALIDATION"
    ]
    assert action["P0-P1"]["conditions"][0]["values"] == ["P0", "P1"]
    assert action["无效或不确定"]["conditions"][0]["values"] == [
        "VALIDATED_INEFFECTIVE",
        "INCONCLUSIVE",
    ]

    signal = tables["04 Signal Register"]["view_filter_contracts"]
    assert signal["未决Signal"]["conditions"][0] == {
        "field": "Current Status",
        "operator": "is_not",
        "values": ["RESOLVED", "CLOSED"],
    }
    assert signal["风险"]["conditions"][0]["values"] == ["RISK"]
    assert signal["机会"]["conditions"][0]["values"] == ["OPPORTUNITY"]


def test_overdue_view_is_deferred_without_a_reliable_due_date() -> None:
    action = _tables_by_name()["03 Action & Validation"]
    overdue = action["view_filter_contracts"]["逾期"]
    assert overdue["status"] == "DEFERRED_NOT_RELIABLY_FILTERABLE"
    assert overdue["requires_human_date_confirmation"] is True


def test_business_health_grain_and_default_health_visibility_are_converged() -> None:
    table = _tables_by_name()["01 Business Health"]
    fields = _fields_by_name(table)
    assert table["grain"] == "week x market x platform x level=PLATFORM"
    assert table["uniqueness"] == ["Week", "Market", "Platform", "Level"]
    assert fields["Level"]["v0_1_allowed"] == ["PLATFORM"]
    assert fields["Channel"]["must_be_blank_when"] == {"Level": "PLATFORM"}
    assert table["ui"]["default_visible_health_fields"] == [
        "Overall Health",
        "Sales Health",
        "Ads Health",
        "Inventory Health",
        "Buyability Health",
    ]
    assert table["ui"]["default_hidden_health_fields"] == [
        "Listing Health",
        "Fulfillment Health",
        "Review Health",
        "Project Health",
    ]
    assert fields["Project Health"]["core_health_input"] is False


def test_storm_id_manifest_is_machine_minted_and_not_a_feishu_record_id() -> None:
    manifest = _load_yaml("config/feishu_schema.yaml")
    contract = manifest["storm_ids"]
    assert contract["immutable"] is True
    assert contract["machine_minted"] is True
    assert contract["human_read_only"] is True
    assert contract["feishu_record_id_is_domain_id"] is False
    assert contract["platform_codes"] == {"Walmart": "WMT", "THD": "THD", "Lowe's": "LOWES"}
    assert contract["sequence"]["user_maintained"] is False
    for table in manifest["tables"]:
        id_field = next(field for field in table["fields"] if field["name"].endswith(" ID"))
        assert id_field["immutable"] is True
        assert id_field["machine_minted"] is True
        assert id_field["human_read_only"] is True


def test_signal_action_relation_is_reciprocal_many_to_many() -> None:
    tables = _tables_by_name()
    action_link = _fields_by_name(tables["03 Action & Validation"])["Related Signals"]
    signal_link = _fields_by_name(tables["04 Signal Register"])["Related Actions"]
    assert action_link["type"] == signal_link["type"] == "link_record"
    assert action_link["cardinality"] == signal_link["cardinality"] == "many"
    assert action_link["reciprocal_field"] == "Related Actions"
    assert signal_link["reciprocal_field"] == "Related Signals"


def test_snapshot_locked_exists_only_on_weekly_snapshot_tables() -> None:
    tables = _tables_by_name()
    with_lock = {
        name
        for name, table in tables.items()
        if "Snapshot Locked" in _fields_by_name(table)
    }
    assert with_lock == {"01 Business Health", "02 Core SKU Performance"}
    manifest = _load_yaml("config/feishu_schema.yaml")
    snapshot = manifest["governance"]["weekly_snapshot"]
    assert set(snapshot["lock_field_tables"]) == with_lock
    assert snapshot["local_path"] == "data/snapshots/{week_id}/"


def test_action_required_inputs_are_the_approved_minimum() -> None:
    table = _tables_by_name()["03 Action & Validation"]
    required = {field["name"] for field in table["fields"] if field["required"]}
    assert required == {
        "Action ID",
        "Week Created",
        "Market",
        "Platform",
        "Action Title",
        "Objective",
        "Owner",
        "Priority",
        "Status",
        "Success Criteria",
    }
    assert _fields_by_name(_tables_by_name()["02 Core SKU Performance"])["Diagnosis"]["required"] is False
    assert _fields_by_name(_tables_by_name()["02 Core SKU Performance"])["Recommended Action"]["required"] is False


def test_ai_fields_are_optional_hidden_non_manual_and_human_decision_is_final() -> None:
    manifest = _load_yaml("config/feishu_schema.yaml")
    ai_fields = [
        field
        for table in manifest["tables"]
        for field in table["fields"]
        if field["name"].startswith("AI ")
    ]
    assert {field["name"] for field in ai_fields} == {
        "AI Analysis",
        "AI Suggested Status",
        "AI Confidence",
    }
    for field in ai_fields:
        assert field["required"] is False
        assert field["default_hidden"] is True
        assert field["manual_entry"] is False
        assert field["authority"] == "advisory"
    assert manifest["governance"]["human_decision_authority"] == "final"


def test_currency_is_not_an_active_feishu_input_field() -> None:
    manifest = _load_yaml("config/feishu_schema.yaml")
    assert all(
        field["name"] != "Currency"
        for table in manifest["tables"]
        for field in table["fields"]
    )


def test_lark_mcp_sorting_limit_is_documented_as_non_blocking() -> None:
    manifest = _load_yaml("config/feishu_schema.yaml")
    limitation = manifest["governance"]["persistent_view_sorting"]
    assert limitation["supported_by_lark_mcp_0_5_1"] is False
    assert limitation["impact"] == "non_blocking"
    assert limitation["runtime_record_sorting_allowed"] is True


def test_repository_contract_does_not_name_feishu_secret_variables() -> None:
    forbidden = (
        "FEISHU_" + "APP_ID",
        "FEISHU_" + "APP_SECRET",
        "tenant_" + "access_token",
    )
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in {".git", ".venv"} for part in path.parts):
            continue
        if path.suffix.lower() not in {".md", ".py", ".toml", ".yaml", ".yml", ".example"}:
            continue
        content = path.read_text(encoding="utf-8")
        assert not any(value in content for value in forbidden), path
