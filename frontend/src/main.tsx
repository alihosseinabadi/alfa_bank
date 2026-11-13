import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'
import './theme.css'

const rootElement = document.getElementById('root')
if (!rootElement){
    throw new Error('Не найден элемент root')
}
createRoot(rootElement).render(
    <BrowserRouter>
        <App />
    </BrowserRouter>
)
