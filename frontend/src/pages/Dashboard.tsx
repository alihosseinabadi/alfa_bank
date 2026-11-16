import { useEffect, useMemo, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import CourseCard from '../components/CourseCard'
import type { PageContext } from '../components/Layout'
import { initials, profileReadiness } from '../services/account'
import { demoCatalog, getRecommendations, recommendationMode } from '../services/recommendations'
import type { Material } from '../types/recommendations'

const plan = [
  { id: 'pick', title: 'Открыть одну карточку из подборки', detail: '15 минут — чтобы появился первый конкретный шаг' },
  { id: 'write', title: 'Записать три идеи по задаче', detail: 'Один экран заметок, без оценки и фильтра' },
  { id: 'ask', title: 'Задать вопрос в поддержку', detail: 'Если задача шире, чем один материал' },
]

export default function Dashboard() {
  const { account, profile } = useOutletContext<PageContext>()
  const [materials, setMaterials] = useState<Material[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'empty' | 'error'>('loading')
  const readiness = useMemo(() => profileReadiness({
    goal: profile?.goal ?? '',
    industry: profile?.industry ?? '',
    stage: profile?.stage ?? '',
    experience: profile?.experience ?? '',
    difficulty: profile?.difficulty ?? '',
    note: profile?.note ?? '',
  }), [profile])
  const [done, setDone] = useState<string[]>([])

  useEffect(() => {
    let active = true
    if (!profile?.goal) { setStatus('empty'); return }
    setStatus('loading')
    getRecommendations({ goal: profile.goal, profile }, recommendationMode)
      .then((result) => {
        if (!active) return
        setMaterials(result.materials.slice(0, 3))
        setStatus(result.materials.length ? 'ready' : 'empty')
      })
      .catch(() => { if (active) setStatus('error') })
    return () => { active = false }
  }, [profile])

  const chips = [profile?.industry, profile?.stage, profile?.experience, profile?.difficulty].filter(Boolean)

  return (
    <div className="dash">
      <section className="dash-hero">
        <div>
          <span className="dash-kicker">ЛИЧНЫЙ КАБИНЕТ{recommendationMode === 'demo' ? ' · ДЕМО' : ''}</span>
          <h1>Здравствуйте, {account?.name.split(' ')[0] ?? 'предприниматель'} 👋</h1>
          <p className="dash-lede">
            {profile?.goal
              ? <>Ваш фокус сейчас: <strong>{profile.goal.toLocaleLowerCase('ru')}</strong>. Ниже — подобранные материалы и короткий план на сегодня.</>
              : <>Профиль пока пуст. Пройдите шесть вопросов, и здесь появится подборка.</>}
          </p>
          <div className="dash-hero-actions">
            <Link className="dash-primary" to="/feed">Смотреть все рекомендации →</Link>
            <Link className="dash-secondary" to="/start">{profile ? 'Изменить ответы' : 'Заполнить профиль'}</Link>
          </div>
        </div>
        <div className="dash-hero-art" aria-hidden="true">
          <svg viewBox="0 0 200 160" fill="none">
            <rect x="12" y="96" width="34" height="52" rx="8" fill="#2b2b2b" />
            <rect x="58" y="68" width="34" height="80" rx="8" fill="#d94a3c" />
            <rect x="104" y="44" width="34" height="104" rx="8" fill="#ef3124" />
            <rect x="150" y="18" width="34" height="130" rx="8" fill="#171717" />
            <path d="M18 70 62 44 108 30 160 8" stroke="#ef3124" strokeWidth="6" strokeLinecap="round" />
          </svg>
        </div>
      </section>

      <div className="dash-grid">
        <section className="dash-card dash-profile" aria-labelledby="profile-title">
          <div className="dash-card-head">
            <div>
              <span className="dash-label">СТАТУС ПРОФИЛЯ</span>
              <h2 id="profile-title">Ваш профиль</h2>
            </div>
            <span className="dash-avatar" aria-hidden="true">{initials(account?.name ?? 'А')}</span>
          </div>
          <div className="dash-meter">
            <div className="dash-meter-bar"><span style={{ width: `${readiness}%` }} /></div>
            <strong>{readiness}%</strong>
          </div>
          <p className="dash-muted">{account?.email}</p>
          {chips.length > 0 && <div className="dash-chips">{chips.map((chip) => <span key={chip}>{chip}</span>)}</div>}
          {profile?.note && <p className="dash-note">«{profile.note}»</p>}
          <Link className="dash-link" to="/start">Дополнить ответы →</Link>
        </section>

        <section className="dash-card dash-focus" aria-labelledby="focus-title">
          <span className="dash-label">ФОКУС</span>
          <h2 id="focus-title">{profile?.goal || 'Задача пока не выбрана'}</h2>
          <p className="dash-muted">
            {profile?.difficulty
              ? <>Главное ограничение: <strong>{profile.difficulty.toLocaleLowerCase('ru')}</strong>.</>
              : 'Ответьте на вопросы, чтобы мы учли ограничения.'}
          </p>
          <div className="dash-stats">
            <div><strong>6</strong><small>вопросов</small></div>
            <div><strong>{materials.length || 3}</strong><small>карточки в подборке</small></div>
            <div><strong>{done.length}/3</strong><small>шага выполнено</small></div>
          </div>
        </section>

        <section className="dash-card dash-recos" aria-labelledby="recos-title">
          <div className="dash-card-head">
            <div>
              <span className="dash-label">РЕКОМЕНДАЦИИ</span>
              <h2 id="recos-title">Что открыть первым</h2>
            </div>
            <Link className="dash-link" to="/feed">Все →</Link>
          </div>
          {status === 'loading' && <p className="dash-muted">Подбираем материалы…</p>}
          {status === 'empty' && <p className="dash-muted">Пока нет подборки: уточните задачу в анкете.</p>}
          {status === 'error' && <p className="dash-muted">Сервис рекомендаций недоступен — попробуйте позже.</p>}
          {status === 'ready' && (
            <div className="dash-reco-grid">
              {materials.map((material) => <CourseCard key={material.id} {...material} />)}
            </div>
          )}
          {(recommendationMode === 'demo' || demoCatalog) && (
            <p className="dash-muted dash-demo-note">Демо-каталог: материалы синтетические, ссылки не ведут на реальные страницы.</p>
          )}
        </section>

        <section className="dash-card dash-plan" aria-labelledby="plan-title">
          <span className="dash-label">ПЛАН НА СЕГОДНЯ</span>
          <h2 id="plan-title">Три маленьких шага</h2>
          <ul>
            {plan.map((item) => {
              const checked = done.includes(item.id)
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`dash-step ${checked ? 'is-checked' : ''}`}
                    aria-pressed={checked}
                    onClick={() => setDone((current) => checked ? current.filter((id) => id !== item.id) : [...current, item.id])}
                  >
                    <span className="dash-step-box" aria-hidden="true">{checked ? '✓' : ''}</span>
                    <span><strong>{item.title}</strong><small>{item.detail}</small></span>
                  </button>
                </li>
              )
            })}
          </ul>
          <Link className="dash-link" to="/analytics">Как мы оцениваем подборку →</Link>
        </section>
      </div>
    </div>
  )
}
