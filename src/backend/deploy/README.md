# deploy

部署配置目录，保存本地或外部服务的部署辅助文件。

## 文件树

```text
deploy/
└── langfuse/    # Langfuse 观测服务部署参考
```

## 设计说明

- RAGENT 自身容器依赖在项目根目录 `docker-compose.yml`。
- 这里保留可选外部组件的部署资料。
