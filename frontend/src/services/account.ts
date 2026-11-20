// Local account + questionnaire state for the demo flow.
//
// Everything here stays in the browser (localStorage). Nothing is sent to a
// server, nothing identifies a real person, and the values only personalise the
// explicitly labelled demo cards.

export type Account = {
  name: string
  email: string
  createdAt: string
}

export type Answers = {
  goal: string
  industry: string
  stage: string
  experience: string
  difficulty: string
  note: string
  position?: string
  interests?: string[]
  hoursPerWeek?: number
  format?: string
}

export type StoredProfile = Answers & { savedAt: string }

const accountKey = 'alfa.account.v1'
const answersKey = 'alfa.answers.v1'
const learningKey = 'alfa.learning.v1'

const emptyAnswers: Answers = {
  goal: '',
  industry: '',
  stage: '',
  experience: '',
  difficulty: '',
  note: '',
  position: '',
  interests: [],
  hoursPerWeek: 0,
  format: '',
}

function readJson(key: string): unknown {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

function writeJson(key: string, value: unknown): void {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, JSON.stringify(value))
  } catch { /* storage may be disabled; the UI still works in memory */ }
}

export function loadAccount(): Account | null {
  const value = readJson(accountKey)
  if (!value || typeof value !== 'object') return null
  const a = value as Record<string, unknown>
  if (typeof a.name !== 'string' || !a.name.trim()) return null
  if (typeof a.email !== 'string' || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(a.email)) return null
  return { name: a.name, email: a.email, createdAt: typeof a.createdAt === 'string' ? a.createdAt : new Date().toISOString() }
}

export function saveAccount(account: Account | null): void {
  writeJson(accountKey, account)
}

export function loadAnswers(): Answers {
  const value = readJson(answersKey)
  if (!value || typeof value !== 'object') return { ...emptyAnswers, interests: [] }
  const v = value as Record<string, unknown>
  const pick = (field: string) => (typeof v[field] === 'string' ? (v[field] as string) : '')
  const interests = Array.isArray(v.interests)
    ? v.interests.filter((item): item is string => typeof item === 'string' && !!item.trim()).slice(0, 12)
    : []
  const hours = typeof v.hoursPerWeek === 'number' && Number.isFinite(v.hoursPerWeek) && v.hoursPerWeek >= 0
    ? v.hoursPerWeek : 0
  return {
    goal: pick('goal'), industry: pick('industry'), stage: pick('stage'),
    experience: pick('experience'), difficulty: pick('difficulty'), note: pick('note'),
    position: pick('position'), interests, hoursPerWeek: hours, format: pick('format'),
  }
}

export function saveAnswers(answers: Answers | null): void {
  writeJson(answersKey, answers ? { ...answers, savedAt: new Date().toISOString() } : null)
}

/** Start a new profile: clears answers and the local learning state. */
export function resetLocalProfile(): void {
  writeJson(answersKey, null)
  writeJson(learningKey, null)
}

/** Share of the profile fields that are filled in, 0–100. */
export function profileReadiness(answers: Answers): number {
  const fields = [
    answers.goal, answers.position, answers.industry, answers.stage,
    answers.experience, answers.difficulty, answers.note, answers.format,
  ]
  const filled = fields.filter((value) => (value ?? '').trim().length > 0).length
    + (answers.interests?.length ? 1 : 0)
    + ((answers.hoursPerWeek ?? 0) > 0 ? 1 : 0)
  return Math.round((filled / 10) * 100)
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2)
  return parts.map((part) => part[0]?.toLocaleUpperCase('ru') ?? '').join('') || 'А'
}

export const demoAccount: Account = {
  name: 'Демо-предприниматель',
  email: 'demo@example.com',
  createdAt: '2026-01-01T00:00:00.000Z',
}
