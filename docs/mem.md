你要指导 Codex 做的话，不要只告诉它“做一个长期记忆”。应该把 Hermes 的设计拆成**可落地的模块、表结构、队列任务、上下文注入流程、记忆更新策略**。我先讲 Hermes 是怎么做的，再给你一份可以直接丢给 Codex 的实现说明。

---

# 1. Hermes 的记忆系统本质是什么？

Hermes 的记忆不是一个单纯的向量库，而是一个**分层上下文系统**。

它把“记忆”分成几类：

```text
1. 始终注入 Prompt 的小型核心记忆
2. 可搜索的历史会话
3. 外部记忆 Provider，例如 Honcho、Mem0、OpenViking 等
4. 社区扩展 Memory OS 的多层长期记忆系统
```

Hermes 官方内置记忆很克制。它主要有两个文件：`MEMORY.md` 和 `USER.md`，都放在 `~/.hermes/memories/` 目录下。`MEMORY.md` 记录 Agent 的个人笔记，例如环境事实、项目约定、工具缺陷、完成过的任务；`USER.md` 记录用户档案，例如用户偏好、沟通风格、工作习惯等。官方文档里给的限制是 `MEMORY.md` 约 2200 字符，`USER.md` 约 1375 字符，并且会在会话开始时作为冻结快照注入系统提示。([Hermes Agent][1])

这个设计的关键点是：

> 不是把所有历史都塞进 Prompt，而是只把最关键、最稳定、最高频的信息压缩成小记忆块注入。

这点对你的 DataAgent 很重要。你的企业数据分析 Agent 不能把所有历史问题、SQL、报错、用户对话都塞进上下文，而是要分层管理。

---

# 2. Hermes 官方内置记忆怎么工作？

## 2.1 两个核心记忆文件

Hermes 内置记忆分两个目标：

```text
MEMORY.md
  Agent 的个人笔记
  记录项目事实、环境事实、工具经验、已完成任务、工作流经验

USER.md
  用户档案
  记录用户偏好、沟通风格、身份、工作习惯、技术熟练程度
```

官方例子里，`memory` 适合保存“服务器运行 Debian 12，使用 PostgreSQL 16”“不要对 Docker 命令使用 sudo”“项目使用某种代码规范”等；`user` 适合保存“用户更喜欢 TypeScript 而不是 JavaScript”“用户偏好简洁回答”等。([Hermes Agent][1])

映射到你的 DataAgent，可以这样理解：

```text
USER.md 类似：
  用户偏好
  用户常用分析方式
  用户喜欢的回答格式
  用户所属角色或业务视角

MEMORY.md 类似：
  当前项目技术栈
  数据库连接方式
  指标口径
  部门命名习惯
  SQL 生成经验
  常见错误和修复方式
```

---

## 2.2 会话开始时注入，不是每轮动态刷新

Hermes 的记忆会在会话开始时加载，并以冻结块形式渲染进系统提示。文档明确说：会话期间修改记忆会立即持久化到磁盘，但不会反映到当前会话的系统提示里，要到下一次会话开始才生效。这样做是为了保留 LLM 的前缀缓存，提高性能。([Hermes Agent][1])

这个点很工程化：

```text
会话开始：
  读取核心记忆
  组成 System Prompt
  冻结本轮上下文

会话中：
  可以新增/修改记忆
  但不强行重写当前 System Prompt

下次会话：
  使用最新记忆
```

你自己的项目可以稍微改一下：
对于企业数据分析系统，**短期状态应该实时更新，长期记忆不一定实时进入当前 Prompt**。

例如：

```text
短期记忆 Redis：
  当前分析意图
  当前指标
  当前筛选条件
  当前节点进度
  当前 SQL 草稿
  当前错误重试信息

长期记忆 MySQL/Qdrant：
  用户偏好
  指标口径
  历史分析模式
  常见问题
  高质量 SQL 案例
```

---

## 2.3 memory 工具只有 add / replace / remove

Hermes 的 `memory` 工具有三个核心操作：

```text
add      添加新记忆
replace  替换旧记忆
remove   删除旧记忆
```

官方文档特别说明：没有 `read` 操作，因为记忆会在会话开始时自动注入系统提示，Agent 把它当成上下文的一部分。`replace` 和 `remove` 使用 `old_text` 子字符串匹配，如果匹配多个条目就会报错，要求提供更具体的匹配。([Hermes Agent][1])

