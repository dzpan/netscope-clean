import { createApp } from 'vue'
import App from './App.vue'
import { vResizableColumns } from './directives/resizableColumns.js'
import './style.css'

const app = createApp(App)
app.directive('resizable-columns', vResizableColumns)
app.mount('#app')
