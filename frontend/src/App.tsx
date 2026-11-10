import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Onboarding from './pages/Onboarding'
import Feed from './pages/Feed'
import Analytics from './pages/Analytics'

export default function App(){
    return(
        <Routes>
            <Route element={<Layout />}>
                <Route index element={<Navigate to="onboarding" replace />} />
                <Route path="onboarding" element={<Onboarding />} />
                <Route path="feed" element={<Feed />} />
                <Route path="analytics" element={<Analytics />} />
                <Route path="*" element={<Navigate to="/onboarding" replace />} />
            </Route>
        </Routes>
    )
}
