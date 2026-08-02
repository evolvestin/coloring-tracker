<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const router = useRouter()
const route = useRoute()
const hasInitData = !!window.Telegram?.WebApp?.initData
const isDevBypass = new URLSearchParams(window.location.search).get('dev') === 'true'
const isLocalPreview = new URLSearchParams(window.location.search).has('local_preview')
const isTelegram = hasInitData || isDevBypass || isLocalPreview
const activeTab = computed(() => route.path === '/catalog' ? 'catalog' : route.path === '/report' ? 'report' : 'tracker')

onMounted(() => {
  if (hasInitData) {
    window.Telegram?.WebApp?.ready()
    window.Telegram?.WebApp?.expand()
  }
})
</script>

<template>
  <template v-if="isTelegram">
    <main class="app-shell"><router-view v-slot="{ Component }"><transition name="screen" mode="out-in"><component :is="Component" /></transition></router-view></main>
    <nav class="bottom-nav" aria-label="Основная навигация">
      <button :class="{ active: activeTab === 'catalog' }" @click="router.push('/catalog')"><svg viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="5.5"/><path d="m16 16 4 4"/></svg><span>Каталог</span></button>
      <button :class="{ active: activeTab === 'tracker' }" @click="router.push('/')"><svg viewBox="0 0 24 24" fill="none"><path d="M4.5 5.5c2.8-1.2 5.5-.8 7.5 1.1 2-1.9 4.7-2.3 7.5-1.1v13c-2.8-1.2-5.5-.8-7.5 1.1-2-1.9-4.7-2.3-7.5-1.1z"/><path d="M12 6.6v13"/></svg><span>Трекер</span></button>
      <button :class="{ active: activeTab === 'report' }" @click="router.push('/report')"><svg viewBox="0 0 24 24" fill="none"><path d="M5 19.5V10m5 9.5V4m5 15.5v-7m5 7V7"/></svg><span>Статистика</span></button>
    </nav>
  </template>
  <div v-else class="landing-stub"><div class="landing-card"><span class="eyebrow">ТРЕКЕР РАСКРАСОК</span><h1>Откройте приложение в Telegram</h1><p>Так мы безопасно свяжем вашу коллекцию и готовые работы с профилем.</p><a href="/admin/" class="primary-link">Панель администратора</a></div></div>
</template>
