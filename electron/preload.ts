import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electronAPI', {
  openFileDialog: (options: Electron.OpenDialogOptions): Promise<string[]> =>
    ipcRenderer.invoke('dialog:openFile', options),

  openFolderDialog: (): Promise<string | null> =>
    ipcRenderer.invoke('dialog:openFolder'),

  openFolder: (folderPath: string): void =>
    ipcRenderer.send('shell:openFolder', folderPath),

  getApiBase: (): Promise<string> =>
    ipcRenderer.invoke('api:getBase'),

  getToken: (): Promise<string> =>
    ipcRenderer.invoke('api:getToken'),

  platform: (): string => process.platform,
})
