@echo off
rem Build the distributable zip (exe + sample + docs). Output: dist\KiyakuNote-<version>-win.zip
cd /d "%~dp0"
python build_release.py
if errorlevel 1 (
  echo.
  echo Build failed. Check that Python and PyInstaller are installed.
)
pause
