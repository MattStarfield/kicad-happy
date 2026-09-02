# Validation Summary

This document describes how kicad-happy is tested and validated. Every change to the analysis engine is verified against a corpus of real-world KiCad projects before release.

*Auto-generated on 2026-05-16 by `generate_validation_md.py`.*

## Why this matters

Hardware design review tools must be trustworthy. A false negative (missed bug) can cost a board respin ($5K-$50K). A false positive (phantom warning) erodes trust until engineers ignore the tool entirely. kicad-happy addresses both through large-scale automated validation that no human reviewer could replicate.

## Test corpus

The [test harness](https://github.com/aklofas/kicad-happy-testharness) contains 5,857 open-source KiCad projects — the kind of designs real engineers actually build.

**Corpus diversity:**

| Dimension | Coverage |
|-----------|----------|
| Project types | Hobby boards, production hardware, motor controllers, RF frontends, battery management systems, IoT devices, audio amplifiers, power supplies, sensor boards, dev kits |
| KiCad versions | KiCad 5, KiCad 6, KiCad 7, KiCad 8, KiCad 9, KiCad 10 |
| File formats | `.kicad_sch` (S-expression), legacy `.sch` (EESchema), `.kicad_pcb` |
| Design complexity | Single-sheet through multi-sheet hierarchical, 2-layer through 6-layer |
| Component counts | 3 to 500+ components per project |
| Net complexity | Simple power supplies to multi-bus digital designs (I2C, SPI, UART, CAN, USB, Ethernet, HDMI) |

**KiCad version distribution:**

| Version | Repos |
|---------|------:|
| KiCad 5 | 2,209 |
| KiCad 6 | 1 |
| KiCad 7 | 9 |
| KiCad 8 | 1,225 |
| KiCad 9 | 1,365 |
| KiCad 10 | 41 |

**Category distribution:**

| Category | Repos |
|----------|------:|
| Miscellaneous KiCad projects | 1,810 |
| Keyboards | 449 |
| Synthesizers / audio | 324 |
| Motor controllers / robotics | 315 |
| LED / display | 304 |
| Arduino recreations | 295 |
| ESP32 | 294 |
| Networking / radio / SDR | 254 |
| Sensor boards / IoT | 250 |
| Retro computing | 235 |
| USB / interface adapters | 214 |
| Power / battery | 207 |
| RP2040 / Raspberry Pi | 192 |
| STM32 | 179 |
| ADC / DAC / measurement | 110 |
| *(other categories)* | 425 |

The corpus is sourced from public GitHub repositories. It is not curated for "easy" designs — it includes incomplete projects, unusual topologies, non-standard conventions, and designs with real bugs.

## What gets tested

Every analysis script runs against every applicable file in the corpus. Nothing is skipped or excluded.

### Crash testing

| Analyzer | Files tested | Success rate |
|----------|-------------|--------------|
| Schematic (`analyze_schematic.py`) | 36,591 | 100% |
| PCB (`analyze_pcb.py`) | 18,752 | 100% |
| Gerber (`analyze_gerbers.py`) | 5,513 | 100% |
| EMC (`analyze_emc.py`) | 42,513 | 100% |
| SPICE (`simulate_subcircuits.py`) | 36,565 | 100% |

A single unhandled exception across any analyzer on any file in the corpus is treated as a release blocker.

### Regression assertions

Hard assertions on known-good output values. If a previously correct result changes, the assertion fails and the change must be investigated.

*Measured via `regression/run_checks.py --json`: 2,362,793 passed / 90 failed / 2 errors out of 2,362,885 (100.0%).*

| Category | Assertion count | Pass rate |
|----------|----------------|-----------|
| **Total** | **2,364,698** | **100.0%** |

Assertions are seeded from validated output and checked on every run. When analyzer logic changes intentionally (new fields, corrected calculations), affected assertions are re-seeded after manual verification.

### v1.4 Layer 1 regression gate

v1.4 introduces the `--only-deterministic` flag to scope analyzer output to evidence-backed findings. The Layer 1 regression gate runs both v1.3.1 (plain) and v1.4 (`--only-deterministic`) over the harness corpus and diffs the resulting envelopes, asserting v1.4 does not silently drop or downgrade any v1.3.1 finding.

Latest run: section `rc1_fix_f561e47_full`, 169,951 analyzer-runs. Verdict: **CLEAN**.

| Outcome | Count |
|---------|------:|
| PASS | 149,561 |
| FAIL | 0 |
| Disappeared | 0 |
| Downgrades | 0 |
| Upgrades | 0 |
| NewKnown | 3,589 |
| NewUpgraded | 0 |
| NewUnknown | 0 |
| WARN | 5 |
| SKIP | 20,385 |

*Gate is CLEAN when `Disappeared == 0`, `Downgrades == 0`, and `FAIL == 0`. `NewKnown` and `NewUpgraded` are tolerated (intentional new v1.4 findings); `NewUnknown` is reported but not gating.*

## Signal detector coverage

65 active schematic detectors verified against the corpus:

| Detector | Repos with hits |
|----------|----------------|
| audit_rail_sources | 5,215 |
| audit_esd_protection | 5,075 |
| detect_design_observations | 4,952 |
| audit_datasheet_coverage | 4,024 |
| audit_sourcing_gate | 3,963 |
| detect_decoupling | 3,849 |
| validate_pullups | 3,294 |
| audit_connector_ground_distribution | 3,148 |
| audit_led_circuits | 3,020 |
| detect_power_regulators | 2,980 |
| analyze_connectivity | 2,825 |
| detect_rc_filters | 2,580 |
| detect_voltage_dividers | 2,282 |
| detect_transistor_circuits | 2,209 |
| detect_crystal_circuits | 1,853 |
| detect_protection_devices | 1,675 |
| audit_power_pin_dc_paths | 1,605 |
| detect_solder_jumpers | 1,399 |
| suggest_certifications | 1,188 |
| validate_led_resistors | 1,149 |
| detect_label_aliases | 1,119 |
| validate_power_sequencing | 1,050 |
| detect_debug_interfaces | 1,025 |
| detect_wireless_modules | 973 |
| detect_lc_filters | 833 |
| validate_usb_bus | 809 |
| validate_voltage_levels | 803 |
| detect_opamp_circuits | 741 |
| validate_i2c_bus | 475 |
| detect_memory_interfaces | 436 |
| detect_led_drivers | 428 |
| detect_pwm_led_dimming | 423 |
| detect_key_matrices | 423 |
| detect_sensor_interfaces | 373 |
| detect_addressable_leds | 366 |
| detect_level_shifters | 359 |
| detect_buzzer_speakers | 307 |
| detect_adc_circuits | 281 |
| detect_motor_drivers | 274 |
| detect_battery_chargers | 273 |
| detect_rf_matching | 245 |
| detect_reset_supervisors | 237 |
| detect_audio_circuits | 226 |
| detect_clock_distribution | 211 |
| detect_isolation_barriers | 189 |
| detect_power_path | 187 |
| detect_current_sense | 176 |
| detect_rf_chains | 155 |
| validate_feedback_stability | 153 |
| detect_bridge_circuits | 137 |
| validate_can_bus | 136 |
| detect_rtc_circuits | 121 |
| detect_ethernet_interfaces | 119 |
| validate_spi_bus | 111 |
| detect_led_driver_ics | 83 |
| detect_hdmi_dvi_interfaces | 80 |
| detect_headphone_jack | 79 |
| detect_display_interfaces | 55 |
| detect_thermocouple_rtd | 48 |
| detect_energy_harvesting | 47 |
| detect_integrated_ldos | 35 |
| detect_bms_systems | 25 |
| detect_transformer_feedback | 20 |
| detect_lvds_interfaces | 15 |
| detect_i2c_address_conflicts | 12 |

## How to reproduce

Anyone can reproduce the validation:

```bash
# 1. Clone the harness
git clone https://github.com/aklofas/kicad-happy-testharness.git
cd kicad-happy-testharness

# 2. Clone test repos
python3 checkout.py

# 3. Run analyzers (auto-parallelizes across all CPU cores)
python3 run/run_schematic.py --resume
python3 run/run_pcb.py --resume
python3 run/run_emc.py --resume

# 4. Run regression assertions
python3 regression/run_checks.py
```

The harness requires Python 3.8+ and a checkout of the corpus repos. ngspice is optional but recommended for SPICE assertions. Use `--cross-section smoke` for a quick 20-repo validation.

## Issue tracking

All analyzer bugs found during validation are tracked with sequential IDs:

- `KH-001` through `KH-326`: analyzer issues (278 filed, 278 closed, 0 open)
- `TH-001` through `TH-040`: harness infrastructure issues (35 filed, 31 closed, 4 open)

Each closed analyzer issue has a corresponding bugfix regression guard assertion that prevents the bug from returning.

## Numbers at a glance

| Metric | Value |
|--------|-------|
| Repos in corpus | 5,857 |
| Schematic files | 36,591 |
| PCB files | 18,752 |
| Gerber directories | 5,513 |
| EMC analyses | 42,513 |
| SPICE simulations | 36,565 |
| Components parsed | 1,305,789 |
| Nets traced | 2,090,189 |
| Regression assertions | 2,756,794 at 100% |
| Bugfix guards | 103 (100% — no regressions) |
| Closed issues | 278 analyzer + 31 harness |
| Open issues | 26 analyzer + 9 harness |
| Schematic detectors | 65 |
