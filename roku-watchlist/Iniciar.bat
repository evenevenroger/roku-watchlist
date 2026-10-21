@echo off
rem Garante que o servidor está ligado (sem janela) e abre a página.
rem Se ele já estiver rodando, a segunda cópia sai sozinha (porta em uso).
cd /d "%~dp0"
wscript.exe "%~dp0IniciarOculto.vbs"
timeout /t 2 /nobreak >nul
start "" http://localhost:8790
