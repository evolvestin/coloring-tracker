/**
 * Russian noun forms used alongside numeric counters in the WebApp.
 * Add new counters here instead of choosing a word form in a component.
 */
const nouns = {
  book: ['раскраска', 'раскраски', 'раскрасок'],
  page: ['страница', 'страницы', 'страниц'],
  work: ['работа', 'работы', 'работ'],
  day: ['день', 'дня', 'дней'],
}

export function pluralize(count, noun) {
  const forms = nouns[noun]
  if (!forms) throw new Error(`Unknown noun for pluralization: ${noun}`)

  const value = Math.abs(Number(count))
  const lastTwoDigits = value % 100
  const lastDigit = value % 10

  if (lastTwoDigits >= 11 && lastTwoDigits <= 14) return forms[2]
  if (lastDigit === 1) return forms[0]
  if (lastDigit >= 2 && lastDigit <= 4) return forms[1]
  return forms[2]
}

export function formatCount(count, noun) {
  return `${count} ${pluralize(count, noun)}`
}
