# SPDX-License-Identifier: MPL-2.0
"""Native OpenCAD adapter for the existing bounded CAD-program export worker."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import runpy
from typing import Any


def build(source: Path, output: Path, tree_output: Path) -> dict[str, Any]:
    """Execute the trusted export wrapper with mandatory OCCT and retain its tree.

    Model-authored source is validated by execute_program, called by the wrapper.
    This adapter shares that worker's component exports and geometry validation;
    it does not require the older Forma checkout's external cad.py script.
    """
    import cadquery as cq
    import opencad
    from opencad.kernel.core.backend_factory import create_backend
    from opencad.kernel_adapter import registry_result_to_dict
    from opencad.runtime import RuntimeContext, use_default_context

    context = RuntimeContext(backend=create_backend("occt", require_native=True))
    with use_default_context(context):
        runpy.run_path(str(source), run_name="__main__")
        if not context.last_shape_id:
            raise ValueError("OpenCAD program produced no shape")
        result = registry_result_to_dict(context.registry, "export_step", {
            "shape_id": context.last_shape_id, "filepath": str(output)})
        if not result.get("ok"):
            raise ValueError(f"Native export failed: {result.get('message')}")
        context.save_tree_json(str(tree_output))
    shape = cq.importers.importStep(str(output)).val()
    if not shape.isValid() or not shape.Solids():
        raise ValueError("Native adapter STEP is invalid")
    return {"valid": True, "opencad_version": opencad.__version__, "backend": "occt",
            "features": len(context.tree.nodes) - 1}


def main() -> None:
    """Expose the same build arguments as the legacy Forma adapter."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build"])
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--tree-output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output, args.tree_output)))


if __name__ == "__main__":
    main()
