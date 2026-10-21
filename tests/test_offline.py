# SPDX-License-Identifier: MPL-2.0
"""Verify the fixed-protocol handoff and prevent cross-boundary accounting."""
from __future__ import annotations

import json
import shutil
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from protocol_pipeline.design import ApparatusRequirements
from protocol_pipeline.offline import WorkflowGraph, compile_coil, run_coil_offline

ROOT = Path(__file__).resolve().parents[1]


class OfflineCoilTests(unittest.TestCase):
    """Exercise actual source files, missing values, links and output protection."""

    def test_full_boundary_not_populated_from_partial(self) -> None:
        """Winding-only assumptions cannot fill full-process cost, yield or energy."""
        with tempfile.TemporaryDirectory() as folder:
            result = run_coil_offline(ROOT, Path(folder) / "run")
            self.assertTrue(all(value["value"] is None for value in result["full_process_evaluation"]["metrics"].values()))
            self.assertAlmostEqual(result["winding_only_evaluation"]["metrics"]["electricity_wh_per_accepted"]["value"], 1 / 6)
            self.assertIsNone(result["winding_only_evaluation"]["metrics"]["cost_usd_per_accepted"]["value"])
            self.assertFalse(result["full_process_evaluation"]["acceptance_verified"])

    def test_source_mapping_and_concurrency(self) -> None:
        """Preserve all preparation, core and finishing operations with references."""
        graph, requirements, sources = compile_coil(ROOT)
        self.assertEqual(len(graph.nodes), 19)
        self.assertEqual(len([node for node in graph.nodes if node.phase == "preparation"]), 9)
        self.assertEqual({node.id for node in graph.nodes}, {op.id for op in requirements.protocol_operations})
        self.assertEqual(len(requirements.required_capabilities), 19)
        self.assertTrue(any(link.source == "maintain_tension" and link.relation == "during" for link in graph.links))
        for node in graph.nodes:
            source, pointer = node.source_ref.split("#/")
            value = json.loads((ROOT / source).read_text())
            for token in pointer.split("/"):
                value = value[int(token)] if isinstance(value, list) else value[token]
            self.assertIsInstance(value, dict)
        self.assertEqual(len(sources), 4)

    def test_network_blocked_and_existing_output_preserved(self) -> None:
        """Execute without network connections and reject any evidence overwrite."""
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "run"
            with patch.object(socket.socket, "connect", side_effect=AssertionError("network prohibited")), patch("socket.create_connection", side_effect=AssertionError("network prohibited")):
                run_coil_offline(ROOT, output)
            original = (output / "summary.json").read_bytes()
            with self.assertRaises(FileExistsError):
                run_coil_offline(ROOT, output)
            self.assertEqual(original, (output / "summary.json").read_bytes())
            ApparatusRequirements.model_validate_json((output / "apparatus-requirements.json").read_text())

    def test_unknown_or_duplicate_protocol_rejected(self) -> None:
        """Unsupported fixed-task variants cannot silently receive candidate mappings."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copytree(ROOT / "snapshots", root / "snapshots")
            path = root / "snapshots/v2/protocol.json"
            data = json.loads(path.read_text())
            data["steps"][0]["operation"] = "unknown"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "five unique"):
                compile_coil(root)
            data["steps"][0]["operation"] = data["steps"][1]["operation"]
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "five unique"):
                compile_coil(root)

    def test_broken_links_and_ordering_cycles_rejected(self) -> None:
        """A graph cannot claim ordering through absent nodes or a cyclic sequence."""
        graph, _, _ = compile_coil(ROOT)
        data = graph.model_dump()
        data["links"].append({"source": "constrain", "target": "missing", "relation": "before"})
        with self.assertRaises(ValueError):
            WorkflowGraph.model_validate(data)
        data = graph.model_dump()
        data["links"].append({"source": "relative_rotation", "target": "constrain", "relation": "before"})
        with self.assertRaises(ValueError):
            WorkflowGraph.model_validate(data)


if __name__ == "__main__":
    unittest.main()
