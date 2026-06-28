# DataAgent 节点编排机制改造思路

本文面向 `/home/chenjy/桌面/RAGENTv2` 的文字问数 DataAgent，不包含语音链路。参考对象是 `/home/chenjy/桌面/agent-master` 中的节点编排、规则路由、语义中转、反悔回撤、跳答补偿和打断恢复机制。

## 1. agent-master 微观实现拆解

`agent-master` 的核心不是“多个 Agent 顺序执行”，而是一个可回放的状态机。`graph/runtime.py` 的 `AgentGraphRunner` 保存运行时状态：`current` 当前节点、`visited/transitions` 访问路径、`pending_enter` 是否刚进入节点、`task_done` 已完成节点、`prompt_allowed_nexts` 当前提示词允许跳转目标、`cross_edge_sources/reverse_source_stack` 反悔来源链、`reverse_pending_nodes/reverse_completed_nodes` 多节点反悔队列、`interrupted_handoff_queue/pending_jump_chain` 打断续跳队列。也就是说，模型只负责产出内容和控制标签，真正决定能不能跳、跳到哪里、历史怎么恢复的是 runner。

### 1.1 节点配置如何变成可执行图

`graph/builder.py` 先把 `Agent.next_nodes` 构造成 `AgentGraph(adjacency=...)`，校验空图、重名节点、未知引用、孤立节点和非连通图。随后 `AgentGraphRunner.from_roots()` 为每个非 router 节点动态拼接跳转规则：

```text
原始节点 system_prompt
  + 当前节点描述
  + 允许的下游节点
  + 每条边的跳转条件 / 目标节点描述
  + <node_jump>/<node_reverse>/<analyse> 输出格式规则
```

关键点在 `runtime.py` 约 1128-1184 行：`jump_instruction_nexts` 会先过滤“可出现在提示词里的下游”，并写入 `prompt_allowed_nexts`。后续 runtime 还会用同一个 `prompt_allowed_nexts` 做运行时拦截，避免模型跳到提示词里没有暴露的节点。

### 1.2 普通业务节点如何执行与跳转

普通节点的主流程在 `graph/runtime_ops.py::step()`：

1. 如果 `pending_enter=True`，先向 `Conversation` 追加一条系统化 user 消息，内容类似 `[节点进入]用户进入「X」节点...`。这条消息告诉模型当前节点任务、允许目标、最近来源节点、已完成下游、反悔队列进度等。
2. 调用当前 `Agent.run()` 得到 LLM 输出。
3. 用 `_extract_runtime_control_tags()` 拆出可见文本、`<node_jump>NODE</node_jump>`、`<node_reverse>NODE</node_reverse>` 和 `<analyse>...</analyse>`。
4. 可见文本写入 conversation；控制标签不展示给用户，只进入状态机。
5. 如果命中 `node_reverse`，走反悔回撤；如果命中合法 `node_jump`，走正常下游；如果没有标签，尝试缺失跳转补偿；如果目标非法或被屏蔽，则留在当前节点。

这种设计的要点是“自然语言输出”和“流程控制”共用一次模型调用，但通过标签把控制面从展示面分离。RAGENTv2 现在的 LangGraph 是固定流水线，`src/backend/data_agent/agent/graph.py` 中只有 `execute_sql` 失败后回到 `generate_sql` 的条件边；它缺少这种“节点输出携带可校验控制意图”的层。

### 1.3 规则节点 router 如何实现

router 节点不调用 LLM。`_step_router()` 根据 `prefill_items` 构造 `prefill_value_map`，再用 `evaluate_jump_rules()` 对每条出边规则求值。规则支持：

- `exists`
- `not_exists`
- `eq`
- `ne`
- `in`

命中必须唯一。没有命中或多条命中都会抛 `GraphRunError`。测试 `scripts/test_router_node.py` 证明了三件事：规则必须确定、必须覆盖状态、支持多层 router 链路。这个机制适合 DataAgent 中“已经有结构化信号就不要问 LLM”的场景，例如：

- 查询类型是指标查询、明细查询、归因查询还是图表分析。
- SQL 执行失败类型是语法错误、权限错误、空结果、超时还是敏感列拒绝。
- 用户是否已经提供时间范围、业务实体、指标、维度、过滤条件。

### 1.4 语义中转 semantic_relay 如何实现

semantic relay 是一个只做分流的 LLM 节点。它的提示词要求模型只输出 `<node_jump>目标</node_jump>`，可选先输出 `<analyse>原因</analyse>`。`_step_semantic_relay()` 会：

- clone 当前 conversation，临时追加节点进入消息；
- 调用 relay agent；
- 提取 `jump/reason`；
- 若输出是问句，拦截，不跳；
- 若目标不存在或不在 `allowed_nexts`，随机 fallback 到允许目标；
- 成功后写一条空的 `router_transition` turn，作为可回放的内部转移记录。

它解决的是规则覆盖不了的“语义判断”。在 DataAgent 里，可以用 semantic relay 判断用户意图，例如“用户是在追问上一轮结果、要求改 SQL、要求解释图表、还是开启新查询”。

`semantic_relay_parallel.py` 还做了一个优化：当多个 semantic relay/router 可穿透时，后台提前跑候选 relay，真正到达该节点时如果 context token 没变，就直接消费已完成结果。这对文字问数也有价值，尤其是前端流式回答时可以提前准备“下一步意图判定”或“下一个 SQL 修正判断”。

