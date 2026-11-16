import { Link } from 'react-router-dom'

// Static, labelled historical evaluation. No live analytics are wired; these
// numbers come from docs/quality_stage56.md and must not be presented as CTR,
// conversion or a LinUCB-vs-baseline simulation.
const rows = [
  { method: 'TF-IDF', ndcg: '0.8321' },
  { method: 'TF-IDF + prior', ndcg: '0.8326' },
  { method: 'BM25', ndcg: '0.8564' },
  { method: 'BM25 + prior', ndcg: '0.8567' },
]

export default function Analytics() {
  return (
    <div className="analytics-page">
      <section className="analytics-intro">
        <div>
          <span className="eyebrow dark-eyebrow">ОЦЕНКА ПОИСКА</span>
          <h1>Историческая оценка рекомендаций</h1>
          <p>Статический срез синтетической оценки, не live-аналитика приложения.</p>
        </div>

        <span className="analytics-symbol" aria-hidden="true">▥</span>
      </section>

      <div className="analytics-grid">
        <section className="panel analytics-card">
          <div className="panel-heading">
            <div>
              <span className="card-kicker">СИНТЕТИЧЕСКАЯ ОЦЕНКА</span>
              <h2>NDCG@10 по методам</h2>
            </div>
            <span className="small-icon" aria-hidden="true">▥</span>
          </div>

          <div className="metric-list">
            {rows.map((row) => (
              <div key={row.method}>
                <span>{row.method}</span>
                <strong>{row.ndcg}</strong>
              </div>
            ))}
          </div>

          <p className="muted-note">
            21 задача, один агентный разметчик, приватные метки недоступны. Это
            историческая оценка retrieval, а не CTR, конверсия или продажи.
          </p>
        </section>

        <section className="panel analytics-card">
          <div className="panel-heading">
            <div>
              <span className="card-kicker">ЧЕГО ЗДЕСЬ НЕТ</span>
              <h2>Live-метрики</h2>
            </div>
            <span className="small-icon yellow-icon" aria-hidden="true">▥</span>
          </div>

          <div className="metric-list">
            <div><span>CTR</span><strong>не измерялся</strong></div>
            <div><span>Просмотры материалов</span><strong>не измерялись</strong></div>
            <div><span>Конверсия в покупку</span><strong>не измерялась</strong></div>
          </div>

          <p className="muted-note">
            События показов и кликов реализованы, но живого трафика и оплат в
            демо нет. LinUCB-против-случайного на реальных данных не проверялся.
          </p>
        </section>
      </div>

      <Link className="inline-link analytics-back" to="/feed">
        ← Вернуться к рекомендациям
      </Link>
    </div>
  )
}
