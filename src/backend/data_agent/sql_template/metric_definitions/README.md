# metric_definitions

指标定义目录，保存收入、成本、留存、ROI 等指标的统一口径。

## 文件树

```text
metric_definitions/
├── revenue.json
├── spend.json
├── roi_d7.json
├── retention_d30.json
└── ...
```

## 设计说明

- 每个 JSON 表示一个指标口径。
- 指标口径变化应先更新这里，再由注册表导入服务同步。
