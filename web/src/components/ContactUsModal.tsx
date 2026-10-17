import type { CSSProperties, ReactNode } from 'react'
import { Modal, Button, theme } from 'antd'
import { WalletOutlined, PhoneOutlined, GlobalOutlined, EnvironmentOutlined } from '@ant-design/icons'

/** 与 or 用户端「联系我们」弹窗字段一致。 */
export const COMPANY_CONTACT = {
  name: '成都智臻善算科技有限公司',
  contact: '殷先生',
  phone: '17302868369',
  creditCode: '91510106MAKFR2T55W',
  address: '四川省成都市金牛区光荣西路 67 号 1 栋 4 楼 517 号',
  site: 'http://hipp.site/',
  icp: '蜀ICP备2024076719号-1',
  icpUrl: 'https://beian.miit.gov.cn/',
} as const

type Props = {
  open: boolean
  onClose: () => void
}

export default function ContactUsModal({ open, onClose }: Props) {
  const { token } = theme.useToken()
  const accent = '#b8860b'

  const rows: { label: string; value: ReactNode; icon?: ReactNode }[] = [
    { label: '联系人', value: COMPANY_CONTACT.contact },
    {
      label: '微信 / 电话',
      icon: <PhoneOutlined style={{ color: accent }} />,
      value: (
        <a href={`tel:${COMPANY_CONTACT.phone}`} style={{ color: accent, fontWeight: 600 }}>
          {COMPANY_CONTACT.phone}
        </a>
      ),
    },
    { label: '统一社会信用代码', value: COMPANY_CONTACT.creditCode },
    {
      label: '公司地址',
      icon: <EnvironmentOutlined style={{ color: accent }} />,
      value: COMPANY_CONTACT.address,
    },
    {
      label: '公司网站',
      icon: <GlobalOutlined style={{ color: accent }} />,
      value: (
        <a href={COMPANY_CONTACT.site} target="_blank" rel="noopener noreferrer" style={{ color: accent }}>
          {COMPANY_CONTACT.site}
        </a>
      ),
    },
    {
      label: '备案号',
      value: (
        <a href={COMPANY_CONTACT.icpUrl} target="_blank" rel="noopener noreferrer" style={{ color: accent }}>
          {COMPANY_CONTACT.icp}
        </a>
      ),
    },
  ]

  const header: CSSProperties = {
    margin: '-20px -24px 20px',
    padding: '22px 24px 18px',
    background: 'linear-gradient(135deg, #d4a017 0%, #8b6914 55%, #5c450c 100%)',
    color: '#fff7e6',
    borderRadius: `${token.borderRadiusLG}px ${token.borderRadiusLG}px 0 0`,
  }

  return (
    <Modal open={open} onCancel={onClose} footer={null} destroyOnHidden width={480} styles={{ body: { paddingTop: 0 } }} closable>
      <div style={header}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: 12,
              background: 'rgba(255,255,255,0.16)',
              display: 'grid',
              placeItems: 'center',
              fontSize: 22,
              color: '#fff7e6',
            }}
          >
            <WalletOutlined />
          </div>
          <div>
            <div style={{ fontSize: 13, opacity: 0.9, letterSpacing: 0.4 }}>账户中心 · 联系我们</div>
            <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 1.35, marginTop: 2 }}>{COMPANY_CONTACT.name}</div>
          </div>
        </div>
      </div>
      <dl style={{ margin: 0, display: 'grid', gap: 0 }}>
        {rows.map((row) => (
          <div
            key={row.label}
            style={{
              display: 'grid',
              gridTemplateColumns: '112px 1fr',
              gap: 12,
              padding: '12px 0',
              borderBottom: `1px solid ${token.colorSplit}`,
              alignItems: 'start',
            }}
          >
            <dt style={{ color: token.colorTextSecondary, fontSize: 13, margin: 0 }}>{row.label}</dt>
            <dd style={{ margin: 0, display: 'flex', gap: 8, alignItems: 'flex-start', lineHeight: 1.55 }}>
              {row.icon}
              <span>{row.value}</span>
            </dd>
          </div>
        ))}
      </dl>
      <Button type="primary" block style={{ marginTop: 20, background: accent, borderColor: accent }} onClick={onClose}>
        关闭
      </Button>
    </Modal>
  )
}
