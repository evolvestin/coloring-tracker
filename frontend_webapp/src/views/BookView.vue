<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import ImageEditor from '../components/ImageEditor.vue'
import { formatCount } from '../pluralize'
import { useTrackerStore } from '../stores/tracker'

const route = useRoute(), router = useRouter(), trackerStore = useTrackerStore()
const data = ref(null), tab = ref('all'), workInput = ref(null), colorCodeInput = ref(null)
const activePage = ref(null), uploading = ref(''), viewer = ref(null), viewerScale = ref(1)
const editor = ref(null), uploadError = ref('')
const uploadVersions = new Map()
const reportVisibilityStatus = ref('')
let reportVisibilityStatusTimer
const pinch = { pointers: new Map(), distance: 0, scale: 1 }
const pages = computed(() => !data.value ? [] : data.value.pages.filter(page => tab.value === 'all' || (tab.value === 'done' ? page.completed : !page.completed)))

async function load() {
  data.value = await api(`/api/tracker/books/${route.params.id}/`)
  if (activePage.value) activePage.value = data.value.pages.find(page => page.id === activePage.value.id) || null
}
function openPage(page) {
  activePage.value = page
  clearTimeout(reportVisibilityStatusTimer)
  reportVisibilityStatus.value = ''
}
function chooseWork() { workInput.value?.click() }
function chooseColorCode() { colorCodeInput.value?.click() }
function openEditor(event, target) {
  const file = event.target.files[0]
  event.target.value = ''
  if (!file || !activePage.value) return
  uploadError.value = ''
  editor.value = { file, target, page: activePage.value }
}
async function saveEditedImage(blob) {
  if (!editor.value) return
  const { target, page } = editor.value
  const previewUrl = URL.createObjectURL(blob)
  const previousUrl = page[target]
  const uploadKey = `${page.id}:${target}`
  const version = (uploadVersions.get(uploadKey) || 0) + 1
  uploadVersions.set(uploadKey, version)
  const wasCompleted = page.completed
  page[target] = previewUrl
  if (target === 'photo' && !wasCompleted) {
    page.completed = true
    data.value.book.done += 1
    data.value.book.progress = Math.round(data.value.book.done * 100 / data.value.book.total)
  }
  editor.value = null
  try {
    const form = new FormData()
    form.append(target === 'photo' ? 'photo' : 'image', blob, target === 'photo' ? 'work.jpg' : 'color-code.jpg')
    const url = target === 'photo'
      ? `/api/tracker/books/${route.params.id}/pages/${page.id}/`
      : `/api/tracker/books/${route.params.id}/pages/${page.id}/color-code/`
    const result = await api(url, { method: 'POST', body: form })
    if (uploadVersions.get(uploadKey) === version) {
      page[target] = target === 'photo' ? result.photo : result.image
    }
    URL.revokeObjectURL(previewUrl)
    if (uploadVersions.get(uploadKey) === version) {
      void Promise.all([
        load(),
        trackerStore.loadCollection(true),
        trackerStore.loadReport('', true),
      ]).catch(() => {})
    }
  } catch (error) {
    if (uploadVersions.get(uploadKey) === version) {
      page[target] = previousUrl
      if (target === 'photo' && !wasCompleted) {
        page.completed = false
        data.value.book.done -= 1
        data.value.book.progress = Math.round(data.value.book.done * 100 / data.value.book.total)
      }
      uploadError.value = error.message
    }
    URL.revokeObjectURL(previewUrl)
  }
}
async function removeColorCode() {
  if (!activePage.value) return
  uploading.value = 'color-code'
  try {
    await api(`/api/tracker/books/${route.params.id}/pages/${activePage.value.id}/color-code/`, { method: 'DELETE' })
    await load()
  } finally { uploading.value = '' }
}
async function toggle(page) {
  uploading.value = 'completion'
  try {
    await api(`/api/tracker/books/${route.params.id}/pages/${page.id}/`, { method: page.completed ? 'DELETE' : 'POST', body: page.completed ? undefined : new FormData() })
    await Promise.all([
      load(),
      trackerStore.loadCollection(true),
      trackerStore.loadReport('', true),
    ])
  } finally { uploading.value = '' }
}
async function toggleHideInReport() {
  if (!activePage.value) return
  const newValue = !activePage.value.hide_in_report
  uploading.value = 'report-visibility'
  reportVisibilityStatus.value = ''
  try {
    const form = new FormData()
    form.append('hide_in_report', newValue)
    await api(`/api/tracker/books/${route.params.id}/pages/${activePage.value.id}/`, { method: 'POST', body: form })
    await Promise.all([
      load(),
      trackerStore.loadCollection(true),
      trackerStore.loadReport('', true),
    ])
    reportVisibilityStatus.value = newValue
      ? 'Сохранено — работа не будет отображаться в статистике.'
      : 'Сохранено — работа снова отображается в статистике.'
    clearTimeout(reportVisibilityStatusTimer)
    reportVisibilityStatusTimer = setTimeout(() => { reportVisibilityStatus.value = '' }, 3500)
  } finally {
    uploading.value = ''
  }
}
function openViewer(src, title) {
  viewer.value = { src, title }
  viewerScale.value = 1
  pinch.pointers.clear()
}
function closeViewer() {
  viewer.value = null
  pinch.pointers.clear()
}
function distance() {
  const [first, second] = [...pinch.pointers.values()]
  return Math.hypot(second.x - first.x, second.y - first.y)
}
function startPinch(event) {
  event.currentTarget.setPointerCapture(event.pointerId)
  pinch.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
  if (pinch.pointers.size === 2) {
    pinch.distance = distance()
    pinch.scale = viewerScale.value
  }
}
function movePinch(event) {
  if (!pinch.pointers.has(event.pointerId)) return
  pinch.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
  if (pinch.pointers.size === 2 && pinch.distance) {
    viewerScale.value = Math.min(4, Math.max(1, pinch.scale * distance() / pinch.distance))
  }
}
function endPinch(event) { pinch.pointers.delete(event.pointerId) }
function toggleZoom() { viewerScale.value = viewerScale.value === 1 ? 2 : 1 }
function imageFailed(event) { event.target.classList.add('is-broken') }
onBeforeUnmount(() => clearTimeout(reportVisibilityStatusTimer))
onMounted(load)
</script>

