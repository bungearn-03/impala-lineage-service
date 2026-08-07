"""Thin wrapper around the Anthropic SDK for the AI column-lineage fallback.

Kept independent of the ORM/connector/FastAPI layers on purpose — this module
only imports from ``app.core.config`` (for default api key/model) and the
``anthropic`` SDK. Callers in the workers layer should never need to import
`anthropic` themselves; every SDK-level failure is re-raised here as a plain
``RuntimeError``.
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings

from .prompts import SYSTEM_PROMPT, build_user_prompt
from .response_schema import LINEAGE_TOOL_SCHEMA, AILineageResponse

TOOL_NAME = "report_column_lineage"

_LINEAGE_TOOL_DEFINITION: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": (
        "Report the column-level lineage edges you have inferred for the "
        "requested target column(s) of the SQL view under analysis."
    ),
    "input_schema": LINEAGE_TOOL_SCHEMA,
}

_DEFAULT_MAX_TOKENS = 2048


class AnthropicLineageClient:
    """Calls Claude to propose best-effort column lineage for a view.

    The underlying ``anthropic.Anthropic`` client is created lazily on first
    use (not in ``__init__``), so simply importing/instantiating this class
    never requires network access or a valid API key. If no API key is
    available at all, ``infer_column_lineage`` raises a clear
    ``RuntimeError`` when actually called — the app itself can still boot
    fine with AI fallback disabled/unconfigured
    (see ``Settings.ai_lineage_fallback_enabled``, gated at the call site).
    """

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._api_key: str | None = api_key or settings.anthropic_api_key
        self._model: str = model or settings.anthropic_model
        self._enabled: bool = bool(self._api_key)
        self._client: Any = None  # anthropic.Anthropic, created lazily

    def _get_client(self) -> Any:
        if not self._enabled:
            raise RuntimeError(
                "AnthropicLineageClient is not configured: no Anthropic API key "
                "was provided (set ANTHROPIC_API_KEY / Settings.anthropic_api_key). "
                "AI-assisted lineage fallback cannot run without it."
            )
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - dependency should be installed
                raise RuntimeError(
                    "The 'anthropic' package is required for AI-assisted lineage "
                    "fallback but is not installed."
                ) from exc
            try:
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except Exception as exc:  # noqa: BLE001 - re-raise as plain RuntimeError
                raise RuntimeError(
                    f"Failed to initialize the Anthropic client: {exc}"
                ) from exc
        return self._client

    def infer_column_lineage(
        self,
        sql: str,
        target_columns: list[str],
        available_tables: dict,
    ) -> AILineageResponse:
        """Ask Claude to propose column-level lineage edges for ``sql``.

        Raises:
            RuntimeError: if no API key is configured, or if the call to the
                Anthropic API fails for any reason (network error, auth
                error, malformed response, etc). Callers never need to catch
                anthropic-SDK-specific exception types.
        """
        client = self._get_client()
        user_prompt = build_user_prompt(sql, target_columns, available_tables)

        try:
            response = client.messages.create(
                model=self._model,
                max_tokens=_DEFAULT_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=[_LINEAGE_TOOL_DEFINITION],
                tool_choice={"type": "tool", "name": TOOL_NAME},
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as exc:  # noqa: BLE001 - never leak the anthropic SDK type
            raise RuntimeError(
                f"AI-assisted lineage inference failed calling the Anthropic API: {exc}"
            ) from exc

        tool_use_block = next(
            (block for block in response.content if getattr(block, "type", None) == "tool_use"),
            None,
        )
        if tool_use_block is None:
            raise RuntimeError(
                "AI-assisted lineage inference failed: the model did not return a "
                f"'{TOOL_NAME}' tool_use block (stop_reason="
                f"{getattr(response, 'stop_reason', 'unknown')!r})."
            )

        try:
            return AILineageResponse.model_validate(tool_use_block.input)
        except Exception as exc:  # noqa: BLE001 - normalize to RuntimeError
            raise RuntimeError(
                f"AI-assisted lineage inference returned a malformed tool call: {exc}"
            ) from exc
