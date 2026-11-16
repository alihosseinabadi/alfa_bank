import { after, before, test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'

let server
let recommendations
let registerUser
let safeMaterialUrl
let createRecommendationController
let adaptStage6Ranking
let adaptMlRanking

before(async () => {
  server = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  recommendations = await server.ssrLoadModule('/src/services/recommendations.ts')
  ;({ registerUser } = await server.ssrLoadModule('/src/services/api.ts'))
  ;({ safeMaterialUrl } = await server.ssrLoadModule('/src/components/CourseCard.tsx'))
  ;({ createRecommendationController } = await server.ssrLoadModule('/src/services/recommendationController.ts'))
  ;({ adaptStage6Ranking, adaptMlRanking } = await server.ssrLoadModule('/src/services/stage6Adapter.ts'))
})

after(async () => { await server?.close() })

test('демо возвращает примеры для задачи и пустой результат при отсутствии совпадений', async () => {
  const found = await recommendations.getRecommendations({ goal: 'Найти клиентов' }, 'demo')
  assert.equal(found.source, 'demo')
  assert.ok(found.materials.length > 0)
  assert.ok(found.materials.every((item) => item.title && item.type && !item.href))
  const empty = await recommendations.getRecommendations({ goal: 'Выбрать помещение' }, 'demo')
  assert.deepEqual(empty.materials, [])
})

test('ошибка API и неизвестная настройка не подменяются демоданными', async () => {
  assert.equal(recommendations.resolveRecommendationMode(undefined), 'demo')
  assert.equal(recommendations.resolveRecommendationMode('api'), 'api')
  assert.equal(recommendations.resolveRecommendationMode('apі'), 'invalid')
  await assert.rejects(recommendations.getRecommendations({ goal: 'Найти клиентов' }, 'invalid'), recommendations.RecommendationConfigurationError)
  const originalFetch = globalThis.fetch
  try {
    globalThis.fetch = async () => new Response(null, { status: 503 })
    await assert.rejects(recommendations.getRecommendations({ goal: 'Найти клиентов', requestKey: 'a' }, 'api'), (error) => error.status === 503)
  } finally { globalThis.fetch = originalFetch }
})

test('новый запрос убирает прежнюю выдачу, поздний ответ игнорируется, ошибка допускает повтор', async () => {
  const pending = []
  const states = []
  const load = ({ goal }) => new Promise((resolve, reject) => pending.push({ goal, resolve, reject }))
  const controller = createRecommendationController(load, (state) => states.push(state))
  const first = controller.request('старая задача')
  const second = controller.request('новая задача')
  assert.deepEqual(states, [{ status: 'loading' }, { status: 'loading' }])
  const current = { source: 'api', materials: [{ id: '2', title: 'Новый материал', type: 'Статья' }] }
  pending[1].resolve(current)
  await second
  pending[0].resolve({ source: 'api', materials: [{ id: '1', title: 'Старый материал', type: 'Статья' }] })
  await first
  assert.deepEqual(states.at(-1), { status: 'success', result: current })
  const failed = controller.request('новая задача')
  assert.deepEqual(states.at(-1), { status: 'loading' })
  pending[2].reject(new Error('network'))
  await failed
  assert.deepEqual(states.at(-1), { status: 'error', configurationError: '' })
  const retry = controller.request('новая задача')
  pending[3].resolve(current)
  await retry
  assert.deepEqual(states.at(-1), { status: 'success', result: current })
  const afterUnmount = controller.request('другая задача')
  controller.dispose()
  const count = states.length
  pending[4].resolve(current)
  await afterUnmount
  assert.equal(states.length, count)
})

test('карточка допускает только абсолютные HTTP(S)-ссылки', () => {
  assert.equal(safeMaterialUrl('https://example.org/course'), 'https://example.org/course')
  for (const value of [undefined, 'javascript:alert(1)', 'data:text/html,hello', '/course', 'not a URL']) {
    assert.equal(safeMaterialUrl(value), undefined)
  }
})

test('адаптер Stage 6 показывает допустимые публичные поля и не называет подписку бесплатной', () => {
  const input = { version: 'prior-ranking-v1', status: 'matched', clarification: null, candidates: [
    { material_key: 'course:1', title: 'Пример', item_type: 'course', access_type: 'По подписке', listed_price: 0,
      duration_minutes: null, url_state: 'unknown', reasons: [{ text: 'Связано с темой' }],
      next_step: { action: 'open_material', url: 'https://example.org/course' }, requires_access_check: true },
  ] }
  const result = adaptStage6Ranking(input)
  assert.equal(result.materials[0].type, 'Курс')
  assert.equal(result.materials[0].price, undefined)
  assert.equal(result.materials[0].reason, 'Связано с темой')
  assert.equal(result.materials[0].access, 'Доступ: По подписке')
  assert.equal(result.materials[0].linkNote, 'Доступность ссылки не проверена.')
  assert.equal(adaptStage6Ranking({ ...input, status: 'needs_clarification', candidates: [], clarification: 'Уточните задачу' }).clarification, 'Уточните задачу')
  assert.throws(() => adaptStage6Ranking({ ...input, candidates: [input.candidates[0], input.candidates[0]] }), /Некорректные данные/)
  assert.throws(() => adaptStage6Ranking({ ...input, status: 'unknown' }), /Некорректные данные/)
  assert.equal(adaptStage6Ranking({ ...input, candidates: [{ ...input.candidates[0], next_step: { action: 'open_material', url: 'javascript:alert(1)' } }] }).materials[0].href, undefined)
})

test('адаптер принимает версии UCB и slate, но не публикует внутренние оценки и seed', () => {
  const candidate = { material_key: 'article:1', title: 'Материал', item_type: 'article', access_type: 'Открытый', listed_price: 0,
    duration_minutes: 10, url_state: 'reachable', reasons: [{ text: 'По теме' }], next_step: { action: 'open_material', url: 'https://example.org/' },
    exploit: 0.2, explore: 0.4, ucb_score: 0.6, selection_probability: 0.1 }
  for (const version of ['shared-linucb-ranking-v1', 'epsilon-diverse-slate-v1', 'epsilon-diverse-slate-v2']) {
    const result = adaptMlRanking({ version, status: 'matched', clarification: null, candidates: [candidate], seed: 123 })
    assert.equal(result.materials[0].title, 'Материал')
    assert.equal(result.materials[0].price, 'Бесплатно')
    assert.equal(result.materials[0].duration, '10 мин')
    assert.equal('seed' in result, false)
    assert.equal('ucb_score' in result.materials[0], false)
    assert.equal('selection_probability' in result.materials[0], false)
  }
  assert.throws(() => adaptMlRanking({ version: 'unknown-v1', status: 'matched', clarification: null, candidates: [candidate] }), /Некорректные данные/)
})

test('регистрация не отправляет свободную задачу или пустое значение в несовместимый backend', async () => {
  const originalFetch = globalThis.fetch
  const requests = []
  globalThis.fetch = async (url, options) => {
    requests.push({ url, payload: JSON.parse(options.body) })
    return new Response(JSON.stringify({ id: 42, email: 'owner@example.org' }), { status: 201 })
  }
  try {
    const profile = { goal: 'Открыть кофейню', stage: 'Запускаю бизнес', industry: 'Услуги', experience: '' }
    await assert.rejects(registerUser('owner@example.org', profile), /готовых задач/)
    await assert.rejects(registerUser('owner@example.org', null), /готовых задач/)
    assert.equal(requests.length, 0)
    assert.deepEqual(await registerUser('owner@example.org', { ...profile, goal: 'Найти клиентов' }), { id: 42, email: 'owner@example.org' })
    assert.match(requests[0].url, /\/api\/v1\/users\/$/)
    assert.equal(requests[0].payload.current_goal, 'Найти клиентов')
    assert.equal(requests[0].payload.business_status, 'Запускаю бизнес')
  } finally { globalThis.fetch = originalFetch }
})

test('регистрация сообщает о конфликте и отклоняет некорректный ответ', async () => {
  const originalFetch = globalThis.fetch
  const profile = { goal: 'Найти клиентов', stage: '', industry: '', experience: '' }
  try {
    globalThis.fetch = async () => new Response(null, { status: 409 })
    await assert.rejects(registerUser('owner@example.org', profile), /уже существует/)
    globalThis.fetch = async () => new Response(JSON.stringify({ id: '42', email: 'owner@example.org' }), { status: 201 })
    await assert.rejects(registerUser('owner@example.org', profile), /неожиданный ответ/)
    globalThis.fetch = async () => new Response('not json', { status: 201 })
    await assert.rejects(registerUser('owner@example.org', profile), /неожиданный ответ/)
  } finally { globalThis.fetch = originalFetch }
})
