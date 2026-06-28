合理，但要加一个边界：

**MySQL 负责模块元数据、状态、版本、入口信息；Python 代码仍然必须部署在本地代码仓库或插件目录中。**

也就是说，编译图时确实可以：

```text
读取 graph
-> 根据 node.module_key / module_version_id 去 MySQL 查模块
-> 判断模块是否 active
-> 拿到 entrypoint
-> 本地 import 这个模块
-> 校验接口
-> 编译到 LangGraph
-> 执行
```

但 MySQL 里不要存“任意本地文件路径然后直接执行”。推荐存：

```text
entrypoint = Modules.competitor_analysis.CompetitorAnalyzer
```

而不是：

```text
/home/chenjy/桌面/Discord-bot/src/Modules/xxx.py
```

这样更安全、可迁移、可测试。

**一、推荐总体架构**

目标链路应该是：

```text
模块代码
  -> 模块 manifest / 注册信息
    -> 注册到 MySQL
      -> 平台管理上线/下线/版本
        -> pipeline 图引用 module_version_id
          -> 编译图时从 MySQL 解析模块
            -> 本地 import entrypoint
              -> 执行并记录调用
```

当前项目是硬编码：

```text
PIPELINE_NODE_TYPES
NODE_RUNNERS
```

未来应该演进为：

```text
MySQL module_versions
  -> 动态生成 NodeTypeSpec
  -> 动态绑定 runner
```

---

**二、MySQL 应该存什么**

核心表建议如下。

**1. module_definitions**

表示模块本身。

```text
id
module_key              唯一标识，例如 sentiment_classify
name                    展示名
category                data / llm / analysis / output / custom
description
owner
created_at
updated_at
```

一个 `module_key` 对应多个版本。

**2. module_versions**

表示模块某个版本。

```text
id
module_id
version                 例如 1.0.0
entrypoint              例如 Modules.xxx.YourModule
adapter_type            class / function / runner
input_schema_json
output_schema_json
config_schema_json
default_config_json
status                  draft/testing/active/deprecated/disabled/archived
runtime_version         兼容的运行时版本
code_checksum           可选，用于校验代码版本
release_note
created_by
created_at
published_at
disabled_at
```

**3. module_release_logs**

记录上线、下线、回滚。

```text
id
module_version_id
action                  publish / deprecate / disable / rollback
from_status
to_status
operator_id
reason
created_at
```

**4. pipeline_versions**

保存 pipeline 图版本。

```text
id
pipeline_id
version
graph_json
status
created_by
created_at
```

注意：`graph_json` 里要保存明确的 `module_version_id`。

**5. module_invocations**

记录每次模块调用。

```text
id
run_id
node_id
project_id
module_key
module_version_id
status
started_at
finished_at
duration_ms
input_rows
output_rows
error_type
error_message
artifacts_json
metrics_json
```

---

**三、模块状态设计**

建议状态如下：

```text
draft：已注册，未发布，不可被普通 pipeline 使用
testing：测试可用，只允许测试项目或管理员使用
active：正式可用
deprecated：不推荐新建使用，但历史 pipeline 可继续跑
disabled：禁止新任务使用
archived：归档，仅保留历史记录
```

执行策略建议：

```text
active：新建 pipeline 和运行都允许
testing：仅测试环境/管理员允许
deprecated：旧 pipeline 可运行，新建时警告或禁止选择
disabled：新运行禁止，历史记录可查看
archived：不可运行，只能审计
```

---

**四、Pipeline 图应该怎么引用模块**

不建议只写：

```json
{
  "type": "sentiment_classify"
}
```

因为这无法锁定版本。

推荐写：

```json
{
  "id": "sentiment",
  "module_key": "sentiment_classify",
  "module_version_id": 12,
  "config": {
    "model": "v4_flash",
    "batch_size": 50
  }
}
```

或者兼容当前结构：

```json
{
  "id": "sentiment",
  "type": "sentiment_classify",
  "module_version_id": 12,
  "config": {}
}
```

关键是：**pipeline 版本必须固定 module_version_id。**

否则模块升级后，旧报告无法复现。

---

**五、编译图时的完整流程**

未来 `compile_reactflow_graph` 应该变成：

```text
1. 读取 graph_json
2. 遍历 nodes
3. 对每个 node 读取 module_version_id
4. 查询 MySQL module_versions
5. 检查 status 是否允许编译
6. 读取 config_schema_json
7. 校验 node.config
8. 读取 input_schema / output_schema
9. 校验边和输入输出兼容性
10. 根据 entrypoint 本地 import 模块
11. 校验模块是否实现标准接口
12. 包装成 LangGraph node
13. 编译执行图
```

现在项目里是：

```text
node.type -> NODE_RUNNERS[node.type]
```

未来变成：

```text
node.module_version_id
  -> MySQL module_versions.entrypoint
  -> ModuleLoader.load(entrypoint)
  -> runner
```

---

**六、模块接口规范**

建议所有新模块统一实现：

```text
execute(context, inputs, config) -> ModuleResult
```

概念上：

