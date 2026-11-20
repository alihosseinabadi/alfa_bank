// Read-only ML preview: the full catalogue ranked by the same BM25 + prior
// pipeline the serving path uses. The endpoint records no decision and no event.
import { getCsrfToken } from './recommendationApi'

const baseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export type RankFormat = 'course' | 'article' | 'document' | 'webinar' | 'podcast' | 'glossary' | 'calculator'

export type RankedCourse = {
  materialKey: string
  title: string
  format: RankFormat
  durationMinutes: number | null
  listedPrice: number | null
  fitScore: number
  mlRank: number | null
  retrieved: boolean
  reason: string
  denseScore: number | null
  banditScore: number | null
}

export type CatalogueRankResult = {
  algorithm: 'hybrid-bm25-dense-prior-linucb-v1' | 'bm25+prior-preview-v1'
  status: 'matched' | 'starter' | 'needs_clarification' | 'no_eligible'
  items: RankedCourse[]
  message?: string
  retrievalMethod: string
  denseModel: string
  denseDimensions: number | null
  banditState: 'cold' | 'warm' | 'unavailable'
  banditObservations: number
}

export type RankInput = {
  task: string
  profile?: { business_stage?: string | null; industry?: string | null; experience?: string | null }
  constraints?: { formats?: RankFormat[]; budget_preference?: 'free_only' | 'paid_allowed' | null; available_time_minutes?: number | null }
  limit?: number
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)

const formats: RankFormat[] = ['course', 'article', 'document', 'webinar', 'podcast', 'glossary', 'calculator']

/** Validate untrusted JSON; copy only the fields the UI renders. */
export function parseCatalogueRank(value: unknown): CatalogueRankResult {
  if (!isRecord(value) || (value.algorithm !== 'hybrid-bm25-dense-prior-linucb-v1' && value.algorithm !== 'bm25+prior-preview-v1')) throw new Error('Некорректный ответ ML-ранжирования.')
  if (!['matched', 'starter', 'needs_clarification', 'no_eligible'].includes(String(value.status))) throw new Error('Некорректный статус ML-ранжирования.')
  if (!Array.isArray(value.items) || value.items.length > 50) throw new Error('Некорректный список ML-ранжирования.')
  const items = value.items.map((raw): RankedCourse => {
    if (!isRecord(raw) || typeof raw.material_key !== 'string' || typeof raw.title !== 'string'
      || typeof raw.reason !== 'string' || typeof raw.fit_score !== 'number'
      || typeof raw.retrieved !== 'boolean' || !formats.includes(raw.format as RankFormat)
      || !(raw.ml_rank === null || (typeof raw.ml_rank === 'number' && raw.ml_rank >= 1))
      || !(raw.duration_minutes === null || (typeof raw.duration_minutes === 'number' && raw.duration_minutes > 0))
      || !(raw.listed_price === null || typeof raw.listed_price === 'string' || typeof raw.listed_price === 'number')) {
      throw new Error('Некорректная карточка ML-ранжирования.')
    }
    return {
      materialKey: raw.material_key,
      title: raw.title,
      format: raw.format as RankFormat,
      durationMinutes: raw.duration_minutes as number | null,
      listedPrice: raw.listed_price === null ? null : Number(raw.listed_price),
      fitScore: Math.max(0, Math.min(100, Math.round(raw.fit_score))),
      mlRank: raw.ml_rank as number | null,
      retrieved: raw.retrieved,
      reason: raw.reason,
      denseScore: typeof raw.dense_score === 'number' ? raw.dense_score : null,
      banditScore: typeof raw.bandit_score === 'number' ? raw.bandit_score : null,
    }
  })
  return {
    algorithm: value.algorithm,
    status: value.status as CatalogueRankResult['status'],
    items,
    message: typeof value.message === 'string' ? value.message : undefined,
    retrievalMethod: typeof value.retrieval_method === 'string' ? value.retrieval_method : 'hybrid-bm25-dense',
    denseModel: typeof value.dense_model === 'string' ? value.dense_model : 'lsa-tfidf-svd-v2',
    denseDimensions: typeof value.dense_dimensions === 'number' ? value.dense_dimensions : null,
    banditState: value.bandit_state === 'warm' || value.bandit_state === 'unavailable' ? value.bandit_state : 'cold',
    banditObservations: typeof value.bandit_observations === 'number' ? value.bandit_observations : 0,
  }
}

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/** Rank every catalogue item for a profile. Anonymous session + CSRF required. */
export async function rankCatalogue(input: RankInput): Promise<CatalogueRankResult> {
  const body = JSON.stringify({
    task: input.task.slice(0, 300),
    profile: input.profile ?? {},
    constraints: input.constraints ?? {},
    limit: Math.min(50, Math.max(1, input.limit ?? 50)),
  })
  const send = async (csrf: string) => fetch(`${baseUrl}/api/v1/catalogue/rank`, {
    method: 'POST',
    credentials: 'include',
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body,
  })
  let lastError: unknown = new Error('ML-ранжирование недоступно.')
  // Docker Desktop may briefly restart the API while the stack wakes up. Retry
  // server/network failures, and refresh the anonymous session if it expired.
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      let response = await send(await getCsrfToken())
      if (response.status === 401 || response.status === 403) response = await send(await getCsrfToken())
      if (!response.ok) throw new Error(`ML-ранжирование недоступно (${response.status}).`)
      return parseCatalogueRank(await response.json())
    } catch (error) {
      lastError = error
      if (attempt < 3) await delay(500 * (attempt + 1))
    }
  }
  throw lastError
}
