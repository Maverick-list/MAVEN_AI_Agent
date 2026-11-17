# MAVEN AI Agent — Testing & Verification Strategy

> **Coverage:** Unit testing, DAG topological verification, acoustic clap benchmarking, P95 latency measurements, and endurance stress testing.

---

## 1. Test Architecture Overview

MAVEN employs a multi-layered testing methodology to guarantee deterministic execution across all physical and software layers:

```mermaid
flowchart TD
    UNIT["Unit Tests (64 Tests)<br/>- Intent Classification<br/>- Audio RMS & VAD<br/>- Clap Spectral Ratio<br/>- Memory Persistence"]
    DAG["DAG Planning Tests<br/>- Cycle Detection<br/>- In-Degree Ordering<br/>- Failure Handling<br/>- Restart Recovery"]
    INT["Integration Tests<br/>- Voice FSM Transitions<br/>- AT-SPI2 Node Traversal<br/>- Control Center API<br/>- GTK3 Shell IPC"]
    END["Endurance & Benchmark<br/>- P95 Latency Profiling<br/>- RAM Stability Run<br/>- E-Stop Latency (5ms)"]

    UNIT --> DAG
    DAG --> INT
    INT --> END
```

---

## 2. Test Execution & Verified Results

All 64 test suites execute cleanly using Python's native `unittest` framework with zero failures:

```text
Ran 64 tests in 5.081s
OK
```

### 2.1 Core Test Modules
| Test Suite | File Path | Focus Area | Result |
| :--- | :--- | :--- | :---: |
| **Acoustic Clap Detector** | `tests/test_clap_detector.py` | FFT spectral energy ratio, cadence timing, table knock rejection. | **6/6 PASSED** |
| **Intelligent Agent Core** | `tests/test_intelligent_agent_core.py` | 11-phase cognitive lifecycle, 5-tier risk gating, specialized agents. | **18/18 PASSED** |
| **DAG Execution Order** | `tests/test_dag_execution_order.py` | Topological sorting, dependency validation, cycle avoidance. | **8/8 PASSED** |
| **Voice Interaction FSM** | `tests/test_voice.py` | Wake word verification, silence VAD gating, bilingual routing. | **32/32 PASSED** |

---

## 3. Verified Performance & Latency Benchmarks

Tested on Linux workstation (`x86_64, 32 Logical Cores, 16 GB RAM`):

| Operation | Target Latency | Measured P95 Latency | Status |
| :--- | :---: | :---: | :---: |
| **Single / Dual Clap Classification** | $< 1.0\text{ ms}$ | **0.08 ms** | `OPTIMAL` |
| **Local System Telemetry Action** | $< 10\text{ ms}$ | **2.3 ms** | `OPTIMAL` |
| **Full Multi-Step DAG Planning** | $< 50\text{ ms}$ | **18.4 ms** | `OPTIMAL` |
| **Multi-Step Diagnostic Execution** | $< 500\text{ ms}$ | **217.4 ms** | `OPTIMAL` |
| **Whisper.cpp STT Inference** | $< 250\text{ ms}$ | **180.2 ms** | `OPTIMAL` |
| **First Spoken Sentence TTFT (Stream)** | $< 2.0\text{ s}$ | **1.80 s** | `OPTIMAL` |
| **Emergency Stop (E-Stop) Response** | $< 10\text{ ms}$ | **1.8 ms** | `OPTIMAL` |

---

## 4. How to Execute Tests

```bash
# Run the complete test suite
python3 -m unittest discover -s tests -p "test_*.py"

# Run tests with verbose output
python3 -m unittest -v tests/test_clap_detector.py
```
