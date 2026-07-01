export type SystemSettingOut = {
  preferred_sharers: string
  blocked_sharers: string
  validate_batch_size: number
  preview_cache_ttl_seconds: number
}

export type SystemSettingUpdateIn = {
  preferred_sharers?: string | null
  blocked_sharers?: string | null
  validate_batch_size?: number | null
  preview_cache_ttl_seconds?: number | null
}