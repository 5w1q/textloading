import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import { api, goToAbLogin } from '../api/client'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'dashboard', component: DashboardView, meta: { requiresAuth: true } },
    { path: '/login', name: 'login', component: LoginView },
    { path: '/register', name: 'register', component: RegisterView },
  ],
})

router.beforeEach(async (to) => {
  if (to.name === 'login') {
    goToAbLogin('login')
    return false
  }
  if (to.name === 'register') {
    goToAbLogin('register')
    return false
  }

  if (to.meta.requiresAuth) {
    try {
      await api.get('/auth/me')
      return true
    } catch {
      goToAbLogin('login')
      return false
    }
  }
  return true
})

export default router
