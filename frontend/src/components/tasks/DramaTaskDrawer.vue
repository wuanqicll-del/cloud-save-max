<script setup lang="ts">
import { ElMessageBox } from 'element-plus'

import { fetchTMDBDetail, searchTMDB } from '@/api/media'
import { browseDrive, fetchMagicRegex, fetchTasks, mkdirDrive, previewShare, validateShareLinksStream } from '@/api/tasks'
import { fetchTMDBConfig } from '@/api/tmdb'
import { fetchTaskSuggestions } from '@/api/resourceSearch'
import { fetchSharerFilterSettings } from '@/api/systemSettings'
import { fetchTaskTemplates, createTaskTemplate } from '@/api/taskTemplates'
import type { TaskTemplate } from '@/api/taskTemplates'
import type { DriveAccountItem, PluginItem } from '@/types/extensions'
import type { TMDBBrief } from '@/types/media'
import type { TaskSuggestionItem } from '@/types/resourceSearch'
import type { SyncTaskItem } from '@/types/syncTasks'
import type { DriveBrowseItem, MagicRegexRule, SharePreviewItem, TaskItem } from '@/types/tasks'
import { detectDriveTypeByUrl } from '@/utils/driveType'
import { normalizeCloud189ShareUrl } from '@/utils/cloud189Share'
import { SYNC_WRITE } from '@/constants/permissions'
import { useAuthStore } from '@/stores/auth'

const TMDB_IMAGE_BASE = 'https://image.tmdb.org/t/p/w185'

type TaskSuggestionItemExt = TaskSuggestionItem & {
  pdir_fid?: string | null
  latest_video?: any | null
  max_video?: boolean
}

type TaskFormPayload = {
  task_type: string
  taskname: string
  shareurl: string
  savepath: string
  sync_task_uids?: string[]
  pattern?: string | null
  replace?: string | null
  ignore_extension: boolean
  account_name?: string | null
  tmdb_id?: number | null
  tmdb_media_type?: string | null
  enabled: boolean
  addition: Record<string, any>
  extra: Record<string, any>
}

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    task?: TaskItem | null
    accounts: DriveAccountItem[]
    plugins: PluginItem[]
    syncTasks?: SyncTaskItem[]
    submitting?: boolean
    presetTaskname?: string
    presetTmdb?: { tmdb_id: number; tmdb_media_type: 'movie' | 'tv' } | null
    autoDeepSuggest?: boolean
  }>(),
  {
    task: null,
    submitting: false,
    syncTasks: () => [],
    presetTaskname: '',
    presetTmdb: null,
    autoDeepSuggest: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  save: [payload: TaskFormPayload]
  'sync-created': []
}>()

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value ?? {}))
}

const isEditing = computed(() => Boolean(props.task?.id))

const state = reactive({
  taskname: '',
  shareurl: '',
  savepath: '',
  account_choice: '__AUTO__' as string,
  auto_update_shareurl: true,
  enabled: true,
  sync_task_uids: [] as string[],
  pattern: '' as string | null,
  replace: '' as string | null,
  ignore_extension: false,
  tmdb_id: null as number | null,
  tmdb_media_type: null as string | null,
  runweek_mode: 'manual' as 'auto' | 'manual',
  runweek: [1, 2, 3, 4, 5, 6, 7] as number[],
  addition: {} as Record<string, any>,
  extra: {} as Record<string, any>,
})

const manualRunweekBackup = ref([] as number[])
const autoRunweekDays = ref([] as number[])

const sharerFilterConfig = reactive({
  preferred: [] as string[],
  blocked: [] as string[],
  batchSize: 5,
})

const filterRuleOptions = ref<Array<{ name: string; keywords: string }>>([])
let filterRulesLoaded = false

async function ensureFilterRules() {
  if (filterRulesLoaded) return
  try {
    const { fetchFilterRules } = await import('@/api/systemSettings')
    filterRuleOptions.value = await fetchFilterRules()
  } catch { /* ignore */ }
  filterRulesLoaded = true
}

const auth = useAuthStore()
const canSyncWrite = computed(() => auth.permissions.includes(SYNC_WRITE))

const templateList = ref<TaskTemplate[]>([])
const selectedTemplateId = ref<number | null>(null)
const saveTemplateDialogVisible = ref(false)
const saveTemplateName = ref('')

const authorMenu = reactive({
  visible: false,
  x: 0,
  y: 0,
  item: null as TaskSuggestionItemExt | null,
})

const createSyncDialog = reactive({
  visible: false,
  submitting: false,
  name: '',
  mode: 'one_way' as string,
  sourceType: 'openlist',
  sourcePath: '',
  targetType: 'openlist',
  targetPath: '',
  overwrite: false,
  one_way_delete_extras: false,
  force_refresh: false,
})

// 暂存的同步任务（未保存到后端）
interface PendingSyncTask {
  tempUid: string
  name: string
  mode: string
  source: { type: string; path: string }
  target: { type: string; path: string }
  strategy: Record<string, any>
}
let pendingUidCounter = 0
const pendingSyncTasks = ref<PendingSyncTask[]>([])
// 编辑期间被移除的已保存同步任务标识
const removedSyncTaskUids = ref<string[]>([])

const syncPathPicker = reactive({
  visible: false,
  loading: false,
  target: 'source' as 'source' | 'target',
  endpointType: 'openlist' as 'openlist' | 'local',
  dirPath: '',
  paths: [] as any[],
  items: [] as any[],
})

const taskSuggestions = reactive({
  visible: false,
  loading: false,
  verifying: false,
  deep: 0 as 0 | 1,
  runId: 0,
  items: [] as TaskSuggestionItemExt[],
  hideTimer: null as any,
  searchTimer: null as any,
  focused: false,
  notice: '' as string,
  lastQuery: '' as string,
  lastDeep: 0 as 0 | 1,
  selectedItem: null as TaskSuggestionItemExt | null,
  _abortController: null as AbortController | null,
})

const tmdbLink = reactive({
  visible: false,
  loading: false,
  configured: true,
  type: 'tv' as 'movie' | 'tv',
  q: '' as string,
  year: '' as string,
  items: [] as TMDBBrief[],
  selectedId: 0,
  detailsById: {} as Record<number, any>,
  loadingById: {} as Record<number, boolean>,
})

const activeAccounts = computed(() => {
  return props.accounts.filter((item) => Boolean(item.enabled) && item.runtime_status === 'active')
})

// 是否设置了重命名规则（pattern和replace都有内容才算）
const hasRenameRule = computed(() => {
  return !!(String(state.pattern || '').trim() && String(state.replace || '').trim())
})

const showAutoUpdateToggle = computed(() => true)

const unavailableSelectedAccount = computed(() => {
  if (state.account_choice === '__AUTO__') return null
  const name = String(state.account_choice || '').trim()
  if (!name) return null
  if (activeAccounts.value.some((item) => item.name === name)) return null
  return props.accounts.find((item) => item.name === name) || { name, drive_type: '', enabled: false, runtime_status: null }
})

const unavailableSelectedAccountLabel = computed(() => {
  const item: any = unavailableSelectedAccount.value
  if (!item) return ''
  const driveType = item.drive_type ? `（${item.drive_type}）` : ''
  const status = item.enabled ? '不可用' : '已禁用'
  const rt = item.runtime_status ? String(item.runtime_status) : ''
  const suffix = rt ? `${status}/${rt}` : status
  return `${item.name}${driveType}（${suffix}）`
})

const newSyncTasks = ref<SyncTaskItem[]>([])

const sortedSyncTasks = computed(() => {
  const all: Array<{ uid: string; name: string; enabled?: boolean; drama_task_uids?: string[] }> = [...(props.syncTasks || [])]
  const existingUids = new Set(all.map((x) => x.uid))
  for (const t of newSyncTasks.value) {
    if (!existingUids.has(t.uid)) {
      all.push(t)
    }
  }
  // 暂存的同步任务也加入列表
  for (const p of pendingSyncTasks.value) {
    if (!existingUids.has(p.tempUid)) {
      all.push({ uid: p.tempUid, name: p.name, enabled: true })
    }
  }
  return all.sort((a, b) => String(a.name || '').localeCompare(String(b.name || '')))
})

// 当父组件列表已包含新任务时，自动清除临时列表
watch(() => props.syncTasks, (newVal) => {
  const existingUids = new Set((newVal || []).map((x: SyncTaskItem) => x.uid))
  const filtered = newSyncTasks.value.filter((t) => !existingUids.has(t.uid))
  if (filtered.length !== newSyncTasks.value.length) newSyncTasks.value = filtered
}, { deep: true })

// 重命名规则变化时，自动切换自动换链状态
watch(() => hasRenameRule.value, (hasRule) => {
  state.auto_update_shareurl = hasRule
})

const magicRegex = reactive({
  loading: false,
  selectedKey: '' as string,
  rules: [] as MagicRegexRule[],
})

const activeMagicRule = computed(() => {
  const key = String(state.pattern || '').trim()
  if (!key) return null
  return magicRegex.rules.find((r) => r.key === key) || null
})

const drivePicker = reactive({
  visible: false,
  loading: false,
  dirPath: '',
  pdir_fid: '' as string,
  drive_type: '' as string,
  paths: [] as Array<{ fid: string; name: string }>,
  items: [] as DriveBrowseItem[],
  sortBy: 'file_name' as 'file_name' | 'updated_at',
  sortOrder: 'asc' as 'asc' | 'desc',
  mobileSort: 'file_name:asc' as string,
})

const sharePicker = reactive({
  visible: false,
  loading: false,
  shareurl: '' as string,
  root_shareurl: '' as string,
  pdir_fid: null as string | null,
  stack: [] as Array<{ name: string; pdir_fid: string }>,
  items: [] as SharePreviewItem[],
  sharerName: '' as string,
  isPreferredSharer: false,
})

const shareAuto = reactive({
  timer: null as any,
  runId: 0,
  lastResolved: '' as string,
})

const autoFill = reactive({
  loading: false,
  text: '正在自动填写...',
  runId: 0,
})

const saveAuto = reactive({
  timer: null as any,
  applying: false,
  touched: false,
  lastApplied: '' as string,
  tasksLoading: false,
  tasks: null as TaskItem[] | null,
  tmdbDetailCache: {} as Record<string, any>,
})

const viewport = reactive({ width: window.innerWidth })
const isMobile = computed(() => viewport.width <= 768)
const shareDialogWidth = computed(() => (isMobile.value ? '96vw' : '1100px'))

function onResize() {
  viewport.width = window.innerWidth
}

onMounted(() => {
  window.addEventListener('resize', onResize, { passive: true })
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
})

function formatTs(value: any) {
  if (value === undefined || value === null || value === '') return ''
  const n = Number(value)
  const ts = Number.isFinite(n) ? (n < 1e12 ? n * 1000 : n) : Date.parse(String(value))
  if (!Number.isFinite(ts)) return String(value)
  const d = new Date(ts)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd} ${hh}:${mi}`
}

function formatSize(size: any) {
  const n = Number(size)
  if (!Number.isFinite(n) || n < 0) return ''
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = n
  let idx = 0
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024
    idx += 1
  }
  if (idx === 0) return `${Math.floor(value)} ${units[idx]}`
  return `${value.toFixed(value >= 10 ? 1 : 2)} ${units[idx]}`
}

function sanitizeSuggestionQuery(value: string) {
  return String(value || '')
    .replace(/\((19|20)\d{2}\)/g, '')
    .trim()
}

function showSuggestions() {
  if (taskSuggestions.hideTimer) {
    clearTimeout(taskSuggestions.hideTimer)
    taskSuggestions.hideTimer = null
  }
  taskSuggestions.focused = true
  taskSuggestions.visible = true
}

function hideSuggestionsLater() {
  if (taskSuggestions.hideTimer) clearTimeout(taskSuggestions.hideTimer)
  taskSuggestions.focused = false
  taskSuggestions.hideTimer = setTimeout(() => {
    // 如果有选中的搜索结果，不隐藏下拉，保持预览区可见
    if (taskSuggestions.selectedItem) return
    taskSuggestions.visible = false
  }, 180)
}

function resetSuggestions() {
  taskSuggestions.runId += 1
  taskSuggestions.visible = false
  taskSuggestions.loading = false
  taskSuggestions.verifying = false
  taskSuggestions.items = []
  taskSuggestions.focused = false
  taskSuggestions.notice = ''
  taskSuggestions.lastQuery = ''
  taskSuggestions.lastDeep = 0
  taskSuggestions.selectedItem = null
  if (taskSuggestions.hideTimer) {
    clearTimeout(taskSuggestions.hideTimer)
    taskSuggestions.hideTimer = null
  }
  if (taskSuggestions.searchTimer) {
    clearTimeout(taskSuggestions.searchTimer)
    taskSuggestions.searchTimer = null
  }
}

function tmdbBindLabel() {
  const id = Number(state.tmdb_id) || 0
  const mt = String(state.tmdb_media_type || '').toLowerCase()
  if (id > 0 && (mt === 'movie' || mt === 'tv')) return `${mt} #${id}`
  return ''
}

function normalizeWeekdays(value: any) {
  const arr = Array.isArray(value) ? value : []
  const days = arr.map((x) => Number(x)).filter((x) => x >= 1 && x <= 7)
  return Array.from(new Set(days)).sort((a, b) => a - b)
}

async function applyRunweekFromTmdbUpdateWeekdays(tmdbId: number, mediaType: 'movie' | 'tv') {
  if (!props.modelValue) return
  if (!tmdbLink.configured) return
  if (mediaType !== 'tv') return
  const id = Number(tmdbId) || 0
  if (id <= 0) return
  try {
    const res: any = await fetchTMDBDetail('tv', id)
    const days = normalizeWeekdays(res?.episode_weekdays || res?.update_weekdays)
    autoRunweekDays.value = days
  } catch {
    return
  }
}

function posterUrlFromTMDB(path?: string | null) {
  const p = String(path || '').trim()
  if (!p) return ''
  return `${TMDB_IMAGE_BASE}${p}`
}

async function ensureTmdbLinkDetail(id: number) {
  const tmdbId = Number(id) || 0
  if (tmdbId <= 0) return
  if (tmdbLink.detailsById[tmdbId]) return
  if (tmdbLink.loadingById[tmdbId]) return
  tmdbLink.loadingById[tmdbId] = true
  try {
    const data = await fetchTMDBDetail(tmdbLink.type, tmdbId)
    tmdbLink.detailsById[tmdbId] = data.data || {}
  } finally {
    tmdbLink.loadingById[tmdbId] = false
  }
}

