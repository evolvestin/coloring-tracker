<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'

const props = defineProps({ userBookId: { type: [String, Number], required: true }, pageId: { type: [String, Number], required: true }, embedded: { type: Boolean, default: false } })
const open = ref(props.embedded)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')
const palette = ref(null)
const shared = ref([])
const manufacturerOptions = ref([])
const markerTypeOptions = ref([])
const sharedIndex = ref(0)
const rows = ref([])
const formOpen = ref(false)
const suggestions = ref({})
const pendingImport = ref(null)

const activeShared = computed(() => shared.value[sharedIndex.value] || null)
const count = computed(() => rows.value.length)

function cloneItems(items = []) {
  return items.map(item => ({
    marker_id: item.marker?.id || item.marker_id || null,
    symbol: item.symbol || item.marker?.symbol || '',
    number: item.marker?.number || item.number || '',
    manufacturer: item.marker?.manufacturer || item.manufacturer || '',
    marker_type: item.marker?.marker_type || item.marker_type || '',
    usage_level: item.usage_level || '',
  }))
}
function markerChipDetail(marker, usageLevel) {
  const brand = marker?.manufacturer_label && marker.manufacturer_label !== 'Не указан'
    ? `${marker.manufacturer_label} · `
    : ''
  const type = marker?.marker_type_label || 'Маркер'
  const usage = { little: 'Немного', medium: 'Средне', much: 'Много' }[usageLevel] || 'Расход не указан'
  return `${brand}${type} · ${usage}`
}
async function loadPanel() {
  if (loading.value || palette.value) return
  loading.value = true
  error.value = ''
  try {
    const result = await api(`/api/tracker/books/${props.userBookId}/pages/${props.pageId}/palette/`)
    palette.value = result.palette
    manufacturerOptions.value = result.manufacturers || []
    markerTypeOptions.value = result.marker_types || []
    rows.value = cloneItems(result.palette?.items)
    shared.value = result.shared || []
    formOpen.value = shared.value.length === 0
  } catch (err) {
    error.value = err.message
  } finally { loading.value = false }
}
async function openPanel() {
  open.value = !open.value
  if (open.value) await loadPanel()
}
function openOwnForm() { formOpen.value = true }
function addRow() {
  if (rows.value.length >= 30) return
  rows.value.push({ marker_id: null, symbol: '', number: '', manufacturer: '', marker_type: '', usage_level: '' })
}
function removeRow(index) { rows.value.splice(index, 1) }
function updateText(row) { row.marker_id = null }
function updateManufacturer(row) { row.marker_id = null }
function normalizeMarkerNumber(value) {
  return String(value || '').toUpperCase().replace(/[^A-Z0-9 -]/g, '').slice(0, 64)
}
function updateNumber(row) {
  row.number = normalizeMarkerNumber(row.number)
  row.marker_id = null
}
function updateMarkerType(row) { row.marker_id = null }
async function findMarkers(index) {
  const row = rows.value[index]
  const query = `${row.symbol} ${row.number}`.trim()
  if (query.length < 1) { suggestions.value[index] = []; return }
  try {
    const result = await api(`/api/tracker/markers/?q=${encodeURIComponent(query)}`)
    suggestions.value[index] = result.markers || []
  } catch { suggestions.value[index] = [] }
}
function chooseMarker(row, marker, index) {
  row.marker_id = marker.id
  row.symbol = marker.symbol
  row.number = marker.number
  row.manufacturer = marker.manufacturer || ''
  row.marker_type = marker.marker_type || ''
  suggestions.value[index] = []
}
function activatePreview(item) { previewImport(item) }
function selectShared(index) { sharedIndex.value = index; pendingImport.value = null }
function previewImport(item) { pendingImport.value = item }
const importQuestion = computed(() => palette.value?.items?.length
  ? 'Заменить свою палитру этим составом?'
  : 'Добавить этот состав в палитру работы?')