这个设计可以直接借鉴。

你的系统里可以做成：

```python
memory_add(content, scope, type, source)
memory_replace(memory_id 或 old_text, new_content)
memory_remove(memory_id 或 old_text)
memory_search(query, filters)
memory_context(query, user_id, project_id)
```

但对你的 DataAgent，我建议比 Hermes 多一个 `search` 和 `context`，因为你的场景不是纯个人 Agent，而是企业数据分析，需要按任务召回相关指标、SQL、部门口径。

---

# 3. Hermes 如何决定“什么应该记住”？

Hermes 的规则非常值得抄。

它会保存：

```text
用户偏好
环境事实
修正信息
项目约定
已完成的重要工作
用户明确要求记住的信息
```

它会忽略：

```text
琐碎信息
容易重新发现的公共事实
大段代码、日志、数据表
会话特有的一次性上下文
已经写在上下文文件里的信息
```

官方文档也强调，记忆满了之后要合并、替换、压缩旧条目，而不是无限增长；当使用率超过 80% 时，应该优先合并已有条目。([Hermes Agent][1])

这对应到你的企业 DataAgent，就是：

## 应该记住

```text
用户常用指标：
  “用户经常看 GMV、转化率、客单价。”

部门口径：
  “销售额口径排除退款订单，按支付成功时间统计。”

分析偏好：
  “用户喜欢先看同比/环比，再看分渠道拆解。”

常见筛选条件：
  “运营部门通常默认过滤测试门店和内部账号。”

高质量 SQL 模式：
  “查询复购率时，先按 user_id 聚合首购和二购时间。”

工具经验：
  “Doris 对某类窗口函数性能差，优先改写为子查询聚合。”
```

## 不应该记住

```text
某次临时查询的完整 SQL
某次用户随口说的无稳定价值信息
大段报错日志
完整数据表结果
可以从元数据服务实时查到的表结构
敏感凭证、token、密码
```

---

# 4. Hermes 的 session_search 是什么？

除了 `MEMORY.md` 和 `USER.md`，Hermes 还会把 CLI 和消息会话存入 SQLite 的 `state.db`，并启用 FTS5 全文搜索。这样，即使某些内容没有进入核心记忆，Agent 也可以通过 `session_search` 找回历史对话。官方文档把“持久记忆”和“会话搜索”区分得很清楚：核心记忆容量很小，但速度快、固定注入；会话搜索容量几乎无限，但需要按需搜索和摘要。([Hermes Agent][1])

这就是你现在长期记忆设计里最容易混淆的地方：

> 长期记忆不等于所有历史都进入 Prompt。
> 长期记忆应该分成“核心记忆”和“可检索历史”。

你的项目应该这样分：

```text
核心记忆：
  少量、高价值、稳定事实
  每次请求默认注入

历史会话：
  所有对话、工具调用、SQL、结果、Trace
  不默认注入
  用户问到相关问题时再检索

结构化业务记忆：
  指标口径、部门口径、用户偏好、常见分析路径
  根据当前任务召回

向量记忆：
  相似问题、相似 SQL、相似分析案例
  根据 query 召回
```

---

# 5. Hermes 外部记忆 Provider 是什么？

Hermes 还支持外部记忆 Provider。文档里列了 Honcho、OpenViking、Mem0、Hindsight、Holographic、RetainDB、ByteRover、Supermemory 等。外部 Provider 不会替代内置 `MEMORY.md / USER.md`，而是叠加运行。启用后，Hermes 会在对话前预取相关记忆，在响应后同步对话轮次，在会话结束时提取记忆，并添加 Provider 专属工具。([Hermes Agent][2])

其中 Honcho 很像“用户建模系统”。它会分析对话内容，持续构建用户偏好、沟通风格、目标和行为模式；它也支持多 Agent 隔离，不同 Agent 可以有自己的同伴档案，避免上下文互相污染。([Hermes Agent][3])

这给你的启发是：

```text
你的 DataAgent 不应该只有一个全局 memory。
至少应该区分：

tenant_id       企业/租户
user_id         用户
project_id      项目
agent_id        Agent 类型
department_id   部门
memory_scope    记忆作用域
```

否则后面会出现严重污染：

```text
A 部门的销售额口径污染 B 部门
测试环境的数据库配置污染生产环境
某个用户的偏好污染所有用户
某个 Agent 的经验污染另一个 Agent
```

