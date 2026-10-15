import { useEffect, useState } from 'react'
import { Card, Select, Table, Tag } from 'antd'
import { fetchTransactions } from '../api/wallet'

const TYPE_LABEL: Record<string, string> = {
  recharge: '充值',
  consume: '消费',
  refund: '退费',
}

export default function TransactionsPage() {
  const [product, setProduct] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [rows, setRows] = useState<
    Array<{
      tx_id: string
      type: string
      amount: number
      product: string
      balance_after: number
      remark: string
      created_at: string
    }>
  >([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    fetchTransactions(page, 20, product)
      .then((r) => {
        setRows(r.items)
        setTotal(r.total)
      })
      .finally(() => setLoading(false))
  }, [page, product])

  return (
    <Card
      title="交易流水"
      extra={
        <Select
          style={{ width: 140 }}
          allowClear
          placeholder="全部产品"
          value={product || undefined}
          onChange={(v) => {
            setPage(1)
            setProduct(v || '')
          }}
          options={[
            { value: 'manager', label: 'manager' },
            { value: 'cert', label: 'cert' },
            { value: 'voice', label: 'voice' },
            { value: 'or', label: 'or' },
          ]}
        />
      }
    >
      <Table
        rowKey="tx_id"
        loading={loading}
        dataSource={rows}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: setPage,
        }}
        columns={[
          { title: '时间', dataIndex: 'created_at', width: 180 },
          {
            title: '类型',
            dataIndex: 'type',
            width: 90,
            render: (t: string) => TYPE_LABEL[t] || t,
          },
          {
            title: '产品',
            dataIndex: 'product',
            width: 90,
            render: (p: string) => <Tag>{p}</Tag>,
          },
          {
            title: '金额',
            dataIndex: 'amount',
            width: 100,
            render: (a: number, row) =>
              row.type === 'consume' ? `-¥${a.toFixed(2)}` : `+¥${a.toFixed(2)}`,
          },
          {
            title: '余额',
            dataIndex: 'balance_after',
            width: 100,
            render: (a: number) => `¥${a.toFixed(2)}`,
          },
          { title: '备注', dataIndex: 'remark' },
        ]}
      />
    </Card>
  )
}
