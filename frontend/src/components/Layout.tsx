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
}

export default function Layout() {
  const [profile, setProfile] = useState<Profile | null>(null)

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

        <div className="topbar-avatar" aria-label="Профиль">
          А
        </div>
      </header>

      <main className="main-content">
        <Outlet context={{ profile, setProfile }} />
      </main>
    </div>
  )
}