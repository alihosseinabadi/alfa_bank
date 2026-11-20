import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Link, useNavigate, useOutletContext } from 'react-router-dom'
import type { PageContext } from '../components/Layout'
import { loadAnswers, profileReadiness, resetLocalProfile, saveAnswers } from '../services/account'
import type { Answers } from '../services/account'
import { loadLearning, touchToday } from '../services/learning'

type SingleStep = {
  kind: 'single'
  id: 'goal' | 'position' | 'experience' | 'difficulty'
  title: string
  hint: string
  options: string[]
  allowCustom?: boolean
}

type Step =
  | SingleStep
  | { kind: 'company'; title: string; hint: string }
  | { kind: 'interests'; title: string; hint: string }
  | { kind: 'rhythm'; title: string; hint: string }
  | { kind: 'note'; title: string; hint: string }

const steps: Step[] = [
  {
    kind: 'single', id: 'goal',
    title: 'Какая задача сейчас главная?',
    hint: 'Один фокус на ближайший месяц. От него зависит первая подборка и ежедневные вопросы.',
    options: ['Найти клиентов', 'Разобраться с финансами', 'Нанять сотрудника', 'Оптимизировать налоги', 'Систематизировать процессы', 'Запустить новый продукт'],
    allowCustom: true,
  },
  {
    kind: 'single', id: 'position',
    title: 'Какова ваша роль в бизнесе?',
    hint: 'Это определяет угол подачи: собственнику — про решения, специалисту — про инструменты.',
    options: ['Владелец или совладелец', 'ИП или самозанятый', 'Генеральный директор', 'Руководитель направления', 'Специалист или эксперт', 'Начинаю с нуля'],
  },
  { kind: 'company', title: 'Расскажите о компании', hint: 'Сфера и стадия помогают подобрать примеры и уровень сложности.' },
  {
    kind: 'single', id: 'experience',
    title: 'Сколько у вас предпринимательского опыта?',
    hint: 'Мы не оцениваем — подбираем формулировки и темп понятнее.',
    options: ['Нет опыта', 'До года', '1–3 года', 'Больше 3 лет'],
  },
  { kind: 'interests', title: 'Что вам интересно изучать?', hint: 'Выберите до четырёх направлений. Они станут основой персональных рекомендаций.' },
  { kind: 'rhythm', title: 'Сколько времени и в каком формате?', hint: 'Реалистичный ритм важнее амбициозного. План подстроится под вас.' },
  {
    kind: 'single', id: 'difficulty',
    title: 'Что мешает больше всего?',
    hint: 'Это ограничение попадёт в профиль и повлияет на следующие шаги.',
    options: ['Не хватает времени', 'Не хватает денег', 'Нет системы', 'Боюсь ошибиться', 'Слишком много задач сразу', 'Пока не знаю'],
  },
  { kind: 'note', title: 'Опишите ситуацию своими словами', hint: 'Одно-два предложения: что происходит сейчас и что хотелось бы изменить.' },
]

const interests = [
  'Маркетинг и клиенты',
  'Продажи и переговоры',
  'Финансы и юнит-экономика',
  'Управление командой',
  'Данные и автоматизация',
  'Запуск и инвестиции',
]

const industries = ['Услуги', 'Торговля', 'Производство', 'IT', 'Общепит', 'Другое']
const stages = ['Идея', 'Запускаю бизнес', 'Действующий бизнес', 'Масштабируюсь']
const hourOptions = [
  { value: 2, label: '2 часа', note: 'Короткие материалы' },
  { value: 4, label: '4 часа', note: 'Спокойный темп' },
  { value: 7, label: '7 часов', note: 'Заметный прогресс' },
  { value: 12, label: '12+ часов', note: 'Интенсив' },
]
const formats = [
  { value: 'Короткие статьи', note: '5–10 минут' },
  { value: 'Видео', note: 'Смотреть и слушать' },
  { value: 'Практика', note: 'Делать руками' },
  { value: 'Вебинары', note: 'Живой разбор' },
]

const interestFocus: Record<string, string> = {
  'Маркетинг и клиенты': 'канал привлечения и позиционирование',
  'Продажи и переговоры': 'воронка и работа с возражениями',
  'Финансы и юнит-экономика': 'деньги, CAC и окупаемость',
  'Управление командой': 'процессы и роли без ручного управления',
  'Данные и автоматизация': 'метрики и рутина, которую можно убрать',
  'Запуск и инвестиции': 'гипотезы, питч и доказательства спроса',
}