### 1.5 反悔回撤如何实现

反悔不是简单地把 `current` 改回旧节点。`agent-master` 做了三层状态维护：

1. `node_reverse` 触发：模型输出 `<node_reverse>目标节点</node_reverse>`，runtime 优先处理反悔，不再按当前节点任务继续。
2. 来源链记录：`_record_reverse_sources(src, dst)` 把“从哪个节点反悔过来”记录到 `reverse_source_stack` 和 `cross_edge_sources[dst]`。
3. 提示词重建：`_rebuild_agent_for_reverse(target, source)` 会把目标节点原始下游 + 来源节点一起注入到允许跳转目标，目标节点修正完成后可以跳回原链路。

多节点反悔靠队列实现。模型可以连续输出多个 `<node_reverse>A</node_reverse><node_reverse>B</node_reverse>`，runner 将它们写入 `reverse_pending_nodes`，完成一个节点后移到 `reverse_completed_nodes`，并只在 `reverse_queue_owner` 节点展示队列进度提示。这样用户一次说“时间和地区都改一下”时，系统不会丢掉第二个修改点。

迁移到 DataAgent 后，反悔可以理解为“用户修正历史查询约束或分析口径”，例如：

- “不是上周，是上个月。”
- “刚才那个渠道不对，改成 TikTok。”
- “不要 GMV，看 ROI。”
- “图表不用按天，按渠道分组。”

这些都不应粗暴开启新会话，而应回到对应槽位或阶段重新生成后续结果。

### 1.6 跳答、抢答、跨节点补充如何避免流程错乱

`agent-master` 解决跳答的核心是“节点职责 + 可跨节点收集 + 运行时屏蔽”：

- 节点进入提示要求当前节点只处理自己负责字段。
- 如果用户表达中包含其他节点信息，可以简要复述但不展开，由后续节点处理。
- 通过预填抽取和 `prefill_items`，后续节点进入时能看到已经提前提供的信息，避免重复询问。
- `edge_is_relevance=False` 且目标节点已在 `task_done` 中时，`_rebuild_agent_for_normal()` 会从提示词里屏蔽该分支。
- 动态独立边/节点走过后也会被屏蔽，避免同一独立补充分支重复进入。

在 DataAgent 中，对应机制是“槽位预填 + 查询计划字段级完成状态”。用户一次说“查上个月北京渠道 ROI，按天画图”，系统应该在入口阶段同时填充：

```json
{
  "metric": "ROI",
  "time_range": "上个月",
  "filters": {"city": "北京"},
  "dimensions": ["day"],
  "output": "chart"
}
```

然后后续 `clarify_metric/clarify_time/clarify_dimension/chart_decision` 节点看到槽位已完成，就直接跳过或进入下一阶段。

### 1.7 缺失跳转补偿如何实现

模型有时已经回答完了，但忘了输出 `<node_jump>`。`_resolve_missing_normal_jump_via_compensation()` 会在以下条件下触发：

- 当前不是 router/semantic relay；
- 输出非空；
- 不是终点节点；
- 输出不像问句；
- 输出像完整陈述，或者开启了 `stay` 判断；
- 有可用下游目标。

补偿有两种策略：

1. continue write：把 assistant 前缀拼成 `原输出<node_jump>`，让模型续写目标节点。
2. judge model：用一个专门的 jump compensation prompt，让模型只判断是否应跳转。

这对 DataAgent 很实用。比如 `interpret_result` 已经输出“已按渠道汇总如下...”，但忘了标记是否需要 `generate_chart`；补偿器可以基于结果形态和用户意图决定跳到 `generate_chart` 或 `persist_memory`。

### 1.8 打断恢复在文字场景中的等价物

语音打断可迁移为文字场景的“用户在上一次回答未完成或刚完成时追加/改口”。`agent-master` 的打断恢复关键字段是：

- `pending_jump_chain`：上一轮已经真实发生但还没被下一次请求消费的跳转链。
- `interrupted_handoff_queue`：打断后需要按原跳转顺序续走的队列，形如 `{node, expected_next, prompt_pending}`。
- `pending_interrupted_last_assistant_seen`：用户已看到的上一段 assistant 文本。
- `Conversation` 的 projection：把用户已看到/未看到的 assistant 片段投影成提示，避免模型重复说用户已经看过的内容。

文字 DataAgent 不需要处理 ASR/TTS，但需要处理：

- 用户在流式 SQL/答案还没结束时发送新问题。
- 用户看到一半回答后说“停，换成按周”。
- 用户在系统已经生成 SQL 但未执行或刚执行时补充条件。

等价方案是保留“可见历史锚点”和“未完成状态快照”：如果前一轮仍在 running，下一轮请求带上 `interrupt_of_thread_id` 或由服务端自动检测同 session active thread，runtime 应将前一轮状态标记为 interrupted，把已输出文本作为 visible prefix，把未完成节点和已发生跳转链写入 session runtime state。

## 2. RAGENTv2 当前结构差距

RAGENTv2 当前后端已经有良好的模块边界：

- `GraphQueryRuntime` 负责请求入口和 SSE 聚合。
- `AgentState` 保存一次请求内状态。
- `RunContext` 注入数据库、LLM、memory、queue、Langfuse。
- `graph.py` 用 LangGraph 定义固定流程。
- `SessionStore/MemoryProvider` 保存问答历史。

