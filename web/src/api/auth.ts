import { apiRequest, setToken } from './client'

export type UserProfile = {
  user_id: string
  phone: string
  nickname: string
  has_password: boolean
  balance: number
}

export async function sendSms(phone: string) {
  return apiRequest<{ detail?: string }>('/auth/sms/send', {
    method: 'POST',
    json: { phone },
    skipAuth: true,
  })
}

export async function loginSms(phone: string, code: string) {
  const data = await apiRequest<{ token: string } & UserProfile>('/auth/sms/login', {
    method: 'POST',
    json: { phone, code, product: 'mgr' },
    skipAuth: true,
  })
  setToken(data.token)
  return data
}

export async function loginPassword(phone: string, password: string) {
  const data = await apiRequest<{ token: string } & UserProfile>('/auth/login', {
    method: 'POST',
    json: { phone, password },
    skipAuth: true,
  })
  setToken(data.token)
  return data
}

export async function fetchMe() {
  return apiRequest<UserProfile>('/auth/me')
}

export async function logoutRemote() {
  try {
    await apiRequest<{ detail?: string }>('/auth/logout', { method: 'POST' })
  } catch {
    /* 幂等：无会话也可本地清 */
  }
}

export async function updateNickname(nickname: string) {
  return apiRequest<UserProfile>('/auth/me', {
    method: 'PATCH',
    json: { nickname },
  })
}

export async function setPassword(newPassword: string, oldPassword?: string) {
  return apiRequest<UserProfile>('/auth/password', {
    method: 'POST',
    json: { new_password: newPassword, old_password: oldPassword },
  })
}
