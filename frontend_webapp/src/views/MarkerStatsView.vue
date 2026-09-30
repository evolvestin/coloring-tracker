<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'

const props = defineProps({ embedded: { type: Boolean, default: false } })
const route = useRoute()
const router = useRouter()
const periodOptions = [
  { value: '1m', label: 'Последний месяц' },
  { value: '3m', label: 'Последние 3 месяца' },
  { value: '6m', label: 'Последние 6 месяцев' },
  { value: '1y', label: 'Последний год' },
  { value: 'all', label: 'Всё время' },
]
const validPeriods = periodOptions.map(option => option.value)
const routePeriod = String(route.query.period || '')
const loading = ref(true)
const loadingMore = ref(false)
const error = ref('')
const stats = ref(null)
const section = ref('personal')
const period = ref(validPeriods.includes(routePeriod) ? routePeriod : '6m')
const importAllowed = ref(true)
const settingsSaving = ref(false)
const markerView = ref('usage')
const stock = ref([])
const stockLoading = ref(false)
const stockSaving = ref(false)
const stockError = ref('')
const stockNotice = ref('')
const stockLoaded = ref(false)
const manufacturers = ref([])
const markerTypes = ref([])
const stockTotal = computed(() => stock.value.reduce((sum, item) => sum + (Number(item.quantity) || 0), 0))
const stockCount = computed(() => stock.value.length)
const active = computed(() => stats.value?.[section.value] || null)
const maxTop = computed(() => Math.max(...(active.value?.top || []).map(item => item.uses), 1))
const maxTrend = computed(() => Math.max(...(active.value?.trend || []).map(item => item.value), 1))

async function fetchStats(append = false) {
  const offset = append ? (active.value?.top?.length || 0) : 0
  const query = new URLSearchParams({ period: period.value, limit: '10', offset: String(offset) })
  const result = await api(`/api/tracker/marker-stats/?${query.toString()}`)
  if (!append) {
    stats.value = result.stats
    return
  }
  const current = stats.value?.[section.value] || {}
  const incoming = result.stats?.[section.value] || {}
  stats.value = {
    ...stats.value,
    period: result.stats.period,
    [section.value]: {
      ...current,
      ...incoming,
      top: [...(current.top || []), ...(incoming.top || [])],
    },
  }
}
async function load() {
  loading.value = true
  error.value = ''
  try {
    await fetchStats()
    const settings = await api('/api/tracker/marker-settings/')
    importAllowed.value = settings.import_allowed
  } catch (err) { error.value = err.message } finally { loading.value = false }
}
async function changePeriod() {
  loading.value = true
  error.value = ''
  try {
    await router.replace({ query: { ...route.query, period: period.value } })
    await fetchStats()
  } catch (err) { error.value = err.message } finally { loading.value = false }
}
async function loadMore() {
  if (loadingMore.value || !active.value?.top_has_more) return
  loadingMore.value = true
  error.value = ''
  try { await fetchStats(true) } catch (err) { error.value = err.message } finally { loadingMore.value = false }
}
async function toggleImport() {
  settingsSaving.value = true
  try {
    const result = await api('/api/tracker/marker-settings/', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ import_allowed: !importAllowed.value }) })
    importAllowed.value = result.import_allowed
  } catch (err) { error.value = err.message } finally { settingsSaving.value = false }
}
async function loadStock() {
  if (stockLoading.value) return
  stockLoading.value = true
  stockError.value = ''
  try {
    const result = await api('/api/tracker/marker-stock/')
    stock.value = (result.items || []).map(item => ({ ...item, marker_id: item.id }))
    manufacturers.value = result.manufacturers || []
    markerTypes.value = result.marker_types || []
    stockLoaded.value = true
  } catch (err) { stockError.value = err.message } finally { stockLoading.value = false }
}
function addStockRow() {
  if (stock.value.length >= 300) return
  stock.value.push({ id: null, marker_id: null, symbol: '', number: '', manufacturer: '', marker_type: '', quantity: 1 })
  stockNotice.value = ''
}
function removeStockRow(index) { stock.value.splice(index, 1); stockNotice.value = '' }
async function saveStock() {
  stockSaving.value = true
  stockError.value = ''
  stockNotice.value = ''
  try {
    const result = await api('/api/tracker/marker-stock/', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: stock.value.map(item => ({
        id: item.id,
        marker_id: item.marker_id,
        symbol: item.symbol,
        number: item.number,
        manufacturer: item.manufacturer,
        marker_type: item.marker_type,
        quantity: Number(item.quantity),
      })) }),
    })
    if (result.saved !== stock.value.length) throw new Error('Не все запасы удалось сохранить. Обновите экран и попробуйте снова.')
    await loadStock()
    stockNotice.value = 'Запасы сохранены.'
  } catch (err) { stockError.value = err.message } finally { stockSaving.value = false }
}
function changeMarkerView(value) {
  markerView.value = value
  if (value === 'stock' && !stockLoaded.value) loadStock()
}
function monthLabel(value) {
  const [year, month] = value.split('-')
  return new Date(Number(year), Number(month) - 1, 1).toLocaleDateString('ru-RU', { month: 'short' }).replace('.', '')
}
function plural(value, one, few, many) {
  const mod10 = value % 10
  const mod100 = value % 100
  if (mod100 >= 11 && mod100 <= 14) return many
  if (mod10 === 1) return one
  if (mod10 >= 2 && mod10 <= 4) return few
  return many
}
function usageText(item) {
  const summary = item.usage_summary || []
  if (!summary.length) return 'не указали'
  return summary.map(entry => `${entry.label}${entry.count > 1 ? ` ×${entry.count}` : ''}`).join(' · ')
}
onMounted(load)
</script>

