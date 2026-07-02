import { http } from '@/api/http'
import type { AuditLogListResponse } from '@/types/audit'

export async function fetchAuditLogs(params: {
  page: number
  page_size: number
  q?: string
  action?: string
  success?: boolean
}) {
  const { data } = await http.get<AuditLogListResponse>('/audit-logs', { params })
  return data
}

export async function deleteAllAuditLogs() {
  const { data } = await http.delete('/audit-logs')
  return data
}

export async function fetchAuditLogScheduler() {
  const { data } = await http.get('/audit-logs/scheduler')
  return data
}

export async function updateAuditLogScheduler(payload: {
  enabled?: boolean
  crontab?: string
  timezone?: string
  retention_days?: number
}) {
  const { data } = await http.patch('/audit-logs/scheduler', payload)
  return data
}

