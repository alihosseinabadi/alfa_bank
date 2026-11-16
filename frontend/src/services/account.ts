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
}

export type StoredProfile = Answers & { savedAt: string }

const accountKey = 'alfa.account.v1'
const answersKey = 'alfa.answers.v1'

const emptyAnswers: Answers = {
  goal: '',
  industry: '',
  stage: '',
  experience: '',
  difficulty: '',
  note: '',
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
  if (!value || typeof value !== 'object') return { ...emptyAnswers }
  const v = value as Record<string, unknown>
  const pick = (field: string) => (typeof v[field] === 'string' ? (v[field] as string) : '')
  return {
    goal: pick('goal'), industry: pick('industry'), stage: pick('stage'),
    experience: pick('experience'), difficulty: pick('difficulty'), note: pick('note'),
  }
}

export function saveAnswers(answers: Answers | null): void {
  writeJson(answersKey, answers ? { ...answers, savedAt: new Date().toISOString() } : null)
}

/** Share of the six answers that are filled in, 0–100. */
export function profileReadiness(answers: Answers): number {
  const fields = [answers.goal, answers.industry, answers.stage, answers.experience, answers.difficulty, answers.note]
  const filled = fields.filter((value) => value.trim().length > 0).length
  return Math.round((filled / fields.length) * 100)
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
