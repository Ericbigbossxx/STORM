# STORM V2 W38 (2026-09-14) — GitHub Push Script
# Run from: C:\Users\admin\Documents\STORM V2

$ErrorActionPreference = "Stop"
$repoDir = "C:\Users\admin\Documents\STORM V2"
$dashDir = "$repoDir\dashboard"
$cdnFile = "$repoDir\snapshots\storm_dashboard_cdn_2026-09-14_w38.html"

Set-Location $repoDir

# 1. Archive current index.html
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
if (Test-Path "$dashDir\index.html") {
    Copy-Item "$dashDir\index.html" "$dashDir\index_backup_$timestamp.html"
    Write-Host "[OK] Archived current index.html -> index_backup_$timestamp.html" -ForegroundColor Green
}

# 2. Deploy CDN version as new index.html
Copy-Item $cdnFile "$dashDir\index.html" -Force
Write-Host "[OK] Deployed W38 (9/14) CDN version as dashboard/index.html" -ForegroundColor Green

# 3. Git add, commit, push
git add -A
git status
git commit -m "W38 (2026-09-14): Sep MTD Rev $179K, CM 15.9%, Conclusions enabled"
git push origin main

Write-Host ""
Write-Host "=== PUSH COMPLETE ===" -ForegroundColor Cyan
Write-Host "Live at: https://ericbigbossxx.github.io/STORM/dashboard/" -ForegroundColor Cyan
