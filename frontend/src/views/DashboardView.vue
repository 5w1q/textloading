<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { isAxiosError } from 'axios'
import { useRouter } from 'vue-router'
import {
  api,
  type DeleteIdentifierResult,
  type SyncTask,
  type TaskStatus,
  type UniqueIdRow,
  type UserVideo,
} from '../api/client'

const router = useRouter()
const uniqueId = ref('')
const tasks = ref<SyncTask[]>([])
const tasksPage = ref(1)
const tasksPageSize = ref(10)
const tasksTotal = ref(0)

const tasksTotalPages = computed(() => Math.max(1, Math.ceil(tasksTotal.value / tasksPageSize.value)))
const tasksJumpDraft = ref('')
const videos = ref<UserVideo[]>([])
const busy = ref(false)
/** 刷新列表进行中（与同步中的 busy 独立） */
const refreshing = ref(false)
const demoMode = ref(false)
const demoExplain = ref('')
/** 刚结束的一次同步任务 id，用于高亮列表中本批新增 */
const justFinishedTaskId = ref<string | null>(null)
/** 列表与导出共用：空字符串表示全部用户标识 */
const selectedUniqueId = ref('')
const identifierOptions = ref<UniqueIdRow[]>([])
const videosPage = ref(1)
const videosPageSize = ref(5)
const videosTotal = ref(0)

const videosTotalPages = computed(() => Math.max(1, Math.ceil(videosTotal.value / videosPageSize.value)))
const videosJumpDraft = ref('')

type FeedbackType = 'info' | 'success' | 'error' | 'warn'
const feedback = ref<{ type: FeedbackType; text: string } | null>(null)

const deletingTaskId = ref<string | null>(null)
const deletingIdentifier = ref(false)

