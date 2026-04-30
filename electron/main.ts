import { app, BrowserWindow, dialog, ipcMain, net, shell } from 'electron'
import * as path from 'path'
import { getToken, startPython, stopPython } from './pythonManager'
import { getLicenseStatus, activateLicense } from './license'

let mainWindow: BrowserWindow | null = null
let apiBase = ''

function createWindow(port: number): void {
  apiBase = `http://127.0.0.1:${port}`

  const isMac = process.platform === 'darwin'

  const isWin = process.platform === 'win32'

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 920,
    minWidth: 1024,
    minHeight: 840,
    titleBarStyle: isMac ? 'hiddenInset' : 'default',
    frame: !isWin,
    backgroundColor: '#c5bfb8',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (process.env.NODE_ENV === 'development' || !app.isPackaged) {
    mainWindow.loadURL('http://localhost:5173')
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }
}

app.whenReady().then(async () => {
  try {
    const port = await startPython()
    createWindow(port)
  } catch (err) {
    console.error('Failed to start Python API:', err)
    if (err instanceof Error && err.message === 'BETA_EXPIRED') {
      dialog.showMessageBoxSync({
        type: 'info',
        title: 'Clip Lab Beta',
        message: 'Thank you so much for testing — the trial is now over! :-)',
        buttons: ['OK'],
      })
    } else {
      dialog.showErrorBox(
        'Startup Error',
        `Could not start the Clip Lab backend.\n\n${err instanceof Error ? err.message : String(err)}`
      )
    }
    app.quit()
  }
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0 && apiBase) {
    const port = parseInt(apiBase.split(':')[2])
    createWindow(port)
  }
})

app.on('before-quit', () => {
  stopPython()
})

// ── IPC handlers ──────────────────────────────────────────────────────────────

ipcMain.handle('api:getBase',  () => apiBase)
ipcMain.handle('api:getToken', () => getToken())

ipcMain.handle('license:getStatus', () => getLicenseStatus())
ipcMain.handle('license:activate',  (_event, key: string) => activateLicense(key))

ipcMain.on('window:minimize', () => mainWindow?.minimize())
ipcMain.on('window:close',    () => mainWindow?.close())

ipcMain.handle('dialog:openFile', async (_event, options: Electron.OpenDialogOptions) => {
  const result = await dialog.showOpenDialog(mainWindow!, options)
  return result.filePaths
})

ipcMain.handle('dialog:openFolder', async () => {
  const result = await dialog.showOpenDialog(mainWindow!, {
    properties: ['openDirectory'],
  })
  return result.filePaths[0] ?? null
})

ipcMain.on('shell:openFolder', (_event, folderPath: string) => {
  shell.openPath(folderPath)
})

ipcMain.on('shell:openUrl', (_event, url: string) => {
  shell.openExternal(url)
})

ipcMain.handle('clipper:submitFeedback', async (_event, text: string, machine: string) => {
  const MACHINE_ENTRY_ID = 'entry.467936750'
  const parts = [`entry.448791064=${encodeURIComponent(text)}`]
  if (machine) parts.push(`${MACHINE_ENTRY_ID}=${encodeURIComponent(machine)}`)
  await net.fetch(
    'https://docs.google.com/forms/d/e/1FAIpQLSfYHYJWEJm5kC0tC1Gf4LsK4TWz1LGt9vIDQ7BI-xlqwU_GwA/formResponse',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: parts.join('&'),
    }
  )
})
