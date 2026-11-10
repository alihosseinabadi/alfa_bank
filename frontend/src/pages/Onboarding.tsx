import { useState } from 'react'
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
  const [error, setError] = useState('')

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!goal) {
      setError('Выберите задачу, чтобы продолжить.')
      return
    }

    setProfile({ goal, industry, stage, experience })
    navigate('/feed')
  }

  function handleSkip() {
    setProfile(null)
    navigate('/feed')
  }

  return (
    <div className="dashboard-grid">
      <aside className="profile-card panel">
        <span className="profile-avatar" aria-hidden="true">А</span>
        <span className="profile-badge">Добро пожаловать</span>
        <h2>Рады знакомству!</h2>
        <p>
          Расскажите немного о себе, и мы поможем найти подходящие материалы.
        </p>

        <div className="profile-tip">
          <span aria-hidden="true">✦</span>
          <p>Начать можно с одной задачи. Остальное заполнять необязательно.</p>
        </div>
      </aside>

      <section className="onboarding-panel">
        <div className="section-heading light-heading">
          <div>
            <span className="eyebrow">ВАШ ПЕРВЫЙ ШАГ</span>
            <h1>Подбор под вашу задачу</h1>
            <p>Выберите, чему хотите научиться в первую очередь.</p>
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

            {error && <p className="form-error" role="alert">{error}</p>}
          </fieldset>

          <div className="form-divider" />

          <div className="form-intro">
            <h2>Немного о вас</h2>
            <p>Эти поля помогут сделать подборку точнее.</p>
          </div>

          <div className="form-fields">
            <label>
              Сфера бизнеса
              <select value={industry} onChange={(event) => setIndustry(event.target.value)}>
                <option value="">Выберите сферу</option>
                <option value="Услуги">Услуги</option>
                <option value="Торговля">Торговля</option>
                <option value="Производство">Производство</option>
                <option value="Другая">Другая</option>
              </select>
            </label>

            <label>
              Стадия бизнеса
              <select value={stage} onChange={(event) => setStage(event.target.value)}>
                <option value="">Выберите стадию</option>
                <option value="Планирую запуск">Планирую запуск</option>
                <option value="Запускаю бизнес">Запускаю бизнес</option>
                <option value="Развиваю бизнес">Развиваю бизнес</option>
              </select>
            </label>

            <label>
              Опыт
              <select value={experience} onChange={(event) => setExperience(event.target.value)}>
                <option value="">Выберите опыт</option>
                <option value="Начинаю">Начинаю</option>
                <option value="Есть опыт">Есть опыт</option>
                <option value="Опытный предприниматель">Опытный предприниматель</option>
              </select>
            </label>
          </div>

          <div className="form-actions">
            <button className="button button-primary" type="submit">
              Подобрать материалы <span aria-hidden="true">→</span>
            </button>

            <button className="text-button" type="button" onClick={handleSkip}>
              Пропустить анкету
            </button>
          </div>
        </form>
      </section>
    </div>
  )
}