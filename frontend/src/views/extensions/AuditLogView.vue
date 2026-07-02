<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { fetchAuditLogs, deleteAllAuditLogs, fetchAuditLogScheduler, updateAuditLogScheduler } from '@/api/audit'
import type { AuditLogItem } from '@/types/audit'
import { useIsMobile } from '@/composables/useIsMobile'
import { useAuthStore } from '@/stores/auth'
import { AUDIT_WRITE } from '@/constants/permissions'
import { validateCrontab5, validateTimezone, describeCrontab, getNextExecutions } from '@/utils/cron'

const auth = useAuthStore()
const canWrite = computed(() => auth.permissions.includes(AUDIT_WRITE))

const loading = ref(false)
const items = ref<AuditLogItem[]>([])
const total = ref(0)
const isMobile = useIsMobile()
const activeTab = ref<'logs' | 'scheduler'>('logs')

const query = reactive({
  page: 1,
  page_size: 20,
  q: '',
  action: '',
  success: 'all' as 'all' | 'success' | 'failed',
})

const successParam = computed(() => {
  if (query.success === 'success') return true
  if (query.success === 'failed') return false
  return undefined
})

const scheduler = reactive({
  loading: false,
  saving: false,
  data: {
    enabled: false,
    crontab: '0 3 * * *',
    timezone: 'Asia/Shanghai',
    retention_days: 30,
  },
})

const cronPreviewVisible = ref(false)

