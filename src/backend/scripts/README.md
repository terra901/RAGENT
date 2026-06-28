# scripts

后端辅助脚本目录，主要用于本地初始化、演示数据和部署检查。

## 文件树

```text
scripts/
├── seed_ragent_mysql_demo.py  # RAGENT MySQL 演示数据初始化入口
└── seeders/                   # 演示数据生成器
```

## 设计说明

- 脚本默认读取 `src/backend/.env`。
- 大体量生成逻辑拆到 `seeders/`，入口脚本保持短小。
