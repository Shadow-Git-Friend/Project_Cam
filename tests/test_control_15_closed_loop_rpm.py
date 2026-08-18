"""Contracts for the uncommissioned control_15 closed-loop RPM candidate.

The deployed control_12/13/14 sketches are immutable evidence.  control_15 may
change only its identity, the parsed updateMotorPWM() body, and an explicit set
of controller blocks.  These are source contracts; the deterministic plant
simulation and the pinned Arduino compile are separate gates.
"""

import hashlib
import importlib.util
import re
import subprocess
import textwrap
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTROL_12 = ROOT / "control_12_full.ino"
CONTROL_13 = ROOT / "control_13_full.ino"
CONTROL_14 = ROOT / "control_14_full.ino"
CONTROL_15 = ROOT / "control_15_full.ino"
BRIDGE = ROOT / "garage_lab_combined/scripts/blm_bridge.py"

PINNED = {
    CONTROL_12: "eefb35acce89f5f1467dab26865b90394e4f880127718c2697cd4924c51b660e",
    CONTROL_13: "54367d26e9dee54283beba08f0d41297ddacaae2538b296349f0b00eb946049f",
    CONTROL_14: "a43b2ef809e20b9b7860e0211b82e74fafb52f3a9d4af9c84f98af3ec6377477",
}

EXPECTED_EXACT = {"shoot", "reload", "setzero", "center", "stop", "info"}
EXPECTED_PREFIXES = {
    "set ",
    "jsset",
    "jfspeedset",
    "jfaccelset",
    "jv",
    "jh",
    "js",
    "jf",
}

BLOCK_NAMES = (
    "BLE_COMMAND_QUEUE_INCLUDE",
    "BLE_COMMAND_QUEUE_STATE",
    "BLE_COMMAND_QUEUE_ENQUEUE_HELPER",
    "RPM_CONTROLLER_STATE",
    "SET_TARGET_VALIDATION",
    "SET_TARGET_TRANSITION",
    "RELOAD_TARGET_TRANSITION",
    "STOP_TARGET_TRANSITION",
    "SHOOT_FAULT_GATE",
    "INFO_CONTROLLER_DIAGNOSTIC",
    "RPM_FRESH_SAMPLE_UPDATE",
    "SHOOTING_FAULT_GATE",
    "BLE_COMMAND_QUEUE_ENQUEUE",
    "BLE_COMMAND_QUEUE_SETUP",
    "BLE_COMMAND_QUEUE_DRAIN_HELPER",
    "BLE_COMMAND_QUEUE_DRAIN",
)

BLOCK_REPLACEMENTS = {
    "BLE_COMMAND_QUEUE_ENQUEUE": "            processCommand(bleInputBuffer);\n",
}

MARKER = re.compile(
    r"^[ \t]*// --- CONTROL_15 (?P<name>[A-Z_]+) "
    r"(?P<edge>BEGIN|END) ---[ \t]*$",
    re.MULTILINE,
)


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def control_15_source() -> str:
    assert CONTROL_15.exists(), "control_15_full.ino is intentionally absent in RED"
    return text(CONTROL_15)


def firmware_commands(source: str) -> tuple[set[str], set[str]]:
    exact = set(re.findall(r'equalsIgnoreCase\("([^"]+)"\)', source))
    prefixes = set(re.findall(r'startsWith\("([^"]+)"\)', source))
    return exact, prefixes


def function_body_span(source: str, name: str) -> tuple[int, int]:
    matches = list(
        re.finditer(rf"\bvoid\s+{re.escape(name)}\s*\(\s*\)\s*\{{", source)
    )
    assert len(matches) == 1, f"expected exactly one {name}() definition"
    opening = source.index("{", matches[0].start())
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return opening + 1, index
    raise AssertionError(f"unclosed {name}() body")


def remove_controller_blocks(source: str) -> str:
    markers = list(MARKER.finditer(source))
    pairs: list[tuple[int, int, str]] = []
    stack: list[re.Match[str]] = []
    for marker in markers:
        name, edge = marker.group("name"), marker.group("edge")
        assert name in BLOCK_NAMES, f"unknown controller block {name}"
        if edge == "BEGIN":
            assert not stack, "controller blocks must not nest"
            stack.append(marker)
            continue
        assert stack, f"orphan END for {name}"
        begin = stack.pop()
        assert begin.group("name") == name, "mismatched controller block"
        end = marker.end()
        if end < len(source) and source[end] == "\n":
            end += 1
        pairs.append((begin.start(), end, name))
    assert not stack, "unclosed controller block"
    counts = Counter(name for _, _, name in pairs)
    assert counts == Counter(BLOCK_NAMES), f"controller block set drifted: {counts}"
    for start, end, name in reversed(pairs):
        source = source[:start] + BLOCK_REPLACEMENTS.get(name, "") + source[end:]
    return source


