import { createRouter, createWebHistory } from "vue-router"
import SmartOrthopedicsLogin from "../views/SmartOrthopedicsLogin.vue"
import PatientPortal from "../views/PatientPortal.vue"
import DoctorWorkstation from "../views/DoctorWorkstation.vue"
import AdminApproval from "../views/AdminApproval.vue"
import Detection from "../views/Detection.vue"
import VideoStreamDetection from "../views/VideoStreamDetection.vue"
import CameraDetection from "../views/CameraDetection.vue"

// 修复 Edge 最小化自动弹回
const originalReplaceState = history.replaceState;
history.replaceState = function (...args) {
  if (document.visibilityState === 'hidden') {
    return;
  }
  originalReplaceState.apply(this, args);
};

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // 智慧骨科登录页面
    { path: "/login", component: SmartOrthopedicsLogin },
    { path: "/", redirect: "/login" },

    // 患者端
    {
      path: "/patient-portal",
      component: PatientPortal,
      meta: { requiresAuth: true, role: "patient" }
    },

    // 医生端
    {
      path: "/doctor-workstation",
      component: DoctorWorkstation,
      meta: { requiresAuth: true, role: "doctor" }
    },

    // 管理员端
    {
      path: "/admin",
      component: AdminApproval,
      meta: { requiresAuth: true, role: "admin" }
    },

    // AI检测页面 - 仅医生和admin可访问
    {
      path: "/detect",
      component: Detection,
      meta: { requiresAuth: true, allowedRoles: ["admin", "doctor"] }
    },

    // 视频流检测页面
    {
      path: "/video",
      component: VideoStreamDetection,
      meta: { requiresAuth: true, allowedRoles: ["admin", "doctor"] }
    },

    // 摄像头检测页面
    {
      path: "/camera",
      component: CameraDetection,
      meta: { requiresAuth: true, allowedRoles: ["admin", "doctor"] }
    }
  ]
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem("token")
  const userRole = localStorage.getItem("userRole")

  // 防止无限重定向：如果已经在目标路径，直接通过
  if (to.path === from.path) {
    next()
    return
  }

  // 未登录拦截（除了登录页）
  if (to.path !== "/login" && !token) {
    next("/login")
    return
  }

  // 已登录用户访问登录页，重定向到对应首页
  if (to.path === "/login" && token) {
    // 如果没有角色信息，清除token并留在登录页
    if (!userRole) {
      localStorage.removeItem("token")
      next()
      return
    }

    // 防止重定向到当前页面
    let targetPath = "/login"
    if (userRole === "admin") {
      targetPath = "/admin"
    } else if (userRole === "doctor") {
      targetPath = "/doctor-workstation"
    } else if (userRole === "patient") {
      targetPath = "/patient-portal"
    }

    // 如果目标路径和当前路径相同，不再重定向
    if (targetPath === "/login" || from.path === targetPath) {
      next()
    } else {
      next(targetPath)
    }
    return
  }

  // 角色权限验证 - 单一角色匹配
  if (to.meta.requiresAuth && to.meta.role) {
    if (!userRole) {
      next("/login")
      return
    }

    if (to.meta.role !== userRole) {
      // 角色不匹配，重定向到对应角色的首页
      let targetPath = "/login"
      if (userRole === "admin") {
        targetPath = "/admin"
      } else if (userRole === "doctor") {
        targetPath = "/doctor-workstation"
      } else if (userRole === "patient") {
        targetPath = "/patient-portal"
      }

      // 防止重定向到当前页面
      if (from.path === targetPath) {
        next()
      } else {
        next(targetPath)
      }
      return
    }
  }

  // 角色权限验证 - 多角色允许
  if (to.meta.requiresAuth && to.meta.allowedRoles) {
    if (!userRole) {
      next("/login")
      return
    }

    if (!to.meta.allowedRoles.includes(userRole)) {
      alert("您没有权限访问此页面")
      let targetPath = "/login"
      if (userRole === "admin") {
        targetPath = "/admin"
      } else if (userRole === "doctor") {
        targetPath = "/doctor-workstation"
      } else if (userRole === "patient") {
        targetPath = "/patient-portal"
      }

      // 防止重定向到当前页面
      if (from.path === targetPath) {
        next()
      } else {
        next(targetPath)
      }
      return
    }
  }

  next()
})

export default router
