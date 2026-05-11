<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { api } from '../api/client'

const router = useRouter()
const route = useRoute()
const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

const sessionExpiredHint = computed(() => route.query.expired === '1')

async function submit() {
  error.value = ''
  loading.value = true
  try {
    const { data } = await api.post<{ access_token: string }>('/auth/login', {
      email: email.value,
      password: password.value,
    })
    localStorage.setItem('access_token', data.access_token)
    const redirect = (route.query.redirect as string) || '/'
    await router.push(redirect)
  } catch {
    error.value = '登录失败，请检查邮箱与密码'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page">
    <!-- Form layout from Uiverse.io by alexruix -->
    <div class="form-box">
      <form class="form" @submit.prevent="submit">
        <h1 class="title">登录</h1>
        <p class="subtitle">使用已注册邮箱进入工作台</p>

        <p v-if="sessionExpiredHint" class="session-expired" role="status">
          登录已失效（例如服务端数据已重置）。请重新登录或注册。
        </p>

        <div class="form-container">
          <label class="sr-only" for="login-email">邮箱</label>
          <input
            id="login-email"
            v-model="email"
            class="input"
            type="email"
            required
            autocomplete="email"
            placeholder="邮箱"
            aria-label="邮箱"
          />
          <label class="sr-only" for="login-password">密码</label>
          <input
            id="login-password"
            v-model="password"
            class="input"
            type="password"
            required
            autocomplete="current-password"
            placeholder="密码"
            aria-label="密码"
          />
        </div>

        <p v-if="error" class="error" role="alert">{{ error }}</p>

        <button type="submit" :disabled="loading">{{ loading ? '提交中…' : '登录' }}</button>

        <div class="form-section">
          没有账号？
          <router-link to="/register">注册</router-link>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
/* From Uiverse.io by alexruix — adapted for Vue + a11y */
.page {
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
  background: linear-gradient(165deg, #dce9f9 0%, #e8f0fb 45%, #f1f7fe 100%);
}

.form-box {
  width: 100%;
  max-width: 300px;
  background: #f1f7fe;
  overflow: hidden;
  border-radius: 16px;
  color: #010101;
  box-shadow:
    0 4px 6px -1px rgb(0 0 0 / 0.06),
    0 10px 24px -4px rgb(0 102 255 / 0.12);
}

.form {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 32px 24px 24px;
  gap: 16px;
  text-align: center;
}

.title {
  margin: 0;
  font-weight: bold;
  font-size: 1.6rem;
}

.subtitle {
  margin: -8px 0 0;
  font-size: 1rem;
  color: #666;
}

.form-container {
  overflow: hidden;
  border-radius: 8px;
  background-color: #fff;
  margin: 1rem 0 0.5rem;
  width: 100%;
}

.input {
  box-sizing: border-box;
  background: none;
  border: 0;
  outline: 0;
  height: 40px;
  width: 100%;
  border-bottom: 1px solid #eee;
  font-size: 0.9rem;
  padding: 8px 15px;
}

.input:last-of-type {
  border-bottom: 0;
}

.input::placeholder {
  color: #9ca3af;
}

.input:focus {
  background: #fafbff;
}

.form-section {
  margin: 0 -24px -24px;
  padding: 16px 24px;
  font-size: 0.85rem;
  background-color: #e0ecfb;
  box-shadow: rgb(0 0 0 / 8%) 0 -1px;
  text-align: center;
}

.form-section :deep(a) {
  font-weight: bold;
  color: #0066ff;
  transition: color 0.3s ease;
  text-decoration: none;
}

.form-section :deep(a:hover) {
  color: #005ce6;
  text-decoration: underline;
}

.form-section :deep(a:focus-visible) {
  outline: 2px solid #0066ff;
  outline-offset: 2px;
  border-radius: 2px;
}

.form button {
  background-color: #0066ff;
  color: #fff;
  border: 0;
  border-radius: 24px;
  padding: 10px 16px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.3s ease;
}

.form button:hover:not(:disabled) {
  background-color: #005ce6;
}

.form button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.form button:focus-visible {
  outline: 2px solid #005ce6;
  outline-offset: 3px;
}

.session-expired {
  margin: -4px 0 0;
  padding: 0.65rem 0.75rem;
  border-radius: 8px;
  background: #fef9c3;
  border: 1px solid #fde047;
  color: #854d0e;
  font-size: 0.8125rem;
  text-align: left;
  line-height: 1.45;
}

.error {
  margin: -4px 0 0;
  color: #b91c1c;
  font-size: 0.8125rem;
  text-align: center;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
