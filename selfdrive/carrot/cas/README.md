# Carrot Adaptive Steering (CAS)

CAS는 기존 lateral 컨트롤러 위에 학습된 잔차 조향 보정을 더하는 carrot 전용 시스템입니다.
기기에는 JSON 가중치만 올리고 numpy 추론으로 동작하며, 학습은 PC에서 진행합니다.

**안전 불변**: CAS 토글이 꺼졌거나, 차종/EPS 매칭 모델이 없거나, α가 0이면 lateral 컨트롤러 출력은 base와 완전히 동일합니다.

---

## 1. 핵심 파일 위치

| 영역 | 경로 |
|---|---|
| 기기 추론 코드 | `selfdrive/carrot/cas/{model.py, runtime.py, features.py, metadata.py}` |
| 가중치 (배포본) | `selfdrive/carrot/cas/weights/<CAR>_<kind>.json` (`kind=torque/angle`, 구형 `<CAR>.json`도 로드 가능) |
| PC 학습 도구 | `tools/cas/{train.py, validate.py, promote.py, gui.py, export_json.py, make_dummy.py, triage.py}` |
| 컨트롤러 통합 | `selfdrive/controls/lib/latcontrol_torque.py`, `latcontrol_angle.py` |
| HUD / 토글 | `selfdrive/ui/carrot.cc` (drawCASDebug), `selfdrive/ui/qt/offroad/settings.cc` |
| 설계 문서 | `docs/cas_design.md` |
| 개발 로드맵 | `docs/cas_roadmap.md` |
| 대화/결정 기록 | `docs/cas_conversation.md` |
| 핸드오프 (날짜별) | `docs/cas_handoff_YYYYMMDD.md` |

---

## 2. 사용자(운전자) 입장 — 토글만

| 토글 | 위치 | 동작 |
|---|---|---|
| `CAS` | 시작 메뉴 | CAS 잔차 보정 사용 (재부팅 권장) |
| `CASDebug` | 시작 메뉴 (CAS 아래) | 화면 우측 정중앙에 CAS 디버그 위젯 표시 |

매칭된 모델이 있으면 차종명 옆에 `,CAS 6h`처럼 현재 적용 모델의 학습 시간이 함께 표기됩니다. HUD 위젯에도 학습 시간/centering score/개입 카운트가 한국어로 표시됩니다.

---

## 3. 개발자(학습/배포) 환경 — PC

### 3.1 OS

| OS | 권장 |
|---|---|
| Linux (Ubuntu 22.04+) | 메인 환경 |
| Windows + WSL2 Ubuntu | OK (rlog 경로는 `/mnt/d/...`) |
| Windows native | OK (GUI 추천, WSL 토글 OFF) |

### 3.2 설치

PC 한 줄 설치 (PyPI에서 일반 deps + PyTorch index에서 CUDA torch):

```powershell
# Windows native (이 PC 예시)
python -m pip install -r tools\cas\requirements.txt
python -m pip install --index-url https://download.pytorch.org/whl/cu128 torch
```

```bash
# Linux / WSL2
python3 -m pip install -r tools/cas/requirements.txt
python3 -m pip install --index-url https://download.pytorch.org/whl/cu128 torch
# CPU only면 두 번째 줄을 그냥 `pip install torch`
```

설치 검증:
```powershell
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

### 3.3 rlog 형식

`rlog`, `rlog.bz2`, `rlog.zst`, `raw_log.bz2`, `*--rlog.zst`, `*--rlog.bz2` 모두 지원. comma connect URL도 가능.

---

## 4. 학습 흐름

### 4.1 GUI (권장, Windows)

```powershell
python tools\cas\gui.py
```

- **Openpilot dir**: 자동 감지 (gui.py 위치 기반). 변경 거의 없음.
- **RLOG dir**: Browse로 rlog 폴더 선택 (예: `D:\rlog`). 마지막 선택은 `~/.cas_train/gui_config.json`에 자동 저장.
- **Car**: 학습할 차종 (예: `HYUNDAI_CASPER_EV`). carParams에서 자동 감지도 가능.
- **WSL 체크**: WSL 사용 시만 ON. native Python이면 OFF.
- **Backend / Device**: `auto`로 두면 GPU 자동.
- **Alpha**: 0.5 권장 (보수는 0.1~0.3, 적극은 0.5+).
- **One Click**: Train + Validate + Promote dry-run 자동.

GUI는 실행 시 RLOG 폴더를 인덱싱해서 `car + kind` 단위로 묶고, 각 그룹에 총 로그 시간/최근 로컬 학습 시간/신규 시간을 표시합니다.
학습+검증이 성공하면 `.cas/train_runs.json`에 로컬 PC 기준 학습 이력이 남습니다. 서버 원본 로그는 건드리지 않습니다.

학습 완료 시 한국어 요약 팝업이 평가(✅ / ⚠️ / ❌)와 다음 단계 안내를 보여줍니다.

### 4.2 CLI

```bash
python tools/cas/train.py \
  --rlogs /mnt/d/rlog \
  --car HYUNDAI_CASPER_EV \
  --kind torque \
  --backend torch --device cuda \
  --workers 4 \
  --alpha-max 0.5 \
  --output /mnt/d/rlog/HYUNDAI_CASPER_EV_torque_candidate.json
