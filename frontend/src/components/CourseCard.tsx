import { useEffect, useRef } from 'react'
import type { Material } from '../types/recommendations'
import { safeMaterialUrl } from '../utils/materialUrl'
import { confirmVisibility, recordAction } from '../services/eventApi'
import { createVisibilityTracker } from '../services/visibilityTracker'
export { safeMaterialUrl } from '../utils/materialUrl'

export default function CourseCard({ title, description, reason, href, type, price, duration, access, linkNote, eventRef }: Material) {
  const safeHref = safeMaterialUrl(href)
  const element = useRef<HTMLElement>(null)
  const pendingImpression = useRef<Promise<string> | null>(null)
  const itemId = eventRef?.itemId
  const materialKey = eventRef?.materialKey

  useEffect(() => {
    pendingImpression.current = null
    if (!itemId || !materialKey || !element.current || typeof IntersectionObserver === 'undefined') return
    const ref = { itemId, materialKey }
    let ratio = 0
    const tracker = createVisibilityTracker((visibleMs, visibleFraction) => {
      const key = crypto.randomUUID()
      const pending = confirmVisibility(ref, key, visibleMs, visibleFraction).then((receipt) => receipt.id)
      pendingImpression.current = pending
      // The card remains usable if telemetry is unavailable.
      void pending.catch(() => {})
    })
    const update = () => tracker.update(ratio, document.visibilityState === 'visible')
    const observer = new IntersectionObserver((entries) => {
      const entry = entries.find((value) => value.target === element.current)
      if (entry) { ratio = entry.isIntersecting ? entry.intersectionRatio : 0; update() }
    }, { threshold: [0, 0.5, 1] })
    observer.observe(element.current)
    document.addEventListener('visibilitychange', update)
    return () => { observer.disconnect(); document.removeEventListener('visibilitychange', update); tracker.dispose() }
  }, [itemId, materialKey])

  function onOpen() {
    const impression = pendingImpression.current
    if (!itemId || !materialKey || !impression) return
    const ref = { itemId, materialKey }
    const clickKey = crypto.randomUUID()
    void impression.then((id) => recordAction(ref, id, 'click', clickKey)).catch(() => {})
  }

  return (
    <article className="course-card" ref={element}>
      <div>
        <span className="course-label"><span className="material-dot" aria-hidden="true" />{type}</span>
        <h3>{title}</h3>
        {description && <p>{description}</p>}
        {(price || duration) && <p>{[price, duration].filter(Boolean).join(' · ')}</p>}
        {access && <p>{access}</p>}
      </div>
      <div className="course-footer">
        {reason && <span className="course-reason">{reason}</span>}
        {safeHref && <a className="course-link" href={safeHref} target="_blank" rel="noopener noreferrer" onClick={onOpen}>Открыть материал →</a>}
        {safeHref && linkNote && <span className="goal-help">{linkNote}</span>}
        {!safeHref && <span className="goal-help">Ссылка недоступна</span>}
      </div>
    </article>
  )
}
