@echo off
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat

if "%DATABASE_URL%"=="" (
  echo ERRO: Defina DATABASE_URL antes de executar.
  echo Exemplo: set DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/turismob2b
  exit /b 1
)

python migrate_sqlite_to_postgres.py
