const telegramInitData = window.Telegram?.WebApp?.initData || ''
const isDevBypass = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('dev') === 'true'
const localPreviewTelegramId = new URLSearchParams(window.location.search).get('local_preview')

export async function api(url, options = {}) {
  const headers = new Headers(options.headers || {})
  if (telegramInitData) headers.set('X-Telegram-Init-Data', telegramInitData)
  if (isDevBypass) headers.set('X-Dev-Mode', 'true')
  if (localPreviewTelegramId) headers.set('X-Local-Preview-Telegram-ID', localPreviewTelegramId)
  if (telegramInitData) {
    headers.set('X-WebApp-Viewport-Width', String(window.innerWidth))
    headers.set('X-WebApp-Viewport-Height', String(window.innerHeight))
  }
  const response = await fetch(url, { ...options, headers })
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).error || 'Не удалось выполнить запрос')
  return response.json()
}
