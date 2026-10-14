# EchoVault 一键启动（Windows PowerShell）
# 用法：右键"使用 PowerShell 运行"，或 cd 到项目目录后执行 .\run.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# 检测 8848 端口是否已被占用（服务已在运行）
$inUse = Get-NetTCPConnection -LocalPort 8848 -State Listen -ErrorAction SilentlyContinue
if ($inUse) {
    Write-Host "EchoVault 服务已经在运行了，直接打开浏览器访问：" -ForegroundColor Green
    Write-Host "  http://localhost:8848" -ForegroundColor Cyan
    Write-Host "（如果打不开，说明占用了 8848 端口的不是本服务，先关掉那个程序再试）" -ForegroundColor Yellow
    Read-Host "按回车键关闭此窗口"
    exit 0
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "首次运行：创建虚拟环境并安装依赖..." -ForegroundColor Cyan
    python -m venv .venv
    & ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "server\requirements.txt"
}

try {
    Write-Host "启动 EchoVault... 浏览器打开 http://localhost:8848" -ForegroundColor Cyan
    Write-Host "手机（同一 Wi-Fi）访问 http://<本机IP>:8848，ipconfig 可查看 IP" -ForegroundColor Cyan
    Write-Host "【关闭本窗口 = 停止服务】" -ForegroundColor Yellow
    & ".venv\Scripts\python.exe" -m uvicorn server.app:app --host 0.0.0.0 --port 8848
} catch {
    Write-Host "启动失败：" -ForegroundColor Red
    Write-Host $_
    Read-Host "按回车键关闭此窗口"
}
