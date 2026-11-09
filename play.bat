@echo off
rem Open the game directly (for manual play, NOT the farming bot)
setlocal
set "PROFILE=%~dp0profile"
set "URL=https://nijitama.app/switchSession/tamacolle"
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" goto nochrome
if not exist "%PROFILE%" goto noprofile
start "" "%CHROME%" --no-sandbox --no-first-run --no-default-browser-check --user-data-dir="%PROFILE%" --window-size=1200,720 --window-position=120,40 --ignore-gpu-blocklist --enable-gpu --use-angle=d3d11 "%URL%"
exit /b 0

:nochrome
echo Chrome not found. Install Chrome, or run:
echo   python -m playwright install chromium
pause
exit /b 1

:noprofile
echo Profile folder not found: %PROFILE%
echo Start the toolbox once to create it, then log in.
pause
exit /b 1