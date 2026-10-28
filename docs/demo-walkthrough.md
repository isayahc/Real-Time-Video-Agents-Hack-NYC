# Saved live-workflow demonstration (v000008)

## Open the verified package

1. Start the workbench with `python -m protocol_pipeline.web` and open
   `http://127.0.0.1:8000`.
2. Select **Import snapshot · populate this workbench** above the stage navigation.
3. Upload `runs/demo-v000008-package/snapshot.zip`, or supply the local directory
   `snapshots/e2e/v000008`.
4. Review the imported saved run. Importing does not run models or archived CAD code.

The local ZIP is **8,539,803 bytes**, contains the original manifest and its 192
indexed files, and has an adjacent `snapshot.zip.sha256`. SHA-256:
`fe50a10ceac25ac6e8ab265ace587c6c89b47fcf21b1c366164d44e314b1b827`.
The actual ZIP importer was exercised offline: restored 191 workbench files under
`runs/demo-v000008-package/import-check/`. Package verification is recorded beside
the ZIP. This checks importability; it is not a browser walkthrough verification.
The package remains local and has not been published.

## Three-minute walkthrough

| Time | Show | Say |
| --- | --- | --- |
| 0:00–0:30 | Source clip and sampled frames | “This is a recorded BridgeData robot manipulation task. We interpret sampled frames, not continuous tracking.” |
| 0:30–1:00 | Observations and procedure | “Live vision and reasoning turn those observations into a structured procedure with retained evidence.” |
| 1:00–1:30 | Design proposal and resource/economics view | “The system proposes equipment and records planning assumptions. These costs and performance estimates are not measured savings.” |
| 1:30–2:15 | Native machine CAD and saved visual review | “The run generated native CAD and applied one visual correction. The final critique still says needs improvement; mechanism visibility remains incomplete.” |
| 2:15–2:45 | Scene/lab and saved views | “The generated asset reaches a rendered lab layout. This is visualization, not simulated or physically verified machine operation.” |
| 2:45–3:00 | Outcome summary | “All seven stages completed in one live run, with 192 artifact checksums verified. Product quality and resource-efficiency gains remain to be demonstrated.” |

Use saved results; generation/correction controls start new paid work and are not
part of this walkthrough. If a view is uninformative, acknowledge the retained
critique rather than presenting it as successful visual validation.

## Keep the two evidence tracks distinct

- **BridgeData:** completed live workflow integration demonstration.
- **HA4M:** separate ten-trial recorded duration baseline and joining-guide
  hypothesis. No tested fixture outcome, accepted-product comparison or savings.

Do not present the BridgeData machine as a solution validated against HA4M timings.

## Credit and evidence

Source: **BridgeData V2 — Homer Walke et al., CoRL 2023; BridgeData contributors.
CC BY 4.0.** [Project](https://rail-berkeley.github.io/bridgedata/) ·
[License](https://creativecommons.org/licenses/by/4.0/).
The project assembled publisher frames into a clip and derived observations,
procedures, proposals and CAD; these are our derivatives, not author endorsement.

- [Completed live-run evidence and limitations](e2e-v000008-outcome.md)
- [Source acquisition and attribution](bridgedata-small-sample.md)
- [Separate HA4M baseline](ha4m-small-sample.md)

Next decision: review the saved demo for presentation suitability. No additional
fixture engineering or live inference is needed to inspect this package.