/** 任务列表时间：日期 + 时:分（不显示秒） */
function formatTaskCreatedAt(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

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

function pagerJumpRaw(v: unknown): string {
  if (v === null || v === undefined) return ''
  return String(v).trim()
}

function goTasksPage() {
  const raw = pagerJumpRaw(tasksJumpDraft.value)
  if (!raw) {
    const msg = '请输入要跳转的页码'
    feedback.value = { type: 'warn', text: msg }
    setTimeout(() => {
      if (feedback.value?.text === msg) feedback.value = null
    }, 2200)
    return
  }
  if (!/^\d+$/.test(raw)) {
    const msg = '页码须为正整数'
    feedback.value = { type: 'warn', text: msg }
    setTimeout(() => {
      if (feedback.value?.text === msg) feedback.value = null
    }, 2200)
    return
  }
  const n = Number.parseInt(raw, 10)
  if (!Number.isFinite(n) || n < 1) {
    const msg = '页码须为大于等于 1 的整数'
    feedback.value = { type: 'warn', text: msg }
    setTimeout(() => {
      if (feedback.value?.text === msg) feedback.value = null
    }, 2200)
    return
  }
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

function prevVideosPage() {
  if (videosPage.value <= 1) return
  videosPage.value -= 1
  videosJumpDraft.value = ''
  void loadVideosPage()
}

function nextVideosPage() {
  if (videosPage.value >= videosTotalPages.value) return
  videosPage.value += 1
  videosJumpDraft.value = ''
  void loadVideosPage()
}

function goVideosPage() {
  const raw = pagerJumpRaw(videosJumpDraft.value)
  if (!raw) {
    const msg = '请输入要跳转的页码'
    feedback.value = { type: 'warn', text: msg }
    setTimeout(() => {
      if (feedback.value?.text === msg) feedback.value = null
    }, 2200)
    return
  }
  if (!/^\d+$/.test(raw)) {
    const msg = '页码须为正整数'
    feedback.value = { type: 'warn', text: msg }
    setTimeout(() => {
      if (feedback.value?.text === msg) feedback.value = null
    }, 2200)
    return
  }
  const n = Number.parseInt(raw, 10)
  if (!Number.isFinite(n) || n < 1) {
    const msg = '页码须为大于等于 1 的整数'
    feedback.value = { type: 'warn', text: msg }
    setTimeout(() => {
      if (feedback.value?.text === msg) feedback.value = null
    }, 2200)
    return
  }
  const maxP = videosTotalPages.value
  videosPage.value = Math.min(maxP, n)
  videosJumpDraft.value = ''
  void loadVideosPage()
}

async function copyPlain(text: string, okMsg: string) {
  try {
    await navigator.clipboard.writeText(text)
    feedback.value = { type: 'success', text: okMsg }
    setTimeout(() => {
      if (feedback.value?.text === okMsg) feedback.value = null
    }, 2000)
  } catch {
    feedback.value = { type: 'error', text: '复制失败' }
  }
}

async function refresh(options?: { quiet?: boolean }) {
  if (refreshing.value) return
  const quiet = options?.quiet === true
  refreshing.value = true
  if (!quiet) feedback.value = null
  const okMsg = '列表已更新'
  try {
    await Promise.all([loadTasksPage(), loadIdentifiers(), loadVideosPage()])
    if (!quiet) {
      feedback.value = { type: 'success', text: okMsg }
      setTimeout(() => {
        if (feedback.value?.text === okMsg) feedback.value = null
      }, 1600)
    }
  } catch {
    feedback.value = { type: 'error', text: '加载失败，请重新登录或检查网络' }
  } finally {
    refreshing.value = false
  }
}

function statusLabel(s: TaskStatus): string {
  const m: Record<TaskStatus, string> = {
    pending: '排队中',
    running: '同步中',
    completed: '已完成',
    partial: '部分成功',
    failed: '失败',
  }
  return m[s] || s
}

function statusClass(s: TaskStatus): string {
  const m: Record<TaskStatus, string> = {
    pending: 'badge badge--muted',
    running: 'badge badge--run',
    completed: 'badge badge--ok',
    partial: 'badge badge--partial',
    failed: 'badge badge--err',
  }
  return m[s] || 'badge'
}

/** 悬停状态徽章可查看 Worker 写入的异常摘要（部分成功 / 失败时） */
function taskStatusTitle(t: SyncTask): string | undefined {
  const msg = t.error_message?.trim()
  if (!msg) return undefined
  if (t.status === 'partial' || t.status === 'failed') return msg
  return undefined
}

/** 从完整主页 URL 或未编码路径中取出「/user/」与「?」「#」之间的用户标识 */
function extractHomepageUniqueId(raw: string): string {
  const t = raw.trim()
  if (!t) return ''
  const m = t.match(/(?:https?:\/\/)?(?:www\.)?douyin\.com\/user\/([^/?#]+)/i)
  if (m?.[1]) {
    try {
      return decodeURIComponent(m[1].trim())
    } catch {
      return m[1].trim()
    }
  }
  return t
}

function normalizeUniqueIdInput(): void {
  const next = extractHomepageUniqueId(uniqueId.value)
  if (next !== uniqueId.value.trim()) uniqueId.value = next
}

function onSyncUidPaste(e: ClipboardEvent) {
  const text = e.clipboardData?.getData('text/plain') ?? ''
  if (!/(?:https?:\/\/)?(?:www\.)?douyin\.com\/user\//i.test(text.trim())) return
  e.preventDefault()
  uniqueId.value = extractHomepageUniqueId(text)
}

function onSyncUidBlur() {
  normalizeUniqueIdInput()
}

async function startSync() {
  feedback.value = null
  justFinishedTaskId.value = null
  videosPage.value = 1
  tasksPage.value = 1
  tasksJumpDraft.value = ''
  videosJumpDraft.value = ''
  normalizeUniqueIdInput()
  const uid = uniqueId.value.trim()
  if (!uid) {
    feedback.value = { type: 'warn', text: '请先填写主页用户标识' }
    return
  }
  busy.value = true
  try {
    const { data } = await api.post<SyncTask>('/tasks/sync', { unique_id: uid })
    feedback.value = { type: 'info', text: `任务已创建，正在等待结果…` }
    await pollTask(data.id)
    await refresh({ quiet: true })
  } catch (e: unknown) {
    if (isAxiosError(e)) {
      const d = e.response?.data as { detail?: unknown } | undefined
      if (d?.detail != null) {
        const detail = d.detail
        let text: string
        if (typeof detail === 'string') {
          text = detail
        } else if (Array.isArray(detail)) {
          text = detail
            .map((x) =>
              typeof x === 'object' && x !== null && 'msg' in x
                ? String((x as { msg: string }).msg)
                : String(x),
            )
            .join('；')
        } else {
          text = JSON.stringify(detail)
        }
        feedback.value = { type: 'error', text: text.slice(0, 500) }
        return
      }
    }
    feedback.value = { type: 'error', text: '创建任务失败，请稍后重试' }
  } finally {
    busy.value = false
  }
}

async function pollTask(id: string) {
  for (let i = 0; i < 120; i++) {
    const { data } = await api.get<SyncTask>(`/tasks/${id}`)
    if (data.status === 'completed' || data.status === 'partial') {
      justFinishedTaskId.value = id
      const n = data.new_links_count
      if (data.status === 'partial') {
        const err = data.error_message ? ` 原因：${data.error_message}` : ''
        feedback.value = {
          type: 'warn',
          text: `部分完成：本批已新增 ${n} 条，后续未跑完（常见：网络/上游超时或 Worker 超时）。${err}`.slice(0, 520),
        }
      } else {
        feedback.value = {
          type: n > 0 ? 'success' : 'info',
          text: n > 0 ? `完成：本批新增 ${n} 条链接` : '完成：本批无新增（可能已全部存在或上游无新作品）',
        }
      }
      return
    }
    if (data.status === 'failed') {
      feedback.value = {
        type: 'error',
        text: `失败：${data.error_message || '未知错误'}`,
      }
      return
    }
    await new Promise((r) => setTimeout(r, 500))
  }
  feedback.value = { type: 'warn', text: '等待超时，请稍后点击「刷新列表」查看任务状态' }
}

function isBatchRow(v: UserVideo): boolean {
  const tid = v.source_task_id
  return Boolean(tid && justFinishedTaskId.value && tid === justFinishedTaskId.value)
}

async function downloadExport(format: 'txt' | 'json' | 'xlsx') {
  feedback.value = null
  try {
    const u = selectedUniqueId.value.trim()
    const res = await api.get<Blob>('/videos/export', {
      params: {
        format,
        ...(u ? { unique_id: u } : {}),
      },
      responseType: 'blob',
    })
    const cd = (res.headers['content-disposition'] as string | undefined) ?? ''
    let filename = `douyin-links.${format}`
    const m = cd.match(/filename="([^"]+)"/)
    if (m?.[1]) filename = m[1]
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.rel = 'noopener'
    a.click()
    URL.revokeObjectURL(url)
    feedback.value = { type: 'success', text: `已下载 ${filename}` }
    setTimeout(() => {
      if (feedback.value?.text?.startsWith('已下载')) feedback.value = null
    }, 2500)
  } catch {
    feedback.value = { type: 'error', text: '导出失败，请重新登录后重试' }
  }
}

async function copyUrl(url: string) {
  try {
    await navigator.clipboard.writeText(url)
    feedback.value = { type: 'success', text: '链接已复制到剪贴板' }
    setTimeout(() => {
      if (feedback.value?.text === '链接已复制到剪贴板') feedback.value = null
    }, 2000)
  } catch {
    feedback.value = { type: 'error', text: '复制失败，请手动选择链接复制' }
  }
}

function taskRowDeletable(t: SyncTask): boolean {
  return t.status !== 'pending' && t.status !== 'running'
}

function axiosDetailText(e: unknown): string | null {
  if (!isAxiosError(e)) return null
  const d = e.response?.data as { detail?: unknown } | undefined
  if (d?.detail == null) return null
  const detail = d.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((x) =>
        typeof x === 'object' && x !== null && 'msg' in x ? String((x as { msg: string }).msg) : String(x),
      )
      .join('；')
  }
  return JSON.stringify(detail)
}

async function deleteTaskRow(t: SyncTask) {
  if (!taskRowDeletable(t) || deletingTaskId.value) return
  if (
    !window.confirm('确定删除该条同步任务记录？已采集链接仍会保留，可在右侧列表继续查看或导出。')
  ) {
    return
  }
  deletingTaskId.value = t.id
  feedback.value = null
  try {
    await api.delete(`/tasks/${t.id}`)
    feedback.value = { type: 'success', text: '任务记录已删除' }
    await refresh({ quiet: true })
  } catch (e: unknown) {
    const msg = axiosDetailText(e)
    feedback.value = { type: 'error', text: msg?.slice(0, 500) ?? '删除失败，请稍后重试' }
  } finally {
    deletingTaskId.value = null
  }
}

async function deleteSelectedIdentifierData() {
  const uid = selectedUniqueId.value.trim()
  if (!uid || deletingIdentifier.value || busy.value || refreshing.value) return
  const preview = uid.length > 36 ? `${uid.slice(0, 36)}…` : uid
  if (
    !window.confirm(
      `确定删除用户标识「${preview}」下的全部已采集链接，以及本账号内与该标识相关的同步任务记录？此操作不可恢复。`,
    )
  ) {
    return
  }
  deletingIdentifier.value = true
  feedback.value = null
  try {
    const { data } = await api.delete<DeleteIdentifierResult>('/videos', {
      params: { unique_id: uid },
    })
    feedback.value = {
      type: 'success',
      text: `已删除链接 ${data.deleted_videos} 条、任务记录 ${data.deleted_tasks} 条`,
    }
    selectedUniqueId.value = ''
    videosPage.value = 1
    videosJumpDraft.value = ''
    await refresh({ quiet: true })
  } catch (e: unknown) {
    const msg = axiosDetailText(e)
    feedback.value = { type: 'error', text: msg?.slice(0, 500) ?? '删除失败，请稍后重试' }
  } finally {
    deletingIdentifier.value = false
  }
}

function logout() {
  localStorage.removeItem('access_token')
  void router.push('/login')
}

const feedbackClass = computed(() => {
  const t = feedback.value?.type
  if (t === 'success') return 'feedback feedback--success'
  if (t === 'error') return 'feedback feedback--error'
  if (t === 'warn') return 'feedback feedback--warn'
  return 'feedback feedback--info'
})

onMounted(() => {
  void loadPublicConfig()
  void refresh({ quiet: true })
})
</script>

<template>
  <div class="layout">
    <main class="main">
      <div class="main-toolbar">
        <h1 class="main-toolbar__title">抖音主页链接同步</h1>
        <button type="button" class="btn btn--ghost btn--toolbar" @click="logout">
          <svg class="btn__icon" width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M10 17H5V7h5M14 7h5v10h-5M10 12h8"
              stroke="currentColor"
              stroke-width="1.75"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          退出
        </button>
      </div>

      <div v-if="demoMode" class="banner-demo" role="alert">
        <strong>演示模式（Mock）</strong>
        <p>{{ demoExplain }}</p>
      </div>

      <section class="panel" aria-labelledby="sync-heading">
        <div class="panel__head">
          <h2 id="sync-heading" class="panel__title">新建同步</h2>
        </div>
        <p class="hint">
          可直接粘贴浏览器地址栏里的<strong>完整主页链接</strong>（含
          <code class="inline-code">https://www.douyin.com/user/…?…</code>
          ），失焦或开始同步时会自动截取
          <code class="inline-code">/user/</code>
          与
          <code class="inline-code">?</code>
          之间的用户标识。也可只填那一段（常为
          <code class="inline-code">MS4wLjABAAAA…</code>
          ）。与页内「抖音号」数字不一定相同。每批最多新增 100 条；同一用户下已存在的作品会自动去重。
          <template v-if="demoMode">
            <strong class="warn">当前为假数据</strong>
            ：链接无法在抖音打开。
          </template>
        </p>
        <div class="form-row">
          <div class="field">
            <label class="field__label" for="sync-uid-input">主页用户标识</label>
            <input
              id="sync-uid-input"
              v-model="uniqueId"
              type="text"
              name="unique_id"
              autocomplete="off"
              placeholder="粘贴完整主页链接，或仅填 MS4wLjABAAAA…"
              :disabled="busy"
              class="field__input"
              @paste="onSyncUidPaste"
              @blur="onSyncUidBlur"
            />
          </div>
          <div class="form-row__actions">
            <button type="button" class="btn btn--primary" :disabled="busy" @click="startSync">
              <span v-if="busy" class="spinner" aria-hidden="true" />
              {{ busy ? '处理中…' : '开始同步' }}
            </button>
            <button
              type="button"
              class="btn btn--ghost"
              :disabled="busy || refreshing"
              :aria-busy="refreshing"
              title="从服务器重新加载：最近任务表、当前页的已采集链接、用户标识筛选下拉与数量统计（不会发起新的同步任务）"
              @click="void refresh()"
            >
              <span v-if="refreshing" class="spinner spinner--ghost" aria-hidden="true" />
              <svg
                v-else
                class="btn__icon"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M4 12a8 8 0 0 1 14.5-4M20 12a8 8 0 0 1-14.5 4"
                  stroke="currentColor"
                  stroke-width="1.75"
                  stroke-linecap="round"
                />
                <path d="M18 4v4h-4M6 20v-4h4" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" />
              </svg>
              {{ refreshing ? '刷新中…' : '刷新列表' }}
            </button>
          </div>
        </div>
        <div
          v-if="feedback"
          :class="feedbackClass"
          role="status"
          aria-live="polite"
        >
          {{ feedback.text }}
        </div>
      </section>

      <div class="workspace">
      <section class="panel panel--workspace" aria-labelledby="tasks-heading">
        <div class="panel__head">
          <h2 id="tasks-heading" class="panel__title">最近任务</h2>
        </div>
        <div class="panel__scroll">
          <div v-if="tasks.length" class="table-scroll">
            <table class="data-table">
              <caption class="sr-only">
                最近同步任务：时间、用户标识（点击可复制）、状态、新增条数与删除记录操作
              </caption>
              <thead>
                <tr>
                  <th scope="col">时间</th>
                  <th scope="col">用户标识</th>
                  <th scope="col">状态</th>
                  <th scope="col" class="num">新增</th>
                  <th scope="col" class="col-actions"><span class="sr-only">操作</span></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="t in tasks" :key="t.id">
                  <td class="mono muted">{{ formatTaskCreatedAt(t.created_at) }}</td>
                  <td class="td-uid">
                    <span
                      class="mono cell-clip td-uid__click"
                      role="button"
                      tabindex="0"
                      :title="'点击复制：' + t.unique_id"
                      @click="copyPlain(t.unique_id, '用户标识已复制')"
                      @keydown.enter.prevent="copyPlain(t.unique_id, '用户标识已复制')"
                    >{{ t.unique_id }}</span>
                  </td>
                  <td>
                    <span :class="statusClass(t.status)" :title="taskStatusTitle(t)">{{ statusLabel(t.status) }}</span>
                  </td>
                  <td class="num mono">{{ t.new_links_count }}</td>
                  <td class="table-actions">
                    <button
                      type="button"
                      class="btn btn--sm btn--ghost btn--danger"
                      :disabled="deletingTaskId !== null || deletingIdentifier || !taskRowDeletable(t)"
                      :title="
                        taskRowDeletable(t)
                          ? '删除该任务记录（不影响已采集链接）'
                          : '排队中或同步中的任务不可删除'
                      "
                      @click="deleteTaskRow(t)"
                    >
                      {{ deletingTaskId === t.id ? '删除中…' : '删除' }}
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="empty">暂无任务</p>
        </div>

        <nav v-if="tasksTotal > 0" class="pager" aria-label="最近任务分页">
          <div class="pager__row pager__row--main">
            <button
              type="button"
              class="btn btn--sm btn--ghost"
              :disabled="tasksPage <= 1"
              @click="prevTasksPage"
            >
              上一页
            </button>
            <span class="pager__info mono">
              第 {{ tasksPage }} / {{ tasksTotalPages }} 页，共 {{ tasksTotal }} 条，每页 {{ tasksPageSize }} 条
            </span>
            <button
              type="button"
              class="btn btn--sm btn--ghost"
              :disabled="tasksPage >= tasksTotalPages"
              @click="nextTasksPage"
            >
              下一页
            </button>
          </div>
          <div class="pager__row pager__row--jump">
            <label class="pager__jump-label" for="tasks-jump-input">跳转</label>
            <input
              id="tasks-jump-input"
              v-model="tasksJumpDraft"
              type="text"
              inputmode="numeric"
              autocomplete="off"
              class="pager__jump-input mono"
              placeholder="页码"
              @keydown.enter.prevent="goTasksPage"
            />
            <button type="button" class="btn btn--sm btn--ghost pager__jump-btn" @click.prevent="goTasksPage">确定</button>
          </div>
        </nav>
      </section>

      <section class="panel panel--workspace" aria-labelledby="videos-heading">
        <div class="panel__head panel__head--split">
          <h2 id="videos-heading" class="panel__title">已采集链接</h2>
          <div v-if="videosTotal > 0" class="export-bar" role="group" aria-label="导出">
            <button type="button" class="btn btn--sm btn--ghost" @click="downloadExport('xlsx')">导出 XLSX</button>
            <button type="button" class="btn btn--sm btn--ghost" @click="downloadExport('txt')">导出 TXT</button>
            <button type="button" class="btn btn--sm btn--ghost" @click="downloadExport('json')">导出 JSON</button>
          </div>
        </div>

        <div class="videos-scope">
          <label class="videos-scope__label" for="uid-scope">已采集用户标识</label>
          <select
            id="uid-scope"
            v-model="selectedUniqueId"
            class="videos-scope__select"
            @change="onUidFilterChange"
          >
            <option value="">全部</option>
            <option v-for="o in identifierOptions" :key="o.unique_id" :value="o.unique_id">
              {{ o.unique_id.length > 32 ? `${o.unique_id.slice(0, 32)}…` : o.unique_id }}（{{ o.video_count }} 条）
            </option>
          </select>
          <div class="videos-scope__foot">
            <span class="videos-scope__hint">筛选下方链接列表与导出范围。</span>
            <button
              v-if="selectedUniqueId.trim()"
              type="button"
              class="btn btn--sm btn--ghost btn--danger videos-scope__purge"
              :disabled="deletingIdentifier || deletingTaskId !== null || busy || refreshing"
              title="删除当前所选用户标识下的全部已采集链接及本账号内相关同步任务记录（不可恢复）"
              @click="deleteSelectedIdentifierData"
            >
              {{ deletingIdentifier ? '删除中…' : '删除该标识全部数据' }}
            </button>
          </div>
        </div>

        <div class="panel__scroll panel__scroll--videos">
        <ul v-if="videos.length" class="video-list">
          <li
            v-for="v in videos"
            :key="v.aweme_id + v.share_url"
            :class="['video-card', { 'video-card--batch': isBatchRow(v) }]"
          >
            <div class="video-card__meta">
              <div class="video-card__left">
                <span v-if="isBatchRow(v)" class="badge badge--batch">本批</span>
                <span class="video-card__field-label">用户标识</span>
                <span class="mono video-card__uid-value" :title="v.unique_id">{{ v.unique_id }}</span>
              </div>
              <button type="button" class="btn btn--sm btn--ghost" @click="copyUrl(v.share_url)">复制</button>
            </div>
            <a
              class="video-card__link"
              :href="v.share_url"
              :title="v.share_url"
              target="_blank"
              rel="noopener noreferrer"
            >{{ v.share_url }}</a>
          </li>
        </ul>
        <p v-else class="empty">暂无数据，请先发起同步或切换页码</p>
        </div>

        <nav v-if="videosTotal > 0" class="pager" aria-label="已采集链接分页">
          <div class="pager__row pager__row--main">
            <button
              type="button"
              class="btn btn--sm btn--ghost"
              :disabled="videosPage <= 1"
              @click="prevVideosPage"
            >
              上一页
            </button>
            <span class="pager__info mono">
              第 {{ videosPage }} / {{ videosTotalPages }} 页，共 {{ videosTotal }} 条，每页 {{ videosPageSize }} 条
            </span>
            <button
              type="button"
              class="btn btn--sm btn--ghost"
              :disabled="videosPage >= videosTotalPages"
              @click="nextVideosPage"
            >
              下一页
            </button>
          </div>
          <div class="pager__row pager__row--jump">
            <label class="pager__jump-label" for="videos-jump-input">跳转</label>
            <input
              id="videos-jump-input"
              v-model="videosJumpDraft"
              type="text"
              inputmode="numeric"
              autocomplete="off"
              class="pager__jump-input mono"
              placeholder="页码"
              @keydown.enter.prevent="goVideosPage"
            />
            <button type="button" class="btn btn--sm btn--ghost pager__jump-btn" @click.prevent="goVideosPage">确定</button>
          </div>
        </nav>
      </section>
      </div>
    </main>
  </div>
</template>

<style scoped>
.layout {
  min-height: 100dvh;
  background: var(--color-bg);
  color: var(--color-text);
}

.main {
  max-width: 72rem;
  margin: 0 auto;
  padding: 1rem 1.25rem 2.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  width: 100%;
}

.main-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.main-toolbar__title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--color-text);
}

.btn--toolbar {
  flex-shrink: 0;
}

.videos-scope {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  padding: 0.6rem 0.75rem;
  margin-bottom: 0.65rem;
  background: #f8fafc;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.videos-scope__label {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text);
}

.videos-scope__select {
  flex: 1;
  min-width: min(100%, 14rem);
  max-width: 100%;
  padding: 0.4rem 0.55rem;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  font-family: var(--font-mono);
  background: #fff;
}

.videos-scope__hint {
  flex: 1 1 12rem;
  font-size: 0.72rem;
  color: var(--color-text-muted);
  line-height: 1.35;
}

.videos-scope__foot {
  flex: 1 1 100%;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 0.75rem;
}

.videos-scope__purge {
  flex-shrink: 0;
}

.pager {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.55rem;
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--color-border);
  flex-shrink: 0;
  width: 100%;
  min-width: 0;
}

.pager__row--main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 0.5rem 0.65rem;
  width: 100%;
}

