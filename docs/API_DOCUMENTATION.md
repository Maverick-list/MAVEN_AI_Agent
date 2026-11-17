# MAVEN AI Agent — API Documentation & Interface Contracts

> **Base URL:** `http://127.0.0.1:8765`  
> **Protocols:** RESTful HTTP JSON & Bi-directional WebSockets  

---

## 1. RESTful HTTP Endpoints

### 1.1 System & Health Telemetry

#### `GET /api/status`
Returns real-time status of all MAVEN subsystems, host OS metrics, and hardware peripherals.

**Response (`application/json`):**
```json
{
  "status": "online",
  "version": "2.2.0",
  "system": {
    "os": "Ubuntu 24.04 LTS",
    "session_type": "wayland",
    "uptime_hours": 3.4
  },
  "resources": {
    "cpu_percent": 1.2,
    "ram_total_gb": 16.0,
    "ram_available_gb": 8.4,
    "ram_used_percent": 47.5,
    "battery_percent": 94,
    "is_charging": true
  },
  "subsystems": {
    "voice_daemon": "active",
    "whisper_server": "online",
    "control_center": "online",
    "vision_camera": "ready"
  }
}
```

---

### 1.2 Cognitive Instruction & Assistant API

#### `POST /api/assistant/chat`
Submit a natural language instruction to `MavenAgentCore` for planning, specialized agent dispatch, or conversational synthesis.

**Request Body (`application/json`):**
```json
{
  "message": "periksa kondisi laptop dan simpan ringkasan",
  "confirmed": false
}
```

**Response (`application/json`):**
```json
{
  "status": "completed",
  "message": "Task completed successfully: periksa kondisi laptop dan simpan ringkasan",
  "intent": {
    "category": "task_execution",
    "action": "system_diagnostics",
    "confidence": 0.95
  },
  "execution": {
    "plan_id": "plan_946447",
    "summary": "Plan completed successfully (3 steps executed).",
    "progress": 100.0
  },
  "response_text": "Diagnostik sistem selesai, Sir. Seluruh subsistem nominal.",
  "elapsed_ms": 217.4
}
```

---

### 1.3 Interactive Step Approval Gate

#### `POST /api/agent/approve`
Approves a gated step in an active DAG task plan.

**Request Body (`application/json`):**
```json
{
  "plan_id": "plan_946447",
  "step_id": 3
}
```

**Response (`application/json`):**
```json
{
  "status": "success",
  "approved_step_id": 3,
  "execution": {
    "status": "completed",
    "summary": "Plan executed to completion."
  }
}
```

#### `POST /api/agent/reject`
Rejects a pending step and halts plan execution.

**Request Body (`application/json`):**
```json
{
  "plan_id": "plan_946447",
  "reason": "Operator rejected terminal launch"
}
```

---

### 1.4 Multimodal Vision & Interaction Mode

#### `POST /api/vision/mode/toggle`
Toggles between Normal Mode (physical keyboard/mouse input) and Vision Control Mode (camera hand gestures).

**Response (`application/json`):**
```json
{
  "status": "success",
  "active_mode": "vision",
  "camera_node": "/dev/video0",
  "fps": 30
}
```

#### `POST /api/vision/emergency-stop`
Synchronously activates global Emergency Stop.

**Response (`application/json`):**
```json
{
  "status": "success",
  "action": "emergency_stop_all_engaged",
  "elapsed_ms": 1.8
}
```

---

## 2. WebSocket Telemetry Stream

### `WS /ws/telemetry`
High-speed bi-directional telemetry and audio waveform streaming for HUD gauges.

**Connection Protocol:**
```javascript
const ws = new WebSocket("ws://127.0.0.1:8765/ws/telemetry");

ws.onmessage = (event) => {
  const payload = JSON.parse(event.data);
  console.log("Telemetry Frame:", payload);
};
```

**Streamed Event Frame (`telemetry_update`):**
```json
{
  "type": "telemetry",
  "timestamp": 1794044946.69,
  "cpu_percent": 2.4,
  "memory": {
    "available_gb": 7.42,
    "percent": 48.2
  },
  "battery": {
    "percent": 90,
    "charging": true
  },
  "voice_state": "idle",
  "vision_active": false,
  "active_plan": null
}
```

---

## 3. Command-Line Interface (CLI)

The `maven` binary provides direct developer control from any terminal:

```bash
# Start the full Maven JARVIS ecosystem (HUD + Voice Daemon)
maven start

# Start the background voice daemon only (headless mode)
maven voice daemon

# Check live health status of all subsystems
maven status

# Halt all background services
maven stop

# Stream live activity logs
maven logs -f
```
