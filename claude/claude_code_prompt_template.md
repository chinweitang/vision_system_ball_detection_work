---
title: "R Notebook"
output: html_notebook
editor_options: 
  chunk_output_type: inline
---

# Claude Code Prompt Template

**Instructions:** Copy this entire template, fill in the [BRACKETS], then paste into Claude Code.

---

## Pre-Flight Checklist

Before filling out this template:
- [ ] Do you have a clear objective? (Can you state it in one sentence?)
- [ ] Do you know the expected completion time? (Rough estimate is fine)
- [ ] Have you identified what files/folders will be modified?
- [ ] For long tasks (>15 min): Have you defined checkpoint intervals?
- [ ] Are you monitoring with `tail -f dev/logs/*.md` in separate terminal?

---

## The Prompt (Copy from here)
```
READ FIRST: dev/claude_rules.md

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

[ONE SENTENCE: What you want accomplished]

Example: "Apply vectorization fix to BigQuery import and run full import of 19 files"

[OPTIONAL - More context if needed]:
[Any background, constraints, or previous work this builds on]

═══════════════════════════════════════════════════════════════════════════════
LOGGING (DETAILED LEVEL)
═══════════════════════════════════════════════════════════════════════════════

Create work log: dev/logs/[YYYY-MM-DD]_[HHMM]_[short-task-name].md

Follow structure in dev/log_template.md

Update in REAL-TIME after each significant step.

DETAIL LEVEL: Detailed (more than balanced, less than comprehensive)

Include:

**Diagnostic Tests:**
- ✅ Command run
- ✅ Full output (not just summary)
- ✅ What you learned from it

**Test Results:**
- ✅ Summary table (always visible)
- ✅ Full verbose output for:
  - Files with errors/warnings
  - Files with anomalies (unusual timing, low match rate, etc.)
  - First and last file (to show start/end state)
- ✅ Summary only for normal/expected results
- ✅ Use <details> tags to hide verbose output (keeps log scannable)

**Code Changes:**
- ✅ File and line numbers
- ✅ High-level before/after description (NOT full code)
- ✅ Performance impact
- Example: "Changed lines 86-95: Replaced sapply() with vectorized gsub()"

**Issues & Errors:**
- ✅ Full error messages (in code blocks)
- ✅ Every attempted solution (even failed ones)
- ✅ Why each approach didn't work
- ✅ Final solution that worked

**Decisions:**
- ✅ All options considered
- ✅ Pros/cons of each
- ✅ Performance/complexity estimates
- ✅ Why you chose what you chose
- ✅ Trade-offs accepted

**Commands:**
- ✅ Exact commands run
- ✅ Key output (not necessarily everything)

**Visual Structure:**
- ✅ Use section separators: ═══════════════════════════════════
- ✅ Use <details><summary> for verbose outputs
- ✅ Put summaries ABOVE detailed output (skim-friendly)

**Why this detail level:**
User monitors with `tail -f` to catch tangents early.
User needs context preservation for long sessions (compaction insurance).
User wants to learn from the process, not just see final results.

═══════════════════════════════════════════════════════════════════════════════
REAL-TIME LOG UPDATES (CRITICAL FOR MONITORING)
═══════════════════════════════════════════════════════════════════════════════

**Problem:** By default, you'll collect all results and write the log once at end.
This defeats the purpose of real-time monitoring.

**Required Behavior:**

For ANY task where user will monitor with tail -f:

✅ Update log IMMEDIATELY after each significant step
✅ Use APPEND operations (don't rewrite entire file each time)
✅ Each update should be visible within 1-2 seconds

**Implementation:**
```r
# After each step:
log_file <- "dev/logs/2025-11-24_task.md"

# Append immediately
cat("\n[12:30:15] Running Check 1: Duplicates...\n", 
    file = log_file, append = TRUE)

# Run the work
result <- run_check_1()

