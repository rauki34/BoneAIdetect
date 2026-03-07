import { createRouter, createWebHistory } from "vue-router"
import Login from "../views/Login.vue"
import Register from "../views/Register.vue"
import Home from "../views/Home.vue"
import Detection from "../views/Detection.vue"

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: Login },
    { path: "/register", component: Register },
    { path: "/", redirect: "/home" },
    { path: "/home", component: Home },
    { path: "/detect", component: Detection }
  ]
})

// 登录拦截
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem("token")
  if (to.path !== "/login" && to.path !== "/register" && !token) {
    next("/login")
  } else {
    next()
  }
})

export default router
