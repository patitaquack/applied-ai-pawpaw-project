import streamlit as st
# Import specific classes and the scheduling function from our backend module
from pawpal_system import Task, Pet, Owner, generate_schedule

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
st.title("🐾 PawPal+")
st.caption("Daily pet care planner")

st.divider()

# ── Owner & Pet ───────────────────────────────────────────────────────────────
st.subheader("Owner & Pet")

# Collect owner and pet info from the user using three side-by-side input fields
col1, col2, col3 = st.columns(3)
with col1:
    owner_name = st.text_input("Owner name", value="Jordan")
with col2:
    pet_name = st.text_input("Pet name", value="Mochi")
with col3:
    species = st.selectbox("Species", ["dog", "cat", "other"])

# Only create Owner and Pet objects when the user clicks Save.
# This prevents them from being recreated on every Streamlit rerun.
if st.button("Save owner & pet"):
    st.session_state.pet = Pet(name=pet_name, species=species)
    st.session_state.owner = Owner(name=owner_name, available_minutes=60, pet=st.session_state.pet)
    st.success(f"Saved {owner_name} and {pet_name}!")

# Remind the user to save if the owner object doesn't exist in session state yet
if "owner" not in st.session_state:
    st.info("Fill in owner & pet info above and click Save.")

st.divider()

# ── Tasks ─────────────────────────────────────────────────────────────────────
st.subheader("Tasks")

# Initialize the task list in session state once so it persists across reruns
if "tasks" not in st.session_state:
    st.session_state.tasks = []

# Task input fields — now includes recurrence and preferred start hour
col1, col2, col3 = st.columns(3)
with col1:
    task_title = st.text_input("Task title", value="Morning walk")
with col2:
    duration = st.number_input("Duration (min)", min_value=1, max_value=240, value=20)
with col3:
    priority = st.selectbox("Priority", ["high", "medium", "low"])

col4, col5 = st.columns(2)
with col4:
    # Recurrence controls whether the task repeats during the day
    recurrence = st.selectbox("Recurrence", ["none", "daily", "twice_daily"])
with col5:
    # Preferred start hour lets the scheduler place the task at the right time
    preferred_hour = st.number_input(
        "Preferred start hour (24h, 0 = none)", min_value=0, max_value=23, value=0
    )

# Add task appends a new dict to the session state list
# Clear all tasks resets the list to empty
add_col, clear_col = st.columns([1, 1])
with add_col:
    if st.button("Add task", use_container_width=True):
        st.session_state.tasks.append({
            "title": task_title,
            "duration_minutes": int(duration),
            "priority": priority,
            "recurrence": recurrence,
            # Store None if the user left it at 0 (meaning no preference)
            "preferred_start_minute": int(preferred_hour) * 60 if preferred_hour > 0 else None,
        })
with clear_col:
    if st.button("Clear all tasks", use_container_width=True):
        st.session_state.tasks = []

# Display current tasks as a table, or prompt the user if none have been added
if st.session_state.tasks:
    st.dataframe(st.session_state.tasks, use_container_width=True)
else:
    st.info("No tasks yet. Add one above.")

st.divider()

# ── Schedule ──────────────────────────────────────────────────────────────────
st.subheader("Generate Schedule")

# Let the user set how much time they have and when the day starts
col1, col2 = st.columns(2)
with col1:
    available_minutes = st.number_input(
        "Available time today (min)", min_value=10, max_value=480, value=60
    )
with col2:
    day_start_hour = st.number_input(
        "Day starts at (hour, 24h)", min_value=0, max_value=23, value=8
    )

if st.button("Generate schedule", type="primary", use_container_width=True):
    # Guard: owner must be saved before generating a schedule
    if "owner" not in st.session_state:
        st.warning("Please save owner & pet info first.")
    # Guard: at least one task must exist
    elif not st.session_state.tasks:
        st.warning("Add at least one task before generating a schedule.")
    else:
        # Update available_minutes on the stored owner object instead of recreating it
        st.session_state.owner.available_minutes = int(available_minutes)
        owner = st.session_state.owner

        # Convert session state task dicts into Task objects — includes new fields
        tasks = [
            Task(
                title=t["title"],
                duration_minutes=t["duration_minutes"],
                priority=t["priority"],
                pet_name=owner.pet.name,
                recurrence=t.get("recurrence", "none"),
                preferred_start_minute=t.get("preferred_start_minute"),
            )
            for t in st.session_state.tasks
        ]

        # Run the scheduling algorithm:
        # filters pending tasks → expands recurring → sorts by time+priority → fits into available time
        schedule = generate_schedule(owner, tasks, day_start_minute=day_start_hour * 60)

        # Show a summary banner with how many tasks fit and total time used
        st.success(
            f"Scheduled {len(schedule.scheduled_tasks)} task(s) "
            f"({schedule.total_minutes_scheduled} of {available_minutes} min used) "
            f"for {owner.name} and {owner.pet.name}."
        )

        # Display the full plan as a table with time slots and reasoning per task
        st.markdown(f"#### {owner.name}'s Daily Care Plan for {owner.pet.name} ({owner.pet.species.capitalize()})")
        st.dataframe(schedule.to_rows(), use_container_width=True)

        # If any tasks didn't fit, show them in a separate skipped table
        if schedule.skipped_tasks:
            st.markdown("#### Skipped")
            st.dataframe(schedule.skipped_rows(), use_container_width=True)

        # If the conflict detector found overlapping slots, warn the user
        if schedule.conflicts:
            st.warning(f"{len(schedule.conflicts)} conflict(s) detected!")
            st.dataframe(schedule.conflict_rows(), use_container_width=True)
        else:
            st.info("No scheduling conflicts detected.")
