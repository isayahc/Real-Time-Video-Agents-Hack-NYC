FROM node:22-bookworm-slim AS node
FROM python:3.11-slim-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml LICENSE ./
COPY protocol_pipeline ./protocol_pipeline
RUN pip install --no-cache-dir '.[robot,simulation]'
COPY examples/so101-robot ./examples/so101-robot
COPY examples/so101-benchmark ./examples/so101-benchmark
COPY examples/so101-fixture ./examples/so101-fixture
COPY examples/so101-simulation ./examples/so101-simulation
COPY examples/so101-comparison ./examples/so101-comparison
COPY scripts/run_so101_job.py ./scripts/run_so101_job.py
RUN python -m protocol_pipeline.robot_contract \
    --lock examples/so101-robot/source-lock.json --source-root /opt/so101-source --fetch
RUN git init /opt/oi-runtime \
    && git -C /opt/oi-runtime remote add origin https://github.com/Mapped-Assembly/Open-Industries.git \
    && git -C /opt/oi-runtime fetch --depth 1 origin 9b34ec217563e2a6788d5e60d9cc74c0bcd21330 \
    && git -C /opt/oi-runtime checkout --detach FETCH_HEAD \
    && npm ci --ignore-scripts --prefix /opt/oi-runtime
ARG SOURCE_REVISION=unrecorded
ENV SOURCE_REVISION=$SOURCE_REVISION PYTHONUNBUFFERED=1
LABEL org.opencontainers.image.revision=$SOURCE_REVISION
CMD ["python", "scripts/run_so101_job.py"]
