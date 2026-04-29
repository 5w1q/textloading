<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { isAxiosError } from 'axios'
import {
  api,
  goToAbLogin,
  type SyncTask,
  type TaskStatus,
  type UniqueIdRow,
  type UserVideo,
} from '../api/client'

const uniqueId = ref('')
const tasks = ref<SyncTask[]>([])
const tasksPage = ref(1)
const tasksPageSize = ref(10)
const tasksTotal = ref(0)

const tasksTotalPages = computed(() => Math.max(1, Math.ceil(tasksTotal.value / tasksPageSize.value)))
const tasksJumpDraft = ref('')
const videos = ref<UserVideo[]>([])
const busy = ref(false)
const refreshing = ref(false)
const demoMode = ref(false)
const demoExplain = ref('')
const justFinishedTaskId = ref<string | null>(null)
const selectedUniqueId = ref('')
const identifierOptions = ref<UniqueIdRow[]>([])
const videosPage = ref(1)
const videosPageSize = ref(5)
const videosTotal = ref(0)

const videosTotalPages = computed(() => Math.max(1, Math.ceil(videosTotal.value / videosPageSize.value)))
const videosJumpDraft = ref('')

type FeedbackType = 'info' | 'success' | 'error' | 'warn'
const feedback = ref<{ type: FeedbackType; text: string } | null>(null)

const currentTab = ref<'home' | 'tasks' | 'videos'>('home')

async function loadPublicConfig() {
  try {
    const { data } = await api.get<{
      demo_mode: boolean
      demo_explain: string
      douyin_adapter: string
    }>('/config/public')
    demoMode.value = data.demo_mode
    demoExplain.value = data.demo_explain || ''
  } catch {
    demoMode.value = false
  }
}

async function loadTasksCount() {
  const { data } = await api.get<{ total: number }>('/tasks/count')
  tasksTotal.value = data.total
}

async function loadTasks() {
  const { data } = await api.get<SyncTask[]>('/tasks', {
    params: {
      limit: tasksPageSize.value,
      skip: (tasksPage.value - 1) * tasksPageSize.value,
    },
  })
  tasks.value = data
}

async function loadTasksPage() {
  await loadTasksCount()
  const maxP = Math.max(1, Math.ceil(tasksTotal.value / tasksPageSize.value) || 1)
  if (tasksPage.value > maxP) tasksPage.value = maxP
  await loadTasks()
}

function prevTasksPage() {
  if (tasksPage.value <= 1) return
  tasksPage.value -= 1
  tasksJumpDraft.value = ''
  void loadTasksPage()
}

function nextTasksPage() {
  if (tasksPage.value >= tasksTotalPages.value) return
  tasksPage.value += 1
  tasksJumpDraft.value = ''
  void loadTasksPage()
}

function goTasksPage() {
  const raw = pagerJumpRaw(tasksJumpDraft.value)
  if (!raw) return
  const n = parseInt(raw, 10)
  if (isNaN(n) || n < 1) return
  const maxP = tasksTotalPages.value
  tasksPage.value = Math.min(maxP, n)
  tasksJumpDraft.value = ''
  void loadTasksPage()
}

async function loadVideosCount() {
  const params: Record<string, string> = {}
  const u = selectedUniqueId.value.trim()
  if (u) params.unique_id = u
  const { data } = await api.get<{ total: number }>('/videos/count', { params })
  videosTotal.value = data.total
}

async function loadVideos() {
  const params: Record<string, string | number> = {
    limit: videosPageSize.value,
    skip: (videosPage.value - 1) * videosPageSize.value,
  }
  const u = selectedUniqueId.value.trim()
  if (u) params.unique_id = u
  const { data } = await api.get<UserVideo[]>('/videos', { params })
  videos.value = data
}

async function loadVideosPage() {
  await loadVideosCount()
  const maxP = Math.max(1, Math.ceil(videosTotal.value / videosPageSize.value) || 1)
  if (videosPage.value > maxP) videosPage.value = maxP
  await loadVideos()
}

async function loadIdentifiers() {
  try {
    const { data } = await api.get<UniqueIdRow[]>('/videos/identifiers')
    identifierOptions.value = data
    if (selectedUniqueId.value && !data.some((r) => r.unique_id === selectedUniqueId.value)) {
      selectedUniqueId.value = ''
      videosPage.value = 1
      videosJumpDraft.value = ''
    }
  } catch {
    identifierOptions.value = []
  }
}

function onUidFilterChange() {
  videosPage.value = 1
  videosJumpDraft.value = ''
  void loadVideosPage()
}

function pagerJumpRaw(v: unknown): string {
  if (v === null || v === undefined) return ''
  return String(v).trim()
}

