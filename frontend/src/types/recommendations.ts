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
  access?: string
  linkNote?: string
  eventRef?: { itemId: string; materialKey: string }
}

export type RecommendationRequest = {
  goal: string
  requestKey?: string
  profile?: {
    business_stage?: string
    stage?: string
    industry?: string
    experience?: string
    difficulty?: string
    note?: string
    goal?: string
  }
}
export type RecommendationResult = { materials: Material[]; source: 'demo' | 'api'; status?: 'matched' | 'starter' | 'needs_clarification' | 'no_eligible'; clarification?: string; learningMode?: 'standard' | 'test_fast' }