---

# 6. Memory OS 的 7 层设计是什么？

社区的 Memory OS 是对 Hermes 的增强。它不是官方内置小记忆，而是一个更完整的长期记忆基础设施。它号称有 7 层：Workspace、Sessions、Structured Facts、Fabric、Vector Database、LLM Wiki、Ground Truth Hierarchy。它要求 Hermes Agent、Docker、Qdrant、Redis、ARQ Worker、Python 3.11+。([GitHub][4])

这 7 层可以这样理解：

```text
Layer 1 Workspace
  MEMORY.md / USER.md / CREATIVE.md
  每轮注入的小型核心记忆

Layer 2 Sessions
  state.db + FTS5
  保存完整历史会话，支持全文搜索

Layer 3 Structured Facts
  memory_store.db
  结构化事实、实体解析、信任评分、反馈循环

Layer 4 Fabric
  跨会话提取和召回
  支持 fabric_recall、fabric_write、fabric_brief 等工具

Layer 5 Vector Database
  Qdrant
  向量 + BM25 混合搜索
  fallback：hybrid → dense → lexical → SQLite

Layer 6 LLM Wiki
  自动整理 concepts / entities / comparisons
  持续摄入向量库

Layer 7 Ground Truth Hierarchy
  SOUL.md / rulebook.md
  明确告诉 Agent：注入的记忆是权威上下文，应该优先使用
```

Memory OS 的执行流也很关键：`pre_llm_call` 阶段从 Fabric、Qdrant、Sessions、Facts 做精准召回；`post_llm_call` 和 `on_session_end` 阶段做自动学习、抽取和保存；同时用相关性阈值、会话内去重、无意义消息过滤来避免上下文灌水。([GitHub][4])

---

# 7. 你自己的 DataAgent 应该怎么借鉴？

你不要直接照抄 Hermes 的文件式记忆。你的系统是企业数据分析 Agent，应该做成数据库化、多租户、可审计的版本。

我建议你的目标架构是：

```text
Redis
  保存短期记忆 / 当前运行态 / 节点状态 / 最近多轮上下文

MySQL 或 PostgreSQL
  保存结构化长期记忆 / 用户偏好 / 指标口径 / 记忆事件 / 审计

Qdrant 或 pgvector
  保存语义向量记忆 / 相似问题 / SQL 案例 / 历史分析片段

RabbitMQ
  异步做记忆抽取 / embedding / 去重 / 衰减 / 归档

LLM
  做候选记忆抽取、摘要、冲突判断、上下文压缩

Prompt Builder
  负责把短期状态 + 核心记忆 + 检索记忆拼成上下文
```

---

# 8. 你的记忆系统推荐分层

## L0：运行态短期记忆，Redis

这是你之前已经想对的部分。

保存：

```text
当前会话状态
当前分析槽位
当前节点进度
最近多轮对话
当前 SQL 草稿
工具调用结果摘要
错误重试状态
用户临时筛选条件
```

Redis key 可以这样设计：

```text
agent:session:{session_id}:state
agent:session:{session_id}:recent_turns
agent:run:{run_id}:slots
agent:run:{run_id}:node_status
agent:run:{run_id}:tool_snapshot
agent:analysis:{analysis_id}:working_context
```

TTL 建议：

```text
recent_turns        24h - 7d
node_status         7d - 30d
tool_snapshot       1d - 7d
working_context     7d - 30d
```

这部分不是长期记忆，不要永久保存。

---

## L1：核心长期记忆，小而稳定

相当于 Hermes 的 `MEMORY.md / USER.md`，但你应该存在数据库里。

保存：

```text
用户偏好
用户常用分析习惯
项目固定配置
部门默认口径
常用指标定义
用户不喜欢的回答方式
```

每次请求都可以注入，但要严格限量，比如：

```text
用户核心记忆：最多 800 tokens
项目核心记忆：最多 1000 tokens
部门核心记忆：最多 800 tokens
```

Prompt 里可以长这样：

```text
[CORE MEMORY - USER]
- 用户偏好：回答需要工程化、落地、详细。
- 用户常做企业数据分析 Agent，关注 Doris、Redis、RabbitMQ、MySQL。
- 用户希望方案能写进简历和面试表达。

[CORE MEMORY - PROJECT]
- 当前项目是企业内部 DataAgent。
- 短期记忆使用 Redis。
- 长期记忆需要支持用户偏好、部门口径、指标定义、历史分析模式。
```

