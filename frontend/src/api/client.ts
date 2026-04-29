import axios from 'axios'

const baseURL = import.meta.env.VITE_API_BASE || ''

export const api = axios.create({
  baseURL,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

export function currentNextPath(): string {
  return window.location.pathname + window.location.search + window.location.hash
}

export function goToAbLogin(mode: 'login' | 'register' = 'login') {
  const endpoint = mode === 'register' ? '/auth/register' : '/auth/login'
  const next = encodeURIComponent(currentNextPath())
  window.location.href = `${baseURL}${endpoint}?next=${next}`
}

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
