<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { formatCount } from '../pluralize'

const route = useRoute(), router = useRouter(), data = ref(null), adding = ref(false)
async function load() { data.value = await api(`/api/tracker/catalog/${route.params.id}/`) }
async function add() {
  if (adding.value) return
  adding.value = true
  try {
    await api('/api/tracker/books/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ book_id: route.params.id }) })
    await Promise.all([
      useTrackerStore().loadCatalog('', true),
      useTrackerStore().loadCollection(true),
    ])
    router.push('/')
  } finally { adding.value = false }
}
onMounted(load)
</script>

<template>
  <section v-if="data" class="page catalog-book-view">
    <header><button class="back" aria-label="Назад" @click="router.back()"><svg viewBox="0 0 24 24" fill="none"><path d="m14.5 5-7 7 7 7"/></svg></button><div><p class="eyebrow">ПРОСМОТР РАСКРАСКИ</p><h1>{{ data.book.title }}</h1><p>{{ data.book.author || 'Раскраска' }}</p></div></header>
    <div class="catalog-book-intro"><img v-if="data.book.cover" :src="data.book.cover" :alt="data.book.title"><div v-else class="cover-placeholder" aria-label="Обложка пока не добавлена">❀</div><div><p v-if="data.book.publisher" class="catalog-publisher">{{ data.book.publisher }}</p><p>{{ data.book.description || 'Описание для этой раскраски пока не добавлено.' }}</p><b>{{ formatCount(data.book.pages, 'page') }}</b></div></div>
    <div class="section-title"><h2>Что внутри</h2><span class="muted">{{ data.pages.length }} позиций</span></div>
    <div class="catalog-page-grid"><article v-for="page in data.pages" :key="page.id" :class="{ spread: page.spread_end }"><span>{{ page.label }}</span><small>{{ page.title || (page.spread_end ? 'Разворот' : 'Страница') }}</small></article></div>
    <button class="primary catalog-add" :disabled="adding" @click="add">{{ adding ? 'Добавляем…' : 'Добавить в коллекцию' }}</button>
  </section>
  <section v-else class="page muted">Загружаем раскраску…</section>
</template>
