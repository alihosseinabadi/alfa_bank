import { demoMaterials } from '../data/demoMaterials'
import type { RecommendationRequest, RecommendationResult } from '../types/recommendations'

export type RecommendationMode = 'demo' | 'api' | 'invalid'

export function resolveRecommendationMode(value: string | undefined): RecommendationMode {
  if (!value || value === 'demo') return 'demo'
  if (value === 'api') return 'api'
  return 'invalid'
}

export const recommendationMode = resolveRecommendationMode(import.meta.env.VITE_RECOMMENDATIONS_SOURCE)

export class RecommendationConfigurationError extends Error {}

// Единственная точка замены при согласовании контракта API. Типы — модель UI.
export async function getRecommendations(
  { goal }: RecommendationRequest,
  mode: RecommendationMode = recommendationMode,
): Promise<RecommendationResult> {
  if (mode !== 'demo') {
    throw new RecommendationConfigurationError(mode === 'api'
      ? 'Сервис рекомендаций пока не подключён.'
      : 'Источник рекомендаций настроен неверно.')
  }
  const query = goal.toLocaleLowerCase('ru')
  const key = /клиент|продаж|покупател/.test(query) ? 'clients'
    : /финанс|деньг|расход|бюджет/.test(query) ? 'finance'
    : /сотрудник|наня|команд|персонал/.test(query) ? 'hiring' : ''
  return { source: 'demo', materials: demoMaterials[key] ?? [] }
}
