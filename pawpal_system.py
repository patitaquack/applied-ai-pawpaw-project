from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import List, Optional


PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
VALID_STATUSES = {"pending", "done", "skipped"}
VALID_RECURRENCES = {"none", "daily", "twice_daily", "weekly"}

# How many days until the next occurrence for each recurrence type
RECURRENCE_DAYS = {"daily": 1, "twice_daily": 1, "weekly": 7}


@dataclass
class Task:
    title: str
    duration_minutes: int
    priority: str                        # "high", "medium", "low"
    notes: str = ""
    pet_name: str = ""                   # which pet this task belongs to
    status: str = "pending"              # "pending", "done", "skipped"
    recurrence: str = "none"             # "none", "daily", "twice_daily"
    preferred_start_minute: Optional[int] = None  # e.g. 480 = prefer 8:00 AM
    due_date: date = field(default_factory=date.today)  # defaults to today

    def __post_init__(self):
        if self.priority not in PRIORITY_ORDER:
            raise ValueError(f"priority must be one of {list(PRIORITY_ORDER)}")
        if self.duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"status must be one of {list(VALID_STATUSES)}")
        if self.recurrence not in VALID_RECURRENCES:
            raise ValueError(f"recurrence must be one of {list(VALID_RECURRENCES)}")

    def mark_complete(self) -> Optional["Task"]:
        """
        Mark this task as done and return a new Task for the next occurrence,
        or None if recurrence is "none".

        Uses timedelta to calculate the next due date:
          - daily / twice_daily: due_date + timedelta(days=1)
          - weekly:              due_date + timedelta(days=7)

        Example:
          next_task = task.mark_complete()
          # task.status is now "done"
          # next_task.due_date is tomorrow (for daily) or 7 days out (for weekly)
          # next_task.status is "pending"
        """
        self.status = "done"

        if self.recurrence == "none":
            return None  # one-off task — no next occurrence

        days_ahead = RECURRENCE_DAYS[self.recurrence]
        next_due = self.due_date + timedelta(days=days_ahead)

        # copy.replace() creates a new Task with only the specified fields changed
        return replace(self, status="pending", due_date=next_due)


@dataclass
class Pet:
    name: str
    species: str  # "dog", "cat", "other"


