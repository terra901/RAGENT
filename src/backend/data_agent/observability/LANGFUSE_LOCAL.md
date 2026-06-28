# Local Langfuse

RAGENTv2 does not require Langfuse Cloud. Langfuse is an optional external
observability service; the agent only sends observations to the configured
`DA_LANGFUSE_HOST`.

## Deployment Boundary

- Run Langfuse as a separate local/self-hosted service.
- Use `backend/deploy/langfuse/` for the local Docker Compose stack.
- After Langfuse starts, open `http://127.0.0.1:3000`, create a project, and copy
  that project's public and secret keys.
- Keep `DA_LANGFUSE_ENABLED=false` until the local service and keys are ready.

```bash
cd /home/chenjy/桌面/RAGENTv2/src/backend/deploy/langfuse
cp .env.example .env
docker compose --env-file .env up -d
```

## RAGENT Configuration

Set these values in `backend/.env`:

```env
DA_LANGFUSE_ENABLED=true
DA_LANGFUSE_PUBLIC_KEY=pk-lf-ragent-local
DA_LANGFUSE_SECRET_KEY=sk-lf-ragent-local
DA_LANGFUSE_HOST=http://127.0.0.1:3000
DA_LANGFUSE_ENVIRONMENT=local
```

Do not replace `DA_LANGFUSE_HOST` with a hosted Langfuse endpoint. The code
default and repository `.env` are local-first.

## What Gets Reported

The LangGraph runtime creates one top-level observation per question:

```text
data_agent.graph
```

Each graph node then records a child observation:

```text
agent.load_memory
agent.recall_schema
agent.generate_sql
agent.validate_sql
agent.execute_sql
agent.interpret_result
agent.generate_chart
agent.persist_memory
```

LLM nodes use Langfuse `generation` observations and include model name, model
parameters, token usage, and sanitized output summaries. Tool and guardrail nodes
mark execution or validation failures with `ERROR`.
