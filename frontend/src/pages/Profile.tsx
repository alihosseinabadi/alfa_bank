import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useOutletContext } from 'react-router-dom'
import type { PageContext, Profile } from '../components/Layout'
import { initials, profileReadiness } from '../services/account'
import {
  completeCourse, guessCategory, loadLearning, localFit, monthCells, roadmapFrom, toggleSaved,
} from '../services/learning'
import type { LearningState } from '../services/learning'
import { rankCatalogue } from '../services/rankingApi'
import type { RankedCourse } from '../services/rankingApi'

const interestOptions = [
  'Маркетинг и клиенты',
  'Продажи и переговоры',
  'Финансы и юнит-экономика',
  'Управление командой',
  'Данные и автоматизация',
  'Запуск и инвестиции',
]

const formatOptions = ['Короткие статьи', 'Видео', 'Практика', 'Вебинары']
const industries = ['Услуги', 'Торговля', 'Производство', 'IT', 'Общепит', 'Другое']
const stages = ['Идея', 'Запускаю бизнес', 'Действующий бизнес', 'Масштабируюсь']
const experiences = ['Нет опыта', 'До года', '1–3 года', 'Больше 3 лет']
const positions = ['Владелец или совладелец', 'ИП или самозанятый', 'Генеральный директор', 'Руководитель направления', 'Специалист или эксперт', 'Начинаю с нуля']
const difficulties = ['Не хватает времени', 'Не хватает денег', 'Нет системы', 'Боюсь ошибиться', 'Слишком много задач сразу', 'Пока не знаю']

const emptyProfile: Profile = {
  goal: '', industry: '', stage: '', experience: '', difficulty: '', note: '',
  position: '', interests: [], hoursPerWeek: 0, format: '',
}

function formatRu(format: string): string {
  const map: Record<string, string> = { course: 'Курс', article: 'Статья', document: 'Документ', webinar: 'Вебинар', podcast: 'Подкаст', glossary: 'Глоссарий', calculator: 'Калькулятор' }
  return map[format] ?? format
}

function plural(value: number, one: string, few: string, many: string): string {
  const mod10 = value % 10
  const mod100 = value % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few
  return many
}

