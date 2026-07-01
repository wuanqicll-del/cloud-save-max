import { createApp } from 'vue'
import 'element-plus/dist/index.css'
import './style.css'
import App from './App.vue'
import { createPinia } from 'pinia'
import { router } from './router'
import { inputBlurOnEnterPlugin } from './plugins/inputBlur'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(inputBlurOnEnterPlugin)
app.mount('#app')
