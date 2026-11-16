import { Link } from 'react-router-dom'

export default function Analytics() {
  return (
    <div className="analytics-page">
      <section className="analytics-intro">
        <div>
          <span className="eyebrow dark-eyebrow">РЕЗУЛЬТАТЫ</span>
          <h1>Оценка рекомендаций</h1>
          <p>Посмотрим, как работают разные подходы к подбору материалов.</p>
        </div>

        <span className="analytics-symbol" aria-hidden="true">▥</span>
      </section>

      <div className="analytics-grid">
        <section className="panel analytics-card">
          <div className="panel-heading">
            <div>
              <span className="card-kicker">АКТИВНОСТЬ</span>
              <h2>События в приложении</h2>
            </div>
            <span className="small-icon" aria-hidden="true">↗</span>
          </div>

          <div className="metric-list">
            <div><span>CTR</span><strong>—</strong></div>
            <div><span>Просмотры материалов</span><strong>—</strong></div>
            <div><span>Конверсия в покупку</span><strong>—</strong></div>
          </div>

          <p className="muted-note">Данные пока недоступны.</p>
        </section>

        <section className="panel analytics-card">
          <div className="panel-heading">
            <div>
              <span className="card-kicker">СИМУЛЯЦИЯ</span>
              <h2>Сравнение алгоритмов</h2>
            </div>
            <span className="small-icon yellow-icon" aria-hidden="true">▥</span>
          </div>

          <div className="metric-list">
            <div><span>LinUCB</span><strong>—</strong></div>
            <div><span>Random</span><strong>—</strong></div>
            <div><span>Popular</span><strong>—</strong></div>
          </div>

          <p className="muted-note">Результаты симуляции пока недоступны.</p>
        </section>
      </div>

      <Link className="inline-link analytics-back" to="/feed">
        ← Вернуться к рекомендациям
      </Link>
    </div>
  )
}