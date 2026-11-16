import type { Profile } from '../components/Layout'

const profileKey = 'alfa.profile.v1'
const requestKey = 'alfa.request.v1'

export function loadProfile(): Profile | null {
  try {
    const raw = sessionStorage.getItem(profileKey)
    if (!raw) return null
    const value: unknown = JSON.parse(raw)
    if (!value || typeof value !== 'object') return null
    const p = value as Record<string, unknown>
    if (typeof p.goal !== 'string' || p.goal.trim().length < 5 || p.goal.length > 300 ||
      typeof p.industry !== 'string' || typeof p.stage !== 'string' || typeof p.experience !== 'string') return null
    return { goal: p.goal, industry: p.industry, stage: p.stage, experience: p.experience }
  } catch { return null }
}

export function saveProfile(profile: Profile | null): void {
  try {
    if (profile) sessionStorage.setItem(profileKey, JSON.stringify(profile))
    else sessionStorage.removeItem(profileKey)
    // Keep the key for identical inputs, including a retry after refresh.
    const saved = sessionStorage.getItem(requestKey)
    if (!profile || (saved && JSON.parse(saved).input !== JSON.stringify(profile))) sessionStorage.removeItem(requestKey)
  } catch { /* The interface remains usable when storage is disabled. */ }
}

export function requestKeyForProfile(input: string): string {
  try {
    const raw = sessionStorage.getItem(requestKey)
    if (raw) {
      const saved = JSON.parse(raw)
      if (saved.input === input && typeof saved.key === 'string' && /^[0-9a-f-]{36}$/i.test(saved.key)) return saved.key
    }
    const key = crypto.randomUUID()
    sessionStorage.setItem(requestKey, JSON.stringify({ input, key }))
    return key
  } catch { return crypto.randomUUID() }
}
