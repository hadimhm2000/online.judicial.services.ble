# ===========================================================
# اسکریپت اعمال فایل‌های اصلاحی پنل ادمین
# فایل‌های اصلاح‌شده: cases-table.tsx و admin-panel.tsx
# ===========================================================

$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\apps\judicial-bot"

# مسیر فایل‌های مقصد
$casesTableDest = Join-Path $ProjectRoot "src\components\admin\cases-table.tsx"
$adminPanelDest = Join-Path $ProjectRoot "src\components\admin\admin-panel.tsx"

# مسیر فایل‌های منبع (در کنار این اسکریپت)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$casesTableSrc = Join-Path $ScriptDir "..\src\components\admin\cases-table.tsx"
$adminPanelSrc = Join-Path $ScriptDir "..\src\components\admin\admin-panel.tsx"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  اعمال فایل‌های اصلاحی پنل ادمین" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── بررسی وجود فایل‌های منبع ──
if (-not (Test-Path $casesTableSrc)) {
    Write-Host "[خطا] فایل منبع cases-table.tsx یافت نشد: $casesTableSrc" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $adminPanelSrc)) {
    Write-Host "[خطا] فایل منبع admin-panel.tsx یافت نشد: $adminPanelSrc" -ForegroundColor Red
    exit 1
}

# ── بررسی وجود پروژه ──
if (-not (Test-Path $ProjectRoot)) {
    Write-Host "[خطا] مسیر پروژه یافت نشد: $ProjectRoot" -ForegroundColor Red
    Write-Host "لطفا مسیر ProjectRoot را در اسکریپت اصلاح کنید." -ForegroundColor Yellow
    exit 1
}

# ── ایجاد پشتیبان ──
$BackupDir = Join-Path $ProjectRoot "backups\admin-fix-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

if (Test-Path $casesTableDest) {
    Copy-Item $casesTableDest (Join-Path $BackupDir "cases-table.tsx.bak")
    Write-Host "[پشتیبان] cases-table.tsx" -ForegroundColor DarkGray
}
if (Test-Path $adminPanelDest) {
    Copy-Item $adminPanelDest (Join-Path $BackupDir "admin-panel.tsx.bak")
    Write-Host "[پشتیبان] admin-panel.tsx" -ForegroundColor DarkGray
}
Write-Host ""

# ── کپی فایل ۱: cases-table.tsx ──
Write-Host "[1/2] جایگزینی cases-table.tsx ..." -ForegroundColor Yellow
Copy-Item -Path $casesTableSrc -Destination $casesTableDest -Force
Write-Host "       ... انجام شد." -ForegroundColor Green

# ── کپی فایل ۲: admin-panel.tsx ──
Write-Host "[2/2] جایگزینی admin-panel.tsx ..." -ForegroundColor Yellow
Copy-Item -Path $adminPanelSrc -Destination $adminPanelDest -Force
Write-Host "       ... انجام شد." -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  هر دو فایل با موفقیت جایگزین شدند!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "فایل‌های پشتیبان در: $BackupDir" -ForegroundColor DarkGray
Write-Host ""
Write-Host "تغییرات اعمال‌شده:" -ForegroundColor Cyan
Write-Host "  - cases-table.tsx: نمایش '—' برای ستون امضا در استعلام‌ها (INQUIRY)" -ForegroundColor White
Write-Host "  - admin-panel.tsx: جداسازی استعلام‌ها از تب‌های پنل ادمین (excludeInquiry)" -ForegroundColor White
Write-Host ""
