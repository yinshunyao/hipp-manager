import { Button, Card, Form, Input, InputNumber, Radio, Select, message } from 'antd'
import { ApiError } from '../../api/client'
import { opsCredit, opsDebit } from '../../api/ops'

const PRODUCTS = [
  { value: 'mgr', label: 'mgr' },
  { value: 'or', label: 'or' },
  { value: 'vf', label: 'vf' },
  { value: 'cert', label: 'cert' },
]

const BIZ_OPTIONS = [
  { value: 'recharge_manual', label: 'recharge_manual' },
  { value: 'refund_manual', label: 'refund_manual' },
  { value: 'refund_task_cancel', label: 'refund_task_cancel' },
  { value: 'refund_appeal', label: 'refund_appeal' },
  { value: 'consume_session', label: 'consume_session' },
  { value: 'consume_voice', label: 'consume_voice' },
  { value: 'consume_cert', label: 'consume_cert' },
]

export default function OpsAdjustPage() {
  const [form] = Form.useForm()

  return (
    <Card title="手工动账" className="page-content-narrow" style={{ maxWidth: 480 }}>
      <Form
        form={form}
        layout="vertical"
        initialValues={{ kind: 'credit', product: 'mgr', biz_type: 'refund_manual' }}
        onFinish={async (v) => {
          try {
            const body = {
              phone: v.phone,
              amount: v.amount,
              product: v.product,
              biz_type: v.biz_type,
              remark: v.remark || '',
              ref_id: v.ref_id || '',
            }
            if (v.kind === 'credit') await opsCredit(body)
            else await opsDebit(body)
            message.success('已完成')
            form.resetFields(['amount', 'remark', 'ref_id'])
          } catch (e) {
            message.error(e instanceof ApiError ? e.message : '失败')
          }
        }}
      >
        <Form.Item name="kind" label="方向" rules={[{ required: true }]}>
          <Radio.Group
            options={[
              { value: 'credit', label: '入账（退费/补偿）' },
              { value: 'debit', label: '扣款' },
            ]}
          />
        </Form.Item>
        <Form.Item name="phone" label="手机号" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="amount" label="金额" rules={[{ required: true }]}>
          <InputNumber min={0.01} precision={2} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="product" label="product" rules={[{ required: true }]}>
          <Select options={PRODUCTS} />
        </Form.Item>
        <Form.Item name="biz_type" label="biz_type" rules={[{ required: true }]}>
          <Select options={BIZ_OPTIONS} showSearch allowClear={false} />
        </Form.Item>
        <Form.Item name="ref_id" label="业务单号">
          <Input />
        </Form.Item>
        <Form.Item name="remark" label="备注">
          <Input.TextArea rows={2} />
        </Form.Item>
        <Button type="primary" htmlType="submit" block>
          提交
        </Button>
      </Form>
    </Card>
  )
}