.pager__row--main > .btn {
  flex-shrink: 0;
}

.pager__row--main .pager__info {
  flex: 1 1 10rem;
  min-width: 0;
  max-width: 100%;
  font-size: 0.75rem;
  color: var(--color-text-muted);
  text-align: center;
  line-height: 1.45;
  white-space: normal;
  word-break: break-word;
}

.pager__row--jump {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 0.45rem 0.55rem;
  width: 100%;
}

.pager__jump-label {
  flex-shrink: 0;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-muted);
  white-space: nowrap;
}

.pager__jump-input {
  box-sizing: border-box;
  width: 3.5rem;
  min-width: 3rem;
  padding: 0.3rem 0.45rem;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  line-height: 1.25;
  background: #fff;
  color: var(--color-text);
  min-height: calc(0.75rem * 1.25 + 0.6rem);
}

.pager__jump-btn {
  flex-shrink: 0;
}

.pager__jump-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px rgb(30 64 175 / 0.12);
}

.workspace {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.25rem;
  /* 两列同高，卡片大小统一 */
  align-items: stretch;
}

@media (max-width: 960px) {
  .workspace {
    grid-template-columns: 1fr;
  }
}

.panel--workspace {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* 中间区域占满两栏对齐后的剩余高度，分页贴底；内容多时在区内滚动 */
.panel--workspace .panel__scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}

