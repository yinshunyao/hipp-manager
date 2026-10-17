import { useEffect, useState } from 'react'
import { Button, Input, Select, Space, Table, message } from 'antd'
import { ApiError } from '../../api/client'
import { listOpsRechargeOrders } from '../../api/ops'

const PRODUCTS = [
  { value: '', label: '全部产品' },
  { value: 'mgr', label: 'mgr' },
  { value: 'or', label: 'or' },
  { value: 'vf', label: 'vf' },
  { value: 'cert', label: 'cert' },
]

export default function OpsRechargePage() {
  const [items, setItems] = useState<Record<string, unknown>[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [phone, setPhone] = useState('')
  const [product, setProduct] = useState('')
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)

  const load = async (p = page) => {
    setLoading(true)
    try {
      const data = await listOpsRechargeOrders({
        page: p,
        page_size: 20,
        phone,
        product,
        status,
      })
      setItems(data.items)
      setTotal(data.total)
      setPage(p)
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Input
          placeholder="手机号"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          style={{ width: 160 }}
        />
        <Select options={PRODUCTS} value={product} onChange={setProduct} style={{ width: 120 }} />
        <Select
          allowClear
          placeholder="状态"
          value={status || undefined}
          onChange={(v) => setStatus(v || '')}
          style={{ width: 120 }}
          options={[
            { value: 'pending', label: 'pending' },
            { value: 'paid', label: 'paid' },
            { value: 'failed', label: 'failed' },
            { value: 'cancelled', label: 'cancelled' },
          ]}
        />
        <Button type="primary" onClick={() => void load(1)}>
          查询
        </Button>
      </Space>
      <Table
        rowKey="order_id"
        loading={loading}
        dataSource={items}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => void load(p),
        }}
        columns={[
          { title: '订单', dataIndex: 'order_id', ellipsis: true },
          { title: '金额', dataIndex: 'amount', render: (v: number) => Number(v).toFixed(2) },
          { title: '状态', dataIndex: 'status', width: 90 },
          { title: 'product', dataIndex: 'product', width: 80 },
          { title: 'biz_type', dataIndex: 'biz_type' },
          { title: '渠道', dataIndex: 'payment_channel', width: 90 },
          { title: '创建', dataIndex: 'created_at', width: 170 },
        ]}
      />
    </div>
  )
}
