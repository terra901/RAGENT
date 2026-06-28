# sql_templates

SQL 模板目录，保存可复用的参数化查询模板。

## 文件树

```text
sql_templates/
├── buy_channel_roi_by_ad_dimension.json
├── cohort_user_dayn_analysis.json
├── material_effect_rank.json
└── ...
```

## 设计说明

- 模板只描述查询结构和参数，不保存用户私密数据。
- 控制器通过 `SqlTemplateStore` 暴露查询、导入、导出能力。
