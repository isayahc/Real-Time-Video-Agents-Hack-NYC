"""Design handoff contracts, provenance and safe execution boundary tests."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from protocol_pipeline.design import (
    ApparatusRequirements, DesignJob, SceneRequest, build_design, synthesis_prompt,
)
from protocol_pipeline.forma_worker import unwrap_project
from protocol_pipeline.models import EngineeringInputs


def requirements() -> ApparatusRequirements:
    """Create an unresolved unit-test handoff with no fabricated observations."""
    return ApparatusRequirements(required_capabilities=[], protocol_operations=[],
                                unresolved_requirements=['Wire specification unknown'],
                                engineering_inputs=EngineeringInputs())


class DesignTests(unittest.TestCase):
    """Validate mode separation, known/unknown constraints and immutable output paths."""

    def test_live_requires_explicit_runtime(self) -> None:
        """Live mode cannot select an implicit model or simulation provider."""
        for provider, model in [(None, None), ('openai', None), ('simulation', 'fixture')]:
            with self.assertRaises(ValidationError):
                DesignJob(mode='live', brief='test', requirements=requirements(),
                          scene=SceneRequest(name='test'), provider=provider, model=model)

    def test_replay_requires_project(self) -> None:
        """Only replay can carry an existing project path."""
        with self.assertRaises(ValidationError):
            DesignJob(mode='replay', brief='test', requirements=requirements(), scene=SceneRequest(name='test'))
        with self.assertRaises(ValidationError):
            DesignJob(mode='simulation', replay_project='existing.json', brief='test',
                      requirements=requirements(), scene=SceneRequest(name='test'))

    def test_room_ranges(self) -> None:
        """Reject impossible/nonfinite rooms before MCP calls."""
        for room in [(0, 5, 3), (101, 5, 3), (float('nan'), 5, 3)]:
            with self.assertRaises(ValidationError):
                SceneRequest(name='test', room_m=room)

    def test_prompt_retains_unknown_and_revision(self) -> None:
        """Unresolved requirements and explicit revision context reach generation."""
        job = DesignJob(mode='simulation', brief='test', requirements=requirements(),
                        scene=SceneRequest(name='test'), revision_instruction='Replace fixture')
        prompt = synthesis_prompt(job)
        self.assertIn('Wire specification unknown', prompt)
        self.assertIn('Replace fixture', prompt)
        self.assertIn('null means unknown', prompt)
        self.assertIn('Do not claim physical validation', prompt)

    def test_supported_forma_wrappers(self) -> None:
        """Replay resolves supported native project wrappers without discarding IR."""
        ir = {'name': 'test'}
        self.assertEqual(unwrap_project({'project_ir': ir}), ir)
        self.assertEqual(unwrap_project({'hardware_ir': ir}), ir)
        self.assertEqual(unwrap_project(ir), ir)

    def test_requirement_reference_validation(self) -> None:
        """A capability cannot quietly target an absent operation."""
        payload = requirements().model_dump()
        payload['required_capabilities'] = [{'id': 'a', 'name': 'test', 'operation_ids': ['missing'], 'rationale': 'test'}]
        with self.assertRaises(ValidationError):
            ApparatusRequirements.model_validate(payload)

    def test_missing_runtime_before_output(self) -> None:
        """Missing OI dependencies fail before a run directory is created."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'requirements.json'
            source.write_text(requirements().model_dump_json())
            with self.assertRaises(ValueError):
                build_design(source, root / 'output', None, root / 'missing', 'simulation', 'test', SceneRequest(name='test'))
            self.assertFalse((root / 'output').exists())

    def test_failure_retains_inputs(self) -> None:
        """Stage failures preserve inputs and a safe failure marker, with no fabricated scene."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            oi = root / 'oi'
            (oi / 'server').mkdir(parents=True)
            (oi / 'server/astra-mcp.mjs').write_text('')
            (oi / 'node_modules/tsx').mkdir(parents=True)
            source = root / 'requirements.json'
            source.write_text(requirements().model_dump_json())
            with patch('protocol_pipeline.design.run_worker', side_effect=RuntimeError('private worker error')):
                with self.assertRaises(RuntimeError):
                    build_design(source, root / 'output', None, oi, 'simulation', 'test', SceneRequest(name='test'))
            failure = json.loads((root / 'output/build-failure.json').read_text())
            self.assertEqual(failure['stage'], 'forma')
            self.assertNotIn('private worker error', json.dumps(failure))
            self.assertTrue((root / 'output/build-input.json').exists())
            self.assertFalse((root / 'output/design-manifest.json').exists())

    def test_existing_output_is_preserved(self) -> None:
        """No generation occurs when the output run path already exists."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'oi/server').mkdir(parents=True)
            (root / 'oi/server/astra-mcp.mjs').write_text('')
            (root / 'oi/node_modules/tsx').mkdir(parents=True)
            source = root / 'requirements.json'
            source.write_text(requirements().model_dump_json())
            output = root / 'output'
            output.mkdir()
            (output / 'keep.txt').write_text('previous evidence')
            with patch('protocol_pipeline.design.run_worker') as worker:
                with self.assertRaises(FileExistsError):
                    build_design(source, output, None, root / 'oi', 'simulation', 'test', SceneRequest(name='test'))
                worker.assert_not_called()
            self.assertEqual((output / 'keep.txt').read_text(), 'previous evidence')

    def test_prediction_link_requires_both_arguments(self) -> None:
        """A source prediction cannot become an unverified detached ID."""
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'requirements.json'
            source.write_text(requirements().model_dump_json())
            with self.assertRaises(ValueError):
                build_design(source, Path(folder)/'output', None, Path(folder), 'simulation', 'test',
                             SceneRequest(name='test'), prediction_id='p1')


if __name__ == '__main__':
    unittest.main()
