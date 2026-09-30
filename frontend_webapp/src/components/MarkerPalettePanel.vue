<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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
const editingIndex = ref(null)
const editDraft = ref(null)
const editError = ref('')
const suggestions = ref([])
const pendingImport = ref(null)
const deleteConfirmIndex = ref(null)
const deleteFromEditor = ref(false)
const swipeIndex = ref(null)
const swipeOffset = ref(0)
const swipeDragging = ref(false)
let rowGesture = null
let rowGestureTimer = null

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
function markerMeta(row) {
  const manufacturer = manufacturerOptions.value.find(item => item.value === row.manufacturer)?.label
  const type = markerTypeOptions.value.find(item => item.value === row.marker_type)?.label
  const usage = { little: 'мало', medium: 'средне', much: 'много' }[row.usage_level] || 'без расхода'
  return [type || 'Маркер', manufacturer && manufacturer !== 'Не указан' ? manufacturer : '', usage].filter(Boolean).join(' · ')
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
    formOpen.value = rows.value.length === 0 && shared.value.length === 0
  } catch (err) {
    error.value = err.message
  } finally { loading.value = false }
}
async function openPanel() {
  open.value = !open.value
  if (open.value) await loadPanel()
}
function openOwnForm() { formOpen.value = true }
function cancelOwnForm() {
  rows.value = cloneItems(palette.value?.items)
  formOpen.value = false
  editDraft.value = null
  error.value = ''
}
function blankRow() { return { marker_id: null, symbol: '', number: '', manufacturer: '', marker_type: '', usage_level: '' } }
function openRowEditor(index) {
  editingIndex.value = index
  editDraft.value = { ...rows.value[index] }
  editError.value = ''
  suggestions.value = []
}
function openNewRowEditor() {
  if (rows.value.length >= 30) return
  editingIndex.value = null
  editDraft.value = blankRow()
  editError.value = ''
  suggestions.value = []
}
function clearRowGestureTimer() {
  if (rowGestureTimer) clearTimeout(rowGestureTimer)
  rowGestureTimer = null
}
function startRowGesture(event, index) {
  if (event.button !== undefined && event.button !== 0) return
  clearRowGestureTimer()
  rowGesture = { index, pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, lastX: event.clientX, moved: false, longPressed: false }
  swipeIndex.value = index
  swipeOffset.value = 0
  swipeDragging.value = false
  try { event.currentTarget.setPointerCapture(event.pointerId) } catch {}
  rowGestureTimer = setTimeout(() => {
    if (!rowGesture || rowGesture.index !== index || rowGesture.moved) return
    rowGesture.longPressed = true
    swipeOffset.value = 0
    openRowEditor(index)
  }, 520)
}
function moveRowGesture(event) {
  if (!rowGesture || rowGesture.pointerId !== event.pointerId) return
  const dx = event.clientX - rowGesture.startX
  const dy = event.clientY - rowGesture.startY
  rowGesture.lastX = event.clientX
  if (Math.abs(dx) > 9 || Math.abs(dy) > 9) {
    rowGesture.moved = true
    clearRowGestureTimer()
  }
  if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 9) {
    swipeDragging.value = true
    swipeOffset.value = Math.max(-92, Math.min(92, dx))
  }
}
function finishRowGesture(event) {
  if (!rowGesture || (event.pointerId !== undefined && rowGesture.pointerId !== event.pointerId)) return
  clearRowGestureTimer()
  const gesture = rowGesture
  rowGesture = null
  swipeDragging.value = false
  if (gesture.longPressed || editDraft.value) {
    swipeIndex.value = null
    swipeOffset.value = 0
    return
  }
  const dx = (event.clientX ?? gesture.lastX) - gesture.startX
  const dy = (event.clientY ?? gesture.startY) - gesture.startY
  if (Math.abs(dx) >= 64 && Math.abs(dx) > Math.abs(dy)) {
    swipeIndex.value = gesture.index
    swipeOffset.value = Math.sign(dx) * 76
    requestDelete(gesture.index, false)
  } else {
    swipeIndex.value = null
    swipeOffset.value = 0
  }
}
function requestDelete(index, fromEditor = false) {
  deleteConfirmIndex.value = index
  deleteFromEditor.value = fromEditor
}
function cancelDelete() {
  deleteConfirmIndex.value = null
  deleteFromEditor.value = false
  swipeIndex.value = null
  swipeOffset.value = 0
}
function confirmDelete() {
  if (deleteConfirmIndex.value === null) return
  rows.value.splice(deleteConfirmIndex.value, 1)
  if (deleteFromEditor.value) editDraft.value = null
  deleteConfirmIndex.value = null
  deleteFromEditor.value = false
  swipeIndex.value = null
  swipeOffset.value = 0
  suggestions.value = []
}
function commitRowDraft() {
  if (!editDraft.value) return
  const row = { ...editDraft.value, symbol: editDraft.value.symbol.trim(), number: normalizeMarkerNumber(editDraft.value.number) }
  if (!row.symbol || !row.number || !row.manufacturer || !row.marker_type) {
    editError.value = 'Заполните значок, номер, производителя и тип.'
    return
  }
  if (editingIndex.value === null) rows.value.push(row)
  else rows.value.splice(editingIndex.value, 1, row)
  editDraft.value = null
  editError.value = ''
  suggestions.value = []
}
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
async function findMarkers() {
  const row = editDraft.value
  if (!row) return
  const query = `${row.symbol} ${row.number}`.trim()
  if (query.length < 1) { suggestions.value = []; return }
  try {
    const result = await api(`/api/tracker/markers/?q=${encodeURIComponent(query)}`)
    suggestions.value = result.markers || []
  } catch { suggestions.value = [] }
}
function chooseMarker(marker) {
  if (!editDraft.value) return
  editDraft.value.marker_id = marker.id
  editDraft.value.symbol = marker.symbol
  editDraft.value.number = marker.number
  editDraft.value.manufacturer = marker.manufacturer || ''
  editDraft.value.marker_type = marker.marker_type || ''
  suggestions.value = []
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
    formOpen.value = false
    notice.value = 'Палитра сохранена.'
  } catch (err) { error.value = err.message } finally { saving.value = false }
}
watch(() => props.pageId, () => {
  palette.value = null
  rows.value = []
  shared.value = []
  formOpen.value = false
  editDraft.value = null
  open.value = props.embedded
  if (props.embedded) loadPanel()
})
onMounted(() => {
  if (props.embedded) loadPanel()
})
onBeforeUnmount(() => clearRowGestureTimer())
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
        <div v-if="rows.length && !formOpen" class="own-palette-summary">
          <div class="own-palette-summary-head"><b>Моя палитра <small>{{ rows.length }} поз.</small></b></div>
          <div class="own-palette-list">
            <div v-for="(row, index) in rows" :key="`${row.marker_id || row.number}-${index}`" class="own-palette-row own-palette-row--interactive" :style="swipeIndex === index ? { transform: `translateX(${swipeOffset}px)` } : undefined" :class="{ 'own-palette-row--dragging': swipeDragging && swipeIndex === index }" @pointerdown="startRowGesture($event, index)" @pointermove="moveRowGesture" @pointerup="finishRowGesture" @pointercancel="finishRowGesture">
              <b class="own-palette-symbol">{{ row.symbol || '✦' }}</b><b class="own-palette-number">{{ row.number || 'Без номера' }}</b>
              <span class="own-palette-meta">{{ markerMeta(row) }}</span>
              <button type="button" class="palette-row-edit" :aria-label="`Редактировать ${row.number || 'позицию'}`" :title="`Редактировать ${row.number || 'позицию'}`" @pointerdown.stop @click.stop="openRowEditor(index)">✎</button>
            </div>
          </div>
        </div>
        <button v-if="shared.length && !formOpen && !rows.length" type="button" class="palette-own-action" @click="openOwnForm">Заполнить свою палитру</button>
        <template v-if="formOpen">
          <div class="palette-form-head"><div><b>Редактирование палитры</b><small>Измените нужную позицию или добавьте новую.</small></div><div class="palette-form-actions"><button v-if="palette?.items?.length" type="button" class="palette-cancel-action" @click="cancelOwnForm">Отмена</button><button type="button" class="add-marker-button" :disabled="rows.length >= 30" @click="openNewRowEditor">+ Добавить</button></div></div>
          <div v-if="!rows.length" class="palette-empty">Палитра пока пустая. Добавьте маркер или ручку.</div>
          <div v-else class="own-palette-list own-palette-list--editing">
            <div v-for="(row, index) in rows" :key="index" class="own-palette-row own-palette-row--interactive">
              <b class="own-palette-symbol">{{ row.symbol || '✦' }}</b><b class="own-palette-number">{{ row.number || 'Без номера' }}</b>
              <span class="own-palette-meta">{{ markerMeta(row) }}</span>
              <button type="button" class="palette-row-edit" :aria-label="`Редактировать ${row.number || 'позицию'}`" :title="`Редактировать ${row.number || 'позицию'}`" @click="openRowEditor(index)">✎</button>
            </div>
          </div>
          <p class="marker-tip"><span>i</span>Номер: английские буквы, цифры, пробелы и дефисы.</p>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p><p v-if="notice" class="palette-notice" role="status">✓ {{ notice }}</p>
          <button type="button" class="primary palette-save" :disabled="saving" @click="save">{{ saving ? 'Сохраняем…' : 'Сохранить палитру' }}</button>
        </template>
        <p v-else-if="error" class="form-error" role="alert">{{ error }}</p>
        <div v-if="editDraft" class="marker-edit-backdrop" @click.self="editDraft = null; suggestions = []">
          <section class="marker-edit-modal" role="dialog" aria-modal="true" :aria-label="editingIndex === null ? 'Добавить маркер' : `Редактировать ${rows[editingIndex].number}`">
            <h3>{{ editingIndex === null ? 'Новый маркер' : `Маркер ${rows[editingIndex].number}` }}</h3>
            <div class="marker-edit-fields">
              <label>Значок<input v-model="editDraft.symbol" maxlength="32" placeholder="✦" @input="updateText(editDraft); findMarkers()"></label>
              <label>Номер<input v-model="editDraft.number" maxlength="64" pattern="[A-Z0-9 -]+" placeholder="599" inputmode="text" autocomplete="off" @input="updateNumber(editDraft); findMarkers()"><div v-if="suggestions.length" class="marker-suggestions marker-edit-suggestions"><button v-for="marker in suggestions" :key="marker.id" type="button" @click="chooseMarker(marker)"><b>{{ marker.manufacturer_label }} · {{ marker.marker_type_label }}</b><span>{{ marker.symbol }} {{ marker.number }}</span></button></div></label>
              <label>Производитель<select v-model="editDraft.manufacturer" @change="updateManufacturer(editDraft)"><option value="" disabled>Выберите</option><option v-if="editDraft.manufacturer && !manufacturerOptions.some(option => option.value === editDraft.manufacturer)" :value="editDraft.manufacturer">Не указан</option><option v-for="manufacturer in manufacturerOptions" :key="manufacturer.value" :value="manufacturer.value">{{ manufacturer.label }}</option></select></label>
              <label>Тип<select v-model="editDraft.marker_type" @change="updateMarkerType(editDraft)"><option value="" disabled>Выберите</option><option v-for="markerType in markerTypeOptions" :key="markerType.value" :value="markerType.value">{{ markerType.label }}</option></select></label>
              <label class="marker-edit-usage">Расход<select v-model="editDraft.usage_level"><option value="">Не знаю</option><option value="little">Немного</option><option value="medium">Средне</option><option value="much">Много</option></select></label>
            </div>
            <p v-if="editError" class="form-error" role="alert">{{ editError }}</p>
            <div class="marker-edit-actions"><button v-if="editingIndex !== null" type="button" class="delete-marker-action" @click="requestDelete(editingIndex, true)">Удалить</button><button type="button" class="secondary" @click="editDraft = null">Отмена</button><button type="button" class="primary" @click="commitRowDraft">Готово</button></div>
          </section>
        </div>
        <div v-if="deleteConfirmIndex !== null" class="marker-edit-backdrop marker-delete-backdrop" @click.self="cancelDelete">
          <section class="marker-delete-modal" role="dialog" aria-modal="true" aria-labelledby="marker-delete-title">
            <h3 id="marker-delete-title">Удалить маркер {{ rows[deleteConfirmIndex]?.number || '' }}?</h3>
            <p>Он будет удалён из палитры после её сохранения.</p>
            <div class="marker-delete-actions"><button type="button" class="secondary" @click="cancelDelete">Оставить</button><button type="button" class="delete-marker-action" @click="confirmDelete">Удалить</button></div>
          </section>
        </div>
      </template>
    </div>
  </div>
</template>
