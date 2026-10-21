# SPDX-License-Identifier: MPL-2.0
"""Verify two distinct processes use one compiler and enforce contract integrity."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from protocol_pipeline.compiler import ProtocolSpecification, compile_protocol_file, compile_specification
from protocol_pipeline.design import ApparatusRequirements
from protocol_pipeline.offline import coil_specification, compile_coil

ROOT = Path(__file__).resolve().parents[1]


class CompilerTests(unittest.TestCase):
    """Check migration equivalence, generality, accounting and invalid references."""

    def specification(self, name: str) -> ProtocolSpecification:
        """Read a real bundled input rather than duplicating compiler output logic."""
        return ProtocolSpecification.model_validate_json((ROOT / f"examples/protocols/{name}.json").read_text())

    def test_coil_migration_preserves_adapter_contract(self) -> None:
        """The exported coil specification and legacy-source adapter agree exactly."""
        graph, requirements, _ = compile_coil(ROOT)
        fixture = self.specification("coil")
        self.assertEqual(fixture.model_dump(), coil_specification(graph).model_dump())
        compiled, _ = compile_specification(fixture)
        self.assertEqual(compiled.model_dump(), requirements.model_dump())
        self.assertEqual(len(compiled.protocol_operations), 19)

    def test_distinct_processes_compile_without_task_lookups(self) -> None:
        """Coil and tube transfer preserve different supplied capabilities/objects."""
        with tempfile.TemporaryDirectory() as folder:
            for name, expected in (("coil", 19), ("tube-transfer", 7)):
                output = Path(folder) / name
                summary = compile_protocol_file(ROOT / f"examples/protocols/{name}.json", output)
                requirements = ApparatusRequirements.model_validate_json((output / "apparatus-requirements.json").read_text())
                self.assertEqual(len(requirements.protocol_operations), expected)
                self.assertFalse(summary["accounting"]["acceptance_verified"])
                self.assertTrue(all(metric["value"] is None for metric in summary["accounting"]["metrics"].values()))
                original = (output / "summary.json").read_bytes()
                with self.assertRaises(FileExistsError):
                    compile_protocol_file(ROOT / f"examples/protocols/{name}.json", output)
                self.assertEqual(original, (output / "summary.json").read_bytes())

    def test_capability_coverage_acceptance_and_ordering(self) -> None:
        """Reject unmapped operations, dangling references and cyclic dependencies."""
        original = self.specification("tube-transfer").model_dump()
        mutations = [
            lambda d: d["capabilities"].pop(),
            lambda d: d["capabilities"][0].update(operation_ids=["missing"]),
            lambda d: d["acceptance_criteria"][0].update(operation_ids=["missing"]),
            lambda d: d["links"].append({'source':'reset_station','target':'prepare_racks','relation':'before'}),
            lambda d: d["operations"].append(d["operations"][0]),
            lambda d: d["resource_inputs"]["electricity_wh"].update(unit="kWh"),
        ]
        for mutation in mutations:
            data = copy.deepcopy(original)
            mutation(data)
            with self.assertRaises(ValueError):
                ProtocolSpecification.model_validate(data)

    def test_arbitrary_ids_and_sourced_resource_values(self) -> None:
        """Changing identifiers needs no compiler code; supplied quantities retain basis."""
        data = self.specification("tube-transfer").model_dump()
        data["protocol_id"] = "another-process"
        data["operations"][0]["id"] = "generic_station_setup"
        data["capabilities"][0]["operation_ids"] = ["generic_station_setup"]
        data["links"][0]["source"] = "generic_station_setup"
        for key, value in (("accepted_count", 10), ("attempted_count", 10), ("elapsed_s", 3600)):
            data["resource_inputs"][key].update(value=value, basis="assumed", source="Explicit test arithmetic scenario")
        spec = ProtocolSpecification.model_validate(data)
        requirements, process = compile_specification(spec)
        self.assertEqual(requirements.protocol_operations[0].id, "generic_station_setup")
        self.assertEqual(process.inputs["elapsed_s"].basis, "assumed")
        self.assertFalse(process.acceptance_verified)


if __name__ == "__main__":
    unittest.main()
