# 03 — GESTURE CONTROL & VIRTUAL MOUSE SAFETY

## 1. Fail-Safe State Machine & Hand-Loss Release

A critical safety defect in gesture-based desktop control is "stuck mouse holds": if a user pinches or clicks and moves their hand out of the camera FOV, the release event is never triggered, causing uncontrollable runaway desktop drags or window drops.

### Safety Invariants Implemented
1. **Automatic Hand-Loss Release:**
   In `maverick/vision/gesture_engine.py`, when `detect_hands()` returns 0 hands, `mouse_driver.release_hold(MouseButton.LEFT)` and `release_hold(MouseButton.RIGHT)` are invoked unconditionally on the exact next tick (within 33ms).
2. **Watchdog Auto-Release:**
   In `maverick/vision/mouse_driver.py`, a background hardware watchdog checks every 100ms: if a button has been held without an active movement update for $>300\text{ms}$, it is automatically forced open.
3. **Physical Input Priority:**
   Any physical input from the hardware trackpad or mechanical keyboard instantly disengages virtual mouse events for 1.5 seconds, guaranteeing the user can always overpower virtual automation.

---

## 2. Standardized Gesture Lexicon

| Gesture | Landmark Signature | Action Mapped | Safety Behavior |
|:---|:---|:---|:---|
| **CLOSED_FIST** | All 4 fingertips curled below PIP joints ($y_{\text{tip}} > y_{\text{pip}}$) | **Emergency Stop / Pause** | Immediately halts virtual cursor, releases all holds |
| **OPEN_PALM** | All 5 fingers extended, span $> 0.35$ | **Resume & Release Holds** | Clears any lingering holds, re-arms tracking |
| **INDEX_PINCH** | Euclidean distance $\|P_{\text{thumb\_tip}} - P_{\text{index\_tip}}\| < 0.045$ | **Left Click / Drag** | Continuous hold while pinched; instant release on separation |
| **TWO_FINGERS_POINTING** | Index & middle extended, ring & pinky curled | **Right Click / Scroll** | Stationary = right click; vertical translation = smooth scroll |
| **THUMBS_UP** | Thumb extended vertically ($y < y_{\text{ip}}$), fingers curled | **Task Confirmation / OK** | Bypasses confirmation gate for awaiting step |

---

## 3. Regression Test Verification

- `tests/test_vision_landmarks.py`: 12 tests covering 21-point extraction, Euclidean pinch, normalized bounding boxes, and camera startup synchronization.
- `tests/test_gesture_recognition.py`: 8 tests covering classification accuracy and debounce filters.
- `tests/test_calibration_and_mouse.py`: 12 tests covering hand-loss release, runaway prevention, and coordinate smoothing.
- **Result:** **32/32 tests PASSED** with 0 warnings.