# Append result immediately
cat(sprintf("[12:30:27] ✅ Check 1 PASSED - %s\n", result),
    file = log_file, append = TRUE)
```

**NOT like this:**
```r
# ❌ WRONG - collects everything, writes once at end
results <- list()
results$check1 <- run_check_1()
results$check2 <- run_check_2()
results$check3 <- run_check_3()

# User sees nothing until all work is done
write_log(results)  # Too late!
```

**User Expectation:**
- They run: `tail -f dev/logs/2025-11-24_task.md`
- They see each step as it happens
- They catch issues within seconds, not minutes

**This applies to:**
- Multi-step processes (>2 steps)
- Long-running tasks (>2 minutes)
- Batch operations (multiple files/items)
- Any task where user explicitly says they'll monitor


═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

ONLY do these specific things:

1. [Specific task 1]
   Example: "Run scripts/07_import_bigquery_full.R"

2. [Specific task 2]
   Example: "Log results to work log"

3. [Specific task 3]
   Example: "Verify total row count matches expected ~130M"

[Add more as needed, but keep list SHORT and SPECIFIC]

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

Do NOT do (unless I explicitly ask later):

- ❌ Commit to git
- ❌ Create/merge branches
- ❌ Write documentation
- ❌ Add tests (unless that's the task)
- ❌ Refactor code
- ❌ Optimize things I didn't mention
- ❌ Add features
- ❌ "Improve" or "clean up" code
- ❌ [Add task-specific things to avoid]

IF you think something else should be done:
1. STOP
2. LOG: "Considered doing [X] but it's not in scope - asking first"
3. Report to me
4. Wait for my response

═══════════════════════════════════════════════════════════════════════════════
TIMING EXPECTATIONS
═══════════════════════════════════════════════════════════════════════════════

Expected total time: [X minutes/hours]

Per-step expectations:
- [Step 1]: [Y minutes]
  Example: "Each file import: 1-2 minutes"

- [Step 2]: [Z minutes]
  Example: "All 19 files: 20-30 minutes total"

[Add more steps as needed]

STOP and report if:
- Any step takes >2x expected time
- You're stuck on same issue for >5 minutes
- You've made no progress for >3 minutes
- [Add task-specific stop conditions]

Don't wait to see if slow processes complete.
If you identify a bottleneck → stop and diagnose immediately.

═══════════════════════════════════════════════════════════════════════════════
CHECKPOINTS (for tasks >15 minutes)
═══════════════════════════════════════════════════════════════════════════════

[DELETE THIS SECTION if task is <15 minutes]

After every [X files / Y minutes / Z steps]:

1. STOP working
2. Update log with checkpoint summary
3. Report to me:
   - What's completed
   - Current status
   - Time taken so far
   - Estimated time remaining
4. Ask: "Continue with next batch?"
5. WAIT for my approval

Checkpoint intervals:
- [Interval 1]: After [X units]
  Example: "After files 1-5: stop and report"

- [Interval 2]: After [Y units]
  Example: "After files 6-10: stop and report"

[Add more as needed]

Do NOT run unsupervised for >15 minutes without checking in.

═══════════════════════════════════════════════════════════════════════════════
ERROR HANDLING
═══════════════════════════════════════════════════════════════════════════════

Expected errors (log and continue):
- [Error type 1]
  Example: "Station name mismatches (<10%)"

- [Error type 2]
  Example: "Invalid date formats (<1%)"

Unexpected errors (STOP immediately):
- [Error type 1]
  Example: "Database connection lost"

- [Error type 2]
  Example: "Out of memory"

- [Any error not in 'expected' list above]

When error occurs:
1. Log it immediately (don't wait for completion)
2. Try [N] solutions (document each attempt)
3. If still failing after [N] tries → STOP and report
4. Don't silently continue with partial success

═══════════════════════════════════════════════════════════════════════════════
GIT WORKFLOW
═══════════════════════════════════════════════════════════════════════════════

[CHOOSE ONE - delete the others]

**Option A: Feature Branch (for new code)**
- Create branch: feature/[short-description]
- Commit changes to branch
- Do NOT merge to main (I'll do that after review)

**Option B: No Git (for running existing scripts)**
- Do NOT create branches
- Do NOT commit anything
- Just run the code and log results

**Option C: Direct to main (rare - ask first)**
- Only if explicitly told to commit to main
- Use for trivial changes (typo fixes, log updates)

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

Task is complete when:

✅ [Criterion 1]
   Example: "All 19 files imported successfully"

✅ [Criterion 2]
   Example: "Total row count is 127-133M (expected ~130M)"

✅ [Criterion 3]
   Example: "Match rate is 89-94% per file"

✅ [Always required]:
   - Work log is complete and up-to-date
   - All tests passed (if applicable)
   - No errors in final run
   - Summary provided

═══════════════════════════════════════════════════════════════════════════════
CONTEXT COMPACTION AWARENESS
═══════════════════════════════════════════════════════════════════════════════

This session may involve many messages over 30+ minutes.
In long sessions, early context gets compressed to save memory.

PROTECTION STRATEGY:
1. Write detailed logs in real-time (preserves context in files)
2. Reference your log file throughout the session
3. User will monitor for context loss and alert you

IF YOU NOTICE CONTEXT LOSS:

Signs you've lost context:
- You're repeating work already done
- You're asking questions already answered
- User references something you said earlier but you don't recall
- You're suggesting approaches already tried

Recovery steps:
1. STOP current work immediately
2. Say: "I think I've lost context from earlier in this session"
3. Read your log: dev/logs/[today]_[time]_[task].md
4. Skim for:
   - What's been completed
   - What decisions were made
   - What's currently in progress
5. Ask user: "Based on the log, should I continue with [next step]?"

USER WILL ALSO MONITOR:
If user says "read your log" → do so immediately before continuing.

The log is your backup memory - use it when conversation gets long.

═══════════════════════════════════════════════════════════════════════════════
START WORK
═══════════════════════════════════════════════════════════════════════════════

Begin now:
1. Create work log first (dev/logs/[date]_[time]_[task].md)
2. Read dev/claude_rules.md if you haven't already
3. Start task
4. Update log in real-time as you work
5. Report completion when done
```

