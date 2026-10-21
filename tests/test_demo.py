# SPDX-License-Identifier: MPL-2.0
"""Single-command demo accounting, evidence separation and report tests."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from protocol_pipeline.demo import report_html, run_demo, value_text
from protocol_pipeline.iteration import load_record

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'


class DemoTests(unittest.TestCase):
    """Check actual evaluator orchestration without optional design runtimes."""

    def test_accounting_demo(self) -> None:
        """Execute both evaluators and revision while keeping coil economics unknown."""
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'demo'
            summary = run_demo(output, EXAMPLES, accounting_only=True)
            self.assertEqual(summary['status'], 'accounting_only')
            self.assertEqual(summary['coil_scene']['status'], 'skipped_accounting_only')
            self.assertEqual(summary['coil_investment_decision'], 'undetermined')
            self.assertIsNone(summary['coil_unit_cost'])
            self.assertEqual(summary['illustrative_loop']['revision_conclusion'], 'predicted_tradeoff')
            self.assertEqual(summary['illustrative_loop']['metrics']['cost_usd_per_accepted']['prediction']['value'], 2)
            self.assertEqual(load_record(output / 'records', 'p2').record.version, 2)
            text = (output / 'report.md').read_text()
            self.assertIn('fabricated examples and do not describe CW-02', text)
            self.assertIn('explicitly skipped', text)
            self.assertIn('Actual coil unit cost: **Unknown**', text)
            self.assertTrue((output / 'report.html').is_file())

    def test_existing_output_preserved(self) -> None:
        """A second demo cannot replace prior records or reports."""
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'demo'
            run_demo(output, EXAMPLES, accounting_only=True)
            before = (output / 'report.md').read_bytes()
            with self.assertRaises(FileExistsError):
                run_demo(output, EXAMPLES, accounting_only=True)
            self.assertEqual((output / 'report.md').read_bytes(), before)

    def test_full_demo_requires_scene_runtime(self) -> None:
        """Do not silently omit scene execution from a full demo."""
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'demo'
            with self.assertRaises(ValueError):
                run_demo(output, EXAMPLES)
            self.assertFalse(output.exists())

    def test_scene_failure_is_not_success(self) -> None:
        """Preserve completed loop evidence but reject a failed scene stage."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / 'project.json'
            project.write_text('{}')
            with patch('protocol_pipeline.demo.build_design', side_effect=RuntimeError('failed scene')):
                with self.assertRaises(RuntimeError):
                    run_demo(root / 'demo', EXAMPLES, oi_root=root, coil_project=project)
            self.assertTrue((root / 'demo/demo-failure.json').is_file())
            self.assertFalse((root / 'demo/report.html').exists())
            self.assertFalse((root / 'demo/demo-summary.json').exists())
            self.assertEqual(load_record(root / 'demo/records', 'p2').record.version, 2)

    def test_report_html_escapes_labels(self) -> None:
        """Treat custom report labels as data, never executable HTML."""
        with tempfile.TemporaryDirectory() as folder:
            summary = run_demo(Path(folder) / 'demo', EXAMPLES, accounting_only=True)
            with patch.dict('protocol_pipeline.demo.LABELS', {'cost_usd_per_accepted': '<script>alert(1)</script>'}):
                document = report_html(summary)
            self.assertNotIn('<script>', document)
            self.assertIn('&lt;script&gt;', document)

    def test_zero_unknown_undefined(self) -> None:
        """Distinguish genuine zero, unknown input and undefined division."""
        self.assertEqual(value_text(0), '0')
        self.assertEqual(value_text(None), 'Unknown')
        self.assertEqual(value_text(None, 'undefined'), 'Undefined')


if __name__ == '__main__':
    unittest.main()