---

## L2：会话归档记忆

保存完整历史，但不默认进入上下文。

表包括：

```text
sessions
messages
tool_calls
analysis_runs
node_traces
sql_generations
query_results_summary
```

用于回答：

```text
“我们上次怎么处理这个指标的？”
“之前那个 SQL 报错是怎么修的？”
“上周做过类似分析吗？”
```

这相当于 Hermes 的 `session_search`，但你的企业版应该带 `tenant_id / user_id / project_id / analysis_id`。

---

## L3：结构化事实记忆

这是你最应该重点做的。

保存：

```text
指标口径
部门口径
用户偏好
项目配置
数据库经验
SQL 生成经验
工具错误经验
业务实体定义
```

例如：

```json
{
  "memory_type": "metric_definition",
  "entity": "GMV",
  "content": "GMV 按支付成功时间统计，排除退款订单和测试门店。",
  "scope": "department",
  "department_id": "sales",
  "confidence": 0.92,
  "source": "user_confirmed"
}
```

这比纯向量记忆可靠，因为企业数据分析最怕口径错。

---

## L4：语义向量记忆

保存：

```text
历史问题
历史 SQL
分析结论摘要
相似案例
业务解释
报错修复经验
```

用于：

```text
根据当前问题召回相似历史问题
根据当前 SQL 报错召回修复经验
根据当前指标召回相关分析案例
```

建议不要只用向量召回，最好做 hybrid：

```text
向量召回
+ 关键词召回
+ 结构化过滤
+ rerank
+ 置信度阈值
```

Memory OS 里也强调 Qdrant 层做混合搜索，并有 fallback：hybrid → dense → lexical → SQLite。([GitHub][4])

---

## L5：知识库 / Wiki 层

这是给企业 DataAgent 做“长期知识沉淀”的。

保存：

```text
指标字典
表结构说明
业务过程文档
部门分析模板
SQL 最佳实践
常见问题 FAQ
分析案例库
```

它不一定是用户记忆，而是项目知识。

例如：

```text
docs/metrics/gmv.md
docs/departments/sales.md
docs/sql_patterns/retention_analysis.md
docs/errors/doris_window_function_perf.md
```

Memory OS 里有类似 LLM Wiki 层，会自动整理 concepts、entities、comparisons，并持续摄入 Qdrant。([GitHub][4])

---

## L6：Ground Truth 规则层

这个很重要。

Memory OS 认为，仅仅召回记忆还不够，还要明确告诉 Agent：这些注入的记忆是权威上下文，否则 Agent 会忽略它们、反复调用工具重新查。Memory OS 把这个叫 Ground Truth Hierarchy。([GitHub][4])

你的系统里也必须有类似规则：

```text
系统规则：
1. 如果 CORE MEMORY 和实时数据库元数据冲突，以实时数据库元数据为准。
2. 如果用户本轮明确更正口径，以用户本轮为准，并生成候选记忆更新。
3. 如果长期记忆之间冲突，优先使用 user_confirmed > admin_verified > inferred。
4. 不允许把低置信度记忆当成事实。
5. SQL 生成时必须标注使用了哪些记忆。
```

这能防止“历史偏好污染当前分析结果”。

---

# 9. 数据库表怎么设计？

下面是一套适合你项目的最小可用表结构。

## memory_items：长期记忆主表