def project_to_control_14(candidate: str) -> str:
    projected = remove_controller_blocks(candidate)
    old = text(CONTROL_14)
    new_start, new_end = function_body_span(projected, "updateMotorPWM")
    old_start, old_end = function_body_span(old, "updateMotorPWM")
    projected = projected[:new_start] + old[old_start:old_end] + projected[new_end:]
    identity_rewrites = (
        (
            'const char* FIRMWARE_ID = "control_15";',
            'const char* FIRMWARE_ID = "control_14";',
        ),
        (
            'Serial.println("SYS: FW control_15 READY");',
            'Serial.println("SYS: FW control_14 READY");',
        ),
    )
    for candidate_identity, deployed_identity in identity_rewrites:
        assert projected.count(candidate_identity) == 1
        projected = projected.replace(candidate_identity, deployed_identity, 1)
    assert "control_15" not in projected
    return projected


def block(source: str, name: str) -> str:
    pattern = re.compile(
        rf"// --- CONTROL_15 {name} BEGIN ---\n(.*?)"
        rf"// --- CONTROL_15 {name} END ---",
        re.DOTALL,
    )
    matches = pattern.findall(source)
    assert len(matches) == 1
    return matches[0]


def update_body(source: str) -> str:
    start, end = function_body_span(source, "updateMotorPWM")
    return source[start:end]


def run_controller_cpp_harness(tmp_path: Path, main_body: str) -> None:
    """Compile the real controller helper from the sketch, not a Python copy."""
    state = block(control_15_source(), "RPM_CONTROLLER_STATE")
    controller_math = state[: state.index("void appendRpmFaultName")]
    harness = tmp_path / "control_15_controller_harness.cpp"
    harness.write_text(
        textwrap.dedent(
            """
            #include <cassert>
            #include <cmath>
            #include <cstdint>
            #include <cstdlib>
            #include <string>

            using std::fabs;
            using std::isfinite;
            using std::lround;

            const double MIN_RPM_THRESHOLD = 200.0;
            const double MIN_FEED_RPM = 400.0;
            const int RAMP_STEP_US = 5;

            template <typename T>
            T constrain(T value, T low, T high) {
              return value < low ? low : (value > high ? high : value);
            }

            class String {
             public:
              explicit String(const char *value) : value_(value) {}
              const char *c_str() const { return value_.c_str(); }

             private:
              std::string value_;
            };
            """
        )
        + controller_math
        + "\nint main() {\n"
        + textwrap.dedent(main_body)
        + "\n}\n",
        encoding="utf-8",
    )
    executable = tmp_path / "control_15_controller_harness"
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(harness),
            "-o",
            str(executable),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run([str(executable)], check=True)


def run_fault_cpp_harness(tmp_path: Path, main_body: str) -> None:
    """Compile the real fault state machine and dispatcher with hardware shims."""
    source = control_15_source()
    state = block(source, "RPM_CONTROLLER_STATE")
    harness = tmp_path / "control_15_fault_harness.cpp"
    harness.write_text(
        textwrap.dedent(
            """
            #include <cassert>
            #include <cmath>
            #include <cstdint>
            #include <cstdlib>
            #include <string>

            using std::fabs;
            using std::isfinite;
            using std::lround;

            const double MIN_RPM_THRESHOLD = 200.0;
            const double MIN_FEED_RPM = 400.0;
            const int RAMP_STEP_US = 5;
            const double LEFT_SLOPE = 0.1763;
            const int LEFT_OFFSET = 1101;
            const double RIGHT_SLOPE = 0.1670;
            const int RIGHT_OFFSET = 1088;
            const int PUSHER_STEP_ENA = 1;
            const int HIGH = 1;
            const int STOP_SPEED = 90;
            const int STATE_IDLE = 0;

            template <typename T>
            T constrain(T value, T low, T high) {
              return value < low ? low : (value > high ? high : value);
            }

            class String {
             public:
              String() = default;
              String(const char *value) : value_(value) {}
              explicit String(std::string value) : value_(std::move(value)) {}
              const char *c_str() const { return value_.c_str(); }
              size_t length() const { return value_.length(); }
              String &operator+=(const char *value) {
                value_ += value;
                return *this;
              }
              friend String operator+(const String &left, const String &right) {
                return String(left.value_ + right.value_);
              }

             private:
              std::string value_;
            };

            struct StepperShim {
              void setCurrentPosition(long) {}
              void moveTo(long) {}
            } pusherStepper;
            struct ServoShim {
              void write(int) {}
            } feederServo;

            double targetRPM_Left = 0.0;
            double targetRPM_Right = 0.0;
            double currentRPM_Left = 0.0;
            double currentRPM_Right = 0.0;
            int desiredPWM_Left = 1000;
            int desiredPWM_Right = 1000;
            int currentPWM_Left = 1000;
            int currentPWM_Right = 1000;
            int currentState = STATE_IDLE;
            unsigned long fakeNow = 0;

            void digitalWrite(int, int) {}
            void sendMsg(const String &) {}
            unsigned long millis() { return fakeNow; }
            """
        )
        + state
        + "\nvoid updateMotorPWM() {\n"
        + update_body(source)
        + "\n}\n"
        + "\nint main() {\n"
        + textwrap.dedent(main_body)
        + "\n}\n",
        encoding="utf-8",
    )
    executable = tmp_path / "control_15_fault_harness"
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(harness),
            "-o",
            str(executable),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run([str(executable)], check=True)


