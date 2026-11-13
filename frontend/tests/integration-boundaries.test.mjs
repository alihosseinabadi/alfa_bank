import { after, before, test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'

let server
let recommendations
let registerUser
let safeMaterialUrl
let createRecommendationController

before(async () => {
  server = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  recommendations = await server.ssrLoadModule('/src/services/recommendations.ts')
  ;({ registerUser } = await server.ssrLoadModule('/src/services/api.ts'))
  ;({ safeMaterialUrl } = await server.ssrLoadModule('/src/components/CourseCard.tsx'))
  ;({ createRecommendationController } = await server.ssrLoadModule('/src/services/recommendationController.ts'))
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

test('неподключённый API и неизвестная настройка не подменяются демоданными', async () => {
  assert.equal(recommendations.resolveRecommendationMode(undefined), 'demo')
  assert.equal(recommendations.resolveRecommendationMode('api'), 'api')
  assert.equal(recommendations.resolveRecommendationMode('apі'), 'invalid')
  for (const mode of ['api', 'invalid']) {
    await assert.rejects(recommendations.getRecommendations({ goal: 'Найти клиентов' }, mode), recommendations.RecommendationConfigurationError)
  }
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

test('регистрация передаёт поддержанные поля и не отправляет свободную задачу как enum', async () => {
  const originalFetch = globalThis.fetch
  const requests = []
  globalThis.fetch = async (url, options) => {
    requests.push({ url, payload: JSON.parse(options.body) })
    return new Response(JSON.stringify({ id: 42, email: 'owner@example.org' }), { status: 201 })
  }
  try {
    const profile = { goal: 'Открыть кофейню', stage: 'Запускаю бизнес', industry: 'Услуги', experience: '' }
    assert.deepEqual(await registerUser('owner@example.org', profile), { id: 42, email: 'owner@example.org' })
    assert.match(requests[0].url, /\/api\/v1\/users\/$/)
    assert.equal(requests[0].payload.current_goal, null)
    assert.equal(requests[0].payload.business_status, 'Запускаю бизнес')
    await registerUser('owner@example.org', { ...profile, goal: 'Найти клиентов' })
    assert.equal(requests[1].payload.current_goal, 'Найти клиентов')
  } finally { globalThis.fetch = originalFetch }
})

test('регистрация сообщает о конфликте и отклоняет некорректный ответ', async () => {
  const originalFetch = globalThis.fetch
  try {
    globalThis.fetch = async () => new Response(null, { status: 409 })
    await assert.rejects(registerUser('owner@example.org', null), /уже существует/)
    globalThis.fetch = async () => new Response(JSON.stringify({ id: '42', email: 'owner@example.org' }), { status: 201 })
    await assert.rejects(registerUser('owner@example.org', null), /неожиданный ответ/)
    globalThis.fetch = async () => new Response('not json', { status: 201 })
    await assert.rejects(registerUser('owner@example.org', null), /неожиданный ответ/)
  } finally { globalThis.fetch = originalFetch }
})
