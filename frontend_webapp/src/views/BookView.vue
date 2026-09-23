<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import ImageEditor from '../components/ImageEditor.vue'
import PersonalPagesEditor from '../components/PersonalPagesEditor.vue'
import RandomizerCard from '../components/RandomizerCard.vue'
import { FLOWER_ICONS } from '../constants'
import { formatCount } from '../pluralize'
import { useTrackerStore } from '../stores/tracker'

const route = useRoute(), router = useRouter(), trackerStore = useTrackerStore()
const data = ref(null), tab = ref('all'), workInput = ref(null), colorCodeInput = ref(null), coverInput = ref(null)
const activePage = ref(null), uploading = ref(''), viewer = ref(null), viewerScale = ref(1)
const editor = ref(null), uploadError = ref('')
const editingExisting = ref(false)
const personalDialog = ref(null), personalError = ref(''), personalBusy = ref(false)
const personalTitle = ref(''), personalEmoji = ref(''), personalPages = ref([])
const personalEmojis = FLOWER_ICONS
const uploadVersions = new Map()
const reportVisibilityStatus = ref('')
let reportVisibilityStatusTimer
const pinch = { pointers: new Map(), distance: 0, scale: 1 }
const pages = computed(() => !data.value ? [] : data.value.pages.filter(page => tab.value === 'all' || (tab.value === 'done' ? page.completed : !page.completed)))
const isPersonal = computed(() => !!data.value?.book?.is_personal)

