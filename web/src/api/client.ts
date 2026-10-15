// 开发代理与生产同源：API 始终走站点根 /api（与 /mgr/ 静态分离）
export const API_ROOT = '/api'

import { MANAGER_TOKEN_KEY, markLogin, setManagerToken } from './sso'

const PRODUCT = 'mgr'

export function getToken(): string | null {
  return localStorage.getItem(MANAGER_TOKEN_KEY)
}

export function setToken(token: string | null) {
  if (token) {
    setManagerToken(token)
    markLogin(PRODUCT)
  } else {
    setManagerToken(null)
  }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function apiRequest<T = unknown>(
  path: string,
  options: RequestInit & { json?: unknown; skipAuth?: boolean } = {},
): Promise<T> {
  const { json, skipAuth, headers: extraHeaders, ...rest } = options
  const headers = new Headers(extraHeaders || {})
  if (json !== undefined) headers.set('Content-Type', 'application/json')
  if (!skipAuth) {
    const token = getToken()
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
