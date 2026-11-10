type CourseCardProps = {
  title?: string
  description?: string
  reason?: string
  href?: string
}

export default function CourseCard({
  title,
  description,
  reason,
  href,
}: CourseCardProps) {
  if (!title) {
    return (
      <article className="course-card course-card-empty">
        <span className="course-icon" aria-hidden="true">✳</span>
        <p>Рекомендации появятся после подключения сервиса</p>
      </article>
    )
  }

  return (
    <article className="course-card">
      <div>
        <span className="course-label">Материал для вас</span>
        <h3>{title}</h3>
        {description && <p>{description}</p>}
      </div>

      <div className="course-footer">
        {reason && <span className="course-reason">{reason}</span>}
        {href && (
          <a className="course-link" href={href}>
            Открыть материал →
          </a>
        )}
      </div>
    </article>
  )
}