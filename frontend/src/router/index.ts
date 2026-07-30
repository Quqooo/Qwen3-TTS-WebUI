import { createRouter, createWebHistory } from "vue-router"

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      redirect: "/base",
    },
    {
      path: "/base",
      name: "base",
      component: () => import("../views/BaseView.vue"),
      meta: { title: "routes.base", icon: "mic-vocal" },
    },
    {
      path: "/custom-voice",
      name: "custom-voice",
      component: () => import("../views/CustomVoiceView.vue"),
      meta: { title: "routes.customVoice", icon: "speech" },
    },
    {
      path: "/voice-design",
      name: "voice-design",
      component: () => import("../views/VoiceDesignView.vue"),
      meta: { title: "routes.voiceDesign", icon: "palette" },
    },
    {
      path: "/batch",
      name: "batch",
      component: () => import("../views/BatchView.vue"),
      meta: { title: "routes.batch", icon: "list-checks" },
    },
    {
      path: "/voices",
      name: "voices",
      component: () => import("../views/VoicesView.vue"),
      meta: { title: "routes.voices", icon: "hard-drive" },
    },
    {
      path: "/settings",
      name: "settings",
      component: () => import("../views/SettingsView.vue"),
      meta: { title: "routes.settings", icon: "settings" },
    },
  ],
})

export default router
