const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

let mainWindow;
let backendProcess;

const BACKEND_PORT = 8000;

// Determine if running in packaged mode
const isPackaged = app.isPackaged;
const PROJECT_ROOT = isPackaged
  ? path.dirname(app.getPath('exe'))
  : path.join(__dirname, '../..');

function startBackend() {
  console.log('Starting Python Backend...');
  const fs = require('fs');

  let executable;
  let args = [];
  let cwd;
  let useShell = false;

  if (isPackaged) {
    // In packaged app, we expect the backend folder to be in resources/backend/mujica_backend/
    const resourcesPath = process.resourcesPath;
    const backendDist = path.join(resourcesPath, 'backend', 'mujica_backend');
    executable = path.join(backendDist, 'mujica_backend.exe');
    cwd = backendDist;

    // Check if backend exe exists
    if (!fs.existsSync(executable)) {
      console.error(`[Backend] ERROR: Backend executable not found at: ${executable}`);
      console.error('[Backend] Please reinstall the application.');
      return;
    }
    console.log(`[Backend] Found backend at: ${executable}`);
  } else {
    // Dev mode - use shell on Windows to find Python in PATH
    executable = process.platform === 'win32' ? 'python' : 'python3';
    args = ['app.py'];
    cwd = path.join(__dirname, '../../backend');
    useShell = process.platform === 'win32'; // Enable shell on Windows
  }

  console.log(`[Backend] Spawning: ${executable} ${args.join(' ')}`);
  console.log(`[Backend] CWD: ${cwd}`);
  console.log(`[Backend] Shell mode: ${useShell}`);
  console.log(`[Backend] Is Packaged: ${isPackaged}`);

  try {
    backendProcess = spawn(executable, args, {
      cwd: cwd,
      stdio: isPackaged ? 'ignore' : 'inherit', // Hide output in packaged mode
      shell: useShell,
      windowsHide: isPackaged, // Only hide window in packaged mode
      detached: false
    });

    backendProcess.on('error', (err) => {
      console.error('[Backend] Failed to start:', err.message);
      console.error('[Backend] Full error:', err);
    });

    backendProcess.on('exit', (code, signal) => {
      console.log(`[Backend] Process exited with code ${code}, signal ${signal}`);
    });

    console.log(`[Backend] Started with PID: ${backendProcess.pid}`);
  } catch (err) {
    console.error('[Backend] Exception while starting:', err);
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    backgroundColor: '#050505',
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#0a0a0c',
      symbolColor: '#c5a059',
      height: 32
    },
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
    show: false,
  });

  // Load appropriate URL based on mode
  if (isPackaged) {
    // Production: load from built files
    mainWindow.loadFile(path.join(__dirname, '../renderer/dist/index.html'));
  } else {
    // Development: load from Vite dev server
    mainWindow.loadURL('http://localhost:5173');
    // Open DevTools in dev mode
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('closed', function () {
    mainWindow = null;
  });
}

app.on('ready', () => {
  startBackend();

  // Wait a moment for backend to start before creating window
  setTimeout(createWindow, 1000);
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', function () {
  if (mainWindow === null) createWindow();
});

app.on('will-quit', () => {
  if (backendProcess) {
    console.log('Killing backend process...');
    backendProcess.kill();
  }
});
