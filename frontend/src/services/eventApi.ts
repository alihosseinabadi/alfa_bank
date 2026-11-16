import { getCsrfToken, RecommendationApiError } from './recommendationApi'

const baseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
export type EventRef = { itemId: string; materialKey: string }
export type EventReceipt = { id: string; impression_id: string | null; replayed: boolean }

async function send(path: string, payload: object): Promise<EventReceipt> {
  const body = JSON.stringify(payload)
  let lastError: unknown
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const csrf = await getCsrfToken()
      const response = await fetch(`${baseUrl}/api/v1/events/${path}`, {
        method: 'POST', credentials: 'include', keepalive: true,
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body,
      })
      if (!response.ok) {
        const error = new RecommendationApiError(response.status)
        if (response.status !== 403 && response.status < 500) throw error
        lastError = error
      } else {
        const result: unknown = await response.json()
        if (!result || typeof result !== 'object' || !('id' in result) || typeof result.id !== 'string' ||
            !('replayed' in result) || typeof result.replayed !== 'boolean' ||
            !('impression_id' in result) || !(result.impression_id === null || typeof result.impression_id === 'string')) {
          throw new Error('Некорректный ответ сервиса событий.')
        }
        return result as EventReceipt
      }
    } catch (error) {
      if (error instanceof RecommendationApiError && error.status < 500 && error.status !== 403) throw error
      lastError = error
    }
    if (attempt < 2) await new Promise((resolve) => setTimeout(resolve, 300 * (attempt + 1)))
  }
  throw lastError
}

export function confirmVisibility(ref: EventRef, eventKey: string, visibleMs: number, visibleFraction: number) {
  return send('visibility', { event_key: eventKey, item_id: ref.itemId, material_key: ref.materialKey,
    visible_ms: visibleMs, visible_fraction: visibleFraction })
}

export function recordAction(ref: EventRef, impressionId: string, kind: 'click' | 'purchase_intent', eventKey: string) {
  return send('action', { event_key: eventKey, item_id: ref.itemId, material_key: ref.materialKey, impression_id: impressionId, kind })
}
