#Requires -Version 5.1
<#
.SYNOPSIS
  注册 M2news Windows 任务计划 + 防火墙规则（需以管理员身份运行）
.DESCRIPTION
  方案 B 本地自动化：
  1. 每日 08:00 运行新闻采集管线 (run_once.ps1)
  2. 开机/登录时自动启动 Flask API (start_api.ps1)
  3. 放行 TCP 5000 端口入站（局域网访问）
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ScriptsDir = Join-Path $ProjectRoot "scripts"

Write-Host "=== M2news Windows 任务计划安装 ===" -ForegroundColor Cyan
Write-Host "项目根目录: $ProjectRoot"
Write-Host ""

# --- 1. 每日 08:00 采集任务 ---
$digestTask = "M2news Daily Digest"
$digestAction = "powershell.exe -ExecutionPolicy Bypass -NoProfile -File `"$ScriptsDir\run_once.ps1`""
schtasks /create /tn $digestTask /tr $digestAction /sc daily /st 08:00 /f
Write-Host "[OK] 已注册: $digestTask (每日 08:00)" -ForegroundColor Green

# --- 2. 开机自启 Flask API ---
$flaskTask = "M2news Flask API"
$flaskAction = "powershell.exe -ExecutionPolicy Bypass -NoProfile -File `"$ScriptsDir\start_api.ps1`""
schtasks /create /tn $flaskTask /tr $flaskAction /sc onlogon /f
Write-Host "[OK] 已注册: $flaskTask (登录时自启)" -ForegroundColor Green

# --- 3. 防火墙放行 TCP 5000 ---
$ruleName = "M2news Flask API (TCP 5000)"
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if (-not $existing) {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow -Profile Private,Domain | Out-Null
    Write-Host "[OK] 已创建防火墙规则: $ruleName" -ForegroundColor Green
} else {
    Write-Host "[SKIP] 防火墙规则已存在: $ruleName" -ForegroundColor Yellow
}

# --- 4. 立即启动一次 Flask API（如果未运行） ---
$listening = netstat -ano | Select-String "0.0.0.0:5000"
if (-not $listening) {
    Write-Host "[INFO] Flask 未运行，立即启动..." -ForegroundColor Yellow
    Start-ScheduledTask -TaskName $flaskTask
    Start-Sleep -Seconds 3
    Write-Host "[OK] Flask API 已启动" -ForegroundColor Green
} else {
    Write-Host "[SKIP] Flask API 已在运行" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== 安装完成 ===" -ForegroundColor Cyan
Write-Host "局域网访问: http://10.5.2.31:5000/news/latest"
Write-Host "每日自动刷新: 08:00 (Asia/Shanghai)"
Write-Host ""
Write-Host "管理命令:"
Write-Host "  手动触发采集: schtasks /run /tn `"$digestTask`""
Write-Host "  手动启动API: schtasks /run /tn `"$flaskTask`""
Write-Host "  查看任务状态: schtasks /query /tn `"$digestTask`" /fo list"
Write-Host "  删除任务:     schtasks /delete /tn `"$digestTask`" /f"
