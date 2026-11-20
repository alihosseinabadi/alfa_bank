import { useEffect, useMemo, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import type { PageContext } from '../components/Layout'
import { profileReadiness } from '../services/account'
import { answeredToday, guessCategory, loadLearning, localFit, topicQueryTerm } from '../services/learning'
import { rankCatalogue } from '../services/rankingApi'
import type { CatalogueRankResult, RankFormat, RankedCourse } from '../services/rankingApi'

type FeedItem = RankedCourse & { displayFit: number; heuristic: boolean }

const formatRu: Record<RankFormat, string> = {
  course: 'Курс', article: 'Статья', document: 'Документ', webinar: 'Вебинар',
  podcast: 'Подкаст', glossary: 'Глоссарий', calculator: 'Калькулятор',
}

function priceLabel(value: number | null): string {
  if (value === null) return 'Цена не указана'
  if (value === 0) return 'Бесплатно'
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(value)} ₽`
}

function firstWords(text: string, count: number): string {
  return text.trim().split(/\s+/).slice(0, count).join(' ')
}

export default function Feed() {
  const { profile } = useOutletContext<PageContext>()
  const [rank, setRank] = useState<CatalogueRankResult | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'empty' | 'clarify' | 'error'>('loading')
  const [attempt, setAttempt] = useState(0)
  const [format, setFormat] = useState<'all' | RankFormat>('all')
  const [topOnly, setTopOnly] = useState(false)
  const [learning] = useState(loadLearning)

  const task = useMemo(() => {
    if (!profile?.goal) return ''
    return [profile.goal, topicQueryTerm(answeredToday(learning)?.topic)]
      .filter(Boolean).join('. ').slice(0, 300)
  }, [profile, learning])

  useEffect(() => {
    let active = true
    if (!profile?.goal || !task) { setStatus('empty'); return }
    setStatus('loading')
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
        setRank(result)
        if (result.status === 'needs_clarification') setStatus('clarify')
        else setStatus(result.items.length ? 'ready' : 'empty')
      })
      .catch(() => { if (active) setStatus('error') })
    return () => { active = false }
  }, [profile, task, attempt])

  const items = rank?.items ?? []
  const retrieved = items.filter((item) => item.retrieved).length
  const formatsAvailable = Array.from(new Set(items.map((item) => item.format)))
  const enriched: FeedItem[] = items.map((item) => ({
    ...item,
    displayFit: item.retrieved
      ? item.fitScore
      : localFit({ title: item.title, category: guessCategory(item.title), duration_minutes: item.durationMinutes ?? 0 }, profile ?? {}),
    heuristic: !item.retrieved,
  }))
  const ordered = [...enriched].sort((a, b) =>
    Number(b.retrieved) - Number(a.retrieved) || b.displayFit - a.displayFit)
  const topFit = ordered[0]?.displayFit ?? 0
  const visible = ordered.filter((item) => (format === 'all' || item.format === format) && (!topOnly || item.displayFit >= 60))
  const top = ordered[0]
  const interest = profile?.interests?.[0]
  const readiness = profileReadiness({
    goal: profile?.goal ?? '', industry: profile?.industry ?? '', stage: profile?.stage ?? '',
    experience: profile?.experience ?? '', difficulty: profile?.difficulty ?? '', note: profile?.note ?? '',
    position: profile?.position ?? '', interests: profile?.interests ?? [],
    hoursPerWeek: profile?.hoursPerWeek ?? 0, format: profile?.format ?? '',
  })

  return (
    <div className="pr-feed">
      <section className="pr-feed-hero">
        <div>
          <span className="pr-eyebrow">ML-подборка · весь каталог</span>
          <h1>Что подходит вам<br />лучше всего</h1>
          <p>
            {profile?.goal
              ? <>Задача: <strong>{profile.goal.toLocaleLowerCase('ru')}</strong>. Каждый материал каталога оценён гибридным поиском BM25 + dense-векторы и prior-ранжированием. Fit score — относительное совпадение с профилем, а не вероятность покупки.</>
              : 'Заполните анкету, чтобы увидеть персональный рейтинг всех материалов каталога.'}
          </p>
          <div className="pr-hero-actions" style={{ marginTop: 18 }}>
            <Link className="pr-btn is-red is-small" to="/coach">Обсудить с наставником →</Link>
            <Link className="pr-btn is-ghost is-small" to="/start">Изменить задачу</Link>
          </div>
        </div>
        <div className="pr-feed-hero-side">
          <div className="pr-feed-stat"><span>В ранге</span><strong>{status === 'clarify' ? '—' : items.length || '—'}</strong></div>
          <div className="pr-feed-stat"><span>Найдено ML-поиском</span><strong>{retrieved || '—'}</strong></div>
          <div className="pr-feed-stat"><span>Лучшее совпадение</span><strong style={{ color: 'var(--pr-red-dark)' }}>{items.length && status !== 'clarify' ? `${topFit}%` : '—'}</strong></div>
          <div className="pr-feed-stat"><span>Алгоритм</span><strong style={{ fontSize: 10 }}>{rank?.denseModel ?? 'BM25 + dense'}</strong></div>
        </div>
      </section>

      {status === 'ready' && (
        <div className="pr-toolbar">
          <div className="pr-filters" role="group" aria-label="Фильтр по формату">
            <button type="button" className={`pr-filter ${format === 'all' ? 'is-active' : ''}`} onClick={() => setFormat('all')}>Все форматы</button>
            {formatsAvailable.map((value) => (
              <button key={value} type="button" className={`pr-filter ${format === value ? 'is-active' : ''}`} onClick={() => setFormat(value)}>
                {formatRu[value]}
              </button>
            ))}
            <button type="button" className={`pr-filter ${topOnly ? 'is-active' : ''}`} onClick={() => setTopOnly((value) => !value)}>
              Совпадение ≥ 60%
            </button>
          </div>
          <span className="pr-toolbar-note">{visible.length} из {items.length} · без записи решения</span>
        </div>
      )}

      {status === 'clarify' && (
        <div className="pr-card is-pad">
          <span className="pr-eyebrow">Нет совпадения</span>
          <h2 className="pr-title-sm">Уточните задачу</h2>
          <p className="pr-sub">
            {rank?.message ?? 'По этой формулировке не нашлось материала. Опишите задачу своими словами или измените ограничения.'}
            {' '}Бессмысленный запрос не превращается в рекомендацию.
          </p>
          <div className="pr-hero-actions" style={{ marginTop: 14 }}>
            <Link className="pr-btn is-red is-small" to="/coach">Спросить наставника →</Link>
            <Link className="pr-btn is-ghost is-small" to="/start">Изменить задачу</Link>
          </div>
        </div>
      )}

      {status === 'loading' && (
        <div className="pr-empty">Считаем BM25 + dense-векторы и prior-ранжирование для всего каталога…</div>
      )}

      {status === 'error' && (
        <div className="pr-card is-pad" role="alert">
          <span className="pr-eyebrow">Сервис недоступен</span>
          <h2 className="pr-title-sm">ML-ранжирование не ответило</h2>
          <p className="pr-sub">
            Проверьте, что стек запущен через <code>docker compose up</code>. Эндпоинт
            <code> /api/v1/catalogue/rank</code> требует анонимную сессию и CSRF-токен — они создаются автоматически.
          </p>
          <button className="pr-btn is-red is-small" type="button" onClick={() => setAttempt((value) => value + 1)} style={{ marginTop: 14 }}>
            Повторить попытку
          </button>
        </div>
      )}

      {status === 'empty' && (
        <div className="pr-card is-pad">
          <span className="pr-eyebrow">Нужен профиль</span>
          <h2 className="pr-title-sm">Сначала — задача и профиль</h2>
          <p className="pr-sub">Восемь вопросов займут около трёх минут. После этого здесь появится рейтинг всех 20 материалов.</p>
          <Link className="pr-btn is-red is-small" to="/start" style={{ marginTop: 14 }}>Заполнить профиль →</Link>
        </div>
      )}

      {status === 'ready' && (
        <>
          <div className="pr-rank-list" aria-live="polite">
            {visible.map((item, index) => (
              <RankRow key={item.materialKey} item={item} position={ordered.indexOf(item) + 1} highlight={index === 0} />
            ))}
            {visible.length === 0 && <div className="pr-empty">Под выбранный фильтр не попал ни один курс. Снимите фильтр или уточните задачу.</div>}
          </div>

          {retrieved > 0 && retrieved < items.length && (
            <p className="pr-synthetic">
              <span><strong>Граница ML-поиска.</strong> {retrieved} из {items.length} материалов вошли в гибридную выдачу BM25 + dense-векторы.
              Остальные показаны ниже с оценкой профиля (эвристика, не ML) — это честный fallback полного каталога, а не расширение слата.</span>
            </p>
          )}

          {top && interest && (
            <section className="pr-card pr-proof" aria-labelledby="proof-title">
              <div>
                <span className="pr-eyebrow">Похожие профили</span>
                <h2 id="proof-title">С интересом «{interest.toLocaleLowerCase('ru')}» обычно выбирают</h2>
                <p className="pr-proof-row">
                  <span className="pr-proof-avatars" aria-hidden="true">
                    {['АК', 'МС', 'ДВ', 'ЕЛ', 'ИП'].map((mark) => <span key={mark}>{mark}</span>)}
                  </span>
                  <small>
                    Демонстрационный паттерн: синтетические профили с тем же интересом чаще всего
                    открывали «{firstWords(top.title, 5)}…» в первую неделю.
                  </small>
                </p>
                <p className="pr-small" style={{ marginTop: 10 }}>
                  Это не измерение конверсии и не реальные пользователи: паттерн собран для показа
                  социального доказательства в демо.
                </p>
              </div>
              <div className="pr-proof-side">
                <strong>Первый шаг</strong>
                <small>{top.title}</small>
                <span className="pr-chip is-red">{top.displayFit}% совпадения</span>
                <small>{formatRu[top.format]} · {top.durationMinutes ? `${top.durationMinutes} мин` : 'длительность не указана'}</small>
              </div>
            </section>
          )}
        </>
      )}

      <section className="pr-card is-sand is-pad">
        <div className="pr-card-head">
          <div>
            <span className="pr-eyebrow">Как это работает</span>
            <h2>Почему курсы стоят именно так</h2>
            <p>Fit score нормирован к лучшему кандидату в вашем запросе — это относительная шкала, не вероятность.</p>
          </div>
          <span className="pr-chip is-ink">BM25 + dense + prior</span>
        </div>
        <div className="pr-analysis-grid" style={{ marginTop: 16 }}>
          <div className="pr-analysis-cell">
            <span>Шаг 1 · retrieval</span>
            <strong>BM25 + dense находят кандидатов</strong>
            <p>Лексический и векторный каналы объединяются; запрос строится из задачи, роли и дневного сигнала профиля.</p>
          </div>
          <div className="pr-analysis-cell">
            <span>Шаг 2 · prior</span>
            <strong>Профиль корректирует порядок</strong>
            <p>Стадия, отрасль, опыт и ограничения меняют итоговый скор.</p>
          </div>
          <div className="pr-analysis-cell">
            <span>Шаг 3 · preview</span>
            <strong>Весь каталог, без решения</strong>
            <p>Endpoint возвращает ранжирование, но не создаёт decision и не пишет события.</p>
          </div>
          <div className="pr-analysis-cell">
            <span>Профиль</span>
            <strong>{readiness}% заполнено</strong>
            <p>{profile?.hoursPerWeek ? `${profile.hoursPerWeek} ч/нед · ${profile.format ?? 'формат не выбран'}` : 'Укажите свободное время и формат.'}</p>
          </div>
        </div>
      </section>

      <p className="pr-synthetic">
        <span><strong>Синтетические данные.</strong> Названия, цены и длительности курсов вымышлены.
        Ранжирование выполняет настоящий гибрид BM25 + dense-векторы и prior на демо-каталоге; CTR, продажи и конверсия не измерялись.</span>
      </p>
    </div>
  )
}

function RankRow({ item, position, highlight }: { item: FeedItem; position: number; highlight: boolean }) {
  return (
    <article className={`pr-rank-row ${highlight ? 'is-top' : ''} ${item.retrieved ? '' : 'is-off'}`}>
      <span className="pr-rank-num" aria-hidden="true">{String(position).padStart(2, '0')}</span>
      <div className="pr-rank-main">
        <h3>{item.title}</h3>
        <div className="pr-rank-meta">
          <span>{formatRu[item.format]}</span>
          {item.durationMinutes && <span>{item.durationMinutes} мин</span>}
          <span>{priceLabel(item.listedPrice)}</span>
          {item.mlRank && <span>ML #{item.mlRank}</span>}
          {item.heuristic && <span>оценка профиля · не ML</span>}
        </div>
        <p className="pr-rank-reason">{item.reason}</p>
      </div>
      <div className="pr-rank-score">
        <strong>{item.heuristic && '~'}{item.displayFit}<small>%</small></strong>
        <span className="pr-rank-bar" aria-hidden="true"><span style={{ width: `${item.displayFit}%` }} /></span>
        <em>{item.heuristic ? 'profile fit' : 'fit score'}</em>
      </div>
    </article>
  )
}
