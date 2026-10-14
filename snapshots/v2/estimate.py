"""Author a Forma-compatible coil-winder concept and reproducible estimates."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from forma_core.workspaces.projects.models import HardwareIntermediateRepresentation


@dataclass(frozen=True)
class Scenario:
    """Illustrative inputs; these are not recovered CREOLab specifications."""

    wire_diameter_mm: float = 0.254
    mandrel_diameter_mm: float = 3.0
    turns: int = 10
    pitch_mm: float = 0.35
    retained_leads_mm: float = 20.0
    trim_loss_mm: float = 5.0
    density_g_cm3: float = 21.45
    reject_fraction: float = 0.05
    cycle_s: float = 30.0
    active_s: float = 15.0
    active_w: float = 30.0
    idle_w: float = 8.0
    operator_touch_s: float = 15.0
    operating_hours: float = 8.0
    wire_price_usd_m: float = 272.8


def calculate(s: Scenario) -> dict[str, Any]:
    """Calculate helix length, material balance, duty-cycle energy and touch labor."""
    turn_length_mm = math.hypot(math.pi * (s.mandrel_diameter_mm + s.wire_diameter_mm), s.pitch_mm)
    retained_mm = s.turns * turn_length_mm + s.retained_leads_mm
    input_mm = retained_mm + s.trim_loss_mm
    linear_mass_g_mm = math.pi * s.wire_diameter_mm**2 / 4 * s.density_g_cm3 / 1000
    yield_fraction = 1 - s.reject_fraction
    gross_per_hour = 3600 / s.cycle_s
    energy_wh_gross = (s.active_w * s.active_s + s.idle_w * (s.cycle_s - s.active_s)) / 3600
    scrap_fraction = 1 - yield_fraction * retained_mm / input_mm
    return {
        "basis": "Illustrative analytical scenario, not measured performance",
        "inputs": asdict(s),
        "retained_wire_length_mm": retained_mm,
        "input_wire_length_mm": input_mm,
        "nominal_coil_outer_diameter_mm_before_springback": s.mandrel_diameter_mm + 2 * s.wire_diameter_mm,
        "nominal_coil_axial_span_mm": (s.turns - 1) * s.pitch_mm + s.wire_diameter_mm,
        "retained_mass_g": retained_mm * linear_mass_g_mm,
        "input_mass_g": input_mm * linear_mass_g_mm,
        "trim_mass_g_per_attempt": s.trim_loss_mm * linear_mass_g_mm,
        "scrap_fraction_including_rejects": scrap_fraction,
        "scrap_g_per_attempt_expected": (input_mm - yield_fraction * retained_mm) * linear_mass_g_mm,
        "wire_purchase_cost_usd_per_accepted_coil_before_scrap_credit": input_mm / 1000 * s.wire_price_usd_m / yield_fraction,
        "gross_coils_per_hour": gross_per_hour,
        "accepted_coils_per_hour": gross_per_hour * yield_fraction,
        "energy_wh_per_attempt": energy_wh_gross,
        "energy_wh_per_accepted_coil": energy_wh_gross / yield_fraction,
        "shift_energy_kwh": energy_wh_gross * gross_per_hour * s.operating_hours / 1000,
        "operator_touch_hours_per_shift": s.operator_touch_s * gross_per_hour * s.operating_hours / 3600,
        "operator_touch_s_per_accepted_coil": s.operator_touch_s / yield_fraction,
        "labor_cost_formula": "operator_touch_s_per_accepted_coil / 3600 * loaded_hourly_rate; add supervision, setup and downtime labor separately",
        "power_sensitivity": [
            {"active_w": a, "idle_w": i, "active_s": s.active_s,
             "wh_per_accepted_coil": (a * s.active_s + i * (s.cycle_s - s.active_s)) / 3600 / yield_fraction,
             "shift_kwh": (a * s.active_s + i * (s.cycle_s - s.active_s)) / s.cycle_s * s.operating_hours / 1000}
            for a, i in [(25, 5), (30, 8), (40, 12)]
        ],
        "motor_copper_loss_upper_example_w": 2 * 2 * 0.35**2 * 35,
        "motor_loss_note": "Two motors, two phases each at full 0.35 A: sum(I^2 R). Driver current waveform, supply efficiency and mechanical work change actual wall draw.",
    }


def author_ir() -> HardwareIntermediateRepresentation:
    """Use Forma's real schema and deterministic BOM derivation for the concept."""
    catalog = [
        ("motor", "Adafruit 324", "NEMA-17 winding/traverse motor", 2, 14.0, "https://www.adafruit.com/product/324", "listed_price"),
        ("driver", "Adafruit 6109", "A4988 driver", 2, 6.95, "https://www.adafruit.com/product/6109", "listed_price"),
        ("controller", "Adafruit 4864", "Pico motion controller", 1, 4.0, "https://www.adafruit.com/product/4864", "listed_price_out_of_stock"),
        ("camera", "Adafruit 5657", "Camera Module 3", 1, 29.25, "https://www.adafruit.com/product/5657", "listed_price"),
        ("supply", "Adafruit 352", "12 V / 5 A supply", 1, 24.95, "https://www.adafruit.com/product/352", "listed_price"),
        ("host", "concept-host-lighting", "Camera host, lighting and 5 V conversion", 1, 130.0, None, "allowance_80_180"),
        ("frame", "concept-frame-guard", "Base frame and enclosure/guard", 1, 175.0, None, "allowance_100_250"),
        ("spindle", "concept-mandrel", "Spindle, bearings and removable mandrel", 1, 110.0, None, "allowance_60_160"),
        ("traverse", "concept-linear-guide", "Lead screw, linear guide and carriage", 1, 100.0, None, "allowance_50_150"),
        ("tension", "concept-dancer-brake", "Passive tensioner, spool brake and rollers", 1, 137.5, None, "allowance_75_200"),
        ("sensing", "concept-tension-sensors", "Tension sensing and home/limit switches", 1, 55.0, None, "allowance_30_80"),
        ("handling", "concept-release-tools", "Manual cutting/release tools and segregated trays", 1, 70.0, None, "allowance_40_100"),
    ]
    definitions = []
    components = []
    for part_id, number, name, quantity, price, url, basis in catalog:
        definitions.append({"part_definition_id": part_id, "part_number": number, "name": name,
                            "category": "Actuator" if part_id == "motor" else "Subsystem",
                            "unit_price": price, "sourcing_url": url,
                            "description": f"Concept selection; pricing basis: {basis}. Must verify engineering suitability.",
                            "sourcing_offers": [{"basis": basis, "checked_date": "2026-10-13"}]})
        for n in range(quantity):
            components.append({"ref_des": f"{part_id.upper()}{n+1}", "part_definition_id": part_id,
                               "rationale": name, "configuration": {"selection_status": "provisional"}})
    ir = HardwareIntermediateRepresentation.model_validate({
        "hardware_ir_version": "0.2", "part_definitions": definitions, "components": components,
        "overview": {"title": "CW-02: two-axis benchtop coil winder", "description": "Agent-authored concept reproducing wire-to-helix transformation with human loading, cutting and unloading. Schema validation is not physical validation.", "difficulty": "Advanced", "category": "Automation"},
        "requirements": {"requirements": ["Constrain wire to a removable cylindrical mandrel", "Maintain adjustable tension without damaging wire", "Synchronize traverse distance with spindle turns to control pitch", "Count turns and inspect geometry", "Release and collect the coil with recoverable scrap separated"], "power_needs": "12 V motion supply and regulated 5 V camera-host/control supply; budget 25–40 W active, 5–12 W released idle", "operating_voltage": 12,
                         "missing_info": ["Actual wire diameter, temper and surface requirements", "Final coil diameter, pitch, turn count, lead lengths and tolerances", "Springback calibration", "Tension and torque limits", "Cutting/release yield and inspection resolution"],
                         "physical_constraints": ["One benchtop workcell; concept geometry only"], "safety_notes": ["Provide a guarded winding zone and stop/interlock before hardware operation; electrical wiring remains undesigned."]},
        "constraints": ["Cold mechanical winding only; no heating or solvent step", "No unattended automatic loading, cutting or unloading", "No scientific equivalence claim beyond the same intended geometric transformation"],
        "assembly_metadata": {"project_id": "cw-02-coil-winder-v2", "revision": "2", "agent": "Codex", "pricing_basis": "supplier examples plus explicitly labeled midpoint allowances", "physical_validation": False, "electrical_wiring_complete": False},
        "is_valid": False,
    })
    ir.overview.estimated_cost = round(sum(item.extended_price for item in ir.bom), 2)
    return ir