function tvTotalEpisodesFromDetail(detail: any) {
  const n = detail?.number_of_episodes
  if (typeof n === 'number' && n > 0) return n
  const seasons = Array.isArray(detail?.seasons) ? detail.seasons : []
  const sum = seasons
    .filter((s: any) => s && typeof s === 'object' && Number(s.season_number) > 0)
    .reduce((acc: number, s: any) => acc + (Number(s.episode_count) || 0), 0)
  return sum > 0 ? sum : null
}

function tvAiredEpisodesFromDetail(detail: any, total: number | null) {
  const status = String(detail?.status || '').toLowerCase()
  if (status === 'ended' && typeof total === 'number' && total > 0) return total
  const last = detail?.last_episode_to_air
  if (!last || typeof last !== 'object') return null
  const seasonNumber = Number(last.season_number) || 0
  const episodeNumber = Number(last.episode_number) || 0
  if (seasonNumber <= 0 || episodeNumber <= 0) return null

  const seasons = Array.isArray(detail?.seasons) ? detail.seasons : []
  const prev = seasons
    .filter((s: any) => s && typeof s === 'object' && Number(s.season_number) > 0 && Number(s.season_number) < seasonNumber)
    .reduce((acc: number, s: any) => acc + (Number(s.episode_count) || 0), 0)
  const aired = prev + episodeNumber
  return aired > 0 ? aired : null
}

function tvProgressTextFromDetail(detail: any) {
  const seasons = typeof detail?.number_of_seasons === 'number' ? detail.number_of_seasons : null
  const total = tvTotalEpisodesFromDetail(detail)
  const aired = tvAiredEpisodesFromDetail(detail, total)
  const last = detail?.last_episode_to_air
  const lastSeason = Number(last?.season_number) || 0
  const lastEp = Number(last?.episode_number) || 0

  const parts: string[] = []
  if (seasons != null) parts.push(`季数：${seasons}`)
  if (total != null) parts.push(`总集数：${total}`)
  if (aired != null && total != null) parts.push(`已播：${aired}/${total}`)
  else if (aired != null) parts.push(`已播：${aired}`)
  if (lastSeason > 0 && lastEp > 0) parts.push(`当前到 S${lastSeason}E${lastEp}`)
  return parts.join(' · ')
}

function tmdbLinkRowProgress(row: any) {
  if (tmdbLink.type !== 'tv') return ''
  const id = Number(row?.id) || 0
  if (id <= 0) return ''
  const detail = tmdbLink.detailsById[id]
  if (detail) return tvProgressTextFromDetail(detail)
  if (tmdbLink.loadingById[id]) return '进度：加载中'
  return ''
}

async function openTmdbLinkDialog() {
  tmdbLink.visible = true
  tmdbLink.loading = false
  tmdbLink.configured = true
  tmdbLink.items = []
  tmdbLink.selectedId = 0
  tmdbLink.detailsById = {}
  tmdbLink.loadingById = {}
  const mt = String(state.tmdb_media_type || '').toLowerCase()
  tmdbLink.type = mt === 'movie' ? 'movie' : 'tv'
  tmdbLink.q = sanitizeSuggestionQuery(state.taskname)
  tmdbLink.year = ''
  if (tmdbLink.q.trim()) {
    await runTmdbLinkSearch()
  }
}

async function runTmdbLinkSearch() {
  const q = String(tmdbLink.q || '').trim()
  if (q.length < 1) return
  tmdbLink.loading = true
  try {
    const data = await searchTMDB({ q, type: tmdbLink.type, year: tmdbLink.year.trim() || undefined, page: 1 })
    tmdbLink.configured = Boolean(data.configured)
    if (!tmdbLink.configured) {
      ElMessage.warning('未配置 TMDB API Key')
      tmdbLink.items = []
      tmdbLink.selectedId = 0
      return
    }
    const list = data.items || []
    tmdbLink.items = list
    tmdbLink.detailsById = {}
    tmdbLink.loadingById = {}
    let picked: TMDBBrief | null = null
    const year = tmdbLink.year.trim()
    if (year) {
      const key = tmdbLink.type === 'movie' ? 'release_date' : 'first_air_date'
      picked = list.find((x: any) => String(x?.[key] || '').startsWith(year)) || null
    }
    picked = picked || list[0] || null
    tmdbLink.selectedId = Number(picked?.id) || 0
    const prefetch = list.slice(0, 6).map((x) => Number((x as any)?.id) || 0).filter((x) => x > 0)
    for (const id of prefetch) {
      ensureTmdbLinkDetail(id)
    }
  } catch (e: any) {
    ElMessage.error(e?.message || 'TMDB 搜索失败')
  } finally {
    tmdbLink.loading = false
  }
}

async function confirmTmdbLink() {
  const id = Number(tmdbLink.selectedId) || 0
  if (id <= 0) return
  state.tmdb_id = id
  state.tmdb_media_type = tmdbLink.type
  if (tmdbLink.type === 'tv' && tmdbLink.configured && state.runweek_mode === 'auto') {
    await applyRunweekFromTmdbUpdateWeekdays(id, 'tv')
  }
  // 关联TMDB后，把{SXX}替换成实际季数写入replace
  if (tmdbLink.type === 'tv') {
    await ensureTmdbLinkDetail(id)
    const detail = tmdbLink.detailsById[id]
    if (detail) {
      const seasons = Array.isArray(detail.seasons) ? detail.seasons : []
      const validSeasons = seasons.filter((s: any) => s && typeof s === 'object' && Number(s.season_number) > 0)
      const last = validSeasons.slice(-1)[0]
      const sn = Number(last?.season_number) || 0
      if (sn > 0 && state.replace && String(state.replace).includes('{SXX}')) {
        state.replace = String(state.replace).replace(/\{SXX\}/g, `S${String(sn).padStart(2, '0')}`)
      }
    }
  }
  tmdbLink.visible = false
}

function clearTmdbLink() {
  state.tmdb_id = null
  state.tmdb_media_type = null
  state.runweek_mode = 'manual'
  autoRunweekDays.value = []
  ElMessage.success('已解除关联')
}

async function verifySuggestions(runId: number, items: TaskSuggestionItemExt[]) {
  taskSuggestions.verifying = true
  await loadSharerFilterConfig()
  if (runId !== taskSuggestions.runId) return

  const allUrls = items.map((x) => x.shareurl).filter(Boolean)
  const dedup = Array.from(new Set(allUrls))

  const validItems: TaskSuggestionItemExt[] = []
  let totalReceived = 0
  let filteredInvalid = 0

  // 取消上一次流式验证
  if (taskSuggestions._abortController) {
    taskSuggestions._abortController.abort()
  }

  taskSuggestions._abortController = validateShareLinksStream(
    dedup,
    (row) => {
      if (runId !== taskSuggestions.runId) return
      totalReceived++
      if (!row.ok) {
        filteredInvalid++
        return
      }
      const orig = items.find((x) => x.shareurl === row.shareurl)
      if (!orig) {
        filteredInvalid++
        return
      }
      const author = (row.share_author_name || '').trim()
      if (!state.addition.show_blocked && author && sharerFilterConfig.blocked.includes(author)) {
        filteredInvalid++
        return
      }
      orig.share_author_name = author || undefined
      const isPreferred = author ? sharerFilterConfig.preferred.includes(author) : false
      orig.is_preferred_sharer = isPreferred
      orig.is_blocked_sharer = author ? sharerFilterConfig.blocked.includes(author) : false
      if (state.addition.preferred_only && !isPreferred) {
        filteredInvalid++
        return
      }
      validItems.push(orig)
      taskSuggestions.items = [...validItems]
    },
    () => {
      // 全部完成
      if (runId === taskSuggestions.runId) {
        taskSuggestions.items = [...validItems]
        taskSuggestions.verifying = false
        const parts: string[] = []
        if (taskSuggestions.notice) parts.push(taskSuggestions.notice)
        if (filteredInvalid > 0) parts.push(`已过滤失效链接 ${filteredInvalid} 条`)
        taskSuggestions.notice = parts.join('；')
      }
    },
    () => {
      // 出错
      if (runId === taskSuggestions.runId) {
        taskSuggestions.verifying = false
      }
    },
  )
}

async function searchSuggestions(deep: 0 | 1) {
  if (!props.modelValue) return
  if (deep === 0 && !taskSuggestions.focused) return
  const q = sanitizeSuggestionQuery(state.taskname)
  if (q.length < 2) return
  taskSuggestions.loading = true
  taskSuggestions.deep = deep
  taskSuggestions.lastQuery = q
  taskSuggestions.lastDeep = deep
  taskSuggestions.notice = ''
  taskSuggestions.runId += 1
  const runId = taskSuggestions.runId
  try {
    let driveType: string | null = null
    if (deep === 1) {
      if (state.account_choice !== '__AUTO__') {
        driveType = driveTypeForAccountName(state.account_choice)
      } else {
        const url = String(state.shareurl || '').trim()
        if (url) {
          const dt = detectDriveTypeByUrl(url)
          driveType = dt ? String(dt) : null
        }
      }
    }
    const data = await fetchTaskSuggestions(q, deep, driveType, state.addition?.search_filter || '', state.addition?.search_exclude || '', state.addition?.search_date_from || '', state.addition?.search_filter_mode || '', state.addition?.search_exclude_mode || '', state.addition?.show_blocked)
    if (runId !== taskSuggestions.runId) return
    const rawItems = (data.data || []).filter((x) => x && x.shareurl)
    taskSuggestions.notice = String((data as any)?.message || '').trim()
    // 先不显示结果，等验证完才增量显示有效的（和夸克自动转存一致）
    taskSuggestions.items = []
    taskSuggestions.visible = true
    if (rawItems.length) {
      verifySuggestions(runId, rawItems.map((x) => ({ ...x })))
    } else {
      taskSuggestions.visible = true
    }
  } finally {
    if (runId === taskSuggestions.runId) {
      taskSuggestions.loading = false
    }
  }
}

function openAuthorMenu(event: MouseEvent, item: TaskSuggestionItemExt) {
  authorMenu.item = item
  authorMenu.x = event.clientX
  authorMenu.y = event.clientY
  authorMenu.visible = true
}

function isSharerPreferred(name: string): boolean {
  return name ? sharerFilterConfig.preferred.includes(name) : false
}

function isSharerBlocked(name: string): boolean {
  return name ? sharerFilterConfig.blocked.includes(name) : false
}

async function addSharerToPreferred(name: string) {
  if (!name) return
  const { updateSharerFilterSettings } = await import('@/api/systemSettings')
  try {
    await loadSharerFilterConfig()
    const preferred = [...sharerFilterConfig.preferred]
    if (!preferred.includes(name)) preferred.push(name)
    const blocked = sharerFilterConfig.blocked.filter((x) => x !== name)
    await updateSharerFilterSettings({ preferred_sharers: preferred.join('|'), blocked_sharers: blocked.join('|') })
    sharerFilterConfig.preferred = preferred
    sharerFilterConfig.blocked = blocked
    sharePicker.isPreferredSharer = true
    // 同步更新搜索结果中的标记
    const matched = taskSuggestions.items.find((x) => (x.share_author_name || '').trim() === name)
    if (matched) matched.is_preferred_sharer = true
    ElMessage.success(`已加入优质分享者：${name}`)
  } catch {
    ElMessage.error('操作失败')
  }
}

async function addSharerToBlocked(name: string) {
  if (!name) return
  const { updateSharerFilterSettings } = await import('@/api/systemSettings')
  try {
    await loadSharerFilterConfig()
    const blocked = [...sharerFilterConfig.blocked]
    if (!blocked.includes(name)) blocked.push(name)
    const preferred = sharerFilterConfig.preferred.filter((x) => x !== name)
    await updateSharerFilterSettings({ preferred_sharers: preferred.join('|'), blocked_sharers: blocked.join('|') })
    sharerFilterConfig.preferred = preferred
    sharerFilterConfig.blocked = blocked
    sharePicker.sharerName = ''
    taskSuggestions.items = taskSuggestions.items.filter((x) => x.share_author_name !== name)
    ElMessage.success(`已屏蔽分享者：${name}`)
  } catch {
    ElMessage.error('操作失败')
  }
}

async function removeSharerFromPreferred(name: string) {
  if (!name) return
  const { updateSharerFilterSettings } = await import('@/api/systemSettings')
  try {
    await loadSharerFilterConfig()
    const preferred = sharerFilterConfig.preferred.filter((x) => x !== name)
    const blocked = [...sharerFilterConfig.blocked]
    await updateSharerFilterSettings({ preferred_sharers: preferred.join('|'), blocked_sharers: blocked.join('|') })
    sharerFilterConfig.preferred = preferred
    sharePicker.isPreferredSharer = false
    const matched = taskSuggestions.items.find((x) => (x.share_author_name || '').trim() === name)
    if (matched) matched.is_preferred_sharer = false
    ElMessage.success(`已移除优选分享者：${name}`)
  } catch {
    ElMessage.error('操作失败')
  }
}

async function removeSharerFromBlocked(name: string) {
  if (!name) return
  const { updateSharerFilterSettings } = await import('@/api/systemSettings')
  try {
    await loadSharerFilterConfig()
    const blocked = sharerFilterConfig.blocked.filter((x) => x !== name)
    const preferred = [...sharerFilterConfig.preferred]
    await updateSharerFilterSettings({ preferred_sharers: preferred.join('|'), blocked_sharers: blocked.join('|') })
    sharerFilterConfig.blocked = blocked
    ElMessage.success(`已取消屏蔽：${name}`)
  } catch {
    ElMessage.error('操作失败')
  }
}

