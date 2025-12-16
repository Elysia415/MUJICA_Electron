@echo off
TITLE MUJICA Electron Launcher

echo ==================================================
echo          MUJICA: SOTA Research Assistant
echo ==================================================

echo [1/4] Checking Python Dependencies...
pip install -r backend/requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install Python dependencies. Please check your python installation.
    pause
    exit /b %ERRORLEVEL%
)

echo [2/4] Starting Python Backend...
start "MUJICA Backend" cmd /k "cd /d %~dp0backend && python app.py"

echo Waiting for backend to start...
timeout /t 3 /nobreak > nul

echo [3/4] Checking Node Dependencies...
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

echo [4/4] Starting Electron Application...
echo Please ensure you have configured your .env file or API Keys in the settings.
npm run dev

pause
