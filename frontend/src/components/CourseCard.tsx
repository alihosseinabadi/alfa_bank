import type { Material } from '../types/recommendations'

// Для внешнего материала разрешаем только явные HTTP(S)-ссылки.
export function safeMaterialUrl(value?: string): string | undefined {
  if (!value) return undefined
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : undefined
  } catch {
    return undefined
  }
}

export default function CourseCard({
  title,
  description,
  reason,
  href,
  type,
  price,
  duration,
}: Material) {
  const safeHref = safeMaterialUrl(href)

  return (
    <article className="course-card">
      <div>
        <span className="course-label"><span className="material-dot" aria-hidden="true" />{type}</span>
        <h3>{title}</h3>
        {description && <p>{description}</p>}
        {(price || duration) && <p>{[price, duration].filter(Boolean).join(' · ')}</p>}
      </div>

      <div className="course-footer">
        {reason && <span className="course-reason">{reason}</span>}
        {safeHref && (
          <a className="course-link" href={safeHref}>
            Открыть материал →
          </a>
        )}
        {!safeHref && <span className="goal-help">Ссылка недоступна</span>}
      </div>
    </article>
  )
}
