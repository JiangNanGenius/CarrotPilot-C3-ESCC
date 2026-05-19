# CAS Training Setup

## Environment

| Item | Value |
|---|---|
| OS | Ubuntu 22.04+ / WSL2 Ubuntu |
| Python | 3.11+ |
| Working directory | openpilot repository root |
| Requirements | `tools/cas/requirements.txt` |

## Install

```bash
sudo apt update
sudo apt install python3-venv

python3 -m venv ~/.cas_train/venv
source ~/.cas_train/venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r tools/cas/requirements.txt
```

Optional GPU backend:

```bash
python -m pip install -r tools/cas/requirements-gpu.txt
```

## rlog Input

Supported:

- `rlog`
- `rlog.bz2`
- `rlog.zst`
- `raw_log.bz2`
- `*--rlog.zst`
- `*--rlog.bz2`

Windows path example:

```text
E:\rlogs
```

WSL path example:

```text
/mnt/e/rlogs
```

## Train

```bash
python tools/cas/train.py \
  --rlogs /mnt/e/rlogs \
  --car HYUNDAI_IONIQ_5 \
  --epochs 60 \
  --sample-stride 5 \
  --alpha-max 0.4 \
  --backend auto
```

For CUDA:

```bash
python tools/cas/train.py \
  --rlogs /mnt/e/rlogs \
  --car HYUNDAI_CASPER_EV \
  --backend torch \
  --device cuda
```

## Windows UI

```powershell
python tools\cas\gui.py
```

## Pipeline Check

```bash
python tools/cas/train.py \
  --rlogs /mnt/e/rlogs \
  --car HYUNDAI_IONIQ_5 \
  --epochs 3 \
  --sample-stride 20 \
  --alpha-max 0.1
```

## Dummy Model

```bash
python tools/cas/make_dummy.py \
  --car HYUNDAI_IONIQ_5 \
  --output selfdrive/carrot/cas/weights/HYUNDAI_IONIQ_5.json \
  --alpha-max 0.0
```

## Promote

```bash
python tools/cas/promote.py \
  --candidate /mnt/e/rlogs/HYUNDAI_IONIQ_5_phase1_test_t2.json \
  --car HYUNDAI_IONIQ_5 \
  --kind torque \
  --max-alpha 0.1 \
  --dry-run
```

## Data Amount

| Purpose | rlog |
|---|---:|
| Pipeline check | 10 min |
| First candidate | 2-5 h |
| Phase 1 validation | 20-40 h |
| Release candidate | 50 h+ |
