@echo off
REM ============================================================
REM  Build PreprodTestTool.exe  (one-folder build, recommended)
REM  Output: dist\PreprodTestTool\PreprodTestTool.exe
REM ============================================================
pip install -r requirements.txt
pyinstaller --noconfirm build.spec
echo.
echo Build finished. See dist\PreprodTestTool\PreprodTestTool.exe
pause
