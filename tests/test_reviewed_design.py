# SPDX-License-Identifier: MPL-2.0
"""Reviewed continuations must reject altered inference before paid design calls."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.design_reviewed_task import run


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