async function startSync() {
  feedback.value = null
  justFinishedTaskId.value = null
  normalizeUniqueIdInput()
  const uid = uniqueId.value.trim()
  if (!uid) {
    feedback.value = { type: 'warn', text: '请填写抖音主页链接或标识' }
    return
  }
  busy.value = true
  try {
    const { data } = await api.post<SyncTask>('/tasks/sync', { unique_id: uid })
    feedback.value = { type: 'info', text: '任务已提交，正在同步...' }
    await pollTask(data.id)
    await refresh({ quiet: true })
    currentTab.value = 'tasks'
  } catch (e: unknown) {
    if (isAxiosError(e) && e.response?.data?.detail) {
      feedback.value = { type: 'error', text: String(e.response.data.detail).slice(0, 100) }
    } else {
      feedback.value = { type: 'error', text: '创建任务失败，请稍后重试' }
    }
  } finally {
    busy.value = false
  }
}

async function pollTask(id: string) {
  for (let i = 0; i < 60; i++) {
    const { data } = await api.get<SyncTask>(`/tasks/${id}`)
    if (['completed', 'partial'].includes(data.status)) {
      justFinishedTaskId.value = id
      feedback.value = { 
        type: 'success', 
        text: `完成！本批新增 ${data.new_links_count} 条链接` 
      }
      return
    }
    if (data.status === 'failed') {
      feedback.value = { type: 'error', text: data.error_message || '同步失败' }
      return
    }
    await new Promise(r => setTimeout(r, 800))
  }
}

function isBatchRow(v: UserVideo): boolean {
  return Boolean(v.source_task_id && justFinishedTaskId.value && v.source_task_id === justFinishedTaskId.value)
}

async function refresh(options?: { quiet?: boolean }) {
  if (refreshing.value) return
  refreshing.value = true
  try {
    await Promise.all([loadTasksPage(), loadIdentifiers(), loadVideosPage()])
    if (!options?.quiet) {
      feedback.value = { type: 'success', text: '已刷新' }
      setTimeout(() => { if (feedback.value?.text === '已刷新') feedback.value = null }, 1500)
    }
  } catch {
    feedback.value = { type: 'error', text: '刷新失败' }
  } finally {
    refreshing.value = false
  }
}

function copyPlain(text: string, okMsg: string) {
  navigator.clipboard.writeText(text).then(() => {
    feedback.value = { type: 'success', text: okMsg }
    setTimeout(() => { if (feedback.value?.text === okMsg) feedback.value = null }, 1800)
  })
}

function logout() {
  api.post('/auth/logout').finally(() => goToAbLogin('login'))
}

