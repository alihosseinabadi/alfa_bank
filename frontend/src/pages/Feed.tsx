import { Link, useOutletContext } from 'react-router-dom'
import CourseCard from '../components/CourseCard'
import ReasonPill from '../components/ReasonPill'
import type { PageContext } from '../components/Layout'

export default function Feed() {
  const { profile } = useOutletContext<PageContext>()

  return (
    <div className="dashboard-grid">
      <aside className="profile-card panel">
        <span className="profile-avatar" aria-hidden="true">А</span>
        <span className="profile-badge">Ваш профиль</span>
        <h2>Ваш путь к знаниям</h2>
        <p>
          {profile
            ? 'Мы учтём вашу задачу при подборе материалов.'
            : 'Расскажите о своей задаче, чтобы получить персональную подборку.'}
        </p>

        <div className="profile-summary">
          <span>Ваша задача</span>
          <strong>{profile?.goal || 'Пока не выбрана'}</strong>
        </div>

        <Link className="button button-outline" to="/onboarding">
          Изменить профиль
        </Link>
      </aside>

      <div className="dashboard-main">
        <section className="recommendations-panel">
          <div className="section-heading light-heading">
            <div>
              <span className="eyebrow">ПЕРСОНАЛЬНЫЙ ПОДБОР</span>
              <h1>Рекомендации для вас</h1>
              <p>Материалы, которые помогут двигаться к вашей цели.</p>
            </div>
            <span className="heading-symbol" aria-hidden="true">✳</span>
          </div>

          <div className="course-grid">
            <CourseCard />
            <CourseCard />
            <CourseCard />
          </div>
        </section>

        <div className="bottom-grid">
          <section className="small-panel panel">
            <div className="panel-heading">
              <h2>Ваша задача</h2>
              <span className="small-icon" aria-hidden="true">◎</span>
            </div>

            {profile ? (
              <>
                <ReasonPill>{profile.goal}</ReasonPill>
                <p>Сохранено на время этой сессии.</p>
              </>
            ) : (
              <p>Вы можете выбрать задачу в анкете.</p>
            )}

            <Link className="inline-link" to="/onboarding">
              Изменить задачу →
            </Link>
          </section>

          <section className="small-panel panel">
            <div className="panel-heading">
              <h2>Оценка рекомендаций</h2>
              <span className="small-icon yellow-icon" aria-hidden="true">▥</span>
            </div>

            <p>Здесь появится сравнение подходов к подбору материалов.</p>

            <Link className="inline-link" to="/analytics">
              Перейти к аналитике →
            </Link>
          </section>
        </div>
      </div>
    </div>
  )
}