async function handleAuthorCommand(cmd: string) {
  const item = authorMenu.item
  authorMenu.visible = false
  if (!item) return
  const author = (item.share_author_name || '').trim()
  if (!author) return
  const { updateSharerFilterSettings } = await import('@/api/systemSettings')
  try {
    await loadSharerFilterConfig()
    if (cmd === 'prefer') {
      // 加入优质，同时从屏蔽中移除
      const preferred = [...sharerFilterConfig.preferred]
      if (!preferred.includes(author)) preferred.push(author)
      const blocked = sharerFilterConfig.blocked.filter((x) => x !== author)
      await updateSharerFilterSettings({ preferred_sharers: preferred.join('|'), blocked_sharers: blocked.join('|') })
      sharerFilterConfig.preferred = preferred
      sharerFilterConfig.blocked = blocked
      item.is_preferred_sharer = true
      ElMessage.success(`已加入优质分享者：${author}`)
    } else if (cmd === 'unprefer') {
      const preferred = sharerFilterConfig.preferred.filter((x) => x !== author)
      const blocked = [...sharerFilterConfig.blocked]
      await updateSharerFilterSettings({ preferred_sharers: preferred.join('|'), blocked_sharers: blocked.join('|') })
      sharerFilterConfig.preferred = preferred
      item.is_preferred_sharer = false
      ElMessage.success(`已移除优选分享者：${author}`)
    } else if (cmd === 'block') {
      // 加入屏蔽，同时从优质中移除
      const blocked = [...sharerFilterConfig.blocked]
      if (!blocked.includes(author)) blocked.push(author)
      const preferred = sharerFilterConfig.preferred.filter((x) => x !== author)
      await updateSharerFilterSettings({ preferred_sharers: preferred.join('|'), blocked_sharers: blocked.join('|') })
      sharerFilterConfig.preferred = preferred
      sharerFilterConfig.blocked = blocked
      // 从搜索结果中移除
      taskSuggestions.items = taskSuggestions.items.filter((x) => x.share_author_name !== author)
      ElMessage.success(`已屏蔽分享者：${author}`)
    } else if (cmd === 'unblock') {
      const blocked = sharerFilterConfig.blocked.filter((x) => x !== author)
      const preferred = [...sharerFilterConfig.preferred]
      await updateSharerFilterSettings({ preferred_sharers: preferred.join('|'), blocked_sharers: blocked.join('|') })
      sharerFilterConfig.blocked = blocked
      ElMessage.success(`已取消屏蔽：${author}`)
    }
  } catch {
    ElMessage.error('操作失败')
  }
}

function onFilterRuleChange(name: string) {
  const rule = filterRuleOptions.value.find((r) => r.name === name)
  state.addition.filter_words = rule ? rule.keywords : ''
}

function removeSyncTaskUid(uid: string) {
  state.sync_task_uids = state.sync_task_uids.filter((u) => u !== uid)
  if (uid.startsWith('__pending_')) {
    pendingSyncTasks.value = pendingSyncTasks.value.filter((p) => p.tempUid !== uid)
  } else {
    removedSyncTaskUids.value.push(uid)
  }
}

function openCreateSyncTask() {
  createSyncDialog.name = state.taskname || ''
  createSyncDialog.mode = 'one_way'
  createSyncDialog.sourceType = 'openlist'
  createSyncDialog.sourcePath = ''
  createSyncDialog.targetType = 'openlist'
  createSyncDialog.targetPath = ''
  createSyncDialog.overwrite = false
  createSyncDialog.one_way_delete_extras = false
  createSyncDialog.force_refresh = false
  createSyncDialog.visible = true
}

function openSyncPathPicker(target: 'source' | 'target') {
  syncPathPicker.target = target
  syncPathPicker.endpointType = (target === 'source' ? createSyncDialog.sourceType : createSyncDialog.targetType) as 'openlist' | 'local'
  const currentPath = target === 'source' ? createSyncDialog.sourcePath : createSyncDialog.targetPath
  syncPathPicker.dirPath = syncPathPicker.endpointType === 'openlist' ? (currentPath || '/') : (currentPath || '')
  syncPathPicker.visible = true
  refreshSyncPathPicker()
}

async function refreshSyncPathPicker() {
  syncPathPicker.loading = true
  try {
    if (syncPathPicker.endpointType === 'openlist') {
      const { browseOpenList } = await import('@/api/openlist')
      const data = await browseOpenList({ path: syncPathPicker.dirPath || '/', max_items: 500 })
      syncPathPicker.dirPath = String(data.dir_path || '/')
      syncPathPicker.paths = data.paths || []
      syncPathPicker.items = data.items || []
    } else {
      const { browseLocalSync } = await import('@/api/syncTasks')
      const data = await browseLocalSync({ path: syncPathPicker.dirPath || '', max_items: 500 })
      syncPathPicker.dirPath = String(data.dir_path || '')
      syncPathPicker.paths = data.paths || []
      syncPathPicker.items = data.items || []
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '加载路径失败')
  } finally {
    syncPathPicker.loading = false
  }
}

async function enterSyncPickerDir(item: any) {
  if (!item.is_dir) return
  syncPathPicker.dirPath = String(item.path || '')
  await refreshSyncPathPicker()
}

function pickSyncPath(path: string) {
  syncPathPicker.dirPath = String(path || '')
  refreshSyncPathPicker()
}

function useSyncPickerPath() {
  const path = syncPathPicker.dirPath || ''
  if (syncPathPicker.target === 'source') {
    createSyncDialog.sourcePath = path
  } else {
    createSyncDialog.targetPath = path
  }
  syncPathPicker.visible = false
}

async function submitCreateSyncTask() {
  if (!createSyncDialog.name.trim()) return ElMessage.warning('请输入同步任务名称')
  if (!createSyncDialog.sourcePath.trim()) return ElMessage.warning('请输入源路径')
  if (!createSyncDialog.targetPath.trim()) return ElMessage.warning('请输入目标路径')
  pendingUidCounter++
  const tempUid = `__pending_${pendingUidCounter}__`
  const pending: PendingSyncTask = {
    tempUid,
    name: createSyncDialog.name.trim(),
    mode: createSyncDialog.mode,
    source: { type: createSyncDialog.sourceType, path: createSyncDialog.sourcePath.trim() },
    target: { type: createSyncDialog.targetType, path: createSyncDialog.targetPath.trim() },
    strategy: {
      overwrite: createSyncDialog.overwrite,
      one_way_delete_extras: createSyncDialog.one_way_delete_extras,
      force_refresh: createSyncDialog.force_refresh,
      concurrency: 4,
      request_interval_seconds: 0,
      openlist_copy_batch_size: 10,
    },
  }
  pendingSyncTasks.value.push(pending)
  const uids = [...(state.sync_task_uids || [])]
  uids.push(tempUid)
  state.sync_task_uids = uids
  createSyncDialog.visible = false
  ElMessage.success('已暂存，保存追剧任务后生效')
}

async function loadSharerFilterConfig() {
  try {
    const data = await fetchSharerFilterSettings()
    sharerFilterConfig.preferred = (data.preferred_sharers || '').split('|').map((s: string) => s.trim()).filter(Boolean)
    sharerFilterConfig.blocked = (data.blocked_sharers || '').split('|').map((s: string) => s.trim()).filter(Boolean)
    sharerFilterConfig.batchSize = data.validate_batch_size || 5
  } catch { /* 忽略 */ }
}

function scheduleLightSearch() {
  if (!props.modelValue) return
  if (!taskSuggestions.focused) return
  if (taskSuggestions.searchTimer) clearTimeout(taskSuggestions.searchTimer)
  taskSuggestions.searchTimer = setTimeout(() => {
    searchSuggestions(0)
  }, 1000)
}

function selectSuggestion(item: TaskSuggestionItemExt) {
  const url = String(item.shareurl || '').trim()
  if (!url) return
  taskSuggestions.selectedItem = item
  sharePicker.sharerName = (item.share_author_name || '').trim()
  sharePicker.isPreferredSharer = Boolean(item.is_preferred_sharer)
  nextTick(() => {
    openSharePicker(url)
  })
}

function sortUpdatedAt(a: any, b: any) {
  const av = Number(a?.updated_at) || 0
  const bv = Number(b?.updated_at) || 0
  return av - bv
}

function sortFileNameRe(a: any, b: any) {
  const an = String(a?.file_name_re || a?.file_name_saved || a?.file_name || a?.name || '').toLowerCase()
  const bn = String(b?.file_name_re || b?.file_name_saved || b?.file_name || b?.name || '').toLowerCase()
  return an.localeCompare(bn, undefined, { numeric: true })
}

function sortDriveList(by = drivePicker.sortBy, order = drivePicker.sortOrder) {
  drivePicker.sortBy = by
  drivePicker.sortOrder = order
  drivePicker.mobileSort = `${drivePicker.sortBy}:${drivePicker.sortOrder}`
  const direction = drivePicker.sortOrder === 'asc' ? 1 : -1
  drivePicker.items.sort((a, b) => {
    if (drivePicker.sortBy === 'updated_at') {
      const av = Number(a.updated_at) || 0
      const bv = Number(b.updated_at) || 0
      return (av - bv) * direction
    }
    const an = String(a.file_name || a.name || '').toLowerCase()
    const bn = String(b.file_name || b.name || '').toLowerCase()
    return an.localeCompare(bn) * direction
  })
}

function applyDriveMobileSort() {
  const [by, order] = String(drivePicker.mobileSort || '').split(':')
  if ((by === 'file_name' || by === 'updated_at') && (order === 'asc' || order === 'desc')) {
    sortDriveList(by, order)
  }
}

function onDriveSortChange(payload: any) {
  const prop = String(payload?.prop || '')
  const order = String(payload?.order || '')
  if (prop !== 'file_name' && prop !== 'updated_at') return
  if (order === 'ascending') sortDriveList(prop as any, 'asc')
  if (order === 'descending') sortDriveList(prop as any, 'desc')
}

function currentDrivePathLabel() {
  if (!drivePicker.paths.length) return '/'
  return `/${drivePicker.paths.map((x) => x.name).join('/')}`
}

async function browseDriveDir(dir_path: string) {
  drivePicker.loading = true
  const account_name = state.account_choice !== '__AUTO__' ? state.account_choice : null
  try {
    const data = await browseDrive({
      dir_path,
      account_name,
      shareurl: state.shareurl || null,
      max_items: 200,
    })
    drivePicker.dirPath = data.dir_path || dir_path
    drivePicker.pdir_fid = data.pdir_fid || (dir_path === '/' || dir_path === '0' ? '0' : drivePicker.pdir_fid)
    drivePicker.drive_type = data.drive_type || ''
    if (Array.isArray(data.paths) && data.paths.length) {
      drivePicker.paths = data.paths
    }
    drivePicker.items = data.exists ? data.items || [] : []
    sortDriveList(drivePicker.sortBy, drivePicker.sortOrder)
  } finally {
    drivePicker.loading = false
  }
}

