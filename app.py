import copy
from collections import Counter
from datetime import date

import streamlit as st

from database import init_db
from logger import get_logger
from models import CATEGORIES, Task, Pet, Owner, Schedule, minutes_to_time
from notifications import (
    check_deadline_warnings, check_overdue, check_upcoming, current_day_minute,
)
from scheduler import generate_schedule, replan_schedule, generate_weekly_schedule
from suggestions import get_suggestions

_log = get_logger(__name__)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="wide")
init_db()

# ── Session state defaults ────────────────────────────────────────────────────
if "owner_name" not in st.session_state:
    st.session_state.owner_name = ""
if "available_minutes" not in st.session_state:
    st.session_state.available_minutes = 120
if "tasks" not in st.session_state:
    st.session_state.tasks = []
if "schedule" not in st.session_state:
    st.session_state.schedule = None
if "suggestions_preview" not in st.session_state:
    st.session_state.suggestions_preview = None
if "editing_idx" not in st.session_state:
    st.session_state.editing_idx = None
if "weekly_schedule" not in st.session_state:
    st.session_state.weekly_schedule = None
if "page" not in st.session_state:
    st.session_state.page = "home"
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "today"
if "pets" not in st.session_state:
    st.session_state.pets = []
if "schedule_preview" not in st.session_state:
    st.session_state.schedule_preview = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "ai_model" not in st.session_state:
    st.session_state.ai_model = "gemini-2.5-flash"

# ── Sidebar — always visible ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🐾 PawPal+")
    st.caption("Daily pet care planner")
    st.divider()
    if st.button("🏠 Home", key="sidebar_home", use_container_width=True):
        st.session_state.page = "home"
        st.session_state.active_tab = "today"
        st.rerun()
    page_labels = {
        "home": "🏠 Home",
        "daily_schedule": "📅 Daily Schedule",
        "weekly_schedule": "📅 Weekly Schedule",
    }
    current_label = page_labels.get(st.session_state.get("page", "home"), "🏠 Home")
    st.markdown(f"**Current page:** {current_label}")
    st.divider()
    st.caption("Need a fresh start? Use 🔄 Start Over anytime.")


# ── Shared helpers ────────────────────────────────────────────────────────────

def _all_pets():
    return list(st.session_state.pets)


def _pets_label() -> str:
    pets = st.session_state.pets
    if not pets:
        return "Your Pets"
    if len(pets) == 1:
        return pets[0].name
    if len(pets) == 2:
        return f"{pets[0].name} & {pets[1].name}"
    return "All Pets"


def _make_owner(available_minutes: int = None) -> Owner:
    avail = available_minutes if available_minutes is not None else st.session_state.available_minutes
    first_pet = st.session_state.pets[0] if st.session_state.pets else None
    return Owner(name=st.session_state.owner_name, available_minutes=avail, pet=first_pet)


