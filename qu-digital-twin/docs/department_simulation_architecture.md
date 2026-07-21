# Department Digital Twin — Simulation Architecture v2

Scope: Enrollment & Demand Forecasting, Faculty & Staffing, Physical Space & Resources,
Org Structure & Curriculum Design, Accreditation & Compliance. This document is the
design to review before anything gets built — nothing here is implemented yet.

## 1. Core concept: State + Intervention = New State

Everything in this system is one pattern, applied five times:

```
CURRENT STATE  +  INTERVENTION  ->  CANDIDATE NEW STATE  ->  re-run affected engines  ->  DIFF + VISUALS
```

This is exactly what M5's `run_scenario()` already does for seat capacity and term
offerings — this version generalizes it so "state" isn't just the course graph, it's
five independent data domains, and "intervention" isn't just a capacity tweak, it's
any of the moves listed below (add, remove, propose, adjust, split, merge...).

A state is never mutated in place. Every intervention produces a *new* state object;
the old one stays around for comparison. You can accept a new state as the baseline,
discard it, or save it as a named scenario to compare against others later.

## 2. Subsystem classification (5 layers)

| Layer | Role | Analogous to |
|---|---|---|
| L1 — State Data Layer | The five data files that together define "how the department is right now" | `courses.json` today |
| L2 — Domain Engines | One engine per category below; pure functions, state in → analysis out | `rule_engine.py`, `simulation.py` |
| L3 — Intervention Layer | Structured "moves" that transform one state into another | `scenarios.py`'s `apply_modification()`, generalized |
| L4 — Frontend / State Manager | Where you load, edit, and swap the state files, and build interventions via forms | new — see §6 |
| L5 — Visualization / Output Layer | Interactive Plotly views per engine + a baseline-vs-scenario comparison view | replaces the static matplotlib charts |

## 3. Data files needed now

All five are independent and swappable — the mock version ships by default, and
uploading a real file through the frontend replaces it with zero code changes,
exactly like `courses.json` works today.

**`courses.json` (extends the existing file)** — needs three new fields added to
every course:
- `"description": str` — required for the new-elective feasibility engine (§5) to
  compare a proposed course against existing ones.
- `"requires_room_type": "lecture" | "lab" | "seminar"` — which room type a section
  needs (see §5.1, the resource requirement model).
- `"equipment_needed": list[str]` — e.g. `["gpu_workstations"]` for a course like
  Machine Learning, `[]` for most gen-ed courses.

Everything else about this file stays as-is.

**`faculty.json` (new)**
```json
{
  "F001": {
    "name": "Dr. A. Al-Sulaiti",
    "rank": "assistant_professor",   // lecturer | assistant | associate | full | adjunct
    "fte": 1.0,                      // adjuncts might be 0.25-0.5
    "max_courses_per_term": 3,
    "qualified_courses": ["CMPS151", "CMPS251", "CMPS303"],
    "specializations": ["algorithms", "databases"],
    "status": "active",              // active | on_leave | sabbatical
    "annual_salary_qar": 240000
  }
}
```

**`rooms.json` (new)**
```json
{
  "ROOM_ENG_A101": {
    "building": "Engineering Building",
    "capacity": 40,
    "room_type": "lecture",          // lecture | lab | seminar
    "equipment": ["projector"],
    "operating_cost_per_term_qar": 8000
  },
  "ROOM_ENG_LAB2": {
    "building": "Engineering Building",
    "capacity": 24,
    "room_type": "lab",
    "equipment": ["gpu_workstations", "linux_images"],
    "operating_cost_per_term_qar": 15000
  }
}
```

**`demand_history.json` (new)** — the enrollment track record the forecasting and
feasibility engines both read from:
```json
{
  "CMPS303": {
    "2022_fall": {"enrolled": 38, "capacity": 35, "pass_rate": 0.82, "waitlisted": 5},
    "2023_fall": {"enrolled": 40, "capacity": 35, "pass_rate": 0.79, "waitlisted": 8},
    "2024_fall": {"enrolled": 42, "capacity": 35, "pass_rate": 0.81, "waitlisted": 10}
  }
}
```

**`accreditation_rules.json` (new)**
```json
{
  "min_credit_hours_by_category": {"core_curriculum": 33, "college": 21, "major_core": 49, "major_elective": 12, "major_supporting": 5},
  "max_student_faculty_ratio": 25,
  "max_class_size": {"lecture": 45, "lab": 24, "seminar": 20}
}
```

## 4. Subsystem breakdown

Each engine takes a state, optionally an intervention, and returns metrics +
a visualization spec. "Moves" are the specific intervention types the frontend
exposes as forms.

