import { after, before, test } from 'node:test'
import assert from 'node:assert/strict'
import { webcrypto } from 'node:crypto'
import { createServer } from 'vite'
let server, session
before(async () => {
  server = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  session = await server.ssrLoadModule('/src/services/profileSession.ts')
  globalThis.crypto = webcrypto
  const data = new Map()
  globalThis.sessionStorage = { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key) }
})
after(async () => { await server?.close() })
test('profile and request identity survive reload but change with the task', () => {
  const profile = { goal: 'Найти клиентов', industry: '', stage: '', experience: '' }
  session.saveProfile(profile)
  assert.deepEqual(session.loadProfile(), profile)
  const key = session.requestKeyForProfile(JSON.stringify(profile))
  assert.equal(session.requestKeyForProfile(JSON.stringify(session.loadProfile())), key)
  const updated = { ...profile, goal: 'Управлять финансами' }
  session.saveProfile(updated)
  assert.notEqual(session.requestKeyForProfile(JSON.stringify(updated)), key)
  session.saveProfile(null)
  assert.equal(session.loadProfile(), null)
})
test('unavailable browser storage does not break requests', () => {
  globalThis.sessionStorage = { getItem() { throw Error('blocked') }, setItem() { throw Error('blocked') }, removeItem() { throw Error('blocked') } }
  assert.equal(session.loadProfile(), null)
  assert.doesNotThrow(() => session.saveProfile(null))
  assert.match(session.requestKeyForProfile('{}'), /^[0-9a-f-]{36}$/i)
})
