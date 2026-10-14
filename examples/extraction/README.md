# Automatic protocol extraction with Nebius

The extraction command connects a model provider directly to the reusable protocol compiler. It accepts procedure text or an existing sampled-frame ingestion run.

## Nebius text extraction

Configure `NEBIUS_API_KEY` or `NEBIUS_TOKEN_FACTORY_KEY` in your environment, and select a text model available to your account:

```bash
python -m protocol_pipeline extract-protocol \
  --text /path/to/procedure.txt \
  --provider nebius --model YOUR_TEXT_MODEL_ID \
  --output runs/text-extraction-001
```

The provider uses Nebius Token Factory's OpenAI-compatible chat-completions endpoint. Model IDs are explicit; text compilation does not impose a vendor-specific model prefix. Model access and structured response reliability must be tested against your account. There is no automatic fallback to replay when credits or credentials are missing.

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

Tests exercise the real Nebius request adapter with mocked HTTP responses for text and two-stage video, including real synthetic-video frame decoding, source-grounding failures, malformed/truncated completions, missing credentials, no secret persistence and preserved failure evidence. CI includes replay as its eighth connection-blocked offline workflow.

**Live Nebius inference has not been executed or verified here; credits and account model access remain pending.**
