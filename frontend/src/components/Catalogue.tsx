import { useEffect, useState } from 'react'

// The product database is the source of truth for the catalogue. This panel
// lists every seeded `courses` row via GET /api/v1/courses, independently of
// the (deliberately narrow) recommendation slate.
type Course = {
  id: number
  title: string
  description: string
  type: string
  price: string
  duration_minutes: number
  category: string
  difficulty: string
  source: string
}

const baseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const categoryRu: Record<string, string> = {
  marketing: 'Маркетинг', sales: 'Продажи', finance: 'Финансы',
  management: 'Управление', programming: 'Программирование', entrepreneurship: 'Предпринимательство',
}
const difficultyRu: Record<string, string> = { 'базовый': 'базовый', 'средний': 'средний', 'продвинутый': 'продвинутый' }

export default function Catalogue({ compact = false }: { compact?: boolean }) {
  const [courses, setCourses] = useState<Course[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    let active = true
    setStatus('loading')
    fetch(`${baseUrl}/api/v1/courses/?limit=100`, { credentials: 'include', cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) throw new Error(String(response.status))
        return response.json() as Promise<Course[]>
      })
      .then((rows) => { if (active) { setCourses(rows); setStatus('ready') } })
      .catch(() => { if (active) setStatus('error') })
    return () => { active = false }
  }, [])

  const counts = courses.reduce<Record<string, number>>((acc, course) => {
    acc[course.category] = (acc[course.category] || 0) + 1
    return acc
  }, {})
  const maxCount = Math.max(1, ...Object.values(counts))

  return (
    <section className="panel catalogue-panel" aria-labelledby="catalogue-title">
      <div className="panel-heading">
        <div>
          <span className="card-kicker">КАТАЛОГ ПРОДУКТОВ</span>
          <h2 id="catalogue-title">Все курсы в базе</h2>
        </div>
        <span className="ana-badge">{status === 'ready' ? `${courses.length} курсов` : status === 'error' ? 'нет связи' : 'загрузка'}</span>
      </div>
      <p className="muted-note">
        Синтетический каталог из <code>data/courses/courses.csv</code> загружен в таблицу
        <code> courses</code> и отдаётся через <code>/api/v1/courses</code>. Цены и
        длительности иллюстративны; это не реальный каталог организатора.
      </p>

      {status === 'error' && <p className="goal-help">Каталог недоступен: проверьте, что стек запущен через <code>docker compose up</code>.</p>}
      {status === 'loading' && <p className="goal-help">Загружаем курсы из продуктовой базы…</p>}

      {status === 'ready' && (
        <>
          <div className="catalogue-bars" role="img" aria-label="Распределение курсов по категориям">
            {Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([category, count]) => (
              <div className="catalogue-bar" key={category}>
                <span className="catalogue-bar-label">{categoryRu[category] || category}</span>
                <span className="catalogue-bar-track"><span style={{ width: `${(count / maxCount) * 100}%` }} /></span>
                <span className="catalogue-bar-value">{count}</span>
              </div>
            ))}
          </div>

          <div className={`catalogue-grid${compact ? ' is-compact' : ''}`}>
            {courses.map((course) => (
              <article className="catalogue-card" key={course.id}>
                <span className="catalogue-cat">{categoryRu[course.category] || course.category}</span>
                <h3>{course.title}</h3>
                {!compact && <p>{course.description}</p>}
                <div className="catalogue-meta">
                  <span>{course.duration_minutes} мин</span>
                  <span>{Number(course.price).toLocaleString('ru-RU')} ₽</span>
                  <span>{difficultyRu[course.difficulty] || course.difficulty}</span>
                </div>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
