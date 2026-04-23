/**
 * electron-builder afterSign hook.
 * Notarizes the macOS .app with Apple's notarytool.
 *
 * Runs automatically after code signing during `npm run dist:mac`.
 * Silently skips if APPLE_ID is not set (local dev / Windows builds).
 *
 * Required env vars (set in CI secrets or locally):
 *   APPLE_ID                    — your Apple ID email
 *   APPLE_APP_SPECIFIC_PASSWORD — app-specific password from appleid.apple.com
 *   APPLE_TEAM_ID               — 10-char team ID from developer.apple.com
 */

const { notarize } = require('@electron/notarize')
const path = require('path')

module.exports = async function (params) {
  if (process.platform !== 'darwin') return
  if (!process.env.APPLE_ID) {
    console.log('  Skipping notarization — APPLE_ID not set')
    return
  }

  const appName = params.packager.appInfo.productFilename
  const appPath = path.join(params.appOutDir, `${appName}.app`)

  console.log(`  Notarizing ${appPath}…`)

  await notarize({
    tool: 'notarytool',
    appPath,
    appleId: process.env.APPLE_ID,
    appleIdPassword: process.env.APPLE_APP_SPECIFIC_PASSWORD,
    teamId: process.env.APPLE_TEAM_ID,
  })

  console.log('  Notarization complete.')
}
