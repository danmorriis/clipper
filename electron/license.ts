/**
 * License management for Clip Lab.
 *
 * Architecture:
 *  - Trial: tracked via Supabase (machine first_seen date). 8-day rolling trial.
 *  - License: key validated against Supabase licenses table.
 *  - Cache: local file with HMAC so any edit invalidates it and forces online check.
 *  - Offline: cache used if still valid; no-expiry licenses never lock out offline.
 *
 * Supabase setup (run once):
 *   create table machines (
 *     machine_id text primary key,
 *     first_seen date not null default current_date
 *   );
 *   create table licenses (
 *     id uuid primary key default gen_random_uuid(),
 *     key text unique not null,
 *     user_name text,
 *     expiry date,
 *     tag text,
 *     machine_id text,
 *     activated_at timestamptz
 *   );
 *   -- Enable RLS on both tables, then add policies:
 *   -- machines: allow insert/select for anon
 *   -- licenses: allow select/update for anon
 */

import { app } from 'electron'
import * as crypto from 'crypto'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { spawnSync } from 'child_process'

// ── Config — fill in once Supabase is set up ─────────────────────────────────
const SUPABASE_URL       = 'https://dnvtnjhxfccrhmsbimey.supabase.co'
const SUPABASE_ANON_KEY  = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRudnRuamh4ZmNjcmhtc2JpbWV5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc1NDY3OTYsImV4cCI6MjA5MzEyMjc5Nn0.l1rhsuEXOcsjKmSKSW6lJp0tCjo3pdgfZJ5ZIODf5VY'

// Embedded in the binary — protects cache against casual editing.
// Change this before distributing to anyone.
const HMAC_SECRET = 'cl-v1-3f8a2b9d1e4c7f0a5b8e2d6c9f3a7b4e'

const TRIAL_DAYS     = 7
const CACHE_TTL_DAYS = 7

const SUPABASE_CONFIGURED = !!(SUPABASE_URL && SUPABASE_ANON_KEY)

// ── Types ─────────────────────────────────────────────────────────────────────

export type LicenseStatus =
  | { status: 'trial';         daysLeft: number }
  | { status: 'licensed';      tag: string | null; daysLeft: number | null }
  | { status: 'expired' }
  | { status: 'offline_locked' }

interface CacheData {
  machine_id:        string
  first_seen:        string        // YYYY-MM-DD
  license_key:       string | null
  license_expiry:    string | null  // YYYY-MM-DD or null
  license_tag:       string | null
  cached_at:         string         // ISO timestamp
  cache_valid_until: string         // ISO timestamp
  hmac:              string
}

type CachePayload = Omit<CacheData, 'hmac'>

// ── Machine ID ────────────────────────────────────────────────────────────────

function getMachineId(): string {
  try {
    if (process.platform === 'darwin') {
      const result = spawnSync('system_profiler', ['SPHardwareDataType'], { timeout: 5000 })
      const out = result.stdout?.toString() ?? ''
      const match = out.match(/Hardware UUID:\s+([A-F0-9-]+)/i)
      if (match?.[1]) {
        return crypto.createHash('sha256').update(match[1]).digest('hex').slice(0, 32)
      }
    } else if (process.platform === 'win32') {
      const result = spawnSync('reg', [
        'query', 'HKLM\\SOFTWARE\\Microsoft\\Cryptography', '/v', 'MachineGuid'
      ], { timeout: 5000 })
      const out = result.stdout?.toString() ?? ''
      const match = out.match(/MachineGuid\s+REG_SZ\s+([a-f0-9-]+)/i)
      if (match?.[1]) {
        return crypto.createHash('sha256').update(match[1]).digest('hex').slice(0, 32)
      }
    }
  } catch {}
  // Fallback: hostname + platform (weaker, but always available)
  return crypto.createHash('sha256').update(os.hostname() + process.platform).digest('hex').slice(0, 32)
}

// ── Cache ─────────────────────────────────────────────────────────────────────

function getCachePath(): string {
  return path.join(app.getPath('userData'), 'license_cache.json')
}

function computeHmac(payload: CachePayload): string {
  // Sort keys for stable serialisation — any field edit changes the HMAC.
  const keys = Object.keys(payload).sort() as (keyof CachePayload)[]
  const ordered: Partial<CachePayload> = {}
  for (const k of keys) (ordered as any)[k] = payload[k]
  return crypto.createHmac('sha256', HMAC_SECRET).update(JSON.stringify(ordered)).digest('hex')
}

