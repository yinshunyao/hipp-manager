# hipp-manager

跨产品**统一身份与共享钱包**平台：登录、资料、改密、余额、充值、流水、账单、运营台、公共媒体。

产品码 `mgr`；用户端路径 `/mgr/`，平台运营台 `/mgr/manager/`。业务产品（`or` / `vf` / `cert`）通过 HTTP 用户 API 或 S2S 接入，不再各自维护第二套资金账本。

## 能力概览

| 域 | 做什么 |
|:---|:---|
| 身份 | 短信/密码登录、资料、改密、重置密码；同站会话互通 |
| 钱包 | 余额、充值面额、微信/支付宝/开发入账、流水、月账单 |
| 运营台 | 用户列表/拉黑/改密、流水与充值单、手工入账/扣款 |
| 媒体 | 公共上传/访问/删除；S2S 删除与孤儿 GC |
| S2S | 余额查询、扣款、入账（须 `product` + `biz_type`） |

## 仓库结构

```text
hipp-manager/
├── readme.md              # 本文件（入口）
├── requirements.txt       # 后端依赖
├── .env.sample            # 环境变量模板
├── server/
│   ├── manager/           # FastAPI 应用（身份/钱包/运营/支付）
│   └── media/             # 公共媒体 API 与落盘
├── web/                   # React 账户控制台 + 运营台（Vite）
├── data/                  # 本地 SQLite / 媒体目录（勿提交密钥）
└── doc/
    ├── 01-or/             # 原始需求
    ├── 02-dr/             # 开发设计
    ├── 03-tr/             # 测试设计
    ├── 99-ops/            # 运行与发布
    └── dev/               # 开发手册（本地联调、目录、接口索引）
```

## 快速开始

**前置**：Python **3.12**（建议）、Node.js 18+。本地默认可不启 Redis（`SMS_MOCK=1`）、不配真实支付（`RECHARGE_DEV_AUTO=1`）。

```bash
# 后端
cd hipp-manager
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp -n .env.sample .env
PYTHONPATH=server python -m manager
# → http://127.0.0.1:9100/health
# → 已构建前端时：http://127.0.0.1:9100/mgr/

# 前端开发（另开终端；Vite 代理 /api → 9100）
cd hipp-manager/web
npm install
npm run dev
# → http://127.0.0.1:5175/mgr/
```

生产前端：`cd web && npm run build`，后端挂载 `web/dist` 到 `/mgr/`。

更细的环境变量、管理员 CLI、支付回调、业务系统接入见：

- **开发手册**：[`doc/dev/`](doc/dev/)（入口 [`doc/dev/readme.md`](doc/dev/readme.md)）
- **运行说明**：[`doc/99-ops/run.md`](doc/99-ops/run.md)

## 路径与端口

| 用途 | 地址 |
|:---|:---|
| 后端默认 | `0.0.0.0:9100` |
| 健康检查 | `GET /health` |
| 用户控制台 | `/mgr/`（资料 / 钱包 / 流水 / 账单） |
| 运营台 | `/mgr/manager/` |
| 前端 dev | `5175`，`base=/mgr/` |
| 媒体静态 | `GET /media/...` |

短信 mock：`SMS_MOCK=1` 时验证码固定 `123456`。

## 文档索引

| 类型 | 路径 |
|:---|:---|
| 开发手册 | `doc/dev/`（见 `doc/dev/readme.md`） |
| 需求 | `doc/01-or/` |
| 设计 | `doc/02-dr/`（身份 / 钱包 / 运营 / 媒体） |
| 测试设计 | `doc/03-tr/` |
| 运行与发布 | `doc/99-ops/` |

产品码与资金 `biz_type` 约定与 workspace 规则 `rules-hipp-product-codes` 一致，代码真源见 `server/manager/products.py`。