```

검증:
```bash
python tools/cas/validate.py \
  --model /mnt/d/rlog/HYUNDAI_CASPER_EV_torque_candidate.json \
  --rlogs /mnt/d/rlog \
  --workers 4 \
  --output /mnt/d/rlog/HYUNDAI_CASPER_EV_torque_validate.json
```

Promote (weights 폴더에 실제 적용):
```bash
python tools/cas/promote.py \
  --candidate /mnt/d/rlog/HYUNDAI_CASPER_EV_torque_candidate.json \
  --car HYUNDAI_CASPER_EV \
  --kind torque \
  --max-alpha 0.5 \
  --force
```

### 4.3 빠른 파이프라인 확인 (Dummy)

```bash
python tools/cas/make_dummy.py \
  --car HYUNDAI_IONIQ_5 \
  --output selfdrive/carrot/cas/weights/HYUNDAI_IONIQ_5.json \
  --alpha-max 0.0
```

α_max 0 더미는 PID-only 동작 (CAS 영향 0) 보장. 컨트롤러/HUD/매칭 로직만 검증.

---

## 5. 데이터 양 가이드

| 목적 | rlog 분량 | 권장 α_max |
|---|---:|---|
| 파이프라인 점검 | 10 분 | 0.0 (dummy) |
| 첫 candidate | 2–5 시간 | 0.1 |
| Phase 1 검증 | 20–40 시간 | 0.3–0.5 |
| 릴리즈 후보 | 50 시간+ | 0.5+ |

자세한 누적별 효과는 [`docs/cas_design.md` §11.2](docs/cas_design.md) 참조.

---

## 6. 매칭 확인 (배포 후)

기기에서 CAS가 모델을 잘 매칭했는지 확인:

```bash
# 1) params 직접 조회
cd /data/openpilot
python -c "
from openpilot.common.params import Params
p = Params()
print('CAS enabled:', p.get_int('CAS'))
print('Model name :', p.get('CASModelName'))
print('Model hours:', p.get('CASModelHours'))
"

# 2) runtime의 [CAS] 매칭 로그
journalctl -u comma -f | grep '\[CAS\]'
# → [CAS] matched HYUNDAI_CASPER_EV kind=torque eps=215ef677b75f ... score=...

# 3) 화면 우측 CAS 위젯 (CASDebug 토글 ON 시)
#   모델명 + "학습 5.98시간" 표시되면 매칭 성공
```

EPS firmware 해시는 학습된 모델의 JSON 메타와 차량 carParams.carFw의 ecu="eps" 항목으로 계산된 SHA1 12자가 일치해야 매칭됩니다.

---

## 7. 문서 맵

- 설계 원칙 / 안전 불변 / 학습 신호 / 메타 포맷 → [docs/cas_design.md](docs/cas_design.md)
- Phase 0~5 체크리스트 / 검증 기준 / 위험 → [docs/cas_roadmap.md](docs/cas_roadmap.md)
- 결정/대화 이력 (왜 이렇게 했나) → [docs/cas_conversation.md](docs/cas_conversation.md)
- 가장 최근 핸드오프 (운영 상태/실차 가이드) → `docs/cas_handoff_YYYYMMDD.md` 중 가장 최신

처음 보는 사람은 이 README → `docs/cas_design.md` 1~4절 → `docs/cas_roadmap.md` Phase 0/1 순서가 빠릅니다.
