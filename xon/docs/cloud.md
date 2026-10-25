# XON on a rented GPU box (Tier B / C)

Copy-paste steps. Tested logic is the same as Tier A; only `xon init` picks bigger sizes from the measured benchmark.

## 1. Rent a machine
Any provider with an NVIDIA GPU (>= 16 GB VRAM for Tier B; 2+ GPUs with >= 20 GB each for Tier C), Ubuntu 22.04+,
CUDA drivers installed (`nvidia-smi` works). 100 GB disk.

## 2. Install
```bash
scp xon.zip user@HOST:~ && ssh user@HOST
unzip xon.zip && cd xon
./scripts/setup.sh              # venv, CUDA torch (detected via nvidia-smi), deps, Chromium
source .venv/bin/activate
xon doctor                      # every line should be OK; follow the printed fixes otherwise
```
Or with Docker:
```bash
docker build -t xon . && docker run --gpus all -p 8787:8787 -v $PWD/state:/opt/xon/data xon
```

## 3. Size the run to your budget
```bash
xon init --budget 8h                      # wall-clock budget
xon init --budget '$40' --gpu-price 1.20  # dollar budget at $1.20/GPU-hour
```
`xon init` runs a 100-step benchmark, picks parameters and tokens together (about 20 tokens/parameter), prints the
estimated time, disk and cost, and refuses a run that cannot finish in budget.

## 4. Run
```bash
xon start --all --cycles 4          # crawler + trainer + agent supervisor + dashboard on :8787
ssh -L 8787:127.0.0.1:8787 user@HOST  # view the dashboard locally
```

## 5. Spot / preemptible instances
Training checkpoints every few minutes and on SIGTERM; just re-run `xon start --all` after a preemption and it resumes
from the last good checkpoint.

## 6. Split nodes across machines
On the crawler box: `xon start --node crawler`. On the GPU box: `xon start --node trainer`. Point both at the same
exchange in `xon.toml`:
```toml
[transport]
kind = "s3"            # or "rsync" / "folder"
url = "s3://my-bucket/xon"   # XON_S3_ENDPOINT=... for MinIO/R2/B2; pip install boto3
```

## 7. Stop
`xon stop` (or the dashboard STOP button) halts every node within seconds. Governor caps in `xon.toml [governor]`
(disk, bandwidth, requests/hour, GPU hours) are hard limits.

Related: [README.md](../README.md) (Tier A quick start), [REPORT.md](../REPORT.md) (what Tier A measured; Tier B/C untrained).
