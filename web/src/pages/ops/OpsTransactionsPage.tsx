import { useEffect, useState } from 'react'
import { Button, Input, Select, Space, Table, message } from 'antd'
import { ApiError } from '../../api/client'
import { listOpsTransactions } from '../../api/ops'

const PRODUCTS = [
  { value: '', label: '全部产品' },
  { value: 'mgr', label: 'mgr' },
  { value: 'or', label: 'or' },
  { value: 'vf', label: 'vf' },
  { value: 'cert', label: 'cert' },
]

export default function OpsTransactionsPage() {
  const [items, setItems] = useState<Record<string, unknown>[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [phone, setPhone] = useState('')
  const [product, setProduct] = useState('')
  const [bizType, setBizType] = useState('')
  const [loading, setLoading] = useState(false)

  const load = async (p = page) => {
    setLoading(true)
    try {
      const data = await listOpsTransactions({
        page: p,
        page_size: 20,
        phone,
        product,
        biz_type: bizType,
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
        <Input
          placeholder="biz_type"
          value={bizType}
          onChange={(e) => setBizType(e.target.value)}
          style={{ width: 180 }}
        />
        <Button type="primary" onClick={() => void load(1)}>
          查询
        </Button>
      </Space>
      <Table
        rowKey="tx_id"
        loading={loading}
        dataSource={items}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => void load(p),
        }}
        columns={[
          { title: '时间', dataIndex: 'created_at', width: 170 },
          { title: '类型', dataIndex: 'type', width: 90 },
          {
            title: '金额',
            dataIndex: 'amount',
            render: (v: number) => Number(v).toFixed(2),
          },
          { title: 'product', dataIndex: 'product', width: 80 },
          { title: 'biz_type', dataIndex: 'biz_type' },
          {
            title: '余额后',
            dataIndex: 'balance_after',
            render: (v: number) => Number(v).toFixed(2),
          },
          { title: '备注', dataIndex: 'remark', ellipsis: true },
        ]}
      />
    </div>
  )
}
