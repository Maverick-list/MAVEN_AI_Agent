/* MAVEN JARVIS // Holographic Control Center Runtime & Core Physics Engine */

(() => {
  "use strict";

  // --- Runtime State ---
  const state = {
    connected: false,
    liveState: "idle",
    visualOverride: "live", // 'live' or manual state inspection
    daemonRunning: false,
    wakeArmed: false,
    liveRms: 0.0,
    noiseFloor: 0.0,
    speakReplies: true,
    micHistory: new Array(32).fill(0.03),
    lastSnapshot: null,
    voicesLoaded: false,
  };

  // --- Web Audio API FFT Synchronizer ---
  const audioEl = document.getElementById("jarvis-tts-audio");
  let audioCtx = null;
  let analyser = null;
  let freqData = null;
  let browserAudioPlaying = false;

  function ensureAudioAnalyser() {
    if (audioCtx) {
      if (audioCtx.state === "suspended") {
        audioCtx.resume().catch(() => {});
      }
      return;
    }
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    try {
      audioCtx = new Ctx();
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.78;
      const source = audioCtx.createMediaElementSource(audioEl);
      source.connect(analyser);
      analyser.connect(audioCtx.destination);
      freqData = new Uint8Array(analyser.frequencyBinCount);
    } catch (_) {
      analyser = null;
    }
  }

  audioEl.addEventListener("play", () => {
    browserAudioPlaying = true;
  });
  audioEl.addEventListener("ended", () => {
    browserAudioPlaying = false;
  });
  audioEl.addEventListener("pause", () => {
    browserAudioPlaying = false;
  });

  function playStreamedAudio(url) {
    ensureAudioAnalyser();
    audioEl.src = url;
    audioEl.play().catch((err) => {
      showToast(`Browser autoplay blocked (${err.name}); click anywhere and retry.`);
    });
  }

  // --- Toast Helper ---
  let toastTimer = null;
  function showToast(msg, durationMs = 3400) {
    const el = document.getElementById("hud-toast");
    if (!el) return;
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.hidden = true;
    }, durationMs);
  }

  // --- Clock ---
  function updateClock() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    const ss = String(now.getSeconds()).padStart(2, "0");
    const clockEl = document.getElementById("clock-time");
    if (clockEl) clockEl.textContent = `${hh}:${mm}:${ss}`;
  }
  setInterval(updateClock, 1000);
  updateClock();

  // --- Initialize Static Bar Grids ---
  const coresContainer = document.getElementById("cores-bars");
  const ramSegmentsContainer = document.getElementById("ram-segments");
  const micSpectrumContainer = document.getElementById("mic-spectrum");

  function initBarGrids(coreCount = 16) {
    coresContainer.innerHTML = "";
    for (let i = 0; i < coreCount; i++) {
      const track = document.createElement("div");
      track.className = "core-bar-track";
      const fill = document.createElement("div");
      fill.className = "core-bar-fill";
      fill.style.height = "10%";
      track.appendChild(fill);
      coresContainer.appendChild(track);
    }

    ramSegmentsContainer.innerHTML = "";
    for (let i = 0; i < 24; i++) {
      const seg = document.createElement("div");
      seg.className = "ram-seg";
      ramSegmentsContainer.appendChild(seg);
    }

    micSpectrumContainer.innerHTML = "";
    for (let i = 0; i < 32; i++) {
      const bar = document.createElement("div");
      bar.className = "spec-bar";
      bar.style.height = "12%";
      micSpectrumContainer.appendChild(bar);
    }
  }
  initBarGrids(16);

  // --- Effective Visual State ---
  function getEffectiveState() {
    if (state.visualOverride && state.visualOverride !== "live") {
      return state.visualOverride;
    }
    if (browserAudioPlaying) {
      return "speaking";
    }
    return state.liveState || "idle";
  }

  // --- Bind Real-Time Telemetry Snapshot ---
  let renderedConvSignature = "";

  function applySnapshot(snap) {
    if (!snap || snap.status !== "success") return;
    state.lastSnapshot = snap;

    const tzEl = document.getElementById("clock-tz");
    if (tzEl && snap.timezone) tzEl.textContent = snap.timezone;

    // 1. Assistant & Core Status
    const asst = snap.assistant || {};
    state.liveState = asst.state || "idle";
    state.daemonRunning = Boolean(asst.daemon_running);
    state.wakeArmed = Boolean(asst.wake_armed);
    state.liveRms = Number(asst.rms || 0);
    state.noiseFloor = Number(asst.noise_floor || 0);

    // Push live RMS sample into rolling 32-bar microphone spectrum
    const normRms = Math.min(1.0, Math.max(0.03, state.liveRms * 1.45));
    state.micHistory.push(normRms);
    if (state.micHistory.length > 32) state.micHistory.shift();

    const effState = getEffectiveState();
    document.body.setAttribute("data-state", effState);

    const statePillLabel = document.getElementById("core-state-label");
    if (statePillLabel) {
      const suffix =
        state.visualOverride !== "live"
          ? "INSPECT MODE"
          : effState === "speaking"
          ? (snap.tts?.last_used_engine === "elevenlabs" ? "ELEVENLABS STREAM" : "VOICE OUTPUT")
          : effState === "thinking"
          ? "GEMINI 2.5 FLASH"
          : state.wakeArmed
          ? "WAKE ARMED"
          : state.daemonRunning
          ? "MUTED"
          : "DAEMON STOPPED";
      statePillLabel.textContent = `${effState.toUpperCase()} · ${suffix}`;
    }

    const coreCap = document.getElementById("core-telemetry-caption");
    if (coreCap) {
      if (state.daemonRunning) {
        coreCap.textContent = `PID ${asst.pid} · RSS ${asst.rss_mb} MiB · Daemon CPU ${asst.cpu_percent}% · Floor ${state.noiseFloor.toFixed(3)}`;
      } else {
        coreCap.textContent = `Voice daemon offline · Click [ START ] to activate continuous wake-word listening`;
      }
    }

    // 2. Top Bar Profile & Display Session
    const sys = snap.system || {};
    const osInfo = sys.os || {};
    const prof = sys.profile || {};
    const sessionType = (osInfo.session_type || "linux").toUpperCase();
    const profName = (prof.display_name || "Developer Mode").toUpperCase();
    document.getElementById("system-mode-label").textContent = `${profName} · ${sessionType}`;

    // 3. Left Panel — System Status, CPU, Per-Core, RAM, Battery
    const daemonLine = document.getElementById("daemon-status-line");
    daemonLine.textContent = state.daemonRunning
      ? `ONLINE · PID ${asst.pid}`
      : `STOPPED · READY TO START`;

    const bat = sys.battery || {};
    const batBadge = document.getElementById("battery-badge");
    if (bat.has_battery && bat.percent != null) {
      batBadge.textContent = `${Math.round(bat.percent)}%${bat.is_charging ? " ⚡" : ""}`;
      batBadge.className = `mini-badge ${bat.percent < 20 && !bat.is_charging ? "warn" : "ok"}`;
    } else {
      batBadge.textContent = "AC POWER";
    }

    const cpu = sys.cpu || {};
    const cpuPct = Number(cpu.usage_percent || 0);
    const logicalCores = Number(cpu.cores_logical || 16);
    const physCores = Number(cpu.cores_physical || logicalCores);
    document.getElementById("cpu-percent-text").textContent = `${cpuPct.toFixed(1)}% · ${physCores}C`;
    document.getElementById("cores-header").textContent = `CORES · ${logicalCores} THREADS`;

    // Donut circumference = 2 * pi * 40 = 251.3
    const arcOffset = 251.3 * (1 - Math.min(100, Math.max(0, cpuPct)) / 100);
    document.getElementById("cpu-donut-arc").style.strokeDashoffset = arcOffset.toFixed(1);

    const perCore = Array.isArray(cpu.per_core) ? cpu.per_core : [];
    const barCount = Math.min(perCore.length || 16, 24);
    if (coresContainer.children.length !== barCount && barCount > 0) {
      initBarGrids(barCount);
    }
    for (let i = 0; i < coresContainer.children.length; i++) {
      const fill = coresContainer.children[i].firstElementChild;
      const val = Number(perCore[i] || 0);
      fill.style.height = `${Math.max(8, Math.min(100, val))}%`;
    }

    const mem = sys.memory || {};
    const totalGb = Number(mem.total_gb || 0);
    const availGb = Number(mem.available_gb || 0);
    const usedGb = Math.max(0, totalGb - availGb);
    const memPct = Number(mem.percent || 0);
    document.getElementById("ram-used-total").textContent = `${usedGb.toFixed(1)} / ${totalGb.toFixed(1)} GiB`;
    document.getElementById("ram-avail-label").textContent = `${availGb.toFixed(2)} GiB avail`;

    const litCount = Math.round((Math.min(100, Math.max(0, memPct)) / 100) * 24);
    const segs = ramSegmentsContainer.children;
    for (let i = 0; i < segs.length; i++) {
      if (i < litCount) {
        segs[i].className = memPct >= 86 ? "ram-seg lit-high" : "ram-seg lit";
      } else {
        segs[i].className = "ram-seg";
      }
    }

    // 4. Left Panel — Microphone & Audio Output
    const audio = snap.audio || {};
    const inName = (audio.default_input || "DISCONNECTED").toUpperCase();
    document.getElementById("mic-device-line").textContent =
      `${inName.slice(0, 22)} · FLOOR ${state.noiseFloor.toFixed(2)}`;

    const vadBadge = document.getElementById("mic-vad-badge");
    vadBadge.textContent = asst.muted ? "MUTED" : (asst.vad || "QUIET");
    vadBadge.className = `mini-badge ${asst.muted ? "warn" : asst.vad === "SPEECH_BURST" ? "ok" : ""}`;

    const specBars = micSpectrumContainer.children;
    for (let i = 0; i < specBars.length; i++) {
      const h = Math.max(10, Math.min(100, state.micHistory[i] * 100));
      specBars[i].style.height = `${h.toFixed(0)}%`;
    }

    if (audio.last_mic_test && audio.last_mic_test.verdict) {
      document.getElementById("mic-foot-note").textContent = `Last test: ${audio.last_mic_test.verdict}`;
    }

    const outName = (audio.default_output || "NO SPEAKER DETECTED").toUpperCase();
    document.getElementById("speaker-device-name").textContent = outName.slice(0, 28);
    document.getElementById("speaker-subline").textContent = audio.has_speaker
      ? `PIPEWIRE SINK · STREAM READY`
      : `OUTPUT UNAVAILABLE`;

    const sttReady = audio.whisper_stt?.ready;
    document.getElementById("whisper-stt-line").textContent = sttReady
      ? `STT: Whisper.cpp (ggml-tiny.bin) · EN & ID Ready`
      : `STT: ${audio.whisper_stt?.detail || "Unavailable"}`;

    // 5. Right Panel — AI Gateway & Conversation History
    const gw = snap.ai_gateway || {};
    const gwActive = Boolean(gw.openclaw_active);
    const modelShort = (gw.primary_model || "google/gemini-2.5-flash").replace("google/", "").toUpperCase();
    document.getElementById("gateway-status-line").textContent =
      `${modelShort} · ${gwActive ? "OPENCLAW ACTIVE" : "GATEWAY OFFLINE"}`;

    const ch = gw.channels || {};
    const chParts = [];
    if (ch.telegram_enabled) chParts.push("TG");
    if (ch.discord_enabled) chParts.push("DC");
    const chBadge = document.getElementById("channels-badge");
    chBadge.textContent = chParts.length ? `${chParts.join(" · ")} ON` : "LOCAL";
    chBadge.className = `mini-badge ${gwActive ? "ok" : "warn"}`;

    renderConversations(snap.conversations || []);

    // 6. Right Panel — Current Activity & Security Gates
    const act = snap.activity || {};
    const sec = snap.security || {};
    const recentActions = act.recent_actions || [];
    if (recentActions.length > 0) {
      const latest = recentActions[0];
      const actLabel = String(latest.action_type || "activity").replace(/_/g, " ").toUpperCase();
      const tgt = latest.target ? ` · ${String(latest.target).slice(0, 18).toUpperCase()}` : "";
      document.getElementById("current-activity-title").textContent = `${actLabel}${tgt}`;
    } else {
      document.getElementById("current-activity-title").textContent =
        `MONITORING DESKTOP · ${effState.toUpperCase()}`;
    }

    const gateTxt = sec.confirmation_gate_armed ? "CONFIRMATION GATE ARMED" : "GATE UNARMED";
    const waTxt = sec.whatsapp_disabled ? "WHATSAPP OFF" : "WHATSAPP CHECK";
    document.getElementById("security-posture-line").textContent = `${gateTxt} · ${waTxt}`;

    const runningApps = act.running_apps || [];
    const appNames = runningApps.map((a) => a.display_name || a.app_id).join(", ");
    document.getElementById("running-apps-line").textContent = runningApps.length
      ? `Running (${runningApps.length}): ${appNames}`
      : `No authorized desktop apps running`;

    // 7. Right Panel — Voice Engine Status
    const tts = snap.tts || {};
    const el = tts.elevenlabs || {};
    const fb = tts.fallback || {};
    const ttsTitle = document.getElementById("tts-engine-title");
    const ttsSub = document.getElementById("tts-engine-subline");
    const ttsBadge = document.getElementById("tts-health-badge");
    const ttsFoot = document.getElementById("tts-fallback-line");

    if (tts.preferred_engine === "elevenlabs" && el.configured) {
      ttsTitle.textContent = "ELEVENLABS";
      const modelTag = String(el.model_id || "multilingual_v2").replace("eleven_", "").replace(/_/g, " ").toUpperCase();
      ttsSub.textContent = `${el.voice_name.toUpperCase()} · ${modelTag}`;
      if (el.last_error_code) {
        ttsBadge.textContent = "FALLBACK";
        ttsBadge.className = "mini-badge warn";
        ttsFoot.textContent = `Fallback active (${el.last_error_code}) → spd-say`;
      } else {
        ttsBadge.textContent = "READY";
        ttsBadge.className = "mini-badge ok";
        const lat = el.last_latency_ms ? ` · TTFB ${el.last_latency_ms}ms` : "";
        ttsFoot.textContent = `Auto-fallback: spd-say ${fb.available ? "ready" : "missing"}${lat}`;
      }
    } else if (tts.preferred_engine === "elevenlabs" && !el.configured) {
      ttsTitle.textContent = "ELEVENLABS (STANDBY)";
      ttsSub.textContent = "ACTIVE FALLBACK · SPEECH DISPATCHER";
      ttsBadge.textContent = "KEY NEEDED";
      ttsBadge.className = "mini-badge warn";
      ttsFoot.textContent = el.hint || "Set sk_... key in ~/.config/maverick/elevenlabs.env";
    } else {
      ttsTitle.textContent = "SPEECH DISPATCHER";
      ttsSub.textContent = "LOCAL OFFLINE TTS · SPD-SAY";
      ttsBadge.textContent = fb.available ? "ONLINE" : "MISSING";
      ttsBadge.className = `mini-badge ${fb.available ? "ok" : "warn"}`;
      ttsFoot.textContent = "Zero-latency local synthesis (EN & ID)";
    }

    // Update live logs drawer if open
    const logsModal = document.getElementById("logs-modal");
    if (!logsModal.hidden) {
      renderLogs(act.recent_logs || []);
    }
  }

  function renderConversations(items) {
    const sig = JSON.stringify(items.map((x) => `${x.id}:${x.status}`));
    if (sig === renderedConvSignature) return;
    renderedConvSignature = sig;

    const box = document.getElementById("conversation-stream");
    box.innerHTML = "";
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "chat-empty";
      empty.innerHTML = 'Awaiting voice or text interaction. Say <strong>"Hey Maven"</strong> or type below.';
      box.appendChild(empty);
      return;
    }

    for (const item of items.slice(-16)) {
      const wrap = document.createElement("div");
      const roleClass = item.role === "user" ? "role-user" : "role-maven";
      const statusClass = item.status ? `status-${item.status}` : "";
      wrap.className = `chat-bubble ${roleClass} ${statusClass}`;

      const meta = document.createElement("div");
      meta.className = "bubble-meta";
      const who = document.createElement("span");
      who.textContent = item.role === "user" ? "● User" : "◈ Maven";
      const ts = document.createElement("span");
      ts.textContent = item.timestamp || "";
      meta.appendChild(who);
      meta.appendChild(ts);

      const txt = document.createElement("div");
      txt.className = "bubble-text";
      txt.textContent = item.text || "";

      wrap.appendChild(meta);
      wrap.appendChild(txt);

      if (item.requires_confirmation && item.pending_command) {
        const actions = document.createElement("div");
        actions.className = "confirm-gate-actions";

        const btnOk = document.createElement("button");
        btnOk.type = "button";
        btnOk.className = "ghost-chip";
        btnOk.textContent = "✔ CONFIRM EXECUTION";
        btnOk.addEventListener("click", () => {
          btnOk.disabled = true;
          submitCommand(item.pending_command, true);
        });

        const btnCancel = document.createElement("button");
        btnCancel.type = "button";
        btnCancel.className = "ghost-chip";
        btnCancel.textContent = "✕ CANCEL";
        btnCancel.addEventListener("click", () => {
          actions.remove();
          showToast("Consequential action cancelled.");
        });

        actions.appendChild(btnOk);
        actions.appendChild(btnCancel);
        wrap.appendChild(actions);
      }

      box.appendChild(wrap);
    }
    box.scrollTop = box.scrollHeight;
  }

  function renderLogs(logs) {
    const term = document.getElementById("live-log-terminal");
    term.innerHTML = "";
    if (!logs.length) {
      term.textContent = "No structured telemetry entries yet.";
      return;
    }
    for (const row of logs) {
      const div = document.createElement("div");
      div.className = "log-row";
      const ts = document.createElement("span");
      ts.className = "log-ts";
      ts.textContent = `[${row.timestamp}] `;
      const sub = document.createElement("span");
      sub.className = "log-sub";
      sub.textContent = `[${row.subsystem}] `;
      const msg = document.createElement("span");
      msg.className = `log-lvl-${row.level}`;
      msg.textContent = row.message;
      div.appendChild(ts);
      div.appendChild(sub);
      div.appendChild(msg);
      term.appendChild(div);
    }
    term.scrollTop = term.scrollHeight;
  }

  // --- API Helpers & SSE Connection ---
  async function apiPost(path, body = {}) {
    const resp = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return resp.json();
  }

  function setConnectionStatus(online) {
    state.connected = online;
    const dot = document.getElementById("connection-dot");
    const label = document.getElementById("connection-label");
    if (online) {
      dot.classList.remove("offline");
      label.textContent = "127.0.0.1 LOCAL LINK · ACTIVE";
    } else {
      dot.classList.add("offline");
      label.textContent = "127.0.0.1 LOCAL LINK · RECONNECTING";
    }
  }

  function connectSSE() {
    const es = new EventSource("/api/events");
    es.addEventListener("telemetry", (ev) => {
      setConnectionStatus(true);
      try {
        applySnapshot(JSON.parse(ev.data));
      } catch (_) {}
    });
    es.onerror = () => {
      setConnectionStatus(false);
      es.close();
      setTimeout(connectSSE, 2000);
    };
  }

  // Initial snapshot fetch + SSE stream
  fetch("/api/status")
    .then((r) => r.json())
    .then((snap) => {
      setConnectionStatus(true);
      applySnapshot(snap);
    })
    .catch(() => setConnectionStatus(false));
  connectSSE();

  // --- Interactive Controls ---
  async function handleDaemonControl(action, btn) {
    btn.disabled = true;
    showToast(`Executing daemon ${action.toUpperCase()}...`);
    try {
      const res = await apiPost(`/api/daemon/${action}`);
      if (res.status === "success") {
        showToast(
          res.daemon_running
            ? `Maven Voice Daemon active (PID ${res.pid})`
            : `Maven Voice Daemon stopped`
        );
      } else {
        showToast(`Daemon ${action} notice: ${res.message || res.status}`);
      }
    } catch (err) {
      showToast(`Daemon control error: ${err.message}`);
    } finally {
      btn.disabled = false;
    }
  }

  document.getElementById("btn-daemon-start").addEventListener("click", (e) => handleDaemonControl("start", e.currentTarget));
  document.getElementById("btn-daemon-stop").addEventListener("click", (e) => handleDaemonControl("stop", e.currentTarget));
  document.getElementById("btn-daemon-restart").addEventListener("click", (e) => handleDaemonControl("restart", e.currentTarget));

  document.getElementById("btn-mic-test").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    showToast("Sampling live microphone input for 1.8s — speak now...");
    try {
      const res = await apiPost("/api/audio/test-mic", { duration_sec: 1.8 });
      if (res.status === "success" && Array.isArray(res.rms_series)) {
        for (const r of res.rms_series) {
          state.micHistory.push(Math.min(1.0, Math.max(0.03, r * 1.6)));
          if (state.micHistory.length > 32) state.micHistory.shift();
        }
        showToast(`Mic OK: ${res.verdict}`);
      } else {
        showToast(`Mic test error: ${res.message || "failed"}`);
      }
    } catch (err) {
      showToast(`Mic test failed: ${err.message}`);
    } finally {
      btn.disabled = false;
    }
  });

  async function triggerVoicePreview(text, lang, overrides = null) {
    ensureAudioAnalyser();
    showToast(`Synthesizing ${lang === "id" ? "Indonesian" : "English"} voice preview...`);
    try {
      const res = await apiPost("/api/voice/test", {
        text,
        lang,
        browser_audio: true,
        overrides,
      });
      if (res.status === "success") {
        if (res.audio_url) {
          playStreamedAudio(res.audio_url);
          showToast(`Streaming ElevenLabs neural voice (TTFB ${res.latency_ms || "--"}ms)`);
        } else {
          const reason = res.fallback_reason ? ` [fallback: ${res.fallback_reason}]` : "";
          showToast(`Speaking via local Speech Dispatcher${reason}`);
        }
      } else {
        showToast(`Voice test failed: ${res.message || "error"}`);
      }
    } catch (err) {
      showToast(`Voice test error: ${err.message}`);
    }
  }

  document.getElementById("btn-voice-test").addEventListener("click", () => {
    const lang = document.getElementById("voice-test-lang").value;
    triggerVoicePreview(null, lang);
  });

  // Speak replies toggle
  const speakToggleBtn = document.getElementById("btn-toggle-speak-reply");
  speakToggleBtn.addEventListener("click", () => {
    state.speakReplies = !state.speakReplies;
    speakToggleBtn.classList.toggle("active", state.speakReplies);
    speakToggleBtn.setAttribute("aria-pressed", String(state.speakReplies));
    speakToggleBtn.textContent = state.speakReplies ? "🔊" : "🔇";
    showToast(state.speakReplies ? "Spoken replies enabled" : "Spoken replies muted");
  });

  // Conversation Command Form
  async function submitCommand(text, confirmed = false) {
    ensureAudioAnalyser();
    const clean = (text || "").trim();
    if (!clean) return;
    try {
      const res = await apiPost("/api/command", {
        text: clean,
        confirmed,
        speak: state.speakReplies,
        browser_audio: true,
      });
      if (res.tts_delivery && res.tts_delivery.audio_url) {
        playStreamedAudio(res.tts_delivery.audio_url);
      }
      if (res.requires_confirmation) {
        showToast("Security gate triggered: confirm action in the conversation panel.");
      }
    } catch (err) {
      showToast(`Command error: ${err.message}`);
    }
  }

  document.getElementById("command-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const input = document.getElementById("command-input");
    const val = input.value.trim();
    if (!val) return;
    input.value = "";
    submitCommand(val, false);
  });

  // --- Modals: Settings & Live Logs ---
  const settingsModal = document.getElementById("settings-modal");
  const logsModal = document.getElementById("logs-modal");

  async function openSettingsModal() {
    settingsModal.hidden = false;
    const snap = state.lastSnapshot;
    const tts = snap?.tts || {};
    const el = tts.elevenlabs || {};
    const settings = el.settings || {};

    const banner = document.getElementById("elevenlabs-key-banner");
    if (el.configured) {
      banner.className = "env-security-banner";
      banner.textContent = "✔ ELEVENLABS_API_KEY verified in secure local environment (never exposed to browser or logs).";
    } else {
      banner.className = "env-security-banner warn";
      banner.textContent = `⚠ ${el.hint || "Set ELEVENLABS_API_KEY=sk_... in ~/.config/maverick/elevenlabs.env"}. Automatic Speech Dispatcher fallback is active.`;
    }

    document.getElementById("set-tts-engine").value = tts.preferred_engine || "elevenlabs";
    document.getElementById("set-voice-id").value = el.voice_id || "onwK4e9ZLuTAKqWW03F9";

    // Populate models
    const modelSel = document.getElementById("set-model-id");
    modelSel.innerHTML = "";
    for (const m of el.models || []) {
      const opt = document.createElement("option");
      opt.value = m.model_id;
      opt.textContent = m.name;
      modelSel.appendChild(opt);
    }
    if (el.model_id) modelSel.value = el.model_id;

    // Populate presets + remote account voices
    const presetSel = document.getElementById("set-voice-preset");
    const populateVoices = (voices) => {
      presetSel.innerHTML = "";
      for (const v of voices) {
        const opt = document.createElement("option");
        opt.value = v.voice_id;
        opt.textContent = `${v.name}${v.accent ? ` · ${v.accent}` : ""}`;
        presetSel.appendChild(opt);
      }
      presetSel.value = el.voice_id || "onwK4e9ZLuTAKqWW03F9";
    };
    populateVoices(el.presets || []);

    if (!state.voicesLoaded) {
      fetch("/api/voice/voices")
        .then((r) => r.json())
        .then((data) => {
          if (Array.isArray(data.voices) && data.voices.length) {
            populateVoices(data.voices);
            state.voicesLoaded = true;
          }
        })
        .catch(() => {});
    }

    const stab = Number(settings.stability ?? 0.55);
    const sim = Number(settings.similarity_boost ?? 0.80);
    const sty = Number(settings.style ?? 0.15);
    const spd = Number(settings.speed ?? 1.0);

    document.getElementById("set-stability").value = stab;
    document.getElementById("val-stability").textContent = stab.toFixed(2);
    document.getElementById("set-similarity").value = sim;
    document.getElementById("val-similarity").textContent = sim.toFixed(2);
    document.getElementById("set-style").value = sty;
    document.getElementById("val-style").textContent = sty.toFixed(2);
    document.getElementById("set-speed").value = spd;
    document.getElementById("val-speed").textContent = `${spd.toFixed(2)}x`;

    const activeProf = snap?.system?.profile?.profile || "developer";
    document.getElementById("set-profile").value = activeProf;
    document.getElementById("set-visual-override").value = state.visualOverride;
  }

  document.getElementById("btn-open-settings").addEventListener("click", openSettingsModal);
  document.getElementById("btn-close-settings").addEventListener("click", () => {
    settingsModal.hidden = true;
  });

  document.getElementById("set-voice-preset").addEventListener("change", (e) => {
    document.getElementById("set-voice-id").value = e.target.value;
  });

  for (const [inputId, labelId, suffix] of [
    ["set-stability", "val-stability", ""],
    ["set-similarity", "val-similarity", ""],
    ["set-style", "val-style", ""],
    ["set-speed", "val-speed", "x"],
  ]) {
    document.getElementById(inputId).addEventListener("input", (e) => {
      document.getElementById(labelId).textContent = `${Number(e.target.value).toFixed(2)}${suffix}`;
    });
  }

  document.getElementById("set-visual-override").addEventListener("change", (e) => {
    state.visualOverride = e.target.value;
    if (state.lastSnapshot) applySnapshot(state.lastSnapshot);
  });

  function gatherFormOverrides() {
    return {
      voice_id: document.getElementById("set-voice-id").value.trim(),
      model_id: document.getElementById("set-model-id").value,
      stability: Number(document.getElementById("set-stability").value),
      similarity_boost: Number(document.getElementById("set-similarity").value),
      style: Number(document.getElementById("set-style").value),
      speed: Number(document.getElementById("set-speed").value),
    };
  }

  document.getElementById("btn-preview-en").addEventListener("click", () => {
    const phrase =
      "Good afternoon. All Maven JARVIS subsystems are calibrated and operating nominally.";
    document.getElementById("preview-phrase-input").value = phrase;
    triggerVoicePreview(phrase, "en", gatherFormOverrides());
  });

  document.getElementById("btn-preview-id").addEventListener("click", () => {
    const phrase = document.getElementById("preview-phrase-input").value.trim() ||
      "Selamat siang. Sistem kecerdasan Maven JARVIS siap membantu Anda.";
    triggerVoicePreview(phrase, "id", gatherFormOverrides());
  });

  document.getElementById("btn-stop-tts").addEventListener("click", async () => {
    audioEl.pause();
    audioEl.currentTime = 0;
    await apiPost("/api/voice/stop");
    showToast("Audio playback stopped.");
  });

  document.getElementById("btn-save-settings").addEventListener("click", async () => {
    const ovr = gatherFormOverrides();
    const payload = {
      tts_engine: document.getElementById("set-tts-engine").value,
      elevenlabs_voice_id: ovr.voice_id,
      elevenlabs_model_id: ovr.model_id,
      elevenlabs_stability: ovr.stability,
      elevenlabs_similarity_boost: ovr.similarity_boost,
      elevenlabs_style: ovr.style,
      elevenlabs_speed: ovr.speed,
      profile: document.getElementById("set-profile").value,
    };
    const res = await apiPost("/api/voice/settings", payload);
    if (res.status === "success") {
      showToast("Voice & profile configuration saved.");
      settingsModal.hidden = true;
    }
  });

  document.getElementById("btn-open-logs").addEventListener("click", () => {
    logsModal.hidden = false;
    renderLogs(state.lastSnapshot?.activity?.recent_logs || []);
  });
  document.getElementById("btn-close-logs").addEventListener("click", () => {
    logsModal.hidden = true;
  });

  // =========================================================================
  // THE CENTRAL JARVIS HOLOGRAPHIC CORE — 60FPS MULTILAYERED CANVAS ENGINE
  // =========================================================================
  const canvas = document.getElementById("jarvis-core-canvas");
  const ctx = canvas.getContext("2d");

  const STATE_PALETTES = {
    idle:      { primary: [0, 240, 255],   secondary: [125, 211, 252], core: [139, 92, 246],  spin: 0.24, scale: 1.0,  pulseAmp: 0.03 },
    listening: { primary: [0, 248, 255],   secondary: [56, 189, 248],  core: [167, 139, 250], spin: 0.55, scale: 1.05, pulseAmp: 0.06 },
    thinking:  { primary: [139, 92, 246],  secondary: [0, 240, 255],   core: [196, 181, 253], spin: 1.65, scale: 0.97, pulseAmp: 0.08 },
    speaking:  { primary: [0, 245, 255],   secondary: [165, 243, 252], core: [255, 255, 255], spin: 0.92, scale: 1.08, pulseAmp: 0.14 },
    error:     { primary: [239, 68, 68],   secondary: [245, 158, 11],  core: [252, 165, 165], spin: 0.18, scale: 0.98, pulseAmp: 0.07 },
  };

  // Spring-interpolated visual parameters for seamless morphing
  const anim = {
    primary: [0, 240, 255],
    secondary: [125, 211, 252],
    core: [139, 92, 246],
    spin: 0.24,
    scale: 1.0,
    energy: 0.05,
    angles: [0, 1.1, 2.3, 0.7, 3.8],
  };

  // 72 Dynamic Energy Particles
  const particles = Array.from({ length: 72 }, (_, idx) => ({
    angle: (idx / 72) * Math.PI * 2,
    radiusFactor: 0.24 + Math.random() * 0.58,
    speed: (Math.random() * 0.6 + 0.2) * (idx % 2 === 0 ? 1 : -1),
    size: 1.1 + Math.random() * 2.1,
    alpha: 0.35 + Math.random() * 0.6,
  }));

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function rgba(rgb, a) {
    return `rgba(${Math.round(rgb[0])}, ${Math.round(rgb[1])}, ${Math.round(rgb[2])}, ${a})`;
  }

  function resizeCanvas() {
    const rect = canvas.parentElement.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.max(300, Math.floor(rect.width * dpr));
    canvas.height = Math.max(300, Math.floor(rect.height * dpr));
  }
  window.addEventListener("resize", resizeCanvas);
  resizeCanvas();

  let lastTs = performance.now();

  function renderCore(now) {
    const dt = Math.min(0.05, (now - lastTs) / 1000);
    lastTs = now;
    const tSec = now / 1000;

    const effState = getEffectiveState();
    const target = STATE_PALETTES[effState] || STATE_PALETTES.idle;

    // Smooth morphing interpolation
    const k = Math.min(1, dt * 5.5);
    for (let i = 0; i < 3; i++) {
      anim.primary[i] = lerp(anim.primary[i], target.primary[i], k);
      anim.secondary[i] = lerp(anim.secondary[i], target.secondary[i], k);
      anim.core[i] = lerp(anim.core[i], target.core[i], k);
    }
    anim.spin = lerp(anim.spin, target.spin, k);
    anim.scale = lerp(anim.scale, target.scale, k);

    // Compute live audio energy from Web Audio FFT (if browser playing) or daemon RMS / speaking harmonic
    let targetEnergy = 0.04;
    if (browserAudioPlaying && analyser && freqData) {
      analyser.getByteFrequencyData(freqData);
      let sum = 0;
      for (let i = 0; i < 48; i++) sum += freqData[i];
      targetEnergy = Math.min(1.0, (sum / (48 * 255)) * 2.1);
    } else if (effState === "speaking") {
      targetEnergy = 0.35 + 0.28 * Math.abs(Math.sin(tSec * 7.5)) + 0.15 * Math.sin(tSec * 13.0);
    } else if (effState === "listening") {
      targetEnergy = Math.max(0.12, Math.min(1.0, state.liveRms * 1.9));
    } else if (effState === "thinking") {
      targetEnergy = 0.25 + 0.14 * Math.sin(tSec * 5.2);
    } else if (effState === "error") {
      targetEnergy = 0.22 + 0.18 * Math.abs(Math.sin(tSec * 4.0));
    } else {
      // Idle gentle breathing
      targetEnergy = 0.04 + 0.03 * Math.sin(tSec * 1.6);
    }
    anim.energy = lerp(anim.energy, targetEnergy, Math.min(1, dt * 14));

    const w = canvas.width;
    const h = canvas.height;
    const cx = w / 2;
    const cy = h / 2;
    const baseR = Math.min(w, h) * 0.385 * anim.scale * (1 + anim.energy * target.pulseAmp);

    ctx.clearRect(0, 0, w, h);

    // 1. Ambient Holographic Bloom
    const outerGlow = ctx.createRadialGradient(cx, cy, baseR * 0.08, cx, cy, baseR * 1.28);
    outerGlow.addColorStop(0, rgba(anim.core, 0.32 + anim.energy * 0.25));
    outerGlow.addColorStop(0.45, rgba(anim.primary, 0.15 + anim.energy * 0.14));
    outerGlow.addColorStop(0.82, rgba(anim.primary, 0.04));
    outerGlow.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = outerGlow;
    ctx.beginPath();
    ctx.arc(cx, cy, baseR * 1.28, 0, Math.PI * 2);
    ctx.fill();

    // 2. Outer 128-Bar Audio-Reactive Waveform Crown
    const crownBins = 128;
    const crownRadius = baseR * 1.07;
    ctx.save();
    ctx.translate(cx, cy);
    for (let i = 0; i < crownBins; i++) {
      const ang = (i / crownBins) * Math.PI * 2 - Math.PI / 2;
      let binVal = 0;
      if (browserAudioPlaying && analyser && freqData) {
        binVal = freqData[i % 64] / 255;
      } else {
        const wave1 = Math.sin(ang * 6 + tSec * 3.8) * 0.5 + 0.5;
        const wave2 = Math.cos(ang * 14 - tSec * 5.4) * 0.5 + 0.5;
        binVal = (wave1 * 0.65 + wave2 * 0.35) * (0.14 + anim.energy * 1.15);
      }
      const tickHalf = baseR * (0.008 + binVal * 0.075);
      const rIn = crownRadius - tickHalf * 0.45;
      const rOut = crownRadius + tickHalf;

      ctx.strokeStyle = rgba(i % 4 === 0 ? anim.secondary : anim.primary, 0.38 + Math.min(0.6, binVal * 0.8));
      ctx.lineWidth = Math.max(1.2, w * 0.0024);
      ctx.beginPath();
      ctx.moveTo(Math.cos(ang) * rIn, Math.sin(ang) * rIn);
      ctx.lineTo(Math.cos(ang) * rOut, Math.sin(ang) * rOut);
      ctx.stroke();
    }
    ctx.restore();

    // 3. Concentric Glowing Cyan & Segmented Counter-Rotating Orbital Rings
    const ringSpecs = [
      { r: 0.96, width: 3.4, dir: 1,    speed: 0.45, segments: [[0.0, 0.36], [0.44, 0.82], [0.88, 0.96]], glow: true },
      { r: 0.86, width: 1.6, dir: -1,   speed: 0.75, segments: [[0.05, 0.25], [0.33, 0.62], [0.70, 0.94]], glow: false },
      { r: 0.72, width: 2.6, dir: 1,    speed: 1.10, segments: [[0.0, 0.22], [0.30, 0.52], [0.62, 0.88]], glow: true },
      { r: 0.55, width: 1.8, dir: -1.3, speed: 1.35, segments: [[0.08, 0.42], [0.55, 0.92]], glow: false },
      { r: 0.38, width: 2.4, dir: 1.5,  speed: 1.75, segments: [[0.0, 0.38], [0.50, 0.86]], glow: true },
    ];

    ringSpecs.forEach((spec, idx) => {
      anim.angles[idx] += dt * anim.spin * spec.speed * spec.dir;
      const rr = baseR * spec.r;

      // Subtle continuous guide circle
      ctx.strokeStyle = rgba(anim.primary, 0.14);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(cx, cy, rr, 0, Math.PI * 2);
      ctx.stroke();

      // Illuminated orbital arc segments
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(anim.angles[idx]);
      if (spec.glow) {
        ctx.shadowColor = rgba(anim.primary, 0.85);
        ctx.shadowBlur = 14 + anim.energy * 16;
      }
      ctx.strokeStyle = rgba(idx === 4 ? anim.core : anim.primary, 0.88);
      ctx.lineWidth = spec.width * (w / 560);
      ctx.lineCap = "round";

      for (const [s0, s1] of spec.segments) {
        ctx.beginPath();
        ctx.arc(0, 0, rr, s0 * Math.PI * 2, s1 * Math.PI * 2);
        ctx.stroke();
      }
      ctx.restore();
    });

    // Precision Compass Degree Ticks on Ring 0.64
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(-anim.angles[1] * 0.4);
    const tickR = baseR * 0.64;
    for (let i = 0; i < 72; i++) {
      const a = (i / 72) * Math.PI * 2;
      const len = i % 6 === 0 ? baseR * 0.032 : baseR * 0.014;
      ctx.strokeStyle = rgba(anim.secondary, i % 6 === 0 ? 0.55 : 0.22);
      ctx.lineWidth = 1.1;
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * tickR, Math.sin(a) * tickR);
      ctx.lineTo(Math.cos(a) * (tickR + len), Math.sin(a) * (tickR + len));
      ctx.stroke();
    }
    ctx.restore();

    // 4. Dynamic Energy Particles & Light Trails
    ctx.save();
    ctx.translate(cx, cy);
    for (const p of particles) {
      p.angle += dt * p.speed * (0.65 + anim.spin * 0.9);
      const pr = baseR * p.radiusFactor * (1 + Math.sin(tSec * 2 + p.angle) * 0.025);
      const px = Math.cos(p.angle) * pr;
      const py = Math.sin(p.angle) * pr;
      const trailAngle = p.angle - p.speed * 0.11 * (0.6 + anim.energy);
      const tx = Math.cos(trailAngle) * pr;
      const ty = Math.sin(trailAngle) * pr;

      ctx.strokeStyle = rgba(anim.secondary, p.alpha * 0.45);
      ctx.lineWidth = p.size * 0.75;
      ctx.beginPath();
      ctx.moveTo(tx, ty);
      ctx.lineTo(px, py);
      ctx.stroke();

      ctx.fillStyle = rgba([235, 250, 255], p.alpha);
      ctx.beginPath();
      ctx.arc(px, py, p.size * (w / 600), 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();

    // 5. Speaking Shockwave Pulse Ring
    if (anim.energy > 0.16) {
      const wavePhase = (tSec * 1.35) % 1;
      const waveR = baseR * (0.25 + wavePhase * 0.78);
      ctx.strokeStyle = rgba(anim.primary, (1 - wavePhase) * anim.energy * 0.65);
      ctx.lineWidth = 2.2;
      ctx.beginPath();
      ctx.arc(cx, cy, waveR, 0, Math.PI * 2);
      ctx.stroke();
    }

    // 6. Central Plasma Nucleus & Horizontal Lens-Flare Crosshair
    const coreR = baseR * (0.21 + anim.energy * 0.06);
    const coreGrad = ctx.createRadialGradient(cx, cy, 1, cx, cy, coreR);
    coreGrad.addColorStop(0, "rgba(255, 255, 255, 0.98)");
    coreGrad.addColorStop(0.28, rgba(anim.core, 0.88));
    coreGrad.addColorStop(0.68, rgba(anim.primary, 0.35));
    coreGrad.addColorStop(1, "rgba(0, 0, 0, 0)");

    ctx.fillStyle = coreGrad;
    ctx.beginPath();
    ctx.arc(cx, cy, coreR, 0, Math.PI * 2);
    ctx.fill();

    // Specular horizontal holographic flare
    const flareW = baseR * (0.38 + anim.energy * 0.22);
    const flareGrad = ctx.createLinearGradient(cx - flareW, cy, cx + flareW, cy);
    flareGrad.addColorStop(0, "rgba(0, 240, 255, 0)");
    flareGrad.addColorStop(0.5, rgba([240, 248, 255], 0.75));
    flareGrad.addColorStop(1, "rgba(0, 240, 255, 0)");
    ctx.strokeStyle = flareGrad;
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    ctx.moveTo(cx - flareW, cy);
    ctx.lineTo(cx + flareW, cy);
    ctx.stroke();

    requestAnimationFrame(renderCore);
  }

  requestAnimationFrame(renderCore);
})();