但它目前缺少以下能力：

- 没有可持久化的节点运行态，`supports_resume=False`。
- 历史只保存 `question/answer`，没有每轮的 `node_before/node_after/jump_kind/slots/plan/sql/result`。
- 节点之间主要靠固定边和 `retry` 布尔值，没有通用 `router/semantic_relay`。
- 用户改口时只能依赖 memory prompt，不能精确回滚到“时间槽位”“指标槽位”“SQL 生成后”等阶段。
- 流式中途的新输入没有清晰的取消、续跑、可见历史对齐机制。

## 3. DataAgent 应如何应用这些机制

建议不要照搬语音客服节点，而是抽象为“文字问数任务图”。推荐节点类型：

### 3.1 业务节点 task node

业务节点负责一个可验证产物，而不是负责一句话术。

```text
intent_classify        判断新查询 / 追问 / 修改 / 解释 / 图表
extract_slots          提取指标、维度、时间、过滤条件、排序、limit、输出形式
clarify_slots          缺关键槽位时澄清
recall_schema          召回表结构
build_query_plan       生成结构化查询计划
generate_sql           生成 SQL
validate_sql           安全校验
execute_sql            执行 SQL
repair_sql             根据错误修复 SQL
interpret_result       解读结果
generate_chart         生成图表
persist_turn           保存历史与节点状态
```

每个节点输出统一结构：

```json
{
  "visible_text": "给用户看的文字，可为空",
  "control": {
    "jump": "next_node | stay | null",
    "reverse": ["node_a", "node_b"],
    "reason": "内部原因",
    "status": "done | need_user | failed"
  },
  "patch": {
    "slots": {},
    "plan": {},
    "sql": "",
    "result_ref": ""
  }
}
```

LLM 节点可以继续用标签，也可以要求 JSON。对 DataAgent 来说更推荐 JSON，因为节点输出本来就是结构化数据。但原则相同：展示内容和控制内容必须分离，并且控制内容必须被 runtime 校验。

### 3.2 规则节点 router

规则节点只读 `slots/plan/error/result_shape`，不调用 LLM。可引入：

```python
class JumpRule(TypedDict):
    key: str
    operator: Literal["exists", "not_exists", "eq", "ne", "in"]
    value: str | None
```

DataAgent 的典型 router：

- `route_after_intent`：新查询 -> `extract_slots`，追问 -> `answer_followup`，修改 -> `reverse_router`。
- `route_after_slots`：关键槽位齐全 -> `recall_schema`，缺槽位 -> `clarify_slots`。
- `route_after_execute`：成功 -> `interpret_result`，语法错误 -> `repair_sql`，空结果 -> `empty_result_decision`，敏感列 -> `refuse_sensitive`。
- `route_after_interpret`：用户要图 -> `generate_chart`，否则 -> `persist_turn`。

规则节点必须满足“唯一命中”。构建时校验覆盖性，运行时遇到多值 key 要失败或进入澄清，不要默默随机选。

### 3.3 语义中转节点 semantic relay

规则节点无法判断的地方再用 LLM relay。DataAgent 中最有价值的 relay：

- `semantic_intent_relay`：判断用户新输入与上一轮的关系。
- `semantic_revision_relay`：判断用户修改的是哪个历史槽位或节点。
- `semantic_result_relay`：判断用户是在要解释、要图表、要导出、要继续筛选，还是要新查询。

relay 输出必须小而硬：

```json
{
  "target": "modify_time_range",
  "reason": "用户把时间从上周改为上个月",
  "confidence": 0.86
}
```

runtime 只接受 `target in allowed_nexts`，否则进入兜底澄清或规则 fallback。

### 3.4 反悔机制在 DataAgent 中的设计

把每次成功问数保存为一个可回滚的 `TaskSnapshot`：

```json
{
  "turn_id": "...",
  "slots": {
    "metric": "ROI",
    "time_range": "上个月",
    "dimensions": ["day"],
    "filters": {"channel": "Facebook"}
  },
  "plan": {},
  "sql": "...",
  "result_ref": "cache_key",
  "chart_spec_ref": "...",
  "node_status": {
    "extract_slots": "done",
    "generate_sql": "done",
    "execute_sql": "done"
  },
  "transitions": [
    ["extract_slots", "recall_schema"],
    ["recall_schema", "generate_sql"]
  ]
}
```

用户说“不是 Facebook，是 TikTok”时：

1. `semantic_revision_relay` 判断修改目标是 `filters.channel`。
2. runtime 找到该字段的 owner node，例如 `extract_slots` 或 `build_query_plan`。
3. 写入 `reverse_pending_nodes=["extract_slots"]`，保存 `source_node=current`。
4. 回到 `extract_slots`，只更新 channel，不重问 metric/time/dimensions。
5. 从受影响节点开始重跑：`build_query_plan -> generate_sql -> validate_sql -> execute_sql -> interpret_result -> chart`。
6. 如果用户一次修改多个字段，则按队列顺序处理。

关键不是“回到旧代码节点”，而是“找到被修改字段的最早影响点，然后废弃它之后的派生产物”。例如时间、指标、维度变化会使 SQL/result/chart 全部失效；只要求“解释更详细”则不需要重跑 SQL。

### 3.5 跳答与跨节点补充

入口处必须先做 `extract_slots`，并把跨节点信息一次性收集到 `slots`。每个业务节点判断自己需要的字段是否已存在：

