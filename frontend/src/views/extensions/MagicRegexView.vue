<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'

import { deleteMagicRegexRule, fetchMagicRegexRules, upsertMagicRegexRule } from '@/api/magicRegex'
import { fetchOpenListConfig, patchOpenListConfig } from '@/api/openlist'
import { fetchResourceSearchSources, patchResourceSearchSource } from '@/api/resourceSearch'
import { fetchTMDBConfig, patchTMDBConfig } from '@/api/tmdb'
import { fetchTaskTemplates, createTaskTemplate, updateTaskTemplate, deleteTaskTemplate } from '@/api/taskTemplates'
import type { TaskTemplate } from '@/api/taskTemplates'
import { TASK_WRITE } from '@/constants/permissions'
import { useAuthStore } from '@/stores/auth'
import type { MagicRegexRuleSetting } from '@/types/magicRegex'
import type { OpenListConfig } from '@/types/openlist'
import type { ResourceSearchSourceItem } from '@/types/resourceSearch'
import type { TMDBConfig } from '@/types/tmdb'

const auth = useAuthStore()
const canWrite = computed(() => auth.permissions.includes(TASK_WRITE))

const loading = ref(false)
const rules = ref<MagicRegexRuleSetting[]>([])
const variables = ref<Record<string, string>>({})
const activeTab = ref('magic_regex')

const templates = reactive({
  loading: false,
  list: [] as TaskTemplate[],
  dialogVisible: false,
  editingId: null as number | null,
  form: {
    name: '',
    config: {} as Record<string, any>,
  },
  // 内置规则
  magicRegex: {
    loading: false,
    selectedKey: '',
    rules: [] as Array<{ key: string; label: string; pattern: string; replace: string }>,
  },
  // 关键词过滤预设
  filterWords: {
    options: [] as Array<{ name: string; keywords: string }>,
  },
})

const TEMPLATE_FIELDS = [
  { key: 'search_filter', label: '搜索筛选词', type: 'keyword', hint: '搜索结果标题必须包含这些词才会显示，用 | 分隔' },
  { key: 'search_exclude', label: '搜索过滤词', type: 'keyword', hint: '搜索结果标题包含这些词将被过滤，用 | 分隔' },
  { key: 'folder_filter', label: '文件夹筛选', type: 'keyword', hint: '只转存文件夹名称包含这些词的目录，用 | 分隔' },
  { key: 'folder_exclude', label: '文件夹过滤', type: 'keyword', hint: '跳过文件夹名称包含这些词的目录，用 | 分隔' },
  { key: 'auto_update_file_min_date', label: '自动更新文件时间过滤', type: 'switch', hint: '追剧进度追上最新集数时自动更新文件时间过滤' },
  { key: 'filter_words', label: '关键词过滤', type: 'filter_words', hint: '转存时过滤掉文件名包含这些关键词的文件' },
  { key: 'file_filter', label: '关键词筛选', type: 'keyword', hint: '只转存文件名包含这些关键词的文件，用 | 分隔' },
  { key: 'min_size', label: '最小文件大小', type: 'text', hint: '小于此大小的文件将被过滤，如：100MB' },
]

const resourceSearch = reactive({
  loading: false,
  savingKey: '' as string,
  selectedSource: 'pansou' as 'pansou' | 'cloudsaver',
  cloudsaver: {
    enabled: false,
    server: '',
    username: '',
    token: '',
    passwordInput: '',
  },
  pansou: {
    enabled: false,
    server: '',
  },
})

const tmdb = reactive({
  loading: false,
  saving: false,
  hasApiKey: false,
  language: 'zh-CN',
  posterLanguage: 'zh-CN',
  apiKeyInput: '',
  enableGuessitFallbackRename: true,
  tvRenameTemplate: '{title}.S{season}E{episode}{ext}',
  movieRenameTemplate: '{title_dot}.{year}{ext}',
})

const openlist = reactive({
  loading: false,
  saving: false,
  url: '',
  hasToken: false,
  tokenInput: '',
})

const sharerFilter = reactive({
  loading: false,
  saving: false,
  preferred: [] as string[],
  blocked: [] as string[],
  validate_batch_size: 5,
  preview_cache_ttl_seconds: 300,
})

const sharerDialog = reactive({
  visible: false,
  type: 'preferred' as 'preferred' | 'blocked',
  inputValue: '',
})

const filterRules = reactive({
  loading: false,
  rules: [] as Array<{ name: string; keywords: string }>,
  dialogVisible: false,
  editIndex: -1,
  form: { name: '', keywords: '' },
})

const builtinKeySet = computed(() => new Set(rules.value.filter((r) => r.built_in).map((r) => r.key)))
const currentIsBuiltinKey = computed(() => builtinKeySet.value.has(normalizeKey(dialog.form.key)))

const dialog = reactive({
  visible: false,
  submitting: false,
  isEdit: false,
  keyLocked: false,
  form: {
    key: '',
    label: '' as string | null,
    enabled: true,
    pattern: '',
    replace: '',
  },
})

function normalizeKey(key: string) {
  return String(key || '').trim()
}

function isValidKey(key: string) {
  const value = normalizeKey(key)
  return value.startsWith('$') && !value.includes(' ') && value.length <= 64
}

async function refresh() {
  loading.value = true
  try {
    const data = await fetchMagicRegexRules()
    rules.value = data.rules || []
    variables.value = data.variables || {}
  } finally {
    loading.value = false
  }
}

function findSource(list: ResourceSearchSourceItem[], key: string) {
  return list.find((x) => x.key === key) || null
}

