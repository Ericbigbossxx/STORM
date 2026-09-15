"""测试 Criteo Product 级报表 — SKU 维度数据"""
import requests
import json
import time

# 从主脚本导入凭证（避免重复填写）
from criteo_lowes_ads import CLIENT_ID, CLIENT_SECRET, ACCOUNT_ID, API_VERSION

TOKEN_URL = "https://api.criteo.com/oauth2/token"
API_BASE = f"https://api.criteo.com/{API_VERSION}/retail-media"

# 认证
token_resp = requests.post(TOKEN_URL, data={
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET,
    'grant_type': 'client_credentials',
})
token = token_resp.json()['access_token']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
print("✓ 认证成功\n")

# 拉取 Product 级报表
print("=== 提交 Product 级报表请求 ===")
payload = {
    "data": {
        "type": "RetailMediaReportRequest",
        "attributes": {
            "accountIds": [ACCOUNT_ID],
            "reportType": "product",
            "startDate": "2026-08-01",
            "endDate": "2026-08-19",
            "timeZone": "America/New_York",
            "campaignType": "sponsoredProducts",
            "format": "json",
        }
    }
}

resp = requests.post(f"{API_BASE}/reports/accounts", headers=headers, json=payload)
print(f"Status: {resp.status_code}")

if resp.status_code != 200:
    print(f"Error: {resp.text}")
    exit()

report_id = resp.json().get("data", {}).get("id")
print(f"Report ID: {report_id}")
print("等待报表生成...")

# 轮询等待
for i in range(30):
    time.sleep(5)
    status_resp = requests.get(f"{API_BASE}/reports/{report_id}/status", headers=headers)
    status = status_resp.json().get("data", {}).get("attributes", {}).get("status")
    print(f"  [{i*5}s] 状态: {status}")
    
    if status == "success":
        print("\n✓ 报表生成完成，正在下载...")
        dl_resp = requests.get(f"{API_BASE}/reports/{report_id}/output", headers=headers)
        
        if dl_resp.status_code == 200:
            content_type = dl_resp.headers.get("Content-Type", "")
            
            if "json" in content_type:
                data = dl_resp.json()
                print(f"\n返回格式: JSON")
                print(json.dumps(data, indent=2, default=str)[:3000])
            else:
                # JSON array 格式
                text = dl_resp.text
                try:
                    records = json.loads(text)
                    print(f"\n返回格式: JSON Array ({len(records)} 条记录)")
                    print(f"字段: {list(records[0].keys()) if records else 'empty'}")
                    print(f"\n前 10 条数据:")
                    for r in records[:10]:
                        print(f"  {r}")
                    
                    # 保存完整数据
                    with open(r"C:\Users\admin\Documents\STORM V2\rithum_data\ads\lowes\product_report_20260801_20260819.json", "w", encoding="utf-8") as f:
                        json.dump(records, f, indent=2, ensure_ascii=False)
                    print(f"\n✓ 已保存完整数据 ({len(records)} 条)")
                except:
                    print(f"\n返回格式: 文本/CSV")
                    print(text[:2000])
                    with open(r"C:\Users\admin\Documents\STORM V2\rithum_data\ads\lowes\product_report_20260801_20260819.csv", "w", encoding="utf-8-sig") as f:
                        f.write(text)
                    print(f"\n✓ 已保存原始文件")
        else:
            print(f"下载失败: {dl_resp.status_code}")
        break
    
    elif status == "failure":
        msg = status_resp.json().get("data", {}).get("attributes", {}).get("message")
        print(f"\n✗ 报表生成失败: {msg}")
        break
else:
    print("\n超时（150s），报表仍未完成")
