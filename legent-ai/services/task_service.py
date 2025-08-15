"""
Task execution service that mirrors the Streamlit app logic using the
agent sampling loop and persists outputs to the database while
broadcasting updates over websockets.
"""

import asyncio
import os
import json
import uuid
from typing import Any, Callable, List, cast
import logging
import base64
from pathlib import Path

from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaTextBlockParam,
    BetaToolUseBlockParam,
)

import models
from models import MessageType
from services.session_service import SessionService
from services.config_service import ConfigService
from services.websocket_service import websocket_service

from agent.loop import (
    APIProvider,
    sampling_loop,
)


logger = logging.getLogger(__name__)


class TaskExecutionService:
    def __init__(
        self,
        anthropic_client: Any,  # reserved for future direct SDK usage
        session_service: SessionService,
        config_service: ConfigService,
    ) -> None:
        self.anthropic_client = anthropic_client
        self.session_service = session_service
        self.config_service = config_service

    async def execute_task(self, task_request: models.TaskRequest) -> str:
        """Kick off task execution asynchronously and return a task id."""
        logger.info(
            "execute_task: received task for session_id=%s", task_request.session_id
        )
        session = self.session_service.get_session(task_request.session_id)
        if not session:
            logger.error(
                "execute_task: session not found for session_id=%s",
                task_request.session_id,
            )
            raise ValueError("Session not found")

        # Persist the user's message immediately
        self.session_service.add_message_to_session(
            task_request.session_id,
            models.MessageCreate(content=task_request.task_description),
            message_type=MessageType.USER,
            is_internal=False,
        )

        task_id = str(uuid.uuid4())
        logger.info(
            "execute_task: created task_id=%s for session_id=%s",
            task_id,
            task_request.session_id,
        )
        # Fire-and-forget the agent loop
        asyncio.create_task(
            self._run_agent_loop(task_id, task_request.session_id)
        )
        return task_id

    async def _run_agent_loop(self, task_id: str, session_id: str) -> None:
        """Run the agent sampling loop and persist outputs incrementally."""
        try:
            config = self.config_service.get_config_by_session_id(session_id)
            if not config:
                # Create default if missing
                session = self.session_service.get_session(session_id)
                if not session:
                    return
                config = self.config_service.create_default_config_for_session(session)
            logger.info(
                "agent_loop: starting with model=%s provider=%s tool_version=%s session_id=%s",
                getattr(config, "model", None),
                getattr(config, "provider", None),
                getattr(config, "tool_version", None),
                session_id,
            )

            # Preflight environment checks (especially for computer tool)
            ok, reasons = self._preflight_env()
            if not ok:
                msg = (
                    "Preflight failed: system is missing required GUI tools or env. "
                    + "; ".join(reasons)
                )
                logger.error("preflight: %s", msg)
                self._persist_message(session_id, MessageType.SYSTEM, msg)
                await websocket_service.send_to_session({"type": "message"}, session_id)
                return

            # Normalize model and thinking defaults
            supported_fallback_model = "claude-3-7-sonnet-20250219"
            deprecated_models = {
                "claude-3-5-sonnet-20241022",
                "claude-3-5-sonnet-20241022-v2",
                "claude-sonnet-4-20250514",
            }
            if getattr(config, "model", None) in deprecated_models:
                logger.warning(
                    "agent_loop: model %s deprecated; falling back to %s",
                    config.model,
                    supported_fallback_model,
                )
                config.model = supported_fallback_model

            if getattr(config, "thinking_budget", None) in (None, 0):
                # Enable thinking by default if not configured
                config.thinking_budget = 2048

            # Build conversation history from DB messages
            history = self._build_history(session_id)
            logger.debug(
                "agent_loop: built history with %d messages for session_id=%s",
                len(history),
                session_id,
            )

            # Define callbacks to persist and broadcast
            async def api_response_callback(
                request: Any, response: Any, error: Exception | None
            ) -> None:
                # No-op for now; could persist HTTP logs if desired
                if error is not None:
                    logger.warning(
                        "api_response: error=%s", str(error)
                    )
                else:
                    try:
                        method = getattr(getattr(request, "method", None), "upper", lambda: "?")()
                        url = getattr(request, "url", None)
                        status = getattr(response, "status_code", None)
                        logger.debug(
                            "api_response: %s %s -> %s", method, url, status
                        )
                    except Exception:
                        logger.debug("api_response: received response")
                return

            async def handle_output(block: BetaContentBlockParam) -> None:
                # Persist assistant text and tool_use blocks as they stream
                if block["type"] == "text":
                    content = cast(BetaTextBlockParam, block)["text"]
                    if content and content.strip():
                        logger.debug(
                            "agent_output: assistant text len=%d session_id=%s",
                            len(content),
                            session_id,
                        )
                        self._persist_message(
                            session_id,
                            MessageType.ASSISTANT,
                            content,
                        )
                        await websocket_service.send_to_session(
                            {"type": "message"}, session_id
                        )
                elif block["type"] == "tool_use":
                    tool_use = cast(BetaToolUseBlockParam, block)
                    logger.info(
                        "agent_output: tool_use name=%s id=%s session_id=%s",
                        tool_use.get("name"),
                        tool_use.get("id"),
                        session_id,
                    )
                    self._persist_message(
                        session_id,
                        MessageType.TOOL_USE,
                        json.dumps(
                            {
                                "id": tool_use["id"],
                                "name": tool_use["name"],
                                "input": tool_use.get("input", {}),
                            }
                        ),
                    )
                    await websocket_service.send_to_session(
                        {"type": "message"}, session_id
                    )

            async def handle_tool_output(result: Any, tool_id: str) -> None:
                # ToolResult has fields: output, error, base64_image, system
                payload: dict[str, Any] = {"tool_use_id": tool_id}
                if getattr(result, "system", None):
                    payload["system"] = result.system
                if getattr(result, "error", None):
                    payload["error"] = result.error
                if getattr(result, "output", None):
                    payload["output"] = result.output
                if getattr(result, "base64_image", None):
                    # Persist screenshot to static folder and include a URL
                    try:
                        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                        shots_dir = os.path.join(base_dir, "static", "screenshots", session_id)
                        Path(shots_dir).mkdir(parents=True, exist_ok=True)
                        fname = f"{uuid.uuid4().hex}.png"
                        fpath = os.path.join(shots_dir, fname)
                        with open(fpath, "wb") as f:
                            f.write(base64.b64decode(result.base64_image))
                        public_url = f"/static/screenshots/{session_id}/{fname}"
                        payload["image"] = True
                        payload["image_url"] = public_url
                    except Exception:
                        logger.exception("screenshot_persist: failed to write image for session_id=%s", session_id)
                        payload["image"] = True

                err_snip = None
                out_snip = None
                if payload.get("error"):
                    try:
                        err_text = str(payload.get("error"))
                        err_snip = (err_text[:200] + "...") if len(err_text) > 200 else err_text
                    except Exception:
                        err_snip = "<unprintable error>"
                if payload.get("output"):
                    try:
                        out_text = str(payload.get("output"))
                        out_snip = (out_text[:200] + "...") if len(out_text) > 200 else out_text
                    except Exception:
                        out_snip = "<unprintable output>"

                logger.info(
                    "agent_tool_result: id=%s has_error=%s has_output=%s has_image=%s error_snip=%s output_snip=%s",
                    tool_id,
                    bool(payload.get("error")),
                    bool(payload.get("output")),
                    bool(payload.get("image")),
                    err_snip,
                    out_snip,
                )

                self._persist_message(
                    session_id,
                    MessageType.TOOL_RESULT,
                    json.dumps(payload),
                )
                await websocket_service.send_to_session({"type": "message"}, session_id)

            # Run the agent loop
            await self._sampling_loop_bridge(
                model=config.model,
                provider=config.provider,
                system_prompt_suffix=config.system_prompt_suffix or "",
                messages=history,
                output_callback=handle_output,
                tool_output_callback=handle_tool_output,
                api_response_callback=api_response_callback,
                api_key=os.getenv("ANTHROPIC_API_KEY", ""),
                only_n_most_recent_images=3,
                tool_version=cast(models.ToolVersion, config.tool_version),
                max_tokens=config.max_tokens,
                thinking_budget=config.thinking_budget,
                token_efficient_tools_beta=config.token_efficient_tools_beta,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("agent_loop: unhandled error session_id=%s", session_id)
            # Persist error as assistant/system message
            self._persist_message(
                session_id,
                MessageType.SYSTEM,
                f"Task failed: {str(e)}",
            )
            await websocket_service.send_to_session({"type": "message"}, session_id)

    async def _sampling_loop_bridge(
        self,
        *,
        model: str,
        provider: APIProvider | str,
        system_prompt_suffix: str,
        messages: List[dict],
        output_callback: Callable[[BetaContentBlockParam], Any],
        tool_output_callback: Callable[[Any, str], Any],
        api_response_callback: Callable[[Any, Any, Exception | None], Any],
        api_key: str | None,
        only_n_most_recent_images: int | None,
        tool_version: models.ToolVersion,
        max_tokens: int,
        thinking_budget: int | None,
        token_efficient_tools_beta: bool,
    ) -> None:
        # Normalize provider to enum if passed as string
        provider_enum = (
            provider if isinstance(provider, APIProvider) else APIProvider(provider)
        )

        # sampling_loop expects synchronous callbacks; wrap awaits
        def _output_cb(block: BetaContentBlockParam) -> None:
            asyncio.create_task(output_callback(block))

        def _tool_output_cb(result: Any, tool_id: str) -> None:
            asyncio.create_task(tool_output_callback(result, tool_id))

        def _api_resp_cb(request: Any, response: Any, error: Exception | None) -> None:
            asyncio.create_task(api_response_callback(request, response, error))

        logger.info(
            "sampling_loop: invoking model=%s provider=%s max_tokens=%s images_n=%s thinking=%s",
            model,
            provider_enum,
            max_tokens,
            only_n_most_recent_images,
            bool(thinking_budget),
        )
        await sampling_loop(
            model=model,
            provider=provider_enum,
            system_prompt_suffix=system_prompt_suffix,
            messages=messages,
            output_callback=_output_cb,
            tool_output_callback=_tool_output_cb,
            api_response_callback=_api_resp_cb,
            api_key=api_key or "",
            only_n_most_recent_images=only_n_most_recent_images,
            max_tokens=max_tokens,
            tool_version=cast("models.ToolVersion", tool_version),
            thinking_budget=thinking_budget,
            token_efficient_tools_beta=token_efficient_tools_beta,
        )

    def _build_history(self, session_id: str) -> List[dict]:
        """Convert stored messages into Anthropic BetaMessageParam list."""
        db_messages = self.session_service.get_messages_for_session(
            session_id, skip=0, limit=1000
        )
        history: List[dict] = []
        for m in db_messages:
            if m.message_type == MessageType.USER.value:
                history.append(
                    {
                        "role": "user",
                        "content": [
                            BetaTextBlockParam(type="text", text=m.content or "")
                        ],
                    }
                )
            elif m.message_type == MessageType.ASSISTANT.value:
                if (m.content or "").strip():
                    history.append(
                        {
                            "role": "assistant",
                            "content": [
                                BetaTextBlockParam(type="text", text=m.content or "")
                            ],
                        }
                    )
            # For now we skip TOOL_USE and TOOL_RESULT in history to keep prompt lean
        return history

    def _persist_message(
        self, session_id: str, message_type: MessageType, content: str
    ) -> None:
        try:
            self.session_service.add_message_to_session(
                session_id,
                models.MessageCreate(content=content),
                message_type=message_type,
                is_internal=False,
            )
            logger.debug(
                "persist_message: type=%s len=%d session_id=%s",
                message_type,
                len(content or ""),
                session_id,
            )
        except Exception:
            # Best-effort persistence; swallow to avoid crashing loop
            logger.exception(
                "persist_message: failed to persist message type=%s session_id=%s",
                message_type,
                session_id,
            )

    def _preflight_env(self) -> tuple[bool, list[str]]:
        """Validate environment requirements for computer-use tools.

        Returns (ok, reasons). If ok is False, reasons includes human-readable
        problems to surface to the user.
        """
        problems: list[str] = []
        width = int(os.getenv("WIDTH") or 0)
        height = int(os.getenv("HEIGHT") or 0)
        display_env = os.getenv("DISPLAY")
        display_num = os.getenv("DISPLAY_NUM")

        # WIDTH/HEIGHT are required by ComputerTool
        if width <= 0 or height <= 0:
            problems.append("WIDTH/HEIGHT env vars must be set to your display size")

        # We need a valid X display; either DISPLAY_NUM for :N or DISPLAY is set
        if not display_num and not display_env:
            problems.append("DISPLAY or DISPLAY_NUM must be set so xdotool can target the display")

        return (len(problems) == 0, problems)