import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Onboarding from './pages/Onboarding'
import Feed from './pages/Feed'
import Analytics from './pages/Analytics'
import Registration from './pages/Registration'
import ProfilePage from './pages/Profile'

export default function App(){
    return(
        <Routes>
            <Route element={<Layout />}>
                <Route index element={<Navigate to="onboarding" replace />} />
                <Route path="onboarding" element={<Onboarding />} />
                <Route path="feed" element={<Feed />} />
                <Route path="analytics" element={<Analytics />} />
                <Route path="register" element={<Registration />} />
                <Route path="profile" element={<ProfilePage />} />
                <Route path="*" element={<Navigate to="/onboarding" replace />} />
            </Route>
        </Routes>
    )
}
