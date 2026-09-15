"""测试 Criteo API — 用正确的端点拉取报表"""
import requests
import json

CLIENT_ID = "a2eef9009b054b798224fa8d6ad81d0a"
# 请确保下面这行是你真实的 secret（带引号的字符串）
CLIENT_SECRET = "W9TzWbe1idpZ18ImBeL7sWUgcwRumHT1bNIHcsWOKbFb"

ACCOUNT_ID = "722533017166663680"

# 认证
token_resp = requests.post('https://api.criteo.com/oauth2/token', data={
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET,
    'grant_type': 'client_credentials',
})
if token_resp.status_code != 200:
    print(f"认证失败: {token_resp.text}")
    exit()

token = token_resp.json()['access_token']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
print("✓ 认证成功\n")

# 方法1: Account 级报表（用 accountIds 复数）
print("=== 方法1: Account 级报表 ===")
payload1 = {
    "data": {
        "type": "RetailMediaReportRequest",
        "attributes": {
            "accountIds": [ACCOUNT_ID],
            "metrics": ["impressions", "clicks", "spend", "attributedSales", "attributedOrders"],
            "dimensions": ["date"],
            "reportType": "summary",
            "startDate": "2026-08-01",
            "endDate": "2026-08-19",
            "timeZone": "America/New_York",
            "campaignType": "sponsoredProducts",
            "format": "json",
        }
    }
}
r1 = requests.post(
    'https://api.criteo.com/2026-01/retail-media/reports/accounts',
    headers=headers,
    json=payload1
)
print(f"Status: {r1.status_code}")
print(r1.text[:2000])

# 方法2: Campaign 级报表（用具体的 campaign ID）
print("\n=== 方法2: 单个 Campaign 报表 ===")
CAMPAIGN_ID = "723832486135775232"  # Lowes- Lawn Mower-WB40V18PLM

payload2 = {
    "data": {
        "type": "RetailMediaReportRequest",
        "attributes": {
            "id": CAMPAIGN_ID,
            "metrics": ["impressions", "clicks", "spend", "attributedSales", "attributedOrders"],
            "dimensions": ["date"],
            "reportType": "summary",
            "startDate": "2026-07-01",
            "endDate": "2026-08-19",
            "timeZone": "America/New_York",
            "campaignType": "sponsoredProducts",
            "format": "json",
        }
    }
}
r2 = requests.post(
    'https://api.criteo.com/2026-01/retail-media/reports/campaigns',
    headers=headers,
    json=payload2
)
print(f"Status: {r2.status_code}")
print(r2.text[:2000])
