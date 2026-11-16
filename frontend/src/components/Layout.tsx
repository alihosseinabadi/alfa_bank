import { useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import alfaSign from '../assets/alfa-sign-red.svg'
import { initials, loadAccount, loadAnswers, saveAccount, saveAnswers } from '../services/account'
import type { Account, Answers } from '../services/account'

export type Profile = {
  goal: string
  industry: string
  stage: string
  experience: string
  difficulty?: string
  note?: string
}

export type PageContext = {
  account: Account | null
  setAccount: (account: Account | null) => void
  profile: Profile | null
  setProfile: (profile: Profile | null) => void
  user: RegisteredUser | null
  setUser: (user: RegisteredUser | null) => void
  registrationEmail: string
  setRegistrationEmail: (email: string) => void
}

export type RegisteredUser = {
  id: number
  email: string
}

function profileFromAnswers(answers: Answers): Profile | null {
  return answers.goal.trim() ? {
    goal: answers.goal,
    industry: answers.industry,
    stage: answers.stage,
    experience: answers.experience,
    difficulty: answers.difficulty,
    note: answers.note,
  } : null
}

export default function Layout() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const [account, setAccountState] = useState<Account | null>(loadAccount)
  const [profile, setProfileState] = useState<Profile | null>(() => profileFromAnswers(loadAnswers()))
  const [user, setUser] = useState<RegisteredUser | null>(null)
  const [registrationEmail, setRegistrationEmail] = useState('')

  const setAccount = (value: Account | null) => { saveAccount(value); setAccountState(value) }

  const setProfile = (value: Profile | null) => {
    if (!value) { saveAnswers(null); setProfileState(null); return }
    const current = loadAnswers()
    saveAnswers({
      goal: value.goal,
      industry: value.industry,
      stage: value.stage,
      experience: value.experience,
      difficulty: value.difficulty ?? current.difficulty,
      note: value.note ?? current.note,
    })
    setProfileState(value)
  }

  function signOut() {
    setAccount(null)
    saveAnswers(null)
    setProfileState(null)
    setUser(null)
    navigate('/auth', { replace: true })
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Перейти к содержимому</a>
      <header className="topbar">
        <NavLink className="brand" to={account ? '/dashboard' : '/auth'}>
          <img className="brand-sign" src={alfaSign} alt="" aria-hidden="true" />
          <span className="brand-word">Альфа-Курс</span>
        </NavLink>

        {account ? (
          <nav className="navigation" aria-label="Главная навигация">
            <NavLink to="/dashboard">Главная</NavLink>
            <NavLink to="/start">Анкета</NavLink>
            <NavLink to="/feed">Рекомендации</NavLink>
            <NavLink to="/analytics">Аналитика</NavLink>
          </nav>
        ) : (
          <span className="topbar-mode">Демо для хакатона</span>
        )}

        {account ? (
          <div className="topbar-user">
            <NavLink className="topbar-avatar profile-link" to="/profile" aria-label="Открыть личный кабинет">
              <span aria-hidden="true">{initials(account.name)}</span>
            </NavLink>
            <button className="topbar-signout" type="button" onClick={signOut}>Выйти</button>
          </div>
        ) : (
          <NavLink className="topbar-signin" to="/auth">Войти</NavLink>
        )}
      </header>

      <main key={pathname} id="main-content" className="main-content" tabIndex={-1}>
        <Outlet context={{ account, setAccount, profile, setProfile, user, setUser, registrationEmail, setRegistrationEmail }} />
      </main>
    </div>
  )
}
