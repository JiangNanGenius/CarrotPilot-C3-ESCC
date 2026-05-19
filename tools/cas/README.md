# CAS Training Tools

## Python

- Python 3.11+
- Ubuntu 22.04+ or WSL2 Ubuntu recommended

## Install

```bash
python3 -m venv ~/.cas_train/venv
source ~/.cas_train/venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r tools/cas/requirements.txt
```

If `venv` is missing:

```bash
sudo apt update
sudo apt install python3-venv
```

## Train

```bash
python tools/cas/train.py \
  --rlogs /mnt/e/rlogs \
  --car HYUNDAI_IONIQ_5
```

GPU acceleration is optional through PyTorch:

```bash
python3 -m pip install --user --break-system-packages -r tools/cas/requirements-gpu.txt

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

Use `One Click: Train + Validate` for the normal flow. It trains a candidate,
validates it, then runs promote dry-run only. Real `Promote` is separate.
Only `RLOG dir`, `Car`, and the one-click button are needed for normal use.
Extra paths and training knobs are hidden under `Advanced`.
Each run writes raw logs under `RLOG dir/cas_runs/<timestamp>_<car>/`.
Set `Workers` under `Advanced` to parallelize rlog parsing. `4` is a safe default
for WSL on a desktop SSD; lower it if disk usage feels too heavy.

Raw/audit files:

- `run_metadata.json`: command, options, backend/device, input/output paths
- `1_3_train_candidate.log`: train stdout/stderr
- `2_3_validate.log`: validate stdout/stderr
- `3_3_promote_dry_run.log`: promote dry-run stdout/stderr
- `train_audit/source_inventory.json`: rlog file size/time inventory
- `train_audit/source_events.jsonl`: per-rlog start/end/error, message counts, triage counts
- `train_audit/samples.jsonl`: collected sample trace with triage, offset, torque, feature vector
- `validate_audit/source_inventory.json`: validation rlog inventory
- `validate_audit/source_events.jsonl`: validation per-rlog trace
- `validate_audit/samples.jsonl`: validation sample trace
- `validate_summary.json`: validation summary copied from the output JSON

## Validate

```bash
python tools/cas/validate.py \
  --model /mnt/e/rlogs/HYUNDAI_IONIQ_5_phase1_test_t2.json \
  --rlogs /mnt/e/rlogs \
  --min-file-age-sec 120 \
  --max-sources 200 \
  --output /mnt/e/rlogs/HYUNDAI_IONIQ_5_phase1_validate.json
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

```bash
python tools/cas/promote.py \
  --candidate /mnt/e/rlogs/HYUNDAI_IONIQ_5_phase1_test_t2.json \
  --car HYUNDAI_IONIQ_5 \
  --kind torque \
  --max-alpha 0.1 \
  --force
```

## Dummy Model

```bash
python tools/cas/make_dummy.py \
  --car HYUNDAI_IONIQ_5 \
  --output selfdrive/carrot/cas/weights/HYUNDAI_IONIQ_5.json \
  --alpha-max 0.0
```
