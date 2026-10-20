# Debug extraction

This is the smallest example for stepping through a live Nebius extraction in VS Code.

1. Open `examples/debug-extraction/run.py`.
2. Set a breakpoint in `run.py` or `protocol_pipeline/pipeline.py`.
3. Press `F5` or choose **Run Python File**.

The process uses `NEBIUS_API_KEY` or `NEBIUS_TOKEN_FACTORY_KEY` from the current environment. Each run writes to a new timestamped directory under `runs/`, so failed attempts are preserved and reruns do not collide.

From the repository root, the equivalent command is:

```powershell
python examples/debug-extraction/run.py
```

To let OpenCode handle the request and retries automatically, run this one Python script:

```powershell
python -m pip install -r examples/debug-extraction/requirements.txt
python examples/debug-extraction/run-opencode.py
```

Uses the native `opencode-ai` Python SDK. Requires the OpenCode CLI on PATH with Nebius connected via `/connect`. Starts a local server if needed, requests structured output, validates through the existing extraction pipeline, and compiles into a new timestamped directory.

Progress and the session ID are printed for inspection. Local schema validation errors are sent back for correction (up to three attempts). SDK HTTP retries and OpenCode structured-output retries are separate from these local validation attempts.

Optional environment variables: `OPENCODE_URL`, `OPENCODE_PROVIDER`, and `OPENCODE_MODEL`. Uses your existing OpenCode credentials; the example does not read `.env`.
