import { Link, useOutletContext } from 'react-router-dom'
import { useEffect, useState } from 'react'
import ReasonPill from '../components/ReasonPill'
import CourseCard from '../components/CourseCard'
import type { PageContext } from '../components/Layout'
import { getRecommendations, recommendationMode } from '../services/recommendations'
import { createRecommendationController } from '../services/recommendationController'
import type { RecommendationState } from '../services/recommendationController'

function materialCount(count: number) {
  const remainder = count % 100
  const word = remainder >= 11 && remainder <= 14 ? 'материалов'
    : count % 10 === 1 ? 'материал' : count % 10 >= 2 && count % 10 <= 4 ? 'материала' : 'материалов'
  return `${count} ${word}`
}

export default function Feed() {
  const { profile } = useOutletContext<PageContext>()
  const details = [profile?.stage, profile?.industry, profile?.experience].filter(Boolean)
  const [state, setState] = useState<RecommendationState>({ status: 'initial' })
  const [attempt, setAttempt] = useState(0)
  const status = state.status
  const result = state.status === 'success' ? state.result : null
  const configurationError = state.status === 'error' ? state.configurationError : ''

  useEffect(() => {
    if (!profile?.goal) { setState({ status: 'initial' }); return }
    const controller = createRecommendationController(getRecommendations, setState)
    void controller.request(profile.goal)
    return () => controller.dispose()
  }, [profile?.goal, attempt])

  return (
    <div className="cabinet">
      <div className="cabinet-content">
        <section className="cabinet-recommendations" aria-labelledby="recommendations-title">
          <div className="cabinet-hero-head">
            <div>
              <span className="cabinet-hero-label">МАТЕРИАЛЫ</span>
              <h1 id="recommendations-title">Знания для ваших задач</h1>
              {recommendationMode !== 'demo' && <p>Материалы для вашей задачи.</p>}
            </div>
            <span className="cabinet-sparkle" aria-hidden="true">✳</span>
          </div>

          {profile && <p className="current-goal"><span>Ваша задача:</span> <strong>{profile.goal}</strong> <Link to="/onboarding">Изменить</Link></p>}
          {recommendationMode === 'demo' && <p className="demo-notice"><strong>Это демонстрация.</strong> Материалы вымышлены, ссылки недоступны. Совпадение по словам задачи может быть неточным.</p>}
          <div aria-live="polite">
            {status === 'initial' && <div className="recommendation-empty"><div><h2>Начните с задачи</h2><p>{recommendationMode === 'demo' ? 'Выберите или опишите задачу, чтобы увидеть примеры материалов.' : 'Выберите или опишите задачу, чтобы найти материалы.'}</p><Link className="button button-primary" to="/onboarding">Выбрать задачу →</Link></div></div>}
            {status === 'loading' && <div className="recommendation-empty"><span className="loading-mark" aria-hidden="true" />Подбираем материалы…</div>}
            {status === 'error' && <div className="recommendation-empty"><div><h2>Не удалось получить материалы</h2><p>{configurationError || 'Попробуйте ещё раз позже.'}</p>{!configurationError && <button className="button button-primary" type="button" onClick={() => setAttempt((n) => n + 1)}>Повторить попытку</button>}</div></div>}
            {status === 'success' && result?.materials.length === 0 && <div className="recommendation-empty"><div><h2>{result.source === 'demo' ? 'Примеры не найдены' : 'Материалы не найдены'}</h2><p>{result.source === 'demo' ? 'Попробуйте уточнить задачу: например, укажите клиентов, финансы или сотрудников.' : 'Попробуйте уточнить задачу и повторить поиск.'}</p><Link className="cabinet-text-link" to="/onboarding">Уточнить задачу →</Link></div></div>}
            {status === 'success' && !!result?.materials.length && <><div className="results-heading"><h2>{result.source === 'demo' ? 'Примеры материалов' : 'Материалы'}</h2><span>{materialCount(result.materials.length)}</span></div><div className="material-grid">{result.materials.map((material) => <CourseCard key={material.id} {...material} />)}</div></>}
          </div>
        </section>

        {profile && <div className="cabinet-bottom cabinet-bottom-single">
          <section className="cabinet-next panel" aria-labelledby="next-title">
            <div className="cabinet-section-head">
              <div>
                <span className="cabinet-label">СЛЕДУЮЩИЙ ШАГ</span>
                <h2 id="next-title">С чего начать?</h2>
              </div>
              <span className="cabinet-symbol cabinet-symbol-lilac" aria-hidden="true">✦</span>
            </div>
            <p>
              {recommendationMode === 'demo' ? 'Попробуйте уточнить задачу, чтобы увидеть другие примеры.' : 'Уточните задачу, чтобы обновить подборку.'}
            </p>
            <Link className="cabinet-action" to="/onboarding">
              Уточнить задачу <span aria-hidden="true">→</span>
            </Link>
          </section>
        </div>}

        <Link className="cabinet-analytics-link" to="/analytics">
          Посмотреть оценку рекомендаций <span aria-hidden="true">→</span>
        </Link>
      </div>
      <aside className="cabinet-profile panel" aria-labelledby="cabinet-profile-title">
        <div className="cabinet-profile-top">
          <span className="profile-avatar" aria-hidden="true">А</span>
          <span className="profile-badge">Ваша анкета</span>
          <h2 id="cabinet-profile-title">Ваши ориентиры</h2>
          <p>Здесь показаны ваши ответы для текущей подборки.</p>
        </div>
        <div className="cabinet-goal">
          <span className="cabinet-label">Ваша задача</span>
          {profile ? <ReasonPill>{profile.goal}</ReasonPill> : <p>Выберите задачу, чтобы уточнить подборку.</p>}
          {details.length > 0 && <p>{details.join(' · ')}</p>}
          <p>Анкета хранится до обновления страницы.</p>
          {profile && <Link className="cabinet-text-link" to="/onboarding">Изменить задачу <span aria-hidden="true">↗</span></Link>}
        </div>
      </aside>
    </div>
  )
}
