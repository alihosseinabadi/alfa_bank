import { demoMaterials } from '../data/demoMaterials'
import type { RecommendationRequest, RecommendationResult } from '../types/recommendations'
import { requestRecommendations } from './recommendationApi'

export type RecommendationMode = 'demo' | 'api' | 'invalid'

export function resolveRecommendationMode(value: string | undefined): RecommendationMode {
  if (!value || value === 'demo') return 'demo'
  if (value === 'api') return 'api'
  return 'invalid'
}

export const recommendationMode = resolveRecommendationMode(import.meta.env.VITE_RECOMMENDATIONS_SOURCE)
export class RecommendationConfigurationError extends Error {}

const formats: Record<string, string> = {
  course: 'Курс', article: 'Статья', document: 'Документ', webinar: 'Вебинар',
  podcast: 'Подкаст', glossary: 'Глоссарий', calculator: 'Калькулятор',
}

export async function getRecommendations(
  { goal, requestKey, profile }: RecommendationRequest,
  mode: RecommendationMode = recommendationMode,
): Promise<RecommendationResult> {
  if (mode === 'invalid') throw new RecommendationConfigurationError('Источник рекомендаций настроен неверно.')
  if (mode === 'api') {
    const response = await requestRecommendations({ request_key: requestKey ?? crypto.randomUUID(), task: goal, profile })
    return {
      source: 'api', status: response.status, clarification: response.message ?? undefined,
      learningMode: response.learning_mode,
      materials: response.items.map((card) => ({
        id: card.material_key, title: card.title, type: formats[card.format], reason: card.reason,
        href: card.url, access: card.access_type ? `Доступ: ${card.access_type}` : 'Доступ не указан',
        price: card.listed_price === null ? undefined : Number(card.listed_price) === 0
          ? (card.access_type === 'Открытый' ? 'Бесплатно' : undefined)
          : `Стоимость по каталогу: ${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(Number(card.listed_price))}`,
        duration: card.duration_minutes === null ? undefined : `${new Intl.NumberFormat('ru-RU').format(card.duration_minutes)} мин`,
        linkNote: card.link_status === 'unknown' ? 'Доступность ссылки не проверена.' : undefined,
        eventRef: { itemId: card.item_id, materialKey: card.material_key },
      })),
    }
  }
  const query = goal.toLocaleLowerCase('ru')
  const key = /клиент|продаж|покупател/.test(query) ? 'clients'
    : /финанс|деньг|расход|бюджет/.test(query) ? 'finance'
    : /сотрудник|наня|команд|персонал/.test(query) ? 'hiring' : ''
  return { source: 'demo', materials: demoMaterials[key] ?? [] }
}
