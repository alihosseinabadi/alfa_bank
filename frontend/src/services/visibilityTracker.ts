/** Confirm only a continuous second with at least half the card in a visible tab. */
export function createVisibilityTracker(onConfirmed: (ms: number, fraction: number) => void, clock = {
  now: () => performance.now(),
  set: (fn: () => void, ms: number) => setTimeout(fn, ms),
  clear: (id: ReturnType<typeof setTimeout>) => clearTimeout(id),
}) {
  let start: number | null = null
  let ratio = 0, pageVisible = false, confirmed = false
  let timer: ReturnType<typeof setTimeout> | null = null
  function resetTimer() {
    if (timer !== null) clock.clear(timer)
    timer = null
  }
  function update(nextRatio: number, visible: boolean) {
    ratio = nextRatio; pageVisible = visible
    if (confirmed) return
    if (!pageVisible || ratio < 0.5) { start = null; resetTimer(); return }
    if (start === null) start = clock.now()
    resetTimer()
    const elapsed = clock.now() - start
    timer = clock.set(() => {
      timer = null
      if (start === null || !pageVisible || ratio < 0.5 || confirmed) return
      const duration = Math.floor(clock.now() - start)
      if (duration < 1000) { update(ratio, pageVisible); return }
      confirmed = true
      onConfirmed(Math.min(duration, 86400000), Math.min(1, ratio))
    }, Math.max(0, 1000 - elapsed))
  }
  return { update, dispose() { resetTimer(); start = null } }
}
