import type { Profile, RegisteredUser } from '../components/Layout'

const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

export async function registerUser(email: string, profile: Profile | null): Promise<RegisteredUser> {
  const response = await fetch(`${baseUrl}/api/v1/users/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email,
      business_status: profile?.stage || null,
      business_sphere: profile?.industry || null,
      current_goal: profile?.goal || null,
      experience: profile?.experience || null,
    }),
  })

  if (response.status === 409) {
    throw new Error('Пользователь с таким email уже существует.')
  }
  if (!response.ok) {
    throw new Error('Не удалось создать профиль. Попробуйте ещё раз.')
  }

  const data: unknown = await response.json()
  if (
    !data || typeof data !== 'object' ||
    !('id' in data) || typeof data.id !== 'number' ||
    !('email' in data) || typeof data.email !== 'string'
  ) {
    throw new Error('Сервис вернул неожиданный ответ.')
  }
  return { id: data.id, email: data.email }
}