```text
context：运行上下文
inputs：上游输入
config：节点配置
ModuleResult：输出结果
```

**context 包含：**

```text
run_id
node_id
project_id
workspace_id
db
logger
artifact_store
llm_provider
secrets
runtime_config
```

**inputs 包含：**

```text
上游模块输出
当前 PipelineState 中可用的数据
```

**config 来自：**

```text
node.config + default_config + 项目配置
```

**ModuleResult 包含：**

```text
outputs
artifacts
metrics
logs
status
```

当前项目可以先兼容：

```text
run_xxx(state: PipelineState) -> PipelineState
```

但长期建议收敛到 `execute(...)`。

---

**七、模块上线流程**

标准流程建议：

```text
1. 开发模块代码
2. 编写模块 manifest
3. 本地测试模块接口
4. 注册到 MySQL，状态 draft
5. 平台执行 import 校验
6. 平台执行 schema 校验
7. 平台执行测试调用
8. 状态改为 testing
9. 测试 pipeline 跑通
10. 状态改为 active
11. 前端节点面板展示
```

模块 manifest 可以包含：

```text
module_key
version
name
category
entrypoint
input_schema
output_schema
config_schema
default_config
side_effects
```

注册动作就是：

```text
读取 manifest
-> 校验 entrypoint 可 import
-> 校验接口存在
-> 写入 module_definitions / module_versions
```

---

**八、模块下线流程**

下线不等于删除代码。

推荐流程：

```text
1. module_versions.status 改为 deprecated
2. 新建 pipeline 不再默认展示
3. 历史 pipeline 仍可运行
4. 观察一段时间
5. 如果确认不用，改为 disabled
6. disabled 后禁止新任务执行
7. 保留历史调用记录和历史 pipeline
```

如果是紧急下线：

```text
active -> disabled
```

编译时直接阻止：

```text
模块 xxx@1.2.0 已禁用，无法执行
```

---

**九、版本更迭流程**

新版本不要覆盖旧版本。

例如：

```text
sentiment_classify@1.0.0 active
sentiment_classify@1.1.0 testing
sentiment_classify@1.1.0 active
sentiment_classify@1.0.0 deprecated
```

已有 pipeline 继续引用：

```text
module_version_id = 1.0.0
```

新建 pipeline 默认使用：

```text
module_version_id = 1.1.0
```

如果新版本有问题：

```text
1. 把 1.1.0 改 disabled
2. 默认版本切回 1.0.0
3. 已经运行失败的任务通过 module_invocations 定位
```

---

**十、前端如何展示**

前端节点面板不应该再直接读硬编码 `PIPELINE_NODE_TYPES`。

应该调用：

```text
GET /api/modules?status=active
```

返回：

```json
[
  {
    "module_key": "sentiment_classify",
    "version": "1.1.0",
    "module_version_id": 12,
    "name": "情绪分类",
    "category": "llm",
    "config_schema": {},
    "default_config": {}
  }
]
```

用户拖到图里时，节点保存：

```text
module_version_id
module_key
config
```

---

**十一、运行时统计**

执行每个模块前写：

```text
module_invocations.status = running
started_at = now
```

执行成功后更新：

```text
status = success
finished_at
duration_ms
metrics_json
artifacts_json
```

执行失败后更新：

```text
status = failed
error_type
error_message
```

这样你可以统计：

```text
模块调用次数
成功率
失败率
平均耗时
哪个版本问题最多
哪个项目调用最多
```

---

**十二、我建议的落地顺序**

不要一次性把所有硬编码都改成动态加载。建议分阶段。

**阶段 1：MySQL 只管理元数据**

保留当前：

```text
PIPELINE_NODE_TYPES
NODE_RUNNERS
```

新增 MySQL 表：

```text
module_definitions
module_versions
module_release_logs
```

把现有节点同步进去。

目的：先有管理后台数据。

**阶段 2：编译前检查 MySQL 状态**

仍然用本地 `NODE_RUNNERS` 执行，但编译前查 MySQL：

```text
这个 node_type 是否存在
版本是否 active
是否 disabled
```

目的：先实现上线/下线控制。

**阶段 3：增加调用统计**

新增：

```text
module_invocations
```

在每个 node 执行前后记录调用。

目的：实现“被调用多少次”。

**阶段 4：图引用 module_version_id**

修改 graph 保存结构：

```text
node.module_version_id
```

目的：支持版本锁定和可复现。

**阶段 5：动态加载 entrypoint**

把执行逻辑从：

```text
NODE_RUNNERS[node.type]
```

升级为：

```text
module_versions.entrypoint -> import -> execute
```

目的：真正实现“注册到 MySQL 后可被编译图发现”。

---

**十三、结论**

你的方案是合理的，但建议严格定义边界：

```text
MySQL 管模块定义、版本、状态、配置 schema、entrypoint
本地代码仓库放真实模块代码
编译图时从 MySQL 解析 module_version_id
执行前校验状态和接口
执行后写 module_invocations
```

不要让 MySQL 直接变成“代码仓库”。  
正确模式是：**代码部署 + MySQL 注册 + 编译时解析 + 运行时统计**。