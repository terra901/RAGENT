"""模型连通性测试。"""
from __future__ import annotations

import time
from typing import Any

from openai import AsyncOpenAI


async def test_model_connectivity(config: dict[str, Any]) -> dict[str, Any]:
    """真实调用一次 OpenAI-compatible chat completions 来验证模型配置。"""
    base_url = str(config.get("baseUrl") or "").strip()
    api_key = str(config.get("apiKey") or "").strip()
    model_code = str(config.get("modelCode") or config.get("code") or "").strip()
    timeout = float(config.get("timeoutSeconds") or 30)
    if not base_url or not api_key or not model_code:
        return {"ok": False, "message": "Base URL、API Key、模型型号不能为空。"}
    client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
    started = time.perf_counter()
    try:
        response = await client.chat.completions.create(
            model=model_code,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=8,
            temperature=0,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        content = response.choices[0].message.content if response.choices else ""
        return {"ok": True, "message": f"模型接口真实调用成功，耗时 {elapsed_ms}ms。", "sample": content}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": str(exc)[:500]}
