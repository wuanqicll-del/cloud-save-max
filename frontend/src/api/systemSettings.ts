import { http } from '@/api/http'
import type { SystemSettingOut, SystemSettingUpdateIn } from '@/types/systemSettings'

export async function fetchSharerFilterSettings() {
  const { data } = await http.get<SystemSettingOut>('/system-settings/sharer-filter')
  return data
}

export async function updateSharerFilterSettings(payload: SystemSettingUpdateIn) {
  const { data } = await http.patch<SystemSettingOut>('/system-settings/sharer-filter', payload)
  return data
}

export type FilterWordRule = { name: string; keywords: string }

export async function fetchFilterRules() {
  const { data } = await http.get<{ rules: FilterWordRule[] }>('/system-settings/filter-rules')
  return data.rules || []
}

export async function saveFilterRules(rules: FilterWordRule[]) {
  const { data } = await http.put<{ rules: FilterWordRule[] }>('/system-settings/filter-rules', { rules })
  return data.rules || []
}