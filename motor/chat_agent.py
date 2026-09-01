"""Agente de chat do job — tools com limite; modelo barato por padrão."""

from __future__ import annotations

import copy
import urllib.error
from typing import Any

from motor.agent_tools import TOOL_SCHEMAS, AgentJobContext, tool_result_message
from motor.llm import openrouter_enabled
from motor.orchestrator import _chat_completion, _parse_args, _system_prompt_chat, chat_model


def run_job_chat(
    ctx: AgentJobContext,
    message: str,
    *,
    history: list[dict[str, str]] | None = None,
    screen_context: dict[str, Any] | None = None,
    max_iters: int = 8,
) -> dict[str, Any]:
    if not openrouter_enabled():
        return {
            "reply": "OpenRouter não configurado. Configure OPENROUTER_API_KEY para o chat técnico.",
            "proposals_updated": [],
            "proposals": {},
            "tool_trace": [],
            "status": "skipped",
        }

    from motor.chat_screen import format_screen_system_block, try_fast_screen_reply

    if screen_context:
        fast = try_fast_screen_reply(message, screen_context)
        if fast:
            return {
                "reply": fast,
                "proposals_updated": [],
                "proposals": {},
                "tool_trace": ["screen_validation"],
                "status": "ok",
            }

    snapshot = copy.deepcopy(ctx.proposals)
    system = _system_prompt_chat()
    if screen_context:
        system += format_screen_system_block(screen_context)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for h in (history or [])[-8:]:
        role = h.get("role") or "user"
        if role not in {"user", "assistant"}:
            continue
        messages.append({"role": role, "content": (h.get("content") or "")[:2000]})
    messages.append({"role": "user", "content": message[:3000]})

    trace: list[str] = []

    for _ in range(max_iters):
        try:
            body = _chat_completion(
                messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                model=chat_model(),
                max_tokens=1400,
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            return {
                "reply": f"Falha no modelo: HTTP {exc.code}",
                "proposals_updated": [],
                "proposals": {},
                "tool_trace": trace + [detail],
                "status": "error",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "reply": f"Falha no modelo: {exc}",
                "proposals_updated": [],
                "proposals": {},
                "tool_trace": trace,
                "status": "error",
            }

        choice = body["choices"][0]["message"]
        tool_calls = choice.get("tool_calls") or []
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": choice.get("content") or "",
        }
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        messages.append(assistant_msg)

        if not tool_calls:
            updated = [k for k, v in ctx.proposals.items() if snapshot.get(k) != v]
            return {
                "reply": (choice.get("content") or "").strip() or "(sem texto)",
                "proposals_updated": updated,
                "proposals": {k: ctx.proposals[k] for k in updated},
                "tool_trace": trace,
                "status": "ok",
            }

        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            args = _parse_args(fn.get("arguments"))
            result = ctx.dispatch(name, args)
            trace.append(name)
            messages.append(tool_result_message(tc.get("id") or name, result))

    updated = [k for k, v in ctx.proposals.items() if snapshot.get(k) != v]
    return {
        "reply": "Não consegui concluir com as tools disponíveis. Reformule o pedido.",
        "proposals_updated": updated,
        "proposals": {k: ctx.proposals[k] for k in updated},
        "tool_trace": trace,
        "status": "max_iters",
    }