- 已存在且可信：直接 `jump` 下一节点。
- 缺失：`stay` 并提出一个明确问题。
- 存在但冲突：进入 `clarify_slots`。

示例：

```text
用户：查上个月北京渠道 ROI，按天画图
extract_slots: metric=ROI, time_range=上个月, city=北京, dimensions=[day], output=chart
route_after_slots: slots_complete -> recall_schema
generate_chart: output=chart -> 执行
```

这就是客服里的“用户提前回答后面的字段不重复问”，迁移到 DataAgent 后就是“用户提前给的查询条件不重复澄清”。

### 3.6 缺失跳转补偿

DataAgent 中建议实现一个轻量 `control_compensator`：

- 如果 LLM 节点返回了自然语言或 JSON patch，但没有 control；
- 且节点不是终点；
- 且 visible_text 不是澄清问题；
- 且 patch 中出现足以完成节点的字段；
- 则用规则优先判断下一节点，规则无法判断时用一个小 prompt 让 LLM 只输出 `jump/stay`。

例如：

```text
generate_sql 返回 sql 但没返回 jump
=> rule: sql exists -> validate_sql

interpret_result 返回 answer，用户要求图表且 result_shape 可画图
=> jump generate_chart
```

这个补偿比在 prompt 里反复强调“必须输出 next”更稳，因为它把错误收敛到 runtime。

### 3.7 文字打断 / 改口恢复

建议在 `GraphQueryRuntime` 增加 session 级 active run 管理：

```text
data-agent:run:active:{session_id} -> thread_id
data-agent:run:state:{thread_id}  -> current_node, state, visible_output, transitions
```

当同一 session 在上一个 thread 未完成时发来新问题：

1. 标记旧 thread interrupted。
2. 停止旧流式输出，保存已发送给前端的 `visible_output`。
3. 新请求读取旧 thread 的 `current_node/transitions/pending_jump_chain`。
4. 判断新输入是改口、补充还是新查询。
5. 如果是改口/补充，按反悔机制回滚；如果是新查询，关闭旧 thread，开新图。

文字场景不需要“用户听到了多少”，但需要“用户看到了多少”。SSE 层可以在每个 `answer_chunk/sql_chunk` 后累计 visible buffer，落到 runtime state。

## 4. 推荐落地模块

建议新增或改造以下模块：

```text
src/backend/data_agent/orchestration/types.py
  NodeSpec, EdgeSpec, JumpRule, RuntimeControl, TaskSnapshot, OrchestrationState

src/backend/data_agent/orchestration/rules.py
  evaluate_jump_rules(), build_prefill_value_map(), validate_router_rules()

src/backend/data_agent/orchestration/control.py
  parse_control_json_or_tags(), validate_target(), compensate_missing_control()

src/backend/data_agent/orchestration/session_state.py
  Redis / DB backed run state, active thread, interruption snapshot

src/backend/data_agent/orchestration/runner.py
  DataAgentGraphRunner, transition(), reverse(), rebuild_allowed_nexts()

src/backend/data_agent/agent/nodes/semantic_intent.py
  文字意图中转

src/backend/data_agent/agent/nodes/extract_slots.py
  统一槽位抽取与跨节点预填

src/backend/data_agent/agent/nodes/clarify_slots.py
  缺槽位澄清
```

短期可以不替换 LangGraph，而是在现有 `AgentState` 中增加：

```python
slots: dict[str, Any]
slot_sources: dict[str, str]
node_status: dict[str, str]
current_node: str
transitions: list[tuple[str, str]]
control: dict[str, Any]
reverse_pending_nodes: list[str]
reverse_completed_nodes: list[str]
interrupted: bool
visible_output: str
snapshot_id: str
```

然后把 `graph.py` 从固定边逐步改成“router 函数读 state 决策”。LangGraph 仍可保留，只是节点间条件边要丰富起来。

## 5. 渐进实施顺序

第一阶段：结构化槽位和快照。
新增 `extract_slots`，让每轮问题先转成 slots；`persist_memory` 不只保存 question/answer，还保存 slots/sql/result/chart 的 snapshot。这样先解决跳答和跨节点补充。

第二阶段：规则路由。
实现 `rules.py`，把 `route_after_execute` 从单一 `retry` 扩展为错误类型路由；把 `route_after_slots` 扩展为 slots complete / need clarify / revision。

第三阶段：语义中转。
新增 `semantic_intent_relay`，判断用户是新查询、追问、修改上一轮、要求图表或解释。relay 只输出结构化 target，不直接回答用户。

第四阶段：反悔回滚。
实现字段 owner 映射和影响范围：

```text
metric/time/filter/dimension -> invalidate plan/sql/result/chart/answer
chart_type/output            -> invalidate chart/answer tail
answer_style/explanation     -> invalidate answer only
```

第五阶段：文字打断。
增加 active thread 和 visible output buffer。同 session 并发请求时，旧 thread 标记 interrupted，新输入走 revision/new_query 判断。

第六阶段：缺失跳转补偿和并行预判。
对 LLM 节点加 control compensator；对高频 relay 加 speculative task，但必须用 context hash 防止消费过期结果。

## 6. 最重要的工程原则