<template>
  <section v-if="data" class="page book-view">
    <header><button class="back" aria-label="Назад" @click="router.back()"><svg viewBox="0 0 24 24" fill="none"><path d="m14.5 5-7 7 7 7"/></svg></button><div><p class="eyebrow">МОЯ РАСКРАСКА</p><h1>{{ data.book.title }}</h1><p>{{ data.book.author }}</p></div></header>
    <div class="progress-card"><div class="progress-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M5 19.5V10m5 9.5V4m5 15.5v-7m5 7V7"/></svg></div><div><b>{{ data.book.done }} из {{ data.book.total }}</b><span>Осталось {{ formatCount(data.book.total - data.book.done, 'page') }}</span></div><div class="progress-line"><i :style="{ width: data.book.progress + '%' }"></i></div></div>
    <div class="tabs"><button :class="{ active: tab === 'all' }" @click="tab = 'all'">Все <small>{{ data.pages.length }}</small></button><button :class="{ active: tab === 'done' }" @click="tab = 'done'">Готово <small>{{ data.book.done }}</small></button><button :class="{ active: tab === 'left' }" @click="tab = 'left'">Осталось <small>{{ data.book.total - data.book.done }}</small></button></div>
    <input ref="workInput" hidden type="file" accept="image/*" @change="openEditor($event, 'photo')">
    <input ref="colorCodeInput" hidden type="file" accept="image/*" @change="openEditor($event, 'color_code')">
    <p v-if="uploadError" class="upload-error" role="alert">{{ uploadError }}</p>
    <transition-group name="pages" tag="div" class="page-grid"><article v-for="page in pages" :key="page.id" :class="['coloring-page', { done: page.completed, spread: page.spread_end }]" @click="openPage(page)"><img v-if="page.photo" :src="page.photo" :alt="'Работа ' + page.label" @error="imageFailed"><div v-else class="page-empty"><svg viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14"/></svg></div><span>{{ page.label }}<template v-if="page.title"> · {{ page.title }}</template></span><i v-if="page.color_code" class="color-code-mark" aria-label="Цветовой код загружен"><svg viewBox="0 0 24 24" fill="none"><path d="M12 3.8a8.2 8.2 0 1 0 0 16.4h1.2a1.8 1.8 0 0 0 0-3.6h-.6a1.8 1.8 0 0 1 0-3.6h1.2a8.2 8.2 0 0 0 0-16.4Z"/><circle cx="7.7" cy="10.2" r=".8" fill="currentColor"/><circle cx="11" cy="7.2" r=".8" fill="currentColor"/><circle cx="15.4" cy="8.7" r=".8" fill="currentColor"/></svg></i><button class="check" :aria-label="page.completed ? 'Удалить работу' : 'Отметить готовой'" @click.stop="toggle(page)"><svg v-if="page.completed" viewBox="0 0 24 24" fill="none"><path d="m5 12 4.2 4.2L19 6.5"/></svg><svg v-else viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="7"/></svg></button></article></transition-group>
    <transition name="modal"><div v-if="activePage" class="modal-backdrop" @click.self="activePage = null"><section class="page-modal" role="dialog" aria-modal="true" :aria-labelledby="`page-title-${activePage.id}`"><button class="modal-close" aria-label="Закрыть" @click="activePage = null">×</button><p class="eyebrow">СТРАНИЦА {{ activePage.label }}<template v-if="activePage.title"> · {{ activePage.title }}</template></p><h2 :id="`page-title-${activePage.id}`">{{ activePage.title || 'Работа и цветовой код' }}</h2><p class="modal-hint">Фото и цветовой код сохраняются отдельно от отметки о готовности.</p><div class="asset-card"><div><b>Фото работы</b><span>{{ activePage.photo ? 'Нажмите, чтобы открыть' : 'Пока нет фото' }}</span></div><button v-if="activePage.photo" class="asset-preview" aria-label="Открыть фото работы" @click="openViewer(activePage.photo, 'Фото работы')"><img :src="activePage.photo" alt="Фото работы"></button><button class="secondary" :disabled="uploading !== ''" @click="chooseWork">{{ activePage.photo ? 'Заменить' : 'Загрузить фото' }}</button></div><div class="asset-card color-code-card"><div><b>Цветовой код</b><span>{{ activePage.color_code ? 'Нажмите, чтобы открыть' : 'Пока не добавлен' }}</span></div><button v-if="activePage.color_code" class="asset-preview" aria-label="Открыть цветовой код" @click="openViewer(activePage.color_code, 'Цветовой код')"><img :src="activePage.color_code" alt="Цветовой код"></button><div class="asset-actions"><button class="secondary" :disabled="uploading !== ''" @click="chooseColorCode">{{ activePage.color_code ? 'Заменить' : 'Загрузить код' }}</button><button v-if="activePage.color_code" class="text-danger" :disabled="uploading !== ''" @click="removeColorCode">Удалить</button></div></div><button class="hide-in-report-option" :class="{ active: activePage.hide_in_report, saving: uploading === 'report-visibility' }" type="button" role="switch" :aria-checked="activePage.hide_in_report" :disabled="uploading !== ''" @click="toggleHideInReport"><span class="report-toggle" aria-hidden="true"><i></i></span><span class="report-option-copy"><b>Не отображать в статистике</b><small>{{ uploading === 'report-visibility' ? 'Сохраняем изменение…' : activePage.hide_in_report ? 'Работа скрыта из статистики' : 'Работа учитывается в статистике' }}</small></span><span class="report-option-state" aria-hidden="true">{{ uploading === 'report-visibility' ? '…' : activePage.hide_in_report ? '✓' : '' }}</span></button><div class="report-visibility-slot"><p class="report-visibility-status" :class="{ visible: reportVisibilityStatus }" :role="reportVisibilityStatus ? 'status' : undefined"><span>✓</span>{{ reportVisibilityStatus }}</p></div><button class="completion-button" :disabled="uploading !== ''" @click="toggle(activePage)">{{ activePage.completed ? 'Снять отметку о готовности' : 'Отметить готовой' }}</button></section></div></transition>
    <ImageEditor v-if="editor" :file="editor.file" :title="editor.target === 'photo' ? 'Фото работы' : 'Цветовой код'" @cancel="editor = null" @save="saveEditedImage">
    </ImageEditor>
    <transition name="modal"><div v-if="viewer" class="image-viewer-backdrop" @click.self="closeViewer"><section class="image-viewer" role="dialog" aria-modal="true" :aria-label="viewer.title"><button class="modal-close" aria-label="Закрыть просмотр" @click="closeViewer">×</button><p>{{ viewer.title }}</p><small>Разведите два пальца для увеличения · двойное нажатие меняет масштаб</small><div class="image-viewer-stage"><img :src="viewer.src" :alt="viewer.title" :style="{ transform: `scale(${viewerScale})` }" @dblclick="toggleZoom" @pointerdown="startPinch" @pointermove="movePinch" @pointerup="endPinch" @pointercancel="endPinch"></div></section></div></transition>
  </section>
  <section v-else class="page muted">Загружаем раскраску…</section>
</template>
