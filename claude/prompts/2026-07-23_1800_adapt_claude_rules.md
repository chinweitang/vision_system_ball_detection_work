# 2026-07-23 18:00 — Adapt claude_rules.md to this project

**Instructions:** Copy the block below and paste it into a fresh Claude Code session
in this repo.

---

```
READ FIRST: claude/claude_rules.md (this is the file you're about to edit — read it
in full before touching it, along with claude/claude_code_prompt_template.md and
claude/logs/2026-07-23_ball_detection_rate_tuning_worklog.md)

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Rewrite claude/claude_rules.md so it fits this project — a solo Python computer-vision
research codebase (stereo ball detection/tracking, Masters project) — instead of the
R/BikeBalance dashboard project it was originally written for.

Context: claude_rules.md was copied from another project and still refers to R/,
tests/, scripts/, dev/ folders, roxygen2 docs, tryCatch(), and a mandatory
feature-branch-only git workflow that doesn't match how this repo is actually used
(all 18 commits so far went straight to main, and there's only one branch). This
repo's real structure is: src/ (calibration/, image_processing/, registration/,
stereo/ — numbered pipeline scripts like 04_stereo_three_frame_diff.py), data/
(session folders, e.g. 2026_07_21_gym/, FULLY GITIGNORED — no git history exists for
anything in it), calibration_outputs/ (tracked: npz/txt/png calibration results per
session), and claude/ (this rules file + claude/logs/ for real-time work logs, which
is already the established convention — same idea as the template's dev/logs/, just
under claude/ instead of dev/).

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

1. Read claude/claude_rules.md and claude/claude_code_prompt_template.md fully before
   editing, plus claude/logs/2026-07-23_ball_detection_rate_tuning_worklog.md to see
   the logging convention actually in use in this project.

2. Rewrite claude/claude_rules.md in place. Keep its overall section structure
   (numbered sections: git workflow, file rules, code standards, dev workflow,
   performance debugging protocol, communication style, project conventions, quality
   checklist, scope boundaries, work logging, prompt clarification protocol,
   emergency stop, summary) — this is an adaptation, not a from-scratch rewrite.
   Adapt content per the numbered points below.

3. Role framing: drop "junior R developer working on BikeBalance." Reframe as a
   Python vision-system research-codebase assistant working with Chin Wei. Keep the
   "ask rather than assume" principle, but scope it per point 6 below — it shouldn't
   apply to literally every task anymore.

4. Git workflow (Section 1): replace the mandatory feature-branch / never-commit-to-
   main rule with a description of actual practice — commits go directly to main
   (solo project, no PR review step). Keep: never push to GitHub without being asked,
   never force-push or rewrite published history without being asked, ask before any
   destructive git operation (reset --hard, deleting branches, etc.), write clear
   commit messages. Remove the Option A/B/C "choose a git workflow" block that
   appears in the prompt-template reference material — not applicable here, there's
   only one workflow now.

5. File creation / NEW data-protection rule (Section 2): rewrite the allowed/
   forbidden folder lists to match src/, data/, calibration_outputs/, claude/ instead
   of R/, tests/, scripts/, dev/, notebooks/. Then add a clearly-flagged new rule:

   NEVER overwrite or delete any file under data/ or calibration_outputs/ — this
   includes raw captures, calibration results (npz/txt/png), AND derived/tuning
   outputs (e.g. data/detector_tuning/*.csv, contact sheets, sweep results) that a
   script would normally regenerate on every run — without explicit permission first.

   State the reasoning in the rule itself: data/ is fully gitignored, so there is no
   git history to recover a previous version from if it's overwritten, and the user
   wants to be able to compare results across previous runs of a script. If a task or
   script run would overwrite or delete an existing file in either of these trees,
   STOP and ask for permission BEFORE running it — ideally flagged during planning,
   before starting the task, not discovered mid-run. Make clear this is stricter than
   the rest of the file-editing rules: code/scripts can be freely created and edited;
   it is specifically data files (outputs like .png, .csv, .npz, .txt, .jpg, etc.)
   that require permission before being overwritten or deleted.

6. Confirmation gate (Section 4 "Development Workflow" + Section 11 "Prompt
   Clarification Protocol"): scale down the current "restate understanding + list
   clarifying questions + wait for explicit confirmation before writing ANY code"
   requirement so it applies to genuinely ambiguous requests and risky/irreversible
   actions (anything touching or overwriting files under data/ or
   calibration_outputs/ per point 5, large refactors, git history changes) — not to
   every single task. For exploratory/diagnostic work (e.g. investigating a detection
   or calibration problem, running a parameter sweep, writing a one-off analysis
   script), Claude should be able to go straight into multi-step investigation the
   way it did in claude/logs/2026-07-23_ball_detection_rate_tuning_worklog.md,
   without a pre-approval gate at each step. Real-time logging (Section 10)
   substitutes for the confirm-first gate on this kind of work — the user catches
   problems by monitoring the log, not by pre-approving every step.

7. Code standards (Section 3): replace the R-specific block (roxygen2 documentation,
   tryCatch/stopifnot, a mandated tests/ folder, R/scripts/ naming conventions) with
   Python equivalents — docstrings and type hints for functions, try/except for error
   handling where it matters, structured return values where useful. Match the
   numbered-script convention already used under src/image_processing/ (e.g.
   04_stereo_three_frame_diff.py) instead of inventing a new naming scheme. Do NOT
   introduce a mandated tests/ folder or testing requirement — none exists in this
   project and it shouldn't be required by the rules.

8. Work logging (Section 10): update every dev/logs/ and dev/log_template.md
   reference to claude/logs/. There is no log_template.md-equivalent file in this
   project. Either (a) point to claude/logs/2026-07-23_ball_detection_rate_tuning_worklog.md
   as the format example, or (b) inline a short structure directly in this section.
   Keep it short — don't create a separate template file unless it's genuinely
   trivial to do so; if you think a dedicated claude/log_template.md is warranted,
   ask me first rather than creating it as part of this task.

9. Performance debugging protocol (Section 5): keep the "measure first, optimize
   second" principle and the aggressive-timeout / stop-and-diagnose thresholds as-is
   — they're language-agnostic. Just swap the R code example (Sys.time() / cat()) for
   a Python equivalent (time.time() / print or logging).

10. Leave claude/claude_code_prompt_template.md untouched — only
    claude/claude_rules.md changes in this task.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

Do NOT do (unless I explicitly ask later):
- ❌ Touch any file under data/ or calibration_outputs/
- ❌ Modify claude/claude_code_prompt_template.md or any existing file under
  claude/logs/
- ❌ Modify any file under src/
- ❌ Commit this change to git
- ❌ Re-architect claude_rules.md's section numbering/order beyond what's needed to
  reflect the changes above
- ❌ Invent new process not asked for above (e.g. a tests/ requirement, a new
  branch-naming scheme, new folders beyond what already exists)
- ❌ Create claude/log_template.md without asking first (see point 8)

IF you think something else should be changed that isn't covered above:
1. STOP
2. Note it explicitly in your summary: "Considered doing [X] but it's not in scope —
   asking first"
3. Wait for my response before doing it

═══════════════════════════════════════════════════════════════════════════════
GIT WORKFLOW (for this task itself)
═══════════════════════════════════════════════════════════════════════════════

No git. Just edit claude/claude_rules.md directly in place. Do not commit.

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ claude/claude_rules.md no longer references R, roxygen2, tryCatch, BikeBalance,
   or dev/ paths anywhere
✅ The mandatory feature-branch workflow is replaced with "commits go directly to
   main," while destructive-git-op and GitHub-push confirmation rules are kept
✅ New data-protection rule is present and unambiguous: no overwrite/delete under
   data/ or calibration_outputs/ (including derived/tuning outputs) without asking
   first, with the reasoning stated (gitignored, no recovery path, user wants to
   compare results across runs)
✅ Confirmation-gate language reflects "ask first for ambiguous/risky work, proceed
   directly into exploratory/diagnostic work otherwise" rather than "ask before
   literally any code, every task"
✅ Logging section points at claude/logs/, not dev/logs/, and doesn't require a
   log_template.md file that doesn't exist (unless you asked me and I said to add one)
✅ Code standards section is Python-native (docstrings/type hints, try/except) and
   does not mandate a tests/ folder
✅ Section structure/headings are still recognizably an edit of the original file,
   not a from-scratch rewrite
✅ Short section-by-section summary of what changed and why, provided at the end

═══════════════════════════════════════════════════════════════════════════════
START WORK
═══════════════════════════════════════════════════════════════════════════════

Begin now:
1. Read claude/claude_rules.md, claude/claude_code_prompt_template.md, and
   claude/logs/2026-07-23_ball_detection_rate_tuning_worklog.md
2. Edit claude/claude_rules.md per the scope above
3. Report a short section-by-section summary of what changed and why
```

---

## Notes on the decisions baked into this prompt

These were confirmed with the user before writing this prompt (2026-07-23):

1. **Git workflow** — matches actual practice (direct-to-main commits), not a
   tightened feature-branch mandate.
2. **Data protection scope** — covers *everything* under `data/` and
   `calibration_outputs/`, including derived/tuning outputs that scripts normally
   regenerate, not just raw captures.
3. **Confirmation gate** — scaled down to ambiguous/risky requests only; exploratory
   and diagnostic multi-step work can proceed without a pre-approval gate at each
   step, relying on real-time logging instead.
4. **Code standards** — translated to Python (docstrings/type hints, try/except),
   matching the existing numbered-script convention under `src/`; no `tests/`
   requirement introduced.
