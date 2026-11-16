import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import type { PageContext } from '../components/Layout'
import { demoAccount, loadAccount, saveAccount } from '../services/account'
import type { Account } from '../services/account'
import { recommendationMode } from '../services/recommendations'

type Mode = 'signin' | 'signup'

const emailPattern = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

export default function Auth() {
  const navigate = useNavigate()
  const { setAccount } = useOutletContext<PageContext>()
  const [mode, setMode] = useState<Mode>('signup')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)

  function enter(account: Account) {
    saveAccount(account)
    setAccount(account)
    navigate('/start', { replace: true })
  }

  async function persistToBackend(account: Account) {
    // Optional: in API mode the same profile is also written to the product
    // database. A failure never blocks the demo, because the UI is local-first.
    if (recommendationMode !== 'api') return
    try {
      const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
      await fetch(`${base}/api/v1/users/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: account.email, current_goal: 'Найти клиентов' }),
      })
    } catch { /* offline demo: the account still exists in this browser */ }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return
    const trimmedName = name.trim()
    const trimmedEmail = email.trim().toLocaleLowerCase('en')
    if (mode === 'signup' && trimmedName.length < 2) return setError('Укажите имя — хотя бы 2 символа.')
    if (!emailPattern.test(trimmedEmail)) return setError('Проверьте e-mail: нужен адрес вида name@example.com.')
    if (password.length < 6) return setError('Пароль должен быть не короче 6 символов.')
    setError('')
    setPending(true)
    const existing = loadAccount()
    if (mode === 'signin' && (!existing || existing.email !== trimmedEmail)) {
      setPending(false)
      return setError('Аккаунт с таким e-mail не найден в этом браузере. Зарегистрируйтесь или войдите в демо.')
    }
    const account: Account = {
      name: mode === 'signup' ? trimmedName : (existing?.name ?? (trimmedName || 'Предприниматель')),
      email: trimmedEmail,
      createdAt: existing?.email === trimmedEmail ? existing.createdAt : new Date().toISOString(),
    }
    await persistToBackend(account)
    setPending(false)
    enter(account)
  }

  return (
    <div className="auth-shell">
      <aside className="auth-hero">
        <div className="auth-hero-top">
          <span className="auth-mark" aria-hidden="true">А</span>
          <span>Альфа-Курс</span>
        </div>
        <h1>Меньше догадок.<br />Больше роста.</h1>
        <p className="auth-lede">
          Шесть коротких вопросов о вашем бизнесе — и «Альфа-Курс» собирает
          персональный план: что делать сейчас, какие материалы открыть и где
          вы отстаёте.
        </p>
        <ul className="auth-points">
          <li><span aria-hidden="true">✓</span><div><strong>Профиль за 2 минуты</strong><small>Выбор вариантов или свой ответ — как удобнее</small></div></li>
          <li><span aria-hidden="true">✓</span><div><strong>Подборка под задачу</strong><small>Карточки с причиной, почему они здесь</small></div></li>
          <li><span aria-hidden="true">✓</span><div><strong>Понятный следующий шаг</strong><small>Статус профиля и короткий чек-лист</small></div></li>
        </ul>
        <div className="auth-stats" aria-hidden="true">
          <div><strong>6</strong><small>вопросов</small></div>
          <div><strong>~2</strong><small>минуты</small></div>
          <div><strong>0</strong><small>документов</small></div>
        </div>
        <p className="auth-demo-note">
          Демонстрация для хакатона: рекомендации вымышлены и подписаны как демо.
          Пароль никуда не отправляется и не проверяется.
        </p>
      </aside>

      <section className="auth-card" aria-labelledby="auth-title">
        <div className="auth-tabs" role="tablist" aria-label="Вход или регистрация">
          <button type="button" role="tab" aria-selected={mode === 'signup'} className={mode === 'signup' ? 'is-active' : ''} onClick={() => { setMode('signup'); setError('') }}>Регистрация</button>
          <button type="button" role="tab" aria-selected={mode === 'signin'} className={mode === 'signin' ? 'is-active' : ''} onClick={() => { setMode('signin'); setError('') }}>Вход</button>
        </div>

        <h2 id="auth-title">{mode === 'signup' ? 'Создайте профиль' : 'С возвращением'}</h2>
        <p className="auth-subtitle">
          {mode === 'signup' ? 'Это локальная демо-учётная запись — без подтверждений и SMS.' : 'Введите e-mail, который указали при регистрации в этом браузере.'}
        </p>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          {mode === 'signup' && (
            <label className="auth-field">
              <span>Как вас зовут</span>
              <input value={name} onChange={(event) => { setName(event.target.value); setError('') }} autoComplete="name" placeholder="Анна Петрова" maxLength={60} />
            </label>
          )}
          <label className="auth-field">
            <span>E-mail</span>
            <input type="email" value={email} onChange={(event) => { setEmail(event.target.value); setError('') }} autoComplete="email" placeholder="name@example.com" maxLength={120} />
          </label>
          <label className="auth-field">
            <span>Пароль</span>
            <input type="password" value={password} onChange={(event) => { setPassword(event.target.value); setError('') }} autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} placeholder="Не короче 6 символов" maxLength={64} />
          </label>

          {error && <p className="auth-error" role="alert">{error}</p>}

          <button className="auth-submit" type="submit" disabled={pending}>
            {pending ? 'Сохраняем…' : mode === 'signup' ? 'Создать профиль →' : 'Войти →'}
          </button>
        </form>

        <div className="auth-divider"><span>или</span></div>

        <button className="auth-demo" type="button" onClick={() => enter(demoAccount)}>
          Войти в демо без регистрации
        </button>
        <p className="auth-footnote">Данные хранятся только в этом браузере и очищаются кнопкой «Выйти».</p>
      </section>
    </div>
  )
}