```sql
CREATE TABLE memory_items (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,

  tenant_id BIGINT NOT NULL,
  user_id BIGINT NULL,
  project_id BIGINT NULL,
  department_id BIGINT NULL,
  agent_id VARCHAR(64) NULL,

  scope ENUM('global', 'tenant', 'project', 'department', 'user', 'session') NOT NULL,
  memory_type ENUM(
    'user_preference',
    'project_fact',
    'metric_definition',
    'department_rule',
    'analysis_preference',
    'sql_pattern',
    'tool_lesson',
    'business_entity',
    'workflow',
    'correction',
    'summary'
  ) NOT NULL,

  title VARCHAR(255) NULL,
  content TEXT NOT NULL,
  summary VARCHAR(1000) NULL,

  entities JSON NULL,
  tags JSON NULL,

  source_type ENUM(
    'user_explicit',
    'user_implicit',
    'assistant_inferred',
    'tool_result',
    'admin_verified',
    'document_import',
    'session_summary'
  ) NOT NULL,

  source_ref_id VARCHAR(128) NULL,

  importance DECIMAL(4,3) DEFAULT 0.500,
  confidence DECIMAL(4,3) DEFAULT 0.500,
  trust_score DECIMAL(4,3) DEFAULT 0.500,

  status ENUM('active', 'superseded', 'archived', 'deleted') DEFAULT 'active',
  version INT DEFAULT 1,
  supersedes_id BIGINT NULL,

  valid_from DATETIME NULL,
  valid_until DATETIME NULL,

  last_accessed_at DATETIME NULL,
  access_count INT DEFAULT 0,

  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  FULLTEXT KEY ft_memory_content (title, content, summary),
  INDEX idx_memory_scope (tenant_id, scope, user_id, project_id, department_id),
  INDEX idx_memory_type (memory_type),
  INDEX idx_memory_status (status),
  INDEX idx_memory_source (source_type)
);
```

---

## memory_events：记忆变更审计表

这个非常关键。企业系统里不能只保存当前记忆，还要知道它怎么来的、谁改的、为什么改。

```sql
CREATE TABLE memory_events (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,

  memory_id BIGINT NULL,
  tenant_id BIGINT NOT NULL,
  user_id BIGINT NULL,
  project_id BIGINT NULL,

  event_type ENUM(
    'candidate_generated',
    'created',
    'updated',
    'merged',
    'superseded',
    'archived',
    'deleted',
    'retrieved',
    'injected',
    'feedback_positive',
    'feedback_negative'
  ) NOT NULL,

  old_content TEXT NULL,
  new_content TEXT NULL,
  reason TEXT NULL,

  actor_type ENUM('user', 'assistant', 'system', 'admin', 'worker') NOT NULL,
  actor_id VARCHAR(128) NULL,

  trace_id VARCHAR(128) NULL,
  run_id VARCHAR(128) NULL,
  session_id VARCHAR(128) NULL,

  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  INDEX idx_memory_events_memory (memory_id),
  INDEX idx_memory_events_trace (trace_id, run_id, session_id)
);
```

---

## memory_candidates：候选记忆表

不要让 LLM 直接写正式记忆。更稳的方式是先生成候选记忆，再经过规则过滤、去重、合并、必要时人工确认。

```sql
CREATE TABLE memory_candidates (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,

  tenant_id BIGINT NOT NULL,
  user_id BIGINT NULL,
  project_id BIGINT NULL,
  department_id BIGINT NULL,

  candidate_type VARCHAR(64) NOT NULL,
  content TEXT NOT NULL,
  reason TEXT NULL,

  source_session_id VARCHAR(128) NULL,
  source_message_ids JSON NULL,
  source_trace_id VARCHAR(128) NULL,

  confidence DECIMAL(4,3) DEFAULT 0.500,
  importance DECIMAL(4,3) DEFAULT 0.500,

  decision ENUM('pending', 'accepted', 'rejected', 'merged') DEFAULT 'pending',
  decision_reason TEXT NULL,

  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  decided_at DATETIME NULL,

  INDEX idx_candidate_status (decision),
  INDEX idx_candidate_scope (tenant_id, user_id, project_id)
);
```

---

## session_messages：会话历史

```sql
CREATE TABLE session_messages (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,

  tenant_id BIGINT NOT NULL,
  session_id VARCHAR(128) NOT NULL,
  run_id VARCHAR(128) NULL,
  user_id BIGINT NULL,
  project_id BIGINT NULL,

  role ENUM('user', 'assistant', 'system', 'tool') NOT NULL,
  content MEDIUMTEXT NOT NULL,

  tool_name VARCHAR(128) NULL,
  tool_args JSON NULL,
  tool_result_summary TEXT NULL,

  token_count INT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  FULLTEXT KEY ft_message_content (content),
  INDEX idx_session_messages (session_id, created_at),
  INDEX idx_session_scope (tenant_id, user_id, project_id)
);
```

---

## memory_embeddings：向量索引映射表

如果你用 Qdrant，MySQL 不需要存真实向量，只存映射。