1. LLM 只提出控制意图，runtime 必须校验目标是否合法。
2. 每次节点转移都要记录 `node_before/node_after/jump_kind/reason`，否则无法回滚和复盘。
3. 用户可见历史和模型输入历史要分层；内部标签、SQL 修复原因、路由原因不应直接展示。
4. 规则能解决的分流不要交给 LLM。
5. 改口不是新问题，应该从受影响的最早节点重新派生后续结果。
6. 槽位和派生产物要分开保存；slots 是用户事实，SQL/result/chart 是可失效重建的派生物。
7. 每个节点的完成条件必须可机器判断，不能只靠“模型觉得完成了”。

## 7. 一句话迁移总结

`agent-master` 的可迁移精髓是：把多轮对话做成“带元数据历史的可控状态机”，用规则节点处理确定性分支，用语义中转处理模糊意图，用反悔队列处理历史修改，用运行时补偿和可见历史投影处理模型漏标与中途改口。RAGENTv2 的 DataAgent 应把这些思想落到 `slots -> plan -> sql -> result -> answer/chart` 的文字问数链路上，而不是照搬客服话术节点。

## 8. 语音打断的代码级链路

语音打断在 `agent-master` 中不是一个单点功能，而是“流式输出中止 + 可见内容落盘 + 跳转链回滚/续接 + 下轮提示注入”的组合。文字版 RAGENT 不需要 ASR/TTS，但需要复用这套状态语义。

### 8.1 请求入口在哪里

主入口在：

```text
/home/chenjy/桌面/agent-master/server/router/deployments_stream.py
```

关键函数：

```text
invoke_deployment_stream()
```

它会读取请求参数：

```text
req.is_interrupted
dynamic_params["voice_session_token"]
dynamic_params["last_assistant_seen"]
req.dialog_history
req.drive_params
```

其中 `last_assistant_seen` 是语音前端告诉后端“用户实际听到的上一段 assistant 文本”。文字版 RAGENT 可以把它等价成 `last_assistant_seen` / `visible_output_seen`，来自 SSE 已发送给前端的 token buffer。

`deployments_stream.py` 会构造 `extra`，传给 runner：

```python
extra = {
    "abort_signal": session.interrupt_requested,
    "response_group_id": response_group_id,
    "is_interrupted": bool(server_is_interrupted_request and not interrupted_prompt_degraded),
    "missing_jump_compensation_enabled": True/False,
    ...
}
```

微观含义：

- `abort_signal` 是打断开关，runner 流式生成时会检查它。
- `response_group_id` 把本轮可能经过的多个内部节点转移归为同一组。
- `is_interrupted` 告诉 prompt 层本轮是打断承接请求。

### 8.2 流式输出中如何真正停止

真正停止在：

```text
/home/chenjy/桌面/agent-master/graph/runtime_ops.py
step_stream()
```

关键代码点在约 2355-2397 行：

```python
abort_signal = extra.get("abort_signal") if extra else None
interrupted_before_commit = bool(abort_signal is not None and abort_signal.is_set())
...
if abort_signal is not None and abort_signal.is_set():
    _drop_buffered_visible()
    extra["interrupted"] = True
    return Generation(text=cleaned_text, raw={**generation.raw, "interrupted": True})
```

这段非常关键：如果用户打断发生在流式输出过程中，runner 不会继续：

- 不写完整 assistant 到 `Conversation`；
- 不推进 `current`；
- 不执行后续 `node_jump`；
- 不把未说完内容暴露给用户；
- 只返回一个带 `interrupted=True` 的 Generation。

外层 `deployments_stream.py` 的 `_write(piece)` 会累积已发出的 token：

```python
accumulated.append(piece)
queue.put_nowait(_DeploymentStreamPacket(text=piece))
```

如果前端断连或语音侧设置打断，则：

```python
session.interrupt_requested.set()
```

文字版 RAGENT 应照搬这个原则：SSE 层维护 `visible_buffer`，如果用户新请求到来，设置旧 run 的 abort event；节点内部看到 abort 后不提交完整 answer/sql/chart，只由外层保存已发出的可见片段。

### 8.3 打断收尾如何保存“用户实际听到/看到”的内容

打断收尾在 `deployments_stream.py` 的 `_finish_interrupted()`，约 767-900 行。它做几件事：

1. 用 `_resolve_interrupted_visible_text()` 决定采用哪份可见文本：

```text
client_disconnected 且 full_answer_text 非空 -> 用前端实际收到的 streamed_text
否则 -> 用 runner accumulated candidate_text
```

2. 用 `_persist_interrupted_visible_assistant()` 写入 conversation：

```text
/home/chenjy/桌面/agent-master/server/router/deployments_interrupts.py
_persist_interrupted_visible_assistant()
```

这个函数只保存截断后的 assistant 文本，不保存模型完整输出。

3. 调 `_set_interrupted_snapshot()` 保存打断快照：

```text
visible_text
candidate_text
front_history_hash
response_group_id
rollback_judge_ctx
```

4. 调 `_mark_response_group_interrupted()` 给本轮 metadata 打标：

```python
{
  "interrupted_response": True,
  "interrupted_jump_chain": bool(has_jump_chain),
  "interrupted_jump_source_node": source_node
}
```

5. 调 `_upsert_visible_history_round()` 保存可见历史轮：

```text
assistant_content=resolved_visible_text
last_assistant_seen=resolved_visible_text
assistant_visible_confirmed=True
assistant_interrupted=True
restore_state=<可恢复状态>
```

这个 visible history 是打断恢复的核心。它让下一轮模型知道“用户看见/听见了什么”，同时保留可恢复的 runner state。

