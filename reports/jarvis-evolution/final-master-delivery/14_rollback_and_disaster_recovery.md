# MAVEN JARVIS — ROLLBACK & DISASTER RECOVERY GUIDE
**Worktree:** `/home/firza-ilmi/Maverick-DevOS-evolution`  
**Safety Status:** Master Worktree (`/home/firza-ilmi/Maverick-DevOS`) remains completely untouched and isolated on commit `f47dbd1`.  

---

## 1. Safety Isolation Architecture
All development, neural model caching, and hardware integration occurred strictly inside the dedicated evolution worktree `/home/firza-ilmi/Maverick-DevOS-evolution` on branch `feature/jarvis-evolution`.

The production master environment `/home/firza-ilmi/Maverick-DevOS` and the active 7-Day Usage Trial monitor (PID 14783) were completely untouched.

---

## 2. Fast Rollback Procedures

### Scenario A: Reverting Evolution Worktree to Prior Tagged State
If it is ever necessary to return `feature/jarvis-evolution` to its state prior to today's upgrades:
```bash
cd /home/firza-ilmi/Maverick-DevOS-evolution

# Check out checkpoint tag created prior to master remediation
git checkout checkpoint-pre-remediation
```

### Scenario B: Emergency Halt of All Active Services
If an automation script enters an unexpected state:
1. **Via Web Dashboard:** Click the red `🛑 E-STOP` button in the top status cluster.
2. **Via Physical Keyboard:** Press `Super + Shift + Escape` (Emergency Stop Hotkey).
3. **Via Physical Terminal:**
```bash
# Emergency kill of any lingering virtual mouse, camera, or voice subprocesses
pkill -f "maverick.voice"
pkill -f "maverick.vision"
fuser -k /dev/video0
```

---

## 3. Persistent State Reset
If SQLite task databases or audio settings require a factory reset:
```bash
# Reset DAG Task Store without affecting other configs
rm -f ~/.local/share/maverick/task_store.db*

# Reset Voice Settings to safe defaults
cat << 'EOF' > ~/.config/maverick/voice_settings.json
{
  "tts_engine": "local_neural",
  "local_neural_voice": "george",
  "tts_default_language": "en"
}
EOF
chmod 0600 ~/.config/maverick/voice_settings.json
```
