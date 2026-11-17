@echo off
rem Start the GUI (Python required). Same as double-clicking the .pyw file.
cd /d "%~dp0"
start "" pythonw -m kiyakunote gui
