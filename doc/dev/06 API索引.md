# HTTP API 索引

鉴权约定（细节见对应 DR）：

- 用户：`Authorization: Bearer <token>`
- 运营：运营会话 Bearer（`/api/ops/...`）
- S2S：请求头 `X-Manager-Key: <MANAGER_S2S_KEY>`

字段与错误码以 `doc/02-dr` 各模块为准。路由实现：`server/manager/api.py`、`server/media/`。

## 身份 `/api/auth/*`

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| POST | `/api/auth/sms/send` | 发短信验证码 |
| POST | `/api/auth/sms/login` | 短信登录（可自动注册） |
| POST | `/api/auth/login` | 密码登录 |
| POST | `/api/auth/logout` | 登出（吊销） |
| GET | `/api/auth/me` | 当前用户（业务侧在线校验常用） |
| PATCH | `/api/auth/me` | 改资料 |
| POST | `/api/auth/password` | 设置/修改密码 |
| POST | `/api/auth/password/reset` | 短信重置密码 |

## 钱包 `/api/wallet/*`

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| GET | `/api/wallet/balance` | 余额 |
| GET | `/api/wallet/presets` | 充值面额 |
| GET | `/api/wallet/pay-channels` | 可用支付渠道 |
| POST | `/api/wallet/recharge` | 下单 |
| GET | `/api/wallet/recharge/orders` | 充值单列表 |
| GET | `/api/wallet/recharge/{order_id}` | 单笔查询 |
| POST | `/api/wallet/recharge/{order_id}/dev-pay` | 开发模拟支付 |
| GET | `/api/wallet/transactions` | 流水 |
| GET | `/api/wallet/bills` | 月账单 |
| POST | `/api/wallet/notify/wechat` | 微信异步通知 |
| POST | `/api/wallet/notify/alipay` | 支付宝异步通知 |

## S2S `/api/s2s/*`

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| GET | `/api/s2s/wallet/balance` | 查余额 |
| POST | `/api/s2s/wallet/deduct` | 扣款（须 product + biz_type） |
| POST | `/api/s2s/wallet/credit` | 入账 |
| POST | `/api/s2s/media/delete` | 删媒体 |
| POST | `/api/s2s/media/gc` | 媒体孤儿 GC |

## 运营 `/api/ops/*`

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| POST | `/api/ops/auth/login` 等 | 运营登录 / 校验 / 登出 / me / 改密 |
| GET | `/api/ops/users` | 用户列表 |
| PUT | `/api/ops/users/{user_id}/blocked` | 拉黑/解禁 |
| POST | `/api/ops/users/{user_id}/password` | 重置用户密码 |
| GET | `/api/ops/transactions` | 全站流水 |
| GET | `/api/ops/recharge/orders` | 充值单 |
| POST | `/api/ops/wallet/credit` | 手工入账 |
| POST | `/api/ops/wallet/debit` | 手工扣款 |

## 媒体

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| POST | `/api/media/upload` | 用户上传（Bearer） |
| DELETE | `/api/media` | 用户删除 |
| GET | `/media/...` | 静态读取 |