def _render_start_over(key: str) -> None:
    if st.button("🔄 Start Over", key=key, help="Clear everything and start fresh",
                 use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()


def _render_schedule_preview(sched: Schedule, owner: Owner) -> None:
    pet_names = sorted({s.task.pet_name for s in sched.scheduled_tasks if s.task.pet_name})
    pets_str = ", ".join(pet_names) if pet_names else "—"
    st.info(
        f"**{len(sched.scheduled_tasks)}** task(s) · "
        f"**{sched.total_minutes_scheduled}** of **{owner.available_minutes}** min · "
        f"Pets: **{pets_str}**"
    )
    if sched.scheduled_tasks:
        st.dataframe(sched.to_rows(), use_container_width=True)
    else:
        st.warning("No tasks fit in the available time window.")
    if sched.conflicts:
        st.markdown(f"##### 🚨 {len(sched.conflicts)} Conflict(s)")
        for c in sched.conflicts:
            duration = c.overlap_end - c.overlap_start
            if c.same_pet:
                st.error(
                    f"**{c.task_a}** and **{c.task_b}** overlap by {duration} min "
                    f"at {minutes_to_time(c.overlap_start)} — "
                    f"**{c.pet_a}** cannot do both at once."
                )
            else:
                st.warning(
                    f"**{c.task_a}** ({c.pet_a}) and **{c.task_b}** ({c.pet_b}) overlap by "
                    f"{duration} min at {minutes_to_time(c.overlap_start)} — "
                    f"you may be responsible for both pets simultaneously."
                )
    else:
        st.success("✅ No scheduling conflicts.")
    if sched.skipped_tasks:
        with st.expander(f"⚠️ {len(sched.skipped_tasks)} task(s) skipped", expanded=False):
            st.dataframe(sched.skipped_rows(), use_container_width=True)


def _render_weekly(weekly: list, clear_key: str) -> None:
    label = _pets_label()
    title = f"{label}'s Weekly Schedule" if label not in ("Your Pets", "All Pets") else "All Pets' Weekly Schedule"
    st.markdown(f"### 📅 {title}")
    st.caption(
        "Daily tasks repeat every day. "
        "Weekly and one-time tasks appear on Day 1 (today) only."
    )
    for day in weekly:
        day_sched: Schedule = day["schedule"]
        n = len(day_sched.scheduled_tasks)
        skipped = len(day_sched.skipped_tasks)
        day_label = f"**{day['day_label']}** — {n} task(s) · {day_sched.total_minutes_scheduled} min"
        if skipped:
            day_label += f" · ⚠️ {skipped} skipped"
        with st.expander(day_label, expanded=(day["date"] == date.today())):
            if day_sched.scheduled_tasks:
                st.dataframe(day_sched.to_rows(), use_container_width=True)
            else:
                st.info("No tasks scheduled for this day.")
            if day_sched.skipped_tasks:
                st.caption("Skipped: " + ", ".join(t.title for t in day_sched.skipped_tasks))
    if st.button("Clear weekly schedule", key=clear_key):
        st.session_state.weekly_schedule = None
        st.rerun()


def _render_daily(sched: Schedule, owner: Owner) -> None:
    total_sched = len(sched.scheduled_tasks)
    done_count = sched.completed_count
    progress = done_count / total_sched if total_sched > 0 else 0
    st.progress(
        progress,
        text=f"{done_count} done / {sched.pending_count} pending / {len(sched.skipped_tasks)} skipped",
    )
    pet_names = sorted({s.task.pet_name for s in sched.scheduled_tasks if s.task.pet_name})
    pets_str = ", ".join(pet_names) if pet_names else _pets_label()
    st.success(
        f"Scheduled **{total_sched}** task(s) · "
        f"**{sched.total_minutes_scheduled}** of **{owner.available_minutes}** min used · "
        f"Owner: **{owner.name}** · Pets: **{pets_str}**"
    )
    st.markdown(f"#### {owner.name}'s Care Plan — {pets_str}")
    if sched.scheduled_tasks:
        st.dataframe(sched.to_rows(), use_container_width=True)
    if sched.skipped_tasks:
        with st.expander(f"⚠️ {len(sched.skipped_tasks)} Skipped Task(s)", expanded=False):
            st.dataframe(sched.skipped_rows(), use_container_width=True)
    if sched.conflicts:
        with st.expander(f"🚨 {len(sched.conflicts)} Conflict(s) Detected", expanded=True):
            st.dataframe(sched.conflict_rows(), use_container_width=True)
    else:
        st.success("✅ No scheduling conflicts.")


def _apply_agent_actions(actions: list) -> list:
    """Apply pending_actions from run_agent() to session state. Returns confirmation strings."""
    msgs = []
    for action in actions:
        kind = action.get("action")
        if kind == "add_tasks":
            pet_name = action["pet_name"]
            for t in action["tasks"]:
                task = dict(t)
                if isinstance(task.get("due_date"), str):
                    task["due_date"] = date.fromisoformat(task["due_date"])
                st.session_state.tasks.append(copy.copy(task))
            msgs.append(f"Added {len(action['tasks'])} tasks for {pet_name}.")
        elif kind == "set_schedule_preview":
            st.session_state.schedule_preview = action["schedule"]
            msgs.append("Schedule preview ready — go to Today's Plan to finalize.")
        else:
            _log.warning("_apply_agent_actions: unknown action '%s'", kind)
    return msgs


def _run_fallback_plan() -> tuple[str, list]:
    """
    Local fallback when Gemini quota is exhausted.
    Uses the rule-based suggestions + scheduler to build a plan without AI.
    Returns (summary_markdown, actions_list).
    """
    from suggestions import get_suggestions as _get_suggestions

    pets = st.session_state.pets
    if not pets:
        return "No pets found. Add pets in the **Pet Profile** tab first.", []

    actions = []
    all_task_dicts = []
    lines = []

    for pet in pets:
        pet_type  = pet.species if pet.species in ("dog", "cat") else "dog"
        size      = pet.size or "medium"
        age_group = pet.age_group or "adult"
        lifestyle = pet.lifestyle or ("active_dog" if pet_type == "dog" else "indoor_cat")

        suggestions = _get_suggestions(pet_type, size, age_group, lifestyle)
        tasks = [{**t, "pet_name": pet.name} for t in suggestions]
        actions.append({"action": "add_tasks", "pet_name": pet.name, "tasks": tasks})
        all_task_dicts.extend(tasks)
        lines.append(f"- **{pet.name}**: {len(tasks)} tasks ({pet_type}, {age_group})")

    owner = _make_owner()
    task_objects = []
    for td in all_task_dicts:
        d = dict(td)
        if not isinstance(d.get("due_date"), date):
            d["due_date"] = date.today()
        task_objects.append(Task(**d))

    sched = generate_schedule(owner, task_objects)
    actions.append({"action": "set_schedule_preview", "schedule": sched})

    summary = (
        "Here's your care plan (built-in planner — AI unavailable):\n\n"
        + "\n".join(lines)
        + f"\n\n**{len(sched.scheduled_tasks)}** tasks scheduled · "
        + f"**{sched.total_minutes_scheduled}** min used"
    )
    if sched.conflicts:
        summary += f" · ⚠️ {len(sched.conflicts)} conflict(s)"
    if sched.skipped_tasks:
        summary += f" · {len(sched.skipped_tasks)} skipped (not enough time)"

    return summary, actions


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: DAILY SCHEDULE
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.page == "daily_schedule":
    col_title, col_home, col_reset = st.columns([4, 1, 1])
    with col_title:
        st.title("📅 Today's Daily Plan")
    with col_home:
        if st.button("🏠 Home", key="home_daily", use_container_width=True):
            st.session_state.page = "home"
            st.session_state.active_tab = "today"
            st.rerun()
    with col_reset:
        _render_start_over("start_over_daily_page")

    if not st.session_state.schedule:
        st.info("No schedule yet. Go home and click Generate Schedule.")
    else:
        owner: Owner = _make_owner()
        sched: Schedule = st.session_state.schedule
        current_min = current_day_minute()
        flat_tasks = [s.task for s in sched.scheduled_tasks]
        for msg in check_overdue(sched.scheduled_tasks, current_min):
            st.error(msg)
        for msg in check_deadline_warnings(flat_tasks, current_min):
            st.warning(msg)
        for msg in check_upcoming(sched.scheduled_tasks, current_min):
            st.info(msg)
        _render_daily(sched, owner)
        st.divider()
        st.markdown("#### Replan")
        rp_col1, rp_col2, rp_col3 = st.columns(3)
        with rp_col1:
            new_minutes = st.number_input(
                "Available time (min)", min_value=10, max_value=720, value=owner.available_minutes,
            )
        with rp_col2:
            new_start = st.number_input(
                "Day starts at (24h hour)", min_value=0, max_value=23, value=8,
            )
        with rp_col3:
            st.markdown("&nbsp;", unsafe_allow_html=True)
            if st.button("Replan", use_container_width=True):
                try:
                    tasks = [Task(**t) for t in st.session_state.tasks]
                    _log.info("Replan (daily page) | owner=%s new_minutes=%d", owner.name, int(new_minutes))
                    st.session_state.schedule = replan_schedule(
                        owner, tasks, int(new_minutes), new_start * 60
                    )
                    st.rerun()
                except Exception as exc:
                    _log.error("Replan (daily page) failed: %s", exc, exc_info=True)
                    st.error(f"Could not replan: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: WEEKLY SCHEDULE
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.page == "weekly_schedule":
    col_title, col_home, col_reset = st.columns([4, 1, 1])
    with col_title:
        st.title("📅 Weekly Schedule")
    with col_home:
        if st.button("🏠 Home", key="home_weekly", use_container_width=True):
            st.session_state.page = "home"
            st.session_state.active_tab = "today"
            st.rerun()
    with col_reset:
        _render_start_over("start_over_weekly_page")

    if not st.session_state.weekly_schedule:
        st.info("No weekly schedule yet. Go home and click Create Weekly Schedule.")
    else:
        _render_weekly(st.session_state.weekly_schedule, clear_key="clear_weekly_page")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: HOME
# ─────────────────────────────────────────────────────────────────────────────
else:
    st.title("🐾 PawPal+")
    st.caption("Production-grade daily pet care planner")

    setup_complete = (
        bool(st.session_state.get("owner_name"))
        and len(st.session_state.get("pets", [])) > 0
    )

    if st.session_state.schedule:
        current_min = current_day_minute()
        sched: Schedule = st.session_state.schedule
        flat_tasks = [s.task for s in sched.scheduled_tasks]
        for msg in check_overdue(sched.scheduled_tasks, current_min):
            st.error(msg)
        for msg in check_deadline_warnings(flat_tasks, current_min):
            st.warning(msg)
        for msg in check_upcoming(sched.scheduled_tasks, current_min):
            st.info(msg)

    # ── Tab navigation row ────────────────────────────────────────────────────
    TAB_DEFS = [
        ("today",         "📅 Today's Plan"),
        ("add_tasks",     "➕ Add Tasks"),
        ("pet_profile",   "🐾 Pet Profile"),
        ("notifications", "🔔 Notifications"),
        ("weekly",        "📊 Weekly Summary"),
        ("ai_planner",    "🤖 AI Planner"),
    ]
    nav_cols = st.columns(len(TAB_DEFS))
    for col, (tab_key, tab_label) in zip(nav_cols, TAB_DEFS):
        with col:
            btn_type = "primary" if st.session_state.active_tab == tab_key else "secondary"
            if st.button(tab_label, key=f"nav_{tab_key}", use_container_width=True, type=btn_type):
                st.session_state.active_tab = tab_key
                st.rerun()

    st.divider()

    active = st.session_state.active_tab

    # ─────────────────────────────────────────────────────────────────────────
    # TAB: TODAY'S PLAN
    # ─────────────────────────────────────────────────────────────────────────
    if active == "today":
        hcol, rcol = st.columns([5, 1])
        with hcol:
            st.subheader("Today's Schedule")
        with rcol:
            _render_start_over("start_over_today")

        if not setup_complete:
            st.info("Complete setup in the **🐾 Pet Profile** tab — add your name and at least one pet.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                available_minutes = st.number_input(
                    "Available time today (min)", min_value=10, max_value=720,
                    value=st.session_state.available_minutes,
                )
            with col2:
                day_start_hour = st.number_input(
                    "Day starts at (24h hour)", min_value=0, max_value=23, value=8,
                )

            owner = _make_owner(int(available_minutes))

            all_pets = _all_pets()
            if all_pets:
                st.caption("Scheduling for: **" + ", ".join(p.name for p in all_pets) + "**")

            col_gen, col_replan = st.columns(2)
            with col_gen:
                if st.button("🔍 Preview Full Schedule", type="primary", use_container_width=True):
                    if not st.session_state.tasks:
                        st.warning("Add tasks in the **Add Tasks** tab first.")
                    else:
                        try:
                            tasks = [Task(**t) for t in st.session_state.tasks]
                            _log.info("Preview schedule | owner=%s tasks=%d", owner.name, len(tasks))
                            st.session_state.schedule_preview = generate_schedule(
                                owner, tasks, day_start_minute=day_start_hour * 60
                            )
                        except Exception as exc:
                            _log.error("Preview schedule failed: %s", exc, exc_info=True)
                            st.error(f"Could not generate schedule: {exc}")

            with col_replan:
                if st.button("Replan (time changed)", use_container_width=True):
                    if st.session_state.schedule and st.session_state.tasks:
                        try:
                            tasks = [Task(**t) for t in st.session_state.tasks]
                            _log.info("Replan | owner=%s new_minutes=%d", owner.name, int(available_minutes))
                            st.session_state.schedule = replan_schedule(
                                owner, tasks, int(available_minutes), day_start_hour * 60
                            )
                            st.session_state.page = "daily_schedule"
                            st.rerun()
                        except Exception as exc:
                            _log.error("Replan failed: %s", exc, exc_info=True)
                            st.error(f"Could not replan schedule: {exc}")

            if st.session_state.schedule_preview:
                st.divider()
                st.markdown("#### 🔍 Schedule Preview")
                _render_schedule_preview(st.session_state.schedule_preview, owner)
                st.divider()
                col_fin, col_cancel = st.columns(2)
                with col_fin:
                    if st.button("✅ Finalize & View Schedule", type="primary", use_container_width=True):
                        st.session_state.schedule = st.session_state.schedule_preview
                        st.session_state.schedule_preview = None
                        st.session_state.page = "daily_schedule"
                        st.rerun()
                with col_cancel:
                    if st.button("✖ Cancel preview", use_container_width=True):
                        st.session_state.schedule_preview = None
                        st.rerun()

            if st.session_state.schedule:
                st.divider()
                if st.button("📅 View daily schedule", use_container_width=True):
                    st.session_state.page = "daily_schedule"
                    st.rerun()

            if st.session_state.weekly_schedule:
                st.divider()
                if st.button("📅 View weekly schedule", use_container_width=True):
                    st.session_state.page = "weekly_schedule"
                    st.rerun()

    # ─────────────────────────────────────────────────────────────────────────
    # TAB: ADD TASKS
    # ─────────────────────────────────────────────────────────────────────────
    elif active == "add_tasks":
        hcol, rcol = st.columns([5, 1])
        with hcol:
            st.subheader("Add Tasks")
        with rcol:
            _render_start_over("start_over_add_tasks")

        if not setup_complete:
            st.info("Complete setup in the **🐾 Pet Profile** tab — add your name and at least one pet.")
        else:
            pet_name_for_task = st.session_state.pets[0].name

            # ── Quick Suggestions ─────────────────────────────────────────────
            with st.expander(f"✨ {_pets_label()}'s Schedule Suggestions", expanded=True):
                st.caption("Select a saved pet to auto-fill suggestions, or choose Custom for manual settings.")

                _qs_pets = _all_pets()
                _qs_pet_names = [p.name for p in _qs_pets]
                _qs_options = _qs_pet_names + ["⚙️ Custom settings"]

                qs_selected = st.selectbox(
                    "Generate suggestions for:",
                    _qs_options,
                    key="qs_selected_pet",
                )

                age_map = {"puppy / kitten": "puppy", "adult": "adult", "senior": "senior"}

                if qs_selected != "⚙️ Custom settings":
                    qs_pet_obj = next((p for p in _qs_pets if p.name == qs_selected), None)
                    if qs_pet_obj:
                        qs_pet_type = qs_pet_obj.species if qs_pet_obj.species in ("dog", "cat") else "dog"
                        qs_size = qs_pet_obj.size or "medium"
                        qs_age = qs_pet_obj.age_group or "adult"
                        qs_lifestyle = qs_pet_obj.lifestyle or (
                            "active_dog" if qs_pet_type == "dog" else "indoor_cat"
                        )
                        profile_tags = [qs_pet_type, qs_size, qs_age]
                        if qs_pet_obj.health_conditions:
                            profile_tags.append(qs_pet_obj.health_conditions)
                        st.caption("Profile: **" + " · ".join(profile_tags) + "**")
                        if st.button(f"Preview suggestions for {qs_pet_obj.name}", key="btn_preview"):
                            st.session_state.suggestions_preview = get_suggestions(
                                qs_pet_type, qs_size, qs_age, qs_lifestyle
                            )
                else:
                    qs_col1, qs_col2 = st.columns(2)
                    with qs_col1:
                        qs_pet_type = st.selectbox("Pet type", ["dog", "cat"], key="qs_pet_type")
                        qs_age_label = st.selectbox(
                            "Age group", ["puppy / kitten", "adult", "senior"], key="qs_age"
                        )
                    with qs_col2:
                        if qs_pet_type == "dog":
                            qs_size = st.selectbox("Dog size", ["small", "medium", "large"], key="qs_size")
                            qs_lifestyle = st.selectbox(
                                "Lifestyle", ["active_dog", "low_energy_dog"],
                                format_func=lambda x: "Active dog" if x == "active_dog" else "Low-energy dog",
                                key="qs_lifestyle",
                            )
                        else:
                            qs_size = "medium"
                            qs_lifestyle = "indoor_cat"
                            st.info("Indoor / enrichment tasks will be suggested for cats.")
                    qs_age = age_map[qs_age_label]
                    if st.button("Preview suggestions", key="btn_preview"):
                        st.session_state.suggestions_preview = get_suggestions(
                            qs_pet_type, qs_size, qs_age, qs_lifestyle
                        )

                if st.session_state.suggestions_preview:
                    preview = st.session_state.suggestions_preview
                    st.dataframe(
                        [
                            {
                                "Task": t["title"],
                                "Category": t["category"],
                                "Priority": t["priority"],
                                "Duration (min)": t["duration_minutes"],
                                "Recurrence": t["recurrence"],
                                "Preferred time": (
                                    minutes_to_time(t["preferred_start_minute"])
                                    if t["preferred_start_minute"] else "—"
                                ),
                                "Notes": t["notes"] or "—",
                            }
                            for t in preview
                        ],
                        use_container_width=True,
                    )
                    qs_all_pets = _all_pets()
                    qs_pet_options = (
                        ["All pets"] + [p.name for p in qs_all_pets]
                        if len(qs_all_pets) > 1
                        else [p.name for p in qs_all_pets] if qs_all_pets
                        else [pet_name_for_task]
                    )
                    qs_pet_target = st.selectbox(
                        "Assign these tasks to which pet?",
                        qs_pet_options,
                        key="qs_pet_target",
                    )
                    if st.button(
                        f"Add {len(preview)} suggestions to task list",
                        type="primary",
                        key="btn_add_suggestions",
                    ):
                        targets = (
                            [p.name for p in qs_all_pets]
                            if qs_pet_target == "All pets"
                            else [qs_pet_target]
                        )
                        for pet_name in targets:
                            for t in preview:
                                st.session_state.tasks.append({**copy.copy(t), "pet_name": pet_name})
                        st.session_state.suggestions_preview = None
                        total = len(preview) * len(targets)
                        label = "all pets" if qs_pet_target == "All pets" else qs_pet_target
                        st.toast(f"Added {total} tasks for {label}!")
                        st.rerun()

            st.divider()

            # ── Manual task form ──────────────────────────────────────────────
            with st.expander("➕ Add a task manually", expanded=False):
                with st.form("add_task_form", clear_on_submit=True):
                    _form_pets = _all_pets()
                    _pet_options = (
                        ["All pets"] + [p.name for p in _form_pets]
                        if len(_form_pets) > 1
                        else [p.name for p in _form_pets] if _form_pets
                        else [pet_name_for_task]
                    )
                    form_pet_name = st.selectbox("Which pet is this task for?", _pet_options)

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        task_title = st.text_input("Task title")
                    with col2:
                        duration = st.number_input("Duration (min)", min_value=1, max_value=240, value=20)
                    with col3:
                        priority = st.selectbox("Priority", ["high", "medium", "low"])

                    col4, col5, col6 = st.columns(3)
                    with col4:
                        category = st.selectbox("Category", sorted(CATEGORIES))
                    with col5:
                        recurrence = st.selectbox("Recurrence", ["none", "daily", "twice_daily", "weekly"])
                    with col6:
                        preferred_hour = st.number_input(
                            "Preferred start hour (0 = none)", min_value=0, max_value=23, value=0
                        )

                    col7, col8 = st.columns(2)
                    with col7:
                        deadline_hour = st.number_input(
                            "Deadline hour (0 = none)", min_value=0, max_value=23, value=0
                        )
                    with col8:
                        medication_dose = st.text_input("Medication dose (if applicable)")

                    notes = st.text_area("Notes / Instructions", height=80)

                    if st.form_submit_button("Add Task", use_container_width=True) and task_title:
                        targets = (
                            [p.name for p in _form_pets]
                            if form_pet_name == "All pets"
                            else [form_pet_name]
                        )
                        base = {
                            "title": task_title,
                            "duration_minutes": int(duration),
                            "priority": priority,
                            "category": category,
                            "notes": notes,
                            "status": "pending",
                            "recurrence": recurrence,
                            "preferred_start_minute": int(preferred_hour) * 60 if preferred_hour > 0 else None,
                            "deadline_minute": int(deadline_hour) * 60 if deadline_hour > 0 else None,
                            "medication_dose": medication_dose,
                            "instructions": notes,
                            "due_date": date.today(),
                        }
                        for pet_name in targets:
                            st.session_state.tasks.append({**base, "pet_name": pet_name})
                        label = "all pets" if form_pet_name == "All pets" else form_pet_name
                        st.toast(f"Added '{task_title}' for {label}")
                        st.rerun()

            st.divider()

            # ── Task queue with per-task edit / delete ────────────────────────
            st.markdown(f"#### Task Queue ({len(st.session_state.tasks)} task(s))")

            editing_idx = st.session_state.editing_idx
            if editing_idx is not None and editing_idx < len(st.session_state.tasks):
                t = st.session_state.tasks[editing_idx]
                st.info(f"Editing: **{t['title']}**")
                with st.form("edit_task_form"):
                    ec1, ec2, ec3 = st.columns(3)
                    with ec1:
                        e_title = st.text_input("Title", value=t["title"])
                    with ec2:
                        e_duration = st.number_input(
                            "Duration (min)", min_value=1, max_value=240, value=t["duration_minutes"]
                        )
                    with ec3:
                        e_priority = st.selectbox(
                            "Priority", ["high", "medium", "low"],
                            index=["high", "medium", "low"].index(t["priority"]),
                        )
                    ec4, ec5, ec6 = st.columns(3)
                    with ec4:
                        e_category = st.selectbox(
                            "Category", sorted(CATEGORIES),
                            index=sorted(CATEGORIES).index(t["category"]),
                        )
                    with ec5:
                        e_recurrence = st.selectbox(
                            "Recurrence", ["none", "daily", "twice_daily", "weekly"],
                            index=["none", "daily", "twice_daily", "weekly"].index(t["recurrence"]),
                        )
                    with ec6:
                        current_pref_hour = (t["preferred_start_minute"] or 0) // 60
                        e_pref_hour = st.number_input(
                            "Preferred start hour (0 = none)", min_value=0, max_value=23,
                            value=current_pref_hour,
                        )
                    e_notes = st.text_area("Notes", value=t.get("notes", ""), height=60)

                    save_btn, cancel_btn = st.columns(2)
                    with save_btn:
                        saved = st.form_submit_button("Save changes", use_container_width=True)
                    with cancel_btn:
                        cancelled = st.form_submit_button("Cancel", use_container_width=True)

                    if saved:
                        st.session_state.tasks[editing_idx] = {
                            **t,
                            "title": e_title,
                            "duration_minutes": int(e_duration),
                            "priority": e_priority,
                            "category": e_category,
                            "recurrence": e_recurrence,
                            "preferred_start_minute": int(e_pref_hour) * 60 if e_pref_hour > 0 else None,
                            "notes": e_notes,
                            "instructions": e_notes,
                        }
                        st.session_state.editing_idx = None
                        st.rerun()
                    if cancelled:
                        st.session_state.editing_idx = None
                        st.rerun()

            if st.session_state.tasks:
                for i, t in enumerate(st.session_state.tasks):
                    pref = (
                        minutes_to_time(t["preferred_start_minute"])
                        if t["preferred_start_minute"] else "—"
                    )
                    row_info, row_edit, row_del = st.columns([7, 1, 1])
                    with row_info:
                        pet_tag = f" 🐾 {t.get('pet_name', '—')} &nbsp;·&nbsp;" if t.get("pet_name") else ""
                        st.markdown(
                            f"**{i + 1}. {t['title']}** &nbsp;·&nbsp;"
                            f"{pet_tag} "
                            f"{t['category']} &nbsp;·&nbsp; {t['priority']} priority &nbsp;·&nbsp; "
                            f"{t['duration_minutes']} min &nbsp;·&nbsp; {t['recurrence']} &nbsp;·&nbsp; ⏰ {pref}"
                        )
                    with row_edit:
                        if st.button("✏️", key=f"edit_{i}", help="Edit this task"):
                            st.session_state.editing_idx = i
                            st.rerun()
                    with row_del:
                        if st.button("🗑️", key=f"del_{i}", help="Delete this task"):
                            st.session_state.tasks.pop(i)
                            if st.session_state.editing_idx == i:
                                st.session_state.editing_idx = None
                            st.rerun()
                st.divider()
                col_clear, col_weekly = st.columns(2)
                with col_clear:
                    if st.button("Clear all tasks", use_container_width=True):
                        st.session_state.tasks = []
                        st.session_state.editing_idx = None
                        st.session_state.weekly_schedule = None
                        st.rerun()
                with col_weekly:
                    if st.button("📅 Create weekly schedule", type="primary", use_container_width=True):
                        try:
                            _tasks = [Task(**t) for t in st.session_state.tasks]
                            _log.info("Weekly schedule | owner=%s tasks=%d", st.session_state.owner_name, len(_tasks))
                            st.session_state.weekly_schedule = generate_weekly_schedule(
                                _make_owner(720), _tasks, day_start_minute=480
                            )
                            st.session_state.page = "weekly_schedule"
                            st.rerun()
                        except Exception as exc:
                            _log.error("Weekly schedule failed: %s", exc, exc_info=True)
                            st.error(f"Could not create weekly schedule: {exc}")
            else:
                st.info("No tasks queued yet. Use Quick Suggestions or add one manually.")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB: PET PROFILE
    # ─────────────────────────────────────────────────────────────────────────
    elif active == "pet_profile":
        hcol, rcol = st.columns([5, 1])
        with hcol:
            st.subheader("Owner & Pet Profile")
        with rcol:
            _render_start_over("start_over_pet_profile")

        # ── Owner ─────────────────────────────────────────────────────────────
        with st.form("owner_form"):
            st.markdown("**Owner**")
            oc1, oc2 = st.columns(2)
            with oc1:
                owner_name = st.text_input(
                    "Owner name",
                    value=st.session_state.owner_name,
                    placeholder="e.g. Jordan",
                )
            with oc2:
                avail_minutes = st.number_input(
                    "Daily available time (min)",
                    min_value=10, max_value=720,
                    value=st.session_state.available_minutes,
                )
            if st.form_submit_button("Save Owner", use_container_width=True):
                if not owner_name.strip():
                    st.warning("Enter an owner name.")
                else:
                    st.session_state.owner_name = owner_name.strip()
                    st.session_state.available_minutes = int(avail_minutes)
                    st.toast(f"Owner saved: {owner_name.strip()}")
                    st.rerun()

        if st.session_state.owner_name:
            st.caption(
                f"Owner: **{st.session_state.owner_name}** · "
                f"{st.session_state.available_minutes} min/day"
            )

        st.divider()

        # ── Add a pet ─────────────────────────────────────────────────────────
        st.markdown("#### Add a Pet")
        if not st.session_state.owner_name:
            st.info("Please save the owner information above first.")
        else:
            with st.form("add_pet_profile_form", clear_on_submit=True):
                pc1, pc2 = st.columns(2)
                with pc1:
                    ap_name = st.text_input("Pet name", placeholder="e.g. Mochi")
                    ap_species = st.selectbox("Species", ["dog", "cat", "other"])
                    ap_age_group = st.selectbox(
                        "Age group", ["puppy / kitten", "adult", "senior"]
                    )
                    ap_age_years = st.number_input(
                        "Age (years)", min_value=0.0, max_value=30.0, value=2.0, step=0.5
                    )
                with pc2:
                    if ap_species == "dog":
                        ap_size = st.selectbox("Size", ["small", "medium", "large"])
                        ap_lifestyle = st.selectbox(
                            "Lifestyle",
                            ["active_dog", "low_energy_dog"],
                            format_func=lambda x: "Active dog" if x == "active_dog" else "Low-energy dog",
                        )
                    else:
                        ap_size = "medium"
                        ap_lifestyle = "indoor_cat"
                        st.caption("Size and lifestyle default to indoor cat settings.")
                    ap_weight = st.number_input(
                        "Weight (kg)", min_value=0.1, max_value=100.0, value=5.0, step=0.1
                    )
                    ap_health = st.text_input("Health notes (optional)")

                if st.form_submit_button("Add Pet Profile", use_container_width=True):
                    if not ap_name.strip():
                        st.warning("Enter a pet name.")
                    else:
                        age_map_pet = {"puppy / kitten": "puppy", "adult": "adult", "senior": "senior"}
                        new_pet = Pet(
                            name=ap_name.strip(),
                            species=ap_species,
                            age_years=ap_age_years,
                            weight_kg=ap_weight,
                            health_conditions=ap_health,
                            activity_level="high" if ap_lifestyle == "active_dog" else "moderate",
                            size=ap_size,
                            age_group=age_map_pet[ap_age_group],
                            lifestyle=ap_lifestyle,
                        )
                        st.session_state.pets.append(new_pet)
                        msg = f"Added {ap_name.strip()}!"
                        if new_pet.is_senior:
                            msg += " 🏥 Senior — consider adding medication reminders."
                        st.toast(msg)
                        st.rerun()

        # ── Saved pets ────────────────────────────────────────────────────────
        if st.session_state.pets:
            st.divider()
            st.markdown(f"#### {_pets_label()} ({len(st.session_state.pets)} pet(s))")
            for i, p in enumerate(st.session_state.pets):
                info_col, del_col = st.columns([9, 1])
                with info_col:
                    tags = [p.species.capitalize()]
                    if p.size:
                        tags.append(p.size)
                    if p.age_group:
                        tags.append(p.age_group)
                    if p.activity_level and p.activity_level != "moderate":
                        tags.append(p.activity_level + " activity")
                    detail = " · ".join(tags) + f" · {p.age_years} yrs"
                    if p.is_senior:
                        detail += " · 🏥 senior"
                    if p.health_conditions:
                        detail += f" · {p.health_conditions}"
                    st.markdown(f"**🐾 {p.name}** — {detail}")
                with del_col:
                    if st.button("🗑️", key=f"del_pet_{i}", help=f"Remove {p.name}"):
                        removed_name = p.name
                        st.session_state.pets.pop(i)
                        # Remove all tasks for this pet
                        st.session_state.tasks = [
                            t for t in st.session_state.tasks
                            if t.get("pet_name") != removed_name
                        ]
                        # Clear schedules that referenced this pet
                        st.session_state.schedule_preview = None
                        st.session_state.weekly_schedule = None
                        if st.session_state.schedule:
                            sched_pets = {
                                s.task.pet_name
                                for s in st.session_state.schedule.scheduled_tasks
                            }
                            if removed_name in sched_pets:
                                st.session_state.schedule = None
                        st.rerun()
        else:
            st.info("No pets added yet. Add your first pet above.")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB: NOTIFICATIONS
    # ─────────────────────────────────────────────────────────────────────────
    elif active == "notifications":
        hcol, rcol = st.columns([5, 1])
        with hcol:
            st.subheader("Notifications & Alerts")
        with rcol:
            _render_start_over("start_over_notifications")

        if st.session_state.schedule is None:
            st.info("Generate a schedule first to see notifications.")
        else:
            current_min = current_day_minute()
            st.caption(f"Current time: **{minutes_to_time(current_min)}**")
            sched: Schedule = st.session_state.schedule
            flat_tasks = [s.task for s in sched.scheduled_tasks]
            overdue = check_overdue(sched.scheduled_tasks, current_min)
            deadline_warns = check_deadline_warnings(flat_tasks, current_min)
            upcoming_60 = check_upcoming(sched.scheduled_tasks, current_min, within_minutes=60)
            if overdue:
                st.markdown("#### Overdue Tasks")
                for msg in overdue:
                    st.error(msg)
            if deadline_warns:
                st.markdown("#### Deadline Warnings")
                for msg in deadline_warns:
                    st.warning(msg)
            if upcoming_60:
                st.markdown("#### Coming Up (next 60 min)")
                for msg in upcoming_60:
                    st.info(msg)
            if not overdue and not deadline_warns and not upcoming_60:
                st.success("✅ No active alerts — you're on track!")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB: WEEKLY SUMMARY
    # ─────────────────────────────────────────────────────────────────────────
    elif active == "weekly":
        hcol, rcol = st.columns([5, 1])
        with hcol:
            st.subheader("Weekly Summary")
        with rcol:
            _render_start_over("start_over_weekly")

        if not setup_complete:
            st.info("Complete setup in the **🐾 Pet Profile** tab — add your name and at least one pet.")
        elif st.session_state.schedule is None:
            st.info("Generate a schedule to start tracking.")
        else:
            sched: Schedule = st.session_state.schedule
            owner: Owner = _make_owner()
            done_items = [s for s in sched.scheduled_tasks if s.task.status == "done"]
            pending_items = [s for s in sched.scheduled_tasks if s.task.status == "pending"]
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Scheduled", len(sched.scheduled_tasks))
            col2.metric("Done", len(done_items))
            col3.metric("Pending", len(pending_items))
            col4.metric("Skipped", len(sched.skipped_tasks))
            st.markdown("#### Time Usage Today")
            used = sched.total_minutes_scheduled
            available = owner.available_minutes
            st.progress(
                min(used / available, 1.0),
                text=f"{used} of {available} min used",
            )
            st.markdown("#### Tasks by Category")
            cat_counts = Counter(s.task.category for s in sched.scheduled_tasks)
            if cat_counts:
                st.bar_chart(cat_counts)
            if sched.skipped_tasks:
                st.markdown("#### Skipped Tasks & Suggestions")
                st.dataframe(sched.skipped_rows(), use_container_width=True)

    # ─────────────────────────────────────────────────────────────────────────
    # TAB: AI PLANNER
    # ─────────────────────────────────────────────────────────────────────────
    elif active == "ai_planner":
        hcol, rcol = st.columns([5, 1])
        with hcol:
            st.subheader("🤖 AI Planner")
        with rcol:
            _render_start_over("start_over_ai_planner")

        if not setup_complete:
            st.info("Complete setup in the **🐾 Pet Profile** tab first — add your name and at least one pet.")
        else:
            import os as _os
            from agent import get_available_models

            _ai_key_for_models = (
                st.secrets.get("GEMINI_API_KEY", "")
                or _os.environ.get("GEMINI_API_KEY", "")
            )
            _live_models = get_available_models(_ai_key_for_models)

            # Auto-correct stored model if it's no longer available
            if st.session_state.ai_model not in _live_models:
                st.session_state.ai_model = next(iter(_live_models))

            # ── Settings row ──────────────────────────────────────────────────
            cfg_col, fallback_col = st.columns([3, 1])
            with cfg_col:
                st.session_state.ai_model = st.selectbox(
                    "Gemini model",
                    options=list(_live_models.keys()),
                    format_func=lambda k: _live_models[k],
                    index=list(_live_models.keys()).index(st.session_state.ai_model),
                    key="ai_model_select",
                    label_visibility="collapsed",
                )
            with fallback_col:
                if st.button("⚙️ Built-in Planner", use_container_width=True,
                             help="Generate a plan locally without using the AI API"):
                    fallback_text, fallback_actions = _run_fallback_plan()
                    if fallback_actions:
                        _apply_agent_actions(fallback_actions)
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": fallback_text}
                    )
                    st.rerun()

            st.caption(
                "Ask me to plan your day, generate tasks for your pets, or build a schedule. "
                "Try: *\"Plan my day for all my pets\"*"
            )

            # ── Chat history display ──────────────────────────────────────────
            for msg in st.session_state.chat_history:
                role = msg["role"]
                content = msg["content"]
                if role == "user" and isinstance(content, str):
                    with st.chat_message("user"):
                        st.markdown(content)
                elif role == "assistant" and isinstance(content, str):
                    with st.chat_message("assistant"):
                        st.markdown(content)

            # ── Schedule preview action bar ───────────────────────────────────
            if st.session_state.schedule_preview:
                st.divider()
                st.markdown("#### 🔍 Schedule Preview Ready")
                _render_schedule_preview(st.session_state.schedule_preview, _make_owner())
                col_fin, col_cancel = st.columns(2)
                with col_fin:
                    if st.button("✅ Finalize Schedule", type="primary",
                                 use_container_width=True, key="ai_finalize"):
                        st.session_state.schedule = st.session_state.schedule_preview
                        st.session_state.schedule_preview = None
                        st.session_state.page = "daily_schedule"
                        st.rerun()
                with col_cancel:
                    if st.button("✖ Discard preview", use_container_width=True, key="ai_cancel"):
                        st.session_state.schedule_preview = None
                        st.rerun()

            # ── Chat input ────────────────────────────────────────────────────
            user_input = st.chat_input("Ask PawPal+ AI…")

            if user_input:
                import os
                from agent import run_agent

                # Resolve API key: Streamlit secrets → env var
                _api_key = st.secrets.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")

                ctx = {
                    "owner_name":        st.session_state.owner_name,
                    "available_minutes": st.session_state.available_minutes,
                    "pets":              list(st.session_state.pets),
                    "tasks":             list(st.session_state.tasks),
                    "_cached":           {},
                    "pending_actions":   [],
                }

                with st.spinner(f"PawPal+ AI thinking ({st.session_state.ai_model})…"):
                    result = run_agent(
                        user_message=user_input,
                        context=ctx,
                        chat_history=list(st.session_state.chat_history),
                        api_key=_api_key,
                        model=st.session_state.ai_model,
                    )

                # Always append the user message
                st.session_state.chat_history.append(
                    {"role": "user", "content": user_input}
                )

                if result["final_answer"]:
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": result["final_answer"]}
                    )

                # Apply session state mutations
                if result.get("pending_actions"):
                    confirmations = _apply_agent_actions(result["pending_actions"])
                    for msg in confirmations:
                        st.toast(msg)

                # On quota error, auto-run the fallback so the user isn't stuck
                if result.get("error") == "quota_exceeded":
                    fallback_text, fallback_actions = _run_fallback_plan()
                    if fallback_actions:
                        _apply_agent_actions(fallback_actions)
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": fallback_text}
                    )
                    _log.info("fallback plan triggered after quota_exceeded")

                st.rerun()

            # ── Clear chat ────────────────────────────────────────────────────
            if st.session_state.chat_history:
                if st.button("🗑️ Clear conversation", key="clear_chat"):
                    st.session_state.chat_history = []
                    st.rerun()
