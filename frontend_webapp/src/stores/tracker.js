import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'

export const useTrackerStore = defineStore('tracker', () => {
  const collectionBooks = ref([])
  const profile = ref(null)
  const collectionLoading = ref(false)
  const collectionLoaded = ref(false)

  const catalogBooks = ref([])
  const catalogLoading = ref(false)
  const catalogLoaded = ref(false)

  const report = ref(null)
  const reportLoading = ref(false)
  const reportLoaded = ref(false)

  async function loadCollection(force = false) {
    if (collectionLoading.value && !force) return
    if (!force && collectionLoaded.value) return
    collectionLoading.value = true
    try {
      const [bookResult, profileResult] = await Promise.all([
        api('/api/tracker/books/'),
        api('/api/tracker/profile/'),
      ])
      collectionBooks.value = bookResult.books
      profile.value = profileResult
      collectionLoaded.value = true
    } finally {
      collectionLoading.value = false
    }
  }

  async function loadCatalog(query = '', force = false) {
    const trimmedQuery = query.trim()
    if (catalogLoading.value && !force) return
    if (!force && catalogLoaded.value && !trimmedQuery) return
    catalogLoading.value = true
    try {
      const params = new URLSearchParams()
      if (trimmedQuery) params.set('q', trimmedQuery)
      const res = await api('/api/tracker/catalog/?' + params)
      catalogBooks.value = res.books
      catalogLoaded.value = true
    } finally {
      catalogLoading.value = false
    }
  }

  async function loadReport(month = '', force = false) {
    if (reportLoading.value && !force) return
    if (!force && reportLoaded.value && !month) return
    reportLoading.value = true
    try {
      const queryStr = month ? `?month=${encodeURIComponent(month)}` : ''
      report.value = await api(`/api/tracker/report/${queryStr}`)
      reportLoaded.value = true
    } catch (err) {
      if (month) {
        report.value = await api('/api/tracker/report/')
        reportLoaded.value = true
      } else {
        throw err
      }
    } finally {
      reportLoading.value = false
    }
  }

  async function preloadAll() {
    await Promise.allSettled([
      loadCollection(),
      loadCatalog(),
      loadReport(),
    ])
  }

  return {
    collectionBooks,
    profile,
    collectionLoading,
    collectionLoaded,
    catalogBooks,
    catalogLoading,
    catalogLoaded,
    report,
    reportLoading,
    reportLoaded,
    loadCollection,
    loadCatalog,
    loadReport,
    preloadAll,
  }
})