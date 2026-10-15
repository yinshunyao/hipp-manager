import { useEffect } from 'react'
import { Button, Card, Form, Input, Space, Typography, message } from 'antd'
import { fetchMe, setPassword, updateNickname } from '../api/auth'
import { useAuthStore } from '../store/auth'
import { ApiError } from '../api/client'

export default function ProfilePage() {
  const user = useAuthStore((s) => s.user)
  const setUser = useAuthStore((s) => s.setUser)
  const [nickForm] = Form.useForm()
  const [pwdForm] = Form.useForm()

  useEffect(() => {
    nickForm.setFieldsValue({ nickname: user?.nickname || '' })
  }, [user, nickForm])

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card title="基本资料">
        <Typography.Paragraph>手机号：{user?.phone}</Typography.Paragraph>
        <Typography.Paragraph>余额：¥{Number(user?.balance ?? 0).toFixed(2)}</Typography.Paragraph>
        <Form
          form={nickForm}
          layout="inline"
          onFinish={async (v) => {
            try {
              const next = await updateNickname(v.nickname)
              setUser(next)
              message.success('昵称已更新')
            } catch (e) {
              message.error(e instanceof ApiError ? e.message : '更新失败')
            }
          }}
        >
          <Form.Item name="nickname" label="昵称" rules={[{ required: true }]}>
            <Input style={{ width: 240 }} maxLength={50} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            保存
          </Button>
        </Form>
      </Card>
      <Card title={user?.has_password ? '修改密码' : '设置密码'}>
        <Form
          form={pwdForm}
          layout="vertical"
          style={{ maxWidth: 360 }}
          onFinish={async (v) => {
            try {
              const next = await setPassword(v.new_password, v.old_password)
              setUser(next)
              pwdForm.resetFields()
              message.success('密码已保存')
              await fetchMe().then(setUser)
            } catch (e) {
              message.error(e instanceof ApiError ? e.message : '保存失败')
            }
          }}
        >
          {user?.has_password ? (
            <Form.Item name="old_password" label="当前密码" rules={[{ required: true }]}>
              <Input.Password />
            </Form.Item>
          ) : null}
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[{ required: true, min: 6, message: '至少 6 位' }]}
          >
            <Input.Password />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            保存密码
          </Button>
        </Form>
      </Card>
    </Space>
  )
}
