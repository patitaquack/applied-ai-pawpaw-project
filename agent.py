"""
PawPal+ AI agent — powered by Google Gemini (free tier).

Pure Python, no Streamlit imports. app.py calls run_agent() and applies
the returned pending_actions to session state.

Get a free Gemini API key at: https://aistudio.google.com/apikey
"""

import os
from datetime import date
from typing import Any

from google import genai
from google.genai import types
import google.api_core.exceptions as google_exc

from logger import get_logger
from models import Task, Owner
from scheduler import generate_schedule
from suggestions import get_suggestions

_log = get_logger(__name__)

MODEL = "gemini-2.5-flash"   # default; overridden by get_available_models() at runtime
MAX_TURNS = 15

# Fallback static list — used when the API key is not yet set
AVAILABLE_MODELS = {
    "gemini-2.5-flash":      "Gemini 2.5 Flash",
    "gemini-2.5-flash-lite": "Gemini 2.5 Flash-Lite",
    "gemini-2.5-pro":        "Gemini 2.5 Pro",
    "gemini-2.0-flash":      "Gemini 2.0 Flash",
    "gemini-2.0-flash-lite": "Gemini 2.0 Flash-Lite",
    "gemini-1.5-flash":      "Gemini 1.5 Flash",
    "gemini-1.5-pro":        "Gemini 1.5 Pro",
}

# Models that support generateContent and are worth offering (preference order)
_PREFERRED_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-1.0-pro",
]

def get_available_models(api_key: str) -> dict[str, str]:
    """
    Query the API for models this key can actually use and return a
    {model_id: label} dict ordered by preference.
    Falls back to AVAILABLE_MODELS if the API call fails.
    """
    if not api_key:
        return AVAILABLE_MODELS
    try:
        client = genai.Client(api_key=api_key)
        live = {
            m.name.removeprefix("models/")
            for m in client.models.list()
            if "generateContent" in (m.supported_actions or [])
        }
        _log.debug("live models from API: %s", live)
        result = {
            mid: AVAILABLE_MODELS.get(mid, mid)
            for mid in _PREFERRED_MODELS
            if mid in live
        }
        if result:
            return result
    except Exception as exc:
        _log.warning("get_available_models failed: %s", exc)
    return AVAILABLE_MODELS


SYSTEM_PROMPT = """\
You are PawPal+, an AI assistant that helps pet owners build daily care schedules.

You have five tools:
  list_pets               — discover what pets are saved
  get_suggestions_for_pet — fetch tailored task recommendations for one pet (caches them)
  add_tasks_for_pet       — enqueue the cached tasks for a pet
  preview_schedule        — generate and return a schedule preview
  get_task_queue_summary  — check what is already in the queue

When asked to plan a day or create a schedule:
1. Call list_pets first to confirm pet names.
2. Call get_suggestions_for_pet for each relevant pet.
3. Call add_tasks_for_pet for each pet.
4. Call preview_schedule to generate the schedule.
5. Reply with a clear, friendly summary: tasks added, total time, any conflicts or skipped tasks.
   Flag medication or high-priority items. Keep the reply concise (3-6 lines).

Never guess pet names — always call list_pets first if unsure.
"""

# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="list_pets",
            description="Return all saved pet profiles. Call this first before doing anything else.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        ),
        types.FunctionDeclaration(
            name="get_suggestions_for_pet",
            description="Fetch recommended care tasks for a named pet. Results are cached. Call add_tasks_for_pet afterwards.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "pet_name": types.Schema(type=types.Type.STRING, description="Exact pet name from list_pets."),
                },
                required=["pet_name"],
            ),
        ),
        types.FunctionDeclaration(
            name="add_tasks_for_pet",
            description="Enqueue the cached suggestions for a pet. Must call get_suggestions_for_pet first.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "pet_name": types.Schema(type=types.Type.STRING, description="Exact pet name."),
                },
                required=["pet_name"],
            ),
        ),
        types.FunctionDeclaration(
            name="preview_schedule",
            description="Generate a schedule from the current task queue and return a summary.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "available_minutes": types.Schema(type=types.Type.INTEGER, description="Minutes available today."),
                    "day_start_hour":    types.Schema(type=types.Type.INTEGER, description="24-hour start hour (default 8)."),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="get_task_queue_summary",
            description="Return a count of tasks in the queue, broken down by pet and category.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        ),
    ])
]


