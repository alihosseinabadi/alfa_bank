import type { Material, RecommendationResult } from '../types/recommendations'
import { safeMaterialUrl } from '../utils/materialUrl'

// Внутренние модели RankingResult из ml/7ec09e5, не утверждённый HTTP-контракт.
// Не отправляет запросы и не обрабатывает идентификаторы показов.
const formats: Record<string, string> = {
  course: 'Курс', article: 'Статья', document: 'Документ', webinar: 'Вебинар',
  podcast: 'Подкаст', glossary: 'Глоссарий', calculator: 'Калькулятор',
}
const statuses = ['matched', 'starter', 'needs_clarification', 'no_eligible'] as const
const versions = ['prior-ranking-v1', 'shared-linucb-ranking-v1', 'epsilon-diverse-slate-v1', 'epsilon-diverse-slate-v2'] as const

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
function invalid(): never { throw new Error('Некорректные данные ранжирования.') }

export function adaptMlRanking(input: unknown): RecommendationResult {
  if (!record(input) || typeof input.version !== 'string' || !versions.some((version) => version === input.version) ||
      typeof input.status !== 'string' || !statuses.some((status) => status === input.status) ||
      !Array.isArray(input.candidates) || input.candidates.length > 50 ||
      !(input.clarification === null || typeof input.clarification === 'string')) invalid()

  const status = input.status as NonNullable<RecommendationResult['status']>
  if ((status === 'matched' || status === 'starter') !== (input.candidates.length > 0)) invalid()
  const ids = new Set<string>()
  const materials: Material[] = input.candidates.map((item: unknown) => {
    if (!record(item) || typeof item.material_key !== 'string' || !item.material_key.trim() || ids.has(item.material_key) ||
        typeof item.title !== 'string' || !item.title.trim() || typeof item.item_type !== 'string' || !Object.hasOwn(formats, item.item_type) ||
        typeof item.access_type !== 'string' || !item.access_type.trim() || typeof item.url_state !== 'string' ||
        !(item.listed_price === null || (typeof item.listed_price === 'number' && Number.isFinite(item.listed_price) && item.listed_price >= 0)) ||
        !(item.duration_minutes === null || (typeof item.duration_minutes === 'number' && Number.isFinite(item.duration_minutes) && item.duration_minutes > 0)) ||
        !Array.isArray(item.reasons) || !item.reasons.every((reason: unknown) => record(reason) && typeof reason.text === 'string') ||
        !record(item.next_step) || item.next_step.action !== 'open_material' || typeof item.next_step.url !== 'string') invalid()
    ids.add(item.material_key)
    const href = item.url_state === 'unavailable' ? undefined : safeMaterialUrl(item.next_step.url)
    const price = item.listed_price === null || (item.listed_price === 0 && item.access_type !== 'Открытый')
      ? undefined : item.listed_price === 0 ? 'Бесплатно' : `${new Intl.NumberFormat('ru-RU').format(item.listed_price)} ₽`
    return {
      id: item.material_key, title: item.title, type: formats[item.item_type],
      reason: item.reasons.map((reason: { text: string }) => reason.text.trim()).filter(Boolean).join(' · ') || undefined,
      price, duration: item.duration_minutes === null ? undefined : `${new Intl.NumberFormat('ru-RU').format(item.duration_minutes)} мин`,
      access: `Доступ: ${item.access_type}`, href,
      linkNote: href && item.url_state !== 'reachable' ? 'Доступность ссылки не проверена.' : undefined,
    }
  })
  return { source: 'api', materials, status, clarification: input.clarification || undefined }
}

// Прежнее имя оставлено для существующих вызовов и тестов.
export const adaptStage6Ranking = adaptMlRanking
