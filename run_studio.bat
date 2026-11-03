@echo off
chcp 65001 >nul
title SHINJUTSU UI — 1-Click Studio Launcher
cd /d "%~dp0"
python setup_and_run.py %*
pause
