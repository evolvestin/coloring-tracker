<script setup>
import { computed, ref, watch } from 'vue'
import { formatCount } from '../pluralize'

const props = defineProps({
  pages: { type: Array, required: true },
})

const emit = defineEmits(['update:pages'])

const MAX_PAGE_COUNT = 300
const DEFAULT_PAGE_COUNT = 50
let pageKey = 0
const pageCountInput = ref('')
const countFocused = ref(false)

function makePage(number) {
  return { id: null, _key: `new-${pageKey += 1}`, number: String(number), spread_end: null, title: '' }
}

function normalizedPages(pages) {
  return pages.map((page) => ({
    id: page.id || null,
    _key: page._key || page.id || `new-${pageKey += 1}`,
    number: page.number ?? '',
    spread_end: page.spread_end ?? null,
    title: page.title || '',
  }))
}

function pageUnits(page) {
  return page.spread_end === null || page.spread_end === '' ? 1 : 2
}

function countPages(pages) {
  return pages.reduce((total, page) => total + pageUnits(page), 0)
}

function reindexPages(pages) {
  let number = 1
  return pages.map((page) => {
    const spread = page.spread_end !== null && page.spread_end !== ''
    const next = { ...page, number: String(number), spread_end: spread ? String(number + 1) : null }
    number += spread ? 2 : 1
    return next
  })
}

function pageLabel(index, page) {
  let number = 1
  for (let cursor = 0; cursor < index; cursor += 1) number += pageUnits(rows.value[cursor])
  return page.spread_end !== null && page.spread_end !== '' ? `${number}–${number + 1}` : String(number)
}

const rows = computed(() => props.pages)
const pageCount = computed(() => countPages(rows.value))

watch(() => props.pages, (pages) => {
  if (!countFocused.value) pageCountInput.value = String(countPages(pages))
}, { deep: true, immediate: true })

function updatePages(nextPages) {
  emit('update:pages', nextPages)
}

function lastPageNumber(pages) {
  return pages.reduce((last, page) => {
    const number = Number(page.spread_end || page.number)
    return Number.isInteger(number) ? Math.max(last, number) : last
  }, 0)
}

function resizePages(target) {
  const nextCount = Math.min(MAX_PAGE_COUNT, Math.max(0, Number(target) || 0))
  const current = reindexPages(normalizedPages(props.pages))
  if (nextCount === 0) {
    updatePages([])
    return
  }

  const next = []
  let used = 0
  for (const page of current) {
    const units = pageUnits(page)
    if (used + units <= nextCount) {
      next.push(page)
      used += units
    } else if (used < nextCount) {
      // Never leave a half-spread behind when the count is reduced.
      next.push({ ...page, spread_end: null })
      used += 1
      break
    } else {
      break
    }
  }

  let number = lastPageNumber(next) + 1
  while (used < nextCount) {
    next.push(makePage(number))
    number += 1
    used += 1
  }
  updatePages(reindexPages(next))
}

function onPageCountInput(event) {
  pageCountInput.value = event.target.value
  if (event.target.value === '') {
    updatePages([])
    return
  }
  resizePages(event.target.value)
  pageCountInput.value = String(Math.min(MAX_PAGE_COUNT, Math.max(0, Number(event.target.value) || 0)))
}

function normalizePageCountInput() {
  pageCountInput.value = String(pageCount.value)
}

function setPageCount(count) {
  pageCountInput.value = String(count)
  resizePages(count)
}

function updateField(index, field, value) {
  const next = normalizedPages(rows.value)
  next[index][field] = value
  updatePages(next)
}

function removePage(index) {
  const next = normalizedPages(rows.value)
  next.splice(index, 1)
  updatePages(reindexPages(next))
}

