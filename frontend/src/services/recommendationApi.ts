import type { MaterialFormat, RecommendationApiCard, RecommendationApiRequest, RecommendationApiResponse } from '../types/recommendationApi'

const baseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const formats = new Set<MaterialFormat>(['course', 'article', 'document', 'webinar', 'podcast', 'glossary', 'calculator'])
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const isRecord = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === 'object' && !Array.isArray(x)
const fail = (): never => { throw new Error('Некорректный ответ сервиса рекомендаций.') }

export class RecommendationApiError extends Error {
  constructor(public readonly status: number) { super('Не удалось получить рекомендации.') }
}

/** Validate untrusted JSON and copy only the documented public fields. */
export function parseRecommendationResponse(value: unknown): RecommendationApiResponse {
  if (!isRecord(value) || typeof value.decision_id !== 'string' || !uuid.test(value.decision_id) ||
      typeof value.status !== 'string' || !['matched', 'starter', 'needs_clarification', 'no_eligible'].includes(value.status) ||
      !Array.isArray(value.items) || value.items.length > 6 || !(value.message === null || (typeof value.message === 'string' && value.message.trim().length > 0))) return fail()
  const status = value.status as RecommendationApiResponse['status']
  if ((status === 'matched' || status === 'starter') !== (value.items.length > 0) || (!value.items.length && !value.message)) return fail()
  const ids = new Set<string>(), keys = new Set<string>()
  const items: RecommendationApiCard[] = value.items.map((card: unknown, index: number) => {
    if (!isRecord(card) || typeof card.item_id !== 'string' || !uuid.test(card.item_id) || ids.has(card.item_id.toLowerCase()) ||
        typeof card.material_key !== 'string' || !card.material_key.trim() || keys.has(card.material_key) || card.position !== index + 1 ||
        typeof card.title !== 'string' || !card.title.trim() || typeof card.format !== 'string' || !formats.has(card.format as MaterialFormat) ||
        typeof card.url !== 'string' || !(card.link_status === 'reachable' || card.link_status === 'unknown') ||
        !(card.access_type === null || (typeof card.access_type === 'string' && !!card.access_type.trim())) ||
        typeof card.requires_access_check !== 'boolean' || (card.access_type !== 'Открытый' && card.requires_access_check !== true) ||
        !(card.listed_price === null || (typeof card.listed_price === 'string' && /^\d+(?:\.\d{1,2})?$/.test(card.listed_price))) ||
        !(card.duration_minutes === null || (typeof card.duration_minutes === 'number' && Number.isFinite(card.duration_minutes) && card.duration_minutes > 0)) ||
        typeof card.reason !== 'string' || !card.reason.trim()) return fail()
    try { const url = new URL(card.url); if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return fail() } catch { return fail() }
    ids.add(card.item_id.toLowerCase()); keys.add(card.material_key)
    return { item_id: card.item_id, material_key: card.material_key, position: card.position as number, title: card.title,
      format: card.format as MaterialFormat, url: card.url, link_status: card.link_status, access_type: card.access_type,
      requires_access_check: card.requires_access_check, listed_price: card.listed_price,
      duration_minutes: card.duration_minutes, reason: card.reason }
  })
  return { status, decision_id: value.decision_id, items, message: value.message as string | null }
}

async function jsonOrThrow(response: Response): Promise<unknown> {
  if (!response.ok) throw new RecommendationApiError(response.status)
  try { return await response.json() } catch { return fail() }
}

let sessionInFlight: Promise<string> | null = null

function getCsrfToken(): Promise<string> {
  // Parallel calls in this tab must not race to create distinct cookies.
  if (!sessionInFlight) {
    sessionInFlight = (async () => {
      const session = await jsonOrThrow(await fetch(`${baseUrl}/api/v1/session`, { method: 'POST', credentials: 'include', cache: 'no-store' }))
      if (!isRecord(session) || typeof session.csrf_token !== 'string' || !/^[0-9a-f]{64}$/.test(session.csrf_token)) return fail()
      return session.csrf_token
    })().finally(() => { sessionInFlight = null })
  }
  return sessionInFlight
}

/** Caller retains request_key across retries of the same input. */
export async function requestRecommendations(input: RecommendationApiRequest): Promise<RecommendationApiResponse> {
  // Freeze the payload for the retry even if the caller later mutates its object.
  const body = JSON.stringify(input)
  const send = async (csrf: string) => fetch(`${baseUrl}/api/v1/recommendations`, {
    method: 'POST', credentials: 'include', cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body,
  })
  let response = await send(await getCsrfToken())
  // Another tab can rotate the cookie between bootstrap and submit. No provider
  // call has happened on a CSRF failure; refresh once using the same payload.
  if (response.status === 403) response = await send(await getCsrfToken())
  return parseRecommendationResponse(await jsonOrThrow(response))
}