function extractShareFid(url: string) {
  const mq = url.match(/(?:\?|&)fid=([^&#]+)/)
  if (mq?.[1] && !['0', 'root'].includes(String(mq[1]).trim())) return String(mq[1]).trim()
  const m1 = url.match(/#\/list\/share\/([a-zA-Z0-9]{6,64})/)
  if (m1?.[1]) return m1[1]
  const m2 = url.match(/\/([a-fA-F0-9]{32})-?[^/]*$/)
  if (m2?.[1]) return m2[1]
  return null
}

function isCloud139HashShareurl(shareurl: string) {
  return /^https?:\/\/(?:yun|caiyun)\.139\.com/i.test(String(shareurl || '').trim())
}

function getShareurl(shareurl: string, dir?: { fid?: string; name?: string }) {
  const raw = String(shareurl || '').trim()
  const fid = String(dir?.fid || '').trim()
  if (isCloud139HashShareurl(raw)) {
    const [head, fragment = ''] = raw.split('#', 2)
    if (fragment) {
      const [fragPath, fragQuery = ''] = fragment.split('?', 2)
      const parts = fragQuery
        .split('&')
        .map((x) => String(x || '').trim())
        .filter((x) => x && !x.startsWith('fid='))
      if (fid && !['0', 'root'].includes(fid)) parts.push(`fid=${encodeURIComponent(fid)}`)
      return `${head}#${parts.length ? `${fragPath}?${parts.join('&')}` : fragPath}`
    }
    let nextHead = head.replace(/([?&])fid=[^&#]*/g, '$1').replace(/[?&]+$/, '').replace('?&', '?')
    if (fid && !['0', 'root'].includes(fid)) {
      nextHead = `${nextHead}${nextHead.includes('?') ? '&' : '?'}fid=${encodeURIComponent(fid)}`
    }
    return nextHead
  }
  if (!fid || fid === '0') {
    const match = raw.match(/.*s\/[a-zA-Z0-9\-_]+(\?[^#]*)?/)
    return (match ? match[0] : raw.split('#')[0]).trim()
  }
  if (raw.includes(fid)) {
    const m = raw.match(new RegExp(`.*/${fid}[^/]*`))
    if (m?.[0]) return m[0]
  }
  if (raw.includes('#/list/share')) {
    return `${raw.split('#')[0]}#/list/share/${fid}`
  }
  return `${raw.split('#')[0]}#/list/share/${fid}`
}

function normalizeSavepath(value: string) {
  const s = String(value || '').trim()
  if (!s) return ''
  const normalized = `/${s}`.replace(/\/+/g, '/')
  return normalized.length > 1 ? normalized.replace(/\/+$/, '') : normalized
}

function driveTypeForAccountName(name: string | null | undefined) {
  const n = String(name || '').trim()
  if (!n) return null
  const found = props.accounts.find((x) => String(x.name) === n)
  return found ? String(found.drive_type || '').trim() || null : null
}

function driveTypeForTask(task: TaskItem) {
  const byAccount = driveTypeForAccountName(task.account_name)
  if (byAccount) return byAccount
  const byUrl = detectDriveTypeByUrl(task.shareurl)
  return byUrl ? String(byUrl) : null
}

function currentDriveType() {
  if (state.account_choice !== '__AUTO__') {
    return driveTypeForAccountName(state.account_choice)
  }
  const dt = detectDriveTypeByUrl(state.shareurl)
  return dt ? String(dt) : null
}

function cleanSavepathBase(savepath: string, taskname: string) {
  let p = normalizeSavepath(savepath)
  if (!p) return ''
  p = p.replace(/\/S\d{1,3}$/i, '')
  const name = String(taskname || '').trim()
  if (!name) return p
  const parts = p.split('/').filter(Boolean)
  const last = String(parts.at(-1) || '')
  if (!last) return p
  if (last === name) return normalizeSavepath(parts.slice(0, -1).join('/'))
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  if (new RegExp(`^${escaped}\\s*\\(\\d{4}\\)$`).test(last)) {
    return normalizeSavepath(parts.slice(0, -1).join('/'))
  }
  return p
}

function existingTaskCategory(task: TaskItem) {
  const savepath = normalizeSavepath(task.savepath)
  if (savepath.includes('/动漫')) return '动漫'
  if (savepath.includes('/综艺')) return '综艺'
  const mt = String(task.tmdb_media_type || '').toLowerCase()
  if (mt === 'movie') return '电影'
  if (mt === 'tv') return '电视剧'
  return ''
}

function categoryFromTmdb(mt: string, detail: any) {
  const mediaType = String(mt || '').toLowerCase()
  if (mediaType === 'movie') return '电影'
  const genres = Array.isArray(detail?.genres) ? detail.genres : []
  const ids = new Set<number>()
  const names = new Set<string>()
  for (const g of genres) {
    const id = Number((g as any)?.id)
    if (Number.isFinite(id) && id > 0) ids.add(id)
    const n = String((g as any)?.name || '').trim().toLowerCase()
    if (n) names.add(n)
  }
  const hasAnime = ids.has(16) || Array.from(names).some((n) => n.includes('animation') || n.includes('动画'))
  if (hasAnime) return '动漫'
  const varietyIds = new Set([10764, 10767, 10763])
  const hasVariety = Array.from(varietyIds).some((id) => ids.has(id)) || Array.from(names).some((n) => n.includes('reality') || n.includes('talk') || n.includes('真人秀') || n.includes('脱口秀'))
  if (hasVariety) return '综艺'
  return '电视剧'
}

function ensureCategorySegment(base: string, category: string) {
  const p = normalizeSavepath(base)
  const c = String(category || '').trim()
  if (!p || !c) return p
  const segs = p.split('/').filter(Boolean)
  if (segs.includes(c)) return p
  return normalizeSavepath(`${p}/${c}`)
}

function yearFromTmdbDetail(mt: string, detail: any) {
  const mediaType = String(mt || '').toLowerCase()
  const raw = mediaType === 'movie' ? String(detail?.release_date || '') : String(detail?.first_air_date || '')
  if (raw.length >= 4 && /^\d{4}/.test(raw)) return Number(raw.slice(0, 4))
  return null
}

function appendYearSuffix(name: string, year: number | null) {
  const n = String(name || '').trim()
  if (!n) return ''
  if (!year || !Number.isFinite(year) || year < 1900 || year > 2100) return n
  if (/\(\d{4}\)\s*$/.test(n)) return n
  return `${n}(${year})`
}

async function ensureTasksLoaded() {
  if (saveAuto.tasks) return saveAuto.tasks
  if (saveAuto.tasksLoading) return saveAuto.tasks || []
  saveAuto.tasksLoading = true
  try {
    const data = await fetchTasks()
    saveAuto.tasks = Array.isArray(data) ? data : []
    return saveAuto.tasks
  } catch {
    saveAuto.tasks = []
    return saveAuto.tasks
  } finally {
    saveAuto.tasksLoading = false
  }
}

async function getTmdbDetailForCurrent() {
  const id = Number(state.tmdb_id) || 0
  const mt = String(state.tmdb_media_type || '').toLowerCase()
  if (id <= 0 || (mt !== 'movie' && mt !== 'tv')) return null
  const key = `${mt}:${id}`
  if (saveAuto.tmdbDetailCache[key]) return saveAuto.tmdbDetailCache[key]
  try {
    const res = await fetchTMDBDetail(mt as any, id)
    const detail = (res as any)?.data || null
    saveAuto.tmdbDetailCache[key] = detail
    return detail
  } catch {
    saveAuto.tmdbDetailCache[key] = null
    return null
  }
}

async function autoFillSavepath(runId: number) {
  if (!props.modelValue) return
  if (runId !== shareAuto.runId) return
  if (saveAuto.touched) return
  const currentSave = String(state.savepath || '').trim()
  if (isEditing.value && currentSave && currentSave !== saveAuto.lastApplied) return
  if (currentSave && currentSave !== saveAuto.lastApplied) return

  const dt = currentDriveType()
  if (!dt) return

  const all = await ensureTasksLoaded()
  if (runId !== shareAuto.runId) return

  const candidates = (all || []).filter((t) => driveTypeForTask(t) === dt && String(t.savepath || '').trim())
  if (!candidates.length) return

  const detail = await getTmdbDetailForCurrent()
  if (runId !== shareAuto.runId) return

  const mt = String(state.tmdb_media_type || '').toLowerCase()
  const category = categoryFromTmdb(mt, detail)
  const titleFromTmdb = String(detail?.name || detail?.title || '').trim()
  const baseNameSeg = String(state.taskname || '').trim() || titleFromTmdb
  const seasonCount = Number(detail?.number_of_seasons) || 0
  const needSeason = mt === 'tv' && seasonCount > 1

  // 获取最新季数和年份（和 driveSavepathHint 一样的逻辑）
  let seasonSuffix = ''
  let year: number | null = yearFromTmdbDetail(mt, detail)  // 默认取首播年份
  if (needSeason && detail) {
    const seasons = Array.isArray(detail?.seasons) ? detail.seasons : []
    const validSeasons = seasons.filter((s: any) => s && Number(s.season_number) > 0)
    const last = validSeasons.slice(-1)[0]
    const sn = Number(last?.season_number) || 1
    seasonSuffix = `/Season ${sn}`
    // 年份取最新季的播出年份，没有则取剧的首播年份
    const seasonAirDate = String(last?.air_date || '')
    if (seasonAirDate.length >= 4 && /^\d{4}/.test(seasonAirDate)) {
      year = Number(seasonAirDate.slice(0, 4))
    }
  }
  const nameSeg = appendYearSuffix(baseNameSeg, year)
  if (!nameSeg) return

  const filteredByCat = candidates.filter((t) => existingTaskCategory(t) === category)
  const pool = filteredByCat.length ? filteredByCat : candidates

  const counts = new Map<string, number>()
  const firstIdx = new Map<string, number>()
  for (let i = 0; i < pool.length; i += 1) {
    const t = pool[i]
    const base = cleanSavepathBase(t.savepath, t.taskname)
    if (!base) continue
    counts.set(base, (counts.get(base) || 0) + 1)
    if (!firstIdx.has(base)) firstIdx.set(base, i)
  }
  const sorted = Array.from(counts.entries()).sort((a, b) => {
    if (b[1] !== a[1]) return b[1] - a[1]
    return (firstIdx.get(a[0]) || 0) - (firstIdx.get(b[0]) || 0)
  })
  const baseRoot = sorted[0]?.[0] || ''
  if (!baseRoot) return

  let root = ensureCategorySegment(baseRoot, category)
  root = normalizeSavepath(root)
  let suggested = normalizeSavepath(`${root}/${nameSeg}${seasonSuffix}`)

  saveAuto.applying = true
  try {
    state.savepath = suggested
    saveAuto.lastApplied = suggested
  } finally {
    saveAuto.applying = false
  }
}

function syncState() {
  pendingSyncTasks.value = []
  pendingUidCounter = 0
  removedSyncTaskUids.value = []
  if (shareAuto.timer) {
    clearTimeout(shareAuto.timer)
    shareAuto.timer = null
  }
  autoFill.loading = false
  shareAuto.lastResolved = ''
  if (props.task) {
    state.taskname = props.task.taskname
    shareAuto.lastResolved = String(props.task.shareurl || '').trim()
    state.shareurl = props.task.shareurl
    state.savepath = props.task.savepath
    state.account_choice = props.task.account_name ? String(props.task.account_name) : '__AUTO__'
    state.enabled = props.task.enabled
    const taskUid = String(props.task.task_uid || '').trim()
    const syncedUids = taskUid
      ? sortedSyncTasks.value
          .filter((it) => Array.isArray(it.drama_task_uids) && it.drama_task_uids.some((uid) => String(uid || '').trim() === taskUid))
          .map((it) => String(it.uid || '').trim())
          .filter(Boolean)
      : []
    // 保留暂存任务的标识
    const pendingUids = pendingSyncTasks.value.map((p) => p.tempUid)
    state.sync_task_uids = [...new Set([...syncedUids, ...pendingUids])]
    state.pattern = props.task.pattern || null
    state.replace = props.task.replace || null
    state.ignore_extension = props.task.ignore_extension
    state.tmdb_id = props.task.tmdb_id ?? null
    state.tmdb_media_type = props.task.tmdb_media_type ?? null
    state.addition = clone(props.task.addition || {})
    state.extra = clone(props.task.extra || {})
    state.auto_update_shareurl =
      detectDriveTypeByUrl(String(props.task.shareurl || '').trim())
        ? Boolean((props.task.extra as any)?.auto_update_shareurl ?? (props.task.extra as any)?.auto_update_115_shareurl ?? true)
        : false
  } else {
    state.taskname = String(props.presetTaskname || '').trim()
    state.shareurl = ''
    state.savepath = ''
    state.account_choice = '__AUTO__'
    state.auto_update_shareurl = true
    state.enabled = true
    state.sync_task_uids = []
    state.pattern = ''
    state.replace = ''
    state.ignore_extension = true
    state.tmdb_id = props.presetTmdb?.tmdb_id ?? null
    state.tmdb_media_type = props.presetTmdb?.tmdb_media_type ?? null
    state.addition = { auto_update_file_min_date: '1' }
    state.extra = {}
  }

  saveAuto.touched = false
  saveAuto.lastApplied = ''

  magicRegex.selectedKey = ''

  const runweek = Array.isArray(state.extra.runweek) ? state.extra.runweek : []
  state.runweek = runweek.length > 0 ? runweek.map((item: any) => Number(item)).filter((item: any) => item >= 1 && item <= 7) : (!isEditing.value ? [1, 2, 3, 4, 5, 6, 7] : [])
  const mode = String((state.extra as any)?.runweek_mode || '').trim().toLowerCase()
  state.runweek_mode = mode === 'auto' ? 'auto' : 'manual'
  manualRunweekBackup.value = clone(state.runweek || [])
  autoRunweekDays.value = []

  const additionValue: any = state.addition
  if (!additionValue || typeof additionValue !== 'object' || Array.isArray(additionValue)) {
    state.addition = {}
  }
  for (const plugin of props.plugins) {
    const key = plugin.plugin_key
    const defaultCfg = clone(plugin.default_task_config || {})
    const currentCfg: any = (state.addition as any)[key]
    if (!currentCfg || typeof currentCfg !== 'object' || Array.isArray(currentCfg)) {
      ;(state.addition as any)[key] = defaultCfg
      continue
    }
    for (const [k, v] of Object.entries(defaultCfg)) {
      if (!(k in currentCfg)) currentCfg[k] = clone(v)
    }
    for (const field of plugin.task_config_fields || []) {
      const fieldKey = String(field.key || '').trim()
      if (!fieldKey) continue
      if (fieldKey in currentCfg) continue
      if (field.default !== undefined) currentCfg[fieldKey] = clone(field.default)
    }
  }
}

watch(
  () => state.savepath,
  (value) => {
    if (!props.modelValue) return
    if (saveAuto.applying) return
    const s = String(value || '').trim()
    if (!s) {
      saveAuto.touched = false
      saveAuto.lastApplied = ''
      return
    }
    if (s === saveAuto.lastApplied) return
    saveAuto.touched = true
  },
)

watch(
  () => [props.modelValue, props.task, props.plugins, props.syncTasks] as const,
  async ([visible]) => {
    if (!visible) return
    syncState()
    refreshMagicRegex()
    try {
      const cfg = await fetchTMDBConfig()
      tmdbLink.configured = Boolean(cfg?.has_api_key)
    } catch {
      tmdbLink.configured = false
    }

    if (!tmdbLink.configured && state.runweek_mode === 'auto') {
      state.runweek_mode = 'manual'
    }

    if (state.runweek_mode === 'auto') {
      const id = Number(state.tmdb_id) || 0
      const mt = String(state.tmdb_media_type || '').toLowerCase()
      if (id > 0 && mt === 'tv') {
        applyRunweekFromTmdbUpdateWeekdays(id, 'tv')
      }
    }
    if (props.autoDeepSuggest && !isEditing.value) {
      nextTick(() => {
        searchSuggestions(1)
      })
    }
  },
  { immediate: true, deep: true },
)

function triggerDeepSuggest() {
  searchSuggestions(1)
}

defineExpose({ triggerDeepSuggest })

async function refreshMagicRegex() {
  if (magicRegex.loading) return
  if (magicRegex.rules.length) return
  magicRegex.loading = true
  try {
    const data = await fetchMagicRegex()
    magicRegex.rules = data.rules || []
  } finally {
    magicRegex.loading = false
  }
}

async function applyMagicRule(key: string) {
  const rule = magicRegex.rules.find((r) => r.key === key)
  if (!rule) return
  state.pattern = rule.pattern
  state.replace = rule.replace
  // 如果已关联TMDB且是电视剧，把{SXX}替换成实际季数
  if (state.tmdb_id && state.tmdb_media_type === 'tv' && state.replace && String(state.replace).includes('{SXX}')) {
    await ensureTmdbLinkDetail(Number(state.tmdb_id))
    const detail = tmdbLink.detailsById[Number(state.tmdb_id)]
    if (detail) {
      const seasons = Array.isArray(detail.seasons) ? detail.seasons : []
      const validSeasons = seasons.filter((s: any) => s && typeof s === 'object' && Number(s.season_number) > 0)
      const last = validSeasons.slice(-1)[0]
      const sn = Number(last?.season_number) || 0
      if (sn > 0) {
        state.replace = String(state.replace).replace(/\{SXX\}/g, `S${String(sn).padStart(2, '0')}`)
      }
    }
  }
}

function closeDrawer() {
  resetSuggestions()
  selectedTemplateId.value = null
  emit('update:modelValue', false)
}

function buildExtraPayload() {
  const extra = clone(state.extra || {})
  extra.runweek_mode = state.runweek_mode
  extra.runweek = state.runweek_mode === 'auto' ? [] : clone(state.runweek || [])
  // 没有重命名规则时强制关闭自动换链
  extra.auto_update_shareurl = (showAutoUpdateToggle.value && hasRenameRule.value) ? Boolean(state.auto_update_shareurl) : false
  return extra
}

function validateBeforeSubmit() {
  const missing: string[] = []
  if (!String(state.taskname || '').trim()) missing.push('任务名称')
  if (!String(state.shareurl || '').trim()) missing.push('分享链接')
  if (!String(state.savepath || '').trim()) missing.push('保存路径（savepath）')
  if (missing.length) {
    ElMessageBox.alert(`请先填写：${missing.join('、')}`, '提示', {
      type: 'warning',
      confirmButtonText: '知道了',
    })
    return false
  }
  return true
}

async function submit() {
  if (!validateBeforeSubmit()) return

  // 没有重命名规则时弹出确认框
  if (!hasRenameRule.value) {
    try {
      await ElMessageBox.confirm(
        '不设置重命名规则将关闭连贯性检查和自动换链',
        '提示',
        {
          confirmButtonText: '确认',
          cancelButtonText: '取消',
          type: 'warning',
        }
      )
    } catch {
      return // 用户点取消
    }
  }

  const account_name = state.account_choice !== '__AUTO__' ? state.account_choice : null
  const normalizedShare = normalizeCloud189ShareUrl(state.shareurl.trim())
  const shareurl = (normalizedShare?.url || state.shareurl).trim()
  if (shareurl !== state.shareurl.trim()) state.shareurl = shareurl

  // 先创建暂存的同步任务
  if (pendingSyncTasks.value.length) {
    try {
      const { createSyncTask } = await import('@/api/syncTasks')
      const createdUids: string[] = []
      for (const p of pendingSyncTasks.value) {
        const result = await createSyncTask({
          name: p.name,
          enabled: true,
          mode: p.mode,
          source: p.source,
          target: p.target,
          strategy: p.strategy,
          drama_task_uids: props.task?.task_uid ? [String(props.task.task_uid)] : [],
        })
        if (result?.uid) {
          createdUids.push(p.tempUid, result.uid)
        }
      }
      // 替换临时标识为真实标识
      state.sync_task_uids = state.sync_task_uids.map((uid) => {
        const idx = createdUids.indexOf(uid)
        return idx >= 0 ? createdUids[idx + 1] : uid
      })
      pendingSyncTasks.value = []
    } catch (e: any) {
      ElMessage.error(e?.message || '创建同步任务失败')
      return
    }
  }

  // 删除被移除的已保存同步任务
  if (removedSyncTaskUids.value.length) {
    try {
      const { deleteSyncTask } = await import('@/api/syncTasks')
      for (const uid of removedSyncTaskUids.value) {
        const st = (props.syncTasks || []).find((t) => t.uid === uid)
        if (st) {
          try { await deleteSyncTask(st.id) } catch { /* 忽略 */ }
        }
      }
      removedSyncTaskUids.value = []
    } catch { /* 忽略 */ }
  }

  emit('save', {
    task_type: 'drama',
    taskname: state.taskname.trim(),
    shareurl,
    savepath: state.savepath.trim(),
    sync_task_uids: [...(state.sync_task_uids || [])],
    pattern: state.pattern ? String(state.pattern).trim() : null,
    replace: state.replace ? String(state.replace).trim() : null,
    ignore_extension: Boolean(state.ignore_extension),
    account_name,
    tmdb_id: state.tmdb_id ?? null,
    tmdb_media_type: state.tmdb_media_type ?? null,
    enabled: Boolean(state.enabled),
    addition: clone(state.addition || {}),
    extra: buildExtraPayload(),
  })
}

async function createSaveDir() {
  const path = String(state.savepath || '').trim()
  if (!path) return ElMessage.warning('请先输入或选择保存路径')
  try {
    await mkdirDrive({ dir_path: path, account_name: state.account_choice !== '__AUTO__' ? state.account_choice : null })
    ElMessage.success('目录已创建')
  } catch (e: any) {
    if (e?.message?.includes('已存在') || e?.message?.includes('exist')) {
      ElMessage.info('目录已存在')
    } else {
      ElMessage.error(e?.message || '创建失败')
    }
  }
}

async function openDrivePicker() {
  drivePicker.visible = true
  drivePicker.sortBy = 'file_name'
  drivePicker.sortOrder = 'asc'
  drivePicker.mobileSort = 'file_name:asc'
  drivePicker.paths = []
  await getTmdbDetailForCurrent()
  await browseDriveDir(state.savepath || '/')
}

async function refreshDrivePicker() {
  if (drivePicker.pdir_fid) {
    await browseDriveDir(drivePicker.pdir_fid)
    return
  }
  await browseDriveDir(state.savepath || '/')
}

function driveNavigateTo(fid: string, name?: string, opts?: { sliceToIndex?: number }) {
  const targetFid = String(fid || '').trim() || '0'
  if (targetFid === '0' || targetFid === '/') {
    drivePicker.paths = []
    drivePicker.pdir_fid = '0'
    browseDriveDir('/')
    return
  }

  const sliceToIndex = opts?.sliceToIndex
  if (typeof sliceToIndex === 'number' && sliceToIndex >= 0) {
    drivePicker.paths = drivePicker.paths.slice(0, sliceToIndex + 1)
  } else {
    const idx = drivePicker.paths.findIndex((p) => String(p.fid) === targetFid)
    if (idx !== -1) {
      drivePicker.paths = drivePicker.paths.slice(0, idx + 1)
    } else if (name) {
      drivePicker.paths = [...drivePicker.paths, { fid: targetFid, name: String(name) }]
    }
  }
  drivePicker.pdir_fid = targetFid
  browseDriveDir(targetFid)
}

function enterDriveDir(item: DriveBrowseItem) {
  if (!item.is_dir) return
  driveNavigateTo(item.fid, String(item.file_name || item.name || ''))
}

function driveGoRoot() {
  driveNavigateTo('0')
}

function driveGoBack() {
  if (!drivePicker.paths.length) {
    driveGoRoot()
    return
  }
  drivePicker.paths = drivePicker.paths.slice(0, -1)
  const target = drivePicker.paths.at(-1)
  const fid = target?.fid || '0'
  drivePicker.pdir_fid = fid
  browseDriveDir(fid === '0' ? '/' : fid)
}

function driveSavepathHint() {
  const name = String(state.taskname || '').trim()
  if (!name) return ''
  const id = Number(state.tmdb_id) || 0
  const mt = String(state.tmdb_media_type || '').toLowerCase()
  if (id <= 0 || (mt !== 'movie' && mt !== 'tv')) return name
  const key = `${mt}:${id}`
  const detail = saveAuto.tmdbDetailCache[key]
  if (!detail) return name
  const seasons = Array.isArray(detail?.seasons) ? detail.seasons : []
  const validSeasons = seasons.filter((s: any) => s && Number(s.season_number) > 0)
  const last = validSeasons.slice(-1)[0]
  const sn = Number(last?.season_number) || 1
  // 年份取最新季的播出年份，没有则取剧的首播年份
  const seasonAirDate = String(last?.air_date || '')
  let year: number | null = null
  if (seasonAirDate.length >= 4 && /^\d{4}/.test(seasonAirDate)) {
    year = Number(seasonAirDate.slice(0, 4))
  } else {
    year = yearFromTmdbDetail(mt, detail)
  }
  const nameWithYear = appendYearSuffix(name, year)
  return `${nameWithYear}/Season ${sn}`
}

function useCurrentDrivePath(withTaskname: boolean) {
  const base = currentDrivePathLabel()
  if (withTaskname && state.taskname.trim()) {
    const hint = driveSavepathHint() || state.taskname.trim()
    state.savepath = `${base}/${hint}`.replace(/\/+/g, '/')
  } else {
    state.savepath = base
  }
  drivePicker.visible = false
}

async function openSharePicker(overrideUrl?: string) {
  const url = overrideUrl || state.shareurl.trim()
  if (!url) {
    ElMessage.warning('请先填写分享链接')
    return
  }
  sharePicker.visible = true
  sharePicker.root_shareurl = getShareurl(url, { fid: '0' })
  sharePicker.shareurl = url
  sharePicker.sharerName = ''
  sharePicker.isPreferredSharer = false
  const fid = extractShareFid(sharePicker.shareurl)
  sharePicker.stack = fid ? [{ name: '当前目录', pdir_fid: fid }] : []
  await refreshSharePicker(null)
}

async function refreshSharePicker(pdir_fid: string | null) {
  sharePicker.loading = true
  try {
    const account_name = state.account_choice !== '__AUTO__' ? state.account_choice : null
    const data = await previewShare({
      shareurl: sharePicker.shareurl,
      account_name,
      pdir_fid: pdir_fid ?? undefined,
      max_items: 200,
      taskname: state.taskname || undefined,
      pattern: state.pattern || undefined,
      replace: state.replace || undefined,
      savepath: state.savepath || undefined,
      ignore_extension: state.ignore_extension,
      min_size: state.addition?.min_size || undefined,
      filter_words: state.addition?.filter_words || undefined,
      file_filter: state.addition?.file_filter || undefined,
      file_filter_mode: state.addition?.file_filter_mode || undefined,
      file_min_date: state.addition?.file_min_date || undefined,
      dir_min_date: state.addition?.dir_min_date || undefined,
      folder_filter: state.addition?.folder_filter || undefined,
      folder_exclude: state.addition?.folder_exclude || undefined,
      folder_filter_mode: state.addition?.folder_filter_mode || undefined,
      folder_exclude_mode: state.addition?.folder_exclude_mode || undefined,
      folder_priority: state.addition?.folder_priority || undefined,
      folder_priority_mode: state.addition?.folder_priority_mode || undefined,
      tmdb_id: state.tmdb_id ?? undefined,
      tmdb_media_type: state.tmdb_media_type || undefined,
    })
    sharePicker.pdir_fid = data.pdir_fid || null
    sharePicker.items = data.items || []
    if (data.share_author_name) {
      sharePicker.sharerName = data.share_author_name
      sharePicker.isPreferredSharer = sharerFilterConfig.preferred.includes(data.share_author_name)
    }
  } finally {
    sharePicker.loading = false
  }
}

function enterShareDir(item: SharePreviewItem) {
  if (!item.is_dir) return
  sharePicker.stack.push({ name: item.name, pdir_fid: item.fid })
  sharePicker.shareurl = getShareurl(sharePicker.root_shareurl, { fid: item.fid, name: item.name })
  refreshSharePicker(item.fid)
}

function goShareBack() {
  sharePicker.stack.pop()
  const target = sharePicker.stack.at(-1)
  const fid = target?.pdir_fid || '0'
  sharePicker.shareurl = getShareurl(sharePicker.root_shareurl, { fid, name: target?.name || '/' })
  refreshSharePicker(fid === '0' ? null : fid)
}

function onShareRowClick(row: SharePreviewItem) {
  if (!row.is_dir) return
  enterShareDir(row)
}

function pickShareFolderCurrent() {
  const current = sharePicker.stack.at(-1)
  if (current?.pdir_fid && current?.name !== '当前目录') {
    state.shareurl = getShareurl(sharePicker.root_shareurl, { fid: current.pdir_fid, name: current.name })
    sharePicker.visible = false
    ElMessage.success('已选择分享文件夹')
    return
  }
  const fid = extractShareFid(sharePicker.shareurl)
  if (fid) {
    state.shareurl = sharePicker.shareurl
    sharePicker.visible = false
    ElMessage.success('已选择分享文件夹')
    return
  }
  // 没有文件夹可选（根目录只有文件），直接使用原始分享链接
  if (sharePicker.items.length) {
    state.shareurl = sharePicker.root_shareurl
    sharePicker.visible = false
    ElMessage.success('已选择分享链接')
    return
  }
  ElMessage.warning('请先进入某个文件夹后再选择')
}

const weekOptions = [
  { label: '一', value: 1 },
  { label: '二', value: 2 },
  { label: '三', value: 3 },
  { label: '四', value: 4 },
  { label: '五', value: 5 },
  { label: '六', value: 6 },
  { label: '日', value: 7 },
]

const autoRunweekText = computed(() => {
  const days = autoRunweekDays.value || []
  if (!days.length) return ''
  const map = new Map(weekOptions.map((x) => [x.value, x.label] as const))
  return days.map((d) => `周${map.get(Number(d) as any) || d}`).join('、')
})

const autoRunweekDisabled = computed(() => {
  if (!tmdbLink.configured) return true
  const mt = String(state.tmdb_media_type || '').toLowerCase()
  const id = Number(state.tmdb_id) || 0
  return mt !== 'tv' || id <= 0
})

watch(
  () => state.runweek_mode,
  (mode) => {
    if (!props.modelValue) return
    if (mode === 'auto') {
      manualRunweekBackup.value = clone(state.runweek || [])
      state.runweek = []
      const id = Number(state.tmdb_id) || 0
      const mt = String(state.tmdb_media_type || '').toLowerCase()
      if (id > 0 && mt === 'tv') applyRunweekFromTmdbUpdateWeekdays(id, 'tv')
      return
    }
    autoRunweekDays.value = []
    if (!state.runweek.length && manualRunweekBackup.value.length) {
      state.runweek = clone(manualRunweekBackup.value)
    }
  },
)

watch(
  () => [state.tmdb_id, state.tmdb_media_type, state.runweek_mode, tmdbLink.configured] as const,
  ([idRaw, mtRaw, mode, configured]) => {
    if (!props.modelValue) return
    if (mode !== 'auto') return
    if (!configured) return
    const id = Number(idRaw) || 0
    const mt = String(mtRaw || '').toLowerCase()
    if (id > 0 && mt === 'tv') applyRunweekFromTmdbUpdateWeekdays(id, 'tv')
  },
)

async function autoResolveShareFolder(shareurl: string, runId: number) {
  const input = String(shareurl || '').trim()
  if (!input) return
  if (!props.modelValue) return
  if (runId !== shareAuto.runId) return

  const account_name = state.account_choice !== '__AUTO__' ? state.account_choice : null
  const root = getShareurl(input, { fid: '0' })
  let current = input

  const toTs = (v: any) => {
    const n = Number(v)
    if (Number.isFinite(n)) return n < 1e12 ? n * 1000 : n
    const t = Date.parse(String(v || ''))
    return Number.isFinite(t) ? t : 0
  }

  const isVideoFile = (name: any) => {
    const s = String(name || '').toLowerCase()
    return /\.(mp4|mkv|mov|m4v|avi|mpeg|ts|flv|wmv|webm|cas)$/.test(s)
  }

  for (let depth = 0; depth < 12; depth += 1) {
    if (!props.modelValue) return
    if (runId !== shareAuto.runId) return
    const data = await previewShare({ shareurl: current, account_name, max_items: 50 })
    if (!props.modelValue) return
    if (runId !== shareAuto.runId) return
    const items = (Array.isArray(data.items) ? data.items : []) as SharePreviewItem[]

    const files = items.filter((x) => x && !x.is_dir)
    const dirs = items.filter((x) => x && x.is_dir)
    if (files.some((f) => isVideoFile(f.name || f.file_name))) {
      break
    }

    if (dirs.length === 1 && files.length === 0) {
      const only = dirs[0]
      current = getShareurl(root, { fid: only.fid, name: only.name })
      continue
    }

    if (dirs.length > 1 && files.length === 0) {
      const picked = [...dirs].sort((a, b) => toTs(b.updated_at) - toTs(a.updated_at))[0]
      if (!picked) break
      current = getShareurl(root, { fid: picked.fid, name: picked.name })
      continue
    }

    break
  }

  if (current !== input) {
    shareAuto.lastResolved = current
    state.shareurl = current
  }
}

watch(
  () => state.shareurl,
  (value) => {
    if (!props.modelValue) return
    const url = String(value || '').trim()
    if (!url) {
      autoFill.loading = false
      return
    }
    const normalized = normalizeCloud189ShareUrl(url)
    if (normalized?.url && normalized.url !== url) {
      state.shareurl = normalized.url
      return
    }
    if (url === shareAuto.lastResolved) return
    if (shareAuto.timer) clearTimeout(shareAuto.timer)
    shareAuto.runId += 1
    const runId = shareAuto.runId
    autoFill.runId = runId
    autoFill.loading = true
    autoFill.text = '正在自动定位目录并填写保存路径...'
    shareAuto.timer = setTimeout(async () => {
      try {
        autoFill.text = '正在自动定位分享目录...'
        await autoResolveShareFolder(url, runId)
      } catch {
        if (autoFill.runId === runId) autoFill.loading = false
        return
      }
      try {
        autoFill.text = '正在自动填写保存路径...'
        await autoFillSavepath(runId)
      } catch {
        if (autoFill.runId === runId) autoFill.loading = false
        return
      }
      if (autoFill.runId === runId) autoFill.loading = false
    }, 800)
  },
)

watch(
  () => [state.taskname, state.tmdb_id, state.tmdb_media_type, state.account_choice] as const,
  () => {
    if (!props.modelValue) return
    if (!String(state.shareurl || '').trim()) return
    if (saveAuto.timer) clearTimeout(saveAuto.timer)
    const runId = shareAuto.runId
    saveAuto.timer = setTimeout(() => {
      autoFillSavepath(runId).catch(() => {
        return
      })
    }, 350)
  },
)

watch(
  () => state.taskname,
  (value) => {
    if (!props.modelValue) return
    const q = sanitizeSuggestionQuery(value)
    if (q.length < 2) {
      taskSuggestions.items = []
      return
    }
    scheduleLightSearch()
  },
)

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) {
      resetSuggestions()
    } else {
      loadTemplateList()
    }
  },
)

async function loadTemplateList() {
  try {
    templateList.value = await fetchTaskTemplates()
  } catch {}
}

function applyTemplate(id: number | null) {
  if (!id) return
  const template = templateList.value.find(t => t.id === id)
  if (!template) return
  const config = template.config || {}
  if (config.search_filter !== undefined) state.addition.search_filter = config.search_filter
  if (config.search_exclude !== undefined) state.addition.search_exclude = config.search_exclude
  if (config.folder_filter !== undefined) state.addition.folder_filter = config.folder_filter
  if (config.folder_exclude !== undefined) state.addition.folder_exclude = config.folder_exclude
  if (config.folder_priority !== undefined) state.addition.folder_priority = config.folder_priority
  if (config.folder_priority_mode !== undefined) state.addition.folder_priority_mode = config.folder_priority_mode
  if (config.auto_update_file_min_date !== undefined) state.addition.auto_update_file_min_date = config.auto_update_file_min_date
  if (config.file_filter !== undefined) state.addition.file_filter = config.file_filter
  if (config.min_size !== undefined) state.addition.min_size = config.min_size
  // 应用模式设置
  if (config.search_filter_mode !== undefined) state.addition.search_filter_mode = config.search_filter_mode
  if (config.search_exclude_mode !== undefined) state.addition.search_exclude_mode = config.search_exclude_mode
  if (config.folder_filter_mode !== undefined) state.addition.folder_filter_mode = config.folder_filter_mode
  if (config.folder_exclude_mode !== undefined) state.addition.folder_exclude_mode = config.folder_exclude_mode
  if (config.file_filter_mode !== undefined) state.addition.file_filter_mode = config.file_filter_mode
  // 关键词过滤：如果有关联预设，选中预设并填充关键词
  if (config.filter_rule_name) {
    state.addition.filter_rule_name = config.filter_rule_name
    ensureFilterRules().then(() => onFilterRuleChange(config.filter_rule_name))
  } else if (config.filter_words !== undefined) {
    state.addition.filter_words = config.filter_words
  }
  // 重命名设置：如果 pattern 是 key（以 $ 开头），选中内置规则；否则直接填入
  if (config.pattern !== undefined) {
    if (config.pattern.startsWith('$')) {
      magicRegex.selectedKey = config.pattern
      applyMagicRule(config.pattern)
    } else {
      magicRegex.selectedKey = ''
      state.pattern = config.pattern
      if (config.replace !== undefined) state.replace = config.replace
    }
  } else if (config.replace !== undefined) {
    state.replace = config.replace
  }
  ElMessage.success(`已应用模板：${template.name}`)
}

function openSaveTemplate() {
  saveTemplateName.value = ''
  saveTemplateDialogVisible.value = true
}

async function submitSaveTemplate() {
  if (!saveTemplateName.value.trim()) return ElMessage.warning('请输入模板名称')
  const config: Record<string, any> = {}
  if (state.addition.search_filter) config.search_filter = state.addition.search_filter
  if (state.addition.search_exclude) config.search_exclude = state.addition.search_exclude
  if (state.addition.folder_filter) config.folder_filter = state.addition.folder_filter
  if (state.addition.folder_exclude) config.folder_exclude = state.addition.folder_exclude
  if (state.addition.folder_priority) config.folder_priority = state.addition.folder_priority
  if (state.addition.folder_priority_mode) config.folder_priority_mode = state.addition.folder_priority_mode
  if (state.addition.auto_update_file_min_date) config.auto_update_file_min_date = state.addition.auto_update_file_min_date
  // 关键词过滤：保存预设名称或手动输入的关键词
  if (state.addition.filter_rule_name) {
    config.filter_rule_name = state.addition.filter_rule_name
  } else if (state.addition.filter_words) {
    config.filter_words = state.addition.filter_words
  }
  if (state.addition.file_filter) config.file_filter = state.addition.file_filter
  if (state.addition.min_size) config.min_size = state.addition.min_size
  // 重命名：如果选中了内置规则，保存 key；否则保存实际内容
  if (magicRegex.selectedKey) {
    config.pattern = magicRegex.selectedKey
  } else if (state.pattern) {
    config.pattern = state.pattern
  }
  if (state.replace) config.replace = state.replace
  // 保存模式设置
  if (state.addition.search_filter_mode) config.search_filter_mode = state.addition.search_filter_mode
  if (state.addition.search_exclude_mode) config.search_exclude_mode = state.addition.search_exclude_mode
  if (state.addition.folder_filter_mode) config.folder_filter_mode = state.addition.folder_filter_mode
  if (state.addition.folder_exclude_mode) config.folder_exclude_mode = state.addition.folder_exclude_mode
  if (state.addition.file_filter_mode) config.file_filter_mode = state.addition.file_filter_mode
  try {
    await createTaskTemplate({ name: saveTemplateName.value.trim(), config })
    ElMessage.success('模板已保存')
    saveTemplateDialogVisible.value = false
    await loadTemplateList()
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  }
}
</script>

<template>
  <el-drawer :model-value="modelValue" :size="isMobile ? '100%' : '620px'" :show-close="false" @close="closeDrawer">
    <template #header>
      <div class="drawer-custom-title">{{ isEditing ? '编辑追剧任务' : '新增追剧任务' }}</div>
    </template>
    <el-form
      v-loading="autoFill.loading"
      :element-loading-text="autoFill.text"
      element-loading-background="rgba(0,0,0,0.55)"
      label-position="top"
      class="drawer-form"
      :disabled="Boolean(submitting) || autoFill.loading"
    >
      <el-alert v-if="autoFill.loading" type="info" show-icon :closable="false" style="margin-bottom: 14px">
        <div style="font-size: 13px; line-height: 1.5">
          <div>{{ autoFill.text }}</div>
          <div>自动完成后可继续手动修改。</div>
        </div>
      </el-alert>
      <div class="drawer-form__section">
        <div class="drawer-form__section-title" style="display: flex; justify-content: space-between; align-items: center">
          <span>基础信息</span>
          <el-switch v-model="state.enabled" active-text="启用" inactive-text="禁用" size="small" />
        </div>
        <el-form-item label="使用账号">
          <el-select v-model="state.account_choice" style="width: 100%">
            <el-option label="自动选择（按分享链接）" value="__AUTO__" />
            <el-option v-if="unavailableSelectedAccount" :key="`unavailable-${state.account_choice}`" :label="unavailableSelectedAccountLabel" :value="state.account_choice" disabled />
            <el-option v-for="item in activeAccounts" :key="item.id" :label="`${item.name}（${item.drive_type}）`" :value="item.name" />
          </el-select>
          <div v-if="state.account_choice === '__AUTO__'" class="drawer-form__hint">
            自动模式下会优先选择与分享链接同类型的默认账号。
          </div>
        </el-form-item>
        <el-form-item label="任务名称">
          <el-input v-model="state.taskname" placeholder="例如：某电视剧" @focus="showSuggestions" @blur="hideSuggestionsLater">
            <template #append>
              <el-button
                :disabled="sanitizeSuggestionQuery(state.taskname).length < 2"
                :loading="taskSuggestions.loading && taskSuggestions.deep === 1"
                @mousedown.prevent
                @click="searchSuggestions(1)"
              >
                深度搜索
              </el-button>
            </template>
          </el-input>
          <div v-if="taskSuggestions.visible" class="task-suggestions">
            <div class="task-suggestions__tip">
              <span v-if="taskSuggestions.verifying">正在检查链接有效性...</span>
              <span v-else>
                {{
                  taskSuggestions.notice
                    ? taskSuggestions.notice
                    : taskSuggestions.items.length
                      ? '以下资源来自网络搜索，请自行辨识'
                      : '未搜索到资源'
                }}
              </span>
            </div>
            <div
              v-for="(item, idx) in taskSuggestions.items"
              :key="`${item.shareurl}-${idx}`"
              class="task-suggestions__item"
              :class="{ 'task-suggestions__item--selected': taskSuggestions.selectedItem === item }"
              :style="item.is_blocked_sharer ? { backgroundColor: '#fde8e8' } : item.is_preferred_sharer ? { backgroundColor: '#e8f5e9' } : {}"
            >
              <span
                v-if="item.datetime"
                class="task-suggestions__time"
              >{{ item.datetime }}</span>
              <div class="task-suggestions__row">
                <span
                  v-if="item.share_author_name"
                  class="task-suggestions__author"
                  :class="{ 'task-suggestions__author--active': authorMenu.visible && authorMenu.item === item }"
                  @click.stop="openAuthorMenu($event, item)"
                >{{ item.share_author_name }}</span>
                <span
                  class="task-suggestions__name"
                  @mousedown.prevent
                  @click="selectSuggestion(item)"
                >{{ item.taskname }}</span>
              </div>
            </div>
            <!-- 分享者右键菜单（浮层，独立于搜索结果行） -->
            <teleport to="body">
              <div
                v-if="authorMenu.visible"
                class="author-menu-overlay"
                @click="authorMenu.visible = false"
              ></div>
              <div
                v-if="authorMenu.visible"
                class="author-menu"
                :style="{ left: authorMenu.x + 'px', top: authorMenu.y + 'px' }"
              >
                <div class="author-menu__item" @click="handleAuthorCommand(isSharerPreferred(authorMenu.item?.share_author_name || '') ? 'unprefer' : 'prefer')">{{ isSharerPreferred(authorMenu.item?.share_author_name || '') ? '移除优选' : '加入优质分享者' }}</div>
                <div class="author-menu__item author-menu__item--danger" @click="handleAuthorCommand(isSharerBlocked(authorMenu.item?.share_author_name || '') ? 'unblock' : 'block')">{{ isSharerBlocked(authorMenu.item?.share_author_name || '') ? '取消屏蔽' : '屏蔽此分享者' }}</div>
              </div>
            </teleport>
          </div>
        </el-form-item>
        <el-form-item label="关联 TMDB（可选）">
          <div class="drawer-form__switch-row" style="justify-content: flex-start; gap: 10px; flex-wrap: wrap">
            <el-tag v-if="tmdbBindLabel()" type="success" effect="plain">{{ tmdbBindLabel() }}</el-tag>
            <el-tag v-else type="info" effect="plain">未关联</el-tag>
            <el-button size="small" @click="openTmdbLinkDialog">搜索关联</el-button>
            <el-button size="small" type="danger" plain :disabled="!state.tmdb_id" @click="clearTmdbLink">解除关联</el-button>
          </div>
        </el-form-item>
        <el-form-item label="分享链接">
          <el-input v-model="state.shareurl" placeholder="https://...">
            <template #append>
              <el-button :disabled="!state.shareurl" @click="openSharePicker()">选择文件夹</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="使用模板">
          <el-select v-model="selectedTemplateId" placeholder="选择模板自动填充配置" clearable style="width: 100%" @change="applyTemplate">
            <el-option v-for="t in templateList" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
      </div>

      <div class="drawer-form__section">
        <div class="drawer-form__section-title">搜索筛选</div>
        <el-form-item label="搜索过滤词">
          <el-input v-model="state.addition.search_exclude" placeholder="可选，用 | 分隔，如：预告|花絮">
            <template #append>
              <el-button @click="state.addition.search_exclude_mode = state.addition.search_exclude_mode === 'all' ? '' : 'all'">{{ state.addition.search_exclude_mode === 'all' ? '包含所有' : '包含任意' }}</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="搜索筛选词">
          <el-input v-model="state.addition.search_filter" placeholder="可选，用 | 分隔，如：4k|hdr">
            <template #append>
              <el-button @click="state.addition.search_filter_mode = state.addition.search_filter_mode === 'any' ? '' : 'any'">{{ state.addition.search_filter_mode === 'any' ? '包含任意' : '包含所有' }}</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="搜索起始日期">
          <el-date-picker v-model="state.addition.search_date_from" type="date" value-format="YYYY-MM-DD" placeholder="可选，早于此日期的结果将被过滤" style="width: 100%" clearable :editable="false" />
          <div class="drawer-form__hint">搜索结果发布时间早于此日期的将被过滤不显示</div>
        </el-form-item>
        <el-form-item label="只看优选分享者">
          <el-switch v-model="state.addition.preferred_only" active-text="开启" inactive-text="关闭" />
          <div class="drawer-form__hint">开启后搜索结果只显示优选分享者的内容</div>
        </el-form-item>
        <el-form-item label="显示屏蔽分享者">
          <el-switch v-model="state.addition.show_blocked" active-text="开启" inactive-text="关闭" />
          <div class="drawer-form__hint">开启后搜索结果和自动换链候选中会包含被屏蔽分享者的内容</div>
        </el-form-item>
        <el-form-item v-if="showAutoUpdateToggle" label="自动换链">
          <el-switch v-model="state.auto_update_shareurl" :disabled="!hasRenameRule" active-text="开启" inactive-text="关闭" />
          <div class="drawer-form__hint">任务执行后如果当前进度小于最新进度会寻找拥有更高进度的链接替换转存</div>
          <div v-if="!hasRenameRule" class="drawer-form__hint" style="color: var(--el-color-warning);">请先设置匹配表达式和替换表达式</div>
        </el-form-item>
      </div>

      <div class="drawer-form__section">
        <div class="drawer-form__section-title">文件筛选</div>
        <el-form-item label="关键词过滤">
          <el-select
            v-model="state.addition.filter_rule_name"
            placeholder="选择预设规则（可选）"
            clearable
            @visible-change="(v: boolean) => { if (v) ensureFilterRules() }"
            @change="onFilterRuleChange"
            style="width: 100%"
          >
            <el-option v-for="r in filterRuleOptions" :key="r.name" :label="r.name" :value="r.name" />
          </el-select>
          <el-input
            v-model="state.addition.filter_words"
            placeholder="手动输入关键词，多个用 | 分隔"
            style="margin-top: 6px"
          />
          <div class="drawer-form__hint">文件名包含过滤词的文件不会被转存，选择预设规则会自动填入，也可手动修改</div>
        </el-form-item>
        <el-form-item label="关键词筛选">
          <el-input v-model="state.addition.file_filter" placeholder="可选，用 | 分隔，如：4k|hdr">
            <template #append>
              <el-button @click="state.addition.file_filter_mode = state.addition.file_filter_mode === 'any' ? '' : 'any'">{{ state.addition.file_filter_mode === 'any' ? '包含任意' : '包含所有' }}</el-button>
            </template>
          </el-input>
          <div class="drawer-form__hint">只转存文件名包含关键词的文件，不包含的将被跳过</div>
        </el-form-item>
        <el-form-item label="最小文件大小">
          <el-input v-model="state.addition.min_size" placeholder="可选，如：100MB" />
          <div class="drawer-form__hint">低于此大小的文件不会被转存，支持 B/KB/MB/GB/TB</div>
        </el-form-item>
        <el-form-item label="文件时间过滤">
          <el-date-picker v-model="state.addition.file_min_date" type="date" value-format="YYYY-MM-DD" placeholder="可选，早于此日期的文件将被跳过" style="width: 100%" clearable :editable="false" />
          <div class="drawer-form__hint">自动换链时跳过修改时间早于此日期的文件</div>
          <div style="margin-top: 8px;">
            <el-switch v-model="state.addition.auto_update_file_min_date" active-value="1" inactive-value="" />
            <span style="margin-left: 8px; font-size: 13px; color: var(--el-text-color-regular)">自动更新文件时间过滤</span>
          </div>
          <div class="drawer-form__hint">转存到影视最新集数时，自动将该文件的修改时间写入上方日期，后续只接受更新的文件</div>
        </el-form-item>
      </div>

      <div class="drawer-form__section">
        <div class="drawer-form__section-title">文件夹筛选</div>
        <el-form-item label="文件夹过滤">
          <el-input v-model="state.addition.folder_exclude" placeholder="可选，用 | 分隔，如：预告|花絮">
            <template #append>
              <el-button @click="state.addition.folder_exclude_mode = state.addition.folder_exclude_mode === 'all' ? '' : 'all'">{{ state.addition.folder_exclude_mode === 'all' ? '包含所有' : '包含任意' }}</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="文件夹筛选">
          <el-input v-model="state.addition.folder_filter" placeholder="可选，用 | 分隔，如：hdr|4k">
            <template #append>
              <el-button @click="state.addition.folder_filter_mode = state.addition.folder_filter_mode === 'any' ? '' : 'any'">{{ state.addition.folder_filter_mode === 'any' ? '包含任意' : '包含所有' }}</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="文件夹优先级">
          <el-input v-model="state.addition.folder_priority" placeholder="可选，用 | 分隔，如：d|4k">
            <template #append>
              <el-button @click="state.addition.folder_priority_mode = state.addition.folder_priority_mode === 'any' ? '' : 'any'">{{ state.addition.folder_priority_mode === 'any' ? '包含任意' : '包含所有' }}</el-button>
            </template>
          </el-input>
          <div class="drawer-form__hint">匹配的文件夹将优先转存，未匹配则走默认逻辑</div>
        </el-form-item>
        <el-form-item label="文件夹时间过滤">
          <el-date-picker v-model="state.addition.dir_min_date" type="date" value-format="YYYY-MM-DD" placeholder="可选，早于此日期的文件夹将被跳过" style="width: 100%" clearable :editable="false" />
          <div class="drawer-form__hint">自动换链时跳过自身时间早于此日期的文件夹</div>
        </el-form-item>
      </div>

      <div class="drawer-form__section">
        <div class="drawer-form__section-title">重命名设置</div>
        <el-form-item label="内置规则（可选）">
          <el-select
            v-model="magicRegex.selectedKey"
            style="width: 100%"
            clearable
            :loading="magicRegex.loading"
            placeholder="选择内置规则后会自动填入下方输入框"
            @change="applyMagicRule"
          >
            <el-option v-for="rule in magicRegex.rules" :key="rule.key" :label="rule.label ? `${rule.label}（${rule.key}）` : rule.key" :value="rule.key" />
          </el-select>
          <div class="drawer-form__hint">选择后会把默认 pattern / replace 填入输入框，可继续修改。</div>
        </el-form-item>
        <el-form-item label="匹配表达式（pattern）">
          <el-input v-model="state.pattern" placeholder="$TV_REGEX 或正则表达式" />
          <div v-if="activeMagicRule" class="drawer-form__hint">内置规则实际正则：{{ activeMagicRule.pattern }}</div>
        </el-form-item>
        <el-form-item label="替换表达式（replace）">
          <el-input v-model="state.replace" placeholder="\1E\2.\3" />
        </el-form-item>
      </div>

      <div class="drawer-form__section">
        <div class="drawer-form__section-title">保存设置</div>
        <el-form-item label="保存路径">
          <el-input v-model="state.savepath" placeholder="/剧集/某电视剧">
            <template #append>
              <el-button style="margin-right: -4px" @click="openDrivePicker">选择</el-button>
              <span style="margin: 0 -4px; color: var(--el-border-color)">|</span>
              <el-button style="margin-left: -4px" @click="createSaveDir">新建</el-button>
            </template>
          </el-input>
          <div class="drawer-form__hint">选择目录后点击"新建"可提前创建目录，便于关联同步任务时直接使用</div>
        </el-form-item>
        <div class="drawer-form__switch-row">
          <el-switch v-model="state.ignore_extension" active-text="忽略后缀判重" inactive-text="严格判重" />
        </div>
      </div>

      <div class="drawer-form__section">
        <div class="drawer-form__section-title">关联同步任务</div>
        <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center">
          <el-tag
            v-for="uid in state.sync_task_uids"
            :key="uid"
            closable
            :style="uid.startsWith('__pending_') ? { borderStyle: 'dashed', borderColor: 'var(--el-color-warning)', color: 'var(--el-color-warning)' } : {}"
            @close="removeSyncTaskUid(uid)"
          >{{ sortedSyncTasks.find((t) => t.uid === uid)?.name || uid }}{{ uid.startsWith('__pending_') ? '（待保存）' : '' }}</el-tag>
          <el-button size="small" bg text :disabled="!canSyncWrite" @click="openCreateSyncTask">新建</el-button>
        </div>
        <div class="drawer-form__hint">追剧任务执行成功后会触发已关联的同步任务执行。</div>
      </div>

      <div class="drawer-form__section">
        <div class="drawer-form__section-title">更新与时间</div>
        <el-form-item label="运行星期">
          <div class="drawer-form__switch-row" style="justify-content: flex-start; gap: 10px; flex-wrap: wrap">
            <el-radio-group v-model="state.runweek_mode">
              <el-radio-button label="auto" :disabled="autoRunweekDisabled">自动</el-radio-button>
              <el-radio-button label="manual">手动</el-radio-button>
            </el-radio-group>
            <div v-if="state.runweek_mode === 'auto'" class="drawer-form__hint" style="margin: 0">
              <span v-if="!tmdbLink.configured">请先在系统设置配置 TMDB</span>
              <span v-else-if="autoRunweekText">已识别：{{ autoRunweekText }}</span>
              <span v-else>识别中…</span>
            </div>
          </div>
          <el-checkbox-group v-if="state.runweek_mode === 'manual'" v-model="state.runweek">
            <el-checkbox v-for="item in weekOptions" :key="item.value" :label="item.value">{{ item.label }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </div>

      <div class="drawer-form__section">
        <div class="drawer-form__section-title">插件选项</div>
        <div v-if="!plugins.length" class="empty-copy">暂无插件。</div>
        <div v-else class="plugin-stack">
          <div v-for="plugin in plugins" :key="plugin.plugin_key" class="plugin-block">
            <div class="plugin-block__title">{{ plugin.plugin_key }}</div>
            <el-form-item v-for="field in (plugin.task_config_fields || []).filter(f => !(plugin.plugin_key === 'auto_unarchive' && f.key === 'auto_clean_zipdir'))" :key="field.key" :label="field.label || field.key">
              <el-switch
                v-if="field.input_type === 'switch'"
                v-model="state.addition[plugin.plugin_key][field.key]"
                active-text="开启"
                inactive-text="关闭"
              />
              <el-input-number v-else-if="field.input_type === 'number'" v-model="state.addition[plugin.plugin_key][field.key]" style="width: 100%" />
              <el-input
                v-else-if="field.input_type === 'textarea'"
                v-model="state.addition[plugin.plugin_key][field.key]"
                type="textarea"
                :rows="field.secret ? 4 : 3"
                :placeholder="field.placeholder || ''"
              />
              <el-input
                v-else
                v-model="state.addition[plugin.plugin_key][field.key]"
                :type="field.input_type === 'password' ? 'password' : 'text'"
                :placeholder="field.placeholder || ''"
                :show-password="field.input_type === 'password'"
              />
              <div v-if="field.description" class="drawer-form__hint">{{ field.description }}</div>
            </el-form-item>
          </div>
        </div>
      </div>

    </el-form>

    <template #footer>
      <div class="drawer-form__footer">
        <el-button @click="closeDrawer">取消</el-button>
        <el-button type="success" plain :disabled="submitting" @click="openSaveTemplate">保存为模板</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </div>
    </template>

    <el-dialog v-model="tmdbLink.visible" title="关联 TMDB" :width="isMobile ? '96vw' : '860px'">
      <div v-loading="tmdbLink.loading">
        <div class="drawer-form__switch-row" style="justify-content: flex-start; gap: 10px; flex-wrap: wrap; margin-bottom: 12px">
          <el-select v-model="tmdbLink.type" style="width: 120px">
            <el-option label="电视剧" value="tv" />
            <el-option label="电影" value="movie" />
          </el-select>
          <el-input v-model="tmdbLink.q" placeholder="关键词（默认使用任务名）" style="flex: 1; min-width: 220px" @keyup.enter="runTmdbLinkSearch" />
          <el-input v-model="tmdbLink.year" placeholder="年份(可选)" style="width: 120px" @keyup.enter="runTmdbLinkSearch" />
          <el-button type="primary" :disabled="!tmdbLink.q.trim()" @click="runTmdbLinkSearch">搜索</el-button>
        </div>

        <div v-if="!tmdbLink.configured" class="drawer-form__hint">未配置 TMDB API Key。</div>
        <el-table
          v-else
          :data="tmdbLink.items"
          class="tmdb-link-table"
          style="width: 100%"
          highlight-current-row
          row-key="id"
          @current-change="
            (row) => {
              tmdbLink.selectedId = Number(row?.id) || 0
              if (tmdbLink.selectedId) ensureTmdbLinkDetail(tmdbLink.selectedId)
            }
          "
        >
          <el-table-column label="海报" width="70">
            <template #default="{ row }">
              <el-image
                v-if="posterUrlFromTMDB(row.poster_path)"
                :src="posterUrlFromTMDB(row.poster_path)"
                fit="cover"
                style="width: 48px; height: 72px; border-radius: 6px"
              />
            </template>
          </el-table-column>
          <el-table-column label="影视" min-width="520">
            <template #default="{ row }">
              <div class="title">
                <div class="title__main">{{ tmdbLink.type === 'movie' ? row.title : row.name }}</div>
                <div class="title__sub">
                  <span>{{ tmdbLink.type === 'movie' ? row.release_date : row.first_air_date }}</span>
                  <span v-if="row.vote_average != null"> · {{ Number(row.vote_average).toFixed(1) }}</span>
                </div>
                <div v-if="tmdbLinkRowProgress(row)" class="title__sub">{{ tmdbLinkRowProgress(row) }}</div>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="tmdbLink.configured && !tmdbLink.items.length" class="drawer-form__hint" style="margin-top: 10px">暂无结果。</div>
      </div>
      <template #footer>
        <el-button @click="tmdbLink.visible = false">取消</el-button>
        <el-button type="primary" :disabled="!tmdbLink.selectedId" @click="confirmTmdbLink">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="drivePicker.visible" title="选择保存目录" :width="shareDialogWidth" :fullscreen="isMobile">
      <div class="drawer-form__section" style="margin-bottom: 12px">
        <div class="drawer-form__switch-row">
          <el-button :loading="drivePicker.loading" @click="refreshDrivePicker">刷新</el-button>
          <el-button @click="driveGoRoot">根目录</el-button>
          <el-button v-if="drivePicker.paths.length" @click="driveGoBack">返回上级</el-button>
          <el-button type="primary" @click="useCurrentDrivePath(false)">当前文件夹</el-button>
          <el-button v-if="state.taskname.trim()" type="primary" @click="useCurrentDrivePath(true)">当前文件夹/{{ driveSavepathHint() }}</el-button>
        </div>
        <div class="drawer-form__hint" style="margin-top: 10px">当前路径：{{ currentDrivePathLabel() }}</div>
        <el-breadcrumb v-if="drivePicker.paths.length" separator="/">
          <el-breadcrumb-item>
            <a href="#" @click.prevent="driveGoRoot">/</a>
          </el-breadcrumb-item>
          <el-breadcrumb-item v-for="(item, idx) in drivePicker.paths" :key="item.fid">
            <a
              v-if="idx !== drivePicker.paths.length - 1"
              href="#"
              @click.prevent="driveNavigateTo(item.fid, item.name, { sliceToIndex: idx })"
            >
              {{ item.name }}
            </a>
            <span v-else class="text-muted">{{ item.name }}</span>
          </el-breadcrumb-item>
        </el-breadcrumb>
        <div v-if="isMobile" style="display: flex; justify-content: flex-end; margin-top: 10px">
          <el-select v-model="drivePicker.mobileSort" size="small" style="width: 150px" @change="applyDriveMobileSort">
            <el-option label="文件名 ↑" value="file_name:asc" />
            <el-option label="文件名 ↓" value="file_name:desc" />
            <el-option label="修改日期 ↑" value="updated_at:asc" />
            <el-option label="修改日期 ↓" value="updated_at:desc" />
          </el-select>
        </div>
      </div>
      <el-table
        :data="drivePicker.items"
        v-loading="drivePicker.loading"
        size="small"
        style="width: 100%"
        @row-click="enterDriveDir"
        @sort-change="onDriveSortChange"
      >
        <el-table-column prop="file_name" label="文件名" min-width="260" sortable="custom">
          <template #default="{ row }">
            <span>{{ row.file_name || row.name }}</span>
            <el-tag v-if="row.is_dir" size="small" type="info" style="margin-left: 8px">目录</el-tag>
            <el-tag v-else size="small" type="success" style="margin-left: 8px">文件</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="130">
          <template #default="{ row }">
            <span v-if="row.is_dir">{{ row.include_items != null ? `${row.include_items}项` : '-' }}</span>
            <span v-else>{{ formatSize(row.size) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="修改日期" width="170" sortable="custom">
          <template #default="{ row }">
            <span>{{ formatTs(row.updated_at) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <el-dialog v-model="sharePicker.visible" title="选择需转存的文件夹" :width="isMobile ? '96vw' : '70vw'" :fullscreen="false" class="share-picker-dialog">
      <div style="flex-shrink: 0">
        <div v-if="sharePicker.sharerName" style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px">
          <span style="font-size: 13px; color: var(--el-text-color-secondary)">分享者：</span>
          <el-tag :type="sharePicker.isPreferredSharer ? 'success' : 'info'">{{ sharePicker.sharerName }}</el-tag>
          <el-button v-if="isSharerPreferred(sharePicker.sharerName)" size="small" type="info" plain @click="removeSharerFromPreferred(sharePicker.sharerName)">移除优选</el-button>
          <el-button v-else size="small" type="success" plain @click="addSharerToPreferred(sharePicker.sharerName)">加入优选</el-button>
          <el-button v-if="isSharerBlocked(sharePicker.sharerName)" size="small" type="info" plain @click="removeSharerFromBlocked(sharePicker.sharerName)">取消屏蔽</el-button>
          <el-button v-else size="small" type="danger" plain @click="addSharerToBlocked(sharePicker.sharerName)">屏蔽</el-button>
        </div>
        <div v-if="sharePicker.stack.length" style="font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px">
          当前路径：/{{ sharePicker.stack.filter((x) => x.name !== '当前目录').map((x) => x.name).join('/') }}
        </div>
      </div>
      <el-table :data="sharePicker.items" v-loading="sharePicker.loading" size="small" style="width: 100%" max-height="55vh" @row-click="onShareRowClick">
        <el-table-column label="名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ row.file_name || row.name }}</span>
            <el-tag v-if="row.is_dir" size="small" type="info" style="margin-left: 6px">目录</el-tag>
            <el-tag v-else size="small" type="success" style="margin-left: 6px">文件</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="110" align="right">
          <template #default="{ row }">
            <span v-if="row.is_dir">{{ (row.include_items ?? row.children_count) != null ? `${row.include_items ?? row.children_count}项` : '-' }}</span>
            <span v-else>{{ formatSize(row.size) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="正则处理" min-width="200" sortable :sort-method="sortFileNameRe" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.file_name_re" style="color: var(--el-color-success)">{{ row.file_name_re }}</span>
            <span v-else-if="row.file_name_saved" style="color: var(--el-color-danger)">× {{ row.file_name_saved }}</span>
            <span v-else-if="row.filtered_by_size" style="color: var(--el-color-danger)">× 大小小于阈值</span>
            <span v-else-if="row.filtered_by_keyword" style="color: var(--el-color-danger)">× 匹配过滤词</span>
            <span v-else-if="row.filtered_by_file_filter" style="color: var(--el-color-danger)">× 不包含筛选词</span>
            <span v-else-if="row.filtered_by_file_date" style="color: var(--el-color-danger)">× 早于文件时间过滤</span>
            <span v-else-if="row.filtered_by_folder" style="color: var(--el-color-danger)">× {{ row.filtered_by_folder }}</span>
            <span v-else-if="row.filtered_by_search" style="color: var(--el-color-danger)">× 不匹配筛选规则</span>
            <span v-else-if="row.dir && row.priority_match" style="color: var(--el-color-warning)">优先</span>
            <span v-else-if="row.dir"></span>
            <span v-else style="color: var(--el-color-danger)">x</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="150" sortable :sort-method="sortUpdatedAt">
          <template #default="{ row }">
            <span>{{ formatTs(row.updated_at) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 8px">
          <el-button v-if="sharePicker.stack.length" @click="goShareBack">返回上级</el-button>
          <el-button type="primary" @click="pickShareFolderCurrent">使用当前文件夹</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 新建同步任务弹窗 -->
    <el-dialog v-model="createSyncDialog.visible" title="新建同步任务" width="500px" append-to-body>
      <el-form label-position="top">
        <el-form-item label="同步任务名称">
          <el-input v-model="createSyncDialog.name" placeholder="例如：媒体库同步" />
        </el-form-item>
        <el-form-item label="模式">
          <el-radio-group v-model="createSyncDialog.mode">
            <el-radio-button label="one_way">单向</el-radio-button>
            <el-radio-button label="two_way" disabled>双向</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-divider content-position="left">源端点</el-divider>
        <el-form-item label="类型">
          <el-select v-model="createSyncDialog.sourceType" style="width: 100%">
            <el-option label="OpenList" value="openlist" />
            <el-option label="本地" value="local" />
          </el-select>
        </el-form-item>
        <el-form-item label="路径">
          <el-input v-model="createSyncDialog.sourcePath" placeholder="OpenList: /xxx  本地: 相对 data/sync 的路径">
            <template #append>
              <el-button @click="openSyncPathPicker('source')">选择</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-divider content-position="left">目标端点</el-divider>
        <el-form-item label="类型">
          <el-select v-model="createSyncDialog.targetType" style="width: 100%">
            <el-option label="OpenList" value="openlist" />
            <el-option label="本地" value="local" />
          </el-select>
        </el-form-item>
        <el-form-item label="路径">
          <el-input v-model="createSyncDialog.targetPath" placeholder="OpenList: /xxx  本地: 相对 data/sync 的路径">
            <template #append>
              <el-button @click="openSyncPathPicker('target')">选择</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-divider content-position="left">策略</el-divider>
        <el-form-item label="覆盖已存在文件">
          <el-switch v-model="createSyncDialog.overwrite" />
        </el-form-item>
        <el-form-item v-if="createSyncDialog.mode === 'one_way'" label="删除目标端多余文件">
          <el-switch v-model="createSyncDialog.one_way_delete_extras" />
        </el-form-item>
        <el-form-item label="强制刷新（不使用缓存）">
          <el-switch v-model="createSyncDialog.force_refresh" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createSyncDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="createSyncDialog.submitting" :disabled="!canSyncWrite" @click="submitCreateSyncTask">创建并关联</el-button>
      </template>
    </el-dialog>

    <!-- 同步任务路径选择器 -->
    <el-dialog v-model="syncPathPicker.visible" title="选择路径" width="600px" append-to-body>
      <div style="display: flex; flex-direction: column; gap: 12px">
        <div style="display: flex; align-items: center; gap: 8px">
          <el-button size="small" @click="syncPathPicker.dirPath = syncPathPicker.endpointType === 'openlist' ? '/' : ''; refreshSyncPathPicker()">根目录</el-button>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item v-for="(p, idx) in syncPathPicker.paths" :key="idx">
              <span style="cursor: pointer" @click="pickSyncPath(p.path)">{{ p.name }}</span>
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <el-table
          :data="syncPathPicker.items.filter((x: any) => x.is_dir)"
          size="small"
          max-height="300px"
          v-loading="syncPathPicker.loading"
          @row-dblclick="(row: any) => enterSyncPickerDir(row)"
        >
          <el-table-column label="文件夹名称" min-width="300">
            <template #default="{ row }">
              <span style="cursor: pointer" @click="enterSyncPickerDir(row)">📁 {{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="修改时间" width="160">
            <template #default="{ row }">{{ row.updated_at ? formatTs(row.updated_at) : '-' }}</template>
          </el-table-column>
        </el-table>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <div style="font-size: 13px; color: var(--el-text-color-secondary)">当前路径：{{ syncPathPicker.dirPath || '/' }}</div>
          <div>
            <el-button @click="syncPathPicker.visible = false">取消</el-button>
            <el-button type="primary" @click="useSyncPickerPath">使用此路径</el-button>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 保存模板弹窗 -->
    <el-dialog v-model="saveTemplateDialogVisible" title="保存为模板" width="400px" append-to-body>
      <el-form label-position="top">
        <el-form-item label="模板名称">
          <el-input v-model="saveTemplateName" placeholder="例如：4K HDR 追剧模板" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="saveTemplateDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitSaveTemplate">保存</el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<style scoped>
.drawer-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.drawer-form__section {
  position: relative;
  margin-top: 48px;
  padding: 18px;
  border-radius: 20px;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
}

.drawer-form__section-title {
  position: relative;
  margin-top: -50px;
  margin-bottom: 24px;
  margin-left: -18px;
  font-size: 16px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.drawer-custom-title {
  font-size: 18px;
  font-weight: 700;
  text-align: center;
  width: 100%;
}

:deep(.el-drawer__header) {
  margin-bottom: 0;
  padding: 16px 20px;
}

:deep(.el-drawer__close-btn) {
  display: none;
}

.drawer-form__switch-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.drawer-form__hint {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
:deep(.el-form-item__label) {
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.task-suggestions {
  margin-top: 10px;
  padding: 10px;
  border-radius: 14px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-blank);
  max-height: 260px;
  overflow-x: auto;
  overflow-y: auto;
}

.task-suggestions__tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 2px 4px 8px 4px;
}

.task-suggestions__item {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 4px 6px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.3;
  min-width: max-content;
  pointer-events: none;
}

.task-suggestions__item .task-suggestions__row {
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.task-suggestions__name {
  pointer-events: auto;
  cursor: pointer;
  border-radius: 4px;
  padding: 0 2px;
}

.task-suggestions__name:hover {
  background: var(--el-fill-color-light);
}

.task-suggestions__name:active {
  background: var(--el-fill-color);
}

.task-suggestions__icon {
  flex-shrink: 0;
  width: 16px;
  text-align: center;
  font-size: 11px;
}

.task-suggestions__name {
  font-weight: 500;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.task-suggestions__time {
  font-size: 9px;
  color: var(--el-text-color-placeholder);
  white-space: nowrap;
}

.task-suggestions__url-short {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--el-text-color-placeholder);
  font-family: monospace;
  white-space: nowrap;
}

.drawer-form__footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  width: 100%;
}

.plugin-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.plugin-block {
  padding: 14px;
  border-radius: 16px;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
}

.plugin-block__title {
  font-weight: 600;
  margin-bottom: 10px;
  color: var(--el-text-color-primary);
}

:deep(.tmdb-link-table .el-table__cell .cell) {
  white-space: normal;
}

:deep(.tmdb-link-table .title__main) {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

:deep(.tmdb-link-table .title__sub) {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
  margin-top: 2px;
}

/* 选中结果高亮 */
.task-suggestions__item--selected {
  background-color: var(--el-color-primary-light-9);
}

/* 分享者名字样式：独立小标签 */
.task-suggestions__author {
  pointer-events: auto;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-right: 4px;
  padding: 1px 6px;
  border-radius: 4px;
  border: none;
  background-color: var(--el-color-primary-light-9);
  cursor: pointer;
  transition: background-color 0.15s;
  font-family: inherit;
  line-height: inherit;
}
.task-suggestions__author:hover {
  background-color: var(--el-color-primary-light-8);
}
.task-suggestions__author:active {
  background-color: var(--el-color-primary-light-8);
  -webkit-tap-highlight-color: transparent;
}
.task-suggestions__author--active {
  color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-8);
}

:deep(.share-picker-dialog .el-dialog) {
  max-height: 75vh;
  display: flex;
  flex-direction: column;
}
:deep(.share-picker-dialog .el-dialog__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 分享者菜单浮层 */
.author-menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
}
.author-menu {
  position: fixed;
  z-index: 10000;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 4px 0;
  box-shadow: 0 4px 12px rgba(0,0,0,0.12);
  min-width: 140px;
}
.author-menu__item {
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
  color: var(--el-text-color-regular);
  transition: background-color 0.1s;
}
.author-menu__item:hover {
  background-color: var(--el-fill-color-light);
}
.author-menu__item--danger {
  color: var(--el-color-danger);
}
.author-menu__item--danger:hover {
  background-color: var(--el-color-danger-light-9);
}
</style>
