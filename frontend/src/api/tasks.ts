import { http } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import type {
  DriveBrowseResponse,
  MagicRegexResponse,
  SharePreviewBatchResponse,
  SharePreviewResponse,
  StopCompletedDramaTasksResponse,
  TaskExecutionItem,
  TaskItem,
  TaskSchedulerSetting,
} from '@/types/tasks'
import { detectDriveTypeByUrl } from '@/utils/driveType'

export async function fetchTasks() {
  const { data } = await http.get<TaskItem[]>('/tasks')
  return data
}

export async function syncDramaSavepathSnapshots() {
  const { data } = await http.post('/tasks/drama/savepath-snapshots/sync')
  return data
}

export async function syncSingleSavepathSnapshot(taskId: number) {
  const { data } = await http.post(`/tasks/${taskId}/savepath-snapshot/sync`)
  return data
}

export async function createTask(payload: {
  task_uid?: string | null
  task_type: string
  taskname: string
  shareurl: string
  savepath: string
  sync_task_uids?: string[]
  pattern?: string | null
  replace?: string | null
  ignore_extension?: boolean
  account_name?: string | null
  tmdb_id?: number | null
  tmdb_media_type?: string | null
  enabled?: boolean
  addition?: Record<string, any>
  extra?: Record<string, any>
}) {
  const { data } = await http.post<TaskItem>('/tasks', payload, { headers: { 'X-Silent-Toast': '1' } })
  return data
}

export async function updateTask(
  taskId: number,
  payload: Partial<{
    task_type: string
    taskname: string
    shareurl: string
    savepath: string
    sync_task_uids: string[]
    pattern: string | null
    replace: string | null
    ignore_extension: boolean
    account_name: string | null
    tmdb_id: number | null
    tmdb_media_type: string | null
    enabled: boolean
    addition: Record<string, any>
    extra: Record<string, any>
  }>,
) {
  const { data } = await http.patch<TaskItem>(`/tasks/${taskId}`, payload, { headers: { 'X-Silent-Toast': '1' } })
  return data
}

export async function setTaskStatus(taskId: number, enabled: boolean) {
  const { data } = await http.patch<TaskItem>(`/tasks/${taskId}/status`, { enabled })
  return data
}

export async function runTask(taskId: number) {
  const { data } = await http.post<TaskExecutionItem>(`/tasks/${taskId}/run`)
  return data
}

export async function deleteTask(taskId: number) {
  const { data } = await http.delete<{ ok: boolean }>(`/tasks/${taskId}`)
  return data
}

export async function fetchTaskSchedulerSetting() {
  const { data } = await http.get<TaskSchedulerSetting>('/tasks/scheduler')
  return data
}

export async function fetchMagicRegex() {
  const { data } = await http.get<MagicRegexResponse>('/tasks/magic-regex')
  return data
}

export async function updateTaskSchedulerSetting(payload: Partial<TaskSchedulerSetting>) {
  const { data } = await http.patch<TaskSchedulerSetting>('/tasks/scheduler', payload)
  return data
}

export async function previewShare(payload: {
  shareurl: string
  account_name?: string | null
  pdir_fid?: string | null
  max_items?: number
  taskname?: string
  pattern?: string | null
  replace?: string | null
  savepath?: string | null
  ignore_extension?: boolean | null
  min_size?: string | null
  filter_words?: string | null
  file_filter?: string | null
  file_filter_mode?: string | null
  file_min_date?: string | null
  dir_min_date?: string | null
  folder_filter?: string | null
  folder_exclude?: string | null
  folder_filter_mode?: string | null
  folder_exclude_mode?: string | null
  folder_priority?: string | null
  folder_priority_mode?: string | null
  tmdb_id?: number | null
  tmdb_media_type?: string | null
}) {
  const { data } = await http.post<SharePreviewResponse>('/tasks/share/preview', payload)
  return data
}

