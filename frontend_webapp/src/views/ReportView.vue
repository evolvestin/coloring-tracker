<script setup>
import '../report.css'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTrackerStore } from '../stores/tracker'
import { formatCount } from '../pluralize'

const router = useRouter()
const route = useRoute()
const store = useTrackerStore()

const month = ref(route.query.month || store.report?.month || '')
const monthPickerOpen = ref(false)
const monthPicker = ref(null)

const report = computed(() => store.report)
const loading = computed(() => store.reportLoading && !store.reportLoaded)

async function load() {
  await store.loadReport(month.value, true)
  if (store.report?.month) {
    month.value = store.report.month
    if (route.query.month !== month.value) router.replace({ query: { ...route.query, month: month.value } })
  }
}

function selectMonth(value) {
  if (value) month.value = value
  monthPickerOpen.value = false
  load()
}
function closeMonthPicker(event) {
  if (monthPicker.value && !monthPicker.value.contains(event.target)) monthPickerOpen.value = false
}
function dayIcons(works) {
  const icons = []
  let needsDefaultFlower = false
  works.forEach(work => {
    if (work.icon) {
      if (!icons.includes(work.icon)) icons.push(work.icon)
    } else {
      needsDefaultFlower = true
    }
  })
  return needsDefaultFlower ? [...icons, '❀'] : icons
}
const activityByColoring = computed(() => {
  if (!report.value) return []
  const colorings = new Map()
  report.value.entries.forEach(entry => {
    entry.works.forEach(work => {
      if (!colorings.has(work.book)) colorings.set(work.book, [])
      colorings.get(work.book).push({ ...work, date: entry.date })
    })
  })
  return [...colorings].map(([title, works]) => {
    const days = new Map()
    works.forEach(work => {
      if (!days.has(work.date)) days.set(work.date, [])
      days.get(work.date).push(work)
    })
    return { title, days: [...days].map(([date, dayWorks]) => ({ date, works: dayWorks })) }
  })
})
const calendar = computed(() => {
  if (!report.value?.month) return []
  const [year, currentMonth] = report.value.month.split('-').map(Number)
  const leadingDays = (new Date(year, currentMonth - 1, 1).getDay() || 7) - 1
  const days = new Date(year, currentMonth, 0).getDate()
  const worksByDay = Object.fromEntries(report.value.entries.map(entry => [entry.date.slice(-2).replace(/^0/, ''), entry.works]))
  return Array.from({ length: leadingDays + days }, (_, index) => {
    if (index < leadingDays) return null
    const day = index - leadingDays + 1
    const count = report.value.days[day] || 0
    const works = worksByDay[day] || []
    return { day, count, level: count ? Math.max(1, Math.ceil((count / report.value.best_day) * 4)) : 0, icons: dayIcons(works) }
  })
})
function capitalize(value) { return value ? value[0].toUpperCase() + value.slice(1) : value }
function dateLabel(value) {
  if (!value) return ''
  const date = new Date(`${value}T12:00:00`)
  if (isNaN(date.getTime())) return ''
  return capitalize(new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', weekday: 'long' }).format(date))
}
function monthLabel(value) {
  if (!value) return ''
  const date = new Date(`${value}-01T12:00:00`)
  if (isNaN(date.getTime())) return ''
  return capitalize(new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' }).format(date))
}

onMounted(() => {
  if (month.value) {
    load()
  } else {
    store.loadReport().then(() => {
      if (store.report?.month) month.value = store.report.month
    })
  }
  document.addEventListener('pointerdown', closeMonthPicker)
})
onBeforeUnmount(() => document.removeEventListener('pointerdown', closeMonthPicker))
</script>

<template>
  <section class="page">
    <header>
      <button class="back" aria-label="Назад" @click="router.back()"><svg viewBox="0 0 24 24" fill="none"><path d="m14.5 5-7 7 7 7"/></svg></button>
      <div><p class="eyebrow">СТАТИСТИКА</p><h1>Отчёт за месяц</h1></div>
      <div v-if="report?.months?.length" ref="monthPicker" class="month-picker">
        <button class="month-picker-trigger" type="button" :aria-expanded="monthPickerOpen" aria-haspopup="listbox" @click="monthPickerOpen = !monthPickerOpen">
          <span>{{ monthLabel(month) }}</span>
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m7 10 5 5 5-5"/></svg>
        </button>
        <div v-if="monthPickerOpen" class="month-picker-menu" role="listbox" aria-label="Выберите месяц">
          <button v-for="item in report.months" :key="item" type="button" role="option" :aria-selected="item === month" :class="{ selected: item === month }" @click="selectMonth(item)">{{ monthLabel(item) }}</button>
        </div>
      </div>
    </header>

    <p v-if="loading && !report" class="muted">Загружаем отчёт…</p>
    <template v-else-if="report?.month">
      <div class="report-card">
        <div class="report-total"><b>{{ report.total }}</b><span>Раскрашено {{ formatCount(report.total, 'page') }}</span></div>
        <div class="chips"><span>🌷 {{ formatCount(report.active_days, 'day') }} активности</span><span>✨ Лучший день: {{ formatCount(report.best_day, 'work') }}</span><span>📚 {{ formatCount(Object.keys(report.books).length, 'book') }}</span></div>
        <h3>Активность</h3>
        <div class="week"><span>Пн</span><span>Вт</span><span>Ср</span><span>Чт</span><span>Пт</span><span>Сб</span><span>Вс</span></div>
        <div class="calendar contribution-calendar">
          <div v-for="(item, index) in calendar" :key="index" class="calendar-day" :class="[item ? `level-${item.level}` : 'empty-day']" :title="item?.count ? `${item.day}: ${formatCount(item.count, 'work')}` : ''">
            <template v-if="item"><span class="day-number">{{ item.day }}</span><span class="day-flowers"><span v-for="(icon, iconIndex) in item.icons" :key="iconIndex">{{ icon }}</span></span></template>
          </div>
        </div>
        <div class="contribution-legend"><span>Меньше</span><i></i><i class="level-1"></i><i class="level-2"></i><i class="level-3"></i><i class="level-4"></i><span>Больше</span></div>
      </div>

      <section class="report-card activity-list">
        <h2>Готовые работы</h2>
        <div class="activity-colorings">
          <article v-for="coloring in activityByColoring" :key="coloring.title" class="activity-coloring">
            <div class="coloring-heading"><span class="work-mark">{{ coloring.days[0].works[0].icon || '❀' }}</span><h3>{{ coloring.title }}</h3></div>
            <div class="activity-days"><div v-for="day in coloring.days" :key="day.date" class="activity-day"><time>{{ dateLabel(day.date) }}</time><div class="activity-works"><div v-for="work in day.works" :key="work.page" class="activity-work"><b>стр. {{ work.page }}</b><span v-if="work.photo" class="photo-mark"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 7.5h3l1.3-2h7.4l1.3 2h3v11H4z"/><circle cx="12" cy="13" r="3.2"/></svg>Фото</span></div></div></div></div>
          </article>
        </div>
      </section>
    </template>
    <div v-else-if="!loading && report" class="empty compact-empty"><div>❀</div><h2>Пока нет работ</h2><p>Первый отчёт появится после завершённой раскраски.</p></div>
  </section>
</template>