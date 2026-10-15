@echo off
rem Construye el ejecutable de Windows en dist\Nesting2D\ (desde la carpeta del proyecto).
rem Requisitos: el entorno virtual creado como dice el README.
call .venv\Scripts\activate || goto :error
pip install -e .[gui] pyinstaller || goto :error
pyinstaller --noconfirm packaging\nesting2d.spec || goto :error
dist\Nesting2D\nesting2d-cli.exe autoprueba || goto :error
echo.
echo Listo: dist\Nesting2D\Nesting2D.exe
goto :eof
:error
echo.
echo ERROR al construir. Revisa los mensajes de arriba.
exit /b 1
