// Local learning loop for the demo: daily questions, completed courses, streak,
// roadmap and activity. Nothing here is sent to a server or presented as a real
// business metric; the UI labels synthetic charts as demo data.

export type DailyLog = {
  questionId: string
  topic: string
  date: string
  answer: string
}

export type LearningState = {
  daily: DailyLog[]
  completed: string[]
  saved: string[]
  streak: number
  lastActive: string
  minutes: number
  insight?: string
}

export type DailyOption = { label: string; insight: string }
export type DailyQuestion = {
  id: string
  topic: TopicKey
  topicLabel: string
  question: string
  why: string
  options: DailyOption[]
}

export type TopicKey = 'marketing' | 'sales' | 'finance' | 'management' | 'programming' | 'entrepreneurship'

export const topicLabels: Record<TopicKey, string> = {
  marketing: 'Маркетинг', sales: 'Продажи', finance: 'Финансы',
  management: 'Управление', programming: 'Данные и код', entrepreneurship: 'Предпринимательство',
}

export const topicKeywords: Record<TopicKey, string[]> = {
  marketing: ['маркет', 'бренд', 'клиент', 'позицион', 'канал', 'трафик'],
  sales: ['продаж', 'переговор', 'воронк', 'сделк', 'возраж'],
  finance: ['финанс', 'деньг', 'юнит', 'налог', 'прибыл', 'cash', 'доход', 'расход'],
  management: ['найм', 'сотрудник', 'процесс', 'команд', 'управлен', 'масштаб'],
  programming: ['python', 'sql', 'данн', 'автоматизац', 'код', 'аналитик'],
  entrepreneurship: ['инвест', 'фандрайз', 'питч', 'запуск', 'стартап', 'раунд'],
}

