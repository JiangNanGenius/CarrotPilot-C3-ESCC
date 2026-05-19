# CAS vA Handoff - 2026-05-20

이 문서는 `jominki354/cas_vA` 브랜치에서 CAS(Carrot Adaptive Steering)를 이어서 작업할 AI/개발자를 위한 인수인계 기록이다.

## 현재 결론

- Phase 0 인프라 구현은 실제 학습/검증/Promote까지 연결되는 수준으로 완료됐다.
- Phase 1은 `HYUNDAI_CASPER_EV` 대상 첫 오프디바이스 학습과 검증, Promote까지 완료됐다.
- 실차 도로 테스트는 아직 수행하지 않았다.
- 현재 모델은 `alpha_max=0.1`로 보수 적용한다.

## 차량명 기준

사용자 UI 표시명은 `Hyundai Casper EV 2024`다.

CAS 학습/모델명은 다음 값을 사용했다.

```text
HYUNDAI_CASPER_EV
```

CAS 런타임은 이름을 정규화해서 매칭한다.

```text
HYUNDAI_CASPER_EV      -> HYUNDAICASPEREV
Hyundai Casper EV 2024 -> HYUNDAICASPEREV2024
```

따라서 현재 모델 파일 `HYUNDAI_CASPER_EV.json`은 `Hyundai Casper EV 2024` 계열에 매칭된다.

## 현재 산출물

실제 적용 위치에 Promote된 파일:

```text
selfdrive/carrot/cas/weights/HYUNDAI_CASPER_EV.json
```

PC 학습 산출물:

```text
E:\rlogs\HYUNDAI_CASPER_EV_candidate.json
E:\rlogs\HYUNDAI_CASPER_EV_validate.json
```

이번 실행 raw 로그:

```text
E:\rlogs\cas_runs\20260520_003400_HYUNDAI_CASPER_EV\
```

주의: 이 실행은 full audit 기능을 붙이기 전에 시작된 실행이라 콘솔 raw 로그 중심이다. full audit은 다음 GUI 실행부터 적용된다.

## 학습 결과

GUI One Click 실행 결과:

```text
sources: 934
collected samples: 544,703
usable samples: 285,843
trained_on_hours: 5.9822439169025
backend: cuda
model_type: cas_torque
alpha_max: 0.1
target RMSE: 0.1008
applied_delta p95_abs: 0.0088
gate pass rate: 0.438
```

Triage 분포:

```text
T1_GOOD: 238,147
T2_OFFSET: 28,592
T3_STRONG_INTERVENTION: 19,104
```

의미:

- 데이터 양은 첫 Phase 1 후보로 충분하다.
- T2 offset 신호와 T3 운전자 개입 신호가 모두 들어갔다.
- `alpha_max=0.1`이라 실차 첫 적용은 약하게 제한된다.
- 아직 실차 테스트로 안전성/체감 개선을 확인하지 않았다.

## Promote 상태

Dry-run 결과:

```text
output: E:\Carrot\openpilot\selfdrive\carrot\cas\weights\HYUNDAI_CASPER_EV.json
dry-run: no files written
```

실제 Promote 결과:

```text
candidate: E:\rlogs\HYUNDAI_CASPER_EV_candidate.json
car: HYUNDAI_CASPER_EV
model_type: cas_torque
trained_on_hours: 5.9822439169025
alpha_max: 0.1
output: E:\Carrot\openpilot\selfdrive\carrot\cas\weights\HYUNDAI_CASPER_EV.json
promoted
exit code: 0
```

Promote는 학습이 아니라 candidate JSON을 검증 후 weights 폴더로 복사하는 작업이다. 1초 내로 끝나는 것이 정상이다.

## 사용자가 원하는 운영 UX

사용자는 복잡한 CLI보다 Windows GUI에서 원클릭으로 처리하기를 원한다.

현재 GUI:

```powershell
python tools\cas\gui.py
```

기본 화면:

- `RLOG dir`
- `Car`
- `One Click: Train + Validate`
- `Detect GPU`
- 상태/로그

Advanced:

- `Kind`
- `Candidate`
- `Validate JSON`
- `Epochs`
- `Stride`
- `Min age`
- `Max sources`
- `Workers`
- `Alpha`
- `Backend`
- `Device`
- `WSL`
- 수동 `Train Candidate`, `Validate`, `Promote Dry Run`, `Promote`

