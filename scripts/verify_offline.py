"""Execute every bundled offline workflow with network connections blocked."""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
from pathlib import Path
from unittest.mock import patch

from protocol_pipeline.alternatives import run_alternatives
from protocol_pipeline.demo import run_demo
from protocol_pipeline.failures import run_failures
from protocol_pipeline.offline import run_coil_offline
from protocol_pipeline.compiler import compile_protocol_file
from protocol_pipeline.extraction import ReplayProvider, extract_protocol


def main() -> None:
    """Build CI artifacts and fail if any offline stage attempts a connection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output must be new")
    root = Path(__file__).resolve().parents[1]
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Offline run attempted network access")), \
         patch.object(socket.socket, "connect_ex", side_effect=AssertionError("Offline run attempted network access")), \
         patch("socket.create_connection", side_effect=AssertionError("Offline run attempted network access")):
        run_demo(args.output / "accounting", root / "examples", accounting_only=True)
        run_coil_offline(root, args.output / "coil")
        for name in ("evidence", "illustrative"):
            run_alternatives(root / f"examples/apparatus-alternatives/{name}-input.json", args.output / name)
        run_failures(root, args.output / "failures")
        for name in ("coil", "tube-transfer"):
            compile_protocol_file(root / f"examples/protocols/{name}.json", args.output / ("compiled-" + name))
        extract_protocol(ReplayProvider(root / "examples/extraction/recorded-response.json"), "offline-fixture",
                         args.output / "extraction-replay", text_path=root / "examples/extraction/procedure.txt")
    checks = {"status": "passed", "network_connections_blocked": True, "physical_validation": False,
              "artifacts_sha256": {str(path.relative_to(args.output)): hashlib.sha256(path.read_bytes()).hexdigest()
                                   for path in sorted(args.output.rglob("*")) if path.is_file()}}
    (args.output / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    print(json.dumps({"status": "passed", "workflows": 8, "network_connections_blocked": True}))


if __name__ == "__main__":
    main()
