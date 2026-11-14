import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import alfaSign from '../assets/alfa-sign-red.svg'

export type Profile = {
  goal: string
  industry: string
  stage: string
  experience: string
}

export type PageContext = {
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

export default function Layout() {
  const { pathname } = useLocation()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [user, setUser] = useState<RegisteredUser | null>(null)
  const [registrationEmail, setRegistrationEmail] = useState('')

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Перейти к содержимому</a>
      <header className="topbar">
        <NavLink className="brand" to="/onboarding">
          <img className="brand-sign" src={alfaSign} alt="" aria-hidden="true" />
          <span className="brand-word">Альфа-Курс</span>
        </NavLink>

        <nav className="navigation" aria-label="Главная навигация">
          <NavLink to="/onboarding">Анкета</NavLink>
          <NavLink to="/feed">Рекомендации</NavLink>
          <NavLink to="/analytics">Аналитика</NavLink>
        </nav>

        <NavLink className="topbar-avatar profile-link" to="/profile" aria-label="Открыть личный кабинет">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
            <circle cx="12" cy="8" r="3.5" />
            <path d="M5 20a7 7 0 0 1 14 0" strokeLinecap="round" />
          </svg>
        </NavLink>
      </header>

      <main key={pathname} id="main-content" className="main-content" tabIndex={-1}>
        <Outlet context={{ profile, setProfile, user, setUser, registrationEmail, setRegistrationEmail }} />
      </main>
    </div>
  )
}
