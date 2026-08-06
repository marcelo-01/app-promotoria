import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { Quasar, Notify, Loading, Dialog } from 'quasar'
import quasarIconSet from 'quasar/icon-set/material-icons'
import '@quasar/extras/roboto-font/roboto-font.css'
import '@quasar/extras/material-icons/material-icons.css'
import 'quasar/dist/quasar.css'

import App from './App.vue'
import router from './router'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(Quasar, {
  plugins: { Notify, Loading, Dialog },
  iconSet: quasarIconSet,
  config: {
    dark: false,
    // Mesmas cores de marca do ERP — quando as telas migrarem, a identidade já bate
    brand: {
      primary: '#1a237e',
      secondary: '#fbc02d',
      accent: '#283593',
      dark: '#0d1442',
      positive: '#2e7d32',
      negative: '#c62828',
      info: '#0288d1',
      warning: '#f57c00',
    },
  },
})

app.mount('#app')
