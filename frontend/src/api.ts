export type Role = 'candidate' | 'employer'

const TOKEN_KEY = 'fsp_token'
const ROLE_KEY = 'fsp_role'

export const session = {
  get token() {
    return localStorage.getItem(TOKEN_KEY)
  },
  get role() {
    return localStorage.getItem(ROLE_KEY) as Role | null
  },
  set(token: string, role: string) {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(ROLE_KEY, role)
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(ROLE_KEY)
  },
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function errorText(body: unknown): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const d = (body as { detail: unknown }).detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) return d.map((e) => e.msg ?? JSON.stringify(e)).join('; ')
  }
  return 'Ошибка запроса'
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = {}
  if (session.token) headers.Authorization = `Bearer ${session.token}`
  let body: BodyInit | undefined
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }
  const res = await fetch(`/api${path}`, { method: opts.method ?? (body ? 'POST' : 'GET'), headers, body })
  const data = res.status === 204 ? null : await res.json().catch(() => null)
  if (res.status === 401) session.clear()
  if (!res.ok) throw new ApiError(res.status, errorText(data))
  return data as T
}

export const GRADE_TITLES: Record<string, string> = {
  intern: 'Intern', junior: 'Junior', junior_plus: 'Junior+', middle: 'Middle', middle_plus: 'Middle+', senior: 'Senior',
}
export const GRADE_ORDER = ['intern', 'junior', 'junior_plus', 'middle', 'middle_plus', 'senior']
export const SPEC_TITLES: Record<string, string> = {
  backend: 'Backend',
  frontend: 'Frontend',
  mobile: 'Mobile',
  data: 'Data Science / ML',
  analyst: 'Аналитик',
  qa: 'QA',
  devops: 'DevOps',
  security: 'Инфобез',
}
export const STATUS_TITLES: Record<string, string> = {
  sent: 'Отправлено',
  viewed: 'Просмотрено',
  accepted: 'Принято',
  offer: 'Оффер',
  hired: 'Вышел на работу',
  declined: 'Отклонено',
  expired: 'Истекло',
  withdrawn: 'Отозвано',
  invited: 'Приглашён',
  rejected: 'Отказ',
}

export const rub = (n: number) => n.toLocaleString('ru-RU') + ' ₽'
export const salary = (a: number, b: number) => `${rub(a)} – ${rub(b)} (gross)`
export const fmtDate = (s?: string | null) => (s ? new Date(s).toLocaleDateString('ru-RU') : '—')

/** Скачивание файла (PDF-профиль) с авторизацией. */
export async function download(path: string, filename: string) {
  const res = await fetch(`/api${path}`, { headers: session.token ? { Authorization: `Bearer ${session.token}` } : {} })
  if (!res.ok) throw new ApiError(res.status, errorText(await res.json().catch(() => null)))
  const url = URL.createObjectURL(await res.blob())
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
