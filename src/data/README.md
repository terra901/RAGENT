# data

项目级数据占位目录，保留给导入导出文件、临时样例或跨前后端共享的数据说明。

## 文件树

```text
data/
└── README.md    # 目录用途说明
```

## 设计说明

- 业务运行数据优先放到 MySQL、Redis 或 `src/backend/data/`。
- 大文件和用户导出结果不提交到 Git。
