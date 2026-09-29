import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './tracker.css'
import './marker.css'
import './marker-influence.css'
import './layout-fixes.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
