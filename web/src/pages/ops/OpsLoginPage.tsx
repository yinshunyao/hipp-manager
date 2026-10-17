import { useState } from 'react'
import { Button, Card, Form, Input, Typography, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../../api/client'
import { opsLogin } from '../../api/ops'
import { useOpsStore } from '../../store/ops'

export default function OpsLoginPage() {
  const navigate = useNavigate()
  const setAdmin = useOpsStore((s) => s.setAdmin)
  const [loading, setLoading] = useState(false)

  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#f5f5f5' }}>
      <Card style={{ width: 400 }} title="平台运营台登录">
        <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
          使用 CLI 创建的平台管理员账号
        </Typography.Paragraph>
        <Form
          layout="vertical"
          onFinish={async (v) => {
            setLoading(true)
            try {
              const data = await opsLogin(v.username, v.password)
              setAdmin({ username: data.username })
              message.success('登录成功')
              navigate('/manager/users')
            } catch (e) {
              message.error(e instanceof ApiError ? e.message : '登录失败')
            } finally {
              setLoading(false)
            }
          }}
        >
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
            <Input autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true }]}>
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            登录
          </Button>
        </Form>
      </Card>
    </div>
  )
}
