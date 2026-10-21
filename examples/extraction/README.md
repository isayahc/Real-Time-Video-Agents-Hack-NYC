# Automatic protocol extraction with Nebius

The extraction command connects a model provider directly to the reusable protocol compiler. It accepts procedure text or an existing sampled-frame ingestion run.

## Nebius text extraction

Configure `NEBIUS_API_KEY` or `NEBIUS_TOKEN_FACTORY_KEY` in your environment, and use the preset NVIDIA compiler (or explicitly override it with an available model):

```bash
python -m protocol_pipeline extract-protocol \
  --text /path/to/procedure.txt \
  --provider nebius \
  --output runs/text-extraction-001
```

The provider uses Nebius Token Factory's OpenAI-compatible chat-completions endpoint. The direct Nebius CLI presets `nvidia/Nemotron-3_5-Lightning` for compilation and `MiniMaxAI/MiniMax-M3` for vision. Explicit model flags and nonblank environment overrides remain supported. OpenCode/replay still require an explicit model ID; text compilation does not impose a vendor-specific prefix. Model access and structured response reliability must be tested against your account. There is no automatic fallback to replay when credits or credentials are missing.

API reference: https://api.tokenfactory.nebius.com/docs

Text is numbered by line. Model operations cite inclusive spans such as `text:L3-L5`; the validator rejects spans outside the supplied text. Quantities explicitly stated in a procedure can be preserved as cited operation constraints, while numeric resource/engineering values remain unknown until supplied separately.

## Nebius sampled-video extraction

First use the existing local ingestion command with an authorized video and matching annotation file. Then:

```bash
python -m protocol_pipeline extract-protocol \
  --run runs/t1-ingested \
  --provider nebius --vision-model YOUR_VISION_MODEL_ID \
  --model YOUR_TEXT_MODEL_ID --output runs/video-extraction-001
```

Stage one infers an observation graph from verified timestamped frames. Stage two extracts a reusable protocol from that graph. Observed operation references use `action:<ID>` and resolve through action citations to the supplied frame IDs. Source procedure annotations/ground truth are excluded from both requests. The new command does not send optional annotation object hints.

The compiler receives an explicit list of allowed action citations. A live candidate with an invalid citation receives at most one additional compiler request containing the validation error and original evidence; this can incur additional provider usage. Both unvalidated candidates are retained as `provider-candidate-1.json` / `provider-candidate-2.json`. The vision stage is not repeated for this correction. A second invalid candidate fails without compiling; replay never triggers live correction requests.

No action evidence means no completed protocol is emitted. Sparse frame sampling can miss actions, contacts and ordering. Preparation not visible in the clip must be labeled `workflow_hypothesis` with a `hypothesis:<explanation>` reference. Equipment is proposed, not verified. Every inferred relationship remains `model_inference`.

## Outputs and limitations

- Preserved source text, or copied sampled frames with a source manifest.
- Video observation graph, when applicable.
- `extracted-protocol.json`: validated candidate input to the reusable compiler.
- `compiled/`: process graph, typed apparatus requirements, resource input template, report and summary.
- `extraction-summary.json`: provider identity, requested/served model metadata, usage, latency and source provenance; no authentication credentials.
- `extraction-failure.json`: stage failure marker when a result cannot be validated; no completed compiled plan is claimed.

All outputs use a new directory. The stage never overwrites a previous extraction. Structural checks reject invalid references, fabricated numeric accounting/engineering values, invented time ranges and claims of reviewed/verified operations. They do not establish that the model correctly interprets the source, that proposed equipment works, or that physical performance/acceptance is verified. Human source review and evaluation against a reference remain necessary.

## Offline provider replay

```bash
python -m protocol_pipeline extract-protocol \
  --text examples/extraction/procedure.txt \
  --provider replay --model offline-fixture \
  --replay examples/extraction/recorded-response.json \
  --output runs/extraction-replay-001
```

The bundled recorded response is hand-authored for integration tests, not a real Nebius response or demonstrated automatic extraction quality. Replay makes no inference calls and is always labeled `live_inference: false`. The [executed replay](executed/compiled/report.md) shows the downstream report.

## OpenCode provider

OpenCode can own the model request and structured-output retries through its local server. Start OpenCode from the repository root with the Nebius provider configured:

```powershell
opencode serve
```

Then use the pipeline with `--provider opencode`:

```powershell
python -m protocol_pipeline extract-protocol `
  --text examples/extraction/procedure.txt `
  --provider opencode --model Qwen/Qwen3-235B-A22B-Instruct-2507 `
  --output runs/opencode-extraction-001
```

The provider connects to `http://127.0.0.1:4096` by default, sends the `ProtocolSpecification` JSON schema, and requests structured-output retries. Set `OPENCODE_URL`, `OPENCODE_PROVIDER`, or `OPENCODE_RETRY_COUNT` to override the defaults. This integration currently supports text extraction; sampled-video extraction remains on the direct Nebius provider.

Tests exercise the real Nebius request adapter with mocked HTTP responses for text and two-stage video, including real synthetic-video frame decoding, source-grounding failures, malformed/truncated completions, missing credentials, no secret persistence and preserved failure evidence. CI includes replay as its eighth connection-blocked offline workflow.

## Verified live text smoke test

On 2026-10-19, direct Nebius text extraction using `Qwen/Qwen3-235B-A22B-Instruct-2507` successfully processed the bundled seven-line procedure, validated source references, and compiled seven operations into process/apparatus/resource artifacts. The request completed in approximately 22 seconds using 4,596 tokens. Local evidence is in `runs/e2e-live-text-20261019-02/`, including `extraction-summary.json` and `compiled/report.md` (runtime outputs are Git-ignored).

With credentials in the shell environment, reproduce with a new output directory:

```powershell
python -m protocol_pipeline extract-protocol `
  --text examples/extraction/procedure.txt `
  --provider nebius --model Qwen/Qwen3-235B-A22B-Instruct-2507 `
  --output runs/live-text-smoke-001
```

This verifies the live text integration, not extraction accuracy or physical performance. Live sampled-video extraction and live scene generation remain unverified. The OpenCode SDK smoke attempts did not return usable structured output; the default Nemotron Lightning direct request also returned an incomplete completion.

The Qwen default is verified only through direct Nebius in the historical smoke test. It does not establish OpenCode compatibility. The CLI provider now retries local cross-field validation up to three attempts in the same session, independently of structured-output retries. Missing output and provider errors fail explicitly.

## NVIDIA preset verification

Run `python -m scripts.verify_nebius --output runs/nebius-verification-001` with a configured key. This checks the account catalog, a minimal complete JSON response, and real extraction through the compiler. It fails on missing credentials or unsuccessful inference; it never substitutes replay or Qwen. See [settings, provenance and current verification limits](../../docs/nebius-model-presets.md). The historical Qwen smoke above remains unchanged evidence.
