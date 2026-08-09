<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import ImageEditor from '../components/ImageEditor.vue'
import PersonalPagesEditor from '../components/PersonalPagesEditor.vue'
import { useTrackerStore } from '../stores/tracker'
import { FLOWER_ICONS } from '../constants'

const router = useRouter()
const store = useTrackerStore()
const emojis = FLOWER_ICONS
const title = ref('')
const emoji = ref(emojis[0])
const cover = ref(null)
const coverSource = ref(null)
const coverPreview = ref('')
const coverInput = ref(null)
const editor = ref(null)
const pages = ref(Array.from({ length: 50 }, (_, index) => ({ id: null, _key: `new-${index + 1}`, number: String(index + 1), spread_end: null, title: '' })))
const error = ref('')
const saving = ref(false)

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

function editCover() {
  if (cover.value) editor.value = { file: coverSource.value || cover.value }
}

function selectCover(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  const hasImageType = (file.type || '').startsWith('image/')
  const hasImageExtension = /\.(jpe?g|png|webp)$/i.test(file.name || '')
  if (!hasImageType && !hasImageExtension) {
    error.value = 'Выберите изображение для обложки.'
    return
  }
  editor.value = { file }
  error.value = ''
}

function saveCover({ blob, sourceFile }) {
  if (coverPreview.value) URL.revokeObjectURL(coverPreview.value)
  const extension = blob.type === 'image/png' ? 'png' : 'jpg'
  cover.value = new File([blob], `cover.${extension}`, { type: blob.type || 'image/jpeg' })
  coverSource.value = sourceFile
  coverPreview.value = URL.createObjectURL(cover.value)
  editor.value = null
}

function removeCover() {
  if (coverPreview.value) URL.revokeObjectURL(coverPreview.value)
  cover.value = null
  coverSource.value = null
  coverPreview.value = ''
}

function interval(page) {
  const number = Number(page.number)
  const end = page.spread_end === null || page.spread_end === '' ? number : Number(page.spread_end)
  return [number, end]
}

function validate() {
  const rows = pages.value.map(interval)
  if (!title.value.trim()) return 'Введите название раскраски.'
  if (!rows.length) return ''
  if (rows.some(([number, end]) => !Number.isInteger(number) || number < 1 || !Number.isInteger(end) || end < number)) {
    return 'Проверьте номера страниц и разворотов.'
  }
  const sorted = rows.slice().sort((a, b) => a[0] - b[0])
  for (let index = 1; index < sorted.length; index += 1) {
    if (sorted[index][0] <= sorted[index - 1][1]) return 'Страницы и развороты не должны пересекаться.'
  }
  return ''
}

async function submit() {
  error.value = validate()
  if (error.value || saving.value) return
  saving.value = true
  try {
    const form = new FormData()
    form.append('title', title.value.trim())
    form.append('emoji', emoji.value)
    form.append('pages', JSON.stringify(pages.value.map(page => ({
      number: Number(page.number),
      spread_end: page.spread_end === null || page.spread_end === '' ? null : Number(page.spread_end),
      title: page.title.trim(),
    }))))
    if (cover.value) form.append('cover', cover.value, cover.value.name)
    if (coverSource.value) form.append('cover_original', coverSource.value, coverSource.value.name)
    const result = await api('/api/tracker/personal-books/', { method: 'POST', body: form })
    await store.loadCollection(true)
    router.replace(`/book/${result.book.id}`)
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    saving.value = false
  }
}

onBeforeUnmount(() => {
  if (coverPreview.value) URL.revokeObjectURL(coverPreview.value)
})
</script>

<template>
  <section class="page personal-create-page">
    <header>
      <button class="back" aria-label="Назад" @click="router.back()"><svg viewBox="0 0 24 24" fill="none"><path d="m14.5 5-7 7 7 7" /></svg></button>
      <div><p class="eyebrow">ЛИЧНАЯ РАСКРАСКА</p><h1>Добавить свою</h1></div>
    </header>

    <div class="personal-create-intro">
      <div class="personal-create-icon"><img v-if="coverPreview" :src="coverPreview" alt="Предпросмотр обложки"><template v-else><i class="cover-spark spark-one">✦</i><i class="cover-spark spark-two">✿</i><span>{{ emoji }}</span></template><button v-if="coverPreview" type="button" class="cover-remove" aria-label="Убрать обложку" @click="removeCover">×</button></div>
      <div><h2>Ваша маленькая коллекция</h2><p>Добавьте обложку и сразу подготовьте весь список страниц.</p></div>
    </div>

    <form class="personal-form" @submit.prevent="submit">
      <label>Название раскраски<input v-model="title" maxlength="255" required placeholder="Например, Мой артбук" /></label>

      <fieldset class="cover-field">
        <legend>Обложка <span>необязательно</span></legend>
        <input ref="coverInput" hidden type="file" accept="image/jpeg,image/png,image/webp" @change="selectCover">
        <div v-if="coverPreview" class="cover-upload-preview"><img :src="coverPreview" alt="Предпросмотр обложки"><div><b>Обложка готова</b><small>{{ cover.name }}</small><div class="cover-upload-actions"><button type="button" class="text-action" @click="editCover">Изменить</button><button type="button" class="text-action" @click="chooseCover">Заменить</button></div></div></div>
        <button v-else type="button" class="cover-upload" @click="chooseCover"><span>▧</span><div><b>Добавить обложку</b><small>JPG, PNG или WebP · до 12 МБ</small></div><i>＋</i></button>
      </fieldset>

      <fieldset class="emoji-field"><legend>Фоновый значок</legend><p>Он будет виден, если обложка не добавлена.</p><div class="emoji-picker"><button v-for="item in emojis" :key="item" type="button" :class="{ selected: emoji === item }" :aria-label="`Выбрать ${item}`" :aria-pressed="emoji === item" @click="emoji = item">{{ item }}</button></div></fieldset>

      <PersonalPagesEditor :pages="pages" @update:pages="pages = $event" />

      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <div class="personal-form-actions"><button class="secondary" type="button" @click="router.back()">Отмена</button><button class="primary" type="submit" :disabled="saving">{{ saving ? 'Создаём…' : 'Добавить раскраску' }}</button></div>
    </form>
    <ImageEditor v-if="editor" :file="editor.file" title="Обложка раскраски" :aspect-ratio="3 / 4" @cancel="editor = null" @save="saveCover" />
  </section>
</template>
