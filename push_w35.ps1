# STORM Dashboard W35 (Aug 25, 2026) Push Script

$ErrorActionPreference = "Stop"
$repoDir = "C:\Users\admin\Documents\STORM"
$cdnSource = "C:\Users\admin\Documents\STORM V2\snapshots\storm_dashboard_cdn_2026-08-25_w35.html"

Set-Location $repoDir

# Archive current version
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
if (!(Test-Path "dashboard/archive")) { New-Item -ItemType Directory -Path "dashboard/archive" }
if (Test-Path "dashboard/index.html") {
    Copy-Item "dashboard/index.html" "dashboard/archive/index_$timestamp.html"
    Write-Host "Archived old version"
}

# Deploy new W35 version
Copy-Item $cdnSource "dashboard/index.html" -Force
Write-Host "Deployed W35 dashboard"

# Git commit and push
git add -A
git commit -m "W35 update: data through 8/24, Aug Revenue $223.5K YTD $2.98M

Data: STORM V2 RAW DATA 8.25 (Aug full 1226 orders) + 8.19 (Jan-Jul)
Cost: cost detail 8.19 (P&L through 8/17)
Highlights: WoW -18.8%, GM 36.7%, CM 16.7%"
git push origin main
Write-Host "Done! Live at https://ericbigbossxx.github.io/STORM/dashboard/"
