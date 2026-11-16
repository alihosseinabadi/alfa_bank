import { Navigate, Route, Routes } from 'react-router-dom'
import type { ReactElement } from 'react'
import Layout from './components/Layout'
import Auth from './pages/Auth'
import Start from './pages/Start'
import Dashboard from './pages/Dashboard'
import Feed from './pages/Feed'
import Analytics from './pages/Analytics'
import Registration from './pages/Registration'
import ProfilePage from './pages/Profile'
import { loadAccount } from './services/account'

function RequireAccount({ children }: { children: ReactElement }) {
  return loadAccount() ? children : <Navigate to="/auth" replace />
}

export default function App(){
    return(
        <Routes>
            <Route element={<Layout />}>
                <Route index element={<Navigate to={loadAccount() ? 'dashboard' : 'auth'} replace />} />
                <Route path="auth" element={<Auth />} />
                <Route path="start" element={<RequireAccount><Start /></RequireAccount>} />
                <Route path="dashboard" element={<RequireAccount><Dashboard /></RequireAccount>} />
                <Route path="feed" element={<RequireAccount><Feed /></RequireAccount>} />
                <Route path="analytics" element={<RequireAccount><Analytics /></RequireAccount>} />
                <Route path="register" element={<RequireAccount><Registration /></RequireAccount>} />
                <Route path="profile" element={<RequireAccount><ProfilePage /></RequireAccount>} />
                <Route path="onboarding" element={<Navigate to="/start" replace />} />
                <Route path="*" element={<Navigate to={loadAccount() ? '/dashboard' : '/auth'} replace />} />
            </Route>
        </Routes>
    )
}
