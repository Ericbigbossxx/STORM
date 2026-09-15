"""
Criteo Retail Media API — Lowe's 广告数据自动拉取（最终版）
===========================================================
全自动拉取 Lowe's One Roof Media Network 广告投放数据
默认 SKU (Product) 级别 — 直接对接 STORM V2 CM 分析

数据输出:
    STORM V2\rithum_data\ads\lowes\
    ├── product_YYYYMMDD.csv          ← 每日 SKU 级广告数据（含 internal_sku）
    ├── campaigns_YYYYMMDD.csv        ← 每日 Campaign 级汇总
    ├── summary_YYYYMMDD.json         ← 每日汇总指标
    └── logs/

使用方法:
    python criteo_lowes_ads.py --test           # 测试连通
    python criteo_lowes_ads.py --daily          # 拉昨日数据
    python criteo_lowes_ads.py --backfill 30    # 回填 30 天
    python criteo_lowes_ads.py --install-task   # 注册 Windows 定时任务
"""

import requests
import pandas as pd
import json
import logging
import time
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import argparse

# ============================================================
# 配置 — 只需改 CLIENT_SECRET
# ============================================================

CLIENT_ID = "a2eef9009b054b798224fa8d6ad81d0a"
CLIENT_SECRET=[REDACTED_PASSWORD]  # ← 唯一需要你填的

ACCOUNT_ID = "722533017166663680"
API_VERSION = "2026-01"

# 本地路径
DATA_ROOT = r"C:\Users\admin\Documents\STORM V2\rithum_data\ads\lowes"
MASTER_SKU_MAP_PATH = r"C:\Users\admin\Documents\STORM V2\rithum_data\master_sku_map.json"

# 定时运行时间 (UTC) — 10:00 UTC = 北京时间 18:00
SCHEDULE_TIME_UTC = "10:00"

# ============================================================
# API
# ============================================================

TOKEN_URL = "https://api.criteo.com/oauth2/token"
API_BASE = f"https://api.criteo.com/{API_VERSION}/retail-media"


