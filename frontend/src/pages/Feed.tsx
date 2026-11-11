import { Link, useOutletContext } from 'react-router-dom'
import ReasonPill from '../components/ReasonPill'
import type { PageContext } from '../components/Layout'

export default function Feed() {
  const { profile } = useOutletContext<PageContext>()
  const details = [profile?.stage, profile?.industry, profile?.experience].filter(Boolean)

  return (
    <div className="cabinet">
      <aside className="cabinet-profile panel" aria-labelledby="cabinet-profile-title">
        <div className="cabinet-profile-top">
          <span className="profile-avatar" aria-hidden="true">А</span>
          <span className="profile-badge">Ваш профиль</span>
          <h2 id="cabinet-profile-title">Рады вас видеть</h2>
          <p>Учитесь в своём темпе и находите ответы для бизнеса.</p>
        </div>

        <div className="cabinet-goal">
          <span className="cabinet-label">Ваша задача</span>
          {profile ? (
            <ReasonPill>{profile.goal}</ReasonPill>
          ) : (
            <p>Выберите задачу, чтобы уточнить подборку.</p>
          )}
          {details.length > 0 && <p>{details.join(' · ')}</p>}
          <Link className="cabinet-text-link" to="/onboarding">
            {profile ? 'Изменить профиль' : 'Заполнить анкету'} <span aria-hidden="true">↗</span>
          </Link>
        </div>

        <section className="cabinet-activity" aria-labelledby="activity-title">
          <div className="cabinet-section-head">
            <div>
              <span className="cabinet-label">ВАШ РИТМ</span>
              <h2 id="activity-title">Активность</h2>
            </div>
            <span className="cabinet-symbol cabinet-symbol-yellow" aria-hidden="true">↗</span>
          </div>
          <div className="activity-empty">
            <span className="activity-icon" aria-hidden="true">○</span>
            <p>Здесь появится ваша активность, когда данные станут доступны.</p>
          </div>
        </section>
      </aside>

      <div className="cabinet-content">
        <section className="cabinet-recommendations" aria-labelledby="recommendations-title">
          <div className="cabinet-hero-head">
            <div>
              <span className="cabinet-hero-label">ПОДОБРАНО ДЛЯ ВАС</span>
              <h1 id="recommendations-title">Знания для ваших задач</h1>
              <p>Материалы, которые помогут сделать следующий шаг в бизнесе.</p>
            </div>
            <span className="cabinet-sparkle" aria-hidden="true">✳</span>
          </div>

          <div className="recommendation-empty">
            <span className="recommendation-empty-icon" aria-hidden="true">✦</span>
            <div>
              <h2>Ваша подборка скоро появится</h2>
              <p>Рекомендации станут доступны после подключения сервиса.</p>
            </div>
          </div>
        </section>

        <div className="cabinet-bottom">
          <section className="cabinet-learning panel" aria-labelledby="learning-title">
            <div className="cabinet-section-head">
              <div>
                <span className="cabinet-label">ВАШЕ ОБУЧЕНИЕ</span>
                <h2 id="learning-title">Мои курсы</h2>
              </div>
              <span className="cabinet-symbol cabinet-symbol-peach" aria-hidden="true">▤</span>
            </div>
            <div className="learning-empty">
              <span className="learning-icon" aria-hidden="true">▱</span>
              <div>
                <h3>Всё впереди</h3>
                <p>Здесь появятся курсы, которые вы проходите.</p>
              </div>
            </div>
            <p className="cabinet-note">Прогресс появится, когда данные об обучении станут доступны.</p>
          </section>

          <section className="cabinet-next panel" aria-labelledby="next-title">
            <div className="cabinet-section-head">
              <div>
                <span className="cabinet-label">СЛЕДУЮЩИЙ ШАГ</span>
                <h2 id="next-title">С чего начать?</h2>
              </div>
              <span className="cabinet-symbol cabinet-symbol-lilac" aria-hidden="true">✦</span>
            </div>
            <p>
              {profile
                ? 'Ваша задача поможет подобрать материалы по интересующей теме.'
                : 'Расскажите, какая задача сейчас важнее всего для вашего бизнеса.'}
            </p>
            <Link className="cabinet-action" to="/onboarding">
              {profile ? 'Уточнить задачу' : 'Выбрать задачу'} <span aria-hidden="true">→</span>
            </Link>
          </section>
        </div>

        <Link className="cabinet-analytics-link" to="/analytics">
          Посмотреть оценку рекомендаций <span aria-hidden="true">→</span>
        </Link>
      </div>
    </div>
  )
}
