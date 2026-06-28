"""Small optional Langfuse adapter used by graph nodes."""
from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

from ..core.logging import get_logger

log = get_logger(__name__)

_GENERATION_TYPES = {"generation", "embedding"}
_current_observation_type: ContextVar[str] = ContextVar(
    "data_agent_langfuse_observation_type",
    default="span",
)


def _usage_details(usage: Any) -> dict[str, int] | None:
    """Convert local UsageInfo-like objects into Langfuse usage_details."""
    if usage is None:
        return None
    details = {
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }
    return details if any(details.values()) else None


class _ObservationContext:
    """Safe wrapper around Langfuse's current-observation context manager."""

    def __init__(
        self,
        observer: "LangfuseObserver",
        name: str,
        *,
        as_type: str,
        input: Any = None,
        output: Any = None,
        metadata: Any = None,
        model: str | None = None,
        model_parameters: dict[str, Any] | None = None,
        usage_details: dict[str, int] | None = None,
    ):
        self._observer = observer
        self._name = name
        self._as_type = as_type
        self._input = input
        self._output = output
        self._metadata = metadata
        self._model = model
        self._model_parameters = model_parameters
        self._usage_details = usage_details
        self._cm = None
        self._token: Token[str] | None = None

    def __enter__(self):
        try:
            self._cm = self._observer.client.start_as_current_observation(
                name=self._name,
                as_type=self._as_type,
                input=self._input,
                output=self._output,
                metadata=self._metadata,
                model=self._model,
                model_parameters=self._model_parameters,
                usage_details=self._usage_details,
            )
            self._token = _current_observation_type.set(self._as_type)
            return self._cm.__enter__()
        except Exception as exc:  # noqa: BLE001
            if self._token is not None:
                _current_observation_type.reset(self._token)
                self._token = None
            self._cm = None
            log.warning("Langfuse span start failed (%s): %s", self._name, exc)
            return None

    def __exit__(self, exc_type, exc, tb):
        if self._cm is None:
            return False
        try:
            if exc is not None:
                err_type = exc_type.__name__ if exc_type is not None else "Exception"
                self._observer.update_current(
                    level="ERROR",
                    status_message=f"{err_type}: {str(exc)[:500]}",
                )
            return self._cm.__exit__(exc_type, exc, tb)
        finally:
            if self._token is not None:
                _current_observation_type.reset(self._token)
                self._token = None


class LangfuseObserver:
    """No-op unless Langfuse is enabled and credentials are configured."""

    def __init__(self, client=None, enabled: bool = False):
        self.client = client
        self.enabled = enabled and client is not None

    @classmethod
    def from_settings(cls, settings) -> "LangfuseObserver":
        """Create a Langfuse client from settings, falling back to no-op."""
        if not settings.langfuse_enabled:
            return cls()
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            log.warning("Langfuse enabled but public/secret key is missing; using no-op observer")
            return cls()
        try:
            from langfuse import Langfuse

            client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
                environment=settings.langfuse_environment,
            )
            return cls(client=client, enabled=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("Langfuse init failed; using no-op observer: %s", exc)
            return cls()

    @staticmethod
    def usage_details(usage: Any) -> dict[str, int] | None:
        """Expose UsageInfo conversion for graph nodes."""
        return _usage_details(usage)

    def span(
        self,
        name: str,
        *,
        as_type: str = "span",
        input: Any = None,
        output: Any = None,
        metadata: Any = None,
        model: str | None = None,
        model_parameters: dict[str, Any] | None = None,
        usage_details: dict[str, int] | None = None,
    ):
        """Return a Langfuse observation context manager or a no-op context."""
        if not self.enabled:
            return _NoopContext()
        return _ObservationContext(
            self,
            name,
            as_type=as_type,
            input=input,
            output=output,
            metadata=metadata,
            model=model,
            model_parameters=model_parameters,
            usage_details=usage_details,
        )

    def update_current(
        self,
        *,
        input: Any = None,
        output: Any = None,
        metadata: Any = None,
        version: str | None = None,
        level: str | None = None,
        status_message: str | None = None,
        model: str | None = None,
        model_parameters: dict[str, Any] | None = None,
        usage_details: dict[str, int] | None = None,
        cost_details: dict[str, float] | None = None,
        prompt: Any = None,
    ) -> None:
        """Update the current Langfuse span when available."""
        if not self.enabled:
            return
        try:
            common = {
                "input": input,
                "output": output,
                "metadata": metadata,
                "version": version,
                "level": level,
                "status_message": status_message,
            }
            current_type = _current_observation_type.get()
            if current_type in _GENERATION_TYPES and hasattr(self.client, "update_current_generation"):
                self.client.update_current_generation(
                    **common,
                    model=model,
                    model_parameters=model_parameters,
                    usage_details=usage_details,
                    cost_details=cost_details,
                    prompt=prompt,
                )
            else:
                self.client.update_current_span(**common)
        except Exception as exc:  # noqa: BLE001
            log.debug("Langfuse span update failed: %s", exc)

    def flush(self) -> None:
        """Flush Langfuse client buffers."""
        if not self.enabled:
            return
        try:
            self.client.flush()
        except Exception as exc:  # noqa: BLE001
            log.debug("Langfuse flush failed: %s", exc)


class _NoopContext:
    """Context manager that preserves the same calling shape when disabled."""

    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False
