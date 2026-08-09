<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import DonationIcon from '../components/DonationIcon.vue'
import RandomizerCard from '../components/RandomizerCard.vue'
import { formatCount } from '../pluralize'
import { useTrackerStore } from '../stores/tracker'

const router = useRouter()
const store = useTrackerStore()

const books = computed(() => store.collectionBooks)
const profile = computed(() => store.profile)
const loading = computed(() => store.collectionLoading && !store.collectionLoaded)

const totals = computed(() => books.value.reduce((value, book) => ({
  done: value.done + book.done,
  total: value.total + book.total,
}), { done: 0, total: 0 }))
const progress = computed(() => totals.value.total ? Math.round(totals.value.done / totals.value.total * 100) : 0)
const name = computed(() => profile.value?.user?.name || 'Моя коллекция')

function openRandomResult(result) {
  if (result?.user_book_id) router.push(`/book/${result.user_book_id}?page=${result.page_id}`)
}

onMounted(() => {
  store.loadCollection(true)
})
</script>

<template>
  <section class="page tracker-page">
    <header class="main-header">
      <div>
        <p class="eyebrow">МОЙ ТРЕКЕР</p>
        <h1>Раскраски</h1>
      </div>
      <div class="header-actions">
        <RandomizerCard @open-result="openRandomResult" />
        <button class="support-quick" type="button" aria-label="Помочь трекеру" title="Помочь трекеру" @click="router.push('/support')"><span aria-hidden="true"><DonationIcon /></span><b>Помочь</b></button>
      </div>
    </header>

    <div class="hero-card">
      <img v-if="profile?.user?.photo_url" class="avatar-photo" :src="profile.user.photo_url" alt="Аватар">
      <div v-else class="avatar">❀</div>
      <div><b>{{ name }}</b><p>{{ formatCount(books.length, 'book') }} · {{ totals.done }} из {{ totals.total }} работ</p></div>
      <div class="ring" :style="{ '--progress': progress + '%' }"><span>{{ progress }}%</span></div>
      <div class="hero-stats"><div><b>{{ totals.done }}</b><span>работ готово</span></div><div><b>{{ books.length }}</b><span>раскрасок</span></div><div><b>{{ Math.max(0, totals.total - totals.done) }}</b><span>работ осталось</span></div></div>
    </div>

    <div class="section-title"><h2>Ваша коллекция</h2><div class="section-actions"><button @click="router.push('/personal/new')">＋ Своя раскраска</button></div></div>
    <p v-if="loading && !books.length" class="muted">Загружаем коллекцию…</p>
    <transition-group v-else-if="books.length" name="cards" tag="div" class="books-grid"><button v-for="book in books" :key="book.id" :class="['book-card', { 'personal-book-card': book.is_personal }]" @click="router.push('/book/' + book.id)"><div v-if="book.is_personal && book.cover" class="personal-cover has-image"><img :src="book.cover" :alt="book.title"><small>Личная</small></div><div v-else-if="book.is_personal" class="personal-cover"><span>{{ book.emoji || '❀' }}</span><small>Личная</small></div><img v-else-if="book.cover" :src="book.cover" :alt="book.title"><div v-else class="cover-placeholder" aria-label="Обложка пока не добавлена">❀</div><strong>{{ book.done }}/{{ book.total }}</strong><span>{{ book.title }}</span></button></transition-group>
    <div v-else-if="!loading && !books.length" class="empty"><div>❀</div><h2>Коллекция ждёт первую раскраску</h2><p>Выберите книгу в каталоге или добавьте свою личную раскраску.</p><div class="empty-actions"><button class="secondary" @click="router.push('/personal/new')">Добавить свою</button><button class="primary" @click="router.push('/catalog')">Открыть каталог</button></div></div>
  </section>
</template>