function applySources(list: ResourceSearchSourceItem[]) {
  const cs = findSource(list, 'cloudsaver')
  if (cs) {
    resourceSearch.cloudsaver.enabled = Boolean(cs.enabled)
    resourceSearch.cloudsaver.server = String(cs.server || '')
    resourceSearch.cloudsaver.username = String(cs.username || '')
    resourceSearch.cloudsaver.token = String(cs.token || '')
  }
  const ps = findSource(list, 'pansou')
  if (ps) {
    resourceSearch.pansou.enabled = Boolean(ps.enabled)
    resourceSearch.pansou.server = String(ps.server || '')
  }
  // 默认选中已启用的搜索源
  if (resourceSearch.cloudsaver.enabled) {
    resourceSearch.selectedSource = 'cloudsaver'
  } else {
    resourceSearch.selectedSource = 'pansou'
  }
}

async function refreshSources() {
  resourceSearch.loading = true
  try {
    const data = await fetchResourceSearchSources()
    applySources(data.sources || [])
  } finally {
    resourceSearch.loading = false
  }
}

function applyTMDBConfig(data: TMDBConfig) {
  tmdb.hasApiKey = Boolean(data.has_api_key)
  tmdb.language = String(data.language || 'zh-CN')
  tmdb.posterLanguage = String(data.poster_language || 'zh-CN')
  tmdb.enableGuessitFallbackRename = !Boolean(data.disable_guessit_tmdb_fallback_rename)
  tmdb.tvRenameTemplate = String(data.guessit_tmdb_tv_rename_template || '{title}.S{season}E{episode}{ext}')
  tmdb.movieRenameTemplate = String(data.guessit_tmdb_movie_rename_template || '{title_dot}.{year}{ext}')
}

async function refreshTMDB() {
  tmdb.loading = true
  try {
    const data = await fetchTMDBConfig()
    applyTMDBConfig(data)
  } finally {
    tmdb.loading = false
  }
}

function applyOpenListConfig(data: OpenListConfig) {
  openlist.url = String(data.url || '')
  openlist.hasToken = Boolean(data.has_token)
}

async function refreshOpenList() {
  openlist.loading = true
  try {
    const data = await fetchOpenListConfig()
    applyOpenListConfig(data)
  } finally {
    openlist.loading = false
  }
}

async function saveOpenList() {
  if (!canWrite.value) return
  openlist.saving = true
  try {
    const payload: any = {
      url: openlist.url ? String(openlist.url).trim() : null,
    }
    const token = String(openlist.tokenInput || '').trim()
    if (token) payload.token = token
    const data = await patchOpenListConfig(payload)
    openlist.tokenInput = ''
    applyOpenListConfig(data)
    ElMessage.success('已保存')
  } finally {
    openlist.saving = false
  }
}

function removeSharer(name: string) {
  if (sharerDialog.type === 'preferred') {
    sharerFilter.preferred = sharerFilter.preferred.filter((x) => x !== name)
  } else {
    sharerFilter.blocked = sharerFilter.blocked.filter((x) => x !== name)
  }
}

function addSharerFromInput() {
  const raw = (sharerDialog.inputValue || '').trim()
  if (!raw) return
  const names = raw.split('|').map((s: string) => s.trim()).filter(Boolean)
  if (sharerDialog.type === 'preferred') {
    for (const name of names) {
      if (!sharerFilter.preferred.includes(name)) sharerFilter.preferred.push(name)
    }
  } else {
    for (const name of names) {
      if (!sharerFilter.blocked.includes(name)) sharerFilter.blocked.push(name)
    }
  }
  sharerDialog.inputValue = ''
}

async function loadSharerFilter() {
  sharerFilter.loading = true
  try {
    const { fetchSharerFilterSettings } = await import('@/api/systemSettings')
    const data = await fetchSharerFilterSettings()
    sharerFilter.preferred = (data.preferred_sharers || '').split('|').map((s: string) => s.trim()).filter(Boolean)
    sharerFilter.blocked = (data.blocked_sharers || '').split('|').map((s: string) => s.trim()).filter(Boolean)
    sharerFilter.validate_batch_size = data.validate_batch_size || 5
    sharerFilter.preview_cache_ttl_seconds = data.preview_cache_ttl_seconds || 300
  } finally {
    sharerFilter.loading = false
  }
}

async function saveSharerFilter() {
  if (!canWrite.value) return
  sharerFilter.saving = true
  try {
    const { updateSharerFilterSettings } = await import('@/api/systemSettings')
    const payload = {
      preferred_sharers: sharerFilter.preferred.join('|') || null,
      blocked_sharers: sharerFilter.blocked.join('|') || null,
      validate_batch_size: Number(sharerFilter.validate_batch_size) || 5,
      preview_cache_ttl_seconds: Number(sharerFilter.preview_cache_ttl_seconds) || 300,
    }
    const data = await updateSharerFilterSettings(payload)
    sharerFilter.preferred = (data.preferred_sharers || '').split('|').map((s: string) => s.trim()).filter(Boolean)
    sharerFilter.blocked = (data.blocked_sharers || '').split('|').map((s: string) => s.trim()).filter(Boolean)
    sharerFilter.validate_batch_size = data.validate_batch_size || 5
    sharerFilter.preview_cache_ttl_seconds = data.preview_cache_ttl_seconds || 300
    ElMessage.success('已保存')
  } finally {
    sharerFilter.saving = false
  }
}

async function loadFilterRules() {
  filterRules.loading = true
  try {
    const { fetchFilterRules } = await import('@/api/systemSettings')
    filterRules.rules = await fetchFilterRules()
  } finally {
    filterRules.loading = false
  }
}

