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