RAGENT 应新增类似字段：

```json
{
  "thread_id": "...",
  "response_group_id": "...",
  "visible_output": "前端已收到的回答片段",
  "full_candidate_output": "模型可能生成但未完全展示的内容，可选",
  "interrupted": true,
  "current_node": "interpret_result",
  "state_snapshot": {...}
}
```

### 8.4 为什么要有 response_group_id

一个用户请求可能不是只跑一个节点。例如普通节点输出 `<node_jump>` 后，runner 可能自动进入 router/semantic relay，再进入下一个普通节点。`response_group_id` 把这轮内部产生的多个 conversation turn 归为一组。

相关函数：

```text
_response_group_turn_indexes()
_response_group_transition_entries()
_response_group_interrupt_summary()
```

位置：

```text
/home/chenjy/桌面/agent-master/server/router/deployments_interrupts.py
```

`_response_group_interrupt_summary()` 会找出：

- 这一组有哪些 turn；
- 哪个 turn 承载 assistant；
- 是否发生过跳转链；
- source node / target node 是什么。

文字版 RAGENT 也需要这个概念。一次问数可能包含：

```text
extract_slots -> recall_schema -> generate_sql -> validate_sql -> execute_sql -> interpret_result
```

如果用户在 `interpret_result` 流式回答到一半时打断，说“停，按周看”，系统要知道这次回答对应的是哪条 SQL、哪个 result、哪个节点链路，而不是只看最后一段文本。

### 8.5 pending_jump_chain 是什么

定义位置：

```text
/home/chenjy/桌面/agent-master/graph/runtime.py
AgentGraphRunner.pending_jump_chain
```

写入位置：

```text
record_pending_jump_transition()
```

触发位置包括：

- `move()` 正常跳转；
- router / semantic relay 的 `_apply_non_task_transition()`；
- `node_reverse`；
- 普通节点 `<node_jump>`。

它的含义是：上一轮响应中已经真实发生了 `node -> expected_next`，但下一次请求还没消费这条链路。语音中，用户可能在节点刚跳完但下个节点承接还没播完时打断，所以系统必须记住“原本应该续到哪里”。

`pending_jump_chain` 的典型元素：

```json
{
  "node": "A",
  "expected_next": "B",
  "jump_kind": "jump"
}
```

RAGENT 等价场景：

```text
generate_sql -> validate_sql -> execute_sql -> interpret_result
```

如果用户在 `interpret_result` 刚开始回答时改口，系统要知道这轮结果是由哪个 `generate_sql/execute_sql` 派生出来的，并能回退到受影响节点。

### 8.6 下一轮请求如何消费 pending_jump_chain

位置：

```text
/home/chenjy/桌面/agent-master/server/router/deployments_interrupts_flow.py
_consume_pending_jump_chain_for_request()
```

调用位置在：

```text
/home/chenjy/桌面/agent-master/server/router/deployments_stream.py
约 557-579 行
```

逻辑：

1. 如果当前请求不是打断，通常跳过。
2. 如果有 `pending_jump_chain` 且本轮是打断请求，先找到用户实际看到的 assistant 和最新用户输入。
3. 如果开启 rollback judge，调用 `_evaluate_interrupted_rollback_judge()` 判断：

```text
keep_target: 用户是在承接当前目标节点，继续当前节点
rollback: 用户是在改口或否定已跳转内容，回滚到链路来源
```

4. 如果 judge 决定 rollback，调用 `_apply_provisional_interrupted_decision_to_session()` 修改 session runner。
5. 保存 provisional interrupt 状态，下一轮空打断或历史 hash 变化时可恢复。

最关键代码点在 `deployments_interrupts_flow.py` 约 661-803 行：

```python
if pending_jump_chain_before and requested_is_interrupted:
    judge_decision = await _evaluate_interrupted_rollback_judge(...)
    judge_decision_value = "keep_target" if judge_decision.keep_target else "rollback"
    _apply_provisional_interrupted_decision_to_session(...)
```

RAGENT 中可以简化：

- 不需要复杂的“抢答/非抢答”语音判断；
- 只需要判断新用户输入是 `continue_current`、`revise_previous_slots`、`new_query`。

建议新增：

```python
async def resolve_interrupted_request(session_state, new_question, visible_output):
    # return keep_target | rollback | new_query
```

输入：

```text
pending_jump_chain
visible_output
current_node
last_slots
last_sql
new_question
```

输出：

```json
{
  "decision": "rollback",
  "target_node": "extract_slots",
  "reason": "用户把时间粒度从日改为周",
  "slot_patch": {"dimensions": ["week"]}
}
```

### 8.7 interrupted_handoff_queue 是什么

定义位置：

```text
/home/chenjy/桌面/agent-master/graph/runtime.py
interrupted_handoff_queue
```

核心方法：

```text
set_interrupted_handoff_queue()
_should_prompt_interrupted_handoff()
_mark_interrupted_handoff_prompt_shown()
_advance_or_clear_interrupted_handoff()
```

它的作用是：打断后如果系统决定“继续原目标节点”，就把原本应该经过的跳转边放进队列，后续每到一个节点就注入一次打断承接提示，并按 `node -> expected_next` 逐步消费。

`_advance_or_clear_interrupted_handoff(src, dst)` 的规则：

