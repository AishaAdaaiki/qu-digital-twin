# QU Digital Twin

Full-Lifecycle Student Flow Simulator with AI Advising Layer, plus a Department
Planning Digital Twin — CS BSc, Qatar University. Scale AI × Qatar University
practical training project.

One JSON backbone (`backend/data/courses.json`), four architectural layers, eight
modules, chaining eleven tasks from the Scale AI internship catalog into one
coherent system instead of eleven isolated deliverables (M1-M8) — extended with a
second subsystem (M9-M13) that generalizes the same "state in, analysis out"
pattern across five department-planning domains: enrollment/demand, accreditation,
faculty, physical space, and org/curriculum structure. See
`docs/department_simulation_architecture.md` for the full design.

## Architecture — student advising (M1-M8)

```
Layer 1 — Data (M1)           courses.json: single source of truth, read-only at runtime.
Layer 2 — Rule Engine (M2/M3) graduation_audit, substitution_check, plan_term,
                               detect_conflicts. Pure functions. No LLM calls.
Layer 3 — Simulation (M4/M5)  Runs Layer 2 thousands of times over synthetic
                               cohorts. Bottleneck heatmaps, graduation-time
                               distributions, stress-test deltas. No LLM calls.
Layer 4 — Agent (M6/M7)       The only layer that uses an LLM. Takes natural
                               language, calls Layer 2 functions as tools, never
                               invents a schedule, requirement, or verdict.
```

Each layer depends only on the layer below it — nothing calls upward. The hard
architectural rule: **the agent layer never generates a schedule, a remaining-
requirements list, or a substitution verdict from its own weights.** Every one of
those four answers is produced by a plain Python function in `rule_engine.py` or
`planner.py`; the LLM's only job is to call the right function with the right
arguments and relay the result.

## Architecture — department planning (M9-M13)

```
L1 State Data      backend/state.py's DepartmentState bundles 9 swappable JSON files
                    (courses, elective_catalog, faculty, rooms, demand_history,
                    accreditation_rules, substitution_rules, mock_schedule, sim config).
L2 Domain Engines   backend/engines/{demand,accreditation,faculty,space,org}.py -
                    pure functions, state in -> analysis/report out. No LLM calls.
L3 Interventions    backend/interventions.py - a dispatcher over every engine's
                    "Move" functions (add_faculty, resize_room, retire_course, ...).
                    Always returns a NEW DepartmentState; input state is never mutated.
L4 Frontend         app/pages/5-12 - State Manager, one page per engine, Propose a
                    Change (bundle builder), Scenario Comparison.
```

Same non-mutation discipline as M4/M5: `DepartmentState.copy()` deep-copies every
field, so `CURRENT STATE + INTERVENTION -> CANDIDATE NEW STATE` never touches the
original — you can always get back to baseline.

## Modules and catalog tasks

| Module | Catalog tasks | File(s) |
|---|---|---|
| M1 — Data layer | T2.1 | `backend/data/courses.json`, `backend/data_layer.py` |
| M2 — Rule engines | T2.2, T2.3 | `backend/rule_engine.py` |
| M3 — Planner + conflict detector | T2.4, T2.5 | `backend/planner.py` |
| M4 — Cohort simulation + Monte Carlo | T3.1, T3.4 | `backend/simulation.py`, `backend/success_rates.py`, `backend/capacity_model.py` |
| M5 — What-if analysis | T3.2, T3.3 | `backend/scenarios.py` |
| M6 — Advising agent (CrewAI) | T4.6 | `backend/agent.py`, `backend/tools.py` |
| M7 — QA / red-team pass | T1.1, T1.2 | `backend/qa_redteam.py` |
| M8 — Student-advising frontend | — | `app/pages/1-4` |
| M9 — Enrollment & demand forecasting | — | `backend/engines/demand.py`, `backend/text_similarity.py` |
| M10 — Accreditation & compliance | — | `backend/engines/accreditation.py` |
| M11 — Faculty & staffing | — | `backend/engines/faculty.py` |
| M12 — Physical space & resources | — | `backend/engines/space.py` |
| M13 — Org structure & curriculum design | — | `backend/engines/org.py` |
| Department-planning frontend | — | `app/pages/5-12` |