---

## End of Prompt Template

---

## How to Use This Template

### Step 1: Copy Everything
Copy from "READ FIRST: dev/claude_rules.md" to "Report completion when done"

### Step 2: Fill in the Blanks
Replace ALL [BRACKETS] with your specific information:
- [YYYY-MM-DD] → Today's date (e.g., 2025-01-29)
- [HHMM] → Current time (e.g., 1500)
- [short-task-name] → Brief task description (e.g., bigquery_import)
- [X minutes] → Your time estimates
- [Step 1] → Your actual steps
- [Error type 1] → Actual expected errors

### Step 3: Customize
- Delete sections you don't need (e.g., CHECKPOINTS if task <15 min)
- Add task-specific items to "What NOT to do"
- Adjust timing expectations based on your knowledge
- Choose appropriate git workflow option

### Step 4: Paste into Claude Code
- Open Claude Code
- Paste the filled-out prompt
- Press Enter
- Monitor with `tail -f dev/logs/[today]*.md` in separate terminal

---

## Examples

### Example 1: Short Task (<15 min)
```
READ FIRST: dev/claude_rules.md

TASK: Fix date validation error in read_and_match_bigquery() function

LOGGING: dev/logs/2025-01-29_1430_fix_date_validation.md

SCOPE - WHAT TO DO:
1. Modify R/db_bigquery_import.R line 157
2. Remove unnecessary as.POSIXct() conversion
3. Run tests/test_bigquery_import_FAST.R to verify fix

SCOPE - WHAT NOT TO DO:
- ❌ Don't commit to git yet
- ❌ Don't optimize other parts of the function
- ❌ Don't run full import (just tests)

TIMING EXPECTATIONS:
- Code fix: 2-3 minutes
- Run tests: 1-2 minutes
- Total: 5 minutes max

STOP if takes >10 minutes (something's wrong)

ERROR HANDLING:
- If tests fail: Try up to 2 approaches, then stop and report

GIT WORKFLOW: Feature branch
- Branch: feature/fix-date-validation

SUCCESS CRITERIA:
✅ Date validation no longer takes 52 seconds
✅ All tests pass
✅ Log is complete

START WORK
```

