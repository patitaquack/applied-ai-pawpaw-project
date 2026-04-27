from datetime import datetime
from typing import List

from models import Task, ScheduledTask, minutes_to_time

_CATEGORY_ICONS = {
    "feeding": "🍽️",
    "walk": "🦮",
    "medication": "💊",
    "grooming": "✂️",
    "playtime": "🎾",
    "litter": "🪣",
    "other": "📋",
}


def current_day_minute() -> int:
    now = datetime.now()
    return now.hour * 60 + now.minute


def check_upcoming(
    scheduled_tasks: List[ScheduledTask],
    current_minute: int,
    within_minutes: int = 30,
) -> List[str]:
    """Return reminder messages for pending tasks starting within N minutes."""
    reminders = []
    for st in scheduled_tasks:
        if st.task.status != "pending":
            continue
        minutes_until = st.start_minute - current_minute
        if 0 <= minutes_until <= within_minutes:
            reminders.append(_format_reminder(st.task, minutes_until, st.start_minute))
    return reminders


def check_overdue(
    scheduled_tasks: List[ScheduledTask],
    current_minute: int,
) -> List[str]:
    """Return warnings for pending tasks whose scheduled start time has already passed."""
    warnings = []
    for st in scheduled_tasks:
        if st.task.status != "pending":
            continue
        if st.start_minute < current_minute:
            overdue_by = current_minute - st.start_minute
            icon = _CATEGORY_ICONS.get(st.task.category, "📋")
            warnings.append(
                f"{icon} OVERDUE: '{st.task.title}' was scheduled at "
                f"{st.start_time_str()} ({overdue_by} min ago)"
            )
    return warnings


def check_deadline_warnings(tasks: List[Task], current_minute: int) -> List[str]:
    """Return alerts for tasks with a deadline_minute approaching within 60 min or already missed."""
    alerts = []
    for task in tasks:
        if task.status != "pending" or task.deadline_minute is None:
            continue
        minutes_until = task.deadline_minute - current_minute
        icon = _CATEGORY_ICONS.get(task.category, "📋")
        if minutes_until < 0:
            alerts.append(
                f"{icon} MISSED DEADLINE: '{task.title}' was due by "
                f"{minutes_to_time(task.deadline_minute)}"
            )
        elif minutes_until <= 60:
            alerts.append(
                f"{icon} DEADLINE SOON: '{task.title}' must be done by "
                f"{minutes_to_time(task.deadline_minute)} ({minutes_until} min remaining)"
            )
    return alerts


# ── Private helpers ───────────────────────────────────────────────────────────

def _format_reminder(task: Task, minutes_until: int, start_minute: int) -> str:
    icon = _CATEGORY_ICONS.get(task.category, "📋")
    if minutes_until == 0:
        timing = "starting NOW"
    elif minutes_until <= 5:
        timing = f"in {minutes_until} min"
    else:
        timing = f"at {minutes_to_time(start_minute)} ({minutes_until} min)"
    dose = f" — dose: {task.medication_dose}" if task.medication_dose else ""
    return f"{icon} {task.title}{dose} {timing}"
