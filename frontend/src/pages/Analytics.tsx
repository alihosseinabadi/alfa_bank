import { Link } from 'react-router-dom'

// Static, labelled historical evaluation. No live analytics are wired; these
// numbers come from docs/quality_stage56.md and must not be presented as CTR,
// conversion or a LinUCB-vs-baseline simulation.
const rows = [
  { method: 'BM25 + prior', ndcg: 0.8567 },
  { method: 'BM25', ndcg: 0.8564 },
  { method: 'TF-IDF + prior', ndcg: 0.8326 },
  { method: 'TF-IDF', ndcg: 0.8321 },
]

const scaleMin = 0.82
const scaleMax = 0.86
const best = Math.max(...rows.map((row) => row.ndcg))
const baseline = rows[rows.length - 1].ndcg
const percent = (value: number) => ((value - scaleMin) / (scaleMax - scaleMin)) * 100
const delta = (value: number) => (value - baseline).toFixed(4)

export default function Analytics() {
  return (
    <div className="analytics-page">
      <section className="analytics-intro ana-hero">
        <div>
          <span className="eyebrow dark-eyebrow">ОЦЕНКА ПОИСКА</span>
          <h1>Историческая оценка рекомендаций</h1>
          <p>Статический срез синтетической оценки, не live-аналитика приложения.</p>
          <div className="ana-stats">
            <div><strong>21</strong><span>задача</span></div>
            <div><strong>4</strong><span>метода</span></div>
            <div><strong>{best.toFixed(4)}</strong><span>лучший NDCG@10</span></div>
            <div><strong>0</strong><span>live-метрик</span></div>
          </div>
        </div>

        <span className="analytics-symbol" aria-hidden="true">▥</span>
      </section>

      <div className="analytics-grid ana-grid">
        <section className="panel analytics-card ana-card">
          <div className="panel-heading">
            <div>
              <span className="card-kicker">СИНТЕТИЧЕСКАЯ ОЦЕНКА</span>
              <h2>NDCG@10 по методам</h2>
            </div>
            <span className="ana-badge">выше — лучше</span>
          </div>

          <div className="ana-bars" role="img" aria-label="NDCG@10 по методам: BM25 + prior 0.8567, BM25 0.8564, TF-IDF + prior 0.8326, TF-IDF 0.8321">
            {rows.map((row, index) => (
              <div className={`ana-bar-row${index < 2 ? ' is-leader' : ''}`} key={row.method}>
                <span className="ana-bar-label">{row.method}</span>
                <span className="ana-bar-track">
                  <span className="ana-bar-fill" style={{ width: `${percent(row.ndcg)}%` }} />
                </span>
                <span className="ana-bar-value">{row.ndcg.toFixed(4)}</span>
                <span className="ana-bar-delta">{index === rows.length - 1 ? 'база' : `+${delta(row.ndcg)}`}</span>
              </div>
            ))}
          </div>

          <div className="ana-axis" aria-hidden="true">
            <span>{scaleMin.toFixed(2)}</span>
            <span>{((scaleMin + scaleMax) / 2).toFixed(2)}</span>
            <span>{scaleMax.toFixed(2)}</span>
          </div>

          <p className="muted-note">
            Шкала 0.82–0.86, чтобы разница между методами была видна. 21 задача,
            один агентный разметчик, приватные метки недоступны. Это
            историческая оценка retrieval, а не CTR, конверсия или продажи.
          </p>
        </section>

        <section className="panel analytics-card ana-card">
          <div className="panel-heading">
            <div>
              <span className="card-kicker">РАЗНИЦА С БАЗОЙ</span>
              <h2>Прирост NDCG@10</h2>
            </div>
            <span className="ana-badge ana-badge-neutral">к TF-IDF</span>
          </div>

          <div className="ana-columns" role="img" aria-label="Прирост NDCG относительно TF-IDF: BM25 + prior +0.0246, BM25 +0.0243, TF-IDF + prior +0.0005, TF-IDF 0">
            {rows.map((row) => (
              <div className="ana-column" key={row.method}>
                <span className="ana-column-value">{row.method === rows[rows.length - 1].method ? '0' : `+${delta(row.ndcg)}`}</span>
                <span className="ana-column-track">
                  <span className="ana-column-fill" style={{ height: `${Math.max(6, percent(row.ndcg))}%` }} />
                </span>
                <span className="ana-column-label">{row.method === 'BM25 + prior' ? 'BM25+prior' : row.method === 'TF-IDF + prior' ? 'TF-IDF+prior' : row.method}</span>
              </div>
            ))}
          </div>

          <p className="muted-note">
            Разрыв между TF-IDF и BM25 больше, чем вклад prior-ранжирования.
            Различия внутри пар малы и не доказывают эффект на живых
            пользователях.
          </p>
        </section>
      </div>

      <section className="panel analytics-card ana-card ana-missing">
        <div className="panel-heading">
          <div>
            <span className="card-kicker">ЧЕГО ЗДЕСЬ НЕТ</span>
            <h2>Live-метрики</h2>
          </div>
          <span className="ana-badge ana-badge-warn">не измерялись</span>
        </div>

        <div className="ana-status">
          <div className="ana-status-row"><span>CTR</span><span className="ana-pill ana-pill-empty">нет данных</span><span className="ana-status-bar"><span style={{ width: '0%' }} /></span></div>
          <div className="ana-status-row"><span>Просмотры материалов</span><span className="ana-pill ana-pill-empty">нет данных</span><span className="ana-status-bar"><span style={{ width: '0%' }} /></span></div>
          <div className="ana-status-row"><span>Конверсия в покупку</span><span className="ana-pill ana-pill-empty">нет данных</span><span className="ana-status-bar"><span style={{ width: '0%' }} /></span></div>
        </div>

        <p className="muted-note">
          События показов и кликов реализованы, но живого трафика и оплат в
          демо нет. LinUCB-против-случайного на реальных данных не проверялся.
        </p>
      </section>

      <Link className="inline-link analytics-back" to="/feed">
        ← Вернуться к рекомендациям
      </Link>
    </div>
  )
}