- 如果当前队头是 `src -> dst`，说明按预期续跳，pop 队头。
- 如果当前跳到了别的分支，说明用户意图变了，清空队列。

RAGENT 可对应为：

```text
用户在解释结果中打断：“继续，不过只看北京”
decision=keep_target，但需要把 filters.city=北京 带到后续 generate_sql 链
handoff_queue = [
  {"node": "extract_slots", "expected_next": "generate_sql"},
  {"node": "generate_sql", "expected_next": "validate_sql"}
]
```

不过文字问数里可以更简单：多数情况下直接回滚到受影响节点重跑，不必保留复杂 handoff queue。只有“用户补充但不否定当前链路”时才需要 keep target。

### 8.8 conversation rewrite：如何避免模型看到未听到内容

位置：

```text
/home/chenjy/桌面/agent-master/server/router/deployments_interrupt_rewrite.py
_rewrite_interrupted_response_group_conversation()
```

它会把一段完整 assistant 切成：

```text
heard_text: 用户实际听到/看到的部分
unheard_text: 用户未听到/未看到的尾部
```

然后写入 conversation projection：

```python
set_interrupt_response_group_projection(
  response_group_id,
  {
    "replacement_text": "...",
    "omit_assistant_turns": [...],
    "heard_text": "...",
    "unheard_text": "...",
    "split_node": "..."
  }
)
```

这样下一次 `Conversation.to_messages()` 时，模型不会把未听到的尾部当成用户已知事实。它只看到类似：

```text
[打断提示] 上一条 assistant 输出被打断。
用户已感知：“...”
用户未感知：“...”
```

RAGENT 文字版也应该做这个，否则前端已经中断的回答尾巴仍在 memory 里，下一轮模型会误以为用户已经看过完整答案。

### 8.9 Session 快照如何恢复 runner

持久化恢复位置：

```text
/home/chenjy/桌面/agent-master/server/deployment_session_store.py
build_deployment_session_from_snapshot()
```

恢复字段包括：

```text
runner.current
runner.start
runner.visited
runner.transitions
runner.pending_enter
runner.task_done
runner.cross_edge_sources
runner.reverse_source_stack
runner.reverse_pending_nodes
runner.reverse_completed_nodes
runner.interrupted_handoff_queue
runner.pending_jump_chain
runner.pending_interrupted_last_assistant_seen
runner.visible_history_state
```

如果只是从 conversation 重建，则用：

```text
/home/chenjy/桌面/agent-master/server/router/deployments_interrupts.py
_rebuild_runner_from_conversation()
```

它遍历每个 turn 的 metadata：

```text
kind=node_enter
node_before
node_after
jump
jump_kind
```

然后重建：

- `runner.current`
- `runner.transitions`
- `runner.task_done`
- `reverse_source_stack`
- `cross_edge_sources`
- `pending_enter_from_reverse`

这说明每一轮 conversation metadata 必须足够丰富。RAGENT 当前 `SessionStore` 只保存 `question/answer`，不够恢复状态。必须扩展为保存节点元数据和快照。

## 9. 节点流转控制的微观代码位置

### 9.1 图构建与节点类型

```text
/home/chenjy/桌面/agent-master/graph/builder.py
build_agent_graph()
```

负责从 `Agent.next_nodes` 建 adjacency，并校验图结构。

```text
/home/chenjy/桌面/agent-master/graph/runtime.py
AgentGraphRunner.from_roots()
```

负责把图、Agent、router 规则、semantic relay、动态独立边、反悔开关组装成 runner。

关键状态字段在 `AgentGraphRunner`：

```text
current
pending_enter
task_done
prompt_allowed_nexts
router_route_keys
router_jump_rules
cross_edge_sources
reverse_source_stack
reverse_pending_nodes
interrupted_handoff_queue
pending_jump_chain
visible_history_state
```

### 9.2 普通节点流转

位置：

```text
/home/chenjy/桌面/agent-master/graph/runtime_ops.py
step()
step_stream()
```

控制流程：

```text
pending_enter -> 注入 [节点进入] user message
run_current / run_current_stream -> LLM 输出
_extract_runtime_control_tags -> 提取 jump/reverse/reason
question_like_output -> 拦截跳转
node_reverse -> 记录来源链并跳回历史节点
missing_jump_compensation -> 补漏跳
allowed_nexts 校验 -> 防止非法跳转
move / _apply_non_task_transition -> 推进 current
_update_last_turn_transition_metadata -> 写 conversation metadata
```

### 9.3 router 节点流转

位置：

```text
/home/chenjy/桌面/agent-master/graph/runtime.py
_step_router()
```

它不调用模型，只做：

```text
prefill_items -> prefill_value_map
router_route_keys -> 检查多值
router_jump_rules[target] -> evaluate_jump_rules()
matched 必须唯一
current = matched[0]
记录 router_transition
```

RAGENT 应把 `execute_sql` 后的错误分流、slots 完整性分流、用户意图分流尽量做成 router。

### 9.4 semantic relay 节点流转

位置：

```text
/home/chenjy/桌面/agent-master/graph/runtime.py
_step_semantic_relay()
```

它 clone conversation，追加 relay 的节点进入消息，让模型只判断目标节点。输出如果是问句、目标不存在、目标不在 allowed_nexts 都会被拦截或 fallback。

RAGENT 应把“用户本轮是在新查询、追问、改口、要图、要解释”做成 semantic relay，而不是让每个业务节点自己猜。