const QUESTIONS: DailyQuestion[] = [
  {
    id: 'mk-1', topic: 'marketing', topicLabel: 'Маркетинг',
    question: 'Откуда сегодня приходит большинство клиентов?',
    why: 'Канал привлечения определяет, какой курс даст быстрый результат.',
    options: [
      { label: 'Рекомендации и знакомые', insight: 'У вас сильный сарафан. Следующий шаг — сделать его повторяемым.' },
      { label: 'Соцсети и контент', insight: 'Контент уже работает. Добавьте атрибуцию, чтобы считать вклад каналов.' },
      { label: 'Платные объявления', insight: 'Платный трафик требует юнит-экономики: проверьте CAC и окупаемость.' },
      { label: 'Пока системно не привлекаем', insight: 'Начните с портрета клиента и одного канала, а не с пяти сразу.' },
    ],
  },
  {
    id: 'mk-2', topic: 'marketing', topicLabel: 'Маркетинг',
    question: 'Что чаще всего мешает сделке на этапе первого контакта?',
    why: 'Возражения показывают, чего не хватает позиционированию.',
    options: [
      { label: 'Не понимают ценность', insight: 'Сформулируйте результат в терминах клиента, а не функции продукта.' },
      { label: 'Сравнивают с конкурентами', insight: 'Нужна позиция, которую сложно скопировать. Начните с бренда.' },
      { label: 'Сомневаются в цене', insight: 'Проверьте, доказана ли ценность до разговора о цене.' },
      { label: 'Долго принимают решение', insight: 'Разбейте решение на маленький первый шаг.' },
    ],
  },
  {
    id: 'sl-1', topic: 'sales', topicLabel: 'Продажи',
    question: 'На каком этапе воронки вы теряете больше всего клиентов?',
    why: 'Узкое место воронки важнее общего «нужно больше продаж».',
    options: [
      { label: 'До первого разговора', insight: 'Проблема в оффере и канале: люди не доходят до диалога.' },
      { label: 'На презентации', insight: 'Сделайте демонстрацию вокруг одной задачи клиента.' },
      { label: 'После отправки предложения', insight: 'Добавьте короткий следующий шаг и дедлайн решения.' },
      { label: 'При повторной продаже', insight: 'Повторные продажи — отдельный процесс, его стоит описать.' },
    ],
  },
  {
    id: 'sl-2', topic: 'sales', topicLabel: 'Продажи',
    question: 'Кто сейчас ведёт продажи в компании?',
    why: 'Роль продавца влияет на то, что автоматизировать в первую очередь.',
    options: [
      { label: 'Я сам(а)', insight: 'Сначала опишите повторяемый скрипт, потом передавайте его команде.' },
      { label: 'Один менеджер', insight: 'Зафиксируйте этапы сделки, чтобы результат не зависел от человека.' },
      { label: 'Небольшая команда', insight: 'Нужны регламент и метрики по этапам воронки.' },
      { label: 'Партнёры или агентство', insight: 'Проверьте, кто отвечает за качество лидов и конверсию.' },
    ],
  },
  {
    id: 'fi-1', topic: 'finance', topicLabel: 'Финансы',
    question: 'Знаете ли вы, сколько стоит привлечение одного клиента?',
    why: 'Без CAC невозможно сравнить каналы и понять, растёт бизнес или просто выручка.',
    options: [
      { label: 'Да, считаю регулярно', insight: 'Отлично. Следующий шаг — связать CAC с LTV и сроком окупаемости.' },
      { label: 'Примерно, по ощущениям', insight: 'Соберите расходы на канал и число клиентов за месяц — это уже база.' },
      { label: 'Нет, не считаю', insight: 'Начните с простой таблицы: канал, расход, клиенты, выручка.' },
      { label: 'Пока нет клиентов', insight: 'Сначала проверьте спрос на 10–20 разговорах, до платного трафика.' },
    ],
  },
  {
    id: 'fi-2', topic: 'finance', topicLabel: 'Финансы',
    question: 'Что будет с бизнесом, если поступления задержатся на месяц?',
    why: 'Кассовый разрыв — частая причина закрытия прибыльных компаний.',
    options: [
      { label: 'Справлюсь без кредита', insight: 'У вас есть подушка. Зафиксируйте минимальный безопасный остаток.' },
      { label: 'Придётся сокращать расходы', insight: 'Составьте план расходов на 8 недель и отложите необязательное.' },
      { label: 'Нужен кредит или отсрочка', insight: 'Начните с прогноза денежного потока и переговоров с поставщиками.' },
      { label: 'Пока не понимаю', insight: 'Это первый финансовый навык, который стоит закрыть.' },
    ],
  },
  {
    id: 'mg-1', topic: 'management', topicLabel: 'Управление',
    question: 'Что происходит с задачами, когда вас нет на месте?',
    why: 'Операционная устойчивость показывает, готов ли бизнес к росту.',
    options: [
      { label: 'Всё останавливается', insight: 'Вы — узкое место. Начните с трёх повторяющихся процессов.' },
      { label: 'Команда решает, но хаотично', insight: 'Нужны владельцы задач и короткий недельный ритм.' },
      { label: 'Процессы работают без меня', insight: 'Можно масштабировать: опишите, что именно работает.' },
      { label: 'У меня пока нет команды', insight: 'Сначала решите, какую роль стоит нанять первой.' },
    ],
  },
  {
    id: 'mg-2', topic: 'management', topicLabel: 'Управление',
    question: 'Как вы выбираете, что делать на этой неделе?',
    why: 'Приоритизация — навык, который напрямую влияет на скорость роста.',
    options: [
      { label: 'По срочности', insight: 'Срочное вытесняет важное. Добавьте один стратегический слот в неделю.' },
      { label: 'По деньгам в коротком сроке', insight: 'Проверьте, не теряете ли вы долгосрочные возможности.' },
      { label: 'По плану и целям', insight: 'Хорошая база. Проверьте, что план связан с метриками.' },
      { label: 'Как получится', insight: 'Начните с одного вопроса: какой результат недели важен больше всего?' },
    ],
  },
  {
    id: 'pg-1', topic: 'programming', topicLabel: 'Данные и код',
    question: 'Сколько времени в неделю уходит на ручные отчёты и таблицы?',
    why: 'Автоматизация освобождает время для решений, а не только для отчётов.',
    options: [
      { label: 'Почти не трачу', insight: 'Можно двигаться к более сложной аналитике и прогнозам.' },
      { label: '1–3 часа', insight: 'Небольшой скрипт уже уберёт половину рутины.' },
      { label: 'Больше 3 часов', insight: 'Это хороший кандидат на автоматизацию в Python.' },
      { label: 'Данные не собраны системно', insight: 'Сначала наведите порядок в источниках, потом автоматизируйте.' },
    ],
  },
  {
    id: 'pg-2', topic: 'programming', topicLabel: 'Данные и код',
    question: 'Можете ли вы ответить на вопрос о клиентах данными, а не ощущениями?',
    why: 'Решения на данных снижают риск и ускоряют обучение.',
    options: [
      { label: 'Да, есть дашборды', insight: 'Проверьте, что метрики отвечают на решения, а не просто красивы.' },
      { label: 'Данные есть, но вручную', insight: 'SQL или Python помогут собирать ответ за минуты.' },
      { label: 'Данные разрознены', insight: 'Начните с одного вопроса и одного источника.' },
      { label: 'Пока не собираю', insight: 'Определите 3 метрики, которые нужны для решений.' },
    ],
  },
  {
    id: 'en-1', topic: 'entrepreneurship', topicLabel: 'Предпринимательство',
    question: 'Что сейчас важнее для бизнеса: расти или стабилизироваться?',
    why: 'Стадия определяет, какой тип материала будет полезнее.',
    options: [
      { label: 'Расти быстрее', insight: 'Сфокусируйтесь на канале, который уже даёт клиентов.' },
      { label: 'Стабилизировать процессы', insight: 'Сначала уберите операционный хаос, потом ускоряйтесь.' },
      { label: 'Найти новую модель', insight: 'Проверьте гипотезу на малой группе клиентов.' },
      { label: 'Привлечь инвестиции', insight: 'Инвестору нужны метрики роста и понятный план использования денег.' },
    ],
  },
  {
    id: 'en-2', topic: 'entrepreneurship', topicLabel: 'Предпринимательство',
    question: 'Что вы уже можете показать инвестору или партнёру?',
    why: 'Готовность к внешнему финансированию начинается с доказательств.',
    options: [
      { label: 'Выручку и повторные продажи', insight: 'Это сильный сигнал. Соберите динамику по месяцам.' },
      { label: 'Первых клиентов и отзывы', insight: 'Покажите, почему клиенты возвращаются.' },
      { label: 'Прототип и гипотезы', insight: 'Нужны доказательства спроса, а не только продукт.' },
      { label: 'Идею и команду', insight: 'Начните с интервью с клиентами и маленького теста.' },
    ],
  },
]

