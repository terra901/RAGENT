# mvc

MVC 架构说明目录，用于固定后端边界约定，不放运行代码。

## 文件树

```text
mvc/
└── README.md    # MVC 分层说明
```

## 分层约定

- `controllers/`: HTTP Controller，只处理协议、鉴权和响应。
- `models/`: Pydantic Schema 和公开数据结构。
- `services/`: 业务服务与运行时协议。
- `storage/`、`admin/`、`runtime/`: 可替换基础设施和领域仓储。
- `frontend/`: View 层，由 Vue ESM 组件组成。
