import { apiRequest } from './client'

export async function fetchBalance() {
  return apiRequest<{ balance: number }>('/wallet/balance')
}

export async function fetchPresets() {
  return apiRequest<{ items: { amount: number }[] }>('/wallet/presets')
}

export async function fetchPayChannels() {
  return apiRequest<{ items: Array<{ id: string; label: string; kind: string }> }>(
    '/wallet/pay-channels',
  )
}

export async function createRecharge(amount: number, channel?: string) {
  const body: { amount: number; channel?: string; product: string } = {
    amount,
    product: 'mgr',
  }
  if (channel) body.channel = channel
  return apiRequest<{
    order_id: string
    amount: number
    status: string
    channel?: string
    code_url: string
    pay_url?: string
    dev_pay: boolean
  }>('/wallet/recharge', { method: 'POST', json: body })
}

export async function getRecharge(orderId: string) {
  return apiRequest<{ order_id: string; status: string; amount: number }>(
    `/wallet/recharge/${orderId}`,
  )
}

export async function devPay(orderId: string) {
  return apiRequest<{ balance: number; status: string }>(
    `/wallet/recharge/${orderId}/dev-pay`,
    { method: 'POST' },
  )
}

export async function fetchTransactions(page = 1, pageSize = 20, product = '') {
  const q = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (product) q.set('product', product)
  return apiRequest<{
    total: number
    items: Array<{
      tx_id: string
      type: string
      amount: number
      product: string
      balance_after: number
      remark: string
      created_at: string
    }>
  }>(`/wallet/transactions?${q}`)
}

export async function fetchBills() {
  return apiRequest<{ items: Array<{ year_month: string; amount: number }> }>(
    '/wallet/bills',
  )
}