const storageKey = 'alfa.learning.v1'

function emptyState(): LearningState {
  return { daily: [], completed: [], saved: [], streak: 0, lastActive: '', minutes: 0 }
}

export function loadLearning(): LearningState {
  try {
    const raw = localStorage.getItem(storageKey)
    if (!raw) return emptyState()
    const value = JSON.parse(raw) as Partial<LearningState>
    return {
      daily: Array.isArray(value.daily) ? value.daily.filter((item) => item && typeof item.questionId === 'string').slice(-90) : [],
      completed: Array.isArray(value.completed) ? value.completed.filter((item): item is string => typeof item === 'string').slice(0, 100) : [],
      saved: Array.isArray(value.saved) ? value.saved.filter((item): item is string => typeof item === 'string').slice(0, 100) : [],
      streak: typeof value.streak === 'number' && value.streak >= 0 ? Math.floor(value.streak) : 0,
      lastActive: typeof value.lastActive === 'string' ? value.lastActive : '',
      minutes: typeof value.minutes === 'number' && value.minutes >= 0 ? Math.floor(value.minutes) : 0,
      insight: typeof value.insight === 'string' && value.insight.trim() ? value.insight.slice(0, 300) : undefined,
    }
  } catch { return emptyState() }
}

export function saveLearning(state: LearningState): void {
  try { localStorage.setItem(storageKey, JSON.stringify(state)) } catch { /* storage disabled */ }
}

function today(): string { return new Date().toISOString().slice(0, 10) }

function dayDiff(a: string, b: string): number {
  const left = Date.parse(`${a}T00:00:00Z`)
  const right = Date.parse(`${b}T00:00:00Z`)
  return Math.round((left - right) / 86_400_000)
}

