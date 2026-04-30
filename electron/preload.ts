import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electronAPI', {
  openFileDialog: (options: Electron.OpenDialogOptions): Promise<string[]> =>
    ipcRenderer.invoke('dialog:openFile', options),

  openFolderDialog: (): Promise<string | null> =>
    ipcRenderer.invoke('dialog:openFolder'),

  openFolder: (folderPath: string): void =>
    ipcRenderer.send('shell:openFolder', folderPath),

  openUrl: (url: string): void =>
    ipcRenderer.send('shell:openUrl', url),

  submitFeedback: (text: string): Promise<void> =>
    ipcRenderer.invoke('clipper:submitFeedback', text),

  getApiBase: (): Promise<string> =>
    ipcRenderer.invoke('api:getBase'),

  getToken: (): Promise<string> =>
    ipcRenderer.invoke('api:getToken'),

  platform: (): string => process.platform,

  getLicenseStatus: (): Promise<import('./license').LicenseStatus> =>
    ipcRenderer.invoke('license:getStatus'),

  activateLicense: (key: string): Promise<{ success: boolean; error?: string }> =>
    ipcRenderer.invoke('license:activate', key),
})
