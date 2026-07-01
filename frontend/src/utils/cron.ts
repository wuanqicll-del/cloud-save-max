export const DEFAULT_TIMEZONE = 'Asia/Shanghai'

function normalizeSpaces(value: string) {
  return value.trim().replace(/\s+/g, ' ')
}

function isInt(value: string) {
  return /^\d+$/.test(value)
}

function parseIntSafe(value: string) {
  if (!isInt(value)) return null
  const n = Number(value)
  if (!Number.isFinite(n)) return null
  return n
}

function validateNumberRange(value: number, min: number, max: number) {
  return value >= min && value <= max
}

function validateStep(value: string) {
  const n = parseIntSafe(value)
  if (n === null) return false
  return n >= 1
}

function validateRangeToken(token: string, min: number, max: number) {
  const [aStr, bStr] = token.split('-', 2)
  const a = parseIntSafe(aStr)
  const b = parseIntSafe(bStr)
  if (a === null || b === null) return null
  if (!validateNumberRange(a, min, max) || !validateNumberRange(b, min, max)) return false
  return a <= b
}

function normalizeDayOfWeekToken(token: string) {
  const map: Record<string, number> = {
    sun: 0,
    mon: 1,
    tue: 2,
    wed: 3,
    thu: 4,
    fri: 5,
    sat: 6,
  }
  const lower = token.toLowerCase()
  if (map[lower] !== undefined) return String(map[lower])
  return token
}

function validateFieldToken(tokenRaw: string, min: number, max: number, opts?: { dayOfWeek?: boolean }) {
  let token = tokenRaw.trim()
  if (!token) return false
  if (opts?.dayOfWeek) token = normalizeDayOfWeekToken(token)
  if (token === '*' || token === '?') return true

  if (token.includes('/')) {
    const [left, step] = token.split('/', 2)
    if (!validateStep(step)) return false
    if (left === '*') return true
    if (left.includes('-')) {
      const ok = validateRangeToken(left, min, max)
      if (ok === null) return true
      return ok
    }
    return true
  }

  if (token.includes('-')) {
    const ok = validateRangeToken(token, min, max)
    if (ok === null) return true
    return ok
  }

  const n = parseIntSafe(token)
  if (n === null) return true
  return validateNumberRange(n, min, max)
}

export function normalizeCrontab(value: string) {
  return normalizeSpaces(String(value || ''))
}

export function validateCrontab5(value: string) {
  const normalized = normalizeCrontab(value)
  if (!normalized) return { ok: false, message: 'crontab 不能为空' }
  const parts = normalized.split(' ')
  if (parts.length !== 5) return { ok: false, message: 'crontab 必须是 5 段：minute hour day month day_of_week' }

  const fields: Array<{ min: number; max: number; label: string; dayOfWeek?: boolean }> = [
    { min: 0, max: 59, label: 'minute' },
    { min: 0, max: 23, label: 'hour' },
    { min: 1, max: 31, label: 'day' },
    { min: 1, max: 12, label: 'month' },
    { min: 0, max: 6, label: 'day_of_week', dayOfWeek: true },
  ]

  for (let i = 0; i < fields.length; i += 1) {
    const field = fields[i]
    const raw = parts[i]
    const tokens = raw.split(',')
    for (const token of tokens) {
      if (!validateFieldToken(token, field.min, field.max, { dayOfWeek: field.dayOfWeek })) {
        return { ok: false, message: `crontab 第 ${i + 1} 段（${field.label}）范围应为 ${field.min}-${field.max}` }
      }
    }
  }

  return { ok: true, message: '', normalized }
}

export function normalizeTimezone(value: string) {
  const text = String(value || '').trim()
  return text || DEFAULT_TIMEZONE
}

export function validateTimezone(value: string) {
  const tz = normalizeTimezone(value)
  try {
    new Intl.DateTimeFormat('zh-CN', { timeZone: tz }).format(new Date())
  } catch (e: any) {
    if (e?.name === 'RangeError') return { ok: false, message: `timezone 无效：${tz}`, normalized: tz }
  }
  return { ok: true, message: '', normalized: tz }
}