def run_queue_cpp_harness(tmp_path: Path, main_body: str) -> None:
    """Execute the sketch's queue policy against a host-side FreeRTOS mock."""
    source = control_15_source()
    queue_state = block(source, "BLE_COMMAND_QUEUE_STATE")
    enqueue = block(source, "BLE_COMMAND_QUEUE_ENQUEUE_HELPER")
    drain = block(source, "BLE_COMMAND_QUEUE_DRAIN_HELPER")
    harness = tmp_path / "control_15_queue_harness.cpp"
    harness.write_text(
        textwrap.dedent(
            """
            #include <algorithm>
            #include <cassert>
            #include <cctype>
            #include <cstdint>
            #include <cstring>
            #include <deque>
            #include <string>
            #include <vector>

            using BaseType_t = int;
            using UBaseType_t = unsigned int;
            constexpr BaseType_t pdTRUE = 1;
            constexpr BaseType_t pdFALSE = 0;
            struct StaticQueue_t {};
            struct MockQueue {
              size_t depth = 0;
              size_t itemSize = 0;
              std::deque<std::vector<uint8_t>> items;
            };
            using QueueHandle_t = MockQueue *;

            QueueHandle_t xQueueCreateStatic(UBaseType_t depth,
                                             UBaseType_t itemSize,
                                             uint8_t *, StaticQueue_t *) {
              auto *queue = new MockQueue;
              queue->depth = depth;
              queue->itemSize = itemSize;
              return queue;
            }
            BaseType_t xQueueSendToBack(QueueHandle_t queue, const void *item,
                                        unsigned int) {
              if (queue->items.size() >= queue->depth) return pdFALSE;
              const auto *begin = static_cast<const uint8_t *>(item);
              queue->items.emplace_back(begin, begin + queue->itemSize);
              return pdTRUE;
            }
            BaseType_t xQueueSendToFront(QueueHandle_t queue, const void *item,
                                         unsigned int) {
              if (queue->items.size() >= queue->depth) return pdFALSE;
              const auto *begin = static_cast<const uint8_t *>(item);
              queue->items.emplace_front(begin, begin + queue->itemSize);
              return pdTRUE;
            }
            BaseType_t xQueueReceive(QueueHandle_t queue, void *item,
                                     unsigned int) {
              if (queue->items.empty()) return pdFALSE;
              std::memcpy(item, queue->items.front().data(), queue->itemSize);
              queue->items.pop_front();
              return pdTRUE;
            }
            BaseType_t xQueueReset(QueueHandle_t queue) {
              queue->items.clear();
              return pdTRUE;
            }

            using portMUX_TYPE = int;
            constexpr portMUX_TYPE portMUX_INITIALIZER_UNLOCKED = 0;
            #define portENTER_CRITICAL(mux) ((void)(mux))
            #define portEXIT_CRITICAL(mux) ((void)(mux))

            class String {
             public:
              String() = default;
              String(const char *value) : value_(value) {}
              size_t length() const { return value_.length(); }
              const char *c_str() const { return value_.c_str(); }
              void toCharArray(char *destination, size_t size) const {
                if (size == 0) return;
                std::strncpy(destination, value_.c_str(), size - 1);
                destination[size - 1] = 0;
              }
              void trim() {
                auto keep = [](unsigned char value) {
                  return !std::isspace(value);
                };
                auto first = std::find_if(value_.begin(), value_.end(), keep);
                auto last = std::find_if(value_.rbegin(), value_.rend(), keep).base();
                value_ = first < last ? std::string(first, last) : std::string();
              }
              bool equalsIgnoreCase(const char *expected) const {
                std::string other(expected);
                if (value_.size() != other.size()) return false;
                for (size_t index = 0; index < value_.size(); ++index) {
                  if (std::tolower(static_cast<unsigned char>(value_[index])) !=
                      std::tolower(static_cast<unsigned char>(other[index]))) {
                    return false;
                  }
                }
                return true;
              }

             private:
              std::string value_;
            };
            """
        )
        + queue_state
        + enqueue
        + "\nstd::vector<std::string> processedCommands;\n"
        + "void processCommand(String command) {\n"
        + "  processedCommands.emplace_back(command.c_str());\n"
        + "}\n"
        + drain
        + "\nint main() {\n"
        + textwrap.dedent(main_body)
        + "\n}\n",
        encoding="utf-8",
    )
    executable = tmp_path / "control_15_queue_harness"
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(harness),
            "-o",
            str(executable),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run([str(executable)], check=True)