function openFilterRuleDialog(index: number) {
  if (index >= 0) {
    filterRules.editIndex = index
    filterRules.form = { ...filterRules.rules[index] }
  } else {
    filterRules.editIndex = -1
    filterRules.form = { name: '', keywords: '' }
  }
  filterRules.dialogVisible = true
}

async function saveFilterRule() {
  const name = filterRules.form.name.trim()
  if (!name) return ElMessage.warning('请输入名称')
  const rules = [...filterRules.rules]
  if (filterRules.editIndex >= 0) {
    rules[filterRules.editIndex] = { ...filterRules.form }
  } else {
    if (rules.some((r) => r.name === name)) return ElMessage.warning('名称已存在')
    rules.push({ ...filterRules.form })
  }
  try {
    const { saveFilterRules } = await import('@/api/systemSettings')
    filterRules.rules = await saveFilterRules(rules)
    filterRules.dialogVisible = false
    ElMessage.success('已保存')
  } catch { ElMessage.error('保存失败') }
}

async function deleteFilterRule(index: number) {
  const name = filterRules.rules[index]?.name || ''
  await ElMessageBox.confirm(`确定删除过滤词规则「${name}」？`, '删除确认', { type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消' })
  const rules = filterRules.rules.filter((_, i) => i !== index)
  try {
    const { saveFilterRules } = await import('@/api/systemSettings')
    filterRules.rules = await saveFilterRules(rules)
    ElMessage.success('已删除')
  } catch { ElMessage.error('删除失败') }
}

async function saveTMDB() {
  if (!canWrite.value) return
  tmdb.saving = true
  try {
    const payload: any = {
      language: tmdb.language ? String(tmdb.language).trim() : null,
      poster_language: tmdb.posterLanguage ? String(tmdb.posterLanguage).trim() : null,
      disable_guessit_tmdb_fallback_rename: !Boolean(tmdb.enableGuessitFallbackRename),
      guessit_tmdb_tv_rename_template: tmdb.tvRenameTemplate ? String(tmdb.tvRenameTemplate).trim() : null,
      guessit_tmdb_movie_rename_template: tmdb.movieRenameTemplate ? String(tmdb.movieRenameTemplate).trim() : null,
    }
    const apiKey = String(tmdb.apiKeyInput || '').trim()
    if (apiKey) payload.api_key = apiKey
    const data = await patchTMDBConfig(payload)
    tmdb.apiKeyInput = ''
    applyTMDBConfig(data)
    ElMessage.success('已保存')
  } finally {
    tmdb.saving = false
  }
}

function useDefaultRenameTemplates() {
  tmdb.tvRenameTemplate = '{title}.S{season}E{episode}{ext}'
  tmdb.movieRenameTemplate = '{title_dot}.{year}{ext}'
}

async function saveSource(key: 'cloudsaver' | 'pansou') {
  if (!canWrite.value) return
  resourceSearch.savingKey = key
  try {
    if (key === 'pansou') {
      await patchResourceSearchSource('pansou', {
        enabled: Boolean(resourceSearch.pansou.enabled),
        server: resourceSearch.pansou.server ? String(resourceSearch.pansou.server).trim() : null,
      })
      ElMessage.success('已保存')
      await refreshSources()
      return
    }

    const payload: any = {
      enabled: Boolean(resourceSearch.cloudsaver.enabled),
      server: resourceSearch.cloudsaver.server ? String(resourceSearch.cloudsaver.server).trim() : null,
      username: resourceSearch.cloudsaver.username ? String(resourceSearch.cloudsaver.username).trim() : null,
    }
    const pw = String(resourceSearch.cloudsaver.passwordInput || '')
    if (pw.trim()) payload.password = pw
    await patchResourceSearchSource('cloudsaver', payload)
    resourceSearch.cloudsaver.passwordInput = ''
    ElMessage.success('已保存')
    await refreshSources()
  } finally {
    resourceSearch.savingKey = ''
  }
}

function openCreate() {
  dialog.visible = true
  dialog.submitting = false
  dialog.isEdit = false
  dialog.keyLocked = false
  dialog.form.key = '$'
  dialog.form.label = null
  dialog.form.enabled = true
  dialog.form.pattern = ''
  dialog.form.replace = ''
}

function openEdit(rule: MagicRegexRuleSetting) {
  dialog.visible = true
  dialog.submitting = false
  dialog.isEdit = true
  dialog.keyLocked = true
  dialog.form.key = rule.key
  dialog.form.label = rule.label ?? null
  dialog.form.enabled = Boolean(rule.enabled)
  dialog.form.pattern = rule.pattern || ''
  dialog.form.replace = rule.replace || ''
}

async function submit() {
  const key = normalizeKey(dialog.form.key)
  if (!isValidKey(key)) {
    ElMessage.warning('key 必须以 $ 开头，且不能包含空格（最长 64）')
    return
  }
  if (!dialog.isEdit) {
    if (!String(dialog.form.pattern || '').trim()) {
      ElMessage.warning('新增规则时 pattern 不能为空')
      return
    }
  }
  dialog.submitting = true
  try {
    const data = await upsertMagicRegexRule(key, {
      label: dialog.form.label ? String(dialog.form.label).trim() : null,
      enabled: Boolean(dialog.form.enabled),
      pattern: String(dialog.form.pattern || '').trim() || null,
      replace: String(dialog.form.replace || ''),
    })
    rules.value = data.rules || []
    dialog.visible = false
    ElMessage.success('已保存')
  } finally {
    dialog.submitting = false
  }
}

async function removeRule(rule: MagicRegexRuleSetting) {
  if (!canWrite.value) return
  const title = rule.built_in ? '恢复默认规则' : '删除自定义规则'
  const message = rule.built_in
    ? `将清除对 ${rule.key} 的覆盖配置，恢复为系统默认值。`
    : `将删除 ${rule.key} 规则。`
  try {
    await ElMessageBox.confirm(message, title, { type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消' })
  } catch {
    return
  }
  const data = await deleteMagicRegexRule(rule.key)
  rules.value = data.rules || []
  ElMessage.success('已更新')
}

const builtinRules = computed(() => rules.value.filter((r) => r.built_in))
const customRules = computed(() => rules.value.filter((r) => !r.built_in))

async function loadTemplates() {
  templates.loading = true
  try {
    templates.list = await fetchTaskTemplates()
  } finally {
    templates.loading = false
  }
}

function openTemplateCreate() {
  templates.editingId = null
  templates.form = { name: '', config: {} }
  templates.magicRegex.selectedKey = ''
  templates.dialogVisible = true
  loadMagicRegexRules()
  loadFilterWordsOptions()
}

function openTemplateEdit(template: TaskTemplate) {
  templates.editingId = template.id
  templates.form = { name: template.name, config: { ...template.config } }
  const patternKey = template.config.pattern || ''
  const filterRuleName = template.config.filter_rule_name || ''
  templates.magicRegex.selectedKey = ''
  templates.dialogVisible = true
  // 加载内置规则和关键词预设
  Promise.all([loadMagicRegexRules(), loadFilterWordsOptions()]).then(() => {
    // 如果 pattern 是 key（以 $ 开头），选中对应的内置规则并填充实际正则
    if (patternKey.startsWith('$')) {
      templates.magicRegex.selectedKey = patternKey
      const rule = templates.magicRegex.rules.find(r => r.key === patternKey)
      if (rule) {
        templates.form.config.pattern = rule.pattern || ''
        templates.form.config.replace = rule.replace || ''
      }
    }
    // 如果有 filter_rule_name，填充关键词显示
    if (filterRuleName) {
      const opt = templates.filterWords.options.find(o => o.name === filterRuleName)
      if (opt) {
        templates.form.config.filter_words = opt.keywords
      }
    }
  })
}

async function loadMagicRegexRules() {
  templates.magicRegex.loading = true
  try {
    const data = await fetchMagicRegexRules()
    templates.magicRegex.rules = (data.rules || []).filter((r: any) => r.enabled !== false).map((r: any) => ({
      key: r.key,
      label: r.label || r.key,
      pattern: r.pattern || '',
      replace: r.replace || '',
    }))
  } finally {
    templates.magicRegex.loading = false
  }
}

function applyMagicRule(key: string) {
  if (!key) {
    templates.magicRegex.selectedKey = ''
    templates.form.config.pattern = ''
    templates.form.config.replace = ''
    return
  }
  const rule = templates.magicRegex.rules.find(r => r.key === key)
  if (!rule) return
  templates.magicRegex.selectedKey = key
  templates.form.config.pattern = rule.pattern || ''
  templates.form.config.replace = rule.replace || ''
}

function onFilterRuleSelect(name: string) {
  if (!name) {
    templates.form.config.filter_words = ''
    return
  }
  const opt = templates.filterWords.options.find(o => o.name === name)
  if (opt) {
    templates.form.config.filter_words = opt.keywords
  }
}

async function loadFilterWordsOptions() {
  try {
    const { fetchFilterRules } = await import('@/api/systemSettings')
    const data = await fetchFilterRules()
    templates.filterWords.options = data || []
  } catch {
    templates.filterWords.options = []
  }
}

function toggleKeywordMode(key: string) {
  const modeMap: Record<string, string> = {
    'search_filter': 'search_filter_mode',
    'search_exclude': 'search_exclude_mode',
    'folder_filter': 'folder_filter_mode',
    'folder_exclude': 'folder_exclude_mode',
    'file_filter': 'file_filter_mode',
  }
  const modeKey = modeMap[key]
  if (!modeKey) return
  
  const currentMode = templates.form.config[modeKey] || ''
  if (key.includes('exclude')) {
    templates.form.config[modeKey] = currentMode === 'all' ? '' : 'all'
  } else {
    templates.form.config[modeKey] = currentMode === 'any' ? '' : 'any'
  }
}

function getKeywordModeLabel(key: string): string {
  const modeMap: Record<string, string> = {
    'search_filter': 'search_filter_mode',
    'search_exclude': 'search_exclude_mode',
    'folder_filter': 'folder_filter_mode',
    'folder_exclude': 'folder_exclude_mode',
    'file_filter': 'file_filter_mode',
  }
  const modeKey = modeMap[key]
  if (!modeKey) return '包含所有'
  
  const currentMode = templates.form.config[modeKey] || ''
  if (key.includes('exclude')) {
    return currentMode === 'all' ? '包含所有' : '包含任意'
  } else {
    return currentMode === 'any' ? '包含任意' : '包含所有'
  }
}

async function submitTemplate() {
  if (!templates.form.name.trim()) return ElMessage.warning('请输入模板名称')
  // 如果选择了内置规则，保存 key 而不是实际正则
  const configToSave = { ...templates.form.config }
  if (templates.magicRegex.selectedKey) {
    configToSave.pattern = templates.magicRegex.selectedKey
  }
  try {
    if (templates.editingId) {
      await updateTaskTemplate(templates.editingId, { name: templates.form.name, config: configToSave })
      ElMessage.success('模板已更新')
    } else {
      await createTaskTemplate({ name: templates.form.name, config: configToSave })
      ElMessage.success('模板已创建')
    }
    templates.dialogVisible = false
    await loadTemplates()
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
  }
}

async function removeTemplate(template: TaskTemplate) {
  try {
    await ElMessageBox.confirm(`确定删除模板"${template.name}"？`, '删除模板', { type: 'warning' })
    await deleteTaskTemplate(template.id)
    ElMessage.success('已删除')
    await loadTemplates()
  } catch {}
}

onMounted(() => {
  refresh()
  refreshSources()
  refreshTMDB()
  refreshOpenList()
  loadSharerFilter()
  loadFilterRules()
  loadTemplates()
})
</script>

<template>
  <div class="page">
    <div class="page__header">
      <div class="page__title">系统设置</div>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="保存规则" name="magic_regex">
        <el-card class="page__card" shadow="never">
          <template #header>
            <div class="card__header">
              <div>任务模板</div>
              <el-button type="primary" size="small" :disabled="!canWrite" @click="openTemplateCreate">新增模板</el-button>
            </div>
          </template>
          <el-table :data="templates.list" :loading="templates.loading" style="width: 100%">
            <el-table-column prop="name" label="模板名称" />
            <el-table-column label="操作" width="160" fixed="right">
              <template #default="{ row }">
                <el-button size="small" :disabled="!canWrite" @click="openTemplateEdit(row)">编辑</el-button>
                <el-button size="small" type="danger" :disabled="!canWrite" @click="removeTemplate(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <div class="page__hint">
          <div>新增的规则 key 需要以 $ 开头（例如：$MY_RULE）。在追剧任务里将 pattern 设置为该 key，即可使用系统保存规则。</div>
          <div>replace 为默认模板；任务里 replace 留空时，会自动使用该默认值。</div>
        </div>

        <el-card class="page__card" shadow="never">
          <template #header>
            <div class="card__header">
              <div>内置规则</div>
              <el-button text :loading="loading" @click="refresh">刷新</el-button>
            </div>
          </template>
          <el-table :data="builtinRules" :loading="loading" style="width: 100%">
            <el-table-column prop="key" label="key" width="180" />
            <el-table-column prop="label" label="名称" min-width="160" />
            <el-table-column label="状态" width="140">
              <template #default="{ row }">
                <el-tag v-if="row.overridden" type="warning">已覆盖</el-tag>
                <el-tag v-else type="info">默认</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200">
              <template #default="{ row }">
                <el-button size="small" :disabled="!canWrite" @click="openEdit(row)">编辑</el-button>
                <el-button size="small" :disabled="!canWrite || !row.overridden" @click="removeRule(row)">恢复默认</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card class="page__card" shadow="never">
          <template #header>
            <div class="card__header">
              <div>自定义规则</div>
              <el-button type="primary" size="small" :disabled="!canWrite" @click="openCreate">新增规则</el-button>
            </div>
          </template>
          <el-table :data="customRules" :loading="loading" style="width: 100%">
            <el-table-column prop="key" label="key" width="180" />
            <el-table-column prop="label" label="名称" min-width="160" />
            <el-table-column label="操作" width="160">
              <template #default="{ row }">
                <el-button size="small" :disabled="!canWrite" @click="openEdit(row)">编辑</el-button>
                <el-button size="small" type="danger" :disabled="!canWrite" @click="removeRule(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card class="page__card" shadow="never">
          <template #header>
            <div class="card__header">
              <div>关键词过滤规则</div>
              <el-button type="primary" size="small" :disabled="!canWrite" @click="openFilterRuleDialog(-1)">新增规则</el-button>
            </div>
          </template>
          <el-table :data="filterRules.rules" :loading="filterRules.loading" style="width: 100%">
            <el-table-column prop="name" label="名称" />
            <el-table-column label="操作" width="160">
              <template #default="{ $index }">
                <el-button size="small" :disabled="!canWrite" @click="openFilterRuleDialog($index)">编辑</el-button>
                <el-button size="small" type="danger" :disabled="!canWrite" @click="deleteFilterRule($index)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-dialog v-model="filterRules.dialogVisible" :title="filterRules.editIndex >= 0 ? '编辑过滤词规则' : '新增过滤词规则'" width="480px" append-to-body>
          <el-form label-position="top">
            <el-form-item label="名称">
              <el-input v-model="filterRules.form.name" placeholder="如：综艺、动漫" />
            </el-form-item>
            <el-form-item label="过滤词">
              <el-input v-model="filterRules.form.keywords" placeholder="用 | 分隔，如：纯享版|会员版|花絮" />
              <div class="form-item-hint">文件名包含任意过滤词的文件不会被转存</div>
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="filterRules.dialogVisible = false">取消</el-button>
            <el-button type="primary" :disabled="!canWrite" @click="saveFilterRule">保存</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>

      <el-tab-pane label="资源搜索" name="resource_search">
        <div class="page__hint">
          <div>任务名称输入框会使用这里的搜索源进行资源建议。</div>
          <div>CloudSaver 密码不回显；如需修改请重新输入后保存。</div>
        </div>

        <el-card class="page__card" shadow="never">
          <template #header>
            <div class="card__header">
              <div>搜索源</div>
              <div>
                <el-button text :loading="resourceSearch.loading" @click="refreshSources">刷新</el-button>
                <el-button type="primary" :loading="!!resourceSearch.savingKey" :disabled="!canWrite" @click="saveSource(resourceSearch.selectedSource)">保存</el-button>
              </div>
            </div>
          </template>
          <el-form label-position="top" :disabled="resourceSearch.loading">
            <el-form-item label="搜索引擎">
              <el-select v-model="resourceSearch.selectedSource" style="width: 100%">
                <el-option label="PanSou" value="pansou" />
                <el-option label="CloudSaver" value="cloudsaver" />
              </el-select>
            </el-form-item>
            <el-form-item label="启用">
              <el-switch v-if="resourceSearch.selectedSource === 'pansou'" v-model="resourceSearch.pansou.enabled" :disabled="!canWrite" />
              <el-switch v-else v-model="resourceSearch.cloudsaver.enabled" :disabled="!canWrite" />
            </el-form-item>

            <template v-if="resourceSearch.selectedSource === 'pansou'">
              <el-form-item label="服务器">
                <el-input v-model="resourceSearch.pansou.server" placeholder="例如：https://so.252035.xyz" />
              </el-form-item>
            </template>

            <template v-else>
              <el-form-item label="服务器">
                <el-input v-model="resourceSearch.cloudsaver.server" placeholder="例如：http://172.17.0.1:8008" />
              </el-form-item>
              <el-form-item label="用户名">
                <el-input v-model="resourceSearch.cloudsaver.username" placeholder="用户名" />
              </el-form-item>
              <el-form-item label="密码（留空表示不修改）">
                <el-input v-model="resourceSearch.cloudsaver.passwordInput" type="password" show-password placeholder="请输入新密码" />
              </el-form-item>
              <el-form-item label="Token（自动维护）">
                <el-input v-model="resourceSearch.cloudsaver.token" disabled placeholder="自动登录后会写入 token" />
              </el-form-item>
            </template>
          </el-form>
        </el-card>

        <el-card class="page__card" shadow="never">
          <template #header>
            <div class="card__header">
              <div>分享者过滤</div>
              <el-button text :loading="sharerFilter.loading" @click="loadSharerFilter">刷新</el-button>
            </div>
          </template>
          <div style="margin-bottom: 12px; color: var(--el-text-color-secondary); font-size: 13px">
            用于资源搜索结果的过滤和高亮显示。多个昵称用竖线 <code>|</code> 分隔。
          </div>
          <el-form label-width="140px" label-position="left">
            <el-form-item label="优选分享者">
              <el-button @click="sharerDialog.type = 'preferred'; sharerDialog.visible = true">
                管理名单（{{ sharerFilter.preferred.length }} 人）
              </el-button>
            </el-form-item>
            <el-form-item label="屏蔽分享者">
              <el-button @click="sharerDialog.type = 'blocked'; sharerDialog.visible = true">
                管理名单（{{ sharerFilter.blocked.length }} 人）
              </el-button>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="sharerFilter.saving" :disabled="!canWrite" @click="saveSharerFilter">保存配置</el-button>
            </el-form-item>
          </el-form>
          <!-- 分享者名单弹窗 -->
          <el-dialog
            v-model="sharerDialog.visible"
            :title="sharerDialog.type === 'preferred' ? '优选分享者名单' : '屏蔽分享者名单'"
            width="420px"
            append-to-body
          >
            <div class="sharer-tag-list">
              <div style="display: flex; gap: 8px; margin-bottom: 12px">
                <el-input v-model="sharerDialog.inputValue" placeholder="名称，多个用 | 分隔" size="small" @keyup.enter="addSharerFromInput" />
                <el-button type="primary" size="small" :disabled="!sharerDialog.inputValue?.trim()" @click="addSharerFromInput">添加</el-button>
              </div>
              <el-tag
                v-for="name in (sharerDialog.type === 'preferred' ? sharerFilter.preferred : sharerFilter.blocked)"
                :key="name"
                :type="sharerDialog.type === 'preferred' ? 'success' : 'danger'"
                closable
                :disabled="!canWrite"
                @close="removeSharer(name)"
              >{{ name }}</el-tag>
              <span v-if="!(sharerDialog.type === 'preferred' ? sharerFilter.preferred : sharerFilter.blocked).length" class="sharer-tag-empty">
                暂无，可手动输入添加或在搜索结果中点击分享者名称添加
              </span>
            </div>
          </el-dialog>
        </el-card>

        <el-card class="page__card" shadow="never">
          <template #header>
            <div class="card__header">
              <div>验证与缓存</div>
            </div>
          </template>
          <el-form label-width="140px" label-position="left">
            <el-form-item label="验证并行数">
              <el-input-number v-model="sharerFilter.validate_batch_size" :min="1" :max="20" :disabled="!canWrite" />
              <div class="form-item-hint">每批同时验证的链接数量，默认 5。越大验证越快，但对网盘账号压力越大。</div>
            </el-form-item>
            <el-form-item label="缓存时长（秒）">
              <el-input-number v-model="sharerFilter.preview_cache_ttl_seconds" :min="30" :max="3600" :disabled="!canWrite" />
              <div class="form-item-hint">文件列表缓存时长，默认 300 秒。越短越实时，但请求越多。</div>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="sharerFilter.saving" :disabled="!canWrite" @click="saveSharerFilter">保存配置</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="TMDB" name="tmdb">
        <div class="page__hint">
          <div>用于影视发现页的 TMDB 信息补全与搜索。</div>
          <div>API Key 不回显；留空保存表示不修改。</div>
        </div>

        <el-card class="page__card" shadow="never">
          <template #header>
            <div class="card__header">
              <div>TMDB 配置</div>
              <div>
                <el-button text :loading="tmdb.loading" @click="refreshTMDB">刷新</el-button>
                <el-button text :disabled="tmdb.loading" @click="useDefaultRenameTemplates">默认模板</el-button>
                <el-button type="primary" :loading="tmdb.saving" :disabled="!canWrite" @click="saveTMDB">保存</el-button>
              </div>
            </div>
          </template>

          <el-form label-position="top" :disabled="tmdb.loading">
            <el-form-item label="API Key（留空不修改）">
              <el-input v-model="tmdb.apiKeyInput" type="password" show-password :placeholder="tmdb.hasApiKey ? '已配置（留空不修改）' : '请输入 TMDB API Key'" />
            </el-form-item>
            <el-form-item label="语言（language）">
              <el-select v-model="tmdb.language" style="width: 260px">
                <el-option label="中文（zh-CN）" value="zh-CN" />
                <el-option label="英文（en-US）" value="en-US" />
              </el-select>
            </el-form-item>
            <el-form-item label="海报语言（poster_language）">
              <el-select v-model="tmdb.posterLanguage" style="width: 260px">
                <el-option label="中文（zh-CN）" value="zh-CN" />
                <el-option label="原始语言（original）" value="original" />
              </el-select>
            </el-form-item>
            <el-form-item label="启用 guessit+TMDB 兜底重命名">
              <el-switch v-model="tmdb.enableGuessitFallbackRename" :disabled="!canWrite || !tmdb.hasApiKey" />
              <div class="page__hint">
                <div>开启后，追剧任务在 pattern/replace 为空时将按下方模板自动生成目标文件名（不会影响手动配置的保存规则）。</div>
              </div>
            </el-form-item>
            <el-form-item label="电视剧兜底命名模板（TV）">
              <el-input
                v-model="tmdb.tvRenameTemplate"
                type="textarea"
                :rows="2"
                :disabled="!tmdb.hasApiKey"
                placeholder="{title}.S{season}E{episode}{ext}"
              />
              <div class="page__hint">
                <div>可用占位符：</div>
                <div>- {title}：标题（空格分隔）</div>
                <div>- {title_dot}：标题（点分隔）</div>
                <div>- {season}：季（两位数，如 01）</div>
                <div>- {episode}：集（两位数，如 02）</div>
                <div>- {season_num}：季（原始数字，如 1）</div>
                <div>- {episode_num}：集（原始数字，如 2）</div>
                <div>- {year}：年份（通常为空；为兼容模板保留）</div>
                <div>- {ext}：扩展名（包含 .，如 .mkv；若模板不写 {ext} 会自动补上）</div>
                <div>- {orig}：原始文件名（含扩展名）</div>
                <div>- {orig_base}：原始文件名（不含扩展名）</div>
                <div>- {orig_base_dot}：orig_base 的点分隔形式</div>
                <div>- {tags_dot}：清洗后的资源标签（点分隔，可能为空）</div>
                <div>- {tags_space}：清洗后的资源标签（空格分隔，可能为空）</div>
                <div>示例：{title}.S{season}E{episode}{ext} → 低智商犯罪.S01E02.mp4</div>
              </div>
            </el-form-item>
            <el-form-item label="电影兜底命名模板（Movie）">
              <el-input
                v-model="tmdb.movieRenameTemplate"
                type="textarea"
                :rows="2"
                :disabled="!tmdb.hasApiKey"
                placeholder="{title_dot}.{year}{ext}"
              />
              <div class="page__hint">
                <div>可用占位符：</div>
                <div>- {title}：标题（空格分隔）</div>
                <div>- {title_dot}：标题（点分隔）</div>
                <div>- {year}：年份（可能为空；为空时会自动清理多余的点/空格/空括号）</div>
                <div>- {ext}：扩展名（包含 .，如 .mkv；若模板不写 {ext} 会自动补上）</div>
                <div>- {orig}：原始文件名（含扩展名）</div>
                <div>- {orig_base}：原始文件名（不含扩展名）</div>
                <div>- {orig_base_dot}：orig_base 的点分隔形式</div>
                <div>- {tags_dot}：清洗后的资源标签（点分隔，可能为空）</div>
                <div>- {tags_space}：清洗后的资源标签（空格分隔，可能为空）</div>
                <div>示例：{title_dot}.{year}{ext} → The.World.of.Love.2025.mkv</div>
              </div>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="OpenList" name="openlist">
        <div class="page__hint">
          <div>用于同步任务等功能的 OpenList 连接配置。</div>
          <div>Token 不回显；留空保存表示不修改。</div>
        </div>

        <el-card class="page__card" shadow="never">
          <template #header>
            <div class="card__header">
              <div>OpenList 配置</div>
              <div>
                <el-button text :loading="openlist.loading" @click="refreshOpenList">刷新</el-button>
                <el-button type="primary" :loading="openlist.saving" :disabled="!canWrite" @click="saveOpenList">保存</el-button>
              </div>
            </div>
          </template>

          <el-form label-position="top" :disabled="openlist.loading">
            <el-form-item label="地址（url）">
              <el-input v-model="openlist.url" placeholder="例如：http://172.17.0.1:5244" />
            </el-form-item>
            <el-form-item label="Token（留空不修改）">
              <el-input
                v-model="openlist.tokenInput"
                type="password"
                show-password
                :placeholder="openlist.hasToken ? '已配置（留空不修改）' : '请输入 OpenList Token'"
              />
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="dialog.visible" :title="dialog.isEdit ? '编辑规则' : '新增规则'" width="720px">
      <el-form label-position="top">
        <el-form-item label="key（以 $ 开头）">
          <el-input v-model="dialog.form.key" :disabled="dialog.keyLocked" placeholder="$MY_RULE" />
        </el-form-item>
        <el-form-item label="名称（可选）">
          <el-input v-model="dialog.form.label" placeholder="例如：综艺命名（含日期）" />
        </el-form-item>
        <el-form-item v-if="!dialog.form.key || !String(dialog.form.key).startsWith('$')" label="提示">
          <div class="page__hint">key 必须以 $ 开头。</div>
        </el-form-item>
        <el-form-item v-if="!currentIsBuiltinKey" label="启用">
          <el-switch v-model="dialog.form.enabled" :disabled="!canWrite" />
        </el-form-item>
        <el-form-item label="pattern（正则表达式）">
          <el-input v-model="dialog.form.pattern" type="textarea" :rows="4" placeholder="例如：^(?!.*纯享).*?第\\d+期.*" />
        </el-form-item>
        <el-form-item label="replace（默认替换模板）">
          <el-input v-model="dialog.form.replace" type="textarea" :rows="3" placeholder="{II}.{TASKNAME}.{DATE}.第{E}期{PART}.{EXT}" />
          <div v-if="Object.keys(variables).length" class="drawer-form__hint" style="margin-top: 8px">
            <div style="font-weight: 600; margin-bottom: 4px">可用变量：</div>
            <div style="display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12px; line-height: 1.8">
              <span v-for="(desc, key) in variables" :key="key"><code>{{ key }}</code> {{ desc }}</span>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.submitting" :disabled="!canWrite" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 模板编辑弹窗 -->
    <el-dialog v-model="templates.dialogVisible" :title="templates.editingId ? '编辑模板' : '新增模板'" width="600px">
      <el-form label-position="top">
        <el-form-item label="模板名称">
          <el-input v-model="templates.form.name" placeholder="例如：4K HDR 追剧模板" />
        </el-form-item>
        <el-divider />
        <el-form-item v-for="field in TEMPLATE_FIELDS" :key="field.key" :label="field.label">
          <!-- 开关类型 -->
          <template v-if="field.type === 'switch'">
            <el-switch v-model="templates.form.config[field.key]" active-value="1" inactive-value="" />
          </template>
          <!-- 日期类型 -->
          <template v-else-if="field.type === 'date'">
            <el-date-picker v-model="templates.form.config[field.key]" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" style="width: 100%" clearable :editable="false" />
          </template>
          <!-- 关键词类型（带模式切换） -->
          <template v-else-if="field.type === 'keyword'">
            <el-input v-model="templates.form.config[field.key]" placeholder="可选，用 | 分隔">
              <template #append>
                <el-button @click="toggleKeywordMode(field.key)">
                  {{ getKeywordModeLabel(field.key) }}
                </el-button>
              </template>
            </el-input>
          </template>
          <!-- 关键词过滤（预设选择 + 手动输入） -->
          <template v-else-if="field.type === 'filter_words'">
            <el-select v-model="templates.form.config.filter_rule_name" placeholder="选择预设规则" style="width: 100%; margin-bottom: 8px" clearable @change="onFilterRuleSelect">
              <el-option v-for="opt in templates.filterWords.options" :key="opt.name" :label="opt.name" :value="opt.name" />
            </el-select>
            <el-input v-model="templates.form.config.filter_words" placeholder="或手动输入关键词" />
          </template>
          <!-- 文本类型 -->
          <template v-else>
            <el-input v-model="templates.form.config[field.key]" :placeholder="field.key === 'min_size' ? '如：100MB' : ''" />
          </template>
          <div v-if="field.hint" class="drawer-form__hint">{{ field.hint }}</div>
        </el-form-item>
        <!-- 重命名设置 -->
        <el-divider />
        <div class="drawer-form__section-title">重命名设置</div>
        <el-form-item label="内置规则（可选）">
          <el-select v-model="templates.magicRegex.selectedKey" style="width: 100%" clearable placeholder="选择内置规则后会自动填入下方输入框" @change="applyMagicRule">
            <el-option v-for="rule in templates.magicRegex.rules" :key="rule.key" :label="rule.label ? `${rule.label}（${rule.key}）` : rule.key" :value="rule.key" />
          </el-select>
          <div class="drawer-form__hint">选择后会把默认 pattern / replace 填入输入框，可继续修改。</div>
        </el-form-item>
        <el-form-item label="匹配表达式（pattern）">
          <el-input v-model="templates.form.config.pattern" placeholder="$TV_REGEX 或正则表达式" />
        </el-form-item>
        <el-form-item label="替换表达式（replace）">
          <el-input v-model="templates.form.config.replace" placeholder="\1E\2.\3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="templates.dialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!canWrite" @click="submitTemplate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page {
  padding: 16px;
}
.page__header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-bottom: 16px;
}
.page__title {
  font-size: 22px;
  font-weight: 700;
}
.page__hint {
  margin: 12px 0 16px;
  color: var(--el-text-color-regular);
  font-size: 14px;
  line-height: 1.7;
}
.page__card {
  margin-bottom: 16px;
}
.card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.form-item-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.sharer-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.sharer-tag-empty {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

/* 标签栏居中、大字号 */
:deep(.el-tabs__nav-wrap) {
  overflow: visible !important;
  display: flex;
  justify-content: center;
}
:deep(.el-tabs__nav-wrap::after) {
  display: none;
}
:deep(.el-tabs__nav-prev),
:deep(.el-tabs__nav-next) {
  display: none !important;
}
:deep(.el-tabs__item) {
  padding: 0 14px;
  font-size: 15px;
  height: 44px;
  line-height: 44px;
}
:deep(.el-tabs__nav) {
  white-space: nowrap;
  float: none;
  display: inline-flex;
}
:deep(.el-tabs__header) {
  display: flex;
  justify-content: center;
}
:deep(.el-tabs__active-bar) {
  height: 3px;
}
.drawer-form__hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  line-height: 1.5;
}
:deep(.el-form-item__label) {
  font-weight: 500;
  color: var(--el-text-color-primary);
}
</style>