export default function ProfilePage() {
  const { account, profile, setProfile, resetProfile } = useOutletContext<PageContext>()
  const navigate = useNavigate()
  const [form, setForm] = useState<Profile>(profile ?? emptyProfile)
  const [learning, setLearning] = useState<LearningState>(loadLearning)
  const [ranked, setRanked] = useState<RankedCourse[]>([])
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const [confirmReset, setConfirmReset] = useState(false)

  useEffect(() => {
    let active = true
    if (!profile?.goal) { setRanked([]); return }
    rankCatalogue({
      task: profile.goal.slice(0, 300),
      profile: { business_stage: profile.stage || null, industry: profile.industry || null, experience: profile.experience || null },
      constraints: profile.hoursPerWeek ? { available_time_minutes: profile.hoursPerWeek * 60 } : {},
      limit: 50,
    })
      .then((result) => { if (active) setRanked(result.items) })
      .catch(() => { if (active) setRanked([]) })
    return () => { active = false }
  }, [profile])

  const readiness = profileReadiness({
    goal: form.goal, industry: form.industry, stage: form.stage, experience: form.experience,
    difficulty: form.difficulty ?? '', note: form.note ?? '', position: form.position ?? '',
    interests: form.interests ?? [], hoursPerWeek: form.hoursPerWeek ?? 0, format: form.format ?? '',
  })

  const ordered = useMemo(() => ranked.map((item) => ({
    ...item,
    displayFit: item.retrieved
      ? item.fitScore
      : localFit({
        title: item.title,
        category: guessCategory(item.title),
        duration_minutes: item.durationMinutes ?? 0,
      }, profile ?? {}),
  })).sort((a, b) => Number(b.retrieved) - Number(a.retrieved) || b.displayFit - a.displayFit), [ranked, profile])

  const best = ordered.find((item) => item.retrieved) ?? ordered[0]
  const roadmap = roadmapFrom(ordered.map((item) => ({ id: item.materialKey, title: item.title })), learning.completed)
  const completedTitles = learning.completed.map((key) => ({
    key,
    title: ranked.find((item) => item.materialKey === key)?.title ?? key,
  }))
  const now = new Date()
  const month = monthCells(now.getFullYear(), now.getMonth(), learning)
  const activeDays = new Set(learning.daily.map((entry) => entry.date)).size

  function patch(next: Partial<Profile>) {
    setForm((current) => ({ ...current, ...next }))
    setSaved(false)
    setError('')
  }

  function toggleInterest(value: string) {
    const current = form.interests ?? []
    patch({ interests: current.includes(value) ? current.filter((item) => item !== value) : [...current, value].slice(0, 6) })
  }

  function save() {
    if (!form.goal.trim()) { setError('Сформулируйте главную задачу — без неё подборка не построится.'); return }
    setProfile({
      ...form,
      goal: form.goal.trim(),
      note: form.note?.trim() ?? '',
      interests: form.interests ?? [],
      hoursPerWeek: Number(form.hoursPerWeek) || 0,
    })
    setSaved(true)
  }

  function reset() {
    resetProfile()
    setLearning(loadLearning())
    navigate('/start', { replace: true })
  }

  return (
    <div className="pr-profile">
      <header className="pr-profile-head">
        <span className="pr-profile-avatar" aria-hidden="true">{initials(account?.name ?? 'А')}</span>
        <div>
          <span className="pr-eyebrow">Личный кабинет</span>
          <h1>{account?.name ?? 'Ваш профиль'}</h1>
          <p>{account?.email ?? 'Локальный демо-профиль'} · готовность {readiness}% · серия {learning.streak}</p>
        </div>
        <div className="pr-profile-actions">
          <Link className="pr-btn is-ghost is-small" to="/feed">К подборке →</Link>
          <Link className="pr-btn is-red is-small" to="/start">Обновить анкету</Link>
        </div>
      </header>

      <div className="pr-kpis">
        <div className="pr-card pr-kpi"><span>Готовность</span><strong>{readiness}%</strong><small>полей анкеты заполнено</small></div>
        <div className="pr-card pr-kpi"><span>Серия</span><strong>{learning.streak}</strong><small>{plural(learning.streak, 'день активности подряд', 'дня активности подряд', 'дней активности подряд')}</small></div>
        <div className="pr-card pr-kpi"><span>Пройдено</span><strong>{learning.completed.length}</strong><small>курсов отмечено</small></div>
        <div className="pr-card pr-kpi is-accent"><span>Лучшее совпадение</span><strong>{best ? `${best.displayFit}%` : '—'}</strong><small>{best ? formatRu(best.format) : 'нужна цель профиля'}</small></div>
      </div>

      <div className="pr-profile-grid">
        <div className="pr-profile-main">
          <section className="pr-card is-pad" aria-labelledby="edit-title">
            <div className="pr-card-head">
              <div>
                <span className="pr-eyebrow">Основной профиль</span>
                <h2 id="edit-title">Данные для ML-подборки</h2>
                <p>Изменения сразу сохраняются в браузере и влияют на ранжирование.</p>
              </div>
              <span className={`pr-badge ${saved ? 'is-green' : ''}`}>{saved ? 'сохранено' : 'локально'}</span>
            </div>

            <div className="pr-form-grid">
              <label className="pr-field is-full">
                <span>Главная задача</span>
                <input value={form.goal} maxLength={160} onChange={(event) => patch({ goal: event.target.value })} placeholder="Например, найти клиентов" />
              </label>
              <label className="pr-field">
                <span>Роль</span>
                <select value={form.position ?? ''} onChange={(event) => patch({ position: event.target.value })}>
                  <option value="">Не указана</option>
                  {positions.map((option) => <option key={option}>{option}</option>)}
                </select>
              </label>
              <label className="pr-field">
                <span>Сфера</span>
                <select value={form.industry} onChange={(event) => patch({ industry: event.target.value })}>
                  <option value="">Не указана</option>
                  {industries.map((option) => <option key={option}>{option}</option>)}
                </select>
              </label>
              <label className="pr-field">
                <span>Стадия</span>
                <select value={form.stage} onChange={(event) => patch({ stage: event.target.value })}>
                  <option value="">Не указана</option>
                  {stages.map((option) => <option key={option}>{option}</option>)}
                </select>
              </label>
              <label className="pr-field">
                <span>Опыт</span>
                <select value={form.experience} onChange={(event) => patch({ experience: event.target.value })}>
                  <option value="">Не указан</option>
                  {experiences.map((option) => <option key={option}>{option}</option>)}
                </select>
              </label>
              <label className="pr-field">
                <span>Часов в неделю</span>
                <input type="number" min={0} max={40} value={form.hoursPerWeek ?? 0} onChange={(event) => patch({ hoursPerWeek: Number(event.target.value) })} />
              </label>
              <label className="pr-field">
                <span>Формат</span>
                <select value={form.format ?? ''} onChange={(event) => patch({ format: event.target.value })}>
                  <option value="">Не выбран</option>
                  {formatOptions.map((option) => <option key={option}>{option}</option>)}
                </select>
              </label>
              <label className="pr-field is-full">
                <span>Главное ограничение</span>
                <select value={form.difficulty ?? ''} onChange={(event) => patch({ difficulty: event.target.value })}>
                  <option value="">Не указано</option>
                  {difficulties.map((option) => <option key={option}>{option}</option>)}
                </select>
              </label>
              <label className="pr-field is-full">
                <span>Ситуация своими словами</span>
                <textarea value={form.note ?? ''} rows={3} maxLength={280} onChange={(event) => patch({ note: event.target.value })} placeholder="Что происходит и что хочется изменить" />
              </label>
            </div>

            <div style={{ marginTop: 18 }}>
              <span className="pr-badge">Интересы</span>
              <div className="pr-interest-grid">
                {interestOptions.map((option) => (
                  <button
                    key={option}
                    type="button"
                    className={`pr-interest ${(form.interests ?? []).includes(option) ? 'is-on' : ''}`}
                    aria-pressed={(form.interests ?? []).includes(option)}
                    onClick={() => toggleInterest(option)}
                  >
                    {option}
                  </button>
                ))}
              </div>
            </div>

            {error && <p className="pr-error" role="alert" style={{ marginTop: 14 }}>{error}</p>}

            <div className="pr-analysis-actions">
              <button className="pr-btn is-red is-small" type="button" onClick={save}>Сохранить профиль</button>
              <button className="pr-btn is-ghost is-small" type="button" onClick={() => { setForm(profile ?? emptyProfile); setSaved(false); setError('') }}>Отменить изменения</button>
            </div>
            <p className="pr-small" style={{ marginTop: 12 }}>
              Профиль хранится в localStorage. Сервер получает только обезличенную формулировку задачи
              и три поля: стадия, отрасль, опыт.
            </p>
          </section>

          <section className="pr-card is-pad" aria-labelledby="roadmap-title">
            <div className="pr-card-head">
              <div>
                <span className="pr-eyebrow">Дорожная карта</span>
                <h2 id="roadmap-title">План на четыре недели</h2>
                <p>Сначала ML-найденные материалы, затем оценка профиля — порядок дорожной карты.</p>
              </div>
              <Link className="pr-btn is-ghost is-small" to="/feed">Все курсы →</Link>
            </div>
            <ol className="pr-roadmap" style={{ marginTop: 18 }}>
              {roadmap.map((step, index) => (
                <li key={step.week} className={step.done ? 'is-done' : index === 0 ? 'is-current' : ''}>
                  <span className="pr-roadmap-num" aria-hidden="true">{step.done ? '✓' : step.week}</span>
                  <div>
                    <strong>Неделя {step.week}. {step.title}</strong>
                    <small>{step.focus} → {step.outcome}</small>
                    <span className="pr-roadmap-course">◆ {step.courseTitle}</span>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </div>

        <div className="pr-profile-side">
          <section className="pr-card is-pad" aria-labelledby="best-title">
            <span className="pr-eyebrow">Лучшее совпадение</span>
            <h2 className="pr-title-sm" id="best-title">{best ? best.title : 'Пока нет подборки'}</h2>
            {best ? (
              <>
                <p className="pr-small" style={{ marginTop: 8 }}>{best.reason}</p>
                <div className="pr-course-meta">
                  <span className="pr-chip is-red">{best.displayFit}% {best.retrieved ? 'fit' : 'profile fit'}</span>
                  <span className="pr-chip">{formatRu(best.format)}</span>
                  {best.durationMinutes && <span className="pr-chip">{best.durationMinutes} мин</span>}
                </div>
                <div className="pr-course-actions">
                  <button
                    className="pr-btn is-red is-small"
                    type="button"
                    onClick={() => setLearning(completeCourse(learning, best.materialKey))}
                    disabled={learning.completed.includes(best.materialKey)}
                  >
                    {learning.completed.includes(best.materialKey) ? 'Пройдено ✓' : 'Отметить пройденным'}
                  </button>
                  <button className="pr-btn is-ghost is-small" type="button" onClick={() => setLearning(toggleSaved(learning, best.materialKey))}>
                    {learning.saved.includes(best.materialKey) ? 'В избранном ✓' : 'В избранное'}
                  </button>
                </div>
              </>
            ) : (
              <p className="pr-small" style={{ marginTop: 8 }}>Заполните цель и обновите страницу — ML-сервис подберёт первый материал.</p>
            )}
          </section>

          <section className="pr-card is-pad" aria-labelledby="completed-title">
            <div className="pr-card-head">
              <div>
                <span className="pr-eyebrow">Прогресс</span>
                <h2 id="completed-title">Пройденные курсы</h2>
              </div>
              <span className="pr-badge">{completedTitles.length}</span>
            </div>
            {completedTitles.length ? (
              <div className="pr-course-mini">
                {completedTitles.map((course) => (
                  <div className="pr-course-mini-row" key={course.key}>
                    <span aria-hidden="true">✓</span>
                    <div><strong>{course.title}</strong><small>отмечено в этом браузере</small></div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="pr-small" style={{ marginTop: 10 }}>
                Пока пусто. Отметьте курс пройденным на главной — он появится здесь и в дорожной карте.
              </p>
            )}
            <div className="pr-detail-list">
              <div><span>Активных дней</span><strong>{activeDays}</strong></div>
              <div><span>Минут в обучении</span><strong>{learning.minutes}</strong></div>
              <div><span>В избранном</span><strong>{learning.saved.length}</strong></div>
            </div>
            <div className="pr-month" aria-hidden="true" style={{ marginTop: 12 }}>
              {month.map((cell, index) => (
                <span key={`${cell.date}-${index}`} className={`pr-month-cell ${cell.active ? 'is-active' : ''} ${cell.today ? 'is-today' : ''} ${cell.day === 0 ? 'is-empty' : ''}`}>
                  {cell.day || ''}
                </span>
              ))}
            </div>
          </section>

          <section className="pr-card is-sand is-pad" aria-labelledby="account-title">
            <span className="pr-eyebrow">Аккаунт</span>
            <h2 className="pr-title-sm" id="account-title">Один профиль — без дублей</h2>
            <p className="pr-small" style={{ marginTop: 8 }}>
              {account ? `${account.name} · ${account.email}. ` : 'Демо-профиль. '}
              Анкета, прогресс и избранное хранятся в этом браузере. «Анкета» обновляет тот же
              профиль, а не создаёт вторую серверную запись.
            </p>
            <div className="pr-course-actions">
              <Link className="pr-btn is-red is-small" to="/start">Обновить анкету →</Link>
              <Link className="pr-btn is-ghost is-small" to="/auth">Сменить аккаунт</Link>
            </div>
          </section>

          <div className="pr-danger">
            <h3>Начать с чистого листа</h3>
            <p>Удаляет анкету, серию, пройденные курсы и избранное из этого браузера. Действие нельзя отменить.</p>
            {confirmReset ? (
              <div style={{ display: 'flex', gap: 8 }}>
                <button type="button" onClick={reset}>Да, удалить профиль</button>
                <button type="button" onClick={() => setConfirmReset(false)} style={{ borderColor: 'var(--pr-line-strong)', color: 'var(--pr-muted)' }}>Отмена</button>
              </div>
            ) : (
              <button type="button" onClick={() => setConfirmReset(true)}>Сбросить профиль</button>
            )}
          </div>
        </div>
      </div>

      <p className="pr-synthetic">
        <span><strong>Синтетические данные.</strong> Курсы, совпадения и прогресс — демонстрационные.
        Регистрация не создаёт реальную учётную запись и не отправляет пароль.</span>
      </p>
    </div>
  )
}