def load_bridge():
    spec = importlib.util.spec_from_file_location("control15_bridge", BRIDGE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deployed_firmware_hashes_are_immutable():
    control_15_source()
    for path, digest in PINNED.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_control_15_grammar_equals_control_14_by_name():
    candidate = control_15_source()
    assert firmware_commands(candidate) == firmware_commands(text(CONTROL_14))
    assert firmware_commands(candidate) == (EXPECTED_EXACT, EXPECTED_PREFIXES)
    assert "wheels <" not in candidate


def test_control_15_projects_to_control_14_byte_for_byte():
    candidate = control_15_source()
    assert project_to_control_14(candidate) == text(CONTROL_14)


def test_projection_rejects_marker_drift():
    candidate = control_15_source()
    with pytest.raises(AssertionError):
        remove_controller_blocks(
            candidate.replace(
                "CONTROL_15 RPM_CONTROLLER_STATE BEGIN",
                "CONTROL_15 UNKNOWN_BLOCK BEGIN",
                1,
            )
        )
    with pytest.raises(AssertionError):
        remove_controller_blocks(
            candidate.replace(
                "// --- CONTROL_15 RPM_CONTROLLER_STATE END ---\n", "", 1
            )
        )


def test_projection_rejects_unmarked_control_15_text():
    candidate = control_15_source()
    mutant = candidate.replace(
        "ESC RAMP PACING (control_14)",
        "ESC RAMP PACING (control_15)",
        1,
    )
    with pytest.raises(AssertionError):
        project_to_control_14(mutant)


def test_each_wheel_has_independent_state_error_base_trim_and_output():
    source = control_15_source()
    state = block(source, "RPM_CONTROLLER_STATE")
    body = update_body(source)
    for token in (
        "WheelControllerState leftController",
        "WheelControllerState rightController",
        "errorRPM",
        "basePWM",
        "integralUs",
        "trimUs",
        "desiredPWM_Left",
        "desiredPWM_Right",
        "currentPWM_Left",
        "currentPWM_Right",
    ):
        assert token in state + body
    assert "currentRPM_Left" in body
    assert "currentRPM_Right" in body


def test_integrator_freezes_until_ramp_catches_but_p_stays_live():
    state = block(control_15_source(), "RPM_CONTROLLER_STATE")
    assert "fabs(desiredPWM - currentPWM) <= RAMP_STEP_US" in state
    assert "proportionalUs = kp * state.errorRPM" in state
    caught = state.index("fabs(desiredPWM - currentPWM) <= RAMP_STEP_US")
    integrate = state.index("state.integralUs = candidateIntegral", caught)
    assert caught < integrate


def test_real_cpp_controller_keeps_each_wheels_p_until_its_next_sample(tmp_path):
    run_controller_cpp_harness(
        tmp_path,
        """
        WheelControllerState state;
        noteTargetTransition(state, 500.0, 1000);
        int desiredPWM = PWM_MIN_US;

        updateWheelController(state, 500.0, 0.0, 0.1763, 1101,
                              0.12, 0.08, PWM_MIN_US, desiredPWM,
                              false, 1000);
        int currentPWM = desiredPWM;

        updateWheelController(state, 500.0, 400.0, 0.1763, 1101,
                              0.12, 0.08, currentPWM, desiredPWM,
                              true, 1200);
        assert(state.errorRPM == 100.0);
        assert(state.proportionalUs > 0.0);
        double sampledP = state.proportionalUs;
        int sampledDesired = desiredPWM;

        updateWheelController(state, 500.0, 999.0, 0.1763, 1101,
                              0.12, 0.08, currentPWM, desiredPWM,
                              false, 1201);
        assert(state.proportionalUs == sampledP);
        assert(desiredPWM == sampledDesired);

        resetWheelController(state, 1400);
        state.lastTarget = 500.0;
        desiredPWM = (int)(500.0 * 0.1763 + 1101);
        currentPWM = desiredPWM;
        updateWheelController(state, 500.0, 600.0, 0.1763, 1101,
                              0.12, 0.08, currentPWM, desiredPWM,
                              true, 1600);
        assert(state.errorRPM == -100.0);
        assert(state.proportionalUs < 0.0);
        assert(desiredPWM < state.basePWM);
        """,
    )


def test_real_cpp_controller_enforces_reset_ramp_trim_and_pwm_bounds(tmp_path):
    run_controller_cpp_harness(
        tmp_path,
        """
        WheelControllerState state;
        state.lastTarget = 500.0;
        state.integralUs = 7.0;

        noteTargetTransition(state, 525.0, 1000);
        assert(state.integralUs == 7.0);
        noteTargetTransition(state, 551.25, 1200);
        assert(state.integralUs == 7.0);
        noteTargetTransition(state, 580.0, 1400);
        assert(state.integralUs == 0.0);

        state.integralUs = 7.0;
        noteTargetTransition(state, 0.0, 1600);
        assert(state.integralUs == 0.0);

        resetWheelController(state, 1800);
        state.lastTarget = 1200.0;
        state.integralUs = 5.0;
        int desiredPWM = 1800;
        updateWheelController(state, 1200.0, 0.0, 1.0, 1790,
                              0.12, 0.08, 1000, desiredPWM,
                              true, 2000);
        assert(state.integralUs == 5.0);
        assert(state.trimUs == MAX_TRIM_US);
        assert(desiredPWM == PWM_MAX_US);

        resetWheelController(state, 2200);
        state.lastTarget = 1200.0;
        desiredPWM = PWM_MIN_US;
        updateWheelController(state, 1200.0, 10000.0, 0.0, 1000,
                              0.12, 0.08, PWM_MIN_US, desiredPWM,
                              true, 2400);
        assert(state.trimUs == -MAX_TRIM_US);
        assert(desiredPWM == PWM_MIN_US);
        """,
    )


def test_target_reset_policy_is_strictly_greater_than_five_percent():
    state = block(control_15_source(), "RPM_CONTROLLER_STATE")
    assert "oldTarget == 0.0" in state
    assert "newTarget == 0.0" in state
    assert "fabs(newTarget - oldTarget) > 0.05 * oldTarget" in state
    assert "fabs(newTarget - oldTarget) >= 0.05 * oldTarget" not in state
    assert "if (reset)" in state
    assert "state.integralUs = 0.0" in state


def test_trim_pwm_startup_stall_and_overspeed_bounds_are_pinned():
    source = control_15_source()
    state = block(source, "RPM_CONTROLLER_STATE")
    body = update_body(source)
    for token in (
        "MAX_TRIM_US = 30.0",
        "PWM_MIN_US = 1000",
        "PWM_MAX_US = 1800",
        "OVERSPEED_RPM = 1300.0",
        "NO_START_TIMEOUT_MS = 15000",
        "ENCODER_LOSS_TIMEOUT_MS = 1000",
    ):
        assert token in state
    assert "constrain(state.proportionalUs + state.integralUs," in state
    assert "constrain(state.basePWM +" in state
    assert "OVERSPEED_RPM" in state + body


def test_fault_latch_blocks_pusher_and_needs_stop_plus_fresh_zero():
    source = control_15_source()
    shoot_command = block(source, "SHOOT_FAULT_GATE")
    shoot_state = block(source, "SHOOTING_FAULT_GATE")
    state = block(source, "RPM_CONTROLLER_STATE")
    assert "rpmControllerFault != RPM_FAULT_NONE" in shoot_command
    assert "return;" in shoot_command
    assert "rpmControllerFault != RPM_FAULT_NONE" in shoot_state
    assert "pusherStepper.moveTo(0)" in shoot_state
    assert "rpmFaultStopRequested" in state
    assert "rpmFaultLeftZeroConfirmed" in state
    assert "rpmFaultRightZeroConfirmed" in state
    assert "if (freshLeft)" in state
    assert "if (freshRight)" in state
    assert "currentRPM_Left < 50.0" in state
    assert "currentRPM_Right < 50.0" in state


def test_real_cpp_fault_clears_after_independent_post_stop_zero_samples(tmp_path):
    run_fault_cpp_harness(
        tmp_path,
        """
        rpmControllerFault = RPM_FAULT_NO_START_L;
        rpmFaultStopRequested = true;
        currentRPM_Left = 0.0;
        currentRPM_Right = 0.0;

        bool cleared = clearRpmFaultIfSafe(true, false, 1000);
        assert(!cleared);
        assert(rpmControllerFault != RPM_FAULT_NONE);

        cleared = clearRpmFaultIfSafe(false, true, 1200);
        assert(cleared);
        assert(rpmControllerFault == RPM_FAULT_NONE);
        """,
    )


def test_real_cpp_fault_thresholds_and_target_parser_are_bounded(tmp_path):
    run_fault_cpp_harness(
        tmp_path,
        """
        double parsed = 0.0;
        assert(parseWheelRpm(String("1200"), parsed));
        assert(parsed == 1200.0);
        assert(!parseWheelRpm(String("1200.1"), parsed));
        assert(!parseWheelRpm(String("-1"), parsed));
        assert(!parseWheelRpm(String("nan"), parsed));
        assert(!parseWheelRpm(String("500junk"), parsed));
        assert(std::string(formatRpmFault(
            RPM_FAULT_NO_START_L | RPM_FAULT_NO_START_R).c_str())
            == "NO_START_L+NO_START_R");

        WheelControllerState state;
        resetWheelController(state, 1000);
        uint8_t faults = evaluateWheelFault(
            state, 250.0, 0.0, true, 15999,
            RPM_FAULT_NO_START_L, RPM_FAULT_ENCODER_LOSS_L,
            RPM_FAULT_OVERSPEED_L);
        assert(faults == RPM_FAULT_NONE);
        faults = evaluateWheelFault(
            state, 250.0, 0.0, true, 16000,
            RPM_FAULT_NO_START_L, RPM_FAULT_ENCODER_LOSS_L,
            RPM_FAULT_OVERSPEED_L);
        assert((faults & RPM_FAULT_NO_START_L) != 0);

        resetWheelController(state, 20000);
        faults = evaluateWheelFault(
            state, 0.0, 1300.1, true, 20200,
            RPM_FAULT_NO_START_L, RPM_FAULT_ENCODER_LOSS_L,
            RPM_FAULT_OVERSPEED_L);
        assert((faults & RPM_FAULT_OVERSPEED_L) != 0);

        resetWheelController(state, 21000);
        state.started = true;
        state.exceeded200 = true;
        faults = evaluateWheelFault(
            state, 400.0, 49.0, true, 21200,
            RPM_FAULT_NO_START_L, RPM_FAULT_ENCODER_LOSS_L,
            RPM_FAULT_OVERSPEED_L);
        assert(faults == RPM_FAULT_NONE);
        faults = evaluateWheelFault(
            state, 400.0, 49.0, true, 22200,
            RPM_FAULT_NO_START_L, RPM_FAULT_ENCODER_LOSS_L,
            RPM_FAULT_OVERSPEED_L);
        assert((faults & RPM_FAULT_ENCODER_LOSS_L) != 0);
        """,
    )


def test_real_cpp_dispatcher_routes_fresh_samples_and_combines_faults(tmp_path):
    run_fault_cpp_harness(
        tmp_path,
        """
        resetWheelController(leftController, 1000);
        resetWheelController(rightController, 1000);
        leftController.lastTarget = 500.0;
        rightController.lastTarget = 700.0;
        targetRPM_Left = 500.0;
        targetRPM_Right = 700.0;
        desiredPWM_Left = (int)(targetRPM_Left * LEFT_SLOPE + LEFT_OFFSET);
        desiredPWM_Right = (int)(targetRPM_Right * RIGHT_SLOPE + RIGHT_OFFSET);
        currentPWM_Left = desiredPWM_Left;
        currentPWM_Right = desiredPWM_Right;
        currentRPM_Left = 400.0;
        currentRPM_Right = 760.0;
        rightController.errorRPM = 23.0;
        rightController.proportionalUs = 4.0;
        rightController.integralUs = 2.0;
        desiredPWM_Right += 6;
        double heldRightP = rightController.proportionalUs;
        int heldRightDesired = desiredPWM_Right;

        fakeNow = 1200;
        rpmFreshLeft = true;
        rpmFreshRight = false;
        updateMotorPWM();
        assert(leftController.errorRPM == 100.0);
        assert(leftController.proportionalUs > 0.0);
        assert(desiredPWM_Left > leftController.basePWM);
        assert(rightController.errorRPM == 23.0);
        assert(rightController.proportionalUs == heldRightP);
        assert(desiredPWM_Right == heldRightDesired);
        assert(!rpmFreshLeft && !rpmFreshRight);

        double heldLeftP = leftController.proportionalUs;
        currentRPM_Right = 760.0;
        fakeNow = 1400;
        rpmFreshLeft = false;
        rpmFreshRight = true;
        updateMotorPWM();
        assert(leftController.proportionalUs == heldLeftP);
        assert(rightController.errorRPM == -60.0);
        assert(rightController.proportionalUs < 0.0);
        assert(desiredPWM_Right < rightController.basePWM);
        assert(!rpmFreshLeft && !rpmFreshRight);

        rpmControllerFault = RPM_FAULT_NONE;
        resetWheelController(leftController, 2000);
        resetWheelController(rightController, 2000);
        leftController.lastTarget = 500.0;
        rightController.lastTarget = 700.0;
        targetRPM_Left = 500.0;
        targetRPM_Right = 700.0;
        currentRPM_Left = OVERSPEED_RPM + 1.0;
        currentRPM_Right = OVERSPEED_RPM + 2.0;
        fakeNow = 2200;
        rpmFreshLeft = true;
        rpmFreshRight = true;
        updateMotorPWM();
        assert((rpmControllerFault & RPM_FAULT_OVERSPEED_L) != 0);
        assert((rpmControllerFault & RPM_FAULT_OVERSPEED_R) != 0);
        assert(targetRPM_Left == 0.0);
        assert(targetRPM_Right == 0.0);
        assert(desiredPWM_Left == PWM_MIN_US);
        assert(desiredPWM_Right == PWM_MIN_US);
        """,
    )


def test_invalid_wheel_tokens_return_before_target_mutation():
    source = control_15_source()
    validation = block(source, "SET_TARGET_VALIDATION")
    assert 'sendMsg("ERR: RPM RANGE")' in validation
    assert "return;" in validation
    validation_end = source.index("// --- CONTROL_15 SET_TARGET_VALIDATION END ---")
    assert source.index("targetRPM_Left = wlStr.toDouble();") > validation_end
    assert source.index("targetRPM_Right = wrStr.toDouble();") > validation_end


def test_compact_telemetry_stays_parser_compatible():
    source = control_15_source()
    assert (
        'sprintf(buffer, "L:%.0f R:%.0f", currentRPM_Left, currentRPM_Right);'
        in source
    )
    bridge = load_bridge()
    assert bridge.parse_telemetry("L:500 R:500") == (500.0, 500.0)


def test_info_reports_actual_bounded_trim_not_only_integral_state():
    diagnostic = block(control_15_source(), "INFO_CONTROLLER_DIAGNOSTIC")
    assert "leftController.trimUs" in diagnostic
    assert "rightController.trimUs" in diagnostic
    assert "leftController.integralUs" not in diagnostic
    assert "rightController.integralUs" not in diagnostic


def test_ble_callback_queues_commands_and_main_loop_owns_actuator_state():
    source = control_15_source()
    callback = source[
        source.index("class MyCallbacks") : source.index(
            "// ==========================================\n// 5. SETUP"
        )
    ]
    assert "processCommand(bleInputBuffer)" not in callback
    assert "enqueueBleCommand(bleInputBuffer)" in callback
    assert "xQueueCreateStatic" in source
    assert "while (true) delay(1000);" in source
    assert "xQueueSendToFront" in source
    assert "processOneQueuedBleCommand();" in source


def test_stop_discards_every_older_ble_command_even_when_queue_is_full(tmp_path):
    run_queue_cpp_harness(
        tmp_path,
        """
        StaticQueue_t harnessQueueControl;
        uint8_t harnessQueueStorage[
            BLE_COMMAND_QUEUE_DEPTH * sizeof(QueuedBleCommand)] = {};
        bleCommandQueue = xQueueCreateStatic(
            BLE_COMMAND_QUEUE_DEPTH, sizeof(QueuedBleCommand),
            harnessQueueStorage, &harnessQueueControl);

        assert(enqueueBleCommand(String("set 0 0 500 500")));
        assert(enqueueBleCommand(String("shoot")));
        assert(enqueueBleCommand(String("stop")));
        assert(bleCommandQueue->items.size() == 1);
        processOneQueuedBleCommand();
        assert(processedCommands.size() == 1);
        assert(processedCommands[0] == "stop");
        processOneQueuedBleCommand();
        assert(processedCommands.size() == 1);

        processedCommands.clear();
        for (UBaseType_t index = 0; index < BLE_COMMAND_QUEUE_DEPTH; ++index) {
          assert(enqueueBleCommand(String("set 0 0 600 600")));
        }
        assert(enqueueBleCommand(String("stop")));
        assert(bleCommandQueue->items.size() == 1);
        processOneQueuedBleCommand();
        assert(processedCommands.size() == 1);
        assert(processedCommands[0] == "stop");

        processedCommands.clear();
        assert(enqueueBleCommand(String("shoot")));
        QueuedBleCommand inFlight = {};
        assert(xQueueReceive(bleCommandQueue, &inFlight, 0) == pdTRUE);
        assert(enqueueBleCommand(String("stop")));
        assert(inFlight.epoch != currentBleCommandEpoch());
        assert(xQueueSendToFront(bleCommandQueue, &inFlight, 0) == pdTRUE);
        processOneQueuedBleCommand();
        assert(processedCommands.empty());
        processOneQueuedBleCommand();
        assert(processedCommands.size() == 1);
        assert(processedCommands[0] == "stop");
        """,
    )


def test_candidate_is_not_commissioned_and_host_gates_are_unchanged():
    control_15_source()
    bridge = text(BRIDGE)
    assert 'COMMISSIONED_FIRMWARE = ("control_13", "control_14")' in bridge
    assert "RPM_BAND_FRAC = 0.10" in bridge
    assert "RPM_BAND_FLOOR = 50.0" in bridge
    assert "RPM_SPREAD_MAX = 75.0" in bridge
    assert "RPM_MIN_FIRE = 400" in bridge


def test_feed_forward_alone_retains_measured_static_error():
    from scripts.simulate_control_15_rpm import simulate_pair

    result = simulate_pair(target_rpm=500.0, closed_loop=False, duration_s=35.0)
    assert abs(result.left.final_rpm - 500.0) >= 25.0
    assert abs(result.right.final_rpm - 500.0) >= 25.0


def test_pi_converges_without_crossing_trim_pwm_or_overspeed_bounds():
    from scripts.simulate_control_15_rpm import simulate_pair

    result = simulate_pair(target_rpm=500.0, closed_loop=True, duration_s=45.0)
    for wheel in (result.left, result.right):
        assert abs(wheel.final_rpm - 500.0) <= 5.0
        assert wheel.max_abs_trim_us <= 30.0
        assert 1000 <= wheel.min_pwm <= wheel.max_pwm <= 1800
        assert wheel.max_rpm < 1300.0
        assert wheel.integrated_while_ramping == 0


def test_simulation_constants_match_the_firmware_contract():
    from scripts import simulate_control_15_rpm as simulation

    state = block(control_15_source(), "RPM_CONTROLLER_STATE")
    source = control_15_source()
    expected = {
        "LEFT_KP": simulation.KP,
        "RIGHT_KP": simulation.KP,
        "LEFT_KI": simulation.KI,
        "RIGHT_KI": simulation.KI,
        "MAX_TRIM_US": simulation.MAX_TRIM_US,
        "PWM_MIN_US": simulation.PWM_MIN_US,
        "PWM_MAX_US": simulation.PWM_MAX_US,
        "OVERSPEED_RPM": simulation.OVERSPEED_RPM,
        "LEFT_SLOPE": simulation.LEFT_SLOPE,
        "RIGHT_SLOPE": simulation.RIGHT_SLOPE,
        "LEFT_OFFSET": simulation.LEFT_OFFSET,
        "RIGHT_OFFSET": simulation.RIGHT_OFFSET,
        "RAMP_STEP_US": simulation.RAMP_STEP_US,
    }
    for name, value in expected.items():
        match = re.search(rf"\b{name}\s*=\s*([-+]?[0-9]+(?:\.[0-9]+)?)", state + source)
        assert match, name
        assert float(match.group(1)) == value
