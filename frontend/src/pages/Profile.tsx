import { Link, useOutletContext } from 'react-router-dom'
import type { PageContext } from '../components/Layout'

export default function ProfilePage() {
  const { user, profile } = useOutletContext<PageContext>()

  return (
    <div className="personal-page">
      <div className="personal-heading">
        <div>
          <span className="account-kicker dark-eyebrow">АЛЬФА-КУРС</span>
          <h1>Личный кабинет</h1>
          <p>Ваши цели, обучение и достижения — в одном месте.</p>
        </div>
        <Link className="account-secondary" to="/feed">К рекомендациям →</Link>
      </div>
      <div className="personal-grid">
        <section className="personal-card personal-identity panel">
          <span className="personal-avatar" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="8" r="3.5" /><path d="M5 20a7 7 0 0 1 14 0" strokeLinecap="round" />
            </svg>
          </span>
          <h2>Мой профиль</h2>
          <p>{user ? user.email : 'Профиль ещё не создан'}</p>
          <Link className="cabinet-text-link" to={user ? '/onboarding' : '/register'}>
            {user ? 'Изменить анкету' : 'Создать профиль'} →
          </Link>
          <div className="personal-details">
            <div><span>Задача</span><strong>{profile?.goal || 'Не указана'}</strong></div>
            <div><span>Сфера</span><strong>{profile?.industry || 'Не указана'}</strong></div>
            <div><span>Стадия</span><strong>{profile?.stage || 'Не указана'}</strong></div>
            <div><span>Опыт</span><strong>{profile?.experience || 'Не указан'}</strong></div>
          </div>
          <p className="account-note">Изменения анкеты доступны до обновления страницы.</p>
        </section>
        <div className="personal-content">
          <section className="personal-card panel">
            <div className="personal-card-heading"><div><span className="account-kicker">ОБУЧЕНИЕ</span><h2>Мой прогресс</h2></div><span className="personal-mark" aria-hidden="true">↗</span></div>
            <div className="personal-empty"><h3>Ваш путь только начинается</h3><p>Здесь появится прогресс по курсам, когда станут доступны данные об обучении.</p></div>
          </section>
          <div className="personal-cards">
            <section className="personal-card panel"><span className="account-kicker">ВАШ РИТМ</span><h2>Активность</h2><p>Здесь появятся дни занятий, когда данные станут доступны.</p></section>
            <section className="personal-card panel"><span className="account-kicker">ВАШИ УСПЕХИ</span><h2>Достижения</h2><p>Здесь будут ваши достижения, когда данные станут доступны.</p></section>
          </div>
          <section className="personal-card panel"><span className="account-kicker">ПРОДОЛЖАЙТЕ УЧИТЬСЯ</span><h2>Мои курсы</h2><p>Начатые курсы появятся здесь после подключения данных об обучении.</p><Link className="cabinet-text-link" to="/feed">Посмотреть рекомендации →</Link></section>
        </div>
      </div>
    </div>
  )
}
