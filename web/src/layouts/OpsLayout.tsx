import { Layout, Menu, Typography, Button, theme } from 'antd'
import {
  UserOutlined,
  TransactionOutlined,
  ShoppingOutlined,
  DollarOutlined,
  KeyOutlined,
  LogoutOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useOpsStore } from '../store/ops'

const { Header, Sider, Content } = Layout

export default function OpsLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const admin = useOpsStore((s) => s.admin)
  const logout = useOpsStore((s) => s.logout)
  const { token } = theme.useToken()
  const selected = location.pathname.includes('/manager/password')
    ? 'password'
    : location.pathname.includes('/manager/adjust')
      ? 'adjust'
      : location.pathname.includes('/manager/recharge')
        ? 'recharge'
        : location.pathname.includes('/manager/transactions')
          ? 'transactions'
          : 'users'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider breakpoint="lg" collapsedWidth={64} theme="dark" width={220}>
        <div style={{ padding: '16px 20px', color: '#fff', fontWeight: 700, fontSize: 18 }}>
          平台运营台
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selected]}
          items={[
            { key: 'users', icon: <UserOutlined />, label: '用户' },
            { key: 'transactions', icon: <TransactionOutlined />, label: '流水' },
            { key: 'recharge', icon: <ShoppingOutlined />, label: '充值单' },
            { key: 'adjust', icon: <DollarOutlined />, label: '手工动账' },
            { key: 'password', icon: <KeyOutlined />, label: '改密' },
          ]}
          onClick={({ key }) => navigate(`/manager/${key}`)}
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
          <Typography.Text>{admin?.username || '管理员'}</Typography.Text>
          <Button
            icon={<LogoutOutlined />}
            onClick={() => {
              logout()
              navigate('/manager/login')
            }}
          >
            退出
          </Button>
        </Header>
        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
