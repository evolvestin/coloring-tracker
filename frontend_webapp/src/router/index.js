import { createRouter, createWebHashHistory } from 'vue-router'
import TrackerView from '../views/TrackerView.vue'
import BookView from '../views/BookView.vue'
import ReportView from '../views/ReportView.vue'
import CatalogView from '../views/CatalogView.vue'
import CatalogBookView from '../views/CatalogBookView.vue'

if (window.location.hash.startsWith('#tgWebApp')) window.history.replaceState(null, '', window.location.pathname + window.location.search)

export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: TrackerView },
    { path: '/catalog', component: CatalogView },
    { path: '/catalog/book/:id', component: CatalogBookView, props: true },
    { path: '/book/:id', component: BookView, props: true },
    { path: '/report', component: ReportView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
