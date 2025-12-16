const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

let mainWindow;
let backendProcess;

const BACKEND_PORT = 8000;
const PY_DIST_FOLDER = path.join(__dirname, '../../backend'); // dev path

function startBackend() {
  console.log('Starting Python Backend...');
  // In dev, assume python is in PATH or venv
  // For robustness, users might need to configure this path
  const pythonExecutable = 'python'; 
  const scriptPath = path.join(PY_DIST_FOLDER, 'app.py');

  backendProcess = spawn(pythonExecutable, [scriptPath], {
    cwd: PY_DIST_FOLDER,
    stdio: 'inherit' // Pipe output to console
  });

  backendProcess.on('error', (err) => {
    console.error('Failed to start backend:', err);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    backgroundColor: '#050505',
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false, // For simple IPC if needed, though we use HTTP
    },
    show: false, // Wait until ready to show
  });

  const startUrl = 'http://localhost:5173'; // Vite dev server

  mainWindow.loadURL(startUrl);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('closed', function () {
    mainWindow = null;
  });
}

app.on('ready', () => {
  startBackend();
  createWindow();
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
