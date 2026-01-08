# Kill processes on port 8010
$processes = Get-NetTCPConnection -LocalPort 8010 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
foreach ($pid in $processes) {
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

# Start new server
Set-Location C:\Projetos\license-server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