```sql
CREATE TABLE memory_embeddings (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,

  memory_id BIGINT NOT NULL,
  vector_collection VARCHAR(128) NOT NULL,
  vector_point_id VARCHAR(128) NOT NULL,

  embedding_model VARCHAR(128) NOT NULL,
  content_hash CHAR(64) NOT NULL,

  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

  UNIQUE KEY uniq_memory_embedding (memory_id, embedding_model),
  INDEX idx_vector_point (vector_collection, vector_point_id)
);
```

---

# 10. 一次请求的完整流程应该怎么走？

你的 Agent 每次收到用户问题时，应该这样跑：

```text
1. 读取 Redis 短期状态
2. 读取核心长期记忆
3. 根据当前问题召回相关长期记忆
4. 对召回结果去重、过滤、排序
5. 构造 Prompt
6. 调用 LLM
7. 执行工具 / SQL / 节点
8. 保存 session message、tool trace、run state
9. 异步投递 memory.extract 任务
10. worker 抽取候选记忆
11. 去重 / 冲突检测 / 合并 / 入库
12. 更新 embedding
```

伪代码：

```python
async def handle_user_message(request):
    session_state = redis_memory.load_session_state(request.session_id)

    core_memories = memory_service.load_core_memories(
        tenant_id=request.tenant_id,
        user_id=request.user_id,
        project_id=request.project_id,
        department_id=request.department_id,
        token_budget=1500,
    )

    retrieved_memories = memory_service.retrieve_relevant_memories(
        query=request.message,
        tenant_id=request.tenant_id,
        user_id=request.user_id,
        project_id=request.project_id,
        department_id=request.department_id,
        top_k=8,
        min_score=0.62,
    )

    prompt = prompt_builder.build(
        user_message=request.message,
        session_state=session_state,
        core_memories=core_memories,
        retrieved_memories=retrieved_memories,
        tool_schemas=tool_registry.schemas(),
    )

    response = await llm.generate(prompt)

    await session_store.save_turn(request, response)

    await rabbitmq.publish(
        queue="memory.extract",
        payload={
            "tenant_id": request.tenant_id,
            "user_id": request.user_id,
            "project_id": request.project_id,
            "department_id": request.department_id,
            "session_id": request.session_id,
            "message_id": response.message_id,
        },
    )

    return response
```

---

# 11. 记忆抽取 Worker 怎么做？

不要同步抽取长期记忆。用 RabbitMQ 异步做。

队列可以这样分：

```text
memory.extract
  从对话和工具结果中抽取候选记忆

memory.deduplicate
  对候选记忆去重、合并、冲突检测

memory.embed
  对确认后的记忆生成向量

memory.decay
  定期做记忆衰减、归档、删除

memory.audit
  记录注入、命中、反馈
```

抽取 Prompt 可以这样写：

```text
你是企业 DataAgent 的记忆抽取器。
请从以下对话中抽取“未来有复用价值”的记忆候选。

只抽取以下类型：
1. user_preference：用户稳定偏好
2. metric_definition：指标口径
3. department_rule：部门规则
4. analysis_preference：分析习惯
5. sql_pattern：可复用 SQL 模式
6. tool_lesson：工具使用经验
7. correction：用户明确纠正的信息
8. project_fact：项目事实

不要抽取：
1. 临时筛选条件
2. 一次性路径
3. 大段日志
4. 完整 SQL
5. 敏感信息
6. 公共常识
7. 已经可以从元数据服务查询到的信息

输出 JSON：
[
  {
    "candidate_type": "...",
    "content": "...",
    "scope": "user|project|department|tenant",
    "importance": 0.0-1.0,
    "confidence": 0.0-1.0,
    "reason": "...",
    "entities": [],
    "should_require_confirmation": true/false
  }
]
```

---

# 12. 记忆召回时怎么排序？

不要只按向量相似度。

建议公式：

```text
final_score =
  0.35 * semantic_score
+ 0.20 * keyword_score
+ 0.15 * recency_score
+ 0.15 * trust_score
+ 0.10 * importance
+ 0.05 * access_frequency
- 0.20 * conflict_penalty
```

同时必须做 scope 过滤：

```text
tenant_id 必须匹配
project_id 优先匹配
department_id 优先匹配
user_id 优先匹配
status 必须是 active
valid_until 不能过期
confidence 不能低于阈值
```

这能避免“历史偏好污染当前分析结果”。

---

# 13. Prompt 注入应该怎么写？

你的 Prompt Builder 里应该有明确的记忆区块。

例如：

