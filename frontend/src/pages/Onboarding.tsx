import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import type { PageContext } from '../components/Layout'

const goals = [
  'Найти клиентов',
  'Разобраться с финансами',
  'Нанять сотрудника',
]

export default function Onboarding() {
  const navigate = useNavigate()
  const { profile, setProfile } = useOutletContext<PageContext>()

  const [goal, setGoal] = useState(profile?.goal ?? '')
  const [industry, setIndustry] = useState(profile?.industry ?? '')
  const [stage, setStage] = useState(profile?.stage ?? '')
  const [experience, setExperience] = useState(profile?.experience ?? '')
  const [detailsOpen, setDetailsOpen] = useState(!!(profile?.industry || profile?.stage || profile?.experience))
  const [error, setError] = useState('')
  const goalInput = useRef<HTMLTextAreaElement>(null)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (goal.trim().length < 5) {
      setError('Выберите готовую задачу или опишите свою хотя бы в 5 символах.')
      goalInput.current?.focus()
      return
    }

    setProfile({ goal: goal.trim(), industry, stage, experience })
    navigate('/feed')
  }

  function handleSkip() {
    navigate('/feed')
  }

  return (
    <div className="dashboard-grid">
      <section className="onboarding-panel">
        <div className="section-heading light-heading">
          <div>
            <span className="eyebrow">ВАШ ПЕРВЫЙ ШАГ</span>
            <h1>Подбор под вашу задачу</h1>
            <p>Выберите готовый вариант или расскажите своими словами.</p>
          </div>
          <span className="heading-symbol" aria-hidden="true">✳</span>
        </div>

        <form className="form-card" onSubmit={handleSubmit}>
          <fieldset className="goal-fieldset">
            <legend>Что хотите сделать?</legend>

            <div className="goal-options">
              {goals.map((item) => (
                <button
                  className={`goal-button ${goal === item ? 'selected' : ''}`}
                  type="button"
                  aria-pressed={goal === item}
                  key={item}
                  onClick={() => {
                    setGoal(item)
                    setError('')
                  }}
                >
                  {item}
                </button>
              ))}
            </div>

            <label className="custom-goal" htmlFor="custom-goal">Или опишите свою задачу</label>
            <textarea ref={goalInput} id="custom-goal" rows={3} maxLength={300} value={goals.includes(goal) ? '' : goal} placeholder="Например, хочу найти клиентов для интернет-магазина" aria-invalid={!!error} aria-describedby={error ? 'goal-error' : 'goal-help'} onChange={(event) => { setGoal(event.target.value); setError('') }} />
            <p id="goal-help" className="goal-help">От 5 до 300 символов. Можно выбрать готовый вариант выше.</p>
            {goal.trim().length >= 5 && <p className="goal-confirmation" role="status"><span aria-hidden="true">✓</span> Задача указана. Можно перейти к материалам.</p>}

            {error && <p id="goal-error" className="form-error" role="alert">{error}</p>}
          </fieldset>

          <details className="optional-details" open={detailsOpen} onToggle={(event) => setDetailsOpen(event.currentTarget.open)}>
          <summary>Немного о вас <span>Необязательно</span></summary>
          <div className="form-intro">
            <p>Необязательно. Пока эти сведения не влияют на демонстрационные материалы.</p>
          </div>

          <div className="form-fields">
            <label>
              Сфера бизнеса
              <select value={industry} onChange={(event) => setIndustry(event.target.value)}>
                <option value="">Выберите сферу</option>
                <option value="Услуги">Услуги</option>
                <option value="Торговля">Торговля</option>
                <option value="Производство">Производство</option>
                <option value="IT">IT</option>
                <option value="Другая">Другая</option>
              </select>
            </label>

            <label>
              Стадия бизнеса
              <select value={stage} onChange={(event) => setStage(event.target.value)}>
                <option value="">Выберите стадию</option>
                <option value="Запускаю бизнес">Запускаю бизнес</option>
                <option value="Действующий бизнес">Действующий бизнес</option>
                <option value="Масштабируюсь">Масштабируюсь</option>
              </select>
            </label>

            <label>
              Опыт
              <select value={experience} onChange={(event) => setExperience(event.target.value)}>
                <option value="">Выберите опыт</option>
                <option value="Нет опыта">Нет опыта</option>
                <option value="Есть опыт">Есть опыт</option>
              </select>
            </label>
          </div>
          </details>

          <div className="form-actions">
            <button className="button button-primary" type="submit">
              Подобрать материалы <span aria-hidden="true">→</span>
            </button>

            <button className="text-button" type="button" onClick={handleSkip}>
              Пропустить анкету
            </button>
          </div>
          <p className="goal-help">Анкета хранится только до обновления страницы.</p>
        </form>
      </section>
      <aside className="profile-card panel">
        <div className="guide-art" aria-hidden="true">
          <svg viewBox="0 0 180 132" fill="none"><rect x="18" y="32" width="100" height="72" rx="14" fill="#F8EAE4"/><rect x="30" y="20" width="100" height="72" rx="14" fill="#EFCFC5"/><rect x="42" y="8" width="100" height="72" rx="14" fill="#A62D24"/><path d="M62 31h59M62 43h45M62 55h34" stroke="white" strokeWidth="5" strokeLinecap="round"/><circle cx="132" cy="91" r="25" fill="#EEDCC9"/><path d="m122 91 7 7 14-16" stroke="#674237" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/></svg>
        </div>
        <span className="guide-kicker">НАЙДЁМ ОТВЕТ ВМЕСТЕ</span>
        <h2>Одна задача — первый шаг</h2>
        <p>Выберите тему, которая сейчас важна для вашего бизнеса.</p>
        <ol className="journey-list" aria-label="Как это работает">
          <li><span>01</span><div><strong>Расскажите о задаче</strong><small>Выберите вариант или напишите свой</small></div></li>
          <li><span>02</span><div><strong>Посмотрите материалы</strong><small>Пока доступны примеры</small></div></li>
        </ol>
      </aside>
    </div>
  )
}
