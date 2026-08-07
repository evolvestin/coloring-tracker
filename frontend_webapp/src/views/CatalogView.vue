<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTrackerStore } from '../stores/tracker'
import { api } from '../api'
import { formatCount } from '../pluralize'

const router = useRouter(), route = useRoute()
const store = useTrackerStore()

const busy = ref(false)
const query = ref(route.query.q || '')
const removing = ref(null)
const suggestionOpen = ref(false), suggestionBusy = ref(false)
const suggestionTitle = ref(''), suggestionSource = ref(''), suggestionError = ref(''), suggestionSent = ref(false)

const books = computed(() => store.catalogBooks)
const loading = computed(() => store.catalogLoading && !store.catalogLoaded)

async function load() {
  const params = new URLSearchParams()
  if (query.value.trim()) params.set('q', query.value.trim())
  router.replace({ query: Object.fromEntries(params) })
  await store.loadCatalog(query.value, true)
}

async function add(book) {
  if (book.owned || busy.value) return
  busy.value = true
  try {
    await api('/api/tracker/books/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ book_id: book.id }) })
    await Promise.all([
      store.loadCatalog(query.value, true),
      store.loadCollection(true),
      store.loadReport('', true),
    ])
  } finally { busy.value = false }
}

async function remove() {
  if (!removing.value || busy.value) return
  busy.value = true
  try {
    await api(`/api/tracker/catalog/${removing.value.id}/collection/`, { method: 'DELETE' })
    removing.value = null
    await Promise.all([
      store.loadCatalog(query.value, true),
      store.loadCollection(true),
      store.loadReport('', true),
    ])
  } finally { busy.value = false }
}

async function submitSuggestion() {
  if (!suggestionTitle.value.trim() || suggestionBusy.value) return
  suggestionBusy.value = true
  suggestionError.value = ''
  try {
    await api('/api/tracker/suggestions/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: suggestionTitle.value, source_text: suggestionSource.value }),
    })
    suggestionSent.value = true
    suggestionTitle.value = ''
    suggestionSource.value = ''
  } catch (error) {
    suggestionError.value = error.message
  } finally { suggestionBusy.value = false }
}

function closeSuggestion() {
  if (suggestionBusy.value) return
  suggestionOpen.value = false
  suggestionSent.value = false
  suggestionError.value = ''
}

onMounted(() => {
  if (query.value) {
    load()
  } else {
    store.loadCatalog()
  }
})
</script>

<template>
  <section class="page catalog-page">
    <header><button class="back" aria-label="Назад" @click="router.push('/')"><svg viewBox="0 0 24 24" fill="none"><path d="m14.5 5-7 7 7 7"/></svg></button><div><p class="eyebrow">КАТАЛОГ</p><h1>Выберите раскраску</h1></div></header>
    <form class="search" @submit.prevent="load"><input v-model="query" placeholder="Название, автор или издатель"><button aria-label="Найти"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="11" cy="11" r="5.5"/><path d="m16 16 4 4"/></svg></button></form>
    <p class="catalog-hint">Нажмите на раскраску, чтобы посмотреть, что внутри, или добавьте её в свою коллекцию.</p>
    <button class="suggestion-open" type="button" @click="suggestionOpen = true">＋ Предложить раскраску</button>
    <p v-if="loading && !books.length" class="muted">Загружаем каталог…</p>
    <transition-group v-else-if="books.length" name="catalog" tag="div" class="catalog"><article v-for="book in books" :key="book.id" :class="['catalog-card', { 'is-owned': book.owned }]" @click="router.push(`/catalog/book/${book.id}`)"><div class="catalog-cover"><img v-if="book.cover" :src="book.cover" :alt="book.title"><div v-else class="cover-placeholder" aria-label="Обложка пока не добавлена">❀</div></div><div class="catalog-info"><h2>{{ book.title }}</h2><p>{{ book.author || 'Раскраска' }}</p><div class="catalog-details"><span>{{ formatCount(book.pages, 'page') }}<template v-if="book.spreads"> ({{ formatCount(book.spreads, 'spread') }})</template></span><span v-if="book.owned">{{ book.completed }} готово</span></div><button :class="book.owned ? 'secondary collection-button' : 'primary'" :disabled="busy" @click.stop="book.owned ? removing = book : add(book)"><template v-if="book.owned"><span>В коллекции</span><small>Убрать</small></template><template v-else>Добавить в коллекцию</template></button></div></article></transition-group>
    <div v-else-if="!loading && !books.length" class="empty"><div>❀</div><h2>Ничего не нашли</h2><p>Попробуйте изменить запрос.</p></div>
    <transition name="modal"><div v-if="removing" class="modal-backdrop" @click.self="removing = null"><section class="confirm-card" role="dialog" aria-modal="true" aria-labelledby="remove-title"><div class="confirm-icon">!</div><h2 id="remove-title">Убрать из коллекции?</h2><p><b>{{ removing.title }}</b> исчезнет из трекера.</p><p v-if="removing.completed" class="warning">Будут удалены {{ formatCount(removing.completed, 'work') }} и записи о них в статистике. Это нельзя отменить.</p><div class="confirm-actions"><button class="secondary" :disabled="busy" @click="removing = null">Оставить</button><button class="danger" :disabled="busy" @click="remove">{{ busy ? 'Удаляем…' : 'Удалить' }}</button></div></section></div></transition>
    <transition name="modal"><div v-if="suggestionOpen" class="modal-backdrop" @click.self="closeSuggestion"><section class="suggestion-modal" role="dialog" aria-modal="true" aria-labelledby="suggestion-title"><button class="modal-close" aria-label="Закрыть" @click="closeSuggestion">×</button><template v-if="suggestionSent"><div class="suggestion-success">✓</div><h2 id="suggestion-title">Спасибо за идею!</h2><p>Предложение записано. Мы проверим его и добавим раскраску, если найдём подходящий скан.</p><button class="primary suggestion-submit" @click="closeSuggestion">Вернуться в каталог</button></template><template v-else><p class="eyebrow">НОВАЯ ИДЕЯ</p><h2 id="suggestion-title">Предложить раскраску</h2><p class="suggestion-instruction">Напишите название как можно точнее — так мы быстрее найдём нужную раскраску. Если знаете, где лежит скан или его превью, оставьте ссылку или любой поясняющий текст ниже.</p><form @submit.prevent="submitSuggestion"><label>Название раскраски<input v-model="suggestionTitle" maxlength="500" required placeholder="Например, Secret Garden by Johanna Basford"></label><label>Где искать скан <span class="optional">необязательно</span><textarea v-model="suggestionSource" rows="4" placeholder="Ссылка, название сайта или любой комментарий"></textarea></label><p v-if="suggestionError" class="suggestion-error" role="alert">{{ suggestionError }}</p><button class="primary suggestion-submit" :disabled="suggestionBusy || !suggestionTitle.trim()">{{ suggestionBusy ? 'Отправляем…' : 'Отправить предложение' }}</button></form><p class="suggestion-note">Новое предложение можно отправлять раз в 30 секунд.</p></template></section></div></transition>
  </section>
</template>
