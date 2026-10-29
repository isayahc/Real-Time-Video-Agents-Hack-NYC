# Submission asset permissions — reviewed October 27, 2026

Tracks #44. This is a source-based permission review, not a blanket determination
that hackathon participation is commercial or noncommercial.

**Replacement selected:** [ten BridgeData V2 trajectories](bridgedata-small-sample.md),
explicitly licensed by the publisher under CC BY 4.0. The CREOLab findings below
remain the historical review; the new E2E input uses BridgeData episode 01 instead.

## CREOLab source review

Reviewed upstream revision
[`6a91b376331871ec758e7a7dbad834b5d2582b8d`](https://github.com/ToyotaCRDL/CREOLab/tree/6a91b376331871ec758e7a7dbad834b5d2582b8d):

- [README](https://github.com/ToyotaCRDL/CREOLab/blob/6a91b376331871ec758e7a7dbad834b5d2582b8d/README.md)
  explicitly applies the same license to dataset and code.
- [LICENSE.md](https://github.com/ToyotaCRDL/CREOLab/blob/6a91b376331871ec758e7a7dbad834b5d2582b8d/LICENSE.md)
  grants use/copy/modification/merge for noncommercial research purposes,
  **specifically limited** to educational use, verification of research results,
  publication in academic papers and presentations at academic conferences.
- Copies or substantial portions must include the copyright and permission notice.
- Use of the copyright holder's name/trademarks in advertising or publicity
  pertaining to the material requires specific prior written permission.
- [Zenodo record 19702197](https://zenodo.org/records/19702197), dataset version 2,
  DOI `10.5281/zenodo.19702197`, identifies the data and links to the project.
  Its API metadata labels access open but provides no separate permissive license
  that expands the upstream grant. Open download access is not a use license.
- The README demonstrates paid hosted LLM API workflows. This supports an intended
  research API workflow; it does not independently establish permission for this
  project's hackathon/product-demo use, Nebius/GMI terms or public redistribution.
- Upstream execution logs have an additional result-inspection-only restriction.
  No upstream execution logs were downloaded or reused in this review.

## Selected candidate and publication inventory

| Local asset | Provenance | Current decision |
| --- | --- | --- |
| `docs/media/scenario05-input.mp4` | Documented as CREOLab `scenario05_decoy0.mp4` | Candidate only; not cleared by this review for the new hackathon provider run or public submission |
| `scenario05-input.jpg` / `.gif` | Still/derived attributed version of that clip | Same source restrictions; attribution alone does not establish expanded permission |
| `stacking-output.mp4` / `.gif` | Authored OpenIndustries animation using model-authored CAD and local refinements | Not source footage or physical execution; full third-party dependency/asset inventory remains to be reviewed |
| `sample-prices.png` | Planning-cost dashboard | Assumptions, not measured costs; final publication review pending |

Candidate MP4 SHA-256:
`c449a1ebe354b33f916a826f5c6d407911e3393031b23638a80140a3133606ff`.
This is the local file fingerprint, not a newly verified byte-for-byte comparison
against the dataset archive. Existing media and snapshots were preserved.

## Decision and authorization boundary

The user authorized **one** fresh paid E2E invocation after the input permission
gate is resolved: Nebius `nvidia/Nemotron-3.5-Super-VL` vision/critique and GMI
`openai/gpt-6-astra` reasoning/CAD, one visual-review pass, including existing
bounded retries/CAD corrections. No automatic second invocation after failure.
Total cost is not known in advance. **That authorization has not been consumed.**

The user selected review of CREOLab permissions rather than asserting additional
permission. The inspected sources do not clearly cover the proposed submission
use. Therefore no new CREOLab frames were uploaded and no paid E2E run was started
as part of this review. Public publication remains a separate decision.

To proceed, obtain specific written permission covering the intended use, or
select user-owned/permitted footage. An original synthetic clip is another option
if explicitly chosen, with all outputs labeled synthetic-input verification.

## Permission request draft (not sent)

> We would like to use CREOLab scenario05_decoy0.mp4 in a Nebius/NVIDIA Physical
> AI hackathon project demonstrating sampled-video procedure understanding and
> candidate CAD/scene generation. May we (1) send sampled frames and derived
> descriptions to Nebius Token Factory and GMI for inference, (2) retain derived
> outputs and checksummed evidence, (3) show the clip/frames with attribution in a
> public YouTube demonstration and Devpost entry, and (4) distribute the selected
> clip or derived frames in a public repository/judge evidence bundle? Please
> confirm permitted scope, attribution wording and any conditions, including use
> of Toyota CRDL's name in the attribution. We will distinguish original footage
> from generated designs and will not claim endorsement or physical execution.

The selected providers' applicable retention/use terms should accompany an actual
request. No permission contact was invented and no message was sent automatically.