function readCache(): CachePayload | null {
  try {
    const raw    = fs.readFileSync(getCachePath(), 'utf-8')
    const parsed = JSON.parse(raw) as CacheData
    const { hmac, ...payload } = parsed

    const expected = computeHmac(payload)
    // timingSafeEqual requires equal-length buffers
    const a = Buffer.from(hmac,     'hex')
    const b = Buffer.from(expected, 'hex')
    if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
      console.warn('[license] cache HMAC mismatch — discarding')
      return null
    }
    return payload
  } catch {
    return null
  }
}

function writeCache(payload: CachePayload): void {
  const full: CacheData = { ...payload, hmac: computeHmac(payload) }
  fs.writeFileSync(getCachePath(), JSON.stringify(full, null, 2), 'utf-8')
}

// ── Date helpers ──────────────────────────────────────────────────────────────

function todayStr(): string {
  return new Date().toISOString().slice(0, 10)
}

function addDays(iso: string, days: number): string {
  const d = new Date(iso)
  d.setDate(d.getDate() + days)
  return d.toISOString()
}

/** Positive = to is in the future; negative = to is in the past. */
function daysUntil(to: string): number {
  const now = new Date(); now.setHours(0, 0, 0, 0)
  const end = new Date(to); end.setHours(0, 0, 0, 0)
  return Math.ceil((end.getTime() - now.getTime()) / 86_400_000)
}

function isCacheStillValid(c: CachePayload): boolean {
  // No-expiry licenses are never locked out offline.
  if (c.license_key && c.license_expiry === null) return true
  return new Date() < new Date(c.cache_valid_until)
}

// ── Status calculation from cache ─────────────────────────────────────────────

function calcStatus(c: CachePayload): LicenseStatus {
  if (c.license_key) {
    if (c.license_expiry === null) {
      return { status: 'licensed', tag: c.license_tag, daysLeft: null }
    }
    const dl = daysUntil(c.license_expiry)
    if (dl > 0) return { status: 'licensed', tag: c.license_tag, daysLeft: dl }
    return { status: 'expired' }
  }

  const trialDaysUsed = -daysUntil(c.first_seen)   // positive = days elapsed since first_seen
  const trialLeft     = TRIAL_DAYS - trialDaysUsed
  if (trialLeft > 0) return { status: 'trial', daysLeft: trialLeft }
  return { status: 'expired' }
}

// ── Supabase REST client ──────────────────────────────────────────────────────