async function loadData() {
  loading.value = true
  try {
    const data = await fetchAuditLogs({
      page: query.page,
      page_size: query.page_size,
      q: query.q || undefined,
      action: query.action || undefined,
      success: successParam.value,
    })
    items.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  query.q = ''
  query.action = ''
  query.success = 'all'
  query.page = 1
  loadData()
}

async function handleDeleteAll() {
  try {
    await ElMessageBox.confirm('确定删除所有审计日志？此操作不可恢复。', '删除确认', { type: 'warning' })
    await deleteAllAuditLogs()
    ElMessage.success('已删除所有审计日志')
    loadData()
  } catch {}
}

async function loadScheduler() {
  scheduler.loading = true
  try {
    const data = await fetchAuditLogScheduler()
    scheduler.data.enabled = data.enabled
    scheduler.data.crontab = data.crontab
    scheduler.data.timezone = data.timezone
    scheduler.data.retention_days = data.retention_days
  } finally {
    scheduler.loading = false
  }
}

async function saveScheduler() {
  if (!validateCrontab5(scheduler.data.crontab)) {
    ElMessage.error('Cron 表达式格式错误，需要 5 段（分 时 日 月 周）')
    return
  }
  if (!validateTimezone(scheduler.data.timezone)) {
    ElMessage.error('时区格式错误')
    return
  }
  scheduler.saving = true
  try {
    await updateAuditLogScheduler({
      enabled: scheduler.data.enabled,
      crontab: scheduler.data.crontab,
      timezone: scheduler.data.timezone,
      retention_days: scheduler.data.retention_days,
    })
    ElMessage.success('已保存')
  } finally {
    scheduler.saving = false
  }
}

onMounted(() => {
  loadData()
  loadScheduler()
})
</script>

<template>
  <div class="shell-page">
    <div class="section-header">
      <div class="section-header__title">
        <h2>审计日志</h2>
      </div>
      <div class="toolbar__right">
        <el-button type="primary" @click="loadData">刷新</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="audit-tabs">
      <el-tab-pane label="日志列表" name="logs">
        <section class="glass-panel filter-strip">
          <div class="toolbar">
            <div class="toolbar__left">
              <el-input
                v-model="query.q"
                clearable
                placeholder="搜索 action / 用户 / 目标 / detail"
                :style="{ width: isMobile ? '100%' : '300px' }"
                @keyup.enter="loadData"
                @clear="loadData"
              />
              <el-input
                v-model="query.action"
                clearable
                placeholder="精确 action（可选）"
                :style="{ width: isMobile ? '100%' : '240px' }"
                @keyup.enter="loadData"
                @clear="loadData"
              />
              <el-segmented
                v-model="query.success"
                :options="[
                  { label: '全部', value: 'all' },
                  { label: '成功', value: 'success' },
                  { label: '失败', value: 'failed' },
                ]"
              />
            </div>
            <div class="toolbar__right">
              <el-button @click="resetFilters">清空筛选</el-button>
              <el-button v-if="canWrite" type="danger" @click="handleDeleteAll">删除所有</el-button>
            </div>
          </div>
        </section>

        <section class="glass-panel table-panel">
          <el-table :data="items" border v-loading="loading">
            <el-table-column prop="created_at" label="时间" min-width="180" />
            <el-table-column label="用户" min-width="140">
              <template #default="{ row }">
                <span>{{ row.actor_username || (row.actor_user_id ? `#${row.actor_user_id}` : '-') }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="action" label="Action" min-width="220" />
            <el-table-column label="目标" min-width="200">
              <template #default="{ row }">
                <span>{{ row.target_type || '-' }}</span>
                <span v-if="row.target_id" class="muted">:{{ row.target_id }}</span>
              </template>
            </el-table-column>
            <el-table-column label="结果" width="100">
              <template #default="{ row }">
                <el-tag :type="row.success ? 'success' : 'danger'" effect="plain" round>
                  {{ row.success ? '成功' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="ip" label="IP" width="140" />
            <el-table-column prop="detail" label="Detail" min-width="320" show-overflow-tooltip />
          </el-table>

          <div class="pagination-bar">
            <el-pagination
              v-model:current-page="query.page"
              v-model:page-size="query.page_size"
              background
              layout="total, sizes, prev, pager, next"
              :total="total"
              @change="loadData"
            />
          </div>
        </section>
      </el-tab-pane>

      <el-tab-pane label="定时清理" name="scheduler">
        <section class="glass-panel scheduler-panel" v-loading="scheduler.loading">
          <el-form label-width="100px" label-position="left">
            <el-form-item label="启用定时清理">
              <el-switch v-model="scheduler.data.enabled" />
            </el-form-item>
            <el-form-item label="Cron 表达式">
              <el-input v-model="scheduler.data.crontab" placeholder="0 3 * * *" style="width: 200px" />
              <el-button style="margin-left: 8px" @click="cronPreviewVisible = true">预览</el-button>
              <div class="form-tip">
                {{ describeCrontab(scheduler.data.crontab) }}
              </div>
            </el-form-item>
            <el-form-item label="时区">
              <el-input v-model="scheduler.data.timezone" placeholder="Asia/Shanghai" style="width: 200px" />
            </el-form-item>
            <el-form-item label="保留天数">
              <el-input-number v-model="scheduler.data.retention_days" :min="1" :max="3650" />
              <div class="form-tip">超过此天数的日志将被自动清理</div>
            </el-form-item>
            <el-form-item>
              <el-button v-if="canWrite" type="primary" :loading="scheduler.saving" @click="saveScheduler">保存</el-button>
            </el-form-item>
          </el-form>
        </section>

        <el-dialog v-model="cronPreviewVisible" title="Cron 执行预览" width="400px">
          <div style="margin-bottom: 12px; color: var(--el-text-color-secondary);">
            表达式: <code>{{ scheduler.data.crontab }}</code>（{{ scheduler.data.timezone }}）
          </div>
          <div style="margin-bottom: 8px; font-weight: 500;">最近 5 次执行时间：</div>
          <ol style="padding-left: 20px; margin: 0;">
            <li v-for="(t, idx) in getNextExecutions(scheduler.data.crontab, 5)" :key="idx" style="line-height: 1.8;">
              {{ t.toLocaleString() }}
            </li>
          </ol>
          <template #footer>
            <el-button @click="cronPreviewVisible = false">关闭</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.audit-tabs {
  margin-top: 0;
}

.table-panel {
  padding: 18px;
}

.scheduler-panel {
  padding: 24px;
}

.muted {
  color: var(--el-text-color-secondary);
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.form-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