# ── Tool execution ─────────────────────────────────────────────────────────────

def execute_tool(name: str, tool_input: dict, context: dict) -> dict:
    """Execute one tool call and return a plain dict."""
    _log.info("tool_call | %s  input=%s", name, tool_input)
    try:
        return _dispatch(name, tool_input, context)
    except Exception as exc:
        _log.error("tool_call error | %s: %s", name, exc, exc_info=True)
        return {"error": str(exc)}


def _dispatch(name: str, tool_input: dict, context: dict) -> dict[str, Any]:
    # ── list_pets ──────────────────────────────────────────────────────────────
    if name == "list_pets":
        pets = context.get("pets", [])
        if not pets:
            return {"pets": [], "note": "No pets saved — ask the user to add pets in the Pet Profile tab."}
        return {
            "pets": [
                {
                    "name":      p.name,
                    "species":   p.species,
                    "size":      p.size or "medium",
                    "age_group": p.age_group or "adult",
                    "lifestyle": p.lifestyle or ("active_dog" if p.species == "dog" else "indoor_cat"),
                    "age_years": p.age_years,
                    "is_senior": p.is_senior,
                    "health":    p.health_conditions or "",
                }
                for p in pets
            ]
        }

    # ── get_suggestions_for_pet ────────────────────────────────────────────────
    elif name == "get_suggestions_for_pet":
        pet_name = tool_input.get("pet_name", "")
        pet = next((p for p in context.get("pets", []) if p.name == pet_name), None)
        if pet is None:
            return {"error": f"No pet named '{pet_name}'. Call list_pets to confirm names."}

        pet_type  = pet.species if pet.species in ("dog", "cat") else "dog"
        size      = pet.size or "medium"
        age_group = pet.age_group or "adult"
        lifestyle = pet.lifestyle or ("active_dog" if pet_type == "dog" else "indoor_cat")

        raw_tasks = get_suggestions(pet_type, size, age_group, lifestyle)
        context.setdefault("_cached", {})[pet_name] = raw_tasks

        return {
            "pet_name":   pet_name,
            "task_count": len(raw_tasks),
            "tasks": [
                {
                    "title":            t["title"],
                    "category":         t["category"],
                    "priority":         t["priority"],
                    "duration_minutes": t["duration_minutes"],
                    "recurrence":       t["recurrence"],
                    "notes":            t.get("notes", ""),
                }
                for t in raw_tasks
            ],
            "note": f"Call add_tasks_for_pet with pet_name='{pet_name}' to enqueue these.",
        }

    # ── add_tasks_for_pet ──────────────────────────────────────────────────────
    elif name == "add_tasks_for_pet":
        pet_name = tool_input.get("pet_name", "")
        cached = context.get("_cached", {}).get(pet_name)
        if not cached:
            return {"error": f"No cached suggestions for '{pet_name}'. Call get_suggestions_for_pet first."}

        tasks_to_add = [{**t, "pet_name": pet_name} for t in cached]
        context.setdefault("pending_actions", []).append(
            {"action": "add_tasks", "pet_name": pet_name, "tasks": tasks_to_add}
        )
        _log.info("add_tasks_for_pet | pet=%s count=%d", pet_name, len(tasks_to_add))
        return {"added": len(tasks_to_add), "pet_name": pet_name}

    # ── preview_schedule ───────────────────────────────────────────────────────
    elif name == "preview_schedule":
        available_minutes = tool_input.get("available_minutes") or context.get("available_minutes", 120)
        day_start_hour    = tool_input.get("day_start_hour", 8)

        all_dicts = list(context.get("tasks", []))
        for action in context.get("pending_actions", []):
            if action["action"] == "add_tasks":
                all_dicts.extend(action["tasks"])

        if not all_dicts:
            return {"error": "No tasks in queue. Use add_tasks_for_pet first."}

        task_objects = []
        for td in all_dicts:
            d = dict(td)
            if isinstance(d.get("due_date"), str):
                d["due_date"] = date.fromisoformat(d["due_date"])
            elif not isinstance(d.get("due_date"), date):
                d["due_date"] = date.today()
            task_objects.append(Task(**d))

        owner = Owner(
            name=context.get("owner_name") or "Owner",
            available_minutes=int(available_minutes),
        )
        sched = generate_schedule(owner, task_objects, day_start_minute=day_start_hour * 60)

        context.setdefault("pending_actions", []).append(
            {"action": "set_schedule_preview", "schedule": sched}
        )

        lines = [
            f"{st.start_time_str()} – {st.end_time_str()} | "
            f"{st.task.pet_name or '?'} | {st.task.title} ({st.task.priority})"
            for st in sched.scheduled_tasks[:8]
        ]
        if len(sched.scheduled_tasks) > 8:
            lines.append(f"… and {len(sched.scheduled_tasks) - 8} more")

        result: dict[str, Any] = {
            "scheduled":    len(sched.scheduled_tasks),
            "skipped":      len(sched.skipped_tasks),
            "conflicts":    len(sched.conflicts),
            "minutes_used": sched.total_minutes_scheduled,
            "schedule":     lines,
        }
        if sched.skipped_tasks:
            result["skipped_tasks"] = [t.title for t in sched.skipped_tasks]
        if sched.conflicts:
            result["conflict_details"] = [
                f"'{c.task_a}' and '{c.task_b}' overlap {c.overlap_end - c.overlap_start} min"
                for c in sched.conflicts
            ]
        return result

    # ── get_task_queue_summary ─────────────────────────────────────────────────
    elif name == "get_task_queue_summary":
        all_dicts = list(context.get("tasks", []))
        for action in context.get("pending_actions", []):
            if action["action"] == "add_tasks":
                all_dicts.extend(action["tasks"])
        if not all_dicts:
            return {"total": 0, "note": "Queue is empty."}
        by_pet: dict[str, int] = {}
        by_cat: dict[str, int] = {}
        for t in all_dicts:
            by_pet[t.get("pet_name") or "unassigned"] = by_pet.get(t.get("pet_name") or "unassigned", 0) + 1
            by_cat[t.get("category") or "other"]      = by_cat.get(t.get("category") or "other", 0) + 1
        return {"total": len(all_dicts), "by_pet": by_pet, "by_category": by_cat}

    return {"error": f"Unknown tool: {name}"}