function expandField(field: string, min: number, max: number): number[] {
  const result: number[] = []
  const tokens = field.split(',')
  for (const token of tokens) {
    if (token === '*' || token === '?') {
      for (let i = min; i <= max; i++) result.push(i)
      continue
    }
    if (token.includes('/')) {
      const [left, stepStr] = token.split('/', 2)
      const step = parseInt(stepStr) || 1
      let start = min
      let end = max
      if (left !== '*') {
        if (left.includes('-')) {
          const [a, b] = left.split('-', 2)
          start = parseInt(a) || min
          end = parseInt(b) || max
        } else {
          start = parseInt(left) || min
        }
      }
      for (let i = start; i <= end; i += step) result.push(i)
      continue
    }
    if (token.includes('-')) {
      const [a, b] = token.split('-', 2)
      const start = parseInt(a) || min
      const end = parseInt(b) || max
      for (let i = start; i <= end; i++) result.push(i)
      continue
    }
    const n = parseInt(token)
    if (!isNaN(n)) result.push(n)
  }
  return [...new Set(result)].sort((a, b) => a - b)
}

const WEEKDAY_NAMES = ['日', '一', '二', '三', '四', '五', '六']
const MONTH_NAMES = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

export function describeCrontab(value: string): string {
  const normalized = normalizeCrontab(value)
  if (!normalized) return ''
  const parts = normalized.split(' ')
  if (parts.length !== 5) return ''

  const minutes = expandField(parts[0], 0, 59)
  const hours = expandField(parts[1], 0, 23)
  const days = expandField(parts[2], 1, 31)
  const months = expandField(parts[3], 1, 12)
  const weekdays = expandField(parts[4], 0, 6)

  if (minutes.length === 0 || hours.length === 0) return ''

  const isAllDays = parts[2] === '*' || parts[2] === '?'
  const isAllMonths = parts[3] === '*' || parts[3] === '?'
  const isAllWeekdays = parts[4] === '*' || parts[4] === '?'

  // 时间部分
  const timeStr = hours.length === 1
    ? `${hours[0]}点${minutes.join('、')}分`
    : `${hours.join('、')}点的${minutes.join('、')}分`

  // 日期部分
  let dateStr = ''
  if (!isAllWeekdays && isAllDays) {
    dateStr = weekdays.map(w => `周${WEEKDAY_NAMES[w]}`).join('、')
  } else if (!isAllDays && isAllWeekdays) {
    dateStr = `每月${days.join('、')}号`
  } else if (!isAllDays && !isAllWeekdays) {
    dateStr = `每月${days.join('、')}号或${weekdays.map(w => `周${WEEKDAY_NAMES[w]}`).join('、')}`
  } else {
    dateStr = '每天'
  }

  // 月份部分
  let monthStr = ''
  if (!isAllMonths) {
    monthStr = months.map(m => MONTH_NAMES[m - 1]).join('、') + '的'
  }

  return `${monthStr}${dateStr}${timeStr}执行`
}

export function getNextExecutions(value: string, count: number = 5): Date[] {
  const normalized = normalizeCrontab(value)
  if (!normalized) return []
  const parts = normalized.split(' ')
  if (parts.length !== 5) return []

  const minutes = expandField(parts[0], 0, 59)
  const hours = expandField(parts[1], 0, 23)
  const days = expandField(parts[2], 1, 31)
  const months = expandField(parts[3], 1, 12)
  const weekdays = expandField(parts[4], 0, 6)

  if (minutes.length === 0 || hours.length === 0) return []

  const isAllDays = parts[2] === '*' || parts[2] === '?'
  const isAllMonths = parts[3] === '*' || parts[3] === '?'
  const isAllWeekdays = parts[4] === '*' || parts[4] === '?'

  const results: Date[] = []
  const now = new Date()
  const checkDate = new Date(now)
  checkDate.setSeconds(0, 0)
  checkDate.setMinutes(checkDate.getMinutes() + 1)

  // 最多检查未来366天
  for (let dayOffset = 0; dayOffset < 366 && results.length < count; dayOffset++) {
    const date = new Date(checkDate)
    date.setDate(date.getDate() + dayOffset)

    const day = date.getDate()
    const month = date.getMonth() + 1
    const weekday = date.getDay()

    // 检查月份
    if (!isAllMonths && !months.includes(month)) continue
    // 检查日期和星期
    const dayMatch = isAllDays || days.includes(day)
    const weekdayMatch = isAllWeekdays || weekdays.includes(weekday)
    if (!dayMatch && !weekdayMatch) continue

    for (const hour of hours) {
      for (const minute of minutes) {
        if (results.length >= count) break
        const executionTime = new Date(date)
        executionTime.setHours(hour, minute, 0, 0)
        if (executionTime > now) {
          results.push(executionTime)
        }
      }
    }
  }

  return results
}
