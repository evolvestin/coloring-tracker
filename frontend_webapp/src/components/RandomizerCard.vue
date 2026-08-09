<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  userBookId: { type: [Number, String], default: null },
  compact: { type: Boolean, default: false },
})

const emit = defineEmits(['open-result'])
const dialog = ref(null)
const status = ref({ available: true, retry_after: 0, next_available_at: null, last_result: null })
const statusLoaded = ref(false)
const remaining = ref(0)
const result = ref(null)
const error = ref('')
let timer

const scopeQuery = computed(() => props.userBookId ? `?user_book_id=${encodeURIComponent(props.userBookId)}` : '')
const isBusy = computed(() => dialog.value === 'rolling')
const cooldownLabel = computed(() => {
  const total = Math.max(0, remaining.value)
  const hours = String(Math.floor(total / 3600)).padStart(2, '0')
  const minutes = String(Math.floor(total % 3600 / 60)).padStart(2, '0')
  const seconds = String(total % 60).padStart(2, '0')
  return `${hours}:${minutes}:${seconds}`
})
const lastResult = computed(() => status.value.last_result)

function applyStatus(next) {
  status.value = next
  remaining.value = Math.max(0, Number(next.retry_after || 0))
}

async function loadStatus() {
  try {
    applyStatus(await api(`/api/tracker/randomizer/${scopeQuery.value}`))
  } catch {
    // The collection request remains useful even when the optional status call fails.
  } finally {
    statusLoaded.value = true
  }
}

function tick() {
  if (remaining.value > 0) remaining.value -= 1
  if (remaining.value === 0 && !status.value.available) status.value = { ...status.value, available: true }
}

function openConfirm() {
  if (!statusLoaded.value || isBusy.value || (!status.value.available && remaining.value > 0)) return
  error.value = ''
  dialog.value = 'confirm'
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function launch() {
  if (isBusy.value) return
  error.value = ''
  dialog.value = 'rolling'
  try {
    const [response] = await Promise.all([
      api(`/api/tracker/randomizer/${scopeQuery.value}`, { method: 'POST' }),
      delay(1100),
    ])
    result.value = response.result
    applyStatus(response)
    dialog.value = 'result'
  } catch (requestError) {
    if (requestError.details?.retry_after !== undefined) applyStatus(requestError.details)
    error.value = requestError.message
    dialog.value = null
  }
}

function openSelectedResult() {
  if (result.value) emit('open-result', result.value)
  dialog.value = null
}

onMounted(() => {
  loadStatus()
  timer = window.setInterval(tick, 1000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div :class="['randomizer-widget', { compact }]">
    <button class="randomizer-launch" type="button" :disabled="!statusLoaded || isBusy || (!status.available && remaining > 0)" :aria-label="!statusLoaded ? 'Загружаем выбор работы' : status.available ? 'Выбрать работу наугад' : `Следующий выбор через ${cooldownLabel}`" :title="!statusLoaded ? 'Загружаем выбор работы' : status.available ? 'Выбрать работу наугад' : `Следующий выбор через ${cooldownLabel}`" @click="openConfirm">
      <span class="randomizer-die" :class="{ rolling: isBusy }" aria-hidden="true">
        <svg viewBox="0 0 48 48" aria-hidden="true"><circle cx="16" cy="16" r="3" fill="currentColor"/><circle cx="32" cy="16" r="3" fill="currentColor"/><circle cx="24" cy="24" r="3" fill="currentColor"/><circle cx="16" cy="32" r="3" fill="currentColor"/><circle cx="32" cy="32" r="3" fill="currentColor"/></svg>
      </span>
      <small>{{ !statusLoaded ? '…' : status.available ? '' : cooldownLabel }}</small>
    </button>
  </div>

  <transition name="modal">
    <div v-if="dialog === 'confirm'" class="modal-backdrop" @click.self="dialog = null">
      <section class="randomizer-modal" role="dialog" aria-modal="true" aria-labelledby="randomizer-confirm-title">
        <button class="modal-close" aria-label="Закрыть" @click="dialog = null">×</button>
        <div class="randomizer-modal-die"><span class="randomizer-die"><svg viewBox="0 0 48 48" aria-hidden="true"><circle cx="16" cy="16" r="3" fill="currentColor"/><circle cx="32" cy="16" r="3" fill="currentColor"/><circle cx="24" cy="24" r="3" fill="currentColor"/><circle cx="16" cy="32" r="3" fill="currentColor"/><circle cx="32" cy="32" r="3" fill="currentColor"/></svg></span></div>
        <p class="eyebrow">СЛУЧАЙНЫЙ ВЫБОР</p>
        <h2 id="randomizer-confirm-title">Выбрать работу?</h2>
        <p>Я выберу одну незакрашенную работу {{ userBookId ? 'из этой раскраски' : 'из всей коллекции' }}.</p>
        <p v-if="!userBookId" class="randomizer-hint">Если хочется выбрать работу из одной раскраски, откройте её — внутри есть отдельный выбор.</p>
        <p v-if="lastResult" class="randomizer-last">В прошлый раз: <b>{{ lastResult.book_title }}</b> · {{ lastResult.page_label }}</p>
        <p v-if="!status.available && remaining > 0" class="randomizer-timer" role="status">Следующий выбор через <b>{{ cooldownLabel }}</b></p>
        <p v-if="error" class="randomizer-error" role="alert">{{ error }}</p>
        <div class="confirm-actions"><button class="secondary" type="button" @click="dialog = null">Не сейчас</button><button class="primary" type="button" @click="launch">Выбрать</button></div>
      </section>
    </div>
  </transition>

  <transition name="modal">
    <div v-if="dialog === 'rolling'" class="modal-backdrop randomizer-rolling-backdrop">
      <section class="randomizer-modal rolling-modal" role="dialog" aria-modal="true" aria-live="polite" aria-label="Выбираем работу">
        <div class="randomizer-orbit"><i>✦</i><i>✿</i><i>·</i><span class="randomizer-die rolling"><svg viewBox="0 0 48 48" aria-hidden="true"><circle cx="16" cy="16" r="3" fill="currentColor"/><circle cx="32" cy="16" r="3" fill="currentColor"/><circle cx="24" cy="24" r="3" fill="currentColor"/><circle cx="16" cy="32" r="3" fill="currentColor"/><circle cx="32" cy="32" r="3" fill="currentColor"/></svg></span></div>
        <h2>Выбираем следующую работу…</h2>
        <p>Среди незакрашенных страниц</p>
      </section>
    </div>
  </transition>

  <transition name="modal">
    <div v-if="dialog === 'result' && result" class="modal-backdrop" @click.self="dialog = null">
      <section class="randomizer-modal result-modal" role="dialog" aria-modal="true" aria-labelledby="randomizer-result-title">
        <button class="modal-close" aria-label="Закрыть" @click="dialog = null">×</button>
        <div class="result-burst"><span>✦</span><i>·</i><i>✿</i><i>✦</i></div>
        <p class="eyebrow">ВАША СЛЕДУЮЩАЯ РАБОТА</p>
        <h2 id="randomizer-result-title">{{ result.book_is_personal ? result.book_emoji + ' ' : '' }}{{ result.book_title }}</h2>
        <p class="result-page">Страница <b>{{ result.page_label }}</b><template v-if="result.page_title"> · {{ result.page_title }}</template></p>
        <button class="primary result-open" type="button" @click="openSelectedResult">Открыть работу</button>
        <button class="randomizer-dismiss" type="button" @click="dialog = null">Закрыть</button>
      </section>
    </div>
  </transition>
</template>
