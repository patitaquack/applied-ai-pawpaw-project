from dataclasses import replace
from datetime import date, timedelta
from typing import List, Optional

from logger import get_logger
from models import (
    Task, Owner, Schedule, ScheduledTask, ConflictWarning,
    PRIORITY_ORDER, minutes_to_time,
)

_log = get_logger(__name__)


def filter_tasks(tasks: List[Task], pet_name: Optional[str] = None, status: Optional[str] = None) -> List[Task]:
    return [
        t for t in tasks
        if (pet_name is None or t.pet_name == pet_name)
        and (status is None or t.status == status)
    ]


def sort_by_time(tasks: List[Task]) -> List[Task]:
    return sorted(
        tasks,
        key=lambda t: t.preferred_start_minute if t.preferred_start_minute is not None else 9999,
    )


def expand_recurring(tasks: List[Task], day_start_minute: int = 480) -> List[Task]:
    expanded = []
    for task in tasks:
        expanded.append(task)
        if task.recurrence == "twice_daily":
            second = replace(
                task,
                title=f"{task.title} (2nd)",
                preferred_start_minute=(
                    (task.preferred_start_minute or day_start_minute) + 480
                ),
            )
            expanded.append(second)
    return expanded


def detect_conflicts(scheduled_tasks: List[ScheduledTask]) -> List[ConflictWarning]:
    warnings = []
    for i, a in enumerate(scheduled_tasks):
        for b in scheduled_tasks[i + 1:]:
            overlap_start = max(a.start_minute, b.start_minute)
            overlap_end = min(a.end_minute, b.end_minute)
            if overlap_start < overlap_end:
                warnings.append(ConflictWarning(
                    task_a=a.task.title,
                    task_b=b.task.title,
                    pet_a=a.task.pet_name or "unknown",
                    pet_b=b.task.pet_name or "unknown",
                    overlap_start=overlap_start,
                    overlap_end=overlap_end,
                ))
    return warnings


def generate_schedule(
    owner: Owner,
    tasks: List[Task],
    day_start_minute: int = 480,
    pet_name: Optional[str] = None,
) -> Schedule:
    _log.info(
        "generate_schedule | owner=%s available=%d min tasks=%d day_start=%d",
        owner.name, owner.available_minutes, len(tasks), day_start_minute,
    )

    filtered = filter_tasks(tasks, pet_name=pet_name, status="pending")
    expanded = expand_recurring(filtered, day_start_minute)
    day_end_minute = day_start_minute + owner.available_minutes

    anchored = sorted(
        [t for t in expanded if t.preferred_start_minute is not None],
        key=lambda t: t.preferred_start_minute,
    )
    floating = sorted(
        [t for t in expanded if t.preferred_start_minute is None],
        key=lambda t: (PRIORITY_ORDER[t.priority], t.duration_minutes),
    )

    schedule = Schedule(owner=owner)

    # Place anchored tasks at their exact preferred start times
    for task in anchored:
        start = task.preferred_start_minute
        if start >= day_start_minute and start + task.duration_minutes <= day_end_minute:
            schedule.scheduled_tasks.append(ScheduledTask(task=task, start_minute=start, reason=""))
        else:
            reason = (
                f"Preferred time {minutes_to_time(task.preferred_start_minute)} is outside today's "
                f"window ({minutes_to_time(day_start_minute)}–{minutes_to_time(day_end_minute)})"
            )
            schedule.skipped_tasks.append(task)
            schedule.skipped_reasons[task.title] = reason
            _log.warning("SKIPPED anchored task '%s' — %s", task.title, reason)

    # Fill gaps with floating tasks sorted by priority then duration
    occupied = sorted((st.start_minute, st.end_minute) for st in schedule.scheduled_tasks)

    for task in floating:
        gap_start = day_start_minute
        placed = False
        for occ_start, occ_end in occupied:
            if occ_start - gap_start >= task.duration_minutes:
                schedule.scheduled_tasks.append(ScheduledTask(task=task, start_minute=gap_start, reason=""))
                occupied = sorted(occupied + [(gap_start, gap_start + task.duration_minutes)])
                placed = True
                break
            gap_start = max(gap_start, occ_end)
        if not placed:
            if day_end_minute - gap_start >= task.duration_minutes:
                schedule.scheduled_tasks.append(ScheduledTask(task=task, start_minute=gap_start, reason=""))
                occupied = sorted(occupied + [(gap_start, gap_start + task.duration_minutes)])
            else:
                reason = f"Needs {task.duration_minutes} min but only {day_end_minute - gap_start} min remain in the day window"
                schedule.skipped_tasks.append(task)
                schedule.skipped_reasons[task.title] = reason
                _log.warning("SKIPPED floating task '%s' — %s", task.title, reason)

    # Sort by start time and assign human-readable reasons
    schedule.scheduled_tasks.sort(key=lambda st: st.start_minute)
    for idx, st in enumerate(schedule.scheduled_tasks):
        minutes_used_before = sum(s.task.duration_minutes for s in schedule.scheduled_tasks[:idx])
        st.reason = _build_reason(st.task, owner.available_minutes - minutes_used_before, st.start_minute, idx + 1)

    schedule.conflicts = detect_conflicts(schedule.scheduled_tasks)

    _log.info(
        "generate_schedule | result: scheduled=%d skipped=%d conflicts=%d",
        len(schedule.scheduled_tasks), len(schedule.skipped_tasks), len(schedule.conflicts),
    )
    for c in schedule.conflicts:
        _log.warning("CONFLICT: %s", c.message())

    return schedule


