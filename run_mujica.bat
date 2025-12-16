@echo off
TITLE MUJICA Electron Launcher

echo ==================================================
echo          MUJICA: SOTA Research Assistant
echo ==================================================

echo [1/3] Checking Python Dependencies...
pip install -r backend/requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install Python dependencies. Please check your python installation.
    pause
    exit /b %ERRORLEVEL%
)

echo [2/3] Checking Node Dependencies...
cd electron-app
if not exist node_modules (
    echo Installing Electron dependencies...
    npm install
)
cd renderer
if not exist node_modules (
    echo Installing Renderer dependencies...
    npm install
)
cd ..

echo [3/3] Starting Application...
echo Please ensure you have configured your .env file or API Keys in the settings.
npm start

pause
