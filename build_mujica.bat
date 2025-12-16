@echo off
TITLE MUJICA One-Click Builder

echo ==================================================
echo          MUJICA: One-Click Packaging
echo ==================================================
echo.

:: 1. Build Backend
echo [1/2] Building Python Backend (PyInstaller)...
cd backend
pip install pyinstaller
pyinstaller mujica_backend.spec --clean --noconfirm
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Backend packaging failed!
    pause
    exit /b %ERRORLEVEL%
)
cd ..

:: 2. Build Frontend & Electron
echo.
echo [2/2] Building Electron App...
cd electron-app
if not exist node_modules (
    echo Installing dependencies...
    call npm install
)

:: Ensure renderer is built
cd renderer
if not exist node_modules (
    call npm install
)
call npm run build
cd ..

:: Package everything
echo Packaging Installer...
call npm run dist

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Electron packaging failed!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ==================================================
echo          BUILD SUCCESSFUL!
echo ==================================================
echo Installer is located at:
echo %~dp0electron-app\release\
echo.
pause
