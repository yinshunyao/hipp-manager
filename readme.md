# hipp-manager

跨产品统一身份与共享钱包：登录、资料、改密、余额、充值、流水、账单。

- 需求与设计：`doc/`
- 运行：`doc/99-ops/run.md`
- 后端（建议 Python 3.12）：
  ```bash
  cd hipp-manager
  python3.12 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  PYTHONPATH=server python -m manager
  ```
- 前端：`web/`（生产路径 `/mgr/`，`npm run build`）
