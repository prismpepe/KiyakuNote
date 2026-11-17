@echo off
rem Build the GUI as an exe (details: build_exe.py), then start it. Output: app\
cd /d "%~dp0"
python build_exe.py --run
if errorlevel 1 (
  echo.
  echo Build failed. Check that Python and PyInstaller are installed.
  pause
)
