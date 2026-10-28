# SPDX-License-Identifier: MPL-2.0
"""Reviewed continuations must reject altered inference before paid design calls."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.design_reviewed_task import run
from scripts.retry_reviewed_cad import retain_cad_constraints
from protocol_pipeline.autonomy import AutonomyProposal
from protocol_pipeline.compiler import ProtocolSpecification
from tests.test_autonomy import proposal_fixture


def test_changed_review_input_stops_before_allocation(tmp_path: Path) -> None:
    """Fail closed on a wrong protocol hash without creating a new snapshot."""
    source = tmp_path / 'source'
    reviewed = tmp_path / 'reviewed'
    (source / 'extracted').mkdir(parents=True)
    reviewed.mkdir()
    (source / 'task-context.json').write_text('{}')
    (source / 'extracted/extracted-protocol.json').write_text('{"changed":true}')
    (reviewed / 'review.json').write_text(json.dumps({'raw_protocol_sha256': 'not-the-file-hash'}))
    output = tmp_path / 'snapshots'
    with patch('scripts.design_reviewed_task.verify_manifest', return_value=({'video_filename': 'source.mp4'}, [])), \
         patch('scripts.design_reviewed_task.preflight') as preflight:
        with pytest.raises(ValueError, match='Reviewed extraction hash mismatch'):
            run(source, reviewed, output)
        preflight.assert_not_called()
    assert not output.exists()


def test_cad_handoff_preserves_exact_reviewed_constraints_and_raw_proposal(tmp_path: Path) -> None:
    """A model summary must not erase dimensions, body identities, or review provenance."""
    root = Path(__file__).resolve().parents[1]
    raw = json.loads((root/'examples/extraction/recorded-response.json').read_text())['responses'][0]['response']
    protocol = ProtocolSpecification.model_validate(raw)
    protocol.operations[0].constraints = ['Exact fixture envelope: 176 x 145 mm; do not scale the reference CAD.']
    proposal = {'proposal': AutonomyProposal.model_validate(proposal_fixture(protocol)).model_dump()}
    folder = tmp_path/'autonomy'/'attempt'
    folder.mkdir(parents=True)
    (tmp_path/'task-review').mkdir()
    (tmp_path/'task-review/protocol.json').write_text(protocol.model_dump_json())
    (tmp_path/'autonomy/job.json').write_text('{"attempt_id":"attempt"}')
    (folder/'proposal.json').write_text(json.dumps(proposal))
    retain_cad_constraints(tmp_path)
    assert json.loads((folder/'raw-proposal-before-cad-review.json').read_text()) == proposal
    updated = json.loads((folder/'proposal.json').read_text())
    assert protocol.operations[0].constraints[0] in [r['description'] for r in updated['proposal']['machine_requirements']]
    assert updated['cad_handoff_review']['protocol_sha256']
    with pytest.raises(ValueError, match='already exists'):
        retain_cad_constraints(tmp_path)
