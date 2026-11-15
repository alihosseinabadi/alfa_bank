import { after, before, test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createServer } from 'vite'

let server, api
const fixture = JSON.parse(await readFile(new URL('../../tests/fixtures/recommendation-api-response.json', import.meta.url), 'utf8'))
before(async () => {
  server = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  api = await server.ssrLoadModule('/src/services/recommendationApi.ts')
})
after(async () => { await server?.close() })

test('public response is shared with backend schema and private fields are discarded', () => {
  const leaky = { ...fixture, seed: 17, items: [{ ...fixture.items[0], vector: [1, 2] }] }
  const result = api.parseRecommendationResponse(leaky)
  assert.deepEqual(result, fixture)
  assert.equal(result.items[0].link_status, 'unknown')
  assert.equal(result.items[0].listed_price, null)
})

test('rejects unsafe URLs, inconsistent empty results and repeated items', () => {
  for (const url of ['javascript:alert(1)', 'https://user:pass@example.org/', '/relative']) {
    assert.throws(() => api.parseRecommendationResponse({ ...fixture, items: [{ ...fixture.items[0], url }] }))
  }
  assert.throws(() => api.parseRecommendationResponse({ ...fixture, status: 'no_eligible' }))
  assert.throws(() => api.parseRecommendationResponse({ ...fixture, status: 'no_eligible', items: [], message: null }))
  assert.throws(() => api.parseRecommendationResponse({ ...fixture, items: [fixture.items[0], { ...fixture.items[0], position: 2 }] }))
  assert.equal(api.parseRecommendationResponse({ ...fixture, status: 'needs_clarification', items: [], message: 'Уточните задачу' }).items.length, 0)
})

test('client sends stable request key and session-bound CSRF, preserving errors', async () => {
  const original = globalThis.fetch
  const seen = []
  const request = { request_key: 'b177117e-96cb-4ba8-9f3f-455d537e90d0', task: 'Найти клиентов' }
  try {
    globalThis.fetch = async (url, options) => {
      seen.push({ url, options })
      return seen.length % 2 === 1
        ? new Response(JSON.stringify({ csrf_token: 'a'.repeat(64) }), { status: 200 })
        : new Response(JSON.stringify(fixture), { status: 200 })
    }
    assert.deepEqual(await api.requestRecommendations(request), fixture)
    assert.deepEqual(await api.requestRecommendations(request), fixture)
    assert.equal(seen[1].options.headers['X-CSRF-Token'], 'a'.repeat(64))
    assert.equal(seen[1].options.credentials, 'include')
    assert.equal(JSON.parse(seen[1].options.body).request_key, JSON.parse(seen[3].options.body).request_key)
    globalThis.fetch = async () => new Response(null, { status: 503 })
    await assert.rejects(api.requestRecommendations(request), (error) => error instanceof api.RecommendationApiError && error.status === 503)
  } finally { globalThis.fetch = original }
})

test('parallel first requests share a single session bootstrap', async () => {
  const original = globalThis.fetch
  let bootstrapCount = 0
  let release
  const gate = new Promise((resolve) => { release = resolve })
  try {
    globalThis.fetch = async (url) => {
      if (url.endsWith('/session')) {
        bootstrapCount++
        await gate
        return new Response(JSON.stringify({ csrf_token: 'a'.repeat(64) }), { status: 200 })
      }
      return new Response(JSON.stringify(fixture), { status: 200 })
    }
    const one = api.requestRecommendations({ request_key: 'b177117e-96cb-4ba8-9f3f-455d537e90d0', task: 'один' })
    const two = api.requestRecommendations({ request_key: '282dcdeb-0301-43fe-95ef-39bf35edc18c', task: 'два' })
    await new Promise((resolve) => setTimeout(resolve, 0))
    assert.equal(bootstrapCount, 1)
    release()
    await Promise.all([one, two])
  } finally { globalThis.fetch = original }
})

test('a changed cookie refreshes CSRF once without changing the request body', async () => {
  const original = globalThis.fetch
  const calls = []
  let sessions = 0, submissions = 0
  try {
    globalThis.fetch = async (url, options) => {
      calls.push({ url, options })
      if (url.endsWith('/session')) {
        sessions++
        return new Response(JSON.stringify({ csrf_token: (sessions === 1 ? 'a' : 'b').repeat(64) }), { status: 200 })
      }
      submissions++
      return submissions === 1 ? new Response(null, { status: 403 }) : new Response(JSON.stringify(fixture), { status: 200 })
    }
    await api.requestRecommendations({ request_key: 'b177117e-96cb-4ba8-9f3f-455d537e90d0', task: 'Найти клиентов' })
    assert.equal(sessions, 2)
    assert.equal(submissions, 2)
    assert.equal(calls[1].options.body, calls[3].options.body)
    assert.equal(calls[3].options.headers['X-CSRF-Token'], 'b'.repeat(64))
  } finally { globalThis.fetch = original }
})
