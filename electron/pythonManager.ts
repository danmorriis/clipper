import { ChildProcess, spawn, spawnSync } from 'child_process'
import { randomUUID } from 'crypto'
import { app } from 'electron'
import * as fs from 'fs'
import * as http from 'http'
import * as net from 'net'
import * as path from 'path'

let pythonProcess: ChildProcess | null = null
let apiToken = ''

export function getToken(): string { return apiToken }

function findFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.listen(0, '127.0.0.1', () => {
      const port = (server.address() as net.AddressInfo).port
      server.close(() => resolve(port))
    })
    server.on('error', reject)
  })
}

function waitForReady(port: number, attempts = 60): Promise<void> {
  return new Promise((resolve, reject) => {
    let tries = 0
    const check = () => {
      const req = http.get(`http://127.0.0.1:${port}/healthz`, (res) => {
        if (res.statusCode === 200) {
          resolve()
        } else {
          retry()
        }
      })
      req.on('error', retry)
    }
    const retry = () => {
      tries++
      if (tries >= attempts) {
        reject(new Error('Python API did not start in time'))
      } else {
        setTimeout(check, 200)
      }
    }
    check()
  })
}

export async function startPython(): Promise<number> {
  const port = await findFreePort()
  const isDev = !app.isPackaged
  const isWin = process.platform === 'win32'

  // In packaged mode, prepend bundled bin/ directory so ffmpeg, ffprobe,
  // and fpcalc are found without needing them on the user's PATH.
  apiToken = randomUUID()
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    DJ_CLIPPER_PORT: String(port),
    DJ_CLIPPER_TOKEN: apiToken,
  }
  if (!isDev) {
    const binDir = path.join(
      process.resourcesPath, 'bin',
      isWin ? 'win' : 'mac'
    )
    env.PATH = `${binDir}${path.delimiter}${env.PATH ?? ''}`
  }

  let cmd: string
  let args: string[]

  if (isDev) {

    // Prefer the project .venv so deps are available without manual activation.
    // Falls back to system python if the venv doesn't exist.
    const projectRoot = path.join(__dirname, '..')
    const venvPython = isWin
      ? path.join(projectRoot, '.venv', 'Scripts', 'python.exe')
      : path.join(projectRoot, '.venv', 'bin', 'python3')
    cmd = fs.existsSync(venvPython) ? venvPython : (isWin ? 'python' : 'python3')
    args = ['-m', 'uvicorn', 'api.main:app', '--host', '127.0.0.1', '--port', String(port)]
  } else {
    // Prod: PyInstaller --onedir binary inside resources/dj_clipper_api/
    const binName = isWin ? 'dj_clipper_api.exe' : 'dj_clipper_api'
    cmd = path.join(process.resourcesPath, 'dj_clipper_api', binName)
    args = ['--host', '127.0.0.1', '--port', String(port)]
  }

  const cwd = isDev ? path.join(__dirname, '..') : undefined
  console.log('[python] spawn:', cmd, args.join(' '))
  console.log('[python] cwd:', cwd)

  // On macOS, Gatekeeper quarantines child executables inside unsigned bundles.
  // Strip the quarantine xattr and ensure the binary is executable before spawning.
  if (!isDev && process.platform === 'darwin') {
    spawnSync('xattr', ['-d', 'com.apple.quarantine', cmd])
    spawnSync('chmod', ['+x', cmd])
  }

  pythonProcess = spawn(cmd, args, { env, cwd, stdio: 'pipe' })

  // Accumulate output so we can include it in the timeout error message
  let stderrBuf = ''
  let exitCode: number | null = null

  pythonProcess.stdout?.on('data', (d: Buffer) => {
    const text = d.toString().trimEnd()
    stderrBuf += text + '\n'   // capture stdout too — uvicorn logs go here
    console.log('[python]', text)
  })
  pythonProcess.stderr?.on('data', (d: Buffer) => {
    const text = d.toString().trimEnd()
    stderrBuf += text + '\n'
    console.error('[python]', text)
  })
  pythonProcess.on('error', (err) => {
    stderrBuf += `spawn error: ${err.message}\n`
    console.error('[python] spawn error:', err.message)
  })
  pythonProcess.on('close', (code) => {
    exitCode = code
    if (code !== null && code !== 0) {
      console.error(`[python] exited with code ${code}`)
    }
  })

  try {
    await waitForReady(port)
  } catch {
    throw new Error(
      `Python API did not start in time (port ${port})` +
      (exitCode !== null ? ` — exited with code ${exitCode}` : ' — process still running') +
      '\n\n' +
      (stderrBuf.trim() ? stderrBuf.trim() : '(no output captured — may be blocked by antivirus)')
    )
  }
  return port
}

export function stopPython(): void {
  if (pythonProcess) {
    pythonProcess.kill()
    pythonProcess = null
  }
}