def replan_schedule(
    owner: Owner,
    tasks: List[Task],
    new_available_minutes: int,
    day_start_minute: int = 480,
    pet_name: Optional[str] = None,
) -> Schedule:
    """Rebuild schedule when available time changes. Critical tasks are preserved first."""
    _log.info("replan_schedule | new_available_minutes=%d", new_available_minutes)
    owner.available_minutes = new_available_minutes

    def task_sort_key(t: Task):
        critical_score = 0 if t.is_critical else 1
        return (critical_score, PRIORITY_ORDER[t.priority], t.preferred_start_minute or 9999)

    sorted_tasks = sorted(tasks, key=task_sort_key)
    return generate_schedule(owner, sorted_tasks, day_start_minute, pet_name)


def generate_weekly_schedule(
    owner: Owner,
    tasks: List[Task],
    day_start_minute: int = 480,
) -> List[dict]:
    """
    Build a 7-day schedule from a task list using each task's recurrence rule.

    Returns a list of 7 dicts, one per day:
      {"date": date, "day_label": str, "schedule": Schedule}

    Recurrence mapping:
      daily / twice_daily  → appears every day
      weekly               → appears on day 0 (today) only
      none                 → appears on day 0 only
    """
    _log.info("generate_weekly_schedule | owner=%s tasks=%d", owner.name, len(tasks))
    today = date.today()
    week = []

    for offset in range(7):
        day_date = today + timedelta(days=offset)
        day_label = day_date.strftime("%A, %b %-d")

        day_tasks = []
        for task in tasks:
            if task.status != "pending":
                continue
            if task.recurrence in {"daily", "twice_daily"}:
                day_tasks.append(replace(task, due_date=day_date))
            elif offset == 0:
                day_tasks.append(task)

        schedule = generate_schedule(owner, day_tasks, day_start_minute)
        week.append({"date": day_date, "day_label": day_label, "schedule": schedule})

    return week


# ── Private helpers ───────────────────────────────────────────────────────────

def _build_reason(task: Task, remaining_before: int, start_minute: int, slot: int) -> str:
    priority_phrases = {
        "high": "ranked first due to high priority",
        "medium": "ranked after high-priority tasks due to medium priority",
        "low": "scheduled last due to low priority",
    }
    slot_label = {1: "1st", 2: "2nd", 3: "3rd"}.get(slot, f"{slot}th")
    time_str = minutes_to_time(start_minute)

    if task.preferred_start_minute is not None:
        pref_str = minutes_to_time(task.preferred_start_minute)
        if start_minute == task.preferred_start_minute:
            time_note = f"placed at preferred time {pref_str}; "
        else:
            time_note = f"preferred {pref_str}, placed at {time_str}; "
    else:
        time_note = f"no preferred time, placed in earliest gap at {time_str}; "

    return (
        f"Placed {slot_label} at {time_str} — {time_note}"
        f"{priority_phrases[task.priority]}. "
        f"Takes {task.duration_minutes} min; {remaining_before} min were still available."
    )
