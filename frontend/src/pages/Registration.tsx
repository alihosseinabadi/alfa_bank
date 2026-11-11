import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useOutletContext } from 'react-router-dom'
import type { PageContext } from '../components/Layout'
import { registerUser } from '../services/api'

export default function Registration() {
  const { user, setUser, profile } = useOutletContext<PageContext>()
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return
    setPending(true)
    setError('')
    try {
      const createdUser = await registerUser(email.trim(), profile)
      setUser(createdUser)
      navigate('/profile')
    } catch (cause) {
      setError(cause instanceof TypeError
        ? 'Не удалось связаться с сервисом. Проверьте подключение и попробуйте ещё раз.'
        : cause instanceof Error ? cause.message : 'Не удалось создать профиль.')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="account-layout">
      <section className="account-intro">
        <span className="account-kicker">АЛЬФА-КУРС</span>
        <h1>Знания для ваших целей</h1>
        <p>Создайте профиль, чтобы начать свой путь в обучении.</p>
        <div className="account-intro-note">
          <span aria-hidden="true">✦</span>
          <p>Один шаг — и вы сможете рассказать о своих задачах.</p>
        </div>
      </section>
      <section className="account-form-panel panel" aria-labelledby="registration-title">
        {user ? (
          <>
            <span className="account-kicker dark-eyebrow">ВАШ ПРОФИЛЬ</span>
            <h2 id="registration-title">Профиль создан</h2>
            <p className="account-description">{user.email}</p>
            <Link className="account-primary" to="/profile">Открыть кабинет <span aria-hidden="true">→</span></Link>
          </>
        ) : (
          <>
            <span className="account-kicker dark-eyebrow">ДОБРО ПОЖАЛОВАТЬ</span>
            <h2 id="registration-title">Создать профиль</h2>
            <p className="account-description">Укажите электронную почту, чтобы создать профиль в Альфа-Курсе.</p>
            <form className="account-form" onSubmit={handleSubmit}>
              <label htmlFor="registration-email">Электронная почта</label>
              <input id="registration-email" type="email" autoComplete="email" required
                placeholder="you@example.ru" value={email}
                onChange={(event) => { setEmail(event.target.value); setError('') }} />
              {error && <p className="account-error" role="alert">{error}</p>}
              <button className="account-primary" type="submit" disabled={pending}>
                {pending ? 'Создаём профиль…' : 'Продолжить'} <span aria-hidden="true">→</span>
              </button>
            </form>
            <p className="account-note">Вход в созданный профиль после обновления страницы пока не подключён.</p>
            <Link className="cabinet-text-link" to="/onboarding">Продолжить без регистрации →</Link>
          </>
        )}
      </section>
    </div>
  )
}