# ── Agentic loop ──────────────────────────────────────────────────────────────

def run_agent(
    user_message: str,
    context: dict,
    chat_history: list[dict],
    api_key: str = "",
    model: str = "",
) -> dict:
    """
    Run the PawPal+ agent for one user turn.

    Args:
        user_message:  Natural language request.
        context:       Session snapshot + sidecars (_cached, pending_actions).
        chat_history:  Prior clean text turns [{"role": ..., "content": str}].
        api_key:       Gemini API key. Falls back to GEMINI_API_KEY env var.
        model:         Gemini model ID. Falls back to MODULE-level MODEL constant.

    Returns dict with keys:
        final_answer    — str for chat UI
        pending_actions — list of actions for app.py to apply
        error           — error code string or None
        retry_after     — suggested wait seconds (quota errors only), or None
    """
    resolved_key   = api_key or os.environ.get("GEMINI_API_KEY", "")
    resolved_model = model or MODEL

    if not resolved_key:
        return {
            "final_answer": (
                "⚠️ Gemini API key not found.\n\n"
                "1. Get a **free** key at https://aistudio.google.com/apikey\n"
                "2. Add it to `.streamlit/secrets.toml`:\n"
                "```toml\nGEMINI_API_KEY = \"AIza...\"\n```\n"
                "3. Restart the app."
            ),
            "pending_actions": [],
            "error": "missing_api_key",
            "retry_after": None,
        }

    client = genai.Client(api_key=resolved_key)
    context.setdefault("_cached", {})
    context.setdefault("pending_actions", [])

    # Build prior conversation history
    history = []
    for msg in chat_history:
        role = "model" if msg["role"] == "assistant" else "user"
        history.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

    config = types.GenerateContentConfig(
        tools=TOOLS,
        system_instruction=SYSTEM_PROMPT,
    )

    chat = client.chats.create(model=resolved_model, history=history, config=config)

    _log.info("run_agent | model=%s user=%r history_turns=%d", resolved_model, user_message[:80], len(history))

    try:
        response = chat.send_message(user_message)

        for turn in range(MAX_TURNS):
            _log.debug("turn %d", turn + 1)

            # Collect function calls from this response
            fn_calls = [
                part.function_call
                for candidate in response.candidates
                for part in candidate.content.parts
                if part.function_call
            ]

            if not fn_calls:
                _log.info("run_agent done | turns=%d actions=%d", turn + 1, len(context["pending_actions"]))
                return {
                    "final_answer":    response.text,
                    "pending_actions": context["pending_actions"],
                    "error":           None,
                }

            # Execute each tool call and collect response parts
            response_parts = []
            for fc in fn_calls:
                _log.info("executing | %s args=%s", fc.name, dict(fc.args))
                result = execute_tool(fc.name, dict(fc.args), context)
                response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(name=fc.name, response=result)
                    )
                )

            response = chat.send_message(response_parts)

        _log.warning("run_agent exceeded MAX_TURNS=%d", MAX_TURNS)
        return {
            "final_answer": "I wasn't able to finish in time. Try a simpler request.",
            "pending_actions": context["pending_actions"],
            "error": "max_turns_exceeded",
            "retry_after": None,
        }

    except google_exc.PermissionDenied:
        return {
            "final_answer": "⚠️ Invalid Gemini API key. Check `.streamlit/secrets.toml`.",
            "pending_actions": [],
            "error": "auth_error",
            "retry_after": None,
        }
    except google_exc.ResourceExhausted as exc:
        _log.error("quota exceeded (full error): %s", exc, exc_info=True)
        retry_after = _extract_retry_delay(exc)
        wait_hint = f" Suggested wait: **{retry_after}s**." if retry_after else ""
        return {
            "final_answer": (
                f"AI is temporarily unavailable because the Gemini API quota was reached.{wait_hint} "
                "You can try again later, switch to a different model in settings, "
                "or use the **Built-in Planner** button below to get a plan without AI."
            ),
            "pending_actions": [],
            "error": "quota_exceeded",
            "retry_after": retry_after,
        }
    except Exception as exc:
        _log.error("run_agent unexpected error: %s", exc, exc_info=True)
        return {
            "final_answer": (
                "Something went wrong with the AI. "
                "Use the **Built-in Planner** button below to continue without AI."
            ),
            "pending_actions": [],
            "error": str(exc),
            "retry_after": None,
        }


def _extract_retry_delay(exc: google_exc.ResourceExhausted) -> int | None:
    """Try to extract retryDelay seconds from a 429 error. Returns None if not found."""
    try:
        for detail in exc.details():
            if hasattr(detail, "retry_delay"):
                return int(detail.retry_delay.seconds)
    except Exception:
        pass
    # Fall back to scanning the string representation
    import re
    match = re.search(r"retry[_\s]?delay[\":\s]+(\d+)", str(exc), re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None