async function sbFetch(
  method: string,
  table: string,
  opts: {
    filter?: Record<string, string>
    body?: object
    prefer?: string
  } = {}
): Promise<any> {
  const params = new URLSearchParams()
  if (opts.filter) {
    for (const [k, v] of Object.entries(opts.filter)) params.set(k, `eq.${v}`)
  }

  const url = `${SUPABASE_URL}/rest/v1/${table}${params.toString() ? '?' + params : ''}`
  const headers: Record<string, string> = {
    'apikey':        SUPABASE_ANON_KEY,
    'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
    'Content-Type':  'application/json',
    'Accept':        'application/json',
  }
  if (opts.prefer) headers['Prefer'] = opts.prefer

  const res = await fetch(url, {
    method,
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Supabase ${method} ${table}: ${res.status} ${text}`)
  }
  const text = await res.text()
  if (!text) return null
  return JSON.parse(text)
}

// ── Online sync ───────────────────────────────────────────────────────────────

async function syncOnline(machineId: string, licenseKey: string | null): Promise<CachePayload> {
  // Register machine — ignore if already exists (DO NOTHING on conflict).
  await sbFetch('POST', 'machines', {
    body:   { machine_id: machineId, first_seen: todayStr() },
    prefer: 'resolution=ignore-duplicates',
  })

  // Fetch the authoritative first_seen date.
  const [machineRow] = await sbFetch('GET', 'machines', {
    filter: { machine_id: machineId },
  })
  const firstSeen: string = machineRow?.first_seen ?? todayStr()

  // Validate license key if present.
  // If no local key, check Supabase for a license already claimed by this machine
  // (recovers from cache loss/tampering without requiring re-activation).
  let validKey:    string | null = null
  let licExpiry:   string | null = null
  let licTag:      string | null = null

  const keyToCheck = licenseKey ?? await (async () => {
    const claimed = await sbFetch('GET', 'licenses', { filter: { machine_id: machineId } })
    return claimed?.[0]?.key ?? null
  })()

  if (keyToCheck) {
    const rows = await sbFetch('GET', 'licenses', { filter: { key: keyToCheck } })
    const row  = rows?.[0]
    if (row) {
      const claimedBy: string | null = row.machine_id ?? null
      if (!claimedBy || claimedBy === machineId) {
        // Claim if not yet claimed.
        if (!claimedBy) {
          await sbFetch('PATCH', 'licenses', {
            filter: { key: keyToCheck },
            body:   { machine_id: machineId, activated_at: new Date().toISOString() },
            prefer: 'return=representation',
          })
        }
        validKey  = keyToCheck
        licExpiry = row.expiry ?? null
        licTag    = row.tag    ?? null
      }
      // Key claimed by a different machine — treat as unlicensed.
    }
  }

  // Calculate cache_valid_until.
  let cacheValidUntil: string
  if (validKey && licExpiry === null) {
    // Permanently licensed — far future sentinel.
    cacheValidUntil = '2099-12-31T00:00:00.000Z'
  } else if (validKey && licExpiry) {
    // Grace period after license expiry.
    cacheValidUntil = addDays(licExpiry, CACHE_TTL_DAYS)
  } else {
    // Trial: 7 days from now.
    cacheValidUntil = addDays(new Date().toISOString(), CACHE_TTL_DAYS)
  }

  return {
    machine_id:        machineId,
    first_seen:        firstSeen,
    license_key:       validKey,
    license_expiry:    licExpiry,
    license_tag:       licTag,
    cached_at:         new Date().toISOString(),
    cache_valid_until: cacheValidUntil,
  }
}

// ── Public API (called from main.ts IPC handlers) ─────────────────────────────

export async function getLicenseStatus(): Promise<LicenseStatus> {
  // Dev mode: always licensed so you can work without Supabase.
  if (!app.isPackaged) {
    return { status: 'licensed', tag: 'DEV', daysLeft: null }
  }

  // Supabase not yet configured — safe fallback so the app still runs.
  if (!SUPABASE_CONFIGURED) {
    return { status: 'trial', daysLeft: TRIAL_DAYS }
  }

  const machineId = getMachineId()
  const cache     = readCache()

  // Try to sync with Supabase (refreshes cache).
  try {
    const fresh = await syncOnline(machineId, cache?.license_key ?? null)
    writeCache(fresh)
    return calcStatus(fresh)
  } catch (err) {
    console.warn('[license] offline or Supabase error:', (err as Error).message)
  }

  // Offline fallback.
  if (cache && isCacheStillValid(cache)) {
    return calcStatus(cache)
  }

  // Cache missing or expired — user must go online.
  return { status: 'offline_locked' }
}

export async function activateLicense(key: string): Promise<{ success: boolean; error?: string }> {
  if (!SUPABASE_CONFIGURED) {
    return { success: false, error: 'License server not configured.' }
  }

  const machineId = getMachineId()

  try {
    const rows = await sbFetch('GET', 'licenses', { filter: { key } })
    const row  = rows?.[0]

    if (!row) {
      return { success: false, error: 'Invalid license key.' }
    }
    const claimedBy: string | null = row.machine_id ?? null
    if (claimedBy && claimedBy !== machineId) {
      return { success: false, error: 'This key is already activated on another device.' }
    }

    // Claim the key.
    if (!claimedBy) {
      await sbFetch('PATCH', 'licenses', {
        filter: { key },
        body:   { machine_id: machineId, activated_at: new Date().toISOString() },
        prefer: 'return=representation',
      })
    }

    // Ensure machine is registered.
    await sbFetch('POST', 'machines', {
      body:   { machine_id: machineId, first_seen: todayStr() },
      prefer: 'resolution=ignore-duplicates',
    })
    const [machineRow] = await sbFetch('GET', 'machines', { filter: { machine_id: machineId } })

    const licExpiry: string | null = row.expiry ?? null
    const licTag:    string | null = row.tag    ?? null

    let cacheValidUntil: string
    if (licExpiry === null) {
      cacheValidUntil = '2099-12-31T00:00:00.000Z'
    } else {
      cacheValidUntil = addDays(licExpiry, CACHE_TTL_DAYS)
    }

    writeCache({
      machine_id:        machineId,
      first_seen:        machineRow?.first_seen ?? todayStr(),
      license_key:       key,
      license_expiry:    licExpiry,
      license_tag:       licTag,
      cached_at:         new Date().toISOString(),
      cache_valid_until: cacheValidUntil,
    })

    return { success: true }
  } catch (err) {
    console.error('[license] activateLicense error:', err)
    return { success: false, error: 'Could not connect to license server. Check your internet connection.' }
  }
}
