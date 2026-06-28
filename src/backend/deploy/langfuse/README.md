# Local Langfuse Deployment

This directory runs a self-hosted Langfuse stack for local RAGENTv2
observability. It does not use Langfuse Cloud.

## Start

```bash
cd /home/chenjy/桌面/RAGENTv2/src/backend/deploy/langfuse
cp .env.example .env
docker compose --env-file .env up -d
```

Open:

```text
http://127.0.0.1:3000
```

Default local login from `.env.example`:

```text
admin@ragent.local
change-me-local-only
```

## Connect RAGENT

Set these values in `backend/.env`:

```env
DA_LANGFUSE_ENABLED=true
DA_LANGFUSE_PUBLIC_KEY=pk-lf-ragent-local
DA_LANGFUSE_SECRET_KEY=sk-lf-ragent-local
DA_LANGFUSE_HOST=http://127.0.0.1:3000
DA_LANGFUSE_ENVIRONMENT=local
```

Restart the backend after changing `backend/.env`.

## Ports

Only Langfuse web and MinIO's public endpoint use their common host ports.
Internal services are mapped to higher local ports to avoid colliding with
RAGENT's own Redis/MySQL setup.

```text
Langfuse web       3000
Langfuse worker    3030
Postgres          15432 -> 5432
Redis             16379 -> 6379
ClickHouse HTTP   18123 -> 8123
ClickHouse native 19000 -> 9000
MinIO API          9090 -> 9000
MinIO console      9091 -> 9001
```

## Stop

```bash
cd /home/chenjy/桌面/RAGENTv2/src/backend/deploy/langfuse
docker compose --env-file .env down
```

To remove local Langfuse data as well:

```bash
docker compose --env-file .env down -v
```
