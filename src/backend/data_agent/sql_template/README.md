# sql_template

SQL 模板注册表目录，保存可审计、可复用的指标、维度和模板定义。

## 文件树

```text
sql_template/
├── dimension_definitions/          # 维度定义 JSON
├── metric_definitions/             # 指标定义 JSON
├── sql_templates/                  # SQL 模板 JSON
└── ragent_sql_template_registry.json
```

## 设计说明

- JSON 文件是模板源数据，启动时由 `SqlTemplateStore` 导入 MySQL。
- 模板变更应优先通过后台或注册表文件完成，避免写死到代码。
