<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'

const route = useRoute(), router = useRouter()
const data = ref(null), tab = ref('all'), fileInput = ref(null), activePage = ref(null), uploading = ref(false)
const pages = computed(() => !data.value ? [] : data.value.pages.filter(page => tab.value === 'all' || (tab.value === 'done' ? page.completed : !page.completed)))
async function load() { data.value = await api(`/api/tracker/books/${route.params.id}/`) }
function choose(page) { activePage.value = page; fileInput.value?.click() }
async function upload(event) { const file = event.target.files[0]; if (!file || !activePage.value) return; uploading.value = true; try { const form = new FormData(); form.append('photo', file); await api(`/api/tracker/books/${route.params.id}/pages/${activePage.value.id}/`, { method: 'POST', body: form }); await load() } finally { uploading.value = false; event.target.value = '' } }
async function toggle(page) { await api(`/api/tracker/books/${route.params.id}/pages/${page.id}/`, { method: page.completed ? 'DELETE' : 'POST', body: page.completed ? undefined : new FormData() }); await load() }
function imageFailed(event) { event.target.classList.add('is-broken') }
onMounted(load)
</script>

<template>
  <section v-if="data" class="page book-view">
    <header><button class="back" aria-label="Назад" @click="router.back()"><svg viewBox="0 0 24 24" fill="none"><path d="m14.5 5-7 7 7 7"/></svg></button><div><p class="eyebrow">МОЯ КНИГА</p><h1>{{ data.book.title }}</h1><p>{{ data.book.author }}</p></div></header>
    <div class="progress-card"><div class="progress-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M5 19.5V10m5 9.5V4m5 15.5v-7m5 7V7"/></svg></div><div><b>{{ data.book.done }} из {{ data.book.total }}</b><span>Осталось {{ data.book.total - data.book.done }} страниц</span></div><div class="progress-line"><i :style="{ width: data.book.progress + '%' }"></i></div></div>
    <div class="tabs"><button :class="{ active: tab === 'all' }" @click="tab = 'all'">Все <small>{{ data.pages.length }}</small></button><button :class="{ active: tab === 'done' }" @click="tab = 'done'">Готово <small>{{ data.book.done }}</small></button><button :class="{ active: tab === 'left' }" @click="tab = 'left'">Осталось <small>{{ data.book.total - data.book.done }}</small></button></div>
    <input ref="fileInput" hidden type="file" accept="image/*" @change="upload"><p v-if="uploading" class="uploading">Сохраняем фотографию…</p>
    <transition-group name="pages" tag="div" class="page-grid"><article v-for="page in pages" :key="page.id" :class="['coloring-page', { done: page.completed, spread: page.spread_end }]"><img v-if="page.photo" :src="page.photo" :alt="'Работа ' + page.label" @error="imageFailed"><button v-else class="add-work" aria-label="Добавить фотографию" @click="choose(page)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M12 5v14M5 12h14"/></svg></button><span>{{ page.label }}</span><button class="check" :aria-label="page.completed ? 'Удалить работу' : 'Отметить готовой'" @click="toggle(page)"><svg v-if="page.completed" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="m5 12 4.2 4.2L19 6.5"/></svg><svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="7"/></svg></button></article></transition-group>
  </section>
  <section v-else class="page muted">Загружаем книгу…</section>
</template>