function toggleSpread(index, event) {
  const next = normalizedPages(rows.value)
  const page = next[index]
  if (!page) return

  if (!event.target.checked) {
    const end = Number(page.spread_end)
    page.spread_end = null
    next.splice(index + 1, 0, makePage(Number.isInteger(end) ? end : Number(page.number) + 1))
    updatePages(reindexPages(next))
    return
  }

  const currentNumber = Number(page.number)
  if (!Number.isInteger(currentNumber) || currentNumber < 1) {
    event.target.checked = false
    return
  }

  if (!next[index + 1]) {
    if (countPages(next) >= MAX_PAGE_COUNT) {
      event.target.checked = false
      return
    }
    next.push(makePage(currentNumber + 1))
  }

  // If the following row is itself a spread, split off its second page first;
  // the current row can then consume exactly the next page, never three.
  const following = next[index + 1]
  if (!page.title && following.title) page.title = following.title
  if (following.spread_end !== null && following.spread_end !== '') {
    const secondPage = makePage(Number(following.number) + 1)
    next.splice(index + 1, 1, { ...following, spread_end: null }, secondPage)
  }

  page.spread_end = String(currentNumber + 1)
  next.splice(index + 1, 1)
  updatePages(reindexPages(next))
}
</script>

<template>
  <fieldset class="page-builder">
    <legend>
      <span class="page-builder-heading">
        <strong>Страницы</strong>
        <small>до {{ MAX_PAGE_COUNT }} физических страниц</small>
      </span>
      <span class="page-builder-summary">{{ formatCount(pageCount, 'page') }} · {{ formatCount(rows.length, 'work') }}</span>
    </legend>
    <div class="page-builder-toolbar">
      <label><span>Количество физических страниц</span>
        <input
          :value="pageCountInput"
          type="number"
          min="0"
          :max="MAX_PAGE_COUNT"
          inputmode="numeric"
          @focus="countFocused = true"
          @blur="countFocused = false; normalizePageCountInput()"
          @input="onPageCountInput"
        >
      </label>
      <div class="page-count-presets" aria-label="Быстрое количество страниц">
        <button type="button" :class="{ active: pageCount === DEFAULT_PAGE_COUNT }" @click="setPageCount(DEFAULT_PAGE_COUNT)">50</button>
        <button type="button" :class="{ active: pageCount === 100 }" @click="setPageCount(100)">100</button>
      </div>
      <p>Номера проставятся автоматически. Объедините две соседние страницы в разворот или добавьте короткую подпись к работе.</p>
    </div>
    <p v-if="!rows.length" class="page-builder-empty">Пока нет страниц. Добавьте их кнопкой 50 или 100 либо впишите количество вручную.</p>
    <transition-group name="page-builder-list" tag="div" class="page-builder-list">
      <div v-for="(page, index) in rows" :key="page.id || page._key || `new-${index}`" class="page-builder-row" :class="{ 'is-spread': page.spread_end !== null && page.spread_end !== '' }">
        <div class="page-builder-index" :class="{ 'is-spread': page.spread_end !== null && page.spread_end !== '' }" :aria-label="`Страницы ${pageLabel(index, page)}`">
          <strong>{{ pageLabel(index, page) }}</strong>
          <small>{{ page.spread_end !== null && page.spread_end !== '' ? 'разворот' : 'страница' }}</small>
        </div>
        <div class="page-builder-fields">
          <label class="spread-check">
            <input type="checkbox" :checked="page.spread_end !== null && page.spread_end !== ''" @change="toggleSpread(index, $event)">
            <span>Разворот</span>
            <small v-if="page.spread_end !== null && page.spread_end !== ''">{{ pageLabel(index, page) }}</small>
          </label>
          <label class="page-builder-title">Подпись <span>необязательно</span>
            <input :value="page.title" maxlength="255" placeholder="Например, обложка" @input="updateField(index, 'title', $event.target.value)">
          </label>
        </div>
        <button class="remove-row" type="button" :aria-label="`Удалить ${page.spread_end ? 'разворот' : 'страницу'} ${pageLabel(index, page)}`" @click="removePage(index)">×</button>
      </div>
    </transition-group>
  </fieldset>
</template>