export async function previewShareBatch(payload: { shareurls: string[]; account_name?: string | null }) {
  const accountName = payload.account_name ?? null
  const shareurls = (payload.shareurls || []).map((x) => String(x || '').trim()).filter(Boolean)
  if (!shareurls.length) return { items: [] }
  const limit = 50

  const postOnce = async (batch: string[]) => {
    const { data } = await http.post<SharePreviewBatchResponse>(
      '/tasks/share/preview-batch',
      { shareurls: batch, account_name: accountName },
      { headers: { 'X-Retryable': '1' } },
    )
    return data
  }

  const chunk = <T,>(items: T[], size: number) => {
    const out: T[][] = []
    for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size))
    return out
  }

  const mergeByInputOrder = (items: SharePreviewBatchResponse['items']) => {
    const mapping = new Map<string, (typeof items)[number]>()
    for (const it of items || []) {
      const url = String((it as any)?.shareurl || '').trim()
      if (!url || mapping.has(url)) continue
      mapping.set(url, it)
    }
    const ordered: (typeof items)[number][] = []
    for (const url of shareurls) {
      const it = mapping.get(url)
      if (it) ordered.push(it)
    }
    return ordered
  }

  if (shareurls.length <= limit) {
    const out = await postOnce(shareurls)
    return { items: mergeByInputOrder(out.items || []) }
  }

  if (accountName) {
    const merged: SharePreviewBatchResponse['items'] = []
    for (const part of chunk(shareurls, limit)) {
      const out = await postOnce(part)
      merged.push(...(out.items || []))
    }
    return { items: mergeByInputOrder(merged) }
  }

  const groups = new Map<string, string[]>()
  for (const url of shareurls) {
    const dt = detectDriveTypeByUrl(url) || 'unknown'
    const list = groups.get(dt) || []
    list.push(url)
    groups.set(dt, list)
  }

  const all = await Promise.all(
    [...groups.values()].map(async (urls) => {
      const merged: SharePreviewBatchResponse['items'] = []
      for (const part of chunk(urls, limit)) {
        const out = await postOnce(part)
        merged.push(...(out.items || []))
      }
      return merged
    }),
  )

  return { items: mergeByInputOrder(all.flat()) }
}

export async function browseDrive(payload: { dir_path: string; account_name?: string | null; shareurl?: string | null; max_items?: number }) {
  const { data } = await http.post<DriveBrowseResponse>('/tasks/drive/browse', payload)
  return data
}

export async function mkdirDrive(payload: { dir_path: string; account_name?: string | null; shareurl?: string | null }) {
  const { data } = await http.post<{ account_name: string; dir_path: string; response: Record<string, any> }>('/tasks/drive/mkdir', payload)
  return data
}

export async function stopCompletedDramaTasks() {
  const { data } = await http.post<StopCompletedDramaTasksResponse>('/tasks/drama/stop-completed', null, {
    headers: { 'X-Silent-Toast': '1' },
  })
  return data
}

export async function validateShareLinks(shareurls: string[]) {
  const urls = (shareurls || []).map((x) => String(x || '').trim()).filter(Boolean)
  if (!urls.length) return { items: [] }
  const { data } = await http.post<{ items: Array<{ shareurl: string; ok: boolean; share_author_name?: string | null; message?: string | null }> }>(
    '/tasks/share/validate',
    { shareurls: urls },
    { headers: { 'X-Retryable': '1' } },
  )
  return data
}

export interface ValidateStreamItem {
  shareurl: string
  ok: boolean
  share_author_name?: string | null
  message?: string | null
}

export function validateShareLinksStream(
  shareurls: string[],
  onItem: (item: ValidateStreamItem) => void,
  onDone: () => void,
  onError: (err: Error) => void,
): AbortController {
  const controller = new AbortController()
  const urls = (shareurls || []).map((x) => String(x || '').trim()).filter(Boolean)
  if (!urls.length) {
    onDone()
    return controller
  }
  const base = (http.defaults?.baseURL || '').replace(/\/+$/, '')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const auth = useAuthStore()
  if (auth.accessToken) headers.Authorization = `Bearer ${auth.accessToken}`
  fetch(`${base}/tasks/share/validate_stream`, {
    method: 'POST',
    headers,
    credentials: 'include',
    body: JSON.stringify({ shareurls: urls }),
    signal: controller.signal,
  })
    .then(async (resp) => {
      if (!resp.ok) {
        onError(new Error(`HTTP ${resp.status}`))
        return
      }
      const reader = resp.body?.getReader()
      if (!reader) {
        onError(new Error('无法读取流'))
        return
      }
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data: ')) continue
          const payload = trimmed.slice(6)
          if (payload === '[DONE]') {
            onDone()
            return
          }
          try {
            const item = JSON.parse(payload) as ValidateStreamItem
            onItem(item)
          } catch {
            // 忽略解析错误
          }
        }
      }
      onDone()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') onError(err)
    })
  return controller
}
