import { useState } from 'react'
import { Layout, Menu, Typography, Button, theme, Avatar, Space } from 'antd'
import {
  UserOutlined,
  WalletOutlined,
  TransactionOutlined,
  FileTextOutlined,
  LogoutOutlined,
  MailOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/auth'
import ContactUsModal from '../components/ContactUsModal'

const { Header, Sider, Content } = Layout

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const { token } = theme.useToken()
  const [contactOpen, setContactOpen] = useState(false)
  const selected = location.pathname.startsWith('/wallet')
    ? 'wallet'
    : location.pathname.startsWith('/transactions')
      ? 'transactions'
      : location.pathname.startsWith('/bills')
        ? 'bills'
        : 'profile'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider breakpoint="lg" collapsedWidth={64} theme="dark" width={220}>
        <div style={{ padding: '16px 20px', color: '#fff', fontWeight: 700, fontSize: 18 }}>
          账户中心
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selected]}
          items={[
            { key: 'profile', icon: <UserOutlined />, label: '资料与改密' },
            { key: 'wallet', icon: <WalletOutlined />, label: '余额充值' },
            { key: 'transactions', icon: <TransactionOutlined />, label: '流水' },
            { key: 'bills', icon: <FileTextOutlined />, label: '月账单' },
            { key: 'contact', icon: <MailOutlined />, label: '联系我们' },
          ]}
          onClick={({ key }) => {
            if (key === 'contact') {
              setContactOpen(true)
              return
            }
            navigate(`/${key === 'profile' ? 'profile' : key}`)
          }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: token.colorBgContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            gap: 16,
            paddingInline: 24,
          }}
        >
          <Space size={10}>
            <Avatar size={28} icon={<UserOutlined />} />
            <Typography.Text>{user?.nickname || user?.phone || '用户'}</Typography.Text>
            <Typography.Text type="secondary">¥{Number(user?.balance ?? 0).toFixed(2)}</Typography.Text>
          </Space>
          <Button
            icon={<LogoutOutlined />}
            onClick={() => {
              logout()
              navigate('/login')
            }}
          >
            退出
          </Button>
        </Header>
        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </Layout>
      <ContactUsModal open={contactOpen} onClose={() => setContactOpen(false)} />
    </Layout>
  )
}
