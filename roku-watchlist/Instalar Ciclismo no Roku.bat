@echo off
rem Envia o canal mais recente ao Roku (a senha fica em roku_senha.txt).
cd /d "%~dp0"
set PAUSE_AT_END=1
python tools\instalar_no_roku.py ciclismo
