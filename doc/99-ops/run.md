# hipp-manager 运行说明

## 目录

- 工程根：`hipp-manager/`
- 后端：`server/`（包名 `manager`）
- 前端：`web/`（生产构建产物由后端挂载 `/mgr/`）
- 默认数据：`data/manager.db`、`data/media/`

## 环境变量（见 `.env.sample`）

| 变量 | 说明 |
|:---|:---|
| `MANAGER_HOST` / `MANAGER_PORT` | 默认 `0.0.0.0:9100` |
| `MANAGER_SESSION_SECRET` | 会话 HMAC 密钥 |
| `MANAGER_S2S_KEY` | 服务间 `X-Manager-Key` |
| `DATABASE_URL` | 生产须 MySQL（如 `mysql+pymysql://user:pass@host:33306/hipp_manager`）；空则开发用 SQLite `data/manager.db` |
| `REDIS_URL` | 默认 `redis://127.0.0.1:6379/3`；`SMS_MOCK=1` 时可无 Redis（内存字典） |
| `SMS_MOCK` | `1` 时验证码固定 `123456` |
| `MANAGER_SMS_*` | 阿里云短信（非 mock 时必填） |
| `WECHAT_PAY_*` | 微信 Native；未启用时可用 `RECHARGE_DEV_AUTO=1` |
| `ALIPAY_*` | 支付宝 RSA2；`ALIPAY_TRADE_MODE=page|precreate`；回调 `ALIPAY_NOTIFY_URL` |
| `RECHARGE_DEV_AUTO` | 开发模拟支付入账 |
| `MEDIA_PUBLIC_BASE` | 媒体绝对 URL 基址（如 `https://hipp.site`）；空则按请求 Host 推导 |
| `MEDIA_MAX_BYTES` | 单文件上限，默认 20971520（20MiB） |
| `MEDIA_DIR` | 可选，覆盖默认 `data/media/` |

公共媒体：`POST /api/media/upload`（Bearer）；`DELETE /api/media`；S2S `POST /api/s2s/media/delete`、`POST /api/s2s/media/gc`；静态读 `GET /media/...`。生产 Nginx 须反代 `/media/`，且 `/api/media/` 的 `client_max_body_size` ≥20m。孤儿定时由各产品（如 or）在凌晨触发 gc。

存量用户导入（MySQL 已建库后）：`PYTHONPATH=server python -m manager.import_legacy`（从同实例 `hipp` + `voicefix` 按手机号合并）。

平台管理员（运营台 `/mgr/manager/`，亦可供 or/vf/cert 管理端校验）。新建与 CLI 重置均为初始密码 `123456`，登录后在运营台「改密」自行修改；命令行不设自定义口令：

```bash
PYTHONPATH=server python -m manager.ops_admin create --username <name_or_phone>
PYTHONPATH=server python -m manager.ops_admin reset-password --username <name_or_phone>
```

## 启动后端

```bash
cd hipp-manager
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp -n .env.sample .env
PYTHONPATH=server python -m manager
```

## 启动前端（开发）

```bash
cd hipp-manager/web
npm install
npm run dev
```

生产：`npm run build`，后端挂载 `web/dist` 到 `/mgr/`。

## 业务系统接入

- hipp-https：`HIPP_MANAGER_BASE=http://127.0.0.1:9100`
- VoiceFix（必填）：`HIPP_MANAGER_BASE` + `HIPP_MANAGER_KEY`（= `MANAGER_S2S_KEY`）；登录/充值/支付/订单/扣款全走本服务；微信/支付宝 `notify_url` 须指向本服务
- hipp-or：`HIPP_MANAGER_BASE`；用户侧（platform=1）短信发码与登录走本服务；管理端员工账号可仍用本地口令

## 支付回调

| 渠道 | 公网路径 | env |
|:---|:---|:---|
| 微信 | `POST {公网}/api/wallet/notify/wechat` | `WECHAT_PAY_NOTIFY_URL` |
| 支付宝 | `POST {公网}/api/wallet/notify/alipay` | `ALIPAY_NOTIFY_URL` |

账单、流水、入账只在本服务处理；VoiceFix / hipp-https 本地支付回调返回 410。
