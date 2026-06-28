# admin

后台管理领域模块，负责模型供应商、模型密钥和后台配置的领域逻辑。控制器只调用这里的仓储和校验器，不直接拼 SQL 或处理密钥细节。

## 文件树

```text
admin/
├── __init__.py                # 包标记
├── model_connectivity.py      # OpenAI 兼容接口连通性测试
├── model_crypto.py            # 模型 API Key 加密与掩码
├── model_payloads.py          # 后台模型表单载荷清洗
└── model_repository.py        # MySQL 模型管理仓储
```

## 设计说明

- 密钥加密密钥来自 `DA_MODEL_KEY_SECRET`，前端永远只看到掩码。
- 仓储独立于 FastAPI，可被脚本、Celery 任务或后续插件复用。
- 新后台模块优先放在这里或独立子包，再由 `controllers/` 暴露 API。