.panel__scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.panel__scroll--videos .video-list {
  max-height: none;
}

.banner-demo {
  background: var(--color-warn-bg);
  border: 1px solid #fdba74;
  border-radius: var(--radius-md);
  padding: 1rem 1.25rem;
  color: var(--color-warn);
  font-size: 0.875rem;
}

.banner-demo p {
  margin: 0.5rem 0 0;
  line-height: 1.55;
}

.warn {
  color: #c2410c;
}

.panel {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 1.25rem 1.5rem;
  box-shadow: var(--shadow-sm);
  transition: border-color var(--transition-base), box-shadow var(--transition-base);
}

.panel:hover {
  border-color: var(--color-border-strong);
}

.panel__head {
  margin-bottom: 0.75rem;
}

.panel__head--split {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.export-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.td-uid {
  vertical-align: middle;
}

.td-uid__click {
  display: inline-block;
  max-width: 9rem;
  cursor: pointer;
  color: var(--color-primary);
  text-decoration: underline;
  text-decoration-style: dashed;
  text-underline-offset: 3px;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast), color var(--transition-fast);
}

.td-uid__click:hover {
  color: var(--color-primary-hover);
  background: rgb(30 64 175 / 0.06);
}

.td-uid__click:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

@media (min-width: 1100px) {
  .td-uid__click {
    max-width: 13rem;
  }
}

