# 发布草稿

- **业务产品鉴权二次校验**：约定 cert / or（Web）/ vf 需鉴权接口由各后端向本服务 `/api/auth/me` 校验在线（短缓存）；吊销后各产品业务接口 401。本服务接口未改协议。
- **支付宝收款**：`ALIPAY_*` 公钥模式 RSA2；`POST /api/wallet/recharge` 支持 `channel=alipay|wechat`；`GET /api/wallet/pay-channels`；异步通知 `POST /api/wallet/notify/alipay` 验签入账。控制台可选支付渠道。
- **充值 UI**：支付渠道改为微信/支付宝大卡片置顶；面额两列大按钮（对齐 VoiceFix）；下方为金额输入与充值按钮（mgr / vf / cert 一致）。
- **支付宝 APPID**：现网切至网页应用 `2021007108665442`（`秘钥web支付/`）；旧 `2021002191622113` 备份见配置信息 `web用用备份.md`。
- 新建 hipp-manager：统一身份（短信/密码/资料/改密）与共享钱包（余额/充值/流水/账单/S2S）。
- 账户控制台挂载 `/mgr/`。
- hipp-https 登录改走 `HIPP_MANAGER_BASE`，新增个人中心代理页。
- 增加充值订单列表、短信重置密码；VoiceFix/or 强制切身份与钱包；VoiceFix 下线会员。
- 生产短信依赖 `aliyun-python-sdk-core`；会话 Redis 白名单 + `/api/auth/logout`；同站 or/cert/mgr 用 `hipp.sso.logout_at` 联动退出。
- 生产库改 MySQL `hipp_manager`；`import_legacy` 从 or/`voicefix` 按手机号合并用户与余额。
- 同站登录态互通：共享 `hipp_manager_token`；cert/or 登录回写 manager 令牌并支持 SSO 换票，与 `/mgr/` 免重复登录。
