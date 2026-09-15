# STORM Dashboard W36 (Sep 1, 2026) Push Script

$ErrorActionPreference = "Stop"
$repoDir = "C:\Users\admin\Documents\STORM"
$cdnSource = "C:\Users\admin\Documents\STORM V2\snapshots\storm_dashboard_cdn_2026-09-01_w36.html"

Set-Location $repoDir

# Archive current version
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
if (!(Test-Path "dashboard/archive")) { New-Item -ItemType Directory -Path "dashboard/archive" }
if (Test-Path "dashboard/index.html") {
    Copy-Item "dashboard/index.html" "dashboard/archive/index_$timestamp.html"
    Write-Host "Archived old version"
}

# Deploy new W36 version
Copy-Item $cdnSource "dashboard/index.html" -Force
Write-Host "Deployed W36 dashboard"

# Git commit and push
git add -A
git commit -m "W36: August full $305.4K, YTD $3.06M, WoW +30.2%

Data: STORM V2 RAW DATA 9.1 (Aug complete 1754 orders) + 8.19 (Jan-Jul)
Cost: cost detail 8.19 (P&L through 8/17)
August closed: Rev $305.4K, GM 36.7%, CM 16.7%
WoW (8/25-31 vs 8/18-24): +30.2%"
git push origin main
Write-Host "Done! Live at https://ericbigbossxx.github.io/STORM/dashboard/"