## GPU/WSL 상태

사용자 PC:

```text
GPU: NVIDIA GeForce RTX 4080 SUPER
WSL: Ubuntu, WSL2
Python: 3.12.3 in WSL
PyTorch: 2.11.0+cu128
CUDA available: True
```

설치한 명령:

```bash
python3 -m pip install --user --break-system-packages torch --index-url https://download.pytorch.org/whl/cu128
```

`tools/cas/requirements-gpu.txt`에도 CUDA wheel index를 기록했다.

## 속도/병목

현재 병목은 대부분 GPU 학습이 아니라 rlog 파싱/압축해제/샘플 수집이다.

구간별 성격:

```text
rlog 읽기/샘플수집: CPU + 디스크 병목
MLP 학습: GPU 사용
검증: CPU + 디스크 병목
full audit 저장: 디스크 쓰기 병목
```

이를 위해 `--workers` 병렬 파싱 옵션을 추가했다.

```bash
python tools/cas/train.py --workers 4 ...
python tools/cas/validate.py --workers 4 ...
```

GUI Advanced 기본값도 `Workers=4`다. SSD/WSL 환경에서는 4부터 시작하고, 너무 디스크 사용이 심하면 낮춘다.

## Raw/Audit 로그 요구사항

사용자의 "raw 로그" 의미는 단순 콘솔 로그가 아니라 가능한 모든 추적 가능한 행동기록이다.

다음 GUI 실행부터 `RLOG dir/cas_runs/<timestamp>_<car>/` 아래에 기록된다.

```text
run_metadata.json
1_3_train_candidate.log
2_3_validate.log
3_3_promote_dry_run.log

train_audit/source_inventory.json
train_audit/source_events.jsonl
train_audit/samples.jsonl
train_audit/train_args.json
train_audit/train_validation.json

validate_audit/source_inventory.json
validate_audit/source_events.jsonl
validate_audit/samples.jsonl
validate_audit/validate_args.json
validate_audit/validate_summary.json
```

포함 정보:

- 어떤 rlog 파일을 읽었는지
- 파일 크기/수정시간
- rlog별 시작/종료/오류
- rlog별 message type 카운트
- rlog별 triage 카운트
- 샘플별 triage
- 샘플별 offset
- 운전자 토크
- feature vector
- 학습 옵션/backend/device
- validate 결과

## 중요한 구현 파일

런타임:

```text
selfdrive/carrot/cas/model.py
selfdrive/carrot/cas/features.py
selfdrive/carrot/cas/runtime.py
selfdrive/carrot/cas/weights/HYUNDAI_CASPER_EV.json
selfdrive/carrot/lateral_data_marker.py
```

컨트롤 통합:

```text
selfdrive/controls/lib/latcontrol_torque.py
selfdrive/controls/lib/latcontrol_angle.py
selfdrive/controls/controlsd.py
cereal/log.capnp
cereal/services.py
common/params_keys.h
selfdrive/carrot_settings.json
```

학습 도구:

```text
tools/cas/train.py
tools/cas/validate.py
tools/cas/export_json.py
tools/cas/triage.py
tools/cas/make_dummy.py
tools/cas/promote.py
tools/cas/gui.py
tools/cas/requirements.txt
tools/cas/requirements-gpu.txt
tools/cas/README.md
```

문서:

```text
selfdrive/carrot/cas/docs/cas_design.md
selfdrive/carrot/cas/docs/cnlt_design.md
selfdrive/carrot/cas/docs/cas_roadmap.md
selfdrive/carrot/cas/docs/cas_training_setup.md
selfdrive/carrot/cas/docs/cas_handoff_20260520.md
```

## T2 offset 이슈와 해결

초기에는 `modelV2.position.y[0]` 또는 `lateralPlan.position.y[0]` 기준이라 대부분 0에 가까웠다.

확인 결과 lane line center 기반 offset에는 실제 값이 있었다.

조치:

- `selfdrive/carrot/cas/features.py`에 `lane_center_offset()` 반영
- `selfdrive/carrot/lateral_data_marker.py`에서 lane line center offset 사용
- `tools/cas/train.py`도 같은 기준 사용
- lane line probability와 lane width 유효성 조건 후 fallback 사용

현재 학습 결과에 `T2_OFFSET=28,592`가 잡힌다.

## Phase 진행상황

### Phase 0

