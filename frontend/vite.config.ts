import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'

export default defineConfig(({ mode }) => {
    const proxyTarget = loadEnv(mode, process.cwd(), '').VITE_API_PROXY_TARGET
    return {
    plugins: [react()],
    css: {
        postcss: {
            plugins: [tailwindcss(), autoprefixer()]
        },
    },
    server: {
        proxy: proxyTarget ? { '/api': { target: proxyTarget, changeOrigin: true } } : undefined,
    },
    }
})
