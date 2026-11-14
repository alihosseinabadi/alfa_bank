import type { Material } from '../types/recommendations'
import { safeMaterialUrl } from '../utils/materialUrl'
export { safeMaterialUrl } from '../utils/materialUrl'

export default function CourseCard({
  title,
  description,
  reason,
  href,
  type,
  price,
  duration,
  access,
  linkNote,
}: Material) {
  const safeHref = safeMaterialUrl(href)

  return (
    <article className="course-card">
      <div>
        <span className="course-label"><span className="material-dot" aria-hidden="true" />{type}</span>
        <h3>{title}</h3>
        {description && <p>{description}</p>}
        {(price || duration) && <p>{[price, duration].filter(Boolean).join(' · ')}</p>}
        {access && <p>{access}</p>}
      </div>

      <div className="course-footer">
        {reason && <span className="course-reason">{reason}</span>}
        {safeHref && (
          <a className="course-link" href={safeHref}>
            Открыть материал →
          </a>
        )}
        {safeHref && linkNote && <span className="goal-help">{linkNote}</span>}
        {!safeHref && <span className="goal-help">Ссылка недоступна</span>}
      </div>
    </article>
  )
}
