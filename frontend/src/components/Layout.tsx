import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

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
}

export type RegisteredUser = {
  id: number
  email: string
}

export default function Layout() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [user, setUser] = useState<RegisteredUser | null>(null)

  return (
    <div className="app-shell">
      <header className="topbar">
        <NavLink className="brand" to="/onboarding">
          <span className="brand-icon" aria-hidden="true">✦</span>
          <span>Альфа-Курс</span>
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

      <main className="main-content">
        <Outlet context={{ profile, setProfile, user, setUser }} />
      </main>
    </div>
  )
}
