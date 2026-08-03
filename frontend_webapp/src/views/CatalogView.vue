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
    <p v-if="loading && !books.length" class="muted">Загружаем каталог…</p>
    <transition-group v-else-if="books.length" name="catalog" tag="div" class="catalog"><article v-for="book in books" :key="book.id" :class="['catalog-card', { 'is-owned': book.owned }]" @click="router.push(`/catalog/book/${book.id}`)"><div class="catalog-cover"><img v-if="book.cover" :src="book.cover" :alt="book.title"><div v-else class="cover-placeholder" aria-label="Обложка пока не добавлена">❀</div></div><div class="catalog-info"><h2>{{ book.title }}</h2><p>{{ book.author || 'Раскраска' }}</p><div class="catalog-details"><span>{{ formatCount(book.pages, 'page') }}</span><span v-if="book.owned">{{ book.completed }} готово</span></div><button :class="book.owned ? 'secondary collection-button' : 'primary'" :disabled="busy" @click.stop="book.owned ? removing = book : add(book)"><template v-if="book.owned"><span>В коллекции</span><small>Убрать</small></template><template v-else>Добавить в коллекцию</template></button></div></article></transition-group>
    <div v-else-if="!loading && !books.length" class="empty"><div>❀</div><h2>Ничего не нашли</h2><p>Попробуйте изменить запрос.</p></div>
    <transition name="modal"><div v-if="removing" class="modal-backdrop" @click.self="removing = null"><section class="confirm-card" role="dialog" aria-modal="true" aria-labelledby="remove-title"><div class="confirm-icon">!</div><h2 id="remove-title">Убрать из коллекции?</h2><p><b>{{ removing.title }}</b> исчезнет из трекера.</p><p v-if="removing.completed" class="warning">Будут удалены {{ formatCount(removing.completed, 'work') }} и записи о них в статистике. Это нельзя отменить.</p><div class="confirm-actions"><button class="secondary" :disabled="busy" @click="removing = null">Оставить</button><button class="danger" :disabled="busy" @click="remove">{{ busy ? 'Удаляем…' : 'Удалить' }}</button></div></section></div></transition>
  </section>
</template>