```text
# Memory Context

你将收到几类记忆：

1. CORE_MEMORY
   长期稳定、经过压缩的核心事实。优先级较高。

2. RETRIEVED_MEMORY
   根据当前问题召回的相关历史记忆。需要结合置信度和时间判断。

3. SESSION_STATE
   当前会话短期状态。对本轮任务优先级最高。

使用规则：
- 如果 SESSION_STATE 与长期记忆冲突，优先使用 SESSION_STATE。
- 如果用户本轮明确纠正旧记忆，优先使用用户本轮说法。
- 如果记忆标记为 low_confidence，不要当作确定事实。
- SQL 生成必须优先遵守 metric_definition 和 department_rule。
- 不要向用户暴露内部 memory_id，除非调试模式开启。
```

注入内容可以这样：

```text
[CORE_MEMORY]
- 用户偏好：希望回答详细、工程化、能指导 Codex 实现。confidence=0.95
- 项目事实：当前项目是企业内部 DataAgent，短期记忆计划使用 Redis。confidence=0.90

[RETRIEVED_MEMORY]
- 指标口径：GMV 按支付成功时间统计，排除退款和测试订单。scope=department confidence=0.92 source=user_confirmed
- SQL 经验：Doris 上复杂窗口函数可能性能差，优先改写为预聚合子查询。scope=project confidence=0.81 source=tool_lesson

[SESSION_STATE]
- 当前用户正在设计记忆系统。
- 当前目标是生成可交给 Codex 的实现方案。
```

---

# 14. 你的项目最小可行版本应该怎么做？

不要一上来做 7 层。建议分 5 个阶段。

## V1：Hermes-like 核心记忆

先做：

```text
memory_items 表
memory_events 表
memory_add
memory_replace
memory_remove
load_core_memories
Prompt 注入
```

不做向量库，不做复杂抽取。

核心目标：

```text
能记住用户偏好、项目事实、指标口径。
能注入到 Prompt。
能人工增删改。
```

---

## V2：会话归档 + 全文搜索

再做：

```text
session_messages
tool_calls
analysis_runs
MySQL FULLTEXT 或 Elasticsearch
session_search(query)
```

核心目标：

```text
能找回历史对话、历史 SQL、历史报错。
```

---

## V3：结构化事实 + 候选记忆

再做：

```text
memory_candidates
LLM 抽取候选记忆
规则过滤
人工确认或自动确认
冲突检测
版本管理
```

核心目标：

```text
让系统自动沉淀业务口径和分析经验。
```

---

## V4：向量召回

再加：

```text
Qdrant 或 pgvector
embedding worker
hybrid search
rerank
dedup
```

核心目标：

```text
能根据当前问题找相似历史案例。
```

---

## V5：记忆治理

最后做：

```text
记忆衰减
过期
归档
删除
审计
命中反馈
管理后台
```

核心目标：

```text
防止长期记忆无限增长、防止旧口径污染结果。
```

---

# 15. 直接给 Codex 的实现任务

你可以把下面这段直接丢给 Codex。