.data-table .td-uid__click {
  max-width: 100%;
  width: 100%;
}

.panel__title {
  margin: 0;
  font-size: 1.0625rem;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.hint {
  margin: 0 0 1rem;
  font-size: 0.875rem;
  color: var(--color-text-muted);
  line-height: 1.6;
}

.inline-code {
  font-family: var(--font-mono);
  font-size: 0.8125em;
  background: #f1f5f9;
  padding: 0.1em 0.35em;
  border-radius: var(--radius-sm);
  color: var(--color-text);
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

@media (min-width: 720px) {
  .form-row {
    flex-direction: row;
    align-items: flex-end;
    flex-wrap: wrap;
  }
}

.field {
  flex: 1;
  min-width: min(100%, 16rem);
}

.field__label {
  display: block;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 0.375rem;
}

.field__input {
  width: 100%;
  padding: 0.6rem 0.85rem;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  font-size: 0.9375rem;
  font-family: var(--font-mono);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.field__input:hover:not(:disabled) {
  border-color: #94a3b8;
}

.field__input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgb(30 64 175 / 0.15);
}

.field__input:disabled {
  opacity: 0.65;
  cursor: not-allowed;
  background: #f8fafc;
}

.form-row__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  padding: 0.55rem 1rem;
  border-radius: var(--radius-md);
  font-weight: 600;
  font-size: 0.875rem;
  font-family: inherit;
  cursor: pointer;
  border: 1px solid transparent;
  transition:
    background var(--transition-base),
    color var(--transition-base),
    border-color var(--transition-base),
    box-shadow var(--transition-base);
}

.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn__icon {
  flex-shrink: 0;
}

.btn--primary {
  background: var(--color-primary);
  color: #fff;
}

.btn--primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn--primary:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.btn--ghost {
  background: transparent;
  color: #334155;
  border-color: var(--color-border-strong);
}

.btn--ghost:hover:not(:disabled) {
  background: #f8fafc;
  border-color: #94a3b8;
}

.btn--ghost:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.btn--danger {
  color: var(--color-danger);
}

.btn--danger:hover:not(:disabled) {
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.btn--danger:focus-visible {
  outline: 2px solid var(--color-danger);
  outline-offset: 2px;
}

.btn--sm {
  padding: 0.3rem 0.55rem;
  font-size: 0.75rem;
}

.spinner {
  width: 1rem;
  height: 1rem;
  border: 2px solid rgb(255 255 255 / 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.65s linear infinite;
}

.spinner--ghost {
  border-color: rgb(51 65 85 / 0.25);
  border-top-color: #334155;
}

@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
    border-top-color: #fff;
  }

  .spinner--ghost {
    border-top-color: #334155;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.feedback {
  margin-top: 1rem;
  padding: 0.65rem 0.85rem;
  border-radius: var(--radius-md);
  font-size: 0.875rem;
  line-height: 1.5;
}

.feedback--info {
  background: #eff6ff;
  color: #1e40af;
  border: 1px solid #bfdbfe;
}

.feedback--success {
  background: var(--color-success-bg);
  color: var(--color-success);
  border: 1px solid #6ee7b7;
}

.feedback--error {
  background: var(--color-danger-bg);
  color: var(--color-danger);
  border: 1px solid #fecaca;
}

.feedback--warn {
  background: var(--color-warn-bg);
  color: var(--color-warn);
  border: 1px solid #fdba74;
}

.table-scroll {
  overflow-x: auto;
  margin: 0 -0.25rem;
  padding: 0 0.25rem;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8125rem;
  table-layout: fixed;
}

.data-table th,
.data-table td {
  text-align: left;
  padding: 0.65rem 0.75rem;
  border-bottom: 1px solid var(--color-border);
  vertical-align: middle;
}

.data-table th:first-child,
.data-table td:first-child {
  width: 10.5rem;
  padding-left: 0.35rem;
  padding-right: 1rem;
  white-space: nowrap;
}

.data-table th:nth-child(2),
.data-table td:nth-child(2) {
  padding-left: 0.5rem;
  padding-right: 1.1rem;
  overflow: hidden;
}

.data-table th:nth-child(3),
.data-table td:nth-child(3) {
  width: 5.5rem;
  padding-left: 0.5rem;
  padding-right: 1rem;
  white-space: nowrap;
}

.data-table th:nth-child(4),
.data-table td:nth-child(4) {
  width: 3.75rem;
  padding-left: 0.75rem;
  padding-right: 0.5rem;
}

.data-table th:nth-child(5),
.data-table td:nth-child(5) {
  width: 4.25rem;
  padding-left: 0.35rem;
  padding-right: 0.35rem;
  text-align: right;
  vertical-align: middle;
}

.table-actions {
  white-space: nowrap;
}

.col-actions {
  width: 4.25rem;
}

.data-table th {
  font-weight: 600;
  color: var(--color-text-muted);
  white-space: nowrap;
}

.data-table tbody tr {
  transition: background var(--transition-fast);
}

.data-table tbody tr:hover {
  background: #f8fafc;
}

.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.cell-clip {
  max-width: 14rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mono {
  font-family: var(--font-mono);
}

.muted {
  color: var(--color-text-muted);
}

.badge {
  display: inline-flex;
  align-items: center;
  padding: 0.2rem 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
}

.badge--muted {
  background: #f1f5f9;
  color: #475569;
}

.badge--run {
  background: #dbeafe;
  color: #1d4ed8;
}

.badge--ok {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.badge--partial {
  background: #fff7ed;
  color: #9a3412;
  border: 1px solid #fdba74;
}

.badge--batch {
  margin-right: 0.35rem;
  background: #dbeafe;
  color: #1e40af;
  font-size: 0.65rem;
  padding: 0.12rem 0.4rem;
}

.badge--err {
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.empty {
  margin: 0;
  color: #94a3b8;
  font-size: 0.875rem;
}

.video-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.video-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 0.65rem 0.85rem;
  background: #fafbfc;
  transition: border-color var(--transition-fast);
}

.video-card:hover {
  border-color: var(--color-border-strong);
}

.video-card--batch {
  border-color: #93c5fd;
  background: linear-gradient(180deg, #f0f7ff 0%, #fafbfc 100%);
  box-shadow: 0 0 0 1px rgb(59 130 246 / 0.12);
}

.video-card__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.45rem;
}

.video-card__left {
  display: flex;
  align-items: center;
  min-width: 0;
  flex: 1;
  gap: 0.35rem;
}

.video-card__field-label {
  flex-shrink: 0;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-muted);
}

.video-card__uid-value {
  min-width: 0;
  flex: 1;
  font-size: 0.75rem;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.video-card__link {
  display: block;
  font-size: 0.8125rem;
  color: var(--color-primary);
  line-height: 1.45;
  text-decoration: none;
  border-radius: var(--radius-sm);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.video-card__link:hover {
  text-decoration: underline;
}

.video-card__link:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
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
