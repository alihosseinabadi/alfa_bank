import { useMemo, useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import type { PageContext } from '../components/Layout'
import { loadAnswers, saveAnswers } from '../services/account'
import type { Answers } from '../services/account'

type Step = {
  id: keyof Omit<Answers, 'note'>
  title: string
  hint: string
  options: string[]
  allowCustom?: boolean
}

const steps: Step[] = [
  {
    id: 'goal',
    title: 'Какая задача сейчас главная?',
    hint: 'Выберите один вариант — от него зависит подборка материалов.',
    options: ['Найти клиентов', 'Разобраться с финансами', 'Нанять сотрудника', 'Оптимизировать налоги', 'Систематизировать процессы'],
    allowCustom: true,
  },
  {
    id: 'industry',
    title: 'В какой сфере вы работаете?',
    hint: 'Это помогает подобрать примеры ближе к вашей отрасли.',
    options: ['Услуги', 'Торговля', 'Производство', 'IT', 'Общепит', 'Другое'],
  },
  {
    id: 'stage',
    title: 'На какой стадии бизнес?',
    hint: 'От стадии зависит, что важнее: запуск или рост.',
    options: ['Идея', 'Запускаю бизнес', 'Действующий бизнес', 'Масштабируюсь'],
  },
  {
    id: 'experience',
    title: 'Сколько у вас опыта?',
    hint: 'Мы не оцениваем — просто подбираем формулировки понятнее.',
    options: ['Нет опыта', 'До года', '1–3 года', 'Больше 3 лет'],
  },
  {
    id: 'difficulty',
    title: 'Что мешает больше всего?',
    hint: 'Этот ответ попадёт в статус профиля и в рекомендации.',
    options: ['Не хватает времени', 'Не хватает денег', 'Нет системы', 'Боюсь ошибиться', 'Пока не знаю'],
  },
]

const totalSteps = steps.length + 1

export default function Start() {
  const navigate = useNavigate()
  const { setProfile } = useOutletContext<PageContext>()
  const [answers, setAnswers] = useState<Answers>(loadAnswers)
  const [index, setIndex] = useState(0)
  const [custom, setCustom] = useState('')
  const [error, setError] = useState('')

  const step = steps[index]
  const isNoteStep = index === steps.length
  const progress = Math.round(((index + 1) / totalSteps) * 100)
  const canContinue = useMemo(() => {
    if (isNoteStep) return answers.note.trim().length >= 10
    return answers[step.id].trim().length > 0
  }, [answers, index, isNoteStep, step])

  function choose(value: string) {
    setAnswers((current) => ({ ...current, [step.id]: value }))
    setCustom('')
    setError('')
  }

  function next() {
    if (!canContinue) {
      setError(isNoteStep ? 'Опишите ситуацию хотя бы в 10 символах — это нужно для точной подборки.' : 'Выберите вариант, чтобы продолжить.')
      return
    }
    setError('')
    if (index < steps.length) { setIndex(index + 1); return }
    saveAnswers(answers)
    setProfile({
      goal: answers.goal,
      industry: answers.industry,
      stage: answers.stage,
      experience: answers.experience,
      difficulty: answers.difficulty,
      note: answers.note,
    })
    navigate('/dashboard', { replace: true })
  }

  return (
    <div className="wizard">
      <div className="wizard-main">
        <div className="wizard-head">
          <div>
            <span className="wizard-kicker">АНКЕТА · ШАГ {index + 1} ИЗ {totalSteps}</span>
            <h1>{isNoteStep ? 'Опишите ситуацию своими словами' : step.title}</h1>
            <p>{isNoteStep ? 'Одно-два предложения: что происходит и что хотелось бы изменить.' : step.hint}</p>
          </div>
          <span className="wizard-badge" aria-hidden="true">{progress}%</span>
        </div>

        <div className="wizard-progress" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100} aria-label="Прогресс анкеты">
          <span style={{ width: `${progress}%` }} />
        </div>

        {!isNoteStep && (
          <div className={`wizard-options ${step.options.length > 4 ? 'is-dense' : ''}`} role="radiogroup" aria-label={step.title}>
            {step.options.map((option, position) => (
              <button
                key={option}
                type="button"
                role="radio"
                aria-checked={answers[step.id] === option}
                className={`wizard-option ${answers[step.id] === option ? 'is-selected' : ''}`}
                onClick={() => choose(option)}
              >
                <span className="wizard-option-mark" aria-hidden="true">{String.fromCharCode(65 + position)}</span>
                <span>{option}</span>
                <span className="wizard-check" aria-hidden="true">✓</span>
              </button>
            ))}

            {step.allowCustom && (
              <div className="wizard-custom">
                <input
                  value={custom}
                  placeholder="Свой вариант: например, выйти на маркетплейсы"
                  maxLength={90}
                  onChange={(event) => {
                    const value = event.target.value
                    setCustom(value)
                    setAnswers((current) => ({ ...current, goal: value }))
                    setError('')
                  }}
                />
                <small>Можно выбрать готовый вариант выше или написать свой.</small>
              </div>
            )}
          </div>
        )}

        {isNoteStep && (
          <div className="wizard-note">
            <textarea
              value={answers.note}
              rows={5}
              maxLength={280}
              placeholder="Например: продаю мебель в интернете, клиенты приходят случайно, хочу стабильный поток заявок"
              onChange={(event) => { setAnswers((current) => ({ ...current, note: event.target.value })); setError('') }}
            />
            <small>{answers.note.trim().length}/280 · осталось ответить и открыть дашборд</small>
          </div>
        )}

        {error && <p className="wizard-error" role="alert">{error}</p>}

        <div className="wizard-actions">
          <button className="wizard-back" type="button" onClick={() => (index === 0 ? navigate('/auth') : setIndex(index - 1))}>
            ← Назад
          </button>
          <button className="wizard-next" type="button" onClick={next} disabled={!canContinue}>
            {index === steps.length ? 'Открыть дашборд →' : 'Далее →'}
          </button>
        </div>
        <p className="wizard-footnote">Ответы хранятся только в этом браузере. Демо-подборка не является консультацией.</p>
      </div>

      <aside className="wizard-aside">
        <span className="wizard-aside-kicker">ВАШ ПРОФИЛЬ</span>
        <h2>Что мы уже знаем</h2>
        <ul className="wizard-summary">
          {steps.map((item, position) => {
            const value = answers[item.id]
            const done = value.trim().length > 0
            return (
              <li key={item.id} className={done ? 'is-done' : position === index ? 'is-current' : ''}>
                <span className="wizard-dot" aria-hidden="true">{done ? '✓' : position + 1}</span>
                <div>
                  <strong>{item.title}</strong>
                  <small>{done ? value : position === index ? 'Отвечаем сейчас' : 'Ещё не отвечено'}</small>
                </div>
              </li>
            )
          })}
          <li className={answers.note.trim().length >= 10 ? 'is-done' : index === steps.length ? 'is-current' : ''}>
            <span className="wizard-dot" aria-hidden="true">{answers.note.trim().length >= 10 ? '✓' : steps.length + 1}</span>
            <div><strong>Ситуация своими словами</strong><small>{answers.note.trim() || (index === steps.length ? 'Отвечаем сейчас' : 'Ещё не отвечено')}</small></div>
          </li>
        </ul>
        <p className="wizard-aside-note">6 вопросов · около 2 минут · без загрузки файлов</p>
      </aside>
    </div>
  )
}
