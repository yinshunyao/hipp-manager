import { Button, Card, Form, Input, message } from 'antd'
import { ApiError } from '../../api/client'
import { opsChangePassword } from '../../api/ops'

export default function OpsPasswordPage() {
  const [form] = Form.useForm()

  return (
    <Card title="修改登录密码" style={{ maxWidth: 420 }}>
      <Form
        form={form}
        layout="vertical"
        onFinish={async (v) => {
          try {
            await opsChangePassword(v.old_password, v.new_password)
            form.resetFields()
            message.success('密码已更新')
          } catch (e) {
            message.error(e instanceof ApiError ? e.message : '修改失败')
          }
        }}
      >
        <Form.Item name="old_password" label="当前密码" rules={[{ required: true }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Form.Item
          name="new_password"
          label="新密码"
          rules={[{ required: true, min: 6, message: '至少 6 位' }]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="confirm"
          label="确认新密码"
          dependencies={['new_password']}
          rules={[
            { required: true, message: '请再次输入新密码' },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue('new_password') === value) {
                  return Promise.resolve()
                }
                return Promise.reject(new Error('两次输入不一致'))
              },
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Button type="primary" htmlType="submit">
          保存
        </Button>
      </Form>
    </Card>
  )
}
