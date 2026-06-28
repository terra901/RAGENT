# seeders

演示数据生成器目录，为 RAGENT MySQL 业务表生成稳定的模拟数据。

## 文件树

```text
seeders/
├── __init__.py       # 包标记
├── common.py         # 公共随机数、日期和行构造工具
└── generators.py     # 各业务表数据生成函数
```

## 设计说明

- 每个生成函数对应一张业务表。
- 公共随机逻辑集中在 `common.py`，避免入口脚本膨胀。