const importButtonLabel = computed(() => palette.value?.items?.length ? 'Заменить палитру' : 'Добавить в работу')
async function usePreview() {
  if (!pendingImport.value || saving.value) return
  saving.value = true
  error.value = ''
  try {
    const result = await api(`/api/tracker/books/${props.userBookId}/pages/${props.pageId}/palette/import/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ palette_id: pendingImport.value.id }),
    })
    palette.value = result.palette
    rows.value = cloneItems(result.palette?.items)
    formOpen.value = true
    notice.value = 'Палитра импортирована. Её можно изменить перед следующим сохранением.'
    pendingImport.value = null
  } catch (err) { error.value = err.message } finally { saving.value = false }
}
async function save() {
  error.value = ''
  notice.value = ''
  const cleanRows = rows.value.filter(row => row.symbol.trim() || row.number.trim() || row.manufacturer || row.marker_type)
  if (cleanRows.some(row => !row.symbol.trim() || !row.number.trim() || !row.manufacturer || !row.marker_type)) {
    error.value = 'Заполните производителя, тип, значок и номер или удалите пустую строку.'
    return
  }
  saving.value = true
  try {
    const result = await api(`/api/tracker/books/${props.userBookId}/pages/${props.pageId}/palette/`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: cleanRows.map(row => ({ marker_id: row.marker_id, symbol: row.symbol.trim(), number: normalizeMarkerNumber(row.number), manufacturer: row.manufacturer, marker_type: row.marker_type, usage_level: row.usage_level })) }),
    })
    palette.value = result.palette
    rows.value = cloneItems(result.palette?.items)
    notice.value = 'Палитра сохранена.'
  } catch (err) { error.value = err.message } finally { saving.value = false }
}
watch(() => props.pageId, () => {
  palette.value = null
  rows.value = []
  shared.value = []
  formOpen.value = false
  open.value = props.embedded
  if (props.embedded) loadPanel()
})
onMounted(() => {
  if (props.embedded) loadPanel()
})
</script>

<template>
  <div class="marker-palette-panel" :class="{ 'marker-palette-panel--embedded': embedded }">
    <button v-if="!embedded" type="button" class="palette-toggle" :class="{ active: open }" @click="openPanel">
      <span class="palette-toggle-icon">✦</span>
      <span><b>Палитра</b><small>{{ count ? `${count} ${count === 1 ? 'позиция' : count < 5 ? 'позиции' : 'позиций'}` : 'Добавьте использованные цвета' }}</small></span>
      <i aria-hidden="true">{{ open ? '⌃' : '⌄' }}</i>
    </button>
    <div v-if="embedded || open" class="palette-body">
      <div v-if="loading" class="palette-loading">Загружаем палитры…</div>
      <template v-else>
        <div v-if="shared.length" class="shared-palette-card">
          <div class="shared-palette-head"><div><p class="eyebrow">ГОТОВЫЕ ПАЛИТРЫ</p></div><label class="shared-palette-picker-label"><select v-model.number="sharedIndex" aria-label="Выбранная палитра" @change="pendingImport = null"><option v-for="(_, index) in shared" :key="index" :value="index">Вариант {{ index + 1 }} из {{ shared.length }}</option></select></label></div>
          <div class="shared-marker-preview shared-marker-preview--clickable" role="button" tabindex="0" aria-label="Посмотреть готовую палитру" @click="activatePreview(activeShared)" @keydown.enter="activatePreview(activeShared)" @keydown.space.prevent="activatePreview(activeShared)"><span v-for="item in activeShared.items" :key="`${item.marker.id}-${item.symbol}-${item.usage_level}`" class="marker-chip"><b>{{ item.symbol || item.marker.symbol }}</b><span>{{ item.marker.number }}</span><small>{{ markerChipDetail(item.marker, item.usage_level) }}</small></span></div>
          <p class="palette-muted">Выбрали {{ activeShared.popularity }} {{ activeShared.popularity === 1 ? 'раз' : 'раза' }}</p>
          <div class="shared-palette-actions"><button type="button" class="secondary" @click="previewImport(activeShared)">Выбрать эту палитру</button></div>
          <div v-if="pendingImport" class="import-preview"><b>{{ importQuestion }}</b><p class="palette-muted">{{ pendingImport.items.length }} {{ pendingImport.items.length === 1 ? 'позиция' : pendingImport.items.length < 5 ? 'позиции' : 'позиций' }}: {{ pendingImport.items.map(item => `${item.marker.marker_type_label} ${item.marker.number}`).join(', ') }}</p><div class="confirm-actions"><button type="button" class="text-action" @click="pendingImport = null">Назад</button><button type="button" class="primary" @click="usePreview">{{ saving ? 'Добавляем…' : importButtonLabel }}</button></div></div>
        </div>
        <button v-if="shared.length && !formOpen" type="button" class="palette-own-action" @click="openOwnForm">{{ rows.length ? 'Изменить свою палитру' : 'Заполнить свою палитру' }}</button>
        <template v-if="formOpen">
          <div class="palette-form-head"><div><b>Моя палитра</b><small>Укажите тип, номер и, если хотите, примерный расход.</small></div><button type="button" class="add-marker-button" :disabled="rows.length >= 30" @click="addRow">+ Добавить</button></div>
          <div v-if="!rows.length" class="palette-empty">Пока пусто. Добавьте маркер или ручку, которые использовали в этом рисунке.</div>
          <div v-for="(row, index) in rows" :key="index" class="marker-row">
          <span class="marker-row-index">{{ index + 1 }}</span>
          <div class="marker-field marker-symbol-field"><label>Значок<input v-model="row.symbol" maxlength="32" placeholder="✦" @input="updateText(row); findMarkers(index)"><div v-if="suggestions[index]?.length" class="marker-suggestions"><button v-for="marker in suggestions[index]" :key="marker.id" type="button" @click="chooseMarker(row, marker, index)"><b>{{ marker.manufacturer_label }} · {{ marker.marker_type_label }}</b><span>{{ marker.symbol }} {{ marker.number }}</span></button></div></label></div>
          <label class="marker-field marker-number-field">Номер<input v-model="row.number" maxlength="64" pattern="[A-Z0-9 -]+" title="Только английские буквы, цифры, пробелы и дефисы" placeholder="599" inputmode="text" autocomplete="off" @input="updateNumber(row); findMarkers(index)"></label>
          <label class="marker-field marker-manufacturer-field">Производитель<select v-model="row.manufacturer" @change="updateManufacturer(row)"><option v-for="manufacturer in manufacturerOptions" :key="manufacturer.value" :value="manufacturer.value">{{ manufacturer.label }}</option></select></label>
          <label class="marker-field marker-type-field">Тип<select v-model="row.marker_type" @change="updateMarkerType(row)"><option value="" disabled>Выберите</option><option v-for="markerType in markerTypeOptions" :key="markerType.value" :value="markerType.value">{{ markerType.label }}</option></select></label>
          <label class="marker-field marker-usage-field">Расход<select v-model="row.usage_level"><option value="">Не знаю</option><option value="little">Немного</option><option value="medium">Средне</option><option value="much">Много</option></select></label>
          <button type="button" class="remove-marker-button" aria-label="Удалить позицию" @click="removeRow(index)">×</button>
          </div>
          <p class="marker-tip"><span>i</span>Номер: английские буквы, цифры, пробелы и дефисы. Регистр исправится автоматически.</p>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p><p v-if="notice" class="palette-notice" role="status">✓ {{ notice }}</p>
          <button type="button" class="primary palette-save" :disabled="saving" @click="save">{{ saving ? 'Сохраняем…' : 'Сохранить палитру' }}</button>
        </template>
        <p v-else-if="error" class="form-error" role="alert">{{ error }}</p>
      </template>
    </div>
  </div>
</template>
