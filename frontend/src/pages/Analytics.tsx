import { useMemo } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import {
  Area, Bar, CartesianGrid, ComposedChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis,
  Radar, RadarChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { PageContext } from '../components/Layout'
import {
  activitySeries, loadLearning, monthCells, topicKeywords, topicLabels,
} from '../services/learning'
import type { TopicKey } from '../services/learning'

// Kept at the bottom, inside a closed disclosure: this is retrieval evaluation
// for engineers, not a client activity metric.
const retrievalRows = [
  { method: 'BM25 + prior', ndcg: 0.8567 },
  { method: 'BM25', ndcg: 0.8564 },
  { method: 'TF-IDF + prior', ndcg: 0.8326 },
  { method: 'TF-IDF', ndcg: 0.8321 },
]

const scaleMin = 0.82
const scaleMax = 0.86
const best = Math.max(...retrievalRows.map((row) => row.ndcg))
const baseline = retrievalRows[retrievalRows.length - 1].ndcg
const percent = (value: number) => ((value - scaleMin) / (scaleMax - scaleMin)) * 100
const delta = (value: number) => (value - baseline).toFixed(4)

const topicOrder: TopicKey[] = ['marketing', 'sales', 'finance', 'management', 'programming', 'entrepreneurship']

const interestTopic: Record<string, TopicKey> = {
  'Маркетинг и клиенты': 'marketing',
  'Продажи и переговоры': 'sales',
  'Финансы и юнит-экономика': 'finance',
  'Управление командой': 'management',
  'Данные и автоматизация': 'programming',
  'Запуск и инвестиции': 'entrepreneurship',
}

const monthNames = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
const weekHeads = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']

function plural(value: number, one: string, few: string, many: string): string {
  const mod10 = value % 10
  const mod100 = value % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few
  return many
}

export default function Analytics() {
  const { profile } = useOutletContext<PageContext>()
  const learning = useMemo(loadLearning, [])

  const activity = useMemo(() => activitySeries(learning, 14), [learning])
  const activeDates = new Set([
    ...learning.daily.map((item) => item.date),
    learning.lastActive,
  ].filter(Boolean))
  const activeDays = activeDates.size
  const totalMinutes = learning.minutes
  const completedCount = learning.completed.length
  const savedCount = learning.saved.length
  const now = new Date()
  const month = monthCells(now.getFullYear(), now.getMonth(), learning)

  const profileText = [
    profile?.goal, profile?.note, profile?.difficulty, profile?.position,
    ...(profile?.interests ?? []),
  ].filter(Boolean).join(' ').toLocaleLowerCase('ru')

  const answersByTopic = learning.daily.reduce<Record<string, number>>((totals, item) => {
    totals[item.topic] = (totals[item.topic] ?? 0) + 1
    return totals
  }, {})

  const radar = topicOrder.map((topic) => {
    const interestHit = (profile?.interests ?? []).some((interest) => interestTopic[interest] === topic) ? 1 : 0
    const keywordHits = Math.min(3, topicKeywords[topic].filter((key) => profileText.includes(key)).length)
    const answers = Math.min(3, answersByTopic[topic] ?? 0)
    return { topic: topicLabels[topic], value: Math.min(98, 22 + interestHit * 30 + keywordHits * 8 + answers * 6) }
  })

  const topTopic = radar.slice().sort((left, right) => right.value - left.value)[0]?.topic ?? 'Управление'
  const weeklyHours = profile?.hoursPerWeek ?? 0
  const dailyTarget = weeklyHours ? Math.round((weeklyHours * 60) / 7) : 15
  const averageStep = activeDays ? Math.round(totalMinutes / activeDays) : 0

  const suggestions = [
    learning.daily.length === 0
      ? 'Ответьте на вопрос дня на главной: так профиль обновляется без длинной анкеты.'
      : `Последний ответ дня сохранён в дневнике. Следующий вопрос появится завтра.`,
    savedCount === 0
      ? 'Сохраните один материал из подборки — он появится здесь и в плане на неделю.'
      : `В коллекции ${savedCount} ${plural(savedCount, 'материал', 'материала', 'материалов')}. Начните с самого короткого.`,
    completedCount === 0
      ? 'Отметьте первый материал пройденным: прогресс и минуты пересчитаются.'
      : `Пройдено ${completedCount}. Спросите наставника, какой материал логичен следующим.`,
    weeklyHours > 0 && weeklyHours <= 4
      ? 'При ритме до 4 часов в неделю берите короткие статьи и один шаг в день.'
      : 'Ритм позволяет добавить практику: выберите один курс и отметьте его пройденным.',
  ].slice(0, 3)

  return (
    <div className="pr-ana">
      <section className="pr-ana-hero">
        <div>
          <span className="pr-eyebrow">Мой прогресс · демо-профиль</span>
          <h1>Учебная активность<br />и следующий шаг</h1>
          <p>
            Только ваши действия в демо: ответы на вопрос дня, сохранённые и пройденные
            материалы. Ни один блок не является измерением продаж, выручки или конверсии.
          </p>
        </div>
        <div className="pr-ana-stats">
          <div className="pr-ana-stat"><strong>{activeDays}</strong><span>{plural(activeDays, 'активный день', 'активных дня', 'активных дней')}</span></div>
          <div className="pr-ana-stat"><strong>{completedCount}</strong><span>{plural(completedCount, 'материал пройден', 'материала пройдено', 'материалов пройдено')}</span></div>
          <div className="pr-ana-stat"><strong>{totalMinutes}</strong><span>{plural(totalMinutes, 'минута в демо', 'минуты в демо', 'минут в демо')}</span></div>
          <div className="pr-ana-stat is-red"><strong>{learning.streak}</strong><span>{plural(learning.streak, 'день подряд', 'дня подряд', 'дней подряд')}</span></div>
        </div>
      </section>

      <div className="pr-ana-grid">
        <section className="pr-card pr-ana-card pr-span-7" aria-labelledby="activity-title">
          <div className="pr-card-head">
            <div>
              <span className="pr-eyebrow">Активность</span>
              <h2 id="activity-title">Минуты и материалы за 14 дней</h2>
              <p className="pr-small">Базовая демо-кривая плюс ваши локальные действия; ряд не отправляется на сервер.</p>
            </div>
            <span className="pr-badge">synthetic</span>
          </div>
          <div className="pr-ana-chart" style={{ height: 250 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={activity} margin={{ top: 10, right: 6, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="anaArea" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#ef3124" stopOpacity={0.24} />
                    <stop offset="100%" stopColor="#ef3124" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0ebe5" />
                <XAxis dataKey="label" tickLine={false} axisLine={false} interval={1} tick={{ fontSize: 9.5, fill: '#9a958e' }} />
                <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 9.5, fill: '#9a958e' }} width={34} />
                <Tooltip />
                <Bar dataKey="lessons" barSize={8} fill="#ded6cd" radius={[3, 3, 0, 0]} name="Материалы" />
                <Area type="monotone" dataKey="minutes" stroke="#ef3124" strokeWidth={2.3} fill="url(#anaArea)" name="Минуты" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="pr-legend">
            <span><i style={{ background: '#ef3124' }} />Минуты</span>
            <span><i style={{ background: '#ded6cd' }} />Материалы</span>
          </div>
        </section>

        <section className="pr-card pr-ana-card pr-span-5" aria-labelledby="radar-title">
          <div className="pr-card-head">
            <div>
              <span className="pr-eyebrow">Тематический профиль</span>
              <h2 id="radar-title">Где вы сейчас сильнее</h2>
              <p className="pr-small">Правило на основе интересов, цели и ответов дня — не обученная модель.</p>
            </div>
            <span className="pr-badge is-red">demo</span>
          </div>
          <div className="pr-ana-chart" style={{ height: 250 }}>
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radar} outerRadius="72%">
                <PolarGrid stroke="#e9e4de" />
                <PolarAngleAxis dataKey="topic" tick={{ fontSize: 9.5, fill: '#6b6f76' }} />
                <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                <Radar dataKey="value" stroke="#ef3124" fill="#ef3124" fillOpacity={0.18} strokeWidth={2} name="Выраженность" />
              </RadarChart>
            </ResponsiveContainer>
          </div>
          <p className="pr-small">
            Сильнее всего профиль выражен в теме «{topTopic}». Радар пересчитывается из ответов
            и не является психометрическим тестом.
          </p>
        </section>

        <section className="pr-card pr-ana-card pr-span-4" aria-labelledby="collection-title">
          <div className="pr-card-head">
            <div>
              <span className="pr-eyebrow">Коллекция</span>
              <h2 id="collection-title">Что уже накопилось</h2>
            </div>
            <span className="pr-badge">локально</span>
          </div>
          <div className="pr-analysis-grid">
            <div className="pr-analysis-cell">
              <span>Сохранено</span>
              <strong>{savedCount} {plural(savedCount, 'материал', 'материала', 'материалов')}</strong>
              <p>Отложено из подборки.</p>
            </div>
            <div className="pr-analysis-cell">
              <span>Пройдено</span>
              <strong>{completedCount} {plural(completedCount, 'материал', 'материала', 'материалов')}</strong>
              <p>Отмечено вами вручную.</p>
            </div>
            <div className="pr-analysis-cell">
              <span>Дневник</span>
              <strong>{learning.daily.length} {plural(learning.daily.length, 'ответ', 'ответа', 'ответов')}</strong>
              <p>Вопросы дня и выводы.</p>
            </div>
            <div className="pr-analysis-cell">
              <span>Серия</span>
              <strong>{learning.streak} {plural(learning.streak, 'день', 'дня', 'дней')}</strong>
              <p>Подряд с активностью.</p>
            </div>
          </div>
        </section>

        <section className="pr-card pr-ana-card pr-span-4" aria-labelledby="rhythm-title">
          <div className="pr-card-head">
            <div>
              <span className="pr-eyebrow">Ритм</span>
              <h2 id="rhythm-title">План и фактический шаг</h2>
            </div>
            <span className="pr-badge">профиль</span>
          </div>
          <div className="pr-analysis-grid">
            <div className="pr-analysis-cell">
              <span>Заявленный ритм</span>
              <strong>{weeklyHours ? `${weeklyHours} ч в неделю` : 'не указан'}</strong>
              <p>{weeklyHours ? 'Из анкеты при входе.' : 'Можно добавить в профиле.'}</p>
            </div>
            <div className="pr-analysis-cell">
              <span>Цель на день</span>
              <strong>{dailyTarget} минут</strong>
              <p>Ритм, разложенный по дням.</p>
            </div>
            <div className="pr-analysis-cell">
              <span>Средний шаг</span>
              <strong>{averageStep} минут</strong>
              <p>По вашим действиям в демо.</p>
            </div>
            <div className="pr-analysis-cell">
              <span>Активных дней</span>
              <strong>{activeDays}</strong>
              <p>Дни с ответом или отметкой.</p>
            </div>
          </div>
        </section>

        <section className="pr-card pr-ana-card pr-span-4" aria-labelledby="suggest-title">
          <div className="pr-card-head">
            <div>
              <span className="pr-eyebrow">Следующие шаги</span>
              <h2 id="suggest-title">Что сделать дальше</h2>
            </div>
            <span className="pr-badge">правила</span>
          </div>
          <div className="pr-needs-list">
            {suggestions.map((textItem, index) => (
              <div key={textItem}>
                <span aria-hidden="true">{index + 1}</span>
                <div><strong>{textItem}</strong></div>
              </div>
            ))}
          </div>
          <Link className="pr-btn is-ghost is-small" to="/coach" style={{ marginTop: 12 }}>Спросить наставника →</Link>
        </section>

        <section className="pr-card pr-ana-card pr-span-12" aria-labelledby="calendar-title">
          <div className="pr-card-head">
            <div>
              <span className="pr-eyebrow">Календарь</span>
              <h2 id="calendar-title">Активность за {monthNames[now.getMonth()]} {now.getFullYear()}</h2>
              <p className="pr-small">Ответы на вопрос дня и отметки о прохождении; данные остаются в браузере.</p>
            </div>
            <span className="pr-chip is-red">{learning.streak} {plural(learning.streak, 'день', 'дня', 'дней')} подряд</span>
          </div>
          <div className="pr-month" role="grid" aria-label="Календарь активности" style={{ maxWidth: 520, marginTop: 18 }}>
            {weekHeads.map((name) => <span className="pr-month-head" key={name}>{name}</span>)}
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
      </div>

      <details className="pr-details">
        <summary>Для инженеров: качество поиска, NDCG@10</summary>
        <p className="pr-small" style={{ marginTop: 10 }}>
          Историческая оценка retrieval на 21 синтетической задаче с метками одного агентного
          разметчика. Шкала 0.82–0.86 растянута, чтобы разница была видна. Это не клиентская
          аналитика и не эффект для бизнеса.
        </p>
        <div className="pr-quality" role="img" aria-label="NDCG@10: BM25 + prior 0.8567, BM25 0.8564, TF-IDF + prior 0.8326, TF-IDF 0.8321">
          {retrievalRows.map((row, index) => (
            <div className={`pr-quality-row ${index < 2 ? 'is-leader' : ''}`} key={row.method}>
              <span>{row.method}</span>
              <span className="pr-quality-track"><span style={{ width: `${percent(row.ndcg)}%` }} /></span>
              <strong>{row.ndcg.toFixed(4)}</strong>
            </div>
          ))}
        </div>
        <div className="pr-quality-scale"><span>{scaleMin.toFixed(2)}</span><span>{((scaleMin + scaleMax) / 2).toFixed(2)}</span><span>{scaleMax.toFixed(2)}</span></div>
        <div className="pr-quality" style={{ marginTop: 18 }}>
          {retrievalRows.map((row, index) => (
            <div className={`pr-quality-row ${index < 2 ? 'is-leader' : ''}`} key={`delta-${row.method}`}>
              <span>{row.method}</span>
              <span className="pr-quality-track"><span style={{ width: `${Math.max(4, (Number(delta(row.ndcg)) / 0.0246) * 100)}%` }} /></span>
              <strong>{index === retrievalRows.length - 1 ? '0' : `+${delta(row.ndcg)}`}</strong>
            </div>
          ))}
        </div>
        <p className="pr-small" style={{ marginTop: 10 }}>
          Вторая полоса — прирост к TF-IDF. Разрыв TF-IDF → BM25 больше вклада prior; живого
          трафика для проверки эффекта в демо нет. Лучший NDCG@10: {best.toFixed(4)}.
        </p>
      </details>

      <section className="pr-card pr-ana-card pr-ana-missing" aria-labelledby="missing-title">
        <div>
          <span className="pr-eyebrow">Чего здесь нет</span>
          <h2 id="missing-title">Live-метрики не измерялись</h2>
          <p className="pr-small">
            События показов и кликов реализованы, но живого трафика и оплат в демо нет.
            LinUCB против случайного на реальных данных не проверялся.
          </p>
          <Link className="pr-btn is-ghost is-small" to="/feed" style={{ marginTop: 14 }}>← Вернуться к подборке</Link>
        </div>
        <div>
          {[
            ['CTR', 'нет данных'],
            ['Просмотры материалов', 'нет данных'],
            ['Конверсия в покупку', 'нет данных'],
          ].map(([label, pill]) => (
            <div className="pr-status-row" key={label}>
              <span>{label}</span>
              <span className="pr-pill">{pill}</span>
              <span className="pr-status-bar"><span style={{ width: '0%' }} /></span>
            </div>
          ))}
        </div>
      </section>

      <p className="pr-synthetic">
        <span><strong>Синтетические данные.</strong> Активность и тематический профиль — демонстрационные
        расчёты по локальным действиям и ответам анкеты. NDCG взят из исторической оценки на
        синтетическом наборе. Ни один блок не является измерением продаж, выручки или конверсии.</span>
      </p>
    </div>
  )
}