상태: 완료에 가까움.

완료된 것:

- CAS 런타임 골격
- features/model/runtime
- cereal 로그 필드
- params
- UI 설정 메뉴 CAS 토글
- latcontrol torque/angle 통합
- off-device train/validate/promote
- Windows GUI
- CUDA backend
- 병렬 rlog 파싱 옵션
- raw/audit 기록

남은 확인:

- 기기 빌드/부팅에서 schema 회귀 없음 확인
- 실제 `casLog`가 원하는 주기로 기록되는지 확인
- `CASModelName` 표시 확인

### Phase 1

상태: 오프디바이스 학습/검증/Promote 완료, 실차 검증 대기.

완료된 것:

- `HYUNDAI_CASPER_EV` rlog 5.98h 학습
- CUDA 학습
- validate 통과
- `HYUNDAI_CASPER_EV.json` Promote 완료

남은 것:

- 기기 배포
- CAS ON 상태에서 저위험 실차 테스트
- 새 rlog 수집
- 실차 후 validate 재측정
- 필요 시 alpha 0.15/0.2 후보 별도 생성

### Phase 2

상태: 시작 전.

진입 조건:

- Phase 1 실차에서 이상 개입 없음
- 평균 offset/개입 빈도 개선 또는 최소한 회귀 없음 확인
- 새로운 실차 rlog 확보

## 실차 테스트 지침

현재 모델은 첫 적용 후보이므로 목적은 "강한 개선 체감"이 아니라 "나쁜 개입이 없는지 확인"이다.

권장:

- `alpha_max=0.1` 유지
- CAS ON/OFF를 쉽게 확인
- 저속/한산한 도로에서 시작
- 조향 이상감, 진동, 한쪽 쏠림, 코너 과보정 여부 확인
- 테스트 후 rlog를 다시 `E:\rlogs`에 추가

금지/주의:

- 첫 주행부터 alpha를 0.2 이상으로 올리지 말 것
- 실차 검증 전 모델 구조/feature spec을 임의 변경하지 말 것
- Promote된 weights 파일을 삭제하거나 이름 변경하지 말 것

## 다시 학습할 의미가 있는 경우

같은 rlog/같은 설정으로 다시 돌리는 것은 의미가 거의 없다.

다시 학습할 조건:

- 새 rlog 추가
- full audit 기록이 필요한 경우
- `Workers` 병렬 파싱 적용 성능을 재확인하는 경우
- `alpha_max=0.15` 또는 `0.2` 후보를 별도로 만들 경우
- 실차 테스트 후 문제 구간 rlog를 추가한 경우
- epochs/stride/feature/triage 정책을 바꿔 비교할 경우

## 다음 AI가 바로 할 일

1. 이 문서와 `cas_roadmap.md`, `cas_design.md`, `cnlt_design.md`를 읽는다.
2. 현재 브랜치가 `jominki354/cas_vA`인지 확인한다.
3. `git status --short`로 사용자의 변경사항을 먼저 확인한다.
4. Promote된 weights 파일이 존재하는지 확인한다.
5. 실차 테스트 전이면 코드 변경보다 배포/관측 체크리스트를 우선한다.
6. 실차 테스트 후 rlog가 추가되면 `tools/cas/gui.py`에서 Workers=4, audit 활성 기본 흐름으로 재학습/검증한다.

## 확인 명령

weights 확인:

```powershell
Get-Item selfdrive\carrot\cas\weights\HYUNDAI_CASPER_EV.json
```

모델 내용 확인:

```powershell
@'
import json
from pathlib import Path
p = Path(r"selfdrive/carrot/cas/weights/HYUNDAI_CASPER_EV.json")
data = json.loads(p.read_text(encoding="utf-8"))
print(data["car"])
print(data["model_type"])
print(data["trained_on_hours"])
print(data["alpha_max"])
'@ | python -
```

GUI 실행:

```powershell
python tools\cas\gui.py
```

WSL CUDA 확인:

```powershell
wsl bash -lc "python3 - <<'PY'
import torch
print(torch.__version__)
print(torch.cuda.is_available())
print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')
PY"
```

## 현재 판단

현 상태에서 같은 조건으로 재학습은 필요 없다. 다음 단계는 Promote된 모델을 기기에 포함하고, CAS ON 상태에서 `alpha_max=0.1`로 실차 안전 확인을 진행하는 것이다.
