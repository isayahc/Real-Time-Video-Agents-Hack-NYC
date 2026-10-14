# V1 snapshot — coil-winding pilot cell

Snapshot date: October 13, 2026 (America/New_York). Parent: [Nebius epic #16](https://github.com/isayahc/Real-Time-Video-Agents-Hack-NYC/issues/16).

| File | Contents |
| --- | --- |
| metadata.json | CREOLab T1 selection, scene instances/transforms, creation provenance, validation and unresolved requirements. |
| cost-estimate.json | Supplier price references, quantities, custom-mechanism allowances and explicit exclusions. |
| human-costs.json | Initial deployment and recurring labor categories; unknown inputs remain null. |
| preprocessing-estimates.json | Estimated preprocessing steps, attended labor ranges, batch-size effects and unresolved inputs. |
| artifacts.json | Saved artifact identities, byte sizes and SHA-256 checksums. |

The cell contains wire feed/preparation, mandrel winding, optical inspection and collection/recovery. Scene geometry is an authored concept based on the published task description. Real OpenIndustries local MCP room creation/readback and native import/render verification are recorded; live Forma/Nebius generation, physical validation and economics evaluation have not occurred.

Priced components total **$601.01**. With unquoted custom-mechanism allowances, preliminary hardware cost is **$1,081.01–$1,731.01**. Human costs, automatic interstation transfer, shipping/tax, material and facility costs are excluded. A separate example quotes one meter of 0.254 mm platinum wire at $272.80; its specification is not established for the dataset.

Forma already provides BOM/cost functionality. This v1 estimate was independently assembled; future versions should bind actual Forma projects and cost outputs to scene instances.

Preserve v1 as the baseline and create v2 for revised designs or estimates.

## Estimated preprocessing — upstream manual work

Added October 13, 2026. These are **low-confidence planning assumptions**, not measured times or confirmed CREOLab annotations. Verify whether each step applies to the manual baseline and the proposed apparatus. The original clip/task description does not establish the complete preparation workflow.

### Per-batch preparation

| Candidate preprocessing operation | Assumed attended labor |
| --- | ---: |
| Select and verify wire stock/specification | 2–5 min/batch |
| Inspect and prepare mandrel/fixture; clean if required | 2–5 min/batch |
| Prepare labels, accepted-part trays and scrap container | 1–3 min/batch |
| Load/thread stock and establish initial tension | 3–8 min/batch |
| Home axes and calibrate inspection, where applicable | 5–15 min/batch |
| Produce/inspect a trial coil and adjust settings | 5–15 min/batch |
| **Illustrative total** | **18–51 min/batch** |

This assumes stock, tooling and equipment already exist. Machine design/fabrication, initial commissioning and operator training remain separate deployment costs. Cleaning, motor homing and machine-specific calibration apply only where needed.

### Per-coil preparation

| Candidate preprocessing operation | Assumed attended labor |
| --- | ---: |
| Measure and cut/pre-position wire | 10–30 s/attempt |
| Straighten/prepare ends if required | 5–20 s/attempt |
| Orient and secure wire for winding | 5–15 s/attempt |
| **Illustrative total** | **20–65 s/attempt** |

These totals exclude winding, final inspection, release/unloading and postprocessing. They are a scenario in which the listed tasks occur sequentially, not a measured production cycle.

### Batch-size effect and cost

Preprocessing time per accepted coil = **(60 × batch preparation minutes ÷ attempted coils per batch + preparation seconds per attempt) ÷ accepted fraction**.

At an illustrative 95% accepted fraction:

| Attempted coils per batch | Estimated preprocessing labor per accepted coil |
| ---: | ---: |
| 100 | 32.4–100.6 s |
| 1000 | 22.2–71.6 s |

Multiply seconds per accepted coil by **fully loaded hourly labor cost ÷ 3,600** to estimate its labor cost. The hourly rate, preparation energy and preparation material loss remain unknown.

**Avoid double counting:** threading/clamping can overlap loading; trial inspection can overlap inspection; calibration can overlap setup. Do not simply add these values to v2's assumed 15 seconds of operator touch. Map the tasks, reconcile overlaps and re-estimate the full cycle and throughput.

Machine-readable assumptions and formulas are in [preprocessing-estimates.json](preprocessing-estimates.json). The existing v1 hardware totals and scene remain unchanged.
