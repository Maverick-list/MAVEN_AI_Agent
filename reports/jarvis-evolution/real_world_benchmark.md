# MAVEN JARVIS 4-Level Benchmark Evaluation Report

**Execution Timestamp:** 2026-10-31 12:00:39  
**Overall Status:** `PASSED`  
**Total Duration:** 1.13s  
**Overall Pass Rate:** 100.0% (16/16)

---

## 1. Summary by Level

| Level | Description | Total | Passed | Failed | Pass Rate | Duration (ms) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| L1 | Unit Capability | 5 | 5 | 0 | 100.0% | 15.4ms |
| L2 | Local Integration | 4 | 4 | 0 | 100.0% | 40.3ms |
| L3 | Real Application Integration | 4 | 4 | 0 | 100.0% | 989.3ms |
| L4 | End-to-End Real-World Workflows | 3 | 3 | 0 | 100.0% | 84.4ms |

---

## 2. Granular Test Results

| ID | Test Name | Level | Status | Duration (ms) | Notes |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `L1-DAG-01` | DAG Validation (Cycles, Duplicates, Self-Deps) | L1 | `PASSED` | 1.16ms | OK |
| `L1-SEC-01` | Filesystem Sandbox & Path Containment Policies | L1 | `PASSED` | 0.69ms | OK |
| `L1-DOC-01` | Document PDF Multi-Page Rendering & Escaping | L1 | `PASSED` | 1.31ms | OK |
| `L1-RES-01` | Research SSRF Prevention & IP Range Filtering | L1 | `PASSED` | 0.96ms | OK |
| `L1-VOX-01` | Voice State Machine Direct Transition & Onset Retention | L1 | `PASSED` | 11.33ms | OK |
| `L2-DAG-01` | SQLite TaskStore & Multi-Pass Topological Execution | L2 | `PASSED` | 3.15ms | OK |
| `L2-SEC-01` | Filesystem Overwrite Backup (.bak) Creation & Swap | L2 | `PASSED` | 0.64ms | OK |
| `L2-TOOL-01` | AST Symbol Discovery & Codebase Grep Tools | L2 | `PASSED` | 36.33ms | OK |
| `L2-RES-01` | Research Engine Unconfigured Provider Honest Handling | L2 | `PASSED` | 0.15ms | OK |
| `L3-ENV-01` | Host System Binary & Environment Dependency Audit | L3 | `PASSED` | 955.04ms | OK |
| `L3-ENV-02` | Linux Desktop Display Session Validation | L3 | `PASSED` | 0.02ms | OK |
| `L3-DESK-01` | Desktop Notification Subsystem Integration | L3 | `PASSED` | 27.67ms | OK |
| `L3-VOX-01` | Audio Whisper STT Server Operational Status Probe | L3 | `PASSED` | 6.58ms | OK |
| `L4-E2E-01` | Autonomous Project Scaffolding, Unit Test & Verification | L4 | `PASSED` | 63.32ms | OK |
| `L4-E2E-02` | Multi-Format Technical Documentation Publishing (MD, DOCX, PDF) | L4 | `PASSED` | 2.66ms | OK |
| `L4-E2E-03` | Voice Assistant Interaction Lifecycle & Barge-In Simulation | L4 | `PASSED` | 18.43ms | OK |
