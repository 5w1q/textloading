import axios from 'axios'

const baseURL = import.meta.env.VITE_API_BASE || ''

export const api = axios.create({
  baseURL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

/** Ab 主站登录/注册页（与 sayhi-ab.asia 实际路由一致） */
export const AB_LOGIN_PATH = '/login.html'

export function buildAbLoginRedirectUrl(redirectAfterLogin: string): string {
  const ab = String(import.meta.env.VITE_AB_ORIGIN || 'https://sayhi-ab.asia').replace(/\/$/, '')
  return `${ab}${AB_LOGIN_PATH}?redirect=${encodeURIComponent(redirectAfterLogin)}`
}

function abLoginUrl(): string {
  return buildAbLoginRedirectUrl(window.location.href)
}

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

/** 登录 / 注册失败的 401 不应清 token、不应整页跳转，以免盖住表单错误提示 */
function isAuthSubmitUrl(url: string | undefined): boolean {
  if (!url) return false
  return url.includes('/auth/login') || url.includes('/auth/register')
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (!axios.isAxiosError(error) || error.response?.status !== 401) {
      return Promise.reject(error)
    }
    if (import.meta.env.VITE_USE_AB_LOGIN !== '0') {
      if (isAuthSubmitUrl(error.config?.url)) {
        return Promise.reject(error)
      }
      localStorage.removeItem('access_token')
      window.location.assign(abLoginUrl())
      return Promise.reject(error)
    }
    if (isAuthSubmitUrl(error.config?.url)) {
      return Promise.reject(error)
    }
    localStorage.removeItem('access_token')
    const path = window.location.pathname
    if (path.endsWith('/login') || path.endsWith('/register')) {
      return Promise.reject(error)
    }
    const rawBase = import.meta.env.BASE_URL || '/'
    const base = rawBase.endsWith('/') ? rawBase.slice(0, -1) : rawBase
    window.location.assign(`${base}/login?expired=1`)
    return Promise.reject(error)
  },
)

export type TaskStatus = 'pending' | 'running' | 'completed' | 'partial' | 'failed'

export interface SyncTask {
  id: string
  unique_id: string
  sec_uid: string | null
  cursor: string | null
  status: TaskStatus
  error_message: string | null
  new_links_count: number
  created_at: string
}

export interface UserVideo {
  aweme_id: string
  share_url: string
  unique_id: string
  sec_uid: string
  created_at: string
  /** 写入该条时对应的同步任务；用于区分「本批新增」 */
  source_task_id?: string | null
}

export interface VideosSummary {
  last_sync_unique_id: string | null
  last_sync_task_id: string | null
  last_sync_at: string | null
  last_sync_status: string | null
}

export interface UniqueIdRow {
  unique_id: string
  video_count: number
}

export interface DeleteIdentifierResult {
  deleted_videos: number
  deleted_tasks: number
}