function profileReadinessFrom(answers: Answers): number {
  return profileReadiness(answers)
}

function directions(count: number): string {
  const remainder = count % 100
  if (remainder >= 11 && remainder <= 14) return 'направлений'
  const last = count % 10
  if (last === 1) return 'направление'
  if (last >= 2 && last <= 4) return 'направления'
  return 'направлений'
}

function archetype(answers: Answers): string {
  const position = answers.position ?? ''
  if (position.includes('Владелец') || position.includes('ИП')) return 'Собственник'
  if (position.includes('Генеральный')) return 'Руководитель бизнеса'
  if (position.includes('Руководитель')) return 'Руководитель направления'
  if (position.includes('Специалист')) return 'Эксперт-практик'
  if (position.includes('Начинаю')) return 'Основатель на старте'
  return 'Предприниматель'
}

function pace(answers: Answers): string {
  const hours = answers.hoursPerWeek ?? 0
  if (hours <= 2) return '2 часа в неделю · один короткий шаг за раз'
  if (hours <= 4) return '4 часа в неделю · два занятия по 2 часа'
  if (hours <= 7) return '7 часов в неделю · стабильный прогресс'
  return '12+ часов в неделю · интенсивный трек'
}

function needs(answers: Answers): { title: string; detail: string }[] {
  const out: { title: string; detail: string }[] = []
  const focus = (answers.interests ?? []).map((item) => interestFocus[item]).filter(Boolean).slice(0, 2)
  for (const item of focus) out.push({ title: `Усилить: ${item}`, detail: 'Это направление вы выбрали сами — начнём с него в подборке и ежедневных вопросах.' })
  if (answers.difficulty) out.push({ title: `Ограничение: ${answers.difficulty.toLocaleLowerCase('ru')}`, detail: 'План будет короткими шагами, чтобы не упираться в это ограничение.' })
  if (!answers.note || answers.note.trim().length < 30) out.push({ title: 'Добавить конкретики в описание', detail: 'Чем точнее ситуация, тем точнее ML-ранжирование каталога.' })
  if ((answers.interests ?? []).length === 0) out.push({ title: 'Выбрать интересующие темы', detail: 'Без интересов подборка опирается только на задачу.' })
  return out.slice(0, 3)
}

/** The human-readable answer that belongs in the user's chat bubble. */
function answerFor(step: Step, answers: Answers): string {
  switch (step.kind) {
    case 'single': return (answers[step.id] ?? '').trim()
    case 'company': return [answers.industry, answers.stage].filter(Boolean).join(' · ')
    case 'interests': return (answers.interests ?? []).join(' · ')
    case 'rhythm': return [
      answers.hoursPerWeek ? `${answers.hoursPerWeek} ч/нед` : '',
      answers.format,
    ].filter(Boolean).join(' · ')
    case 'note': return answers.note.trim()
  }
}

/** A short reaction from the mentor before the next question. */
function acknowledge(previous: Step, answers: Answers): string {
  switch (previous.kind) {
    case 'single':
      if (previous.id === 'goal') return `Понял задачу: «${answers.goal}».`
      if (previous.id === 'position') return `Записал: ${answers.position?.toLocaleLowerCase('ru')}.`
      if (previous.id === 'experience') return `Опыт: ${answers.experience?.toLocaleLowerCase('ru')}. Подберу подходящую глубину.`
      return `Понял ограничение: «${answers.difficulty?.toLocaleLowerCase('ru')}».`
    case 'company':
      return `Записал: ${answers.industry}, стадия «${answers.stage}».`
    case 'interests':
      return `Отметил ${(answers.interests ?? []).length} ${directions((answers.interests ?? []).length)} — они попадут в подборку и вопросы дня.`
    case 'rhythm':
      return `Ритм: ${answers.hoursPerWeek} ч в неделю, формат «${answers.format}».`
    case 'note':
      return 'Спасибо, это поможет точнее ранжировать каталог.'
  }
}