def main() -> None:
    """Save scenario estimates, protocol, and schema-validated Forma IR."""
    output = Path(__file__).resolve().parent
    estimate = calculate(Scenario())
    ir = author_ir()
    protocol = {"basis": "Published CREOLab T1 task, with proposed machine implementation; original annotation not ingested", "steps": [
        {"operation": "constrain", "apparatus": "removable mandrel clamp", "human_action": "load wire end", "expected": "wire held without slipping"},
        {"operation": "establish_contact", "apparatus": "guide and mandrel", "human_action": "thread the guide", "expected": "wire contacts cylindrical forming surface"},
        {"operation": "relative_rotation", "apparatus": "stepper spindle and synchronized traverse", "human_action": "start cycle", "expected": "target turns and pitch formed"},
        {"operation": "maintain_tension", "apparatus": "passive dancer/spool brake and tension sensor", "human_action": "set tension during setup", "expected": "stable tension below tested damage limit"},
        {"operation": "verify_and_release", "apparatus": "camera/backlight, removable mandrel and manual cutting tools", "human_action": "cut and remove coil", "expected": "inspect final diameter, pitch, turns and lead geometry after release"}],
        "equivalence_gate": "Measure released coil against actual protocol target; calibrate mandrel diameter for springback. Geometry alone does not establish electrode/experiment performance."}
    for name, value in [("estimates.json", estimate), ("protocol.json", protocol), ("coil-winder.forma.json", ir.model_dump(mode="json"))]:
        (output / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    checks = {"forma_schema_validated": True, "forma_source_commit": "d83f0799a182894ff04366ba0f8137d0e5b2b99a", "bom_line_count": len(ir.bom), "component_instance_count": len(ir.components), "midpoint_bom_usd": ir.overview.estimated_cost, "hardware_low_usd": 535.10, "hardware_high_usd": 1220.10, "is_valid": ir.is_valid, "note": "Typed data/BOM validation only. No compile_project call, LLM inference, electrical rule validation or physical validation."}
    (output / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    print(json.dumps({"checks": checks, "estimates": estimate}))


if __name__ == "__main__":
    main()
