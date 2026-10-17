# CLI 与数据工具

在工程根、已激活 venv、`PYTHONPATH=server`：

```bash
# 新建运营管理员（初始密码 123456，登录后运营台改密）
python -m manager.ops_admin create --username <name_or_phone>

# 重置运营管理员密码为 123456
python -m manager.ops_admin reset-password --username <name_or_phone>

# 存量用户导入（MySQL 已建库；从同实例 hipp + voicefix 按手机号合并）
python -m manager.import_legacy
```

实现：`server/manager/ops_admin.py`、`server/manager/import_legacy.py`。
