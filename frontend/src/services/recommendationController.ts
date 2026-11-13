import type { RecommendationRequest, RecommendationResult } from '../types/recommendations'
import { RecommendationConfigurationError } from './recommendations'

export type RecommendationState =
  | { status: 'initial' | 'loading' }
  | { status: 'success'; result: RecommendationResult }
  | { status: 'error'; configurationError: string }

// Устаревший ответ не должен заменять результат более нового запроса.
export function createRecommendationController(
  load: (request: RecommendationRequest) => Promise<RecommendationResult>,
  publish: (state: RecommendationState) => void,
) {
  let generation = 0
  let disposed = false
  return {
    async request(goal: string) {
      const requestId = ++generation
      publish({ status: 'loading' })
      try {
        const result = await load({ goal })
        if (!disposed && requestId === generation) publish({ status: 'success', result })
      } catch (error: unknown) {
        if (!disposed && requestId === generation) publish({
          status: 'error',
          configurationError: error instanceof RecommendationConfigurationError ? error.message : '',
        })
      }
    },
    dispose() { disposed = true; generation++ },
  }
}
