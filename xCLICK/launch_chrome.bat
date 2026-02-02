@echo off
REM xCLICK Chrome Launcher
REM Launches Chrome with correct viewport size and debugging enabled

REM Import config
set VIEWPORT_WIDTH=1280
set VIEWPORT_HEIGHT=720
set CHROME_HEIGHT_OFFSET=85
set /A WINDOW_WIDTH=%VIEWPORT_WIDTH%
set /A WINDOW_HEIGHT=%VIEWPORT_HEIGHT% + %CHROME_HEIGHT_OFFSET%

echo Starting Chrome with viewport %VIEWPORT_WIDTH%x%VIEWPORT_HEIGHT%
echo Window size: %WINDOW_WIDTH%x%WINDOW_HEIGHT%

REM Launch Chrome
start chrome.exe ^
  --remote-debugging-port=9222 ^
  --window-size=%WINDOW_WIDTH%,%WINDOW_HEIGHT% ^
  --user-data-dir=C:\ChromeDebug ^
  --disable-gpu-vsync ^
  --disable-blink-features=AutomationControlled

echo Chrome launched on port 9222
echo.
echo Now run: python xclick.py --vision