```text
请为当前企业 DataAgent 项目实现一个 Hermes-style 分层记忆系统。

目标：
1. 使用 Redis 保存短期会话状态。
2. 使用 MySQL 保存长期结构化记忆。
3. 支持核心记忆注入 Prompt。
4. 支持会话历史归档。
5. 支持异步记忆抽取任务，后续接 RabbitMQ。
6. 先不要实现复杂向量库，但要预留 Qdrant/pgvector 接口。

模块要求：

一、创建 memory 模块
- MemoryItem 数据模型
- MemoryEvent 数据模型
- MemoryCandidate 数据模型
- SessionMessage 数据模型
- MemoryService
- MemoryExtractor
- MemoryRetriever
- MemoryPromptBuilder

二、实现 MemoryService
方法：
- add_memory(...)
- replace_memory(...)
- remove_memory(...)
- archive_memory(...)
- search_memories(...)
- load_core_memories(...)
- retrieve_relevant_memories(...)
- record_memory_event(...)

要求：
- 所有记忆必须带 tenant_id。
- user_id、project_id、department_id 可为空，但查询时必须按 scope 做隔离。
- 记忆状态包括 active、superseded、archived、deleted。
- replace 不要物理覆盖旧内容，要创建新版本，并把旧记忆标记为 superseded。
- remove 默认软删除。
- 所有写操作必须写 memory_events 审计记录。

三、实现 RedisShortTermMemory
保存：
- session_state
- recent_turns
- run_slots
- node_status
- tool_snapshot

Redis key：
- agent:session:{session_id}:state
- agent:session:{session_id}:recent_turns
- agent:run:{run_id}:slots
- agent:run:{run_id}:node_status
- agent:run:{run_id}:tool_snapshot

要求：
- 每类 key 支持 TTL。
- recent_turns 只保留最近 N 轮。
- 不要把长期记忆写入 Redis。

四、实现 PromptBuilder
输入：
- user_message
- session_state
- core_memories
- retrieved_memories
- tool_schemas

输出：
- system prompt
- memory context block

Prompt 规则：
- SESSION_STATE 优先级最高。
- 用户本轮明确纠正的信息优先于长期记忆。
- metric_definition 和 department_rule 对 SQL 生成有高优先级。
- low confidence memory 不能当作确定事实。
- 注入记忆时必须包含 source_type、confidence、scope。

五、实现 MemoryExtractor
输入：
- session_id
- 最近若干轮消息
- 工具调用摘要

输出：
- memory_candidates

抽取类型：
- user_preference
- project_fact
- metric_definition
- department_rule
- analysis_preference
- sql_pattern
- tool_lesson
- business_entity
- correction
- summary

忽略：
- 临时筛选条件
- 大段日志
- 完整 SQL
- 密钥和凭证
- 公共常识
- 一次性路径
- 可从元数据服务实时查询的信息

六、实现检索逻辑
第一版先用 MySQL FULLTEXT + 结构化过滤。
过滤条件：
- tenant_id 必须匹配
- status = active
- scope 按 global、tenant、project、department、user 逐级召回
- confidence >= 0.6
- valid_until 为空或大于当前时间

排序：
- importance
- confidence
- trust_score
- updated_at
- access_count

七、实现数据库迁移
创建以下表：
- memory_items
- memory_events
- memory_candidates
- session_messages
- memory_embeddings，先预留不用

八、实现 API
- POST /memory
- PUT /memory/{id}
- DELETE /memory/{id}
- GET /memory/search
- GET /memory/context
- POST /memory/extract
- POST /memory/{id}/feedback

九、测试
写单元测试：
- 添加记忆
- 替换记忆
- 删除记忆
- scope 隔离
- Prompt 注入 token 限制
- 重复记忆检测
- 低置信度记忆不注入
- 用户级记忆不会污染其他用户
- 部门级指标口径不会污染其他部门

十、不要做的事
- 不要把所有历史消息塞进 Prompt。
- 不要让 LLM 直接写正式 memory_items，必须先写 memory_candidates。
- 不要物理删除记忆，默认软删除。
- 不要保存密码、token、密钥。
- 不要跨 tenant 召回任何记忆。
```

---

# 16. 你现在最应该先做哪一版？

结合你目前的项目阶段，我建议你先做：

```text
Redis 短期记忆
+ MySQL 长期结构化记忆
+ memory_candidates 候选记忆
+ Prompt 注入
+ memory_events 审计
```

暂时不要急着上复杂 Memory OS 全套 7 层。你的第一版目标应该是：

> 让 Agent 能稳定记住用户偏好、项目事实、指标口径、分析习惯，并且不会污染当前分析结果。

等这个跑通以后，再加：

```text
会话搜索
向量召回
SQL 案例库
记忆衰减
管理后台
```

一句话总结：

> Hermes 的核心思想不是“用向量库存所有历史”，而是“核心记忆小而稳定、历史会话可搜索、结构化事实可治理、相关上下文按需注入、记忆更新有审计和边界”。你的 DataAgent 应该照这个思想做企业化版本。

[1]: https://hermesagent.org.cn/docs/user-guide/features/memory "持久记忆 | Hermes Agent 中文社区"
[2]: https://hermesagent.org.cn/docs/user-guide/features/memory-providers "记忆提供者 | Hermes Agent 中文社区"
[3]: https://hermesagent.org.cn/docs/user-guide/features/honcho "Honcho 记忆 | Hermes Agent 中文社区"
[4]: https://github.com/ClaudioDrews/memory-os "GitHub - ClaudioDrews/memory-os: A 7-layer memory operating system for Hermes Agent — persistent memory with Qdrant, structured facts, fabric recall, auto-curated wiki, and surgical context injection. Runs locally, any LLM provider. · GitHub"
