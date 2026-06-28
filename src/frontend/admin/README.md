# admin

前端后台管理页面目录，挂在主界面左侧“后台管理”入口下，视觉风格与聊天主页面保持一致。

## 文件树

```text
admin/
├── AdminPanel.js        # 后台管理容器和标签切换
├── ModelManagement.js   # 模型供应商、模型和密钥管理
└── TraceAdmin.js        # Agent trace 可观测页面
```

## 设计说明

- 只有管理员用户会看到后台入口。
- 页面使用主站同一套 CSS 变量和线框表格风格。