### 4.1 Enrollment & Demand Forecasting

**Moves:** forecast next N terms per course from `demand_history.json` trend; make
an elective mandatory (demand shock); retire a course (redistribute its historical
demand across remaining electives); simulate an intake shock (+/- N% new students);
**propose a brand-new elective** (see §5, the deep-dive feature you asked for).

**Outputs:** per-course demand forecast chart (actual history + projected line),
oversubscription/undersubscription flags, ripple report when a course is
retired/added showing which other electives absorb the shifted demand.

### 4.2 Faculty & Staffing

**Moves:** add/remove a faculty member; put someone on leave/sabbatical; change
qualifications; auto-assign faculty to sections for a proposed term (greedy match
on `qualified_courses` + `max_courses_per_term`); hiring simulation ("add 2 faculty
with AI specialization — what does that unlock").

**Outputs:** workload heatmap (faculty × term, over/under capacity), list of
sections with no qualified instructor ("unteachable" alert), student-faculty ratio
trend, hiring-impact report (which currently-blocked courses/electives become
teachable).

### 4.3 Physical Space & Resources

**Moves:** add/remove/resize a room; take a room offline (renovation); add an
equipment/license pool with a seat cap distinct from room capacity; auto-schedule a
proposed term's sections into rooms and time slots.

**Outputs:** room utilization heatmap (room × time block), scheduling infeasibility
report (sections that don't fit anywhere given room type/capacity/equipment
constraints), capacity shortfall by room type.

### 4.4 Org Structure & Curriculum Design

**Moves:** split a program into two (e.g., CS → CS + AI/Data Science, seeded from
the elective pool); create a new minor/concentration from a subset of existing
electives, with a feasibility check against current faculty + seat capacity; merge
or retire a program, with a grandfathering plan for students mid-program; shift
credit hours between categories (curriculum modernization).

**Outputs:** before/after org chart, credit-hour distribution comparison
(stacked bar, old vs new), count of currently-enrolled students affected by a
split/merge/retirement and what their path forward looks like.

### 4.5 Accreditation & Compliance

This one is different from the other four: it's not move-driven, it's a **validator
that runs automatically against every candidate state**, from any engine.

**Checks:** credit-hour-by-category minimums vs `accreditation_rules.json`; class
size vs `max_class_size` (feeds off the room/section data from §4.3); student-faculty
ratio vs `max_student_faculty_ratio` (feeds off §4.2).

**Outputs:** a compliance scorecard — pass/fail per rule, with the actual number
next to the threshold, attached to every scenario result so you can see at a glance
whether a proposed change (say, a department split) would put you out of compliance.

## 5. New-elective feasibility engine (deep dive)

Input from the frontend: a name, a free-text description, proposed credits, and
optionally a target category/prerequisites — no other data required, this is
specifically for a course that doesn't exist yet.

Pipeline:
1. **Similarity scoring** — compare the proposed description against every existing
   course's `description` field. Default method: TF-IDF + cosine similarity (free,
   deterministic, no API dependency). Optional second pass: ask the LLM (Groq) for a
   qualitative "why these are similar" explanation on the top matches, since you
   already have that wired up for the advisor agent.
2. **Evidence pull** — for the top-K most similar existing courses, pull their
   `demand_history.json` track record (enrollment trend, waitlist pressure, pass
   rate) and their `category`.
