// Внутренняя модель интерфейса, не контракт backend.
export type Material = {
  id: string
  title: string
  type: string
  description?: string
  reason?: string
  price?: string
  duration?: string
  href?: string
}

export type RecommendationRequest = { goal: string }
export type RecommendationResult = { materials: Material[]; source: 'demo' | 'api' }