export default function Start() {
  const navigate = useNavigate()
  const { setProfile, resetProfile } = useOutletContext<PageContext>()
  const [answers, setAnswers] = useState<Answers>(loadAnswers)
  const [index, setIndex] = useState(0)
  const [custom, setCustom] = useState('')
  const [error, setError] = useState('')
  const threadRef = useRef<HTMLDivElement | null>(null)

  const isAnalysis = index === steps.length
  const step = steps[Math.min(index, steps.length - 1)]
  const progress = Math.round((Math.min(index + 1, steps.length) / (steps.length + 1)) * 100)

  const canContinue = useMemo(() => {
    if (isAnalysis) return true
    switch (step.kind) {
      case 'single': return (answers[step.id] ?? '').trim().length > 0
      case 'company': return !!answers.industry && !!answers.stage
      case 'interests': return (answers.interests ?? []).length > 0
      case 'rhythm': return (answers.hoursPerWeek ?? 0) > 0 && !!answers.format
      case 'note': return answers.note.trim().length >= 10
    }
  }, [answers, isAnalysis, step])

  // Keep the newest message visible inside the thread, not by scrolling the page.
  useEffect(() => {
    const node = threadRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [index])

  function patch(next: Partial<Answers>) {
    setAnswers((current) => ({ ...current, ...next }))
    setError('')
  }

  function choose(value: string) {
    if (step.kind !== 'single') return
    patch({ [step.id]: value } as Partial<Answers>)
    setCustom('')
  }

  function toggleInterest(value: string) {
    const current = answers.interests ?? []
    if (current.includes(value)) {
      patch({ interests: current.filter((item) => item !== value) })
      return
    }
    if (current.length >= 4) { setError('Можно выбрать не больше четырёх направлений.'); return }
    patch({ interests: [...current, value] })
  }

  function next() {
    if (!canContinue) {
      setError(step.kind === 'note' ? 'Опишите ситуацию хотя бы в 10 символах — это нужно для точной подборки.' : 'Ответьте на вопрос, чтобы продолжить.')
      return
    }
    setError('')
    if (index < steps.length) { setIndex(index + 1); return }
    finish()
  }

  function finish() {
    saveAnswers(answers)
    setProfile({
      goal: answers.goal,
      industry: answers.industry,
      stage: answers.stage,
      experience: answers.experience,
      difficulty: answers.difficulty,
      note: answers.note,
      position: answers.position,
      interests: answers.interests,
      hoursPerWeek: answers.hoursPerWeek,
      format: answers.format,
    })
    touchToday(loadLearning())
    navigate('/dashboard', { replace: true })
  }

  function startFresh() {
    resetLocalProfile()
    resetProfile()
    setAnswers(loadAnswers())
    setCustom('')
    setIndex(0)
    setError('')
  }

  const readiness = profileReadinessFrom(answers)

  return (
    <div className={isAnalysis ? 'pr-analysis' : 'pr-onb'}>
      <div className={isAnalysis ? 'pr-card pr-analysis-hero' : 'pr-card pr-chat-card pr-onb-chat'}>
        {!isAnalysis ? (
          <>
            <header className="pr-chat-head">
              <span className="pr-chat-avatar" aria-hidden="true">АК</span>
              <div>
                <h1>Наставник Альфа-Курса</h1>
                <p>онлайн · собираем профиль · шаг {index + 1} из {steps.length}</p>
              </div>
              <span className="pr-onb-count" aria-label={`Профиль заполнен на ${readiness} процентов`}>{readiness}%</span>
            </header>

            <div className="pr-onb-progress is-chat" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100} aria-label="Прогресс разговора">
              {steps.map((item, position) => (
                <span key={position} className={position < index ? 'is-done' : position === index ? 'is-current' : ''} />
              ))}
            </div>

            <div className="pr-chat-body pr-onb-thread" ref={threadRef} aria-live="polite">
              <div className="pr-msg">
                <span className="pr-msg-mark" aria-hidden="true">АК</span>
                <div className="pr-bubble">
                  <p>Привет! Я помогу собрать профиль за пару минут. Задам {steps.length} коротких вопросов — отвечайте кнопкой или своими словами.</p>
                  <p className="pr-bubble-note">Ответы остаются в этом браузере. Подборка — демонстрация рекомендательной системы, не консультация.</p>
                </div>
              </div>

              {steps.map((item, position) => {
                if (position > index) return null
                const answer = answerFor(item, answers)
                return (
                  <Fragment key={position}>
                    <div className="pr-msg">
                      <span className="pr-msg-mark" aria-hidden="true">АК</span>
                      <div className="pr-bubble">
                        {position > 0 && <p className="pr-chat-ack">{acknowledge(steps[position - 1], answers)}</p>}
                        <p className="pr-chat-q">{item.title}</p>
                        {position === index && <p className="pr-bubble-note">{item.hint}</p>}
                      </div>
                    </div>
                    {position < index && answer && (
                      <div className="pr-msg is-user">
                        <span className="pr-msg-mark" aria-hidden="true">Вы</span>
                        <div className="pr-bubble">{answer}</div>
                      </div>
                    )}
                  </Fragment>
                )
              })}
            </div>

            <div className="pr-chat-compose">
              {step.kind === 'single' && (
                <div className={`pr-chat-suggest is-inline ${step.options.length > 4 ? 'is-dense' : ''}`} role="radiogroup" aria-label={step.title}>
                  {step.options.map((option) => (
                    <button
                      key={option}
                      type="button"
                      role="radio"
                      aria-checked={answers[step.id] === option}
                      className={`pr-suggest ${answers[step.id] === option ? 'is-selected' : ''}`}
                      onClick={() => choose(option)}
                    >
                      {option}
                    </button>
                  ))}
                </div>
              )}

              {step.kind === 'single' && step.allowCustom && (
                <div className="pr-chat-custom">
                  <input
                    value={custom}
                    placeholder="Или своими словами: например, выйти на маркетплейсы"
                    maxLength={90}
                    aria-label="Своя формулировка задачи"
                    onChange={(event) => {
                      const value = event.target.value
                      setCustom(value)
                      patch({ goal: value })
                    }}
                  />
                  <small>Можно выбрать готовый вариант или написать свой.</small>
                </div>
              )}

              {step.kind === 'company' && (
                <>
                  <div className="pr-chat-group">
                    <span>Сфера</span>
                    <div className="pr-chat-suggest is-inline" role="radiogroup" aria-label="Сфера">
                      {industries.map((option) => (
                        <button key={option} type="button" role="radio" aria-checked={answers.industry === option} className={`pr-suggest ${answers.industry === option ? 'is-selected' : ''}`} onClick={() => patch({ industry: option })}>
                          {option}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="pr-chat-group">
                    <span>Стадия</span>
                    <div className="pr-chat-suggest is-inline" role="radiogroup" aria-label="Стадия бизнеса">
                      {stages.map((option) => (
                        <button key={option} type="button" role="radio" aria-checked={answers.stage === option} className={`pr-suggest ${answers.stage === option ? 'is-selected' : ''}`} onClick={() => patch({ stage: option })}>
                          {option}
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {step.kind === 'interests' && (
                <div className="pr-chat-suggest is-inline" role="group" aria-label="Интересы">
                  {interests.map((option) => {
                    const on = (answers.interests ?? []).includes(option)
                    return (
                      <button
                        key={option}
                        type="button"
                        aria-pressed={on}
                        title={interestFocus[option]}
                        className={`pr-suggest ${on ? 'is-selected' : ''}`}
                        onClick={() => toggleInterest(option)}
                      >
                        {on ? '✓ ' : ''}{option}
                      </button>
                    )
                  })}
                </div>
              )}

              {step.kind === 'rhythm' && (
                <>
                  <div className="pr-chat-group">
                    <span>Свободное время в неделю</span>
                    <div className="pr-chat-suggest is-inline" role="radiogroup" aria-label="Часов в неделю">
                      {hourOptions.map((option) => (
                        <button key={option.value} type="button" role="radio" aria-checked={answers.hoursPerWeek === option.value} className={`pr-suggest ${answers.hoursPerWeek === option.value ? 'is-selected' : ''}`} onClick={() => patch({ hoursPerWeek: option.value })}>
                          {option.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="pr-chat-group">
                    <span>Удобный формат</span>
                    <div className="pr-chat-suggest is-inline" role="radiogroup" aria-label="Формат обучения">
                      {formats.map((option) => (
                        <button key={option.value} type="button" role="radio" aria-checked={answers.format === option.value} className={`pr-suggest ${answers.format === option.value ? 'is-selected' : ''}`} onClick={() => patch({ format: option.value })}>
                          {option.value}
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {step.kind === 'note' && (
                <div className="pr-chat-custom">
                  <textarea
                    value={answers.note}
                    rows={4}
                    maxLength={280}
                    aria-label="Ситуация своими словами"
                    placeholder="Например: продаю мебель в интернете, клиенты приходят случайно, хочу стабильный поток заявок"
                    onChange={(event) => patch({ note: event.target.value })}
                  />
                  <small>{answers.note.trim().length}/280 · чем конкретнее, тем точнее подборка</small>
                </div>
              )}

              {error && <p className="pr-error" role="alert">{error}</p>}

              <div className="pr-chat-actions">
                <button className="pr-btn is-ghost is-small" type="button" onClick={() => (index === 0 ? navigate('/auth') : setIndex(index - 1))}>
                  ← {index === 0 ? 'Выйти' : 'Назад'}
                </button>
                <button className="pr-btn is-red is-small" type="button" onClick={next} disabled={!canContinue}>
                  {index === steps.length - 1 ? 'Проанализировать профиль →' : 'Отправить →'}
                </button>
              </div>
            </div>
          </>
        ) : (
          <>
            <span className="pr-eyebrow">Профиль готов · предварительный анализ</span>
            <h1 className="pr-title" style={{ fontSize: 'clamp(26px, 3vw, 38px)' }}>
              {answers.goal ? `Фокус: ${answers.goal.toLocaleLowerCase('ru')}` : 'Ваш персональный профиль'}
            </h1>
            <p className="pr-sub">
              На основе ответов мы собрали стартовый профиль и определили, с чего начать.
              Дальше профиль будет уточняться ежедневными вопросами и вашими действиями.
            </p>

            <div className="pr-analysis-score">
              <div className="pr-ring" style={{ ['--value' as string]: readiness } as CSSProperties}>
                <div>
                  <strong>{readiness}%</strong>
                  <small>готовность</small>
                </div>
              </div>
              <div>
                <h3>{archetype(answers)} · {answers.stage || 'стадия не указана'}</h3>
                <p>
                  {answers.position || 'Роль не указана'}. {answers.industry || 'Сфера не указана'}.
                  {' '}Рекомендуемый ритм: {pace(answers)}.
                </p>
              </div>
            </div>

            <div className="pr-analysis-grid">
              <div className="pr-analysis-cell">
                <span>Архетип</span>
                <strong>{archetype(answers)}</strong>
                <p>Угол подачи и примеры подстроены под вашу роль.</p>
              </div>
              <div className="pr-analysis-cell">
                <span>Опыт</span>
                <strong>{answers.experience || 'Не указан'}</strong>
                <p>Влияет на сложность и глубину материалов.</p>
              </div>
              <div className="pr-analysis-cell">
                <span>Ритм</span>
                <strong>{answers.hoursPerWeek ? `${answers.hoursPerWeek} ч / неделю` : 'Не указан'}</strong>
                <p>{answers.format || 'Формат не выбран'} — основной способ подачи.</p>
              </div>
              <div className="pr-analysis-cell">
                <span>Интересы</span>
                <strong>{(answers.interests ?? []).length ? `${(answers.interests ?? []).length} направления` : 'Не выбраны'}</strong>
                <p>{(answers.interests ?? []).join(' · ') || 'Добавьте интересы в анкете.'}</p>
              </div>
            </div>

            <div style={{ marginTop: 22 }}>
              <span className="pr-eyebrow">Что профилю действительно нужно</span>
              <div className="pr-needs">
                {needs(answers).map((item, position) => (
                  <div className="pr-need" key={item.title}>
                    <span aria-hidden="true">{String(position + 1).padStart(2, '0')}</span>
                    <div><strong>{item.title}</strong><small>{item.detail}</small></div>
                  </div>
                ))}
              </div>
            </div>

            <div className="pr-analysis-actions">
              <button className="pr-btn is-red" type="button" onClick={finish}>Открыть мой план →</button>
              <button className="pr-btn is-ghost" type="button" onClick={() => setIndex(steps.length - 1)}>← Изменить ответы</button>
            </div>
            <p className="pr-onb-count-note" style={{ marginTop: 14 }}>
              Анализ собран по правилам демо-коучинга, а не обученной моделью. Рекомендации материалов —
              результат гибридного поиска BM25 + dense-векторы и prior-ранжирования по вашему профилю.
            </p>
          </>
        )}
      </div>

      {!isAnalysis && (
        <aside className="pr-onb-side">
          <div className="pr-card is-pad">
            <span className="pr-eyebrow">Ваш профиль</span>
            <h2 className="pr-title-sm">Что мы уже знаем</h2>
            <ul className="pr-onb-list">
              <li className={answers.goal.trim() ? 'is-done' : index === 0 ? 'is-current' : ''}>
                <span className="pr-onb-dot" aria-hidden="true">{answers.goal.trim() ? '✓' : '1'}</span>
                <div><strong>Главная задача</strong><small>{answers.goal || (index === 0 ? 'Отвечаем сейчас' : 'Ещё не отвечено')}</small></div>
              </li>
              <li className={answers.position ? 'is-done' : index === 1 ? 'is-current' : ''}>
                <span className="pr-onb-dot" aria-hidden="true">{answers.position ? '✓' : '2'}</span>
                <div><strong>Роль</strong><small>{answers.position || (index === 1 ? 'Отвечаем сейчас' : 'Ещё не отвечено')}</small></div>
              </li>
              <li className={answers.industry && answers.stage ? 'is-done' : index === 2 ? 'is-current' : ''}>
                <span className="pr-onb-dot" aria-hidden="true">{answers.industry && answers.stage ? '✓' : '3'}</span>
                <div><strong>Компания</strong><small>{[answers.industry, answers.stage].filter(Boolean).join(' · ') || (index === 2 ? 'Отвечаем сейчас' : 'Ещё не отвечено')}</small></div>
              </li>
              <li className={answers.experience ? 'is-done' : index === 3 ? 'is-current' : ''}>
                <span className="pr-onb-dot" aria-hidden="true">{answers.experience ? '✓' : '4'}</span>
                <div><strong>Опыт</strong><small>{answers.experience || (index === 3 ? 'Отвечаем сейчас' : 'Ещё не отвечено')}</small></div>
              </li>
              <li className={(answers.interests ?? []).length ? 'is-done' : index === 4 ? 'is-current' : ''}>
                <span className="pr-onb-dot" aria-hidden="true">{(answers.interests ?? []).length ? '✓' : '5'}</span>
                <div><strong>Интересы</strong><small>{(answers.interests ?? []).join(' · ') || (index === 4 ? 'Отвечаем сейчас' : 'Ещё не отвечено')}</small></div>
              </li>
              <li className={answers.hoursPerWeek && answers.format ? 'is-done' : index === 5 ? 'is-current' : ''}>
                <span className="pr-onb-dot" aria-hidden="true">{answers.hoursPerWeek && answers.format ? '✓' : '6'}</span>
                <div><strong>Ритм и формат</strong><small>{[answers.hoursPerWeek ? `${answers.hoursPerWeek} ч/нед` : '', answers.format].filter(Boolean).join(' · ') || (index === 5 ? 'Отвечаем сейчас' : 'Ещё не отвечено')}</small></div>
              </li>
              <li className={answers.difficulty ? 'is-done' : index === 6 ? 'is-current' : ''}>
                <span className="pr-onb-dot" aria-hidden="true">{answers.difficulty ? '✓' : '7'}</span>
                <div><strong>Ограничение</strong><small>{answers.difficulty || (index === 6 ? 'Отвечаем сейчас' : 'Ещё не отвечено')}</small></div>
              </li>
              <li className={answers.note.trim().length >= 10 ? 'is-done' : index === 7 ? 'is-current' : ''}>
                <span className="pr-onb-dot" aria-hidden="true">{answers.note.trim().length >= 10 ? '✓' : '8'}</span>
                <div><strong>Ситуация</strong><small>{answers.note.trim() || (index === 7 ? 'Отвечаем сейчас' : 'Ещё не отвечено')}</small></div>
              </li>
            </ul>
            <p className="pr-onb-aside-note">Разговор · {steps.length} вопросов · около 3 минут · без загрузки файлов</p>
          </div>

          <div className="pr-card is-sand" style={{ padding: 18 }}>
            <span className="pr-eyebrow">Начать заново</span>
            <p className="pr-small" style={{ marginTop: 8 }}>
              Очистить ответы и локальный прогресс, чтобы пройти анкету как новый пользователь.
            </p>
            <button className="pr-btn is-ghost is-small" type="button" onClick={startFresh} style={{ marginTop: 12 }}>
              Сбросить профиль
            </button>
            <p className="pr-onb-aside-note">
              Уже есть профиль? <Link to="/dashboard">Вернуться на главную</Link>
            </p>
          </div>
        </aside>
      )}
    </div>
  )
}