function normalizeUniqueIdInput() {
  const t = uniqueId.value.trim()
  if (!t) return
  const m = t.match(/douyin\.com\/user\/([^/?#]+)/i)
  if (m?.[1]) uniqueId.value = decodeURIComponent(m[1])
}

onMounted(() => {
  void loadPublicConfig()
  void refresh({ quiet: true })
})
</script>

<template>
  <div class="min-h-screen bg-slate-50 pb-20">
    <!-- 顶部标题栏 -->
    <header class="bg-white border-b sticky top-0 z-50 shadow-sm">
      <div class="max-w-2xl mx-auto px-4 py-4 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 bg-amber-500 text-white rounded-2xl flex items-center justify-center text-2xl shadow-inner">🔗</div>
          <div>
            <h1 class="font-bold text-xl text-slate-900">抖音同步</h1>
            <p class="text-xs text-slate-500 -mt-0.5">Ab 项目专属工具</p>
          </div>
        </div>
        <button @click="logout" class="text-slate-500 hover:text-red-500 transition-colors">
          <span class="text-sm">退出</span>
        </button>
      </div>
    </header>

    <!-- 主要内容 -->
    <div class="max-w-2xl mx-auto px-4 pt-6">
      <!-- 演示模式提示 -->
      <div v-if="demoMode" class="mb-6 bg-orange-50 border border-orange-200 rounded-2xl p-4 text-sm">
        <strong class="text-orange-700">演示模式</strong>
        <p class="text-orange-600 mt-1 text-xs">{{ demoExplain }}</p>
      </div>

      <!-- Tab 切换 -->
      <div class="flex bg-white rounded-3xl p-1 shadow-sm mb-6">
        <button 
          @click="currentTab = 'home'" 
          :class="{ 'bg-amber-500 text-white shadow': currentTab === 'home' }"
          class="flex-1 py-3 text-sm font-medium rounded-3xl transition-all"
        >
          新建同步
        </button>
        <button 
          @click="currentTab = 'tasks'" 
          :class="{ 'bg-amber-500 text-white shadow': currentTab === 'tasks' }"
          class="flex-1 py-3 text-sm font-medium rounded-3xl transition-all"
        >
          最近任务
        </button>
        <button 
          @click="currentTab = 'videos'" 
          :class="{ 'bg-amber-500 text-white shadow': currentTab === 'videos' }"
          class="flex-1 py-3 text-sm font-medium rounded-3xl transition-all"
        >
          已采集链接
        </button>
      </div>

      <!-- Home Tab: 新建同步 -->
      <div v-if="currentTab === 'home'" class="space-y-6">
        <div class="bg-white rounded-3xl p-6 shadow">
          <h2 class="text-lg font-semibold mb-4 text-slate-800">同步抖音主页视频</h2>
          <textarea
            v-model="uniqueId"
            rows="3"
            placeholder="粘贴完整抖音主页链接&#10;例如：https://www.douyin.com/user/MS4wLjABAAAA..."
            class="w-full p-4 border border-slate-200 rounded-2xl focus:border-amber-500 focus:ring-2 focus:ring-amber-100 resize-none text-sm font-mono"
            @blur="normalizeUniqueIdInput"
          ></textarea>

          <button
            @click="startSync"
            :disabled="busy"
            class="mt-6 w-full h-14 bg-gradient-to-r from-amber-500 to-yellow-500 text-white font-semibold rounded-2xl flex items-center justify-center gap-2 active:scale-95 transition-all shadow-lg shadow-amber-500/40 text-base"
          >
            <span v-if="busy" class="animate-spin w-5 h-5 border-2 border-white/30 border-t-white rounded-full"></span>
            {{ busy ? '正在提交任务...' : '开始同步' }}
          </button>
        </div>

        <div v-if="feedback" class="p-4 rounded-2xl text-sm" :class="{
          'bg-green-100 text-green-700': feedback.type === 'success',
          'bg-red-100 text-red-700': feedback.type === 'error',
          'bg-amber-100 text-amber-700': feedback.type === 'warn'
        }">
          {{ feedback.text }}
        </div>
      </div>

      <!-- Tasks Tab -->
      <div v-if="currentTab === 'tasks'" class="space-y-4">
        <div v-for="t in tasks" :key="t.id" class="bg-white rounded-3xl p-5 shadow-sm">
          <div class="flex justify-between items-start">
            <div>
              <div class="font-mono text-xs text-slate-400">{{ new Date(t.created_at).toLocaleString() }}</div>
              <div class="font-medium text-slate-800 mt-1 break-all">{{ t.unique_id }}</div>
            </div>
            <span :class="{
              'px-3 py-1 text-xs rounded-full font-medium': true,
              'bg-blue-100 text-blue-700': t.status === 'running',
              'bg-green-100 text-green-700': t.status === 'completed',
              'bg-orange-100 text-orange-700': t.status === 'partial',
              'bg-red-100 text-red-700': t.status === 'failed',
              'bg-slate-100 text-slate-600': t.status === 'pending'
            }">
              {{ t.status === 'completed' ? '完成' : t.status === 'partial' ? '部分完成' : t.status }}
            </span>
          </div>
          <div class="mt-3 text-sm text-emerald-600 font-medium">
            新增 {{ t.new_links_count }} 条链接
          </div>
        </div>
        <p v-if="!tasks.length" class="text-center py-12 text-slate-400">暂无同步任务</p>
      </div>

      <!-- Videos Tab -->
      <div v-if="currentTab === 'videos'" class="space-y-4">
        <div v-for="v in videos" :key="v.aweme_id" class="bg-white rounded-3xl p-5 shadow-sm">
          <div class="font-mono text-xs text-slate-400 mb-2">{{ v.unique_id }}</div>
          <a :href="v.share_url" target="_blank" class="block text-blue-600 hover:text-blue-700 break-all text-sm leading-relaxed">
            {{ v.share_url }}
          </a>
          <div class="text-[10px] text-slate-400 mt-3">
            {{ new Date(v.created_at).toLocaleDateString() }}
          </div>
        </div>
      </div>
    </div>

    <!-- 底部导航 -->
    <nav class="bottom-nav bg-white border-t border-slate-200">
      <div class="max-w-2xl mx-auto flex text-xs">
        <button @click="currentTab = 'home'" :class="{ 'text-amber-500': currentTab === 'home' }" class="flex-1 py-3 flex flex-col items-center gap-1 text-slate-500">
          <span class="text-xl">🏠</span>
          <span class="font-medium">首页</span>
        </button>
        <button @click="currentTab = 'tasks'" :class="{ 'text-amber-500': currentTab === 'tasks' }" class="flex-1 py-3 flex flex-col items-center gap-1 text-slate-500">
          <span class="text-xl">📋</span>
          <span class="font-medium">任务</span>
        </button>
        <button @click="currentTab = 'videos'" :class="{ 'text-amber-500': currentTab === 'videos' }" class="flex-1 py-3 flex flex-col items-center gap-1 text-slate-500">
          <span class="text-xl">🎥</span>
          <span class="font-medium">视频</span>
        </button>
        <button @click="logout" class="flex-1 py-3 flex flex-col items-center gap-1 text-slate-500">
          <span class="text-xl">⏻</span>
          <span class="font-medium">退出</span>
        </button>
      </div>
    </nav>
  </div>
</template>

<style scoped>
.bottom-nav {
  box-shadow: 0 -4px 12px -2px rgb(0 0 0 / 0.08);
}
</style>
