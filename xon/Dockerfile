# XON GPU-capable image. CPU hosts work too (torch falls back to CPU).
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends git rsync && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/xon
COPY . .
RUN pip install --no-cache-dir -r scripts/requirements.txt && pip install --no-cache-dir -e . \
    && python -m playwright install --with-deps chromium
EXPOSE 8787
# mount a volume at /opt/xon/data, /opt/xon/checkpoints, /opt/xon/exchange to keep state across runs
CMD ["bash", "-lc", "xon doctor; xon init --budget ${XON_BUDGET:-8h} && xon start --all --port 8787"]
