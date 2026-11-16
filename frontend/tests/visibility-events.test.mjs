import { after, before, test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'

let server, trackerModule, eventApi
before(async () => {
  server = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  trackerModule = await server.ssrLoadModule('/src/services/visibilityTracker.ts')
  eventApi = await server.ssrLoadModule('/src/services/eventApi.ts')
})
after(async () => { await server?.close() })

function fakeClock() {
  let now = 0, next = 0
  const tasks = new Map()
  return {
    now: () => now,
    set: (fn, ms) => { const id = ++next; tasks.set(id, { fn, at: now + ms }); return id },
    clear: (id) => tasks.delete(id),
    advance(ms) {
      const end = now + ms
      while (true) {
        const due = [...tasks.entries()].filter(([, task]) => task.at <= end).sort((a, b) => a[1].at - b[1].at)[0]
        if (!due) break
        now = due[1].at; tasks.delete(due[0]); due[1].fn()
      }
      now = end
    },
  }
}

test('visibility needs one continuous second at 50% in a visible tab', () => {
  const clock = fakeClock(), received = []
  const tracker = trackerModule.createVisibilityTracker((ms, fraction) => received.push({ ms, fraction }), clock)
  tracker.update(.7, true); clock.advance(900)
  tracker.update(.7, false); clock.advance(500)
  tracker.update(.49, true); clock.advance(3000)
  assert.equal(received.length, 0)
  tracker.update(.8, true); clock.advance(999); assert.equal(received.length, 0)
  clock.advance(1); assert.deepEqual(received, [{ ms: 1000, fraction: .8 }])
  tracker.update(.9, true); clock.advance(5000); assert.equal(received.length, 1)
  tracker.dispose()
})

test('event retries reuse one idempotency key and do not fake opening', async () => {
  const original = globalThis.fetch, seen = []
  let attempts = 0
  try {
    globalThis.fetch = async (url, options) => {
      if (url.endsWith('/session')) return new Response(JSON.stringify({ csrf_token: 'a'.repeat(64) }), { status: 200 })
      seen.push({ url, body: JSON.parse(options.body) })
      attempts++
      return attempts === 1 ? new Response(null, { status: 503 }) : new Response(JSON.stringify({ id: '123', impression_id: null, replayed: false }), { status: 200 })
    }
    const result = await eventApi.confirmVisibility({ itemId: 'item', materialKey: 'material' }, 'stable-key', 1000, .6)
    assert.equal(result.id, '123')
    assert.equal(seen.length, 2)
    assert.deepEqual(seen[0].body, seen[1].body)
    assert.equal(seen[0].body.event_key, 'stable-key')
    assert.ok(seen.every((entry) => entry.url.endsWith('/visibility')))
  } finally { globalThis.fetch = original }
})