<template>
  <section class="page marker-stats-page">
    <header v-if="!props.embedded" class="main-header"><div><p class="eyebrow">АНАЛИТИКА</p><h1>Мои расходники</h1><p>Понимайте, какие цвета уходят быстрее.</p></div></header>
    <div v-if="loading" class="empty">Собираем статистику…</div>
    <p v-else-if="error" class="form-error" role="alert">{{ error }}</p>
    <template v-else-if="stats && active">
      <div class="marker-stat-tabs marker-view-tabs" role="tablist"><button :class="{ active: markerView === 'usage' }" role="tab" :aria-selected="markerView === 'usage'" @click="changeMarkerView('usage')">Расход</button><button :class="{ active: markerView === 'stock' }" role="tab" :aria-selected="markerView === 'stock'" @click="changeMarkerView('stock')">Мой запас</button></div>
      <template v-if="markerView === 'usage'">
      <div class="marker-stat-tabs marker-audience-tabs" role="tablist"><button :class="{ active: section === 'personal' }" role="tab" @click="section = 'personal'">Моя статистика</button><button :class="{ active: section === 'global' }" role="tab" @click="section = 'global'">Общая статистика</button></div>
      <label class="marker-period-filter">Период<select v-model="period" @change="changePeriod"><option v-for="option in periodOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
      <article class="marker-insight-card"><div class="marker-card-heading"><div><p class="eyebrow">ИСПОЛЬЗОВАНИЕ</p><h2>Расходники и расход</h2></div><span>{{ active.top_total }}</span></div><div v-if="active.top.length" class="marker-ranking"><div v-for="(item, index) in active.top" :key="item.marker.id" class="marker-ranking-row"><span class="marker-rank">{{ index + 1 }}</span><div class="marker-ranking-copy"><div><b>{{ item.marker.manufacturer_label }} · {{ item.marker.marker_type_label }} · {{ item.marker.number }}</b><small>{{ item.uses }} {{ plural(item.uses, 'работа', 'работы', 'работ') }} · {{ item.books }} {{ plural(item.books, 'раскраска', 'раскраски', 'раскрасок') }}</small></div><small class="marker-usage-copy">Расход: {{ usageText(item) }}</small><div class="marker-ranking-line"><i :style="{ width: `${item.uses / maxTop * 100}%` }"></i></div></div><strong>{{ item.uses }}</strong></div></div><div v-else class="palette-empty">За выбранный период расходников нет.</div><div v-if="active.top_has_more" class="marker-more"><button type="button" class="secondary" :disabled="loadingMore" @click="loadMore">{{ loadingMore ? 'Загружаем…' : 'Показать ещё 10' }}</button><small>Показано {{ active.top.length }} из {{ active.top_total }}</small></div></article>
      <div class="marker-kpi-grid"><article><span>Маркеров добавлено</span><b>{{ active.total_entries }}</b><small>в {{ active.palettes }} {{ plural(active.palettes, 'работе', 'работах', 'работах') }}</small></article></div>
      <article class="marker-insight-card"><div class="marker-card-heading"><div><p class="eyebrow">ДИНАМИКА</p><h2>Добавлено по месяцам</h2></div><span>6 мес.</span></div><p class="palette-muted">Сколько расходников добавили в работы</p><div class="marker-trend"><div v-for="item in active.trend" :key="item.month" class="marker-trend-column"><div class="marker-trend-bar"><i :style="{ height: `${Math.max(item.value / maxTrend * 100, item.value ? 9 : 2)}%` }"></i></div><small>{{ monthLabel(item.month) }}</small><b>{{ item.value }}</b></div></div></article>
      <article v-if="section === 'global'" class="marker-insight-card anonymous-card"><div class="marker-card-heading"><div><p class="eyebrow">УЧАСТНИКИ</p><h2>Кто добавил больше</h2></div><span>{{ active.users }}</span></div><p class="palette-muted">Рейтинг по количеству добавленных расходников</p><div class="anonymous-leaders"><div v-for="leader in active.leaderboard" :key="leader.rank"><span>№{{ leader.rank }}</span><i><b :style="{ width: `${leader.entries / (active.leaderboard[0]?.entries || 1) * 100}%` }"></b></i><strong>{{ leader.entries }}</strong></div></div></article>
      <article v-if="section === 'global'" class="marker-influence-card"><div><p class="eyebrow">МОЯ ДОЛЯ</p><h2>Мой результат</h2><p>На вашу долю приходится {{ active.my_share_percent }}% всех записей о расходниках.</p></div><strong v-if="active.my_rank">№{{ active.my_rank }}</strong><strong v-else>—</strong></article>
      <article class="marker-settings-card"><div><b>Делиться моими списками расходников</b><small>Другие пользователи смогут использовать ваши списки в своих работах.</small></div><button type="button" class="mini-switch" :class="{ active: importAllowed }" role="switch" :aria-checked="importAllowed" :disabled="settingsSaving" @click="toggleImport"><i></i></button></article>
      </template>
      <section v-else class="marker-stock-view">
        <div class="marker-stock-heading"><div><h2>Мои запасы</h2><p>Сколько маркеров и ручек есть сейчас</p></div><button type="button" class="add-marker-button" :disabled="stock.length >= 300" @click="addStockRow">+ Добавить</button></div>
        <div v-if="stockLoading" class="empty">Загружаем запасы…</div>
        <template v-else>
          <div class="marker-stock-summary"><article><span>Всего</span><b>{{ stockTotal }}</b><small>маркеров и ручек</small></article><article><span>Позиций</span><b>{{ stockCount }}</b><small>разных номеров</small></article></div>
          <div v-if="!stock.length" class="palette-empty">Запас пока пуст. Добавьте маркеры вручную — палитры работ на него не влияют.</div>
          <div class="marker-stock-list">
            <article v-for="(item, index) in stock" :key="item.id || `new-${index}`" class="marker-stock-row" :class="{ 'marker-stock-row--new': !item.id, 'marker-stock-row--saved': !!item.id }">
              <div class="marker-stock-fields">
                <label v-if="!item.id" class="marker-stock-field">Значок<input v-model="item.symbol" maxlength="32" placeholder="✦"></label>
                <div v-else class="marker-stock-symbol">{{ item.symbol || '✦' }}</div>
                <label class="marker-stock-field">Номер<input v-model="item.number" maxlength="64" placeholder="599" :readonly="!!item.id"></label>
                <label v-if="!item.id" class="marker-stock-field">Производитель<select v-model="item.manufacturer"><option value="" disabled>Выберите</option><option v-for="option in manufacturers" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
                <div v-else class="marker-stock-brand">{{ item.manufacturer_label }} · {{ item.marker_type_label }}</div>
                <label v-if="!item.id" class="marker-stock-field">Тип<select v-model="item.marker_type"><option value="" disabled>Выберите</option><option v-for="option in markerTypes" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
                <label class="marker-stock-field marker-stock-quantity">Количество<input v-model.number="item.quantity" type="number" min="0" max="100000" inputmode="numeric"></label>
              </div>
              <button type="button" class="remove-marker-button" :aria-label="`Удалить ${item.number || 'новую позицию'}`" @click="removeStockRow(index)">×</button>
            </article>
          </div>
          <p v-if="stockError" class="form-error" role="alert">{{ stockError }}</p><p v-if="stockNotice" class="palette-notice" role="status">✓ {{ stockNotice }}</p>
          <button type="button" class="primary palette-save" :disabled="stockSaving" @click="saveStock">{{ stockSaving ? 'Сохраняем…' : 'Сохранить запасы' }}</button>
        </template>
      </section>
    </template>
  </section>
</template>
