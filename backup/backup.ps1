<#
.SYNOPSIS
    Sauvegarde Time Tracker : zippe le dossier data et en garde une copie datée sur plusieurs disques.

.DESCRIPTION
    1. Copie le dossier data (sans les fichiers temporaires) et le zippe : TimeTracker_AAAA-MM-JJ_HHmm.zip
    2. Copie ce zip dans chaque dossier de $Destinations (par défaut sur D: et sur E:)
    3. Dans chaque dossier, ne garde que les $Keep sauvegardes les plus récentes

    Si une destination est indisponible (disque débranché…), les autres sont quand même
    sauvegardées et l'erreur est notée dans le journal (code de sortie 1).

.EXAMPLE
    .\backup.ps1               # sauvegarde maintenant
    .\backup.ps1 -Install      # planifie une sauvegarde quotidienne (et à l'ouverture de session)
    .\backup.ps1 -Uninstall    # retire la planification
#>
param(
    [string]$DataDir        = "C:\Program Files (x86)\TimeTracker\data",
    [string[]]$Destinations = @("D:\Sauvegardes\TimeTracker", "E:\Sauvegardes\TimeTracker"),
    [int]$Keep              = 30,
    [string]$DailyAt        = "20:00",
    [switch]$Install,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$LogDir   = Join-Path $env:LOCALAPPDATA "TimeTracker-backup"
$LogFile  = Join-Path $LogDir "backup.log"
$TaskName = "Time Tracker - Sauvegarde"

# Fichiers de fonctionnement, inutiles dans une sauvegarde
$Excluded = @("active_sessions.json", "untracked_active.json", "*.tmp")

function Write-Log([string]$msg, [string]$color = "Gray") {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $msg -ForegroundColor $color
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# ── Planification ────────────────────────────────────────────────────────────

if ($Install) {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`""
    $triggers = @(
        (New-ScheduledTaskTrigger -Daily -At $DailyAt),
        (New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME")
    )
    # StartWhenAvailable : si le PC était éteint à l'heure prévue, la sauvegarde se fait au démarrage
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Settings $settings `
        -Description "Zippe les données de Time Tracker et en garde $Keep copies dans : $($Destinations -join ', ')" `
        -Force | Out-Null
    Write-Host "Sauvegarde planifiée : tous les jours à $DailyAt et à l'ouverture de session." -ForegroundColor Green
    return
}

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Planification retirée." -ForegroundColor Green
    return
}

# ── Sauvegarde ───────────────────────────────────────────────────────────────

$staging = $null
$failed  = 0
try {
    if (-not (Test-Path (Join-Path $DataDir "games.json"))) {
        throw "games.json introuvable dans $DataDir : rien à sauvegarder."
    }

    # Copie de travail (sans les fichiers temporaires), puis zip daté
    $stamp   = Get-Date -Format "yyyy-MM-dd_HHmm"
    $staging = Join-Path $env:TEMP "TimeTracker-backup-$stamp"
    Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path "$staging\data" | Out-Null
    Copy-Item -Path (Join-Path $DataDir "*") -Destination "$staging\data" -Recurse -Exclude $Excluded
    Get-ChildItem "$staging\data" -Recurse -File -Include $Excluded | Remove-Item -Force

    # Le zip doit contenir un games.json lisible : sinon on ne remplace pas les bonnes sauvegardes
    $null = Get-Content "$staging\data\games.json" -Raw -Encoding UTF8 | ConvertFrom-Json

    $name = "TimeTracker_$stamp.zip"
    $zip  = Join-Path $staging $name
    Compress-Archive -Path "$staging\data\*" -DestinationPath $zip -Force
    $sizeKo = [math]::Round((Get-Item $zip).Length / 1KB)

    # Une destination en échec n'empêche pas les autres
    foreach ($dest in $Destinations) {
        try {
            New-Item -ItemType Directory -Force -Path $dest | Out-Null
            Copy-Item $zip $dest -Force
            $old = Get-ChildItem $dest -Filter "TimeTracker_*.zip" | Sort-Object Name -Descending | Select-Object -Skip $Keep
            foreach ($f in $old) { Remove-Item $f.FullName -Force }
            $note = if ($old) { " ($(@($old).Count) ancienne(s) supprimée(s))" } else { "" }
            Write-Log "Sauvegardé : $dest\$name ($sizeKo Ko)$note" "Green"
        }
        catch {
            $failed++
            Write-Log "ERREUR sur $dest : $($_.Exception.Message)" "Red"
        }
    }
    if ($failed) { exit 1 }
    exit 0
}
catch {
    Write-Log "ERREUR : $($_.Exception.Message)" "Red"
    exit 1
}
finally {
    if ($staging) { Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue }
}
