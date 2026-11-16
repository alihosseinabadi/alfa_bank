/** Public API v1. The application UI model is intentionally separate. */
export type MaterialFormat = 'course' | 'article' | 'document' | 'webinar' | 'podcast' | 'glossary' | 'calculator'
export type RecommendationApiRequest = {
  request_key: string
  task: string
  profile?: { business_stage?: string | null; industry?: string | null; experience?: string | null }
  constraints?: { formats?: MaterialFormat[]; budget_preference?: 'free_only' | 'paid_allowed' | null; available_time_minutes?: number | null }
  limit?: number
  /** Reserved until authenticated identity exists; currently rejected by the API. */
  user_id?: number | null
}
export type RecommendationApiCard = {
  item_id: string
  material_key: string
  position: number
  title: string
  format: MaterialFormat
  url: string
  link_status: 'reachable' | 'unknown'
  access_type: string | null
  requires_access_check: boolean
  /** Decimal string, or null when no price is known. */
  listed_price: string | null
  duration_minutes: number | null
  reason: string
}
export type RecommendationApiResponse = {
  learning_mode: 'standard' | 'test_fast'
  status: 'matched' | 'starter' | 'needs_clarification' | 'no_eligible'
  decision_id: string
  items: RecommendationApiCard[]
  message: string | null
}
