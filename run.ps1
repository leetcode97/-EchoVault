# 🏆 EchoVault 一键启动（Windows PowerShell）
# 用法：右键“使用 PowerShell 运行”，或 cd 到项目目录后执行 .\run.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "首次运行：创建虚拟环境并安装依赖…" -ForegroundColor Cyan
    python -m venv .venv
    & ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "server\requirements.txt"
}

Write-Host "启动 EchoVault… 浏览器打开 http://localhost:8000" -ForegroundColor Cyan
& ".venv\Scripts\python.exe" -m uvicorn server.app:app --host 0.0.0.0 --port 8000