## Setup

```bash
git clone <your-repo-url>
cd qu-digital-twin
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: LLM_PROVIDER defaults to "groq" (free tier, no credit card - get a
# key at https://console.groq.com/keys). Set GROQ_API_KEY, or switch
# LLM_PROVIDER to "anthropic"/"openai" and set the matching key instead.
```

## Running each module

```bash
# M1 — sanity-check the data layer
python -m backend.data_layer

# Full test suite (94 tests total, across M2-M5 and M9-M13)
pytest backend/tests/ -v

# M4 — one seeded cohort run from the command line (per-course success rates + capacity on by default)
python -m backend.simulation

# M5 — top-5 seat-capacity bottlenecks from the command line
python -m backend.scenarios

# M6 — one advisor turn from the command line (needs .env configured)
python -m backend.agent "I've completed CMPS151, CMPS152, MATH101. What should I take next fall?"

# M7 — full red-team campaign against the live agent (needs .env configured)
python -m backend.qa_redteam
# writes qa_results.csv — review the auto-flagged classification column by hand

# M8 — the full app
streamlit run app/Home.py
```

## Known limitations

- **Course data.** `backend/data/courses.json` is built from the real QU CS BSc
  catalog export (41 courses, 120 credit hours, catalog year 2024). Corequisites
  from the source catalog are merged into `prerequisites` (treated as "must be
  done before enrolling" rather than modeling true concurrent enrollment) — the
  original prerequisite/corequisite split is preserved per-course under
  `source_prerequisites`/`source_corequisites` for reference. The Senior Project I
  compound gate (CMPS310 AND (CMPS350 OR CMPS405) AND >=84 completed credit
  hours) is modeled via two extra optional fields, `one_of_prerequisites` and
  `min_credits_required` — see the schema docstring in `backend/data_layer.py`.
  Major electives are modeled as 4 generic slots (`ELEC1`-`ELEC4`), matching how
  the source catalog itself represents "12 CH chosen from an 18-course pool";
  the actual elective pool is preserved as reference metadata under
  `_elective_pool_reference` in courses.json but isn't wired into the graph.
- **Section meeting times are mocked.** QU doesn't publish per-section times in
  the public catalog, so `backend/data/mock_schedule.json` is student-authored,
  as the T2.5 brief allows.
- **Pass/fail/withdraw outcomes are per-course, per-semester, and network-aware**
  (`backend/success_rates.py`), not one flat rate per category. Each course's
  effective pass rate blends its own historical rate from
  `backend/data/demand_history.json` with its direct prerequisites' rates
  (default 80% own / 20% prerequisite chain — see the module docstring), so a
  course whose prerequisites perform poorly gets nudged down too. The
  "Course Success Rates" tab on the Simulation page lets you inspect any
  course's rate, its prerequisite chain, and propagate a hypothetical rate
  change forward to see the cascading effect on every downstream course. The
  underlying historical numbers are still invented mock data for this build —
  swap in real registrar pass-rate history via the same
  `{course: {"YYYY_term": {"pass_rate": ...}}}` schema and the whole chain
  updates automatically. `simulation_config.json`'s per-category rates remain
  as the fallback for courses with no history on record (new electives, the
  generic `ELEC1`-`ELEC4` slots).
- **Seat capacity is also per-course/semester and real-data-driven**
  (`backend/capacity_model.py`), not the single static `seat_capacity` field
  in `courses.json`. It uses the most recent year's recorded capacity from
  `demand_history.json`, which is often a real number even for courses
  courses.json itself marks "unlimited" (e.g. CMPS151 is `None` in
  courses.json but has actually been capped at 24 seats every year on
  record) — the same "Course Success Rates" tab surfaces both numbers side
  by side and flags every course/term where they disagree. M5's capacity
  what-if functions (`capacity_bottleneck_ranking`,
  `capacity_sensitivity_curve`) build their scenarios by overriding
  `demand_history.json`'s capacity, not `courses.json`'s field, since the
  real recorded number always takes priority once it exists. Each term,
  students competing for a capacity-limited course are still admitted
  uniformly at random up to the cap — there's no priority registration,
  waitlist carry-over, or class-standing preference.
- **No summer offerings in the source data.** The catalog export only lists a
  Fall or Spring term per course, so the simulator's summer term is naturally
  empty in the baseline (distinct from the M5 "remove summer" scenario, which
  models cutting an existing summer session).
- **The advising agent needs a live API key.** Default provider is Groq (free
  tier — `GROQ_API_KEY`); Anthropic and OpenAI also work by setting
  `LLM_PROVIDER` and the matching key in `.env`. `qa_redteam.py`'s `auto_flag`
  column is a first-pass heuristic classifier, not a substitute for manually
  reading each transcript before it goes in a findings note.
- **CrewAI's per-turn design.** Each chat turn is a fresh `Crew.kickoff()`; prior
  turns are passed in as a text block rather than true persistent agent memory,
  since CrewAI tasks are stateless by design.

## Repository layout

```
qu-digital-twin/
├── backend/
│   ├── data/
│   │   ├── courses.json              # M1 backbone (extended w/ description,
│   │   │                              #   requires_room_type, equipment_needed)
│   │   ├── substitution_rules.json
│   │   ├── mock_schedule.json
│   │   ├── simulation_config.json    # category fallback rates (M4)
│   │   ├── elective_catalog.json     # M9 - 18 concrete electives
│   │   ├── demand_history.json       # M4/M9 - 3-yr enrollment/capacity/pass-rate/waitlist history
│   │   ├── faculty.json              # M11 - 19-person mock roster
│   │   ├── rooms.json                # M12 - 12-room mock inventory
│   │   └── accreditation_rules.json  # M10 - credit-hour/class-size/ratio policy
│   ├── engines/
│   │   ├── demand.py                 # M9
│   │   ├── accreditation.py          # M10
│   │   ├── faculty.py                # M11
│   │   ├── space.py                  # M12
│   │   └── org.py                    # M13
│   ├── tests/
│   │   ├── test_rule_engine.py       # M2
│   │   ├── test_planner.py           # M3
│   │   ├── test_simulation.py        # M4
│   │   ├── test_scenarios.py         # M5
│   │   ├── test_success_rates.py     # M4 success-rate model
│   │   ├── test_capacity_model.py    # M4 capacity model
│   │   ├── test_state.py             # M9-M13 state container
│   │   ├── test_demand_engine.py     # M9
│   │   ├── test_accreditation_engine.py  # M10
│   │   ├── test_faculty_engine.py    # M11
│   │   ├── test_space_engine.py      # M12
│   │   ├── test_org_engine.py        # M13
│   │   └── test_interventions.py     # L3 dispatcher
│   ├── data_layer.py                 # M1 (+ M9-M13 file loaders)
│   ├── rule_engine.py                # M2
│   ├── planner.py                    # M3
│   ├── simulation.py                 # M4
│   ├── success_rates.py              # M4 - per-course/term, prereq-chain-aware pass rates
│   ├── capacity_model.py             # M4 - per-course/term real seat capacity
│   ├── plots.py                      # shared matplotlib chart builders (M4/M5/M8)
│   ├── scenarios.py                  # M5
│   ├── tools.py                      # M6 — CrewAI tool wrappers
│   ├── agent.py                      # M6 — CrewAI advisor
│   ├── qa_redteam.py                 # M7
│   ├── text_similarity.py            # M9 - dependency-free TF-IDF
│   ├── state.py                      # L1 - DepartmentState container
│   └── interventions.py              # L3 - generalized "apply a move" dispatcher
├── app/
│   ├── Home.py
│   ├── state_session.py              # L4 - session-state helpers for department planning
│   └── pages/
│       ├── 1_Graduation_Audit.py
│       ├── 2_Planner.py
│       ├── 3_Simulation.py           # includes the Course Success Rates tab
│       ├── 4_Advisor.py
│       ├── 5_State_Manager.py
│       ├── 6_Demand_Forecasting.py
│       ├── 7_Accreditation.py
│       ├── 8_Faculty_Staffing.py
│       ├── 9_Physical_Space.py
│       ├── 10_Org_Structure.py
│       ├── 11_Propose_Change.py
│       └── 12_Scenario_Comparison.py
├── docs/
│   ├── final_report.md
│   └── department_simulation_architecture.md
├── requirements.txt
├── .env.example
└── README.md
```
