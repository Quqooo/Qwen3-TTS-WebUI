import { createApp } from "vue"
import { createPinia } from "pinia"
import router from "./router"
import { vTooltip } from "./directives/tooltip"
import { t } from "./lang"
import App from "./App.vue"
import "./style.css"

const app = createApp(App)
app.directive("tooltip", vTooltip)
app.config.globalProperties.$t = t
app.use(createPinia())
app.use(router)
app.mount("#app")
