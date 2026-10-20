"""Small, debuggable live extraction example."""
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from protocol_pipeline.extraction import create_provider, extract_protocol


TEXT = ROOT / "examples" / "extraction" / "procedure.txt"
MODEL = "nvidia/Nemotron-3_5-Lightning"


def main() -> None:
    """Run one live text extraction using the project pipeline."""
    output = ROOT / "runs" / f"debug-extraction-{datetime.now():%Y%m%d-%H%M%S-%f}"
    provider = create_provider("nebius")
    result = extract_protocol(provider, MODEL, output, text_path=TEXT)
    print(result)


if __name__ == "__main__":
    main()
