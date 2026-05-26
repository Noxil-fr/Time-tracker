Set-Location $PSScriptRoot

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Time Tracker - Build complet"           -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. PyInstaller ──────────────────────────────────────────────────────────
Write-Host "[1/2] PyInstaller..." -ForegroundColor Yellow
python -m PyInstaller --clean --noconfirm TimeTracker.spec
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERREUR : PyInstaller a echoue (code $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}

# Verification : les fichiers web source sont bien dans dist/
foreach ($f in @("app.js", "app.css", "index.html")) {
    $src  = "web\$f"
    $dist = "dist\TimeTracker\_internal\web\$f"
    if (-not (Test-Path $dist)) {
        Write-Host "ERREUR : $dist absent apres PyInstaller !" -ForegroundColor Red
        exit 1
    }
    $srcHash  = (Get-FileHash $src  -Algorithm MD5).Hash
    $distHash = (Get-FileHash $dist -Algorithm MD5).Hash
    if ($srcHash -ne $distHash) {
        Write-Host "ERREUR : $dist != $src (hash different) !" -ForegroundColor Red
        Write-Host "  Source : $srcHash"
        Write-Host "  Dist   : $distHash"
        exit 1
    }
    Write-Host "  OK  $f" -ForegroundColor Green
}
Write-Host ""

# ── 2. Inno Setup ───────────────────────────────────────────────────────────
Write-Host "[2/2] Inno Setup..." -ForegroundColor Yellow
$iscc = $null
foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
    $candidate = "$base\Inno Setup 6\ISCC.exe"
    if (Test-Path $candidate) { $iscc = $candidate; break }
}
if (-not $iscc) {
    Write-Host "ERREUR : Inno Setup 6 introuvable." -ForegroundColor Red
    exit 1
}

& $iscc installer\TimeTracker.iss
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERREUR : Inno Setup a echoue (code $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}

$output = "installer\Output\TimeTracker_Setup_v1.0.exe"
$size   = [math]::Round((Get-Item $output).Length / 1MB, 1)
$built  = (Get-Item $output).LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")

Write-Host ""
Write-Host "=========================================" -ForegroundColor Green
Write-Host "  Build termine !"                        -ForegroundColor Green
Write-Host "  $output"                                -ForegroundColor White
Write-Host "  Taille : ${size} MB   Date : $built"   -ForegroundColor White
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""