### Example 2: Long Task (30+ min) with Checkpoints
```
READ FIRST: dev/claude_rules.md

TASK: Run full BigQuery import of 19 CSV files (~130M rows)

LOGGING: dev/logs/2025-01-29_1500_bigquery_full_import.md

SCOPE - WHAT TO DO:
1. Run scripts/07_import_bigquery_full.R
2. Log each file's result in real-time
3. Verify final row counts

SCOPE - WHAT NOT TO DO:
- ❌ Don't commit
- ❌ Don't optimize indexes
- ❌ Don't refactor any code
- ❌ Just run the script, nothing else

TIMING EXPECTATIONS:
- Each file: 1-2 minutes
- Total: 20-30 minutes
- STOP if any file >5 minutes

CHECKPOINTS:
After every 5 files:
1. STOP
2. Report: files done, time taken, rows imported
3. Ask: "Continue?"
4. Wait for approval

Intervals:
- After files 1-5: checkpoint
- After files 6-10: checkpoint
- After files 11-15: checkpoint
- After files 16-19: final report

ERROR HANDLING:
Expected (continue):
- Station mismatches <10%
- Invalid dates <1%

Unexpected (STOP):
- Database connection lost
- Out of memory
- >3 files fail

GIT WORKFLOW: No git (just running existing code)

SUCCESS CRITERIA:
✅ All 19 files imported
✅ 127-133M total rows
✅ 89-94% match rate per file
✅ Complete log with all details

START WORK
```

---

## Common Mistakes to Avoid

### ❌ Too Vague:
```
TASK: Make the import faster
```

### ✅ Specific:
```
TASK: Apply vectorization fix to clean_station_name() in R/db_bigquery_import.R
Expected: reduce time from 120s to 2s per file
```

---

### ❌ No Time Expectations:
```
SCOPE - WHAT TO DO:
1. Run the import
```

### ✅ With Expectations:
```
SCOPE - WHAT TO DO:
1. Run scripts/07_import_bigquery_full.R
   Expected: 20-30 minutes for 19 files
   STOP if >40 minutes
```

---

### ❌ Unclear Scope:
```
SCOPE - WHAT TO DO:
1. Import the data and make it work
```

### ✅ Clear Boundaries:
```
SCOPE - WHAT TO DO:
1. Run scripts/07_import_bigquery_full.R
2. Log results
3. Report row counts

SCOPE - WHAT NOT TO DO:
- ❌ Don't optimize indexes
- ❌ Don't add validation
- ❌ Don't refactor code
```

---

## Template Evolution

As you use this template, you'll learn what works. Update this file:
- Add common stop conditions you discover
- Add patterns of things Claude does that you don't want
- Refine timing expectations based on experience
- Add project-specific error types

This template should get BETTER over time based on real usage.

---

## Checklist Before Submitting Prompt

Before pasting into Claude Code, verify:

- [ ] Task is clearly stated in ONE sentence
- [ ] All [BRACKETS] are filled in
- [ ] Timing expectations are realistic
- [ ] Stop conditions are defined
- [ ] Scope boundaries are explicit (what TO do and what NOT to do)
- [ ] Git workflow is chosen
- [ ] Success criteria are measurable
- [ ] Checkpoints defined if task >15 minutes
- [ ] You have `tail -f` ready to monitor the log

If all checked → Ready to paste into Claude Code! 🚀

---

*Keep this template updated as you learn what works best for your workflow.*