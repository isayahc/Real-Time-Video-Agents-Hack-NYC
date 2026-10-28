# SPDX-License-Identifier: MPL-2.0
"""Run only task-context-assisted observations/protocol, stopping before design/CAD."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol_pipeline.environment import load_environment
from protocol_pipeline.extraction import GMIProvider, NebiusProvider, extract_protocol


def main() -> None:
    """Keep paid extraction separate from downstream generation for semantic review."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ingested', type=Path, required=True)
    parser.add_argument('--task-context', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--vision-model', default='nvidia/Nemotron-3.5-Super-VL')
    parser.add_argument('--text-model', default='openai/gpt-6-astra')
    args = parser.parse_args()
    load_environment()
    result = extract_protocol(GMIProvider(), args.text_model, args.output, run=args.ingested,
                              vision_model=args.vision_model, vision_provider=NebiusProvider(),
                              task_context=args.task_context, progress=lambda stage: print(stage, flush=True))
    print(result['status'])


if __name__ == '__main__':
    main()
