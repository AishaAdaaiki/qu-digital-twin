# QU Digital Twin — Final Report

Scale AI × Qatar University Internship · Aisha Adaaiki · [fill in submission date]

*Skeleton — fill in each section once real course data, simulation numbers, and
agent transcripts are in. Anything marked `[TODO]` needs your input; the
structure below follows the Problem → Contribution → Tools → Output → Challenges
framework.*

## 1. Problem

[TODO: 1-2 paragraphs. What problem does the QU Digital Twin address, and why
build it as one connected system instead of eleven separate catalog
submissions? E.g.: advising, planning, and QA tasks in the catalog all operate
on the same underlying prerequisite graph — building them as isolated
deliverables means re-deriving that graph (and re-testing rule logic) eleven
times over. This project builds it once and lets every module read from it.]

## 2. Contribution

Summarize what was actually built, module by module. Suggested structure —
replace the placeholder bullets with your real numbers once you've run
everything against the final course data:

- **M1 — Data layer.** [TODO: how many courses, how many prerequisite edges,
  which program.]
- **M2 — Rule engines.** `graduation_audit()` and `substitution_check()`.
  Tested on 5 student states and 10 substitution pairs (`backend/tests/test_rule_engine.py`).
- **M3 — Planner + conflict detector.** `plan_term()` and `detect_conflicts()`.
  Tested on 5 starting states spanning freshman to final term (`backend/tests/test_planner.py`).
- **M4 — Cohort simulation + Monte Carlo.** [TODO: after running
  `python -m backend.simulation` and the Monte Carlo wrapper at production scale
  (100+ students, 1000 runs), report: mean graduation term, top bottleneck
  courses, and which parameter the sensitivity analysis (`sensitivity_analysis()`
  in `backend/simulation.py`) flagged as the biggest driver of variance.]
- **M5 — What-if analysis.** [TODO: run `capacity_bottleneck_ranking()`,
  `term_restriction_comparison()`, and `remove_summer_scenario()` at production
  scale and report the top-5 bottleneck courses with concrete Δ-graduation-term
  numbers, plus which of the 3 term-restriction scenarios hurt most and why.]
- **M6 — Advising agent.** CrewAI agent with 4 tools
  (`graduation_audit`, `substitution_check`, `plan_term`, `detect_conflicts`)
  and a hard must-not list. [TODO: after running 12 representative interactions
  through `backend/agent.py`, summarize what worked and where the agent needed
  a clarifying question or declined to answer.]
- **M7 — QA pass.** [TODO: after running `python -m backend.qa_redteam` and
  manually reviewing `qa_results.csv`, report pass/partial/fail counts across
  the 13 prompt-injection attempts and 10 hallucinated-policy questions, and
  the 2-3 clearest failure patterns if any.]
- **M8 — Frontend.** 4-page Streamlit app (Graduation Audit, Planner,
  Simulation + What-If, Advisor Chat), each page a thin wrapper over the
  backend with no business logic in the UI layer.

## 3. Tools

- **Language / runtime:** Python 3.10+
- **Agent framework:** CrewAI (`crewai`, `crewai-tools`)
- **LLM provider:** [TODO: which you used — Anthropic Claude or OpenAI, and
  which model]
- **Simulation:** NumPy (seeded `Generator` for reproducibility), Matplotlib
- **Frontend:** Streamlit
- **Testing:** pytest (25 automated tests across M2-M5)

## 4. Output

[TODO: paste in the actual artifacts once generated —]
- Screenshot(s) of each Streamlit page
- The Monte Carlo graduation-time histogram
- The seat-capacity bottleneck ranking table
- A few representative advisor chat transcripts (including the tool-call
  transparency panel)
- The `qa_results.csv` summary table

## 5. Challenges

[TODO: what actually went wrong or took longer than expected while building
this. Some candidates worth reflecting on honestly, if true for your build:]
- Encoding the real QU CS BSc prerequisite graph accurately from the public
  catalog (course codes, credit values, cross-listed prerequisites)
- Balancing simulation realism (pass/fail/withdraw assumptions) against having
  no real QU data to calibrate against
- Getting the CrewAI agent to consistently call tools rather than answer from
  its own training knowledge, especially under adversarial prompts in the M7
  red-team pass
- Any specific prompt-injection or hallucination failure that required a
  system-prompt or tool-description fix, and what the fix was

## Limitations

See the "Known limitations" section in `README.md` for the standing caveats
(placeholder course data pending your real catalog import, mocked section
times, assumption-based simulation rates, simplified seat-capacity model).
