# xCLICK Chrome Launcher (PowerShell)
# Launches Chrome with correct viewport size and debugging enabled

$VIEWPORT_WIDTH = 1280
$VIEWPORT_HEIGHT = 720
$CHROME_HEIGHT_OFFSET = 85
$WINDOW_WIDTH = $VIEWPORT_WIDTH
$WINDOW_HEIGHT = $VIEWPORT_HEIGHT + $CHROME_HEIGHT_OFFSET

Write-Host "Starting Chrome with viewport ${VIEWPORT_WIDTH}x${VIEWPORT_HEIGHT}" -ForegroundColor Green
Write-Host "Window size: ${WINDOW_WIDTH}x${WINDOW_HEIGHT}" -ForegroundColor Yellow

# Kill existing Chrome instances connected to debug port
Get-Process chrome -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*remote-debugging-port*" } | Stop-Process -Force -ErrorAction SilentlyContinue

Start-Sleep -Milliseconds 500

# Find Chrome executable
$chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
if (-not (Test-Path $chromePath)) {
    $chromePath = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
}

if (-not (Test-Path $chromePath)) {
    Write-Host "Chrome not found! Please install Chrome or update the path." -ForegroundColor Red
    exit 1
}

# Launch Chrome
& $chromePath `
  --remote-debugging-port=9222 `
  --window-size=${WINDOW_WIDTH},${WINDOW_HEIGHT} `
  --user-data-dir="$env:TEMP\ChromeDebug" `
  --disable-gpu-vsync `
  --disable-blink-features=AutomationControlled

Write-Host "`nChrome launched on port 9222" -ForegroundColor Green
Write-Host "`nNow run: python xclick.py --vision" -ForegroundColor Cyan
