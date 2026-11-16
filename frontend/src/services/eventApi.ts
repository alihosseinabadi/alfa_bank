import { getCsrfToken, RecommendationApiError } from './recommendationApi'

const baseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const outboxKey = 'alfa-event-outbox-v1'
const maxPending = 100
const maxAgeMs = 7 * 24 * 60 * 60 * 1000
const allowedPaths = new Set(['visibility', 'action', 'unattributed-click'])
export type EventRef = { itemId: string; materialKey: string }
export type EventReceipt = { id: string; impression_id: string | null; replayed: boolean }
type PendingEvent = { path: string; body: string; created: number; key: string }

function storage(): Storage | null {
  try { return typeof sessionStorage === 'undefined' ? null : sessionStorage } catch { return null }
}
function readOutbox(): PendingEvent[] {
  try {
    const value: unknown = JSON.parse(storage()?.getItem(outboxKey) ?? '[]')
    if (!Array.isArray(value)) return []
    const items = value.filter((x): x is PendingEvent => x && typeof x === 'object' &&
      allowedPaths.has(x.path) && typeof x.body === 'string' && x.body.length <= 4096 &&
      typeof x.key === 'string' && x.key.length <= 100 && typeof x.created === 'number' &&
      Number.isFinite(x.created) && Date.now() - x.created <= maxAgeMs && x.created <= Date.now())
      .slice(0, maxPending)
    if (items.length !== value.length) {
      const target = storage()
      if (items.length) target?.setItem(outboxKey, JSON.stringify(items))
      else target?.removeItem(outboxKey)
    }
    return items
  } catch { return [] }
}
function writeOutbox(items: PendingEvent[]) {
  try {
    const target = storage()
    if (!target) return
    if (items.length) target.setItem(outboxKey, JSON.stringify(items))
    else target.removeItem(outboxKey)
  } catch { /* Storage may be disabled; delivery is best effort. */ }
}
function enqueue(path: string, body: string, key: string) {
  const items = readOutbox()
  if (!items.some((item) => item.key === key) && items.length < maxPending) {
    writeOutbox([...items, { path, body, key, created: Date.now() }])
  }
  scheduleFlush()
}
const retryable = (error: unknown) => !(error instanceof RecommendationApiError) || error.status === 403 || error.status >= 500

async function deliver(path: string, body: string): Promise<EventReceipt> {
  let lastError: unknown
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const csrf = await getCsrfToken()
      const response = await fetch(`${baseUrl}/api/v1/events/${path}`, {
        method: 'POST', credentials: 'include', keepalive: true,
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body,
      })
      if (!response.ok) throw new RecommendationApiError(response.status)
      const result: unknown = await response.json()
      if (!result || typeof result !== 'object' || !('id' in result) || typeof result.id !== 'string' ||
          !('replayed' in result) || typeof result.replayed !== 'boolean' ||
          !('impression_id' in result) || !(result.impression_id === null || typeof result.impression_id === 'string')) {
        throw new Error('Некорректный ответ сервиса событий.')
      }
      return result as EventReceipt
    } catch (error) {
      if (!retryable(error)) throw error
      lastError = error
    }
    if (attempt < 2) await new Promise((resolve) => setTimeout(resolve, 300 * (attempt + 1)))
  }
  throw lastError
}

let flushing: Promise<void> | null = null
let retryTimer: ReturnType<typeof setTimeout> | null = null
function scheduleFlush() {
  if (typeof window === 'undefined' || retryTimer !== null || !readOutbox().length) return
  retryTimer = setTimeout(() => { retryTimer = null; void flushEventOutbox() }, 30000)
}
export function flushEventOutbox(): Promise<void> {
  if (flushing) return flushing
  flushing = (async () => {
    for (const entry of readOutbox()) {
      try {
        await deliver(entry.path, entry.body)
      } catch (error) {
        if (retryable(error)) break
        // An expired session or wrong actor cannot deliver this event safely.
      }
      writeOutbox(readOutbox().filter((item) => item.key !== entry.key))
    }
  })().finally(() => { flushing = null; scheduleFlush() })
  return flushing
}
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => { void flushEventOutbox() })
  queueMicrotask(() => { void flushEventOutbox() })
}

async function send(path: string, payload: { event_key: string } & Record<string, unknown>): Promise<EventReceipt> {
  const body = JSON.stringify(payload)
  // Write before the first network operation so navigation or reload during a
  // pending fetch cannot discard the event when sessionStorage is available.
  enqueue(path, body, payload.event_key)
  try {
    const receipt = await deliver(path, body)
    writeOutbox(readOutbox().filter((item) => item.key !== payload.event_key))
    return receipt
  } catch (error) {
    if (!retryable(error)) writeOutbox(readOutbox().filter((item) => item.key !== payload.event_key))
    throw error
  }
}

export function confirmVisibility(ref: EventRef, eventKey: string, visibleMs: number, visibleFraction: number) {
  return send('visibility', { event_key: eventKey, item_id: ref.itemId, material_key: ref.materialKey,
    visible_ms: visibleMs, visible_fraction: visibleFraction, client_time: new Date().toISOString() })
}

export function recordAction(ref: EventRef, impressionId: string, kind: 'click' | 'purchase_intent', eventKey: string) {
  return send('action', { event_key: eventKey, item_id: ref.itemId, material_key: ref.materialKey,
    impression_id: impressionId, kind, client_time: new Date().toISOString() })
}

export function recordUnattributedClick(ref: EventRef, eventKey: string) {
  return send('unattributed-click', { event_key: eventKey, item_id: ref.itemId, material_key: ref.materialKey,
    client_time: new Date().toISOString() })
}

/** Decide event type before sending; never turn an uncertain action into a different event. */
export function recordClick(ref: EventRef, impression: Promise<string> | null, eventKey: string): Promise<EventReceipt> {
  if (!impression) return recordUnattributedClick(ref, eventKey)
  return impression.then(
    (id) => recordAction(ref, id, 'click', eventKey),
    () => recordUnattributedClick(ref, eventKey),
  )
}
