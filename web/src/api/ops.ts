import { API_ROOT, ApiError } from './client'

const OPS_TOKEN_KEY = 'hipp_manager_ops_token'

export function getOpsToken(): string | null {
  return localStorage.getItem(OPS_TOKEN_KEY)
}

export function setOpsToken(token: string | null) {
  if (token) localStorage.setItem(OPS_TOKEN_KEY, token)
  else localStorage.removeItem(OPS_TOKEN_KEY)
}

async function opsRequest<T = unknown>(
  path: string,
  options: RequestInit & { json?: unknown; skipAuth?: boolean } = {},
): Promise<T> {
  const { json, skipAuth, headers: extraHeaders, ...rest } = options
  const headers = new Headers(extraHeaders || {})
  if (json !== undefined) headers.set('Content-Type', 'application/json')
  if (!skipAuth) {
    const token = getOpsToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
  }
  const res = await fetch(`${API_ROOT}${path}`, {
    ...rest,
    headers,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  })
  const text = await res.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (!res.ok) {
    const detail =
      data && typeof data === 'object' && data !== null && 'detail' in data
        ? String((data as { detail: unknown }).detail)
        : typeof data === 'string' && data
          ? data
          : '请求失败'
    throw new ApiError(res.status, detail)
  }
  return data as T
}

export type OpsAdmin = { admin_id?: string; username: string }

export async function opsLogin(username: string, password: string) {
  const data = await opsRequest<{ token: string; username: string }>('/ops/auth/login', {
    method: 'POST',
    json: { username, password },
    skipAuth: true,
  })
  setOpsToken(data.token)
  return data
}

export async function opsLogout() {
  try {
    await opsRequest('/ops/auth/logout', { method: 'POST' })
  } finally {
    setOpsToken(null)
  }
}

export async function opsMe() {
  return opsRequest<OpsAdmin>('/ops/auth/me')
}

export async function opsChangePassword(oldPassword: string, newPassword: string) {
  return opsRequest<{ username: string; detail: string }>('/ops/auth/password', {
    method: 'POST',
    json: { old_password: oldPassword, new_password: newPassword },
  })
}

export type OpsUser = {
  user_id: string
  phone: string
  nickname: string
  balance: number
  register_source: string
  is_blocked: boolean
  has_password: boolean
  created_at?: string
}

export async function listOpsUsers(params: Record<string, string | number | undefined>) {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') q.set(k, String(v))
  })
  return opsRequest<{ total: number; items: OpsUser[] }>(`/ops/users?${q}`)
}

export async function setUserBlocked(userId: string, blocked: boolean) {
  return opsRequest<OpsUser>(`/ops/users/${userId}/blocked`, {
    method: 'PUT',
    json: { blocked },
  })
}

export async function resetUserPassword(userId: string, password: string) {
  return opsRequest(`/ops/users/${userId}/password`, {
    method: 'POST',
    json: { password },
  })
}

export async function listOpsTransactions(params: Record<string, string | number | undefined>) {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') q.set(k, String(v))
  })
  return opsRequest<{ total: number; items: Record<string, unknown>[] }>(`/ops/transactions?${q}`)
}

export async function listOpsRechargeOrders(params: Record<string, string | number | undefined>) {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') q.set(k, String(v))
  })
  return opsRequest<{ total: number; items: Record<string, unknown>[] }>(
    `/ops/recharge/orders?${q}`,
  )
}

export async function opsCredit(body: Record<string, unknown>) {
  return opsRequest('/ops/wallet/credit', { method: 'POST', json: body })
}

export async function opsDebit(body: Record<string, unknown>) {
  return opsRequest('/ops/wallet/debit', { method: 'POST', json: body })
}
