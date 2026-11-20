import { useEffect, useMemo, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { PageContext } from '../components/Layout'
import { profileReadiness } from '../services/account'
import { rankCatalogue } from '../services/rankingApi'
import type { RankedCourse } from '../services/rankingApi'
import {
  activitySeries, answeredToday, completeCourse, findQuestion, guessCategory, loadLearning, localFit,
  monthCells, pickDailyQuestion, recordAnswer, roadmapFrom, topicQueryTerm, touchToday,
} from '../services/learning'
import type { LearningState } from '../services/learning'

const formatRu: Record<string, string> = {
  course: 'Курс', article: 'Статья', document: 'Документ', webinar: 'Вебинар',
  podcast: 'Подкаст', glossary: 'Глоссарий', calculator: 'Калькулятор',
}

const monthNames = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
const weekNames = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']

function priceLabel(value: number | null): string {
  if (value === null) return 'Цена не указана'
  if (value === 0) return 'Бесплатно'
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(value)} ₽`
}

function plural(count: number, one: string, few: string, many: string): string {
  const remainder = count % 100
  if (remainder >= 11 && remainder <= 14) return many
  const last = count % 10
  if (last === 1) return one
  if (last >= 2 && last <= 4) return few
  return many
}

export default function Dashboard() {
  const { account, profile, setProfile } = useOutletContext<PageContext>()
  const [learning, setLearning] = useState<LearningState>(() => touchToday(loadLearning()))
  const [items, setItems] = useState<RankedCourse[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'empty' | 'error'>('loading')

  const readiness = useMemo(() => profileReadiness({
    goal: profile?.goal ?? '',
    industry: profile?.industry ?? '',
    stage: profile?.stage ?? '',
    experience: profile?.experience ?? '',
    difficulty: profile?.difficulty ?? '',
    note: profile?.note ?? '',
    position: profile?.position ?? '',
    interests: profile?.interests ?? [],
    hoursPerWeek: profile?.hoursPerWeek ?? 0,
    format: profile?.format ?? '',
  }), [profile])

  useEffect(() => {
    let active = true
    if (!profile?.goal) { setStatus('empty'); return }
    setStatus('loading')
    const task = [profile.goal, topicQueryTerm(answeredToday(learning)?.topic)]
      .filter(Boolean).join('. ').slice(0, 300)
    rankCatalogue({
      task,
      profile: {
        business_stage: profile.stage || null,
        industry: profile.industry || null,
        experience: profile.experience || null,
      },
      constraints: profile.hoursPerWeek ? { available_time_minutes: profile.hoursPerWeek * 60 } : {},
      limit: 50,
    })
      .then((result) => {
        if (!active) return
        setItems(result.items)
        setStatus(result.items.length ? 'ready' : 'empty')
      })
      .catch(() => { if (active) setStatus('error') })
    return () => { active = false }
  }, [profile, learning.insight])

  // Retrieved items keep their real ML order. Everything else is ordered by the
  // labelled local heuristic, only to give the roadmap a sensible fallback.
  const ranked = useMemo(() => items.map((item) => ({
    ...item,
    displayFit: item.retrieved
      ? item.fitScore
      : localFit({
        title: item.title,
        category: guessCategory(item.title),
        duration_minutes: item.durationMinutes ?? 0,
      }, profile ?? {}),
  })), [items, profile])

  const ordered = useMemo(() => [...ranked].sort((a, b) =>
    Number(b.retrieved) - Number(a.retrieved) || b.displayFit - a.displayFit), [ranked])

  // The daily course slot should be a course when one is retrieved.
  const top = useMemo(() => (
    ordered.find((item) => item.retrieved && item.format === 'course')
    ?? ordered.find((item) => item.retrieved)
    ?? ordered.find((item) => item.format === 'course')
    ?? ordered[0]
  ), [ordered])
  const today = answeredToday(learning)
  const question = useMemo(() => pickDailyQuestion(profile ?? {}, learning), [profile, learning])
  const answeredQuestion = today ? findQuestion(today.questionId) : undefined
  const todayInsight = answeredQuestion?.options.find((option) => option.label === today?.answer)?.insight ?? learning.insight
  const activity = useMemo(() => activitySeries(learning, 14), [learning])
  const week = activity.slice(-7)
  const now = new Date()
  const month = monthCells(now.getFullYear(), now.getMonth(), learning)
  const goal = profile?.goal ?? ''
  const goalLabel = goal.replace(/[.?!]+$/, '')
  const completed = learning.completed.length

  function answer(label: string, insight: string) {
    const next = recordAnswer(learning, question, label, insight)
    setLearning(next)
    if (profile) {
      const note = [profile.note, insight].filter(Boolean).join(' ').slice(0, 280)
      setProfile({ ...profile, note })
    }
  }

  function markComplete(course: RankedCourse) {
    setLearning(completeCourse(learning, course.materialKey))
  }

  const roadmap = roadmapFrom(
    ordered.map((item) => ({ id: item.materialKey, title: item.title })),
    learning.completed,
  )

  const needs = [
    profile?.interests?.length
      ? { title: `Продолжить: ${profile.interests[0].toLocaleLowerCase('ru')}`, detail: 'Вы выбрали это направление — оно первым попадает в подборку и ежедневные вопросы.' }
      : { title: 'Уточнить интересы в анкете', detail: 'Профиль без интересов опирается только на формулировку задачи.' },
    profile?.difficulty
      ? { title: `Снять ограничение: ${profile.difficulty.toLocaleLowerCase('ru')}`, detail: 'План разбит на короткие шаги, чтобы ограничение не останавливало прогресс.' }
      : { title: 'Определить главное ограничение', detail: 'Оно поможет выбрать между быстрым результатом и системной работой.' },
    top
      ? { title: `Ближайший материал: ${top.title}`, detail: `Совпадение ${top.displayFit}% ${top.retrieved ? 'по ML-ранжированию' : '(оценка профиля, не ML)'}. Первый шаг уже выбран.` }
      : { title: 'Дождаться первой подборки', detail: 'Как только ML-сервис ответит, здесь появится конкретный следующий шаг.' },
  ]

  const isDoneToday = !!today
  const nextQuestion = question
  const firstName = account?.name?.trim().split(/\s+/)[0] ?? ''
  const hour = new Date().getHours()
  const greeting = hour < 6 ? 'Доброй ночи' : hour < 12 ? 'Доброе утро' : hour < 18 ? 'Добрый день' : 'Добрый вечер'
  const interest = profile?.interests?.[0]
  const personalLine = [
    interest ? `Учитываю ваш интерес «${interest.toLocaleLowerCase('ru')}».` : '',
    profile?.difficulty ? `И ограничение «${profile.difficulty.toLocaleLowerCase('ru')}».` : '',
  ].filter(Boolean).join(' ')

  return (
    <div className="pr-dash">
      <section className="pr-hero">
        <div>
          <span className="pr-eyebrow is-light">Личный план · демо</span>
          <h1>
            {account?.name ? <>Здравствуйте, <em>{account.name.split(' ')[0]}</em>.</> : <>Ваш следующий <em>шаг</em>.</>}
          </h1>
          <p>
            {goal
              ? <>Фокус профиля: <strong>{goalLabel.toLocaleLowerCase('ru')}</strong>. Ниже — материал дня, вопрос для уточнения профиля и план на неделю.</>
              : <>Профиль пока пуст. Пройдите восемь коротких вопросов, и здесь появится персональный план.</>}
          </p>
          <div className="pr-hero-actions">
            <Link className="pr-btn is-red" to="/feed">Смотреть все рекомендации →</Link>
            <Link className="pr-btn is-ghost" to="/coach">Спросить наставника</Link>
            <Link className="pr-btn is-ghost" to="/start">{profile ? 'Изменить профиль' : 'Заполнить профиль'}</Link>
          </div>
        </div>

        <div className="pr-hero-side">
          <div>
            <div className="pr-hero-side-top">
              <span>Готовность профиля</span>
              <strong>◆ live</strong>
            </div>
            <div style={{ marginTop: 12 }}>
              <div className="pr-meter">
                <div className="pr-meter-track"><span style={{ width: `${readiness}%` }} /></div>
                <span className="pr-meter-value">{readiness}%</span>
              </div>
              <p className="pr-small" style={{ marginTop: 10 }}>
                {readiness >= 80 ? 'Профиль достаточно полный для точной подборки.' : 'Добавьте ответы, чтобы ML точнее ранжировал каталог.'}
              </p>
            </div>
          </div>
          <div className="pr-hero-mini">
            <div><strong>{learning.streak}</strong><small>{plural(learning.streak, 'день', 'дня', 'дней')} подряд</small></div>
            <div><strong>{ranked.length || '—'}</strong><small>курсов в ранге</small></div>
            <div><strong>{completed}</strong><small>пройдено</small></div>
          </div>
        </div>
      </section>

      <div className="pr-kpis">
        <div className="pr-card pr-kpi">
          <span>Серия</span>
          <strong>{learning.streak}</strong>
          <small>{plural(learning.streak, 'день', 'дня', 'дней')} активности подряд</small>
        </div>
        <div className="pr-card pr-kpi is-accent">
          <span>Совпадение дня</span>
          <strong>{top ? `${top.displayFit}%` : '—'}</strong>
          <small>{top ? formatRu[top.format] ?? top.format : 'Ждём ответа ML-сервиса'}</small>
        </div>
        <div className="pr-card pr-kpi">
          <span>Время в обучении</span>
          <strong>{activity.reduce((sum, day) => sum + day.minutes, 0)}</strong>
          <small>минут синтетической активности за 14 дней</small>
        </div>
        <div className="pr-card pr-kpi">
          <span>Профиль</span>
          <strong>{readiness}%</strong>
          <small>заполнено полей анкеты</small>
        </div>
      </div>

      <div className="pr-dash-grid">
        <div className="pr-dash-stack">
          <section className="pr-card pr-course-hero" aria-labelledby="course-day-title">
            <div>
              <span className="pr-eyebrow">Курс дня · {top?.retrieved ? 'ML-подбор' : 'оценка профиля'}</span>
              <h2 id="course-day-title">
                {top ? top.title : status === 'loading' ? 'Ранжируем каталог…' : 'Пока нет материала дня'}
              </h2>
              <p>
                {top
                  ? top.reason
                  : status === 'error'
                    ? 'ML-сервис недоступен. Проверьте, что стек запущен, и обновите страницу.'
                    : 'Заполните профиль — и здесь появится курс с лучшим совпадением.'}
              </p>
              {top && (
                <>
                  <div className="pr-course-meta">
                    <span className="pr-chip">{formatRu[top.format] ?? top.format}</span>
                    {top.durationMinutes && <span className="pr-chip">{top.durationMinutes} мин</span>}
                    <span className="pr-chip">{priceLabel(top.listedPrice)}</span>
                    {top.mlRank && <span className="pr-chip is-green">ML rank #{top.mlRank}</span>}
                    {!top.retrieved && <span className="pr-chip is-amber">~profile fit</span>}
                  </div>
                  <div className="pr-course-actions">
                    <button className="pr-btn is-red is-small" type="button" onClick={() => markComplete(top)} disabled={learning.completed.includes(top.materialKey)}>
                      {learning.completed.includes(top.materialKey) ? 'Пройдено ✓' : 'Отметить пройденным'}
                    </button>
                    <Link className="pr-btn is-ghost is-small" to="/feed">Почему этот курс →</Link>
                  </div>
                </>
              )}
            </div>
            <div className="pr-fit-dial" aria-label={top ? `Совпадение ${top.displayFit} процентов` : 'Совпадение не рассчитано'}>
              <strong>{top ? top.displayFit : '—'}</strong>
              <small>{top?.retrieved ? 'fit score' : 'profile fit'}</small>
            </div>
          </section>

          <section className="pr-card pr-chart-card" aria-labelledby="progress-title">
            <div className="pr-chart-head">
              <div>
                <span className="pr-eyebrow">Прогресс</span>
                <h2 id="progress-title">Активность за 14 дней</h2>
              </div>
              <span className="pr-badge">синтетика</span>
            </div>
            <div className="pr-chart-wrap" style={{ height: 190 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={activity} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
                  <defs>
                    <linearGradient id="dashArea" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#ef3124" stopOpacity={0.28} />
                      <stop offset="100%" stopColor="#ef3124" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0ebe5" />
                  <XAxis dataKey="label" tickLine={false} axisLine={false} interval={2} tick={{ fontSize: 9.5, fill: '#9a958e' }} />
                  <YAxis hide />
                  <Tooltip formatter={(value) => [`${String(value)} мин`, 'Активность']} />
                  <Area type="monotone" dataKey="minutes" stroke="#ef3124" strokeWidth={2.4} fill="url(#dashArea)" activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="pr-chart-legend">
              <span><i style={{ background: '#ef3124' }} />Минуты обучения</span>
              <span><i style={{ background: '#d8d0c7' }} />Базовый демо-ряд</span>
            </div>
            <p className="pr-small" style={{ marginTop: 8 }}>
              Демонстрационный ряд: локальные действия добавляются поверх стабильной синтетической кривой.
            </p>
          </section>

          <section className="pr-card is-pad" aria-labelledby="roadmap-title">
            <div className="pr-card-head">
              <div>
                <span className="pr-eyebrow">Дорожная карта</span>
                <h2 id="roadmap-title">Четыре недели до результата</h2>
                <p>Сначала ML-найденные материалы, затем оценка профиля — порядок дорожной карты.</p>
              </div>
              <span className="pr-chip is-red">демо-план</span>
            </div>
            <ol className="pr-roadmap">
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

        <div className="pr-dash-stack">
          <section className="pr-card pr-daily pr-daily-chat" aria-labelledby="daily-title">
            <header className="pr-chat-head">
              <span className="pr-chat-avatar" aria-hidden="true">АК</span>
              <div>
                <h1 id="daily-title">Наставник · вопрос дня</h1>
                <p>персональное сообщение · {nextQuestion.topicLabel.toLocaleLowerCase('ru')}</p>
              </div>
              <span className={`pr-badge ${isDoneToday ? 'is-green' : 'is-red'}`}>{isDoneToday ? 'готово' : '1 минута'}</span>
            </header>

            <div className="pr-chat-body" aria-live="polite">
              <div className="pr-msg">
                <span className="pr-msg-mark" aria-hidden="true">АК</span>
                <div className="pr-bubble">
                  <p>
                    <strong>{greeting}{firstName ? `, ${firstName}` : ''}!</strong>{' '}
                    {goal
                      ? `Держим фокус на «${goalLabel.toLocaleLowerCase('ru')}».`
                      : 'Профиль пока пустой — начнём с первого шага.'}
                  </p>
                  {personalLine && <p>{personalLine}</p>}
                </div>
              </div>

              {top && (
                <div className="pr-msg">
                  <span className="pr-msg-mark" aria-hidden="true">АК</span>
                  <div className="pr-bubble is-quiet">
                    <p>
                      Сегодня в плане — «{top.title}»: {top.displayFit}%{' '}
                      {top.retrieved ? 'ML-совпадения' : 'оценки профиля'}.
                    </p>
                    <p className="pr-bubble-note">Ответ ниже уточнит профиль и следующий запрос к каталогу.</p>
                  </div>
                </div>
              )}

              <div className="pr-msg">
                <span className="pr-msg-mark" aria-hidden="true">АК</span>
                <div className="pr-bubble">
                  <p className="pr-chat-q">{nextQuestion.question}</p>
                  <p className="pr-bubble-note">{nextQuestion.why}</p>
                </div>
              </div>

              {isDoneToday && (
                <>
                  <div className="pr-msg is-user">
                    <span className="pr-msg-mark" aria-hidden="true">Вы</span>
                    <div className="pr-bubble">{today?.answer}</div>
                  </div>
                  <div className="pr-msg">
                    <span className="pr-msg-mark" aria-hidden="true">АК</span>
                    <div className="pr-bubble">
                      <p>{todayInsight ?? 'Сигнал сохранён и будет учтён в следующем ранжировании.'}</p>
                      <p className="pr-bubble-note">Профиль обновлён. Следующий вопрос придёт завтра.</p>
                    </div>
                  </div>
                </>
              )}
            </div>

            {!isDoneToday ? (
              <>
                <div className="pr-chat-suggest is-inline" role="group" aria-label="Ответ на вопрос дня">
                  {nextQuestion.options.map((option) => (
                    <button
                      key={option.label}
                      type="button"
                      className="pr-suggest"
                      onClick={() => answer(option.label, option.insight)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                <p className="pr-small" style={{ marginTop: 10 }}>
                  Один вопрос в день · ответ меняет профиль и следующий ML-запрос.
                </p>
              </>
            ) : (
              <Link className="pr-btn is-ghost is-small" to="/feed" style={{ marginTop: 12 }}>Посмотреть новую подборку →</Link>
            )}
          </section>

          <section className="pr-card pr-cal" aria-labelledby="calendar-title">
            <div className="pr-cal-head">
              <div>
                <span className="pr-eyebrow">Календарь</span>
                <strong id="calendar-title" style={{ display: 'block', marginTop: 4 }}>{monthNames[now.getMonth()]} {now.getFullYear()}</strong>
              </div>
              <span>{learning.streak} {plural(learning.streak, 'день', 'дня', 'дней')} подряд</span>
            </div>

            <div className="pr-week">
              {week.map((day, index) => {
                const active = learning.daily.some((entry) => entry.date === day.date) || learning.lastActive === day.date
                return (
                  <div key={day.date} className={`pr-week-day ${active ? 'is-done' : ''} ${index === week.length - 1 ? 'is-today' : ''}`}>
                    <small>{weekNames[index]}</small>
                    <span>{day.label.slice(0, 2)}</span>
                  </div>
                )
              })}
            </div>

            <div className="pr-month" role="grid" aria-label="Календарь активности за месяц">
              {weekNames.map((name) => <span className="pr-month-head" key={name}>{name}</span>)}
              {month.map((cell, index) => (
                <span
                  key={`${cell.date}-${index}`}
                  className={`pr-month-cell ${cell.active ? 'is-active' : ''} ${cell.today ? 'is-today' : ''} ${cell.day === 0 ? 'is-empty' : ''}`}
                >
                  {cell.day || ''}
                </span>
              ))}
            </div>
            <div className="pr-cal-legend">
              <span><i />активный день</span>
              <span><i style={{ background: 'transparent', boxShadow: 'inset 0 0 0 1.5px #101114' }} />сегодня</span>
            </div>
          </section>

          <section className="pr-card is-sand is-pad" aria-labelledby="needs-title">
            <span className="pr-eyebrow">Что профилю действительно нужно</span>
            <h2 className="pr-title-sm" id="needs-title">Три ближайших приоритета</h2>
            <div className="pr-needs-list">
              {needs.map((need, index) => (
                <div key={need.title}>
                  <span aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
                  <div><strong>{need.title}</strong><small>{need.detail}</small></div>
                </div>
              ))}
            </div>
            <Link className="pr-btn is-ghost is-small" to="/start" style={{ marginTop: 14 }}>Дополнить анкету →</Link>
          </section>
        </div>
      </div>

      <p className="pr-synthetic">
        <span><strong>Синтетические данные.</strong> Каталог, активность и «курс дня» — демонстрационные.
        ML-ранжирование настоящее (гибрид BM25 + dense-векторы и prior), но метрики бизнеса не измерялись. Профиль хранится в этом браузере.</span>
      </p>
    </div>
  )
}
