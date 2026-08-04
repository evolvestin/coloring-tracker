const telegramInitData = window.Telegram?.WebApp?.initData || ''
const isDevBypass = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('dev') === 'true'
const trackerPreviewTelegramId = new URLSearchParams(window.location.search).get('tracker_preview')

export async function api(url, options = {}) {
  const headers = new Headers(options.headers || {})
  if (telegramInitData) headers.set('X-Telegram-Init-Data', telegramInitData)
  if (isDevBypass) headers.set('X-Dev-Mode', 'true')
  if (trackerPreviewTelegramId) {
    headers.set('X-Tracker-Preview-Telegram-ID', trackerPreviewTelegramId)
  }
  if (telegramInitData) {
    headers.set('X-WebApp-Viewport-Width', String(window.innerWidth))
    headers.set('X-WebApp-Viewport-Height', String(window.innerHeight))
  }
  const response = await fetch(url, { ...options, headers })
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).error || 'Не удалось выполнить запрос')
  return response.json()
}
