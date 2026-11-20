import { useEffect, useRef, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import type { FormEvent } from 'react'
import type { PageContext } from '../components/Layout'
import { rankCatalogue } from '../services/rankingApi'
import type { RankedCourse } from '../services/rankingApi'

type Message = {
  id: string
  role: 'assistant' | 'user'
  text: string
  items?: RankedCourse[]
  meta?: string
}

type CatalogueRankState = 'cold' | 'warm' | 'unavailable'

const formatRu: Record<string, string> = {
  course: 'Курс', article: 'Статья', document: 'Документ', webinar: 'Вебинар',
  podcast: 'Подкаст', glossary: 'Глоссарий', calculator: 'Калькулятор',
}

const prompts = [
  'Хочу стабильный поток клиентов',
  'Как посчитать юнит-экономику?',
  'Как нанять первого сотрудника?',
  'С чего начать запуск продукта?',
]

function banditLabel(state: CatalogueRankState, observations: number): string {
  if (state === 'warm') return `warm, ${observations} наград`
  if (state === 'cold') return 'cold start'
  return 'недоступен'
}

function answerText(query: string, items: RankedCourse[]): string {
  if (!items.length) return 'По этому запросу ML не нашёл совпадений в каталоге. Попробуйте сформулировать задачу конкретнее: что происходит и какой результат нужен.'
  const top = items[0]
  return `По запросу «${query}» лучше всего совпадает «${top.title}» (${top.fitScore}%).\n\nЯ обновил цель профиля и пересчитал ранжирование. Дальше можно открыть первый материал или уточнить запрос — профиль и подборка обновятся.`
}

function clarifyText(query: string): string {
  return `По запросу «${query}» точного совпадения в каталоге нет: гибридный поиск BM25 + dense не зацепился за эту формулировку.\n\nЦель профиля я не менял. Уточните задачу:\n• что происходит сейчас — «продаю мебель, заявки приходят случайно»;\n• какой результат нужен — «стабильный поток заявок»;\n• какая тема ближе — клиенты, финансы, найм или процессы.`
}

export default function Coach() {
  const { profile, setProfile } = useOutletContext<PageContext>()
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'hello',
      role: 'assistant',
      text: profile?.goal
        ? `Здравствуйте. Вижу ваш фокус: «${profile.goal}». Спросите своими словами, что хотите изменить, — я прогоню запрос через BM25, векторный поиск и LinUCB и обновлю цель профиля.`
        : 'Здравствуйте. Опишите задачу своими словами — я найду материалы через BM25, векторный поиск и LinUCB и предложу обновить цель профиля.',
      meta: 'hybrid retrieval · BM25 + dense · LinUCB',
    },
  ])
  const [query, setQuery] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [lastItems, setLastItems] = useState<RankedCourse[]>([])
  const [savedGoal, setSavedGoal] = useState(profile?.goal ?? '')
  const bodyRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, pending])

  async function ask(text: string) {
    const clean = text.trim().slice(0, 300)
    if (!clean || pending) return
    setError('')
    setQuery('')
    setMessages((current) => [...current, { id: `u-${Date.now()}`, role: 'user', text: clean }])
    if (/[a-z]/i.test(clean) && !/[а-яё]/i.test(clean)) {
      setMessages((current) => [...current, {
        id: `a-${Date.now()}`,
        role: 'assistant',
        text: 'Каталог и ML-индекс демо — русскоязычные. Переформулируйте задачу по-русски, например: «хочу стабильный поток заявок без роста бюджета». Английский запрос я не отправляю в поиск, чтобы не показать случайное совпадение.',
        meta: 'язык запроса: не поддержан · цель не изменена',
      }])
      return
    }
    setPending(true)
    try {
      const result = await rankCatalogue({
        task: clean,
        profile: {
          business_stage: profile?.stage || null,
          industry: profile?.industry || null,
          experience: profile?.experience || null,
        },
        constraints: profile?.hoursPerWeek ? { available_time_minutes: profile.hoursPerWeek * 60 } : {},
        limit: 6,
      })
      const picks = result.items.filter((item) => item.retrieved).slice(0, 3)
      if (result.status === 'needs_clarification' || picks.length === 0) {
        // No retrieval match: do not pretend a 0% item is a recommendation and
        // do not overwrite the profile goal with an unranked query.
        setLastItems([])
        setMessages((current) => [...current, {
          id: `a-${Date.now()}`,
          role: 'assistant',
          text: clarifyText(clean),
          meta: `статус: ${result.status} · цель не изменена`,
        }])
        return
      }
      setLastItems(picks)
      setMessages((current) => [...current, {
        id: `a-${Date.now()}`,
        role: 'assistant',
        text: answerText(clean, picks),
        items: picks,
        meta: `алгоритм: ${result.algorithm} · dense: ${result.denseModel}${result.denseDimensions ? ` (${result.denseDimensions}D)` : ''} · LinUCB: ${banditLabel(result.banditState, result.banditObservations)}`,
      }])
      if (profile) {
        const compact = clean.replace(/\s+/g, ' ').slice(0, 120)
        setProfile({ ...profile, goal: compact })
        setSavedGoal(compact)
      }
    } catch {
      setError('ML-сервис не ответил после нескольких попыток. Проверьте, что стек запущен, и повторите запрос.')
      setMessages((current) => [...current, {
        id: `e-${Date.now()}`, role: 'assistant',
        text: 'Не удалось получить ранжирование: API не ответил. Это не результат ML-поиска, поэтому цель профиля не изменена.',
      }])
    } finally {
      setPending(false)
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void ask(query)
  }

  return (
    <div className="pr-coach">
      <section className="pr-card pr-chat-card" aria-labelledby="coach-title">
        <div className="pr-chat-head">
          <span className="pr-chat-avatar" aria-hidden="true">ML</span>
          <div>
            <h1 id="coach-title">Наставник Альфа-Курс</h1>
            <p>Hybrid retrieval · BM25 + dense · LinUCB · обновляет цель профиля</p>
          </div>
          <span className={`pr-badge ${pending ? '' : 'is-green'}`}>{pending ? 'думает' : 'на связи'}</span>
        </div>

        <div className="pr-chat-body" ref={bodyRef} aria-live="polite">
          {messages.map((message) => (
            <div key={message.id} className={`pr-msg ${message.role === 'user' ? 'is-user' : ''}`}>
              <span className="pr-msg-mark" aria-hidden="true">{message.role === 'user' ? 'Вы' : 'AI'}</span>
              <div className="pr-bubble">
                <div style={{ whiteSpace: 'pre-line' }}>{message.text}</div>
                {message.items && message.items.length > 0 && (
                  <ul>
                    {message.items.map((item) => (
                      <li key={item.materialKey}>
                        <strong>{item.title}</strong> — {item.fitScore}% · {formatRu[item.format] ?? item.format}
                        {item.durationMinutes ? ` · ${item.durationMinutes} мин` : ''}
                      </li>
                    ))}
                  </ul>
                )}
                {message.meta && <p className="pr-bubble-note">{message.meta}</p>}
              </div>
            </div>
          ))}
          {pending && (
            <div className="pr-msg">
              <span className="pr-msg-mark" aria-hidden="true">AI</span>
              <div className="pr-bubble">Ранжирую каталог под ваш запрос…</div>
            </div>
          )}
        </div>

        <div className="pr-chat-suggest">
          {prompts.map((prompt) => (
            <button key={prompt} type="button" className="pr-suggest" onClick={() => { void ask(prompt) }} disabled={pending}>
              {prompt}
            </button>
          ))}
        </div>

        {error && <p className="pr-error" role="alert" style={{ margin: '0 16px 10px' }}>{error}</p>}

        <form className="pr-chat-form" onSubmit={submit}>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Опишите задачу: «хочу больше заявок без роста бюджета»"
            maxLength={300}
            aria-label="Запрос к наставнику"
          />
          <button className="pr-btn is-red" type="submit" disabled={pending || !query.trim()}>Спросить →</button>
        </form>
      </section>

      <aside className="pr-coach-side">
        <div className="pr-card">
          <span className="pr-eyebrow">Цель профиля</span>
          <div className="pr-goal-box" style={{ marginTop: 10 }}>
            <span>Цель для ранжирования</span>
            <strong>{savedGoal || 'Пока не задана'}</strong>
            <small>{savedGoal ? 'Цель меняется только при найденном совпадении в каталоге.' : 'Задайте вопрос — цель обновится после успешного поиска.'}</small>
          </div>
          {lastItems.length > 0 && (
            <div className="pr-coach-picks">
              {lastItems.map((item) => (
                <div className="pr-coach-pick" key={item.materialKey}>
                  <strong>{item.title}</strong>
                  <span>{item.fitScore}% · {formatRu[item.format] ?? item.format}{item.durationMinutes ? ` · ${item.durationMinutes} мин` : ''}</span>
                </div>
              ))}
            </div>
          )}
          <Link className="pr-btn is-ghost is-small" to="/feed" style={{ marginTop: 12 }}>Открыть полный рейтинг →</Link>
        </div>

        <div className="pr-card">
          <span className="pr-eyebrow">Профиль для ML</span>
          <div className="pr-detail-list">
            <div><span>Роль</span><strong>{profile?.position || 'не указана'}</strong></div>
            <div><span>Задача</span><strong>{profile?.goal || 'не указана'}</strong></div>
            <div><span>Стадия</span><strong>{profile?.stage || 'не указана'}</strong></div>
            <div><span>Отрасль</span><strong>{profile?.industry || 'не указана'}</strong></div>
            <div><span>Ритм</span><strong>{profile?.hoursPerWeek ? `${profile.hoursPerWeek} ч/нед` : 'не указан'}</strong></div>
            <div><span>Интересы</span><strong>{(profile?.interests ?? []).join(', ') || 'не выбраны'}</strong></div>
          </div>
          <Link className="pr-btn is-quiet is-small" to="/start" style={{ marginTop: 8 }}>Дополнить профиль →</Link>
        </div>

        <p className="pr-coach-disclaimer">
          Наставник — демо-интерфейс над настоящим ранжированием. Он не консультирует по юридическим
          или финансовым вопросам и не гарантирует результат. Цель профиля сохраняется только в браузере.
        </p>
      </aside>
    </div>
  )
}
