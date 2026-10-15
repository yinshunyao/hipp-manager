import { useEffect, useState } from 'react'
import { Card, Table } from 'antd'
import { fetchBills } from '../api/wallet'

export default function BillsPage() {
  const [rows, setRows] = useState<Array<{ year_month: string; amount: number }>>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    fetchBills()
      .then((r) => setRows(r.items))
      .finally(() => setLoading(false))
  }, [])

  return (
    <Card title="月账单（消费汇总）">
      <Table
        rowKey="year_month"
        loading={loading}
        dataSource={rows}
        pagination={false}
        columns={[
          { title: '月份', dataIndex: 'year_month' },
          {
            title: '消费合计',
            dataIndex: 'amount',
            render: (a: number) => `¥${Number(a).toFixed(2)}`,
          },
        ]}
      />
    </Card>
  )
}