/** Mark today active and update the streak. Returns a new state. */
export function touchToday(state: LearningState): LearningState {
  const date = today()
  if (state.lastActive === date) return state
  const streak = state.lastActive && dayDiff(date, state.lastActive) === 1 ? state.streak + 1 : 1
  const next = { ...state, lastActive: date, streak, minutes: state.minutes + 10 }
  saveLearning(next)
  return next
}

export function recordAnswer(state: LearningState, question: DailyQuestion, answer: string, insight?: string): LearningState {
  const date = today()
  const next = touchToday({
    ...state,
    insight: insight ? insight.slice(0, 300) : state.insight,
    daily: [...state.daily.filter((item) => !(item.questionId === question.id && item.date === date)),
      { questionId: question.id, topic: question.topic, date, answer }],
  })
  saveLearning(next)
  return next
}

export function completeCourse(state: LearningState, courseId: string): LearningState {
  if (state.completed.includes(courseId)) return state
  const next = touchToday({ ...state, completed: [...state.completed, courseId], minutes: state.minutes + 45 })
  saveLearning(next)
  return next
}

export function toggleSaved(state: LearningState, courseId: string): LearningState {
  const saved = state.saved.includes(courseId)
    ? state.saved.filter((item) => item !== courseId)
    : [...state.saved, courseId]
  const next = { ...state, saved }
  saveLearning(next)
  return next
}

function topicFromProfile(profile: { difficulty?: string; interests?: string[]; goal?: string; note?: string }): TopicKey {
  const goal = (profile.goal ?? '').toLocaleLowerCase('ru')
  const note = (profile.note ?? '').toLocaleLowerCase('ru')
  const difficulty = (profile.difficulty ?? '').toLocaleLowerCase('ru')
  const interests = profile.interests ?? []
  const order: TopicKey[] = ['marketing', 'sales', 'finance', 'management', 'programming', 'entrepreneurship']
  // The stated goal must beat a passing mention elsewhere in the profile, so it
  // gets the largest weight; interests come next, then the free-form note and
  // the stated constraint.  Ties keep the fixed order for reproducibility.
  const scores = order.map((topic) => {
    const keywords = topicKeywords[topic]
    const hits = (text: string) => keywords.filter((keyword) => text.includes(keyword)).length
    const interestHit = interests.some((interest) => interestCategory[interest] === topic) ? 1 : 0
    return {
      topic,
      score: hits(goal) * 4 + interestHit * 3 + hits(note) * 2 + hits(difficulty),
    }
  })
  const best = scores.reduce((left, right) => (right.score > left.score ? right : left))
  return best.score > 0 ? best.topic : 'management'
}

/** Deterministic daily question: topic comes from the profile, rotation from answers. */
export function pickDailyQuestion(
  profile: { difficulty?: string; interests?: string[]; goal?: string; note?: string },
  state: LearningState,
): DailyQuestion {
  const preferred = topicFromProfile(profile)
  const pool = QUESTIONS.filter((question) => question.topic === preferred)
  const answeredIds = new Set(state.daily.map((item) => item.questionId))
  const fresh = pool.find((question) => !answeredIds.has(question.id))
  if (fresh) return fresh
  const answered = state.daily.filter((item) => item.topic === preferred).length
  return pool[answered % pool.length] ?? QUESTIONS[0]
}

export function nextQuestion(
  profile: { difficulty?: string; interests?: string[]; goal?: string },
  state: LearningState,
): DailyQuestion {
  const preferred = topicFromProfile(profile)
  const pool = QUESTIONS.filter((question) => question.topic === preferred)
  if (pool.length > 1) {
    const answeredIds = new Set(state.daily.map((item) => item.questionId))
    const fresh = pool.find((question) => !answeredIds.has(question.id))
    if (fresh) return fresh
  }
  const all = QUESTIONS.filter((question) => question.topic !== preferred)
  const answered = new Set(state.daily.map((item) => item.questionId))
  return all.find((question) => !answered.has(question.id)) ?? QUESTIONS[0]
}

export function answeredToday(state: LearningState): DailyLog | undefined {
  return state.daily.find((item) => item.date === today())
}

