/**
 * 影巢任务 API
 */
import { http } from './http'

export interface HiveResource {
  item_id: number
  resource_id?: number
  title?: string
  media_type?: string
  tmdb_id?: string
  full_url?: string
  access_code?: string
  validate_status?: string
  uploader_name?: string
}

export interface HiveResourceListResponse {
  success: boolean
  data: HiveResource[]
  message?: string
}

export interface HiveStatusResponse {
  success: boolean
  data?: {
    logged_in: boolean
    cid: boolean
    playlist_uuid?: string
    playlist_title?: string
    check_interval?: number
    last_checked_at?: string
    auto_login_enabled?: boolean
  }
}

/**
 * 获取HDHive服务状态
 */
export async function getHiveStatus(): Promise<HiveStatusResponse> {
  const { data } = await http.get('/hive/status')
  return data
}

/**
 * 获取HDHive片单资源列表
 */
export async function getHiveResources(): Promise<HiveResourceListResponse> {
  const { data } = await http.get('/hive/resources')
  return data
}

/**
 * 触发HDHive更新资源
 */
export async function updateHiveResources(): Promise<{ success: boolean; data?: any }> {
  const { data } = await http.post('/hive/update')
  return data
}

/**
 * 获取单个HDHive资源详情
 */
export async function getHiveResource(itemId: number): Promise<{ success: boolean; data?: HiveResource }> {
  const { data } = await http.get(`/hive/resource/${itemId}`)
  return data
}
