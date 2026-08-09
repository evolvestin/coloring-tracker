<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import DonationIcon from '../components/DonationIcon.vue'
import { api } from '../api'

const router = useRouter()
const config = ref(null)
const selectedAmount = ref(50)
const busy = ref(false)
const error = ref('')
const currentDonation = ref(null)
const stage = ref('ready')
const customAmount = ref('')

const amounts = computed(() => config.value?.amounts || [10, 50, 100, 250])
const isTestMode = computed(() => Boolean(config.value?.test_mode))
const isUnavailable = computed(() => config.value && !config.value.enabled && !isTestMode.value)
const amountToSend = computed(() => {
  const rawAmount = String(customAmount.value ?? '').trim()
  if (!rawAmount) return selectedAmount.value
  const amount = Number(rawAmount)
  return Number.isInteger(amount) ? amount : 0
})
const amountIsValid = computed(() => amountToSend.value >= 1 && amountToSend.value <= 10000)

async function load() {
  try {
    config.value = await api('/api/tracker/stars/')
    if (!amounts.value.includes(selectedAmount.value)) selectedAmount.value = amounts.value[0]
  } catch (loadError) {
    error.value = loadError.message
  }
}

async function waitForPayment(donationId) {
  for (let attempt = 0; attempt < 7; attempt += 1) {
    const result = await api(`/api/tracker/stars/${donationId}/`)
    if (result.donation.status === 'succeeded') return true
    await new Promise(resolve => window.setTimeout(resolve, 700))
  }
  return false
}

async function startDonation() {
  if (busy.value || isUnavailable.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await api('/api/tracker/stars/invoice/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ amount: amountToSend.value }),
    })
    currentDonation.value = result.donation
    if (result.test_mode) {
      stage.value = 'test-checkout'
      return
    }

    const webApp = window.Telegram?.WebApp
    if (!webApp?.openInvoice) {
      error.value = 'Похоже, экран открыт не в Telegram. Откройте приложение там — и всё получится.'
      return
    }
    stage.value = 'waiting'
    webApp.openInvoice(result.invoice_url, async status => {
      if (status === 'paid') {
        stage.value = await waitForPayment(result.donation.id) ? 'success' : 'pending'
      } else if (status === 'pending') {
        stage.value = 'pending'
      } else {
        stage.value = 'ready'
        error.value = status === 'failed' ? 'Не получилось завершить оплату. Можно попробовать ещё раз — Stars не пропадут.' : ''
      }
    })
  } catch (startError) {
    error.value = startError.message
  } finally {
    busy.value = false
  }
}

async function completeTestDonation() {
  if (!currentDonation.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    await api(`/api/tracker/stars/${currentDonation.value.id}/test-complete/`, { method: 'POST' })
    stage.value = 'success'
  } catch (testError) {
    error.value = testError.message
  } finally {
    busy.value = false
  }
}

function reset() {
  if (busy.value) return
  currentDonation.value = null
  stage.value = 'ready'
  error.value = ''
}

function selectPreset(amount) {
  selectedAmount.value = amount
  customAmount.value = ''
}

onMounted(load)
</script>

<template>
  <section class="page support-page">
    <header><button class="back" aria-label="Назад" @click="router.push('/')"><svg viewBox="0 0 24 24" fill="none"><path d="m14.5 5-7 7 7 7"/></svg></button><div><p class="eyebrow">ОТ ВСЕЙ ДУШИ</p><h1>Помочь трекеру</h1></div></header>

    <div class="support-hero">
      <div class="support-orbit support-orbit-one">✦</div><div class="support-orbit support-orbit-two">✿</div><div class="support-flower">✾</div>
      <p class="eyebrow">СПАСИБО, ЧТО РАСКРАШИВАЕТЕ С НАМИ</p><h2>Пусть здесь будет ещё уютнее</h2><p>Если захотите поддержать проект, даже маленький знак внимания поможет нам находить новые раскраски и делать трекер приятнее.</p>
    </div>

    <template v-if="stage === 'success'">
      <div class="support-success-card"><div class="support-success-burst"><i>✦</i><i>✿</i><i>✧</i><span>✓</span></div><p class="eyebrow">СПАСИБО ОТ ВСЕЙ ДУШИ</p><h2>Это правда очень помогает ✨</h2><p>У трекера стало чуть больше сил на новые раскраски.</p><button class="primary support-submit" @click="reset">Оставить ещё один знак внимания</button></div>
    </template>
    <template v-else>
      <div class="support-card">
        <div class="support-card-title"><div><h2>Сколько подарить проекту?</h2><p>Разовая поддержка через Telegram Stars.</p></div><span class="stars-mark"><DonationIcon /></span></div>
        <template v-if="config">
          <div class="support-amounts" role="group" aria-label="Быстрый выбор суммы"><button v-for="amount in amounts" :key="amount" type="button" :class="{ selected: !customAmount && selectedAmount === amount }" @click="selectPreset(amount)"><DonationIcon />{{ amount }}</button></div>
          <label class="support-custom-amount">Своя сумма <span><input v-model="customAmount" type="number" min="1" max="10000" step="1" inputmode="numeric" placeholder="Например, 37"><b>Stars</b></span></label>
        </template>
        <div v-else class="support-loading">Сейчас всё подготовим…</div>
        <div v-if="isTestMode" class="support-test-note"><span>⌁</span><div><b>Можно спокойно попробовать</b><small>Это тестовый режим: Stars не списываются, а после кнопки покажется экран благодарности.</small></div></div>
        <p v-if="isUnavailable" class="support-disabled">Мы ещё настраиваем эту возможность. Скоро всё будет готово.</p>
        <p v-if="error" class="support-error" role="alert">{{ error }}</p>
        <button class="primary support-submit" :disabled="busy || isUnavailable || !config || !amountIsValid" @click="startDonation">{{ busy ? 'Секундочку…' : (isTestMode ? 'Посмотреть, как это работает' : `Подарить ${amountToSend} Stars`) }}</button>
        <p class="support-footnote">Только один раз · никакой подписки</p>
      </div>
    </template>

    <transition name="modal"><div v-if="stage === 'test-checkout'" class="modal-backdrop" @click.self="reset"><section class="support-test-modal" role="dialog" aria-modal="true" aria-labelledby="support-test-title"><button class="modal-close" aria-label="Закрыть" @click="reset">×</button><div class="test-ticket"><DonationIcon /><b>{{ currentDonation?.amount }}</b><small>Stars · демо</small></div><p class="eyebrow">НЕБОЛЬШАЯ ПРОВЕРКА</p><h2 id="support-test-title">Посмотрим, как всё будет?</h2><p>Это только демонстрация: Telegram не откроется, деньги и Stars не списываются. Можно просто увидеть финальную анимацию.</p><button class="primary support-submit" :disabled="busy" @click="completeTestDonation">{{ busy ? 'Секундочку…' : 'Показать благодарность' }}</button><button class="support-cancel" :disabled="busy" @click="reset">Не сейчас</button></section></div></transition>
    <div v-if="stage === 'waiting'" class="support-toast">Возвращаемся с новостями…</div>
    <div v-if="stage === 'pending'" class="support-pending"><span>⌁</span><div><b>Telegram ещё подтверждает оплату</b><small>Это может занять немного времени. Мы сохранили всё и дождёмся подтверждения.</small></div><button class="support-cancel" @click="reset">Хорошо</button></div>
  </section>
</template>
