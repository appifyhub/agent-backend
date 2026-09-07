FROM python:3.12.12-slim

# Install system dependencies and pipenv
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi8 libssl3 ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir pipenv

# Set up working directory
WORKDIR /app

# Copy the contents over (respecting .dockerignore)
COPY . .
RUN mv .github/ISSUE_TEMPLATE src/templates && rm -rf .github

# Install the dependencies
RUN pipenv install --deploy --ignore-pipfile --verbose \
    && find /usr/local/lib/python3.12 -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local/lib/python3.12 -type f -name "*.pyc" -delete \
    && rm -rf /root/.cache/pip /root/.cache/pipenv

ENV OTEL_SDK_DISABLED=true \
    OTEL_TRACES_EXPORTER=otlp \
    OTEL_METRICS_EXPORTER=otlp \
    OTEL_LOGS_EXPORTER=none \
    OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
    OTEL_EXPORTER_OTLP_TIMEOUT=5000 \
    OTEL_BSP_MAX_QUEUE_SIZE=512 \
    OTEL_BSP_MAX_EXPORT_BATCH_SIZE=128 \
    OTEL_BSP_SCHEDULE_DELAY=5000 \
    OTEL_METRIC_EXPORT_INTERVAL=60000 \
    OTEL_METRIC_EXPORT_TIMEOUT=5000 \
    OTEL_TRACES_SAMPLER=parentbased_always_on \
    OTEL_PYTHON_LOG_CORRELATION=true

# Set the entrypoint command
CMD ["pipenv", "run", "python", "tools/run_instrumented.py"]
