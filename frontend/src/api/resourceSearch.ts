import { http } from '@/api/http'
import type { ResourceSearchSourceKey, ResourceSearchSourceListResponse, TaskSuggestionResponse } from '@/types/resourceSearch'

export async function fetchResourceSearchSources() {
  const { data } = await http.get<ResourceSearchSourceListResponse>('/resource-search/sources')
  return data
}

export async function patchResourceSearchSource(key: ResourceSearchSourceKey, payload: Partial<{ enabled: boolean; server: string | null; username: string | null; password: string | null; token: string | null }>) {
  const { data } = await http.patch<ResourceSearchSourceListResponse>(`/resource-search/sources/${encodeURIComponent(key)}`, payload)
  return data
}

export async function fetchTaskSuggestions(q: string, d: number, drive_type?: string | null, search_filter?: string, search_exclude?: string, search_date_from?: string, search_filter_mode?: string, search_exclude_mode?: string, show_blocked?: boolean) {
  const params: any = { q, d }
  const dt = String(drive_type || '').trim()
  if (dt) params.drive_type = dt
  const sf = String(search_filter || '').trim()
  if (sf) params.sf = sf
  const se = String(search_exclude || '').trim()
  if (se) params.se = se
  const df = String(search_date_from || '').trim()
  if (df) params.df = df
  const sfm = String(search_filter_mode || '').trim()
  if (sfm) params.sfm = sfm
  const sem = String(search_exclude_mode || '').trim()
  if (sem) params.sem = sem
  if (show_blocked) params.show_blocked = true
  const { data } = await http.get<TaskSuggestionResponse>('/tasks/suggestions', { params, timeout: 60000 })
  return data
}

export async function fetchShareAuthor(shareurl: string) {
  const { data } = await http.get<{ author_name: string }>('/resource-search/share-author', { params: { shareurl }, timeout: 15000 })
  return data.author_name || ''
}