// One catalogue term per topic keeps the daily answer in the query without
// letting a whole coaching sentence dilute BM25.
const topicTerm: Record<string, string> = {
  marketing: 'привлечение клиентов',
  sales: 'личные продажи',
  finance: 'юнит-экономика',
  management: 'управление командой',
  programming: 'python для автоматизации',
  entrepreneurship: 'запуск продукта',
}

export function topicQueryTerm(topic?: string): string {
  return topic ? topicTerm[topic] ?? '' : ''
}

export function hasQuestionToday(state: LearningState, questionId: string): boolean {
  return state.daily.some((item) => item.date === today() && item.questionId === questionId)
}

export function findQuestion(id: string): DailyQuestion | undefined {
  return QUESTIONS.find((question) => question.id === id)
}

const fitWeights: Record<TopicKey, string[]> = {
  marketing: ['маркет', 'клиент', 'бренд', 'позицион', 'канал', 'трафик'],
  sales: ['продаж', 'сделк', 'воронк', 'переговор', 'возраж'],
  finance: ['финанс', 'деньг', 'юнит', 'налог', 'прибыл', 'доход', 'расход'],
  management: ['найм', 'сотрудник', 'процесс', 'команд', 'управлен', 'масштаб'],
  programming: ['python', 'sql', 'данн', 'автоматизац', 'код', 'аналитик'],
  entrepreneurship: ['инвест', 'фандрайз', 'питч', 'запуск', 'стартап', 'раунд'],
}

/** Coarse category from a public course title, for the local fallback only. */
export function guessCategory(title: string): string {
  const text = title.toLocaleLowerCase('ru')
  if (/python|sql|данн|автоматизац|аналитик|таблиц/.test(text)) return 'programming'
  if (/налог|финанс|деньг|разрыв|юнит|прибыл|доход|расход/.test(text)) return 'finance'
  if (/продаж|переговор|воронк|возраж|сделк/.test(text)) return 'sales'
  if (/найм|сотрудник|команд|масштаб|операц|процесс|регламент/.test(text)) return 'management'
  if (/фандрайз|инвест|питч|раунд|стартап|продукт/.test(text)) return 'entrepreneurship'
  return 'marketing'
}

const interestCategory: Record<string, TopicKey> = {
  'Маркетинг и клиенты': 'marketing',
  'Продажи и переговоры': 'sales',
  'Финансы и юнит-экономика': 'finance',
  'Управление командой': 'management',
  'Данные и автоматизация': 'programming',
  'Запуск и инвестиции': 'entrepreneurship',
}

/**
 * Offline fit score used when the ML preview endpoint is unavailable.
 * Deliberately simple and labelled `~profile fit` in the UI: it is a heuristic
 * over the profile text, not a model output.
 */
export function localFit(
  course: { title: string; category: string; duration_minutes?: number },
  profile: { goal?: string; difficulty?: string; position?: string; interests?: string[]; hoursPerWeek?: number; experience?: string; stage?: string },
): number {
  const category = (course.category || '').toLocaleLowerCase('ru') as TopicKey
  const interests = profile.interests ?? []
  let score = 44
  if (interests.some((interest) => interestCategory[interest] === category)) score += 16
  const keywords = fitWeights[category] ?? []
  const goalText = (profile.goal ?? '').toLocaleLowerCase('ru')
  const interestText = interests.join(' ').toLocaleLowerCase('ru')
  const goalHits = keywords.filter((keyword) => goalText.includes(keyword)).length
  const interestHits = keywords.filter((keyword) => interestText.includes(keyword)).length
  score += Math.min(20, goalHits * 10) + Math.min(12, interestHits * 6)
  const title = course.title.toLocaleLowerCase('ru')
  const duration = course.duration_minutes ?? 0
  // A short material is a cheaper first step at the chosen weekly pace.
  if (duration > 0 && duration <= 90) score += 4
  if ((profile.stage ?? '').includes('Действующий') && /процесс|систем|команд|масштаб|воронк|операц/.test(title)) score += 4
  // Title tokens are the only signal left when BM25 did not retrieve the item.
  const goalWords = (profile.goal ?? '')
    .toLocaleLowerCase('ru')
    .split(/[^a-zа-яё0-9-]+/)
    .filter((word) => word.length >= 5)
  const titleHits = goalWords.filter((word) => title.includes(word.slice(0, 5))).length
  score += Math.min(16, titleHits * 8)
  if (category === 'programming' && !interests.includes('Данные и автоматизация')) score -= 12
  if (profile.hoursPerWeek && profile.hoursPerWeek >= duration / 60) score += 6
  const level = (profile.experience ?? '').toLocaleLowerCase('ru')
  if (level.includes('нет') || level.includes('до года')) score += title.includes('перв') ? 6 : 0
  return Math.max(32, Math.min(96, score))
}