### 9.5 反悔流转

位置：

```text
/home/chenjy/桌面/agent-master/graph/runtime_ops.py
node_reverse 分支
```

以及：

```text
/home/chenjy/桌面/agent-master/graph/runtime.py
_record_reverse_sources()
_propagate_reverse_sources_on_normal_arrive()
_prune_reverse_sources_on_arrive()
_refresh_reverse_queue_on_multi_targets()
_mark_reverse_node_completed()
```

提示词重建在：

```text
/home/chenjy/桌面/agent-master/graph/runtime_ops.py
_rebuild_agent_for_reverse()
_rebuild_agent_for_normal()
```

RAGENT 的反悔不要只改 `question` 文本，而要找到字段 owner 和派生产物依赖：

```text
time/filter/metric/dimension 改动 -> 回滚到 extract_slots/build_query_plan
SQL 错误修正 -> 回滚到 generate_sql
展示方式改动 -> 回滚到 generate_chart/interpret_result
```

## 10. RAGENT 微观改造建议

### 10.1 新增运行态结构

在 `src/backend/data_agent/agent/state.py` 扩展：

```python
class AgentState(TypedDict, total=False):
    # existing...
    current_node: str
    response_group_id: str
    transitions: list[tuple[str, str]]
    node_status: dict[str, str]
    slots: dict[str, Any]
    slot_sources: dict[str, str]
    control: dict[str, Any]
    visible_output: str
    interrupted: bool
    pending_jump_chain: list[dict[str, Any]]
    interrupted_handoff_queue: list[dict[str, Any]]
    snapshot_id: str
```

### 10.2 新增 run state store

当前 `SessionStore` 只有：

```python
append(session_id, question, answer)
get(session_id) -> list[{"question", "answer"}]
```

应新增：

```python
class RunStateStore(Protocol):
    async def get_active_thread(session_id: str) -> str | None: ...
    async def set_active_thread(session_id: str, thread_id: str) -> None: ...
    async def save_snapshot(thread_id: str, snapshot: dict[str, Any]) -> None: ...
    async def load_snapshot(thread_id: str) -> dict[str, Any] | None: ...
    async def append_visible(thread_id: str, event_text: str) -> None: ...
    async def mark_interrupted(thread_id: str, visible_output: str) -> None: ...
```

Redis key 可参考：

```text
data-agent:run:active:{session_id}
data-agent:run:snapshot:{thread_id}
data-agent:run:visible:{thread_id}
```

### 10.3 修改 `GraphQueryRuntime.ask_stream`

位置：

```text
/home/chenjy/桌面/RAGENTv2/src/backend/data_agent/agent/runtime.py
GraphQueryRuntime.ask_stream()
```

当前每个请求直接创建新 `thread_id` 并 `ainvoke()`。建议改为：

1. 检查同 session 是否有 active thread。
2. 如果有且未完成，设置旧 run abort event，读取旧 visible buffer。
3. 新请求进入 `semantic_intent_relay`，判断 `new_query/revision/followup`。
4. 如果 revision，加载旧 snapshot，按字段 owner 回滚。
5. 每个流式 chunk 通过 `emit()` 前先写入 visible buffer。
6. finally 中保存 snapshot，清理 active thread。

### 10.4 修改节点事件 emit

位置：

```text
/home/chenjy/桌面/RAGENTv2/src/backend/data_agent/agent/context.py
emit()
```

可以在 `emit()` 内统一处理：

```python
if event_type in {"answer_chunk", "sql_chunk"}:
    await ctx.runtime.run_state.append_visible(ctx.thread_id, data.get("text", ""))
```

这样中断恢复不用散落在每个节点里。

### 10.5 新增控制解析与路由

新增：

```text
src/backend/data_agent/orchestration/control.py
src/backend/data_agent/orchestration/rules.py
```

`control.py` 负责：

```python
parse_control(output)
validate_jump(target, allowed_nexts)
compensate_missing_control(state, node_name)
```

`rules.py` 负责照搬并改造 `evaluate_jump_rules()`。

### 10.6 改造 LangGraph

当前：

```text
load_memory -> recall_schema -> generate_sql -> validate_sql -> execute_sql -> interpret_result -> generate_chart -> persist_memory
```

建议变为：

```text
load_memory
-> semantic_intent_relay
-> extract_slots
-> route_after_slots
   -> clarify_slots
   -> recall_schema
-> build_query_plan
-> generate_sql
-> validate_sql
-> execute_sql
-> route_after_execute
   -> repair_sql
   -> interpret_result
   -> refuse_sensitive
   -> empty_result_decision
-> route_after_interpret
   -> generate_chart
   -> persist_memory
```

新增条件边只读 `state["control"]`、`state["slots"]`、`state["error"]`、`state["result"]`，不要让每个节点手写复杂 if。

### 10.7 最小可落地版本

如果不想一次改太大，先做四步：

1. `AgentState` 加 `slots/current_node/transitions/response_group_id/visible_output`。
2. 新增 `extract_slots_node`，在 `load_memory` 后执行。
3. `persist_memory_node` 保存完整 snapshot，而不是只保存 question/answer。
4. `ask_stream` 维护 active thread 和 visible buffer；新请求到来时能把旧 thread 标记 interrupted。

这四步做完，就已经具备文字版“跳答收集 + 可见历史打断”的基础。随后再加 rollback judge 和 semantic relay。
