# IndustReal: capped recorded-baseline retrieval

**Continuation:** the accessible [HA4M ten-trial baseline](ha4m-small-sample.md)
now supplies authoritative action timelines. IndustReal remains a future option
for richer error/state evaluation once its labels become accessible.

## Current result

Retrieval is **blocked**, not a completed benchmark. The official 4TU landing page
and `/v2/articles/b008dd74-020d-4ea4-a8ba-7bb60769d224/files` endpoint time out.
Two bounded mirror download attempts failed with TLS connection resets while
reading ZIP metadata. **Zero recordings downloaded; no baseline calculated.**
Failure manifests remain in ignored `runs/industreal-ten-20261028/` and
`runs/industreal-ten-20261028-attempt2/`. No paid inference was performed.

## Sources and provenance

- [Authors' project](https://timschoonbeek.github.io/industreal.html): 84 manual
  construction-toy assembly/maintenance recordings by 27 participants.
- Authors' code revision: `ad86a35d4b5125739e24af677e5d7b55c74af945` at
  [TimSchoonbeek/IndustReal](https://github.com/TimSchoonbeek/IndustReal).
- Publisher DOI v1: `10.4121/b008dd74-020d-4ea4-a8ba-7bb60769d224.v1`.
  A newer v2 exists, published August 23, 2024. DataCite metadata confirms
  **Apache-2.0** for both versions; neither supplies direct file URLs.
- Third-party video mirror: [Zzitang/IndustReal](https://huggingface.co/datasets/Zzitang/IndustReal),
  revision `c408f6effaa96512bd4eb5036c871bb7601ddc3e`, predating publisher v2.
  Its 2,505,914,072-byte ZIP contains 44 MP4s and macOS metadata, **no labels**.
  The mirror has no license card and is not byte-verified against publisher files.
- Author-supplied `PSR/procedure_info.json` describes 33 operations over 11 part
  states. It defines procedures; it is not observed recording-level evidence.

## Reproducible capped downloader

Requires `ffprobe` and `ffmpeg` on PATH:

```powershell
python scripts/sample_industreal.py --output runs/industreal-ten-new-attempt
```

The script selects exactly ten smallest compressed MP4 members, using filename
as the tie-break. This is a **size-biased convenience sample**, not representative
or held-out. This selection bounds transfer while official split lists are
unavailable. No split is inferred from recording filenames.

It requests exact HTTP ranges and refuses full-archive responses before reading
their body. Limits: 8 MiB/request, 1 GiB aggregate successful range payloads,
200 MiB uncompressed/member, ten recordings. It retains ZIP CRC validation,
per-video SHA-256, media metadata and full decoding results on successful downloads.
It does not claim to verify the archive's published SHA-256 without the full archive.
Output directories must be new; partial attempts are preserved. Offline tests cover
range refusal, byte budgets, truncated responses and cursor handling. Full suite:
**249 passed, 4 skipped, 12 subtests passed**.

## Baseline gates after retrieval

1. Recover authoritative split membership and matching `AR_labels.csv`,
   `PSR_labels.csv`, `PSR_labels_with_errors.csv`, and `PSR_labels_raw.csv` for
   the selected recordings. Preserve version and original bytes/checksums.
2. Validate timestamps/frame mapping against the mirror videos. The authors use
   10 FPS; mirror FPS alone would not prove absence of trimming or dropped frames.
3. Report action intervals and labeled completion/error states separately.
   Time between step completions is not necessarily active step duration.
4. Preserve official train/validation/test assignments and participant grouping.
   Do not tune interventions on test labels and then claim held-out validation.
5. Feed only supported recorded quantities into existing evaluation infrastructure.
   Recording duration is not complete operator attendance; completed steps are not
   automatically accepted products. Wages, energy, material waste and intervention
   performance remain unknown or separately labeled assumptions/simulation.

The next smallest action is to recover the publisher's annotation archive/file
list from a reachable endpoint. The user's next step is not to collect hardware
measurements. If access remains unavailable, select another publicly accessible
annotated assembly dataset before spending on model inference.
