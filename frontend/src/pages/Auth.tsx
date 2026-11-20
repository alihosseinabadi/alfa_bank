import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import alfaSign from '../assets/alfa-sign-red.svg'
import type { PageContext } from '../components/Layout'
import { demoAccount, loadAccount, loadAnswers, resetLocalProfile, saveAccount } from '../services/account'
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

  function enter(account: Account, fresh: boolean) {
    if (fresh) resetLocalProfile()
    saveAccount(account)
    setAccount(account)
    const hasProfile = !fresh && !!loadAnswers().goal.trim()
    navigate(hasProfile ? '/dashboard' : '/start', { replace: true })
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
    enter(account, mode === 'signup')
  }

  return (
    <div className="pr-auth">
      <aside className="pr-auth-art">
        <div>
          <div className="pr-auth-brand">
            <img src={alfaSign} alt="" aria-hidden="true" />
            <span>
              Альфа-Курс
              <small>персональный учебный план</small>
            </span>
          </div>

          <h1 className="pr-auth-title">
            Меньше догадок.<br />
            <em>Больше роста.</em>
          </h1>
          <p className="pr-auth-lede">
            Ответьте на восемь коротких вопросов — и ML-подборка соберёт личный план:
            что изучать сегодня, какой курс даст быстрый результат и чего не хватает
            вашему профилю.
          </p>

          <ul className="pr-auth-points">
            <li>
              <span aria-hidden="true">1</span>
              <div><strong>Анализ профиля, а не тест</strong><small>Роль, стадия, интересы и свободное время формируют стартовый профиль</small></div>
            </li>
            <li>
              <span aria-hidden="true">2</span>
              <div><strong>Настоящее ML-ранжирование</strong><small>Гибрид BM25 + dense-векторы и prior-модель ранжируют весь каталог под вашу задачу</small></div>
            </li>
            <li>
              <span aria-hidden="true">3</span>
              <div><strong>Ежедневный цикл обучения</strong><small>Один вопрос в день уточняет профиль и меняет следующие рекомендации</small></div>
            </li>
          </ul>
        </div>

        <div>
          <div className="pr-auth-foot">
            <div className="pr-auth-metrics">
              <div><strong>12</strong><small>курсов в каталоге</small></div>
              <div><strong>8</strong><small>вопросов профиля</small></div>
              <div><strong>1</strong><small>шаг в день</small></div>
            </div>
          </div>
          <p className="pr-auth-note" style={{ textAlign: 'left', color: '#8f8b92', marginTop: 16 }}>
            Демонстрационный продукт. Каталог синтетический, пароль не отправляется
            и не проверяется, данные профиля остаются в этом браузере.
          </p>
        </div>
      </aside>

      <section className="pr-auth-panel" aria-labelledby="auth-title">
        <div className="pr-tabs" role="tablist" aria-label="Вход или регистрация">
          <button type="button" role="tab" aria-selected={mode === 'signup'} className={mode === 'signup' ? 'is-active' : ''} onClick={() => { setMode('signup'); setError('') }}>Регистрация</button>
          <button type="button" role="tab" aria-selected={mode === 'signin'} className={mode === 'signin' ? 'is-active' : ''} onClick={() => { setMode('signin'); setError('') }}>Вход</button>
        </div>

        <h2 id="auth-title" style={{ margin: '24px 0 0', fontSize: 26, fontWeight: 800, letterSpacing: '-.04em' }}>
          {mode === 'signup' ? 'Создайте профиль' : 'С возвращением'}
        </h2>
        <p style={{ margin: '8px 0 0', color: 'var(--pr-muted)', fontSize: 12.5, lineHeight: 1.55 }}>
          {mode === 'signup'
            ? 'Новый профиль начинается с чистого листа: сразу после входа — короткая анкета.'
            : 'Введите e-mail, который указали при регистрации в этом браузере.'}
        </p>

        <form className="pr-form" onSubmit={handleSubmit} noValidate>
          {mode === 'signup' && (
            <label className="pr-field">
              <span>Как вас зовут</span>
              <input value={name} onChange={(event) => { setName(event.target.value); setError('') }} autoComplete="name" placeholder="Анна Петрова" maxLength={60} />
            </label>
          )}
          <label className="pr-field">
            <span>E-mail</span>
            <input type="email" value={email} onChange={(event) => { setEmail(event.target.value); setError('') }} autoComplete="email" placeholder="name@example.com" maxLength={120} />
          </label>
          <label className="pr-field">
            <span>Пароль</span>
            <input type="password" value={password} onChange={(event) => { setPassword(event.target.value); setError('') }} autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} placeholder="Не короче 6 символов" maxLength={64} />
            <small>Демо: пароль не сохраняется и не проверяется.</small>
          </label>

          {error && <p className="pr-error" role="alert">{error}</p>}

          <button className="pr-btn is-red is-wide" type="submit" disabled={pending} style={{ minHeight: 50 }}>
            {pending ? 'Сохраняем…' : mode === 'signup' ? 'Создать профиль →' : 'Войти →'}
          </button>
        </form>

        <div className="pr-divider"><span>или</span></div>

        <button className="pr-demo" type="button" onClick={() => enter(demoAccount, false)}>
          Войти в демо без регистрации
        </button>

        <div className="pr-auth-trust">
          <span>◆ Локальный профиль</span>
          <span>◆ Без SMS</span>
          <span>◆ Синтетические данные</span>
        </div>
        <p className="pr-auth-note">
          Данные хранятся только в этом браузере и очищаются кнопкой «Выйти».
          Подборка — демонстрация рекомендательной системы, не консультация.
        </p>
      </section>
    </div>
  )
}