export type RoadmapStep = {
  week: number
  title: string
  focus: string
  courseId: string | number
  courseTitle: string
  outcome: string
  done: boolean
}

const roadmapPlan: { title: string; focus: string; outcome: string }[] = [
  { title: 'Диагностика', focus: 'Собрать факты о клиентах и деньгах', outcome: 'Понятная картина: где вы теряете клиентов и деньги' },
  { title: 'Быстрый результат', focus: 'Один канал и один оффер', outcome: 'Первые измеримые заявки или продажи' },
  { title: 'Система', focus: 'Процесс, который не зависит от вас', outcome: 'Повторяемая воронка и роли в команде' },
  { title: 'Рост', focus: 'Масштабирование и метрики', outcome: 'Решение о следующем вложении времени и денег' },
]

/** Four-week roadmap built from the courses the profile matches best. */
export function buildRoadmap(
  courses: { id: number | string; title: string; category: string }[],
  profile: { goal?: string; difficulty?: string; position?: string; interests?: string[]; hoursPerWeek?: number },
  completed: string[],
): RoadmapStep[] {
  const scored = courses
    .map((course) => ({ course, score: localFit(course, profile) }))
    .sort((a, b) => b.score - a.score)
  return roadmapPlan.map((plan, index) => {
    const course = scored[index % Math.max(1, scored.length)]?.course
    return {
      week: index + 1,
      title: plan.title,
      focus: plan.focus,
      outcome: plan.outcome,
      courseId: course?.id ?? '',
      courseTitle: course?.title ?? 'Курс из каталога',
      done: !!course && completed.includes(String(course.id)),
    }
  })
}

/** Four-week roadmap from an already-ranked list (ML preview order wins). */
export function roadmapFrom(items: { id: string | number; title: string }[], completed: string[]): RoadmapStep[] {
  return roadmapPlan.map((plan, index) => {
    const course = items[index % Math.max(1, items.length)]
    return {
      week: index + 1,
      title: plan.title,
      focus: plan.focus,
      outcome: plan.outcome,
      courseId: course?.id ?? '',
      courseTitle: course?.title ?? 'Курс из каталога',
      done: !!course && completed.includes(String(course.id)),
    }
  })
}

/** Stable demo activity for charts; local actions are added on top. */
export function activitySeries(state: LearningState, days = 14): { date: string; label: string; minutes: number; lessons: number }[] {
  const base = [18, 32, 24, 46, 38, 52, 30, 42, 58, 44, 61, 39, 54, 48]
  const todayDate = new Date()
  return Array.from({ length: days }, (_, index) => {
    const date = new Date(todayDate)
    date.setDate(todayDate.getDate() - (days - 1 - index))
    const iso = date.toISOString().slice(0, 10)
    const logged = state.daily.some((item) => item.date === iso)
    return {
      date: iso,
      label: date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' }),
      minutes: logged ? base[index % base.length] + 25 : base[index % base.length],
      lessons: logged ? 2 : index % 3 === 0 ? 1 : 0,
    }
  })
}

export function monthCells(year: number, month: number, state: LearningState): { date: string; day: number; active: boolean; today: boolean }[] {
  const first = new Date(Date.UTC(year, month, 1))
  const startWeekday = (first.getUTCDay() + 6) % 7
  const daysInMonth = new Date(Date.UTC(year, month + 1, 0)).getUTCDate()
  const todayIso = today()
  const active = new Set([...state.daily.map((item) => item.date), state.lastActive].filter(Boolean))
  const cells = Array.from({ length: startWeekday }, () => ({ date: '', day: 0, active: false, today: false }))
  for (let day = 1; day <= daysInMonth; day += 1) {
    const iso = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    cells.push({ date: iso, day, active: active.has(iso), today: iso === todayIso })
  }
  return cells
}