3. **Feasibility signal** — a weighted estimate: projected first-year demand
   (based on similar courses' enrollment, adjusted by how many prerequisites gate
   access to it), a resourcing check (do we have a qualified faculty member per
   §4.2, is there room capacity per §4.3), and an accreditation check (does adding
   it keep the category's credit-hour distribution sane per §4.5).
4. **Output** — a feasibility score with the supporting rationale spelled out
   ("similar to CMPS460 Machine Learning (0.81 similarity) and CMPS453 Data Mining
   (0.74), both of which have grown 12%/year in enrollment and run at 95%+ capacity;
   2 faculty are qualified to teach it; no room conflict"), not just a bare number.

## 5.1 Resource requirement model

This is the missing link between "a course exists" and "a course costs something to
run" — how every engine (Faculty, Physical Space, and the feasibility engine above)
knows what a course actually needs. It's a mix of explicit per-course fields and
numbers derived fresh every time a scenario runs — nothing about resource needs is
hardcoded separately from the course itself.

**Explicit (stored on the course, existing or proposed):**
- `requires_room_type` and `equipment_needed`, from the schema in §3.

**Derived (computed at simulation time, not stored):**
- **Sections needed** = `ceil(projected_enrollment / section_capacity)`. For an
  existing course: projected enrollment comes from `demand_history.json`, section
  capacity is the existing `seat_capacity` (or a room-type default if null, e.g.
  45 for lecture / 24 for lab, matching `accreditation_rules.json`'s
  `max_class_size`).
- **Faculty needed** = one qualified instructor per section, checked against
  `faculty.json`'s `qualified_courses` and each instructor's remaining
  `max_courses_per_term` capacity that term.
- **Room needed** = one room per section, matching `requires_room_type` and
  `equipment_needed`, checked against `rooms.json` inventory for that term.

**For a brand-new proposed elective** (no history, no one "qualified" by
definition), all three legs are estimated from the similarity match in §5 instead:
- Projected enrollment ≈ the demand of the top-K similar existing courses.
- Room type/equipment ≈ inherited from the closest match, overridable in the
  proposal form if you already know it needs a lab.
- Faculty match ≈ search `faculty.json` for instructors whose `specializations`
  overlap with keywords pulled from the proposed description (a "who could
  plausibly teach this" proxy, not a guarantee, since `qualified_courses` is by
  definition empty for a course that doesn't exist yet).

The feasibility score in §5 is the bundle of four checks, reported separately so
you can see which one is the actual constraint: demand feasibility, faculty
feasibility (≥1 plausible instructor with free load), room feasibility (spare
capacity of the right type that term), accreditation feasibility (credit-hour
distribution stays sane).

## 6. Frontend flow

**State Manager (new page)** — upload or edit each of the five data files. Files
you don't upload fall back to the bundled mock defaults, so the system is always
runnable out of the box. Editing happens two ways: re-upload a JSON file, or edit
inline via a table (`st.data_editor`) for quick tweaks without leaving the browser.
The active state persists across the session (and optionally saves to disk as a
named snapshot you can reload later — e.g. "Fall 2026 baseline").

**Propose a Change (new page)** — pick an intervention type from a dropdown (Add
Faculty / Remove Room / Propose New Elective / Split Program / Adjust Credit
Requirement / ...), fill in a type-specific form, and either apply it immediately
or add it to a bundle of changes to apply together as one scenario (e.g. "hire 2
faculty AND open a new lab AND launch the AI minor" as a single combined proposal).

**Scenario Comparison (new page)** — baseline vs one or more saved scenarios,
side by side, with the relevant engine outputs from §4 rendered as interactive
Plotly charts (hover for exact numbers, toggle series on/off) instead of static
images, plus the accreditation scorecard for each.

## 7. How it all works, end to end

1. Load state (defaults, or whatever's been uploaded/edited in State Manager).
2. Build an intervention — one move, or a bundle — via the Propose a Change forms.
3. Intervention layer validates and applies it to produce a candidate new state
   (pure function; original state is untouched).
4. The relevant domain engine(s) re-run on the new state — only the ones the
   intervention actually touches, to keep it fast.
5. Accreditation/Compliance always re-validates the new state regardless of which
   engine triggered the change.
6. Result: a diff report (old state vs new state, in numbers) plus each engine's
   interactive visualization, plus the compliance scorecard.
7. You accept the new state as the new baseline, discard it, or save it as a named
   scenario to keep comparing against others.

## 8. Decisions locked

- Similarity method: TF-IDF + cosine similarity (free, offline, deterministic),
  with an optional LLM explanation pass via Groq on the top matches.
- Faculty/room/cost mock numbers: invented at plausible QU scale, clearly
  labeled as mock data, swappable the same way `courses.json` is.
- Out of scope for now: Budget/Financial as a standalone category, Advising/Equity,
  Risk/External-shock. (Budget-adjacent numbers like salary and room operating cost
  still exist in `faculty.json`/`rooms.json` since the resource model in §5.1 needs
  them, but there's no dedicated budget engine or ROI analysis yet.)
- Build order: Enrollment & Demand → Accreditation & Compliance → Faculty &
  Staffing → Physical Space → Org Structure.

## 9. Two remaining fine points on the resource model

- **Missing description/room-type/equipment on the 41 real courses.** These three
  new fields don't exist in your data yet. I'll write plausible values for all 41
  (descriptions from the course titles/context, room type inferred — labs for
  courses with a hands-on component like CMPE355 Networks or a future ML elective,
  lecture otherwise) and flag them as inferred so you can correct any that are
  wrong, rather than blocking on you filling in 41 rows by hand first.
- **Zero-faculty-match case.** If a proposed new elective has no faculty whose
  `specializations` overlap at all, should the feasibility engine report it as
  infeasible outright, or as feasible-but-flagged ("would require hiring or
  retraining — no current faculty match")? I'd default to the latter, since it's
  more useful for planning than a flat rejection — say if you want it stricter.