async function load() {
  data.value = await api(`/api/tracker/books/${route.params.id}/`)
  if (activePage.value) activePage.value = data.value.pages.find(page => page.id === activePage.value.id) || null
  const requestedPageId = Number(route.query.page)
  if (requestedPageId && !activePage.value) activePage.value = data.value.pages.find(page => page.id === requestedPageId) || null
}
function openPage(page) {
  activePage.value = page
  clearTimeout(reportVisibilityStatusTimer)
  reportVisibilityStatus.value = ''
}
function openRandomResult(randomResult) {
  const page = data.value?.pages.find(item => item.id === randomResult?.page_id)
  if (page) openPage(page)
}
function chooseWork() { workInput.value?.click() }
function chooseColorCode() { colorCodeInput.value?.click() }
function chooseCover() {
  const input = coverInput.value
  if (!input) return
  input.value = ''
  if (typeof input.showPicker === 'function') {
    try {
      input.showPicker()
      return
    } catch {
      // Some Telegram WebView versions reject showPicker; use the compatible fallback.
    }
  }
  input.click()
}
async function editExisting(target) {
  const item = target === 'cover' ? data.value?.book : activePage.value
  const sourceKey = target === 'cover' ? 'cover_source' : `${target}_source`
  const sourceUrl = item?.[target] || item?.[sourceKey]
  if (!sourceUrl || editingExisting.value) return
  editingExisting.value = true
  uploadError.value = ''
  try {
    const response = await fetch(sourceUrl)
    if (!response.ok) throw new Error('Не удалось открыть сохранённое изображение.')
    const blob = await response.blob()
    editor.value = {
      file: new File([blob], target === 'cover' ? 'cover.jpg' : target === 'photo' ? 'work.jpg' : 'color-code.jpg', { type: blob.type || 'image/jpeg' }),
      target,
      page: target === 'cover' ? null : activePage.value,
    }
  } catch (error) {
    uploadError.value = error.message
  } finally {
    editingExisting.value = false
  }
}
function openEditor(event, target) {
  const file = event.target.files[0]
  event.target.value = ''
  if (!file || (target !== 'cover' && !activePage.value)) return
  uploadError.value = ''
  editor.value = { file, target, page: target === 'cover' ? null : activePage.value }
}
async function saveEditedImage({ blob, sourceFile }) {
  if (!editor.value) return
  const { target, page } = editor.value
  const item = target === 'cover' ? data.value.book : page
  const previewUrl = URL.createObjectURL(blob)
  const previousUrl = item[target]
  const uploadKey = target === 'cover' ? `book:${route.params.id}:cover` : `${page.id}:${target}`
  const version = (uploadVersions.get(uploadKey) || 0) + 1
  uploadVersions.set(uploadKey, version)
  const wasCompleted = page?.completed
  item[target] = previewUrl
  if (target === 'photo' && !wasCompleted) {
    page.completed = true
    data.value.book.done += 1
    data.value.book.progress = Math.round(data.value.book.done * 100 / data.value.book.total)
  }
  editor.value = null
  try {
    const form = new FormData()
    form.append(target === 'photo' ? 'photo' : 'image', blob, target === 'photo' ? 'work.jpg' : 'color-code.jpg')
    if (target === 'cover') {
      form.append('cover', blob, 'cover.jpg')
      form.delete('image')
      if (sourceFile) form.append('cover_original', sourceFile, sourceFile.name || 'cover-original.jpg')
    }
    if (target !== 'cover' && sourceFile) {
      form.append(target === 'photo' ? 'source_photo' : 'source_image', sourceFile, sourceFile.name || 'original.jpg')
    }
    const url = target === 'cover'
      ? `/api/tracker/personal-books/${route.params.id}/`
      : target === 'photo'
      ? `/api/tracker/books/${route.params.id}/pages/${page.id}/`
      : `/api/tracker/books/${route.params.id}/pages/${page.id}/color-code/`
    const result = await api(url, { method: target === 'cover' ? 'PATCH' : 'POST', body: form })
    if (uploadVersions.get(uploadKey) === version) {
      if (target === 'cover') {
        data.value.book.cover = result.book.cover
        data.value.book.cover_source = result.book.cover_source
      } else {
        page[target] = target === 'photo' ? result.photo : result.image
        page[`${target}_source`] = target === 'photo' ? result.photo_source : result.image_source
      }
    }
    URL.revokeObjectURL(previewUrl)
    if (uploadVersions.get(uploadKey) === version) {
      void Promise.all([
        load(),
        trackerStore.loadCollection(true),
        ...(target === 'cover' ? [] : [trackerStore.loadReport('', true)]),
      ]).catch(() => {})
    }
  } catch (error) {
    if (uploadVersions.get(uploadKey) === version) {
      item[target] = previousUrl
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
function openPersonalSettings() {
  personalTitle.value = data.value.book.title
  personalEmoji.value = data.value.book.emoji || personalEmojis[0]
  personalPages.value = data.value.pages.map(page => ({
    id: page.id,
    number: page.number,
    spread_end: page.spread_end,
    title: page.title,
  }))
  personalError.value = ''
  personalDialog.value = 'settings'
}
// Page removal is handled by the complete list editor. Keep old deep links
// harmless while older cached templates are still open in a WebApp tab.
function askDeletePage() { openPersonalSettings() }
async function savePersonalSettings() {
  if (personalBusy.value) return
  personalBusy.value = true
  personalError.value = ''
  try {
    await api(`/api/tracker/personal-books/${route.params.id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: personalTitle.value,
        emoji: personalEmoji.value,
        pages: personalPages.value.map(page => ({
          id: page.id,
          number: Number(page.number),
          spread_end: page.spread_end === null || page.spread_end === '' ? null : Number(page.spread_end),
          title: page.title.trim(),
        })),
      }),
    })
    personalDialog.value = null
    await Promise.all([load(), trackerStore.loadCollection(true)])
  } catch (error) {
    personalError.value = error.message
  } finally { personalBusy.value = false }
}
function askDeleteBook() {
  personalError.value = ''
  personalDialog.value = 'delete-book'
}
async function deletePersonalBook() {
  if (personalBusy.value) return
  personalBusy.value = true
  personalError.value = ''
  try {
    await api(`/api/tracker/personal-books/${route.params.id}/`, { method: 'DELETE' })
    await trackerStore.loadCollection(true)
    router.replace('/')
  } catch (error) {
    personalError.value = error.message
  } finally { personalBusy.value = false }
}
onBeforeUnmount(() => clearTimeout(reportVisibilityStatusTimer))
onMounted(load)
</script>

<template>
  <section v-if="data" class="page book-view">
    <header><button class="back" aria-label="Назад" @click="router.back()"><svg viewBox="0 0 24 24" fill="none"><path d="m14.5 5-7 7 7 7"/></svg></button><div><p class="eyebrow">МОЯ РАСКРАСКА</p><h1>{{ data.book.title }}</h1><p><template v-if="isPersonal"><span class="personal-heading-flag">{{ data.book.emoji }}</span> Личная</template><template v-else>{{ data.book.author }}</template></p></div></header>
    <div class="progress-card"><div class="progress-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M5 19.5V10m5 9.5V4m5 15.5v-7m5 7V7"/></svg></div><div><b>{{ data.book.done }} из {{ data.book.total }} работ</b><span>Осталось {{ formatCount(data.book.total - data.book.done, 'work') }}</span></div><div class="progress-line"><i :style="{ width: data.book.progress + '%' }"></i></div></div>
    <RandomizerCard :user-book-id="route.params.id" compact @open-result="openRandomResult" />
    <div v-if="isPersonal" class="personal-cover-panel"><div v-if="data.book.cover" class="personal-cover personal-cover-large has-image"><img :src="data.book.cover" :alt="data.book.title"><small>Личная обложка</small></div><div v-else class="personal-cover personal-cover-large"><i class="cover-spark spark-one">✦</i><i class="cover-spark spark-two">✿</i><i class="cover-spark spark-three">·</i><span>{{ data.book.emoji || '❀' }}</span><small>Личная обложка</small></div><div class="personal-cover-actions"><b>Обложка раскраски</b><span>{{ data.book.cover ? 'Её можно изменить в редакторе.' : 'Добавьте изображение или оставьте эмодзи.' }}</span><input ref="coverInput" hidden type="file" accept="image/jpeg,image/png,image/webp" @change="openEditor($event, 'cover')"><div><button class="secondary" type="button" @click="chooseCover">{{ data.book.cover ? 'Заменить' : 'Добавить изображение' }}</button><button v-if="data.book.cover" class="text-action" type="button" :disabled="editingExisting" @click="editExisting('cover')">{{ editingExisting ? 'Открываем…' : 'Изменить' }}</button></div></div></div>
    <div v-if="isPersonal" class="personal-tools"><button class="secondary" type="button" @click="openPersonalSettings">Редактировать книгу и страницы</button></div>
    <div class="tabs"><button :class="{ active: tab === 'all' }" @click="tab = 'all'">Все работы <small>{{ data.pages.length }}</small></button><button :class="{ active: tab === 'done' }" @click="tab = 'done'">Готово <small>{{ data.book.done }}</small></button><button :class="{ active: tab === 'left' }" @click="tab = 'left'">Осталось работ <small>{{ data.book.total - data.book.done }}</small></button></div>
    <input ref="workInput" hidden type="file" accept="image/*" @change="openEditor($event, 'photo')">
    <input ref="colorCodeInput" hidden type="file" accept="image/*" @change="openEditor($event, 'color_code')">
    <p v-if="uploadError" class="upload-error" role="alert">{{ uploadError }}</p>
    <transition-group name="pages" tag="div" class="page-grid"><article v-for="page in pages" :key="page.id" :class="['coloring-page', { done: page.completed, spread: page.spread_end }]" @click="openPage(page)"><img v-if="page.photo" :src="page.photo" :alt="'Работа ' + page.label" @error="imageFailed"><div v-else class="page-empty"><svg viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14"/></svg></div><span>{{ page.label }}<template v-if="page.title"> · {{ page.title }}</template></span><i v-if="page.color_code" class="color-code-mark" aria-label="Цветовой код загружен"><svg viewBox="0 0 24 24" fill="none"><path d="M12 3.8a8.2 8.2 0 1 0 0 16.4h1.2a1.8 1.8 0 0 0 0-3.6h-.6a1.8 1.8 0 0 1 0-3.6h1.2a8.2 8.2 0 0 0 0-16.4Z"/><circle cx="7.7" cy="10.2" r=".8" fill="currentColor"/><circle cx="11" cy="7.2" r=".8" fill="currentColor"/><circle cx="15.4" cy="8.7" r=".8" fill="currentColor"/></svg></i><button class="check" :aria-label="page.completed ? 'Удалить работу' : 'Отметить готовой'" @click.stop="toggle(page)"><svg v-if="page.completed" viewBox="0 0 24 24" fill="none"><path d="m5 12 4.2 4.2L19 6.5"/></svg><svg v-else viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="7"/></svg></button></article></transition-group>
    <transition name="modal"><div v-if="activePage" class="modal-backdrop" @click.self="activePage = null"><section class="page-modal" role="dialog" aria-modal="true" :aria-labelledby="`page-title-${activePage.id}`"><button class="modal-close" aria-label="Закрыть" @click="activePage = null">×</button><p class="eyebrow">СТРАНИЦА {{ activePage.label }}<template v-if="activePage.title"> · {{ activePage.title }}</template></p><h2 :id="`page-title-${activePage.id}`">{{ activePage.title || 'Работа и цветовой код' }}</h2><p class="modal-hint">Фото и цветовой код сохраняются отдельно от отметки о готовности.</p><div class="asset-card"><div><b>Фото работы</b><span>{{ activePage.photo ? 'Нажмите, чтобы открыть' : 'Пока нет фото' }}</span></div><button v-if="activePage.photo" class="asset-preview" aria-label="Открыть фото работы" @click="openViewer(activePage.photo, 'Фото работы')"><img :src="activePage.photo" alt="Фото работы"></button><div class="asset-actions"><button class="secondary" :disabled="uploading !== '' || editingExisting" @click="chooseWork">{{ activePage.photo ? 'Заменить' : 'Загрузить фото' }}</button><button v-if="activePage.photo" class="text-action" :disabled="uploading !== '' || editingExisting" @click="editExisting('photo')">{{ editingExisting ? 'Открываем…' : 'Изменить' }}</button></div></div><div class="asset-card color-code-card"><div><b>Цветовой код</b><span>{{ activePage.color_code ? 'Нажмите, чтобы открыть' : 'Пока не добавлен' }}</span></div><button v-if="activePage.color_code" class="asset-preview" aria-label="Открыть цветовой код" @click="openViewer(activePage.color_code, 'Цветовой код')"><img :src="activePage.color_code" alt="Цветовой код"></button><div class="asset-actions"><button class="secondary" :disabled="uploading !== '' || editingExisting" @click="chooseColorCode">{{ activePage.color_code ? 'Заменить' : 'Загрузить код' }}</button><button v-if="activePage.color_code" class="text-action" :disabled="uploading !== '' || editingExisting" @click="editExisting('color_code')">{{ editingExisting ? 'Открываем…' : 'Изменить' }}</button><button v-if="activePage.color_code" class="text-danger" :disabled="uploading !== ''" @click="removeColorCode">Удалить</button></div></div><button class="hide-in-report-option" :class="{ active: activePage.hide_in_report, saving: uploading === 'report-visibility' }" type="button" role="switch" :aria-checked="activePage.hide_in_report" :disabled="uploading !== ''" @click="toggleHideInReport"><span class="report-toggle" aria-hidden="true"><i></i></span><span class="report-option-copy"><b>Не отображать в статистике</b><small>{{ uploading === 'report-visibility' ? 'Сохраняем изменение…' : activePage.hide_in_report ? 'Работа скрыта из статистики' : 'Работа учитывается в статистике' }}</small></span><span class="report-option-state" aria-hidden="true">{{ uploading === 'report-visibility' ? '…' : activePage.hide_in_report ? '✓' : '' }}</span></button><div class="report-visibility-slot"><p class="report-visibility-status" :class="{ visible: reportVisibilityStatus }" :role="reportVisibilityStatus ? 'status' : undefined"><span>✓</span>{{ reportVisibilityStatus }}</p></div><button class="completion-button" :disabled="uploading !== ''" @click="toggle(activePage)">{{ activePage.completed ? 'Снять отметку о готовности' : 'Отметить готовой' }}</button><button v-if="isPersonal" class="delete-page-link" type="button" @click="askDeletePage(activePage)">Удалить эту страницу</button></section></div></transition>
    <transition name="modal"><div v-if="personalDialog === 'settings'" class="modal-backdrop" @click.self="personalDialog = null"><section class="personal-modal personal-pages-modal" role="dialog" aria-modal="true" aria-labelledby="personal-settings-title"><button class="modal-close" aria-label="Закрыть" @click="personalDialog = null">×</button><p class="eyebrow">ЛИЧНАЯ РАСКРАСКА</p><h2 id="personal-settings-title">Настроить раскраску</h2><label>Название<input v-model="personalTitle" maxlength="255"></label><fieldset class="emoji-field"><legend>Значок</legend><div class="emoji-picker"><button v-for="item in personalEmojis" :key="item" type="button" :class="{ selected: personalEmoji === item }" :aria-label="`Выбрать ${item}`" :aria-pressed="personalEmoji === item" @click="personalEmoji = item">{{ item }}</button></div></fieldset><PersonalPagesEditor :pages="personalPages" @update:pages="personalPages = $event" /><p class="personal-pages-warning">Если уменьшить количество строк, удалённые страницы вместе с работами и фотографиями будут удалены.</p><p v-if="personalError" class="form-error" role="alert">{{ personalError }}</p><div class="confirm-actions"><button class="secondary" type="button" @click="personalDialog = null">Отмена</button><button class="primary" type="button" :disabled="personalBusy" @click="savePersonalSettings">{{ personalBusy ? 'Сохраняем…' : 'Сохранить всё' }}</button></div><button class="delete-book-link" type="button" @click="askDeleteBook">Удалить личную раскраску</button></section></div></transition>
    <transition name="modal"><div v-if="personalDialog === 'delete-book'" class="modal-backdrop" @click.self="personalDialog = null"><section class="confirm-card personal-confirm" role="dialog" aria-modal="true" aria-labelledby="delete-book-title"><div class="confirm-icon">!</div><h2 id="delete-book-title">Удалить личную раскраску?</h2><p><b>{{ data.book.title }}</b> и все её страницы, работы и фотографии исчезнут без возможности восстановления.</p><p v-if="personalError" class="form-error" role="alert">{{ personalError }}</p><div class="confirm-actions"><button class="secondary" :disabled="personalBusy" @click="personalDialog = 'settings'">Назад</button><button class="danger" :disabled="personalBusy" @click="deletePersonalBook">{{ personalBusy ? 'Удаляем…' : 'Удалить всё' }}</button></div></section></div></transition>
    <ImageEditor v-if="editor" :file="editor.file" :title="editor.target === 'cover' ? 'Обложка раскраски' : editor.target === 'photo' ? 'Фото работы' : 'Цветовой код'" :aspect-ratio="editor.target === 'cover' ? 3 / 4 : 0" @cancel="editor = null" @save="saveEditedImage">
    </ImageEditor>
    <transition name="modal"><div v-if="viewer" class="image-viewer-backdrop" @click.self="closeViewer"><section class="image-viewer" role="dialog" aria-modal="true" :aria-label="viewer.title"><button class="modal-close" aria-label="Закрыть просмотр" @click="closeViewer">×</button><p>{{ viewer.title }}</p><small>Разведите два пальца для увеличения · двойное нажатие меняет масштаб</small><div class="image-viewer-stage"><img :src="viewer.src" :alt="viewer.title" :style="{ transform: `scale(${viewerScale})` }" @dblclick="toggleZoom" @pointerdown="startPinch" @pointermove="movePinch" @pointerup="endPinch" @pointercancel="endPinch"></div></section></div></transition>
  </section>
  <section v-else class="page muted">Загружаем раскраску…</section>
</template>
