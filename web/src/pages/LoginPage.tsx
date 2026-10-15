import { useState } from 'react'
import { Button, Card, Form, Input, Tabs, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import { loginPassword, loginSms, sendSms } from '../api/auth'
import { useAuthStore } from '../store/auth'
import { ApiError } from '../api/client'

export default function LoginPage() {
  const navigate = useNavigate()
  const setUser = useAuthStore((s) => s.setUser)
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(false)
  const [smsForm] = Form.useForm()

  async function onSend() {
    const phone = smsForm.getFieldValue('phone')
    if (!phone) {
      message.warning('请先填写手机号')
      return
    }
    setSending(true)
    try {
      await sendSms(phone)
      message.success('验证码已发送')
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : '发送失败')
    } finally {
      setSending(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24 }}>
      <Card style={{ width: 420 }} title="账户登录">
        <Tabs
          items={[
            {
              key: 'sms',
              label: '短信登录',
              children: (
                <Form
                  form={smsForm}
                  layout="vertical"
                  onFinish={async (v) => {
                    setLoading(true)
                    try {
                      const user = await loginSms(v.phone, v.code)
                      setUser(user)
                      navigate('/profile')
                    } catch (e) {
                      message.error(e instanceof ApiError ? e.message : '登录失败')
                    } finally {
                      setLoading(false)
                    }
                  }}
                >
                  <Form.Item name="phone" label="手机号" rules={[{ required: true }]}>
                    <Input placeholder="11 位手机号" maxLength={11} />
                  </Form.Item>
                  <Form.Item name="code" label="验证码" rules={[{ required: true }]}>
                    <Input
                      placeholder="验证码"
                      addonAfter={
                        <Button type="link" size="small" loading={sending} onClick={onSend}>
                          发送
                        </Button>
                      }
                    />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" block loading={loading}>
                    登录
                  </Button>
                </Form>
              ),
            },
            {
              key: 'password',
              label: '密码登录',
              children: (
                <Form
                  layout="vertical"
                  onFinish={async (v) => {
                    setLoading(true)
                    try {
                      const user = await loginPassword(v.phone, v.password)
                      setUser(user)
                      navigate('/profile')
                    } catch (e) {
                      message.error(e instanceof ApiError ? e.message : '登录失败')
                    } finally {
                      setLoading(false)
                    }
                  }}
                >
                  <Form.Item name="phone" label="手机号" rules={[{ required: true }]}>
                    <Input placeholder="11 位手机号" maxLength={11} />
                  </Form.Item>
                  <Form.Item name="password" label="密码" rules={[{ required: true }]}>
                    <Input.Password />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" block loading={loading}>
                    登录
                  </Button>
                </Form>
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}
