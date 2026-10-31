# Maven JARVIS — Rollback & Disaster Recovery Guide
**Safe Reversion Procedures & Operational Safeguards**
*Document Version: 1.0.0 | Date: October 31, 2026 | Environment: Ubuntu 26.04.1 LTS (Wayland)*

---

## 1. Executive Summary

A core operational principle of the **Maven JARVIS Evolution** is absolute preservation of existing system stability and zero disruption to the running 7-Day Real-World Usage Trial.

All modifications, tool expansions, and architectural upgrades are developed and tested within an **isolated Git worktree** (`/home/firza-ilmi/Maverick-DevOS-evolution` on branch `feature/jarvis-evolution`). The primary production repository (`/home/firza-ilmi/Maverick-DevOS` on branch `master`) and its active daemons remain untouched.

In the event of an unexpected regression, unstable daemon behavior, or operational hazard, this guide provides deterministic, step-by-step procedures to revert state instantaneously.

---

## 2. Fast Rollback Procedure (Worktree Isolation)

Because evolution work is encapsulated within a separate worktree, a complete rollback to the exact pre-evolution state requires no code modifications or destructive git actions:

### Step 1: Terminate Any Evolution Scratch Processes
If any benchmark script or development test process is running:
```bash
pkill -f "run_jarvis_evolution_benchmark.py"
```

### Step 2: Detach and Remove the Evolution Worktree
```bash
cd /home/firza-ilmi/Maverick-DevOS
git worktree remove /home/firza-ilmi/Maverick-DevOS-evolution --force
```

### Step 3: Remove the Evolution Feature Branch (Optional)
```bash
git branch -D feature/jarvis-evolution
```

---

## 3. Production Daemon Health Verification

After any rollback action, verify that the primary 7-Day Trial processes on `master` are intact and running healthy:

```bash
ps aux | grep -E "trial_monitor|dashboard|desktop\.app|whisper|voice" | grep -v grep
```

Expected healthy process roster:
1. `whisper-server` (Port `18791`)
2. `maverick.cli voice daemon`
3. `maverick.cli dashboard --port 8765`
4. `maverick.desktop.app`
5. `trial_monitor.py run --interval 15.0`

### Step 4: Verify 7-Day Trial Log Integrity
Check that trial logs have not been modified or corrupted:
```bash
tail -n 5 /home/firza-ilmi/Maverick-DevOS/reports/7-day-trial/day1_activity.jsonl
```

---

## 4. In-Place Reversion (If Merged to Master)

If changes from `feature/jarvis-evolution` are merged to `master` and subsequently require reversion:

### Safe Git Revert
```bash
cd /home/firza-ilmi/Maverick-DevOS
git revert --no-commit HEAD~3..HEAD
git commit -m "revert: rollback jarvis evolution enhancements to commit f47dbd1"
```

### Clean Artifact Scratch Files
Remove temporary benchmark project files created during validation:
```bash
rm -rf ~/projects/JarvisBenchmark
```

### Restore SQLite Task Database
If task database corruption is suspected:
```bash
cp ~/.maverick/tasks.db ~/.maverick/tasks.db.bak_$(date +%s)
sqlite3 ~/.maverick/tasks.db "DELETE FROM orchestrated_plans WHERE plan_id LIKE 'plan_%';"
```
