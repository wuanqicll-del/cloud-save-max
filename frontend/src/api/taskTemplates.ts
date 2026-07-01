import { http } from './http'

export interface TaskTemplate {
  id: number
  name: string
  config: Record<string, any>
  created_at?: string
  updated_at?: string
}

export async function fetchTaskTemplates() {
  const { data } = await http.get<TaskTemplate[]>('/task-templates')
  return data
}

export async function createTaskTemplate(payload: { name: string; config: Record<string, any> }) {
  const { data } = await http.post<TaskTemplate>('/task-templates', payload)
  return data
}

export async function updateTaskTemplate(id: number, payload: { name?: string; config?: Record<string, any> }) {
  const { data } = await http.patch<TaskTemplate>(`/task-templates/${id}`, payload)
  return data
}

export async function deleteTaskTemplate(id: number) {
  const { data } = await http.delete(`/task-templates/${id}`)
  return data
}
