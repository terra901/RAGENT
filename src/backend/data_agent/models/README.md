# models

MVC 架构中的 Model/Schema 层，保存 HTTP 请求和响应的结构定义。这里不连接数据库，数据库表结构放在 `storage/` 和领域仓储中。

## 文件树

```text
models/
├── __init__.py      # 包标记
└── schemas.py       # Pydantic 请求/响应模型
```

## 设计说明

- 控制器使用这里的 Pydantic 模型约束输入。
- 数据库行到公开响应的转换在对应仓储或控制器辅助函数完成。
- 后续新增 API 时先补 schema，再接控制器。
