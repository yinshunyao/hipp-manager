import { useEffect, useState } from 'react'
import { Button, Input, Select, Space, Table, Modal, message, Tag } from 'antd'
import { ApiError } from '../../api/client'
import {
  listOpsUsers,
  resetUserPassword,
  setUserBlocked,
  type OpsUser,
} from '../../api/ops'

const PRODUCTS = [
  { value: '', label: '全部来源' },
  { value: 'mgr', label: 'mgr' },
  { value: 'or', label: 'or' },
  { value: 'vf', label: 'vf' },
  { value: 'cert', label: 'cert' },
]

export default function OpsUsersPage() {
  const [items, setItems] = useState<OpsUser[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [phone, setPhone] = useState('')
  const [source, setSource] = useState('')
  const [loading, setLoading] = useState(false)

  const load = async (p = page) => {
    setLoading(true)
    try {
      const data = await listOpsUsers({
        page: p,
        page_size: 20,
        phone,
        register_source: source,
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
        <Select
          options={PRODUCTS}
          value={source}
          onChange={setSource}
          style={{ width: 140 }}
        />
        <Button type="primary" onClick={() => void load(1)}>
          查询
        </Button>
      </Space>
      <Table
        rowKey="user_id"
        loading={loading}
        dataSource={items}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => void load(p),
        }}
        columns={[
          { title: '手机号', dataIndex: 'phone' },
          { title: '昵称', dataIndex: 'nickname' },
          {
            title: '来源',
            dataIndex: 'register_source',
            render: (v: string) => <Tag>{v}</Tag>,
          },
          {
            title: '余额',
            dataIndex: 'balance',
            render: (v: number) => `¥${Number(v).toFixed(2)}`,
          },
          {
            title: '状态',
            dataIndex: 'is_blocked',
            render: (v: boolean) => (v ? <Tag color="red">已拉黑</Tag> : <Tag>正常</Tag>),
          },
          {
            title: '操作',
            render: (_, row) => (
              <Space>
                <Button
                  size="small"
                  danger={!row.is_blocked}
                  onClick={() => {
                    void setUserBlocked(row.user_id, !row.is_blocked)
                      .then(() => {
                        message.success(row.is_blocked ? '已解黑' : '已拉黑')
                        return load(page)
                      })
                      .catch((e) =>
                        message.error(e instanceof ApiError ? e.message : '失败'),
                      )
                  }}
                >
                  {row.is_blocked ? '解黑' : '拉黑'}
                </Button>
                <Button
                  size="small"
                  onClick={() => {
                    let pwd = ''
                    Modal.confirm({
                      title: `重置密码：${row.phone}`,
                      content: (
                        <Input.Password
                          placeholder="新密码至少 6 位"
                          onChange={(e) => {
                            pwd = e.target.value
                          }}
                        />
                      ),
                      onOk: async () => {
                        if (pwd.length < 6) {
                          message.error('密码至少 6 位')
                          throw new Error('pwd')
                        }
                        await resetUserPassword(row.user_id, pwd)
                        message.success('已重置')
                      },
                    })
                  }}
                >
                  改密
                </Button>
              </Space>
            ),
          },
        ]}
      />
    </div>
  )
}
