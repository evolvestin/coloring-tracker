<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
const router=useRouter(), profile=ref(null)
onMounted(async()=>{profile.value=await api('/api/tracker/profile/')})
</script>
<template><section v-if="profile" class="page"><header><button class="back" @click="router.back()">‹</button><div><p class="eyebrow">ПРОФИЛЬ</p><h1>Мои результаты</h1></div></header><div class="profile-card"><img v-if="profile.user.photo_url" :src="profile.user.photo_url"><div v-else class="avatar">❀</div><div><h2>{{profile.user.name}}</h2><p v-if="profile.user.username">@{{profile.user.username}}</p><p v-else>Личный трекер</p></div><b>{{profile.stats.progress}}%</b></div><div class="profile-stats"><div><b>{{profile.stats.completed}}</b><span>раскрашено</span></div><div><b>{{profile.stats.books}}</b><span>книг</span></div><div><b>{{profile.stats.total}}</b><span>страниц всего</span></div></div><button class="report-link" @click="router.push('/report')">▥ Открыть отчёт за месяц <span>›</span></button></section><section v-else class="page muted">Загружаем профиль…</section></template>
