# HA4M · ten assembly previews

**Ten 12-frame slideshows, not ten complete or original-speed videos.** Each MP4
shows twelve uniformly sampled RGB images at one image per second. Its playback
duration must not be used to measure action or process time.

| Participant's first trial | Preview | Labeled frames |
| --- | --- | ---: |
| IDU001V001 | [Watch/download MP4](IDU001V001/sparse-preview.mp4) | 2,427 |
| IDU002V001 | [Watch/download MP4](IDU002V001/sparse-preview.mp4) | 3,802 |
| IDU003V001 | [Watch/download MP4](IDU003V001/sparse-preview.mp4) | 4,659 |
| IDU004V001 | [Watch/download MP4](IDU004V001/sparse-preview.mp4) | 3,095 |
| IDU005V001 | [Watch/download MP4](IDU005V001/sparse-preview.mp4) | 4,813 |
| IDU006V001 | [Watch/download MP4](IDU006V001/sparse-preview.mp4) | 6,126 |
| IDU007V001 | [Watch/download MP4](IDU007V001/sparse-preview.mp4) | 3,013 |
| IDU008V001 | [Watch/download MP4](IDU008V001/sparse-preview.mp4) | 4,887 |
| IDU009V001 | [Watch/download MP4](IDU009V001/sparse-preview.mp4) | 4,138 |
| IDU010V001 | [Watch/download MP4](IDU010V001/sparse-preview.mp4) | 5,418 |

GitHub may offer download rather than inline playback; use the raw/download link.
The package is approximately 7.1 MB, including the ten MP4s, unchanged complete
`Labels.txt` files and derived full RGB frame-ID/device-timestamp indexes.
The approximately 403 MB of original sampled PNGs remain outside Git.

## Attribution and license

**HA4M: Human Action Multi-Modal Monitoring in Manufacturing** by Grazia Cicirelli,
Roberto Marani, Laura Romeo, Manuel García Domínguez, Jónathan Heras, Anna G. Perri
and Tiziana D'Orazio.

- Paper: [Scientific Data 9, 745 (2022)](https://doi.org/10.1038/s41597-022-01843-z).
- Dataset: [DOI 10.57760/sciencedb.01872](https://doi.org/10.57760/sciencedb.01872).
- [Publisher project and license](https://baltig.cnr.it/ISP/ha4m).
- [Official CNR download source](https://cloud.cnr.it/owncloud/index.php/s/j5BZvG1sXPzh6x1).
- **[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)**; the publisher's
  license text is included as [LICENSE-CC-BY-4.0.txt](LICENSE-CC-BY-4.0.txt).

The third-party dataset and derived previews retain CC BY 4.0 terms, separate
from the repository's software license. No author endorsement is implied.
The source is provided as-is without warranties; see the license disclaimer.

**Changes:** uniformly sampled source images were resized to width 1024 and encoded
as H.264 MP4 slideshows. Labels are unchanged. `rgb-index.json` files convert source
directory listings into `[frame_id, device_timestamp_us]` arrays. `baseline.json`
and per-recording summaries are derived annotation/timing summaries.

## Evidence and reproduction

- `manifest.json`: packaged paths, attribution, original sampled-frame IDs,
  timestamps, source hashes and timing summaries.
- `source-manifest.json`: original downloader receipt, retained verbatim. It also
  references PNGs and XML listings **not included in this compact package**.
- `checksums.json`: exact bytes/SHA-256 of packaged files, excluding itself.
- `baseline.json`: full annotation coverage, not accepted-output or quality proof.

This is the first trial of each of the first ten participant IDs: a convenience
sample, not a representative or official held-out benchmark. Labels do not supply
product acceptance/defect ground truth. Recorded spans exclude unrecorded setup
and cleanup; accepted outputs/hour, full-process hands-on labor, first-pass yield
and cost per accepted output remain unknown. Preview animations are not evidence
of a proposed machine's performance or process improvement.

To retrieve the original sparse PNGs and XML listings into a **new local folder**:

```sh
python scripts/sample_ha4m.py --output runs/ha4m-ten-local
```

See [the sample and recorded-baseline guide](../../docs/ha4m-small-sample.md).
