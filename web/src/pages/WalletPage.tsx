import { useEffect, useState } from 'react'
import { Button, Card, InputNumber, Space, Typography, message, Modal } from 'antd'
import { AlipayCircleOutlined, WechatOutlined } from '@ant-design/icons'
import { QRCodeSVG } from 'qrcode.react'
import {
  createRecharge,
  devPay,
  fetchBalance,
  fetchPayChannels,
  fetchPresets,
  getRecharge,
} from '../api/wallet'
import { fetchMe } from '../api/auth'
import { useAuthStore } from '../store/auth'
import { ApiError } from '../api/client'

function PayChannelCards({
  channels,
  value,
  onChange,
}: {
  channels: Array<{ id: string; label: string }>
  value: string
  onChange: (id: string) => void
}) {
  if (channels.length === 0) return null
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
        gap: 12,
        marginBottom: 16,
      }}
    >
      {channels.map((c) => {
        const active = value === c.id
        const isAlipay = c.id === 'alipay'
        const accent = isAlipay ? '#1677ff' : '#07c160'
        return (
          <button
            key={c.id}
            type="button"
            onClick={() => onChange(c.id)}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              minHeight: 88,
              padding: '16px 12px',
              borderRadius: 10,
              border: `2px solid ${active ? accent : '#e5e5e5'}`,
              background: active ? `${accent}14` : '#fff',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: 16,
              color: active ? accent : '#262626',
            }}
          >
            {isAlipay ? (
              <AlipayCircleOutlined style={{ fontSize: 28, color: accent }} />
            ) : (
              <WechatOutlined style={{ fontSize: 28, color: accent }} />
            )}
            {c.label}
          </button>
        )
      })}
    </div>
  )
}

export default function WalletPage() {
  const setUser = useAuthStore((s) => s.setUser)
  const [balance, setBalance] = useState(0)
  const [presets, setPresets] = useState<number[]>([])
  const [amount, setAmount] = useState<number>(50)
  const [loading, setLoading] = useState(false)
  const [payUrl, setPayUrl] = useState('')
  const [orderId, setOrderId] = useState('')
  const [devMode, setDevMode] = useState(false)
  const [channel, setChannel] = useState<string>('')
  const [channels, setChannels] = useState<Array<{ id: string; label: string }>>([])
  const [payHint, setPayHint] = useState('请扫码完成支付')

  async function refresh() {
    const b = await fetchBalance()
    setBalance(b.balance)
    const me = await fetchMe()
    setUser(me)
  }

  useEffect(() => {
    refresh().catch(() => undefined)
    fetchPresets()
      .then((r) => {
        const amounts = r.items.map((i) => i.amount)
        setPresets(amounts)
        if (amounts[0]) setAmount(amounts[0])
      })
      .catch(() => undefined)
    fetchPayChannels()
      .then((r) => {
        setChannels(r.items || [])
        if (r.items?.[0]?.id) setChannel(r.items[0].id)
      })
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    if (!orderId || !payUrl) return
    const timer = window.setInterval(async () => {
      try {
        const o = await getRecharge(orderId)
        if (o.status === 'paid') {
          message.success('充值成功')
          setPayUrl('')
          setOrderId('')
          await refresh()
        }
      } catch {
        /* ignore */
      }
    }, 2500)
    return () => window.clearInterval(timer)
  }, [orderId, payUrl])

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card title="余额">
        <Typography.Title level={2} style={{ margin: 0 }}>
          ¥{balance.toFixed(2)}
        </Typography.Title>
      </Card>
      <Card title="充值">
        <PayChannelCards channels={channels} value={channel} onChange={setChannel} />
        <Typography.Paragraph type="secondary" style={{ marginTop: 0, marginBottom: 12 }}>
          选择金额或自定义整数
        </Typography.Paragraph>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
            gap: 10,
            marginBottom: 16,
          }}
        >
          {presets.map((a) => {
            const active = amount === a
            return (
              <Button
                key={a}
                size="large"
                type={active ? 'primary' : 'default'}
                ghost={active}
                onClick={() => setAmount(a)}
                style={{ height: 48, fontWeight: 600 }}
              >
                ¥{a}
              </Button>
            )
          })}
        </div>
        <Space.Compact style={{ width: '100%' }}>
          <InputNumber
            min={1}
            value={amount}
            onChange={(v) => setAmount(Number(v || 0))}
            prefix="¥"
            size="large"
            style={{ width: '100%' }}
          />
          <Button
            type="primary"
            size="large"
            loading={loading}
            style={{ minWidth: 96 }}
            onClick={async () => {
              setLoading(true)
              try {
                const order = await createRecharge(amount, channel || undefined)
                setOrderId(order.order_id)
                setDevMode(Boolean(order.dev_pay))
                const qr = order.code_url || order.pay_url || ''
                if (qr) {
                  setPayUrl(qr)
                  setPayHint(
                    order.channel === 'alipay'
                      ? '请使用支付宝扫码或打开支付链接完成支付'
                      : '请使用微信扫码支付',
                  )
                } else if (order.dev_pay) {
                  Modal.confirm({
                    title: '开发入账',
                    content: '未配置支付渠道，是否模拟支付成功？',
                    onOk: async () => {
                      await devPay(order.order_id)
                      message.success('入账成功')
                      await refresh()
                    },
                  })
                } else {
                  message.warning('未返回支付链接，请配置微信或支付宝')
                }
              } catch (e) {
                message.error(e instanceof ApiError ? e.message : '下单失败')
              } finally {
                setLoading(false)
              }
            }}
          >
            去充值
          </Button>
        </Space.Compact>
        {payUrl ? (
          <div style={{ marginTop: 24, textAlign: 'center' }}>
            <QRCodeSVG value={payUrl} size={200} />
            <Typography.Paragraph type="secondary">{payHint}</Typography.Paragraph>
            {payUrl.startsWith('http') ? (
              <Typography.Link href={payUrl} target="_blank" rel="noreferrer">
                打开支付页面
              </Typography.Link>
            ) : null}
          </div>
        ) : null}
        {devMode && orderId && !payUrl ? (
          <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
            开发模式订单：{orderId}
          </Typography.Paragraph>
        ) : null}
      </Card>
    </Space>
  )
}