class CriteoAPI:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expiry = None

    def authenticate(self):
        resp = requests.post(TOKEN_URL, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        })
        if resp.status_code != 200:
            raise Exception(f"认证失败 ({resp.status_code}): {resp.text}")
        data = resp.json()
        self.token = data["access_token"]
        self.token_expiry = datetime.now() + timedelta(seconds=data.get("expires_in", 900) - 60)

    def _headers(self):
        if not self.token or datetime.now() >= self.token_expiry:
            self.authenticate()
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def _submit_and_poll(self, payload, label="report"):
        """提交报表请求 → 轮询 → 下载结果"""
        resp = requests.post(f"{API_BASE}/reports/accounts", headers=self._headers(), json=payload)
        if resp.status_code != 200:
            raise Exception(f"{label} 请求失败 ({resp.status_code}): {resp.text}")

        report_id = resp.json().get("data", {}).get("id")
        logging.info(f"    报表已提交 (id: {report_id[:12]}...), 等待生成...")

        for _ in range(60):
            time.sleep(5)
            sr = requests.get(f"{API_BASE}/reports/{report_id}/status", headers=self._headers())
            if sr.status_code != 200:
                continue
            status = sr.json().get("data", {}).get("attributes", {}).get("status")
            if status == "success":
                logging.info(f"    报表完成，下载中...")
                dl = requests.get(f"{API_BASE}/reports/{report_id}/output", headers=self._headers())
                if dl.status_code == 200:
                    try:
                        return json.loads(dl.text)
                    except:
                        return {"raw_text": dl.text}
                elif dl.status_code == 400:
                    logging.warning(f"    该时段无数据")
                    return []
                else:
                    raise Exception(f"下载失败: {dl.status_code}")
            elif status == "failure":
                raise Exception(f"报表生成失败")
        raise Exception("报表超时 (300s)")

    def get_product_report(self, account_id, start_date, end_date):
        """SKU/Product 级报表（默认）"""
        payload = {
            "data": {
                "type": "RetailMediaReportRequest",
                "attributes": {
                    "accountIds": [account_id],
                    "reportType": "product",
                    "startDate": start_date.strftime("%Y-%m-%d"),
                    "endDate": end_date.strftime("%Y-%m-%d"),
                    "timeZone": "America/New_York",
                    "campaignType": "sponsoredProducts",
                    "format": "json",
                }
            }
        }
        return self._submit_and_poll(payload, "Product")

    def get_campaign_report(self, account_id, start_date, end_date):
        """Campaign 级报表"""
        payload = {
            "data": {
                "type": "RetailMediaReportRequest",
                "attributes": {
                    "accountIds": [account_id],
                    "metrics": ["impressions", "clicks", "spend",
                                "attributedSales", "attributedOrders", "attributedUnits"],
                    "dimensions": ["date", "campaignId", "campaignName"],
                    "reportType": "summary",
                    "startDate": start_date.strftime("%Y-%m-%d"),
                    "endDate": end_date.strftime("%Y-%m-%d"),
                    "timeZone": "America/New_York",
                    "campaignType": "sponsoredProducts",
                    "format": "json",
                }
            }
        }
        return self._submit_and_poll(payload, "Campaign")

    def list_accounts(self):
        resp = requests.get(f"{API_BASE}/accounts", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def list_campaigns(self, account_id):
        resp = requests.get(f"{API_BASE}/accounts/{account_id}/campaigns", headers=self._headers())
        resp.raise_for_status()
        return resp.json()


# ============================================================
# SKU 映射
# ============================================================

def load_sku_map():
    """加载 Master SKU Map，返回 advProductId → internal_sku/upc 的字典"""
    map_path = Path(MASTER_SKU_MAP_PATH)
    if not map_path.exists():
        logging.warning(f"Master SKU Map 不存在: {map_path}")
        return {}

    with open(map_path, "r", encoding="utf-8") as f:
        sku_list = json.load(f)

    # 构建 criteo_product_id → entry 映射
    mapping = {}
    for entry in sku_list:
        criteo_id = entry.get("lowes", {}).get("criteo_product_id")
        if criteo_id:
            mapping[str(criteo_id)] = {
                "internal_sku": entry["internal_sku"],
                "upc": entry["upc"],
                "product_category": entry.get("product_category", ""),
                "brand": entry.get("brand", ""),
            }
    return mapping


def enrich_with_sku(df, sku_map):
    """给 DataFrame 添加 internal_sku, upc 列"""
    if not sku_map or "advProductId" not in df.columns:
        return df

    df["advProductId"] = df["advProductId"].astype(str)
    df["internal_sku"] = df["advProductId"].map(lambda x: sku_map.get(x, {}).get("internal_sku", ""))
    df["upc"] = df["advProductId"].map(lambda x: sku_map.get(x, {}).get("upc", ""))
    df["mapped_category"] = df["advProductId"].map(lambda x: sku_map.get(x, {}).get("product_category", ""))

    # 未映射的 SKU 警告
    unmapped = df[df["internal_sku"] == ""]["advProductId"].unique()
    if len(unmapped) > 0:
        logging.warning(f"  未映射的 Criteo Product ID: {list(unmapped)}")
        logging.warning(f"  请更新 Master SKU Map: {MASTER_SKU_MAP_PATH}")

    return df


# ============================================================
# 数据存储
# ============================================================

def save_data(records, report_type, date_label, data_root, sku_map=None):
    """保存报表数据"""
    root = Path(data_root)
    root.mkdir(parents=True, exist_ok=True)

    if not records:
        logging.warning(f"  无数据: {report_type} ({date_label})")
        return None

    if isinstance(records, dict) and "raw_text" in records:
        # 原始文本，直接保存
        raw_file = root / f"raw_{report_type}_{date_label}.txt"
        with open(raw_file, "w", encoding="utf-8") as f:
            f.write(records["raw_text"])
        return None

    df = pd.DataFrame(records)
    if df.empty:
        return None

    # 如果是 product 报表，添加内部 SKU 映射
    if report_type == "product" and sku_map:
        df = enrich_with_sku(df, sku_map)

    # 保存 CSV
    csv_file = root / f"{report_type}_{date_label}.csv"
    df.to_csv(csv_file, index=False, encoding="utf-8-sig")
    logging.info(f"  保存: {csv_file.name} ({len(df)} 行)")

    # 生成汇总
    summary = {
        "date": date_label,
        "report_type": report_type,
        "rows": len(df),
        "generated_at": datetime.now().isoformat(),
    }
    for metric in ["impressions", "clicks", "spend", "attributedSales", "attributedOrders"]:
        if metric in df.columns:
            summary[f"total_{metric}"] = round(float(pd.to_numeric(df[metric], errors='coerce').sum()), 2)

    total_spend = summary.get("total_spend", 0)
    total_sales = summary.get("total_attributedSales", 0)
    summary["roas"] = round(total_sales / total_spend, 2) if total_spend > 0 else 0

    json_file = root / f"summary_{report_type}_{date_label}.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return summary


# ============================================================
# 运行模式
# ============================================================

def run_daily(api, account_id, data_root):
    """每日拉取（Product + Campaign 双层）"""
    yesterday = datetime.now() - timedelta(days=1)
    date_label = yesterday.strftime("%Y%m%d")
    sku_map = load_sku_map()

    logging.info(f"日期: {yesterday.strftime('%Y-%m-%d')}")
    logging.info(f"SKU Map: {len(sku_map)} 条映射已加载")

    # 1. Product (SKU) 级 — 主数据
    logging.info("拉取 Product (SKU) 级报表...")
    try:
        data = api.get_product_report(account_id, yesterday, yesterday)
        summary = save_data(data, "product", date_label, data_root, sku_map)
        if summary:
            logging.info(f"    花费: ${summary.get('total_spend', 0):,.2f} | "
                         f"销售: ${summary.get('total_attributedSales', 0):,.2f} | "
                         f"ROAS: {summary.get('roas', 0)}")
    except Exception as e:
        logging.error(f"  Product 报表失败: {e}")

    # 2. Campaign 级 — 辅助参考
    logging.info("拉取 Campaign 级报表...")
    try:
        data = api.get_campaign_report(account_id, yesterday, yesterday)
        save_data(data, "campaigns", date_label, data_root)
    except Exception as e:
        logging.error(f"  Campaign 报表失败: {e}")


def run_backfill(api, account_id, data_root, days=30):
    """回填历史（Product 级）"""
    end = datetime.now() - timedelta(days=1)
    start = end - timedelta(days=days)
    sku_map = load_sku_map()

    logging.info(f"回填: {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}")
    logging.info(f"SKU Map: {len(sku_map)} 条映射已加载")

    current = start
    while current <= end:
        batch_end = min(current + timedelta(days=6), end)
        date_label = f"{current.strftime('%Y%m%d')}_{batch_end.strftime('%Y%m%d')}"
        logging.info(f"  批次: {current.strftime('%Y-%m-%d')} ~ {batch_end.strftime('%Y-%m-%d')}")

        try:
            data = api.get_product_report(account_id, current, batch_end)
            save_data(data, "product", date_label, data_root, sku_map)
        except Exception as e:
            logging.error(f"    失败: {e}")

        current = batch_end + timedelta(days=1)
        time.sleep(2)


def install_windows_task():
    script_path = Path(__file__).resolve()
    bat_path = script_path.parent / "criteo_auto_run.bat"
    bat_content = f"""@echo off
cd /d "{script_path.parent}"
python "{script_path}" --daily >> "{DATA_ROOT}\\logs\\auto_run.log" 2>&1
"""
    with open(bat_path, "w") as f:
        f.write(bat_content)

    task_name = "Criteo_Lowes_Ads_Daily"
    cmd = f'schtasks /create /tn "{task_name}" /tr "{bat_path}" /sc daily /st {SCHEDULE_TIME_UTC.replace(":", "")} /f'

    print(f"注册定时任务: {task_name}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✓ 成功！每天 {SCHEDULE_TIME_UTC} UTC (北京 18:00) 自动运行")
    else:
        print(f"✗ 失败: {result.stderr}\n手动运行: {cmd}")


# ============================================================
# 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Criteo Lowe's 广告数据自动拉取")
    parser.add_argument("--test", action="store_true", help="测试连通性")
    parser.add_argument("--daily", action="store_true", help="拉取昨日数据")
    parser.add_argument("--backfill", type=int, default=0, help="回填 N 天历史")
    parser.add_argument("--list-accounts", action="store_true")
    parser.add_argument("--list-campaigns", action="store_true")
    parser.add_argument("--install-task", action="store_true")
    args = parser.parse_args()

    Path(DATA_ROOT).mkdir(parents=True, exist_ok=True)
    (Path(DATA_ROOT) / "logs").mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(Path(DATA_ROOT) / "logs" / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )

    if args.install_task:
        install_windows_task()
        return

    if not CLIENT_ID or CLIENT_SECRET == "YOUR_SECRET_HERE":
        print("请填入 CLIENT_SECRET（第 37 行）")
        return

    api = CriteoAPI(CLIENT_ID, CLIENT_SECRET)

    if args.test:
        print("测试 Criteo API...")
        try:
            api.authenticate()
            print("✓ 认证成功！")
            accounts = api.list_accounts()
            print(f"✓ 账户: {json.dumps(accounts, indent=2, default=str)[:500]}")
        except Exception as e:
            print(f"✗ 失败: {e}")
        return

    if args.list_accounts:
        api.authenticate()
        print(json.dumps(api.list_accounts(), indent=2, default=str))
        return

    if args.list_campaigns:
        api.authenticate()
        print(json.dumps(api.list_campaigns(ACCOUNT_ID), indent=2, default=str))
        return

    logging.info("=" * 50)
    logging.info("Criteo Lowe's 广告数据拉取（SKU 级）")
    logging.info("=" * 50)
    api.authenticate()
    logging.info("✓ 认证成功")

    if args.backfill > 0:
        run_backfill(api, ACCOUNT_ID, DATA_ROOT, args.backfill)
    else:
        run_daily(api, ACCOUNT_ID, DATA_ROOT)


if __name__ == "__main__":
    main()
