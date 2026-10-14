# Reusable protocol compiler

The same command accepts the coil and empty-tube transfer examples:

```bash
python -m protocol_pipeline compile-protocol \
  --input examples/protocols/coil.json --output runs/compiled-coil-001
python -m protocol_pipeline compile-protocol \
  --input examples/protocols/tube-transfer.json --output runs/compiled-transfer-001
```

The compiler validates explicitly supplied planning data and translates it into the existing apparatus and accounting contracts. It does not choose equipment automatically, extract instructions from video, or validate physical feasibility. There are no task-name branches or hardware lookup tables in `compiler.py`.

## Input contract

See [JSON Schema](../../schemas/protocol-specification.json), [coil input](coil.json) and [tube-transfer input](tube-transfer.json).

| Field | Meaning |
| --- | --- |
| `protocol_id`, `title` | Process identity and report title |
| `functional_unit`, `boundary` | What accepted output means and which full-process work is included |
| `operations` | Preparation/processing/finishing operations, repetition, objects, provenance, conditions, constraints and optional unmeasured attended ranges |
| `links` | Explicit proposed `before` or `during` relationships; precedence must be acyclic |
| `capabilities` | Required capabilities mapped to operation IDs, with supplied candidate equipment and rationale |
| `acceptance_criteria` | Expected results, related operations, source references and required verification |
| `resource_inputs` | Existing accounting quantities with exact units, basis and source; missing remains unknown |
| `engineering_inputs` | Separate sourced hardware parameters, costs, labor, power and byproduct inputs retained in the design handoff |
| `limitations` | What remains unreviewed, unmeasured or unsupported |

Every operation needs capability coverage. Dangling references, duplicate IDs, invalid units/ranges and precedence cycles are rejected. Concurrent links are preserved rather than made sequential. Acceptance intent never sets `acceptance_verified` true.

The resource report evaluates supplied full-batch values; it does not sum preparation ranges or infer quantities from equipment labels. Engineering design parameters are separate from production resource accounting: a motor specification alone is not measured full-process energy.

## Outputs

- `protocol-input.json`: original input bytes and a SHA-256 in the summary.
- `process-graph.json`: operations, provenance, repetitions and dependencies.
- `apparatus-requirements.json`: the existing typed design handoff, usable by `build --requirements` when a compatible runtime is available.
- `process-input.json`: the existing resource-evaluator contract, with acceptance unverified.
- `summary.json` and `report.md`: resource results, acceptance checks, missing inputs and limitations.

The executed reports are included in [coil output](coil/report.md) and [tube-transfer output](tube-transfer/report.md).

## Coil migration and second example

The existing coil adapter still reads legacy protocol/preparation sources for compatibility. It now converts them into `ProtocolSpecification` and delegates both apparatus requirements and full-process inputs to the shared compiler. `coil.json` exports the same plan; a test checks exact equivalence to the legacy-source adapter. Winding-only accounting remains separate.

The second example transfers empty, capped, inert demonstration tubes between racks. Its seven operations cover preparation, identification, grip, transfer, placement, verification and reset. Equipment choices are authored candidates, not an observed laboratory protocol or a recommendation to execute an unverified system. No liquids or biological processing are included.

## Verification

77 tests passed without skips. Four new tests cover coil migration parity, compilation of two different processes, missing resource values/output preservation, malformed references/coverage/units/cycles and arbitrary IDs with sourced resource inputs. CI now runs seven offline workflows, including both generic examples, with Python socket connections blocked. [Checks](checks.json) preserve the local verification evidence.
