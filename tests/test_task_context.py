# SPDX-License-Identifier: MPL-2.0
"""Explicit task annotations must be attributed, video-bound and disclosed."""
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from protocol_pipeline.extraction import extract_protocol


@pytest.mark.parametrize('mismatch', [True, False])
def test_context_binding_and_disclosure(tmp_path: Path, mismatch: bool) -> None:
    """Reject wrong-video context before calls; retain assistance on provider failure."""
    run = tmp_path / 'ingested'
    (run / 'frames').mkdir(parents=True)
    context = tmp_path / 'context.json'
    context.write_text(json.dumps({'video_sha256': 'wrong' if mismatch else 'source-hash',
                                  'attribution': 'Publisher and reviewer', 'source_url': 'https://example.org',
                                  'task_scope': 'Join two blocks; exclude numbered card.'}))
    provider = Mock(name='provider', live=True)
    provider.name = 'test-provider'
    provider.complete.side_effect = RuntimeError('intentional stop before inference')
    output = tmp_path / 'output'
    with patch('protocol_pipeline.extraction.verify_manifest', return_value=({'video_sha256': 'source-hash'}, [])), \
         patch('protocol_pipeline.extraction.vision_content', return_value=[]):
        with pytest.raises(ValueError if mismatch else RuntimeError):
            extract_protocol(provider, 'text', output, run=run, vision_model='vision', task_context=context)
    if mismatch:
        provider.complete.assert_not_called()
        assert not output.exists()
    else:
        sent = provider.complete.call_args.args[3]
        assert 'Join two blocks' in sent[0]['text']
        source = json.loads((output / 'source-manifest.json').read_text())
        assert source['annotation_ground_truth_sent_to_model'] is True
        assert source['extraction_mode'] == 'annotation_assisted_video'
        assert (output / 'task-context.json').read_bytes() == context.read_bytes()
