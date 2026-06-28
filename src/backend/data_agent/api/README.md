# api

FastAPI 应用装配层。这里负责创建 app、初始化数据库/缓存/记忆/trace/队列依赖，并聚合 `controllers/` 中的 MVC 控制器。

## 文件树

```text
api/
├── __init__.py     # 包标记
├── bootstrap.py    # 应用依赖装配和释放
├── main.py         # FastAPI app 创建、CORS、静态前端挂载
└── routes.py       # 控制器路由聚合，兼容旧导入路径
```

## 与 agent 的关系

`bootstrap.py` 调用 `build_runtime(RuntimeDependencies(...))` 得到 runtime，然后挂到 `app.state.runtime`。控制器通过依赖注入读取 runtime、auth store、model repo、job store 和 trace store。