@dataclass
class Owner:
    name: str
    available_minutes: int
    pet: Optional[Pet] = None
    tasks: List[Task] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """
        Append a Task to this owner's task list.

        Args:
            task: A fully constructed Task instance to track.
        """
        self.tasks.append(task)

    def clear_tasks(self) -> None:
        """
        Remove all tasks from this owner's task list.

        Use this to reset the task list between days or test runs.
        """
        self.tasks.clear()

    def mark_task_complete(self, title: str) -> Optional[Task]:
        """
        Find a pending task by title, mark it complete, and automatically
        add the next occurrence to the task list if it recurs.

        Returns the newly created next-occurrence Task, or None if the task
        doesn't recur or wasn't found.

        How timedelta works here (via Task.mark_complete):
          next_due = task.due_date + timedelta(days=1)  # daily
          next_due = task.due_date + timedelta(days=7)  # weekly
        """
        for task in self.tasks:
            if task.title == title and task.status == "pending":
                next_task = task.mark_complete()  # marks task.status = "done"
                if next_task is not None:
                    self.tasks.append(next_task)  # auto-add the next occurrence
                return next_task
        return None  # task not found or already done

    def filter_tasks(
        self,
        pet_name: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List["Task"]:
        """
        Return tasks matching the given pet_name and/or status.
        Pass None to skip that filter (acts as a wildcard).

        Examples:
          owner.filter_tasks(status="pending")         # all pending tasks
          owner.filter_tasks(pet_name="Mochi")         # all of Mochi's tasks
          owner.filter_tasks(pet_name="Mochi", status="done")  # Mochi's done tasks
        """
        return [
            t for t in self.tasks
            if (pet_name is None or t.pet_name == pet_name)
            and (status is None or t.status == status)
        ]


@dataclass
class ScheduledTask:
    task: Task
    start_minute: int  # minutes from midnight (e.g. 480 = 8:00 AM)
    reason: str = ""

    @property
    def end_minute(self) -> int:
        """Return the minute-from-midnight when this task finishes."""
        return self.start_minute + self.task.duration_minutes

    def start_time_str(self) -> str:
        """Return the start time as a human-readable string, e.g. '8:00 AM'."""
        return _minutes_to_time(self.start_minute)

    def end_time_str(self) -> str:
        """Return the end time as a human-readable string, e.g. '8:20 AM'."""
        return _minutes_to_time(self.end_minute)


@dataclass
class Schedule:
    owner: Owner
    scheduled_tasks: List[ScheduledTask] = field(default_factory=list)
    skipped_tasks: List[Task] = field(default_factory=list)
    conflicts: List["ConflictWarning"] = field(default_factory=list)

    @property
    def total_minutes_scheduled(self) -> int:
        """Return the sum of all scheduled task durations in minutes."""
        return sum(st.task.duration_minutes for st in self.scheduled_tasks)

    def to_rows(self) -> List[dict]:
        """
        Return scheduled tasks as a list of dicts for display in st.dataframe.

        Each dict contains: Time, Task, Duration, Priority, Recurrence, Why.
        """
        return [
            {
                "Time": f"{st.start_time_str()} – {st.end_time_str()}",
                "Task": st.task.title,
                "Duration (min)": st.task.duration_minutes,
                "Priority": st.task.priority.capitalize(),
                "Recurrence": st.task.recurrence,
                "Why": st.reason,
            }
            for st in self.scheduled_tasks
        ]

    def skipped_rows(self) -> List[dict]:
        """
        Return skipped tasks as a list of dicts for display in st.dataframe.

        Each dict contains: Task, Duration, Priority, Reason skipped.
        """
        return [
            {
                "Task": t.title,
                "Duration (min)": t.duration_minutes,
                "Priority": t.priority.capitalize(),
                "Reason skipped": "Not enough time remaining",
            }
            for t in self.skipped_tasks
        ]

    def conflict_rows(self) -> List[dict]:
        """
        Return conflict warnings as a list of dicts for display in st.dataframe.

        Each dict contains: Task A, Task B, Same pet, Pets, Overlap at, Overlap (min).
        """
        return [
            {
                "Task A": c.task_a,
                "Task B": c.task_b,
                "Same pet": c.same_pet,
                "Pets": f"{c.pet_a} / {c.pet_b}",
                "Overlap at": _minutes_to_time(c.overlap_start),
                "Overlap (min)": c.overlap_end - c.overlap_start,
            }
            for c in self.conflicts
        ]


# ── Algorithm 1: Filter tasks by pet name and/or status ──────────────────────

def filter_tasks(
    tasks: List[Task],
    pet_name: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Task]:
    """
    Return only tasks matching the given pet_name and/or status.

    Args:
        tasks:    The list of Task objects to filter.
        pet_name: If provided, only return tasks where task.pet_name matches.
        status:   If provided, only return tasks where task.status matches
                  ("pending", "done", or "skipped").

    Returns:
        A new list containing only the matching tasks. The original list
        is not modified. Passing None for either argument acts as a wildcard.

    Examples:
        filter_tasks(tasks, status="pending")              # all pending tasks
        filter_tasks(tasks, pet_name="Mochi")              # all of Mochi's tasks
        filter_tasks(tasks, pet_name="Mochi", status="done")  # Mochi's done tasks
    """
    return [
        t for t in tasks
        if (pet_name is None or t.pet_name == pet_name)
        and (status is None or t.status == status)
    ]


# ── Algorithm 1b: Sort tasks by preferred start time ─────────────────────────

def sort_by_time(tasks: List[Task]) -> List[Task]:
    """
    Return tasks sorted by preferred_start_minute ascending.

    How the lambda works:
      sorted() calls the key function on each item to get a comparison value.
      - t.preferred_start_minute is an int like 480 (8:00 AM) or None.
      - `t.preferred_start_minute or 9999` converts None → 9999 so tasks
        with no preferred time sort to the end rather than crashing.

    Example:
      tasks with preferred times [540, None, 480] → sorted as [480, 540, None]
    """
    return sorted(
        tasks,
        key=lambda t: t.preferred_start_minute if t.preferred_start_minute is not None else 9999,
    )


# ── Algorithm 2: Expand recurring tasks into multiple copies ─────────────────

def expand_recurring(tasks: List[Task], day_start_minute: int = 480) -> List[Task]:
    """
    Expand recurring tasks into multiple same-day copies before scheduling.

    Args:
        tasks:            The list of tasks to expand.
        day_start_minute: The minute-from-midnight when the day begins (default 480 = 8 AM).
                          Used as the base time when a twice_daily task has no preferred start.

    Returns:
        A new list where twice_daily tasks appear twice (offset by 8 hours),
        and all other tasks appear once. The original list is not modified.

    Recurrence rules:
        - "none" / "daily": included once, unchanged.
        - "twice_daily":    included twice — original + a copy with preferred_start_minute
                            shifted forward by 480 minutes (8 hours).
        - "weekly":         included once (next week's copy is created by mark_complete).
    """
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


# ── Algorithm 3: Conflict detection ──────────────────────────────────────────

@dataclass
class ConflictWarning:
    task_a: str
    task_b: str
    pet_a: str
    pet_b: str
    overlap_start: int   # minute when the overlap begins
    overlap_end: int     # minute when the overlap ends

    @property
    def same_pet(self) -> bool:
        """Return True if both conflicting tasks belong to the same pet."""
        return self.pet_a == self.pet_b

    def message(self) -> str:
        """
        Return a human-readable warning string instead of crashing.
        Lightweight strategy: describe the problem and let the caller decide
        what to do — the scheduler never raises an exception for conflicts.
        """
        overlap_duration = self.overlap_end - self.overlap_start
        who = (
            f"same pet ({self.pet_a})"
            if self.same_pet
            else f"different pets ({self.pet_a} and {self.pet_b})"
        )
        return (
            f"WARNING: '{self.task_a}' and '{self.task_b}' overlap by "
            f"{overlap_duration} min at {_minutes_to_time(self.overlap_start)} "
            f"[{who}]"
        )


def detect_conflicts(scheduled_tasks: List[ScheduledTask]) -> List[ConflictWarning]:
    """
    Lightweight conflict detection — returns ConflictWarning objects instead
    of raising exceptions. The scheduler stays running; callers print warnings.

    Checks every pair of scheduled tasks for overlapping time windows:
      overlap exists when:  a.start < b.end  AND  b.start < a.end
    """
    warnings = []
    for i, a in enumerate(scheduled_tasks):
        for b in scheduled_tasks[i + 1:]:
            overlap_start = max(a.start_minute, b.start_minute)
            overlap_end   = min(a.end_minute,   b.end_minute)
            if overlap_start < overlap_end:  # positive overlap = real conflict
                warnings.append(ConflictWarning(
                    task_a=a.task.title,
                    task_b=b.task.title,
                    pet_a=a.task.pet_name or "unknown",
                    pet_b=b.task.pet_name or "unknown",
                    overlap_start=overlap_start,
                    overlap_end=overlap_end,
                ))
    return warnings


# ── Algorithm 4: Main scheduling function ────────────────────────────────────

def generate_schedule(
    owner: Owner,
    tasks: List[Task],
    day_start_minute: int = 480,
    pet_name: Optional[str] = None,
) -> Schedule:
    """
    Build a daily schedule for the owner.

    Steps:
    1. Filter to only pending tasks (and optionally by pet).
    2. Expand recurring tasks into multiple copies.
    3. Sort by preferred start time first, then priority, then duration.
    4. Greedily fit tasks into available time.
    5. Detect any time conflicts in the result.
    """
    # Step 1 — only schedule pending tasks; optionally filter by pet
    filtered = filter_tasks(tasks, pet_name=pet_name, status="pending")

    # Step 2 — expand recurring tasks (e.g. twice_daily → two entries)
    expanded = expand_recurring(filtered, day_start_minute)

    day_end_minute = day_start_minute + owner.available_minutes

    # Step 3 — split into anchored (has preferred time) and floating (no preferred time)
    anchored = sorted(
        [t for t in expanded if t.preferred_start_minute is not None],
        key=lambda t: t.preferred_start_minute,
    )
    floating = sorted(
        [t for t in expanded if t.preferred_start_minute is None],
        key=lambda t: (PRIORITY_ORDER[t.priority], t.duration_minutes),
    )

    schedule = Schedule(owner=owner)

    # Step 4 — place anchored tasks at their exact preferred start times
    for task in anchored:
        start = task.preferred_start_minute
        if start >= day_start_minute and start + task.duration_minutes <= day_end_minute:
            schedule.scheduled_tasks.append(
                ScheduledTask(task=task, start_minute=start, reason="")
            )
        else:
            schedule.skipped_tasks.append(task)

    # Step 5 — fill gaps between anchored tasks with floating tasks
    occupied = sorted((st.start_minute, st.end_minute) for st in schedule.scheduled_tasks)

    for task in floating:
        gap_start = day_start_minute
        placed = False
        for occ_start, occ_end in occupied:
            if occ_start - gap_start >= task.duration_minutes:
                schedule.scheduled_tasks.append(
                    ScheduledTask(task=task, start_minute=gap_start, reason="")
                )
                occupied = sorted(occupied + [(gap_start, gap_start + task.duration_minutes)])
                placed = True
                break
            gap_start = max(gap_start, occ_end)
        if not placed:
            if day_end_minute - gap_start >= task.duration_minutes:
                schedule.scheduled_tasks.append(
                    ScheduledTask(task=task, start_minute=gap_start, reason="")
                )
                occupied = sorted(occupied + [(gap_start, gap_start + task.duration_minutes)])
            else:
                schedule.skipped_tasks.append(task)

    # Step 6 — sort by start time and assign human-readable reasons
    schedule.scheduled_tasks.sort(key=lambda st: st.start_minute)
    for idx, st in enumerate(schedule.scheduled_tasks):
        minutes_used_before = sum(s.task.duration_minutes for s in schedule.scheduled_tasks[:idx])
        st.reason = _build_reason(st.task, owner.available_minutes - minutes_used_before, st.start_minute, idx + 1)

    # Step 7 — detect conflicts in the final schedule
    schedule.conflicts = detect_conflicts(schedule.scheduled_tasks)

    return schedule


# ── Helpers ──────────────────────────────���────────────────────────────────────

def _build_reason(task: Task, remaining_before: int, start_minute: int, slot: int) -> str:
    """
    Build a plain-English explanation for why a task was placed at a given slot.

    Args:
        task:             The task being scheduled.
        remaining_before: Minutes still available before this task was placed.
        start_minute:     The minute-from-midnight when this task starts.
        slot:             The 1-based position of this task in the schedule (1st, 2nd, ...).

    Returns:
        A sentence describing the task's priority ranking, preferred time (if any),
        and how much time remained when it was scheduled.
    """
    priority_phrases = {
        "high": "ranked first due to high priority",
        "medium": "ranked after high-priority tasks due to medium priority",
        "low": "scheduled last due to low priority",
    }
    slot_label = {1: "1st", 2: "2nd", 3: "3rd"}.get(slot, f"{slot}th")
    time_str = _minutes_to_time(start_minute)

    if task.preferred_start_minute is not None:
        pref_str = _minutes_to_time(task.preferred_start_minute)
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


def _minutes_to_time(minutes: int) -> str:
    """Convert absolute minutes-from-midnight to a readable H:MM AM/PM string."""
    h, m = divmod(minutes % (24 * 60), 60)
    period = "AM" if h < 12 else "PM"
    display_h = h % 12 or 12
    return f"{display_h}:{m:02d} {period}"
