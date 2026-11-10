@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .env (
  echo Не найден .env. Скопируй .env.example в .env и заполни настройки.
  pause
  exit /b 1
)
if not exist .venv (
  echo Создаю виртуальное окружение...
  py -3 -m venv .venv
  if errorlevel 1 python -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python bot.py
pause
