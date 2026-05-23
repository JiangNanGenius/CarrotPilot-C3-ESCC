# selfdrive/carrot/cas/ — 구조 문서

```
selfdrive/carrot/cas/
├── __init__.py                # 빈 패키지 마커
├── README.md                  # 운영/학습 진입점 (한국어)
├── STRUCTURE.md               # 본 문서 — 구조 전용 인덱스
│
├── model.py                   # numpy MLP 추론기 (CASModel)
├── runtime.py                 # 차량 매칭 + α 게이트 + casLog 생성 (CASRuntime)
├── features.py                # 20차원 입력 벡터 빌더 (PC/기기 공유)
├── metadata.py                # EPS firmware SHA1-12 해시 계산
│
├── upload_config.py           # 업로드 엔드포인트/HMAC secret 해석
├── uploader_state.py          # 업로드 진척/재시도 영구 상태 (JSON)
├── data_uploader.py           # firehose 업로드 데몬 (managed process)
│
├── weights/
│   ├── .gitkeep
│   ├── HYUNDAI_CASPER_EV.json # 실제 학습본 (5.98h, α_max=0.5, format_v2; 구형 파일명)
│   └── HYUNDAI_IONIQ_5.json   # 더미 (α_max=0, format_v1)
│
└── docs/
    ├── cas_design.md          # 설계 윤곽
    ├── cas_roadmap.md         # Phase 0~5+ 체크리스트
    ├── cas_conversation.md    # 결정/패러다임 전환 이력
    ├── cas_dataset_sync_plan.md # 업로드/학습 연동 단계별 작업계획
    ├── cas_server_phase6.md   # LXC 서버 API 배포/검증 메모
    ├── cas_handoff_20260520.md# 최근 운영 상태 핸드오프
    └── cas_data_upload_design.md # 업로더 + NAS 서버 설계
```

---

## 모듈 책임 (런타임)

| 파일 | 클래스/함수 | 책임 |
|---|---|---|
| `__init__.py` | — | 패키지 마커 |
| `model.py` | `CASModel`, `SUPPORTED_FORMAT_VERSION=2` | JSON 가중치 로드, `evaluate(x) → (clipped_delta, max_abs_z)` |
| `features.py` | `CASFeatureState`, `build_feature_vector`, `FEATURE_SCHEMA="cas_v2_timed_20d"`, `FEATURE_SPEC[20]` | 20차원 입력 벡터 생성, lane line center 우선 offset |
| `metadata.py` | `eps_firmware_hash`, `FORMAT_VERSION=2` | carFw 중 EPS ECU → SHA1 앞 12자 |
| `runtime.py` | `CASRuntime(CP, kind)` | weights/ 스캔·차량/EPS 매칭, α 곱셈 게이트, 39d casLog |

## 모듈 책임 (업로더)

| 파일 | 진입점/상수 | 책임 |
|---|---|---|
| `upload_config.py` | `DEFAULT_ENDPOINT`, `DEFAULT_SECRET`, `resolve_endpoint`, `resolve_secret` | 엔드포인트/HMAC secret 해석 (`/data/carrot_upload_secret`, param override) |
| `uploader_state.py` | `STATE_PATH=/data/cas_upload_state.json`, `MAX_ATTEMPTS=5`, `load/save/mark_uploaded/record_failure/should_retry` | 업로드 진척·재시도 영구 상태 (atomic write) |
| `data_uploader.py` | `run`, `main`, `ROUTE_SEG_RE`, `UPLOAD_FILES=("rlog.zst","qlog.zst")` | managed process(`cas_uploader`), 세그먼트 스캔·HMAC POST·route_meta.json 전송 |

---

## 데이터 흐름

```
[기기]
  carState, modelV2, controlsState, lateralPlan
        │
        ▼
  features.build_feature_vector  →  20d 벡터
        │
        ▼
  CASModel.evaluate              →  (δ, |z|_max)
        │
        ▼
  CASRuntime._alpha              →  α (곱셈 게이트)
        │
        ▼
  latcontrol_torque/angle.py     →  ff += α·δ   (pid.error는 무변)
        │
        ▼
  casLog (39 float) → pid_log.casLog → cereal → UI HUD
```

```
[업로더] (CarrotDataUpload=1)
  /data/media/0/realdata/<route>--<seg>/{rlog.zst,qlog.zst}
        │
        ▼
  data_uploader.run (게이트: NTP/WiFi/offroad)
        │
        ▼
  HTTPS POST + HMAC(X-Carrot-TS, X-Carrot-Sig)
        │
        ▼
  https://casroute.jominki354.live  (Cloudflare Tunnel → NAS LXC)
        │
        ▼
  route당 1회 route_meta.json 별도 POST
```

---

## 외부 통합 지점

| 외부 파일 | 통합 내용 |
|---|---|
| `selfdrive/controls/lib/latcontrol_torque.py:90,291-312` | `CASRuntime(CP,"torque")` 생성·`ff += cas_alpha*cas_delta`·`pid_log.casLog=cas_log` |
| `selfdrive/controls/lib/latcontrol_angle.py` | 동일 패턴 (angle 컨트롤러용) |
| `system/manager/process_config.py:147` | `PythonProcess("cas_uploader", "selfdrive.carrot.cas.data_uploader", always_run, enabled=not PC)` |
| `selfdrive/ui/cas_debug.{h,cc}` | **CAS HUD 전용 파일** (carrot.cc에서 분리). 삭제하면 HUD만 제거됨 |
| `selfdrive/ui/carrot.cc:3031, 3094` | `#include cas_debug.h` + `ui_draw_cas_overlay(s)` 호출 (2줄) |
| `selfdrive/ui/carrot.cc` | 차량명에 `,CAS 6h` 접미 (`CASModelName`/`CASModelHours` 직접 읽음) |
| `selfdrive/ui/qt/offroad/settings.cc` | `CAS`, `CASDebug` 토글 |
| `cereal/log.capnp` | `LateralTorqueState.casLog` 필드 |
| `common/params_keys.h` | `CAS`, `CASDebug`, `CASModelName`, `CASModelHours`, `CASAlphaOverride`, `CarrotDataUpload`, `CarrotUploadWifiOnly`, `CarrotUploadOnlyOffroad`, `CarrotUploadEndpoint`, `CarrotDeviceId` |

---

## 가중치 JSON 스키마 (format_version 2)

| 필드 | 타입 | 비고 |
|---|---|---|
| `format_version` | int | 2 (model.py가 하드 가드) |
| `model_type` | str | `cas_torque` 또는 `cas_angle` |
| `kind` | str | `torque` 또는 `angle` |
| `car` / `car_names[]` | str / list | 정규화 매칭 대상 |
| `eps_firmware_hash` | str | SHA1 앞 12자, 매칭 보너스용 |
| `feature_schema` | str | 반드시 `cas_v2_timed_20d` |
| `feature_spec[]` | list[str] | 20개 (features.py FEATURE_SPEC) |
| `input_size` / `output_size` | int | 20 / 1 |
| `input_mean[]` / `input_std[]` | list[float] | 길이 input_size |
| `layers[]` | list | `{W_i, b_i, activation, type="linear"}` |
| `alpha_max` | float | 0.0 ~ 1.0 |
| `output_clip` | [low, high] | default `[-3.0, 3.0]` |
| `vego_min` / `vego_max` | float | 학습 데이터 5/95 percentile |
| `use_steering_angle` | bool | default true |
| `trained_on_hours` / `trained_at` / `trained_by` | meta | HUD/감사용 |
| `triage_counts` / `target_metrics` / `offset_metrics` / `msg_counts` | dict | 학습 audit 메타 |

신규 promote 기본 파일명은 `<CAR>_<kind>.json`이다. 예: `HYUNDAI_CASPER_EV_torque.json`.
기존 `<CAR>.json` 파일명도 runtime이 계속 로드하므로 구형 배포본과 호환된다.

---

## PC 학습 로컬 상태

`tools/cas/gui.py`는 선택한 RLOG 루트 아래 `.cas/`에 로컬 작업 상태를 저장한다.
이 상태는 학습 PC 전용이며 서버 원본 route 삭제/변경과 무관하다.

| 경로 | 용도 |
|---|---|
| `.cas/index.json` | rlog 인덱스. `car`, `kind`, EPS hash, duration 요약 |
| `.cas/local_manifest.json` | 서버 manifest와 같은 형태의 로컬 데이터셋 요약 |
| `.cas/train_runs.json` | 성공한 train+validate 이력. `car_key + kind`별 최근 학습 시간 계산 |
| `.cas/runs/<timestamp>_<car>_<kind>/` | 각 실행의 raw stdout/stderr, audit, validate summary |
| `.cas/source_lists/selected_rlogs*.txt` | Windows 명령줄 길이 제한 회피용 임시 rlog 목록 |
| `.cas/candidates/<CAR>_<kind>_candidate.json` | GUI 기본 candidate 출력 |
| `.cas/validations/<CAR>_<kind>_validate.json` | GUI 기본 validate summary 출력 |

GUI의 학습 대상 콤보는 `.cas/index.json`과 `.cas/train_runs.json`을 합쳐 총 로그 시간, 최근 로컬 학습 시간, 신규 시간을 표시한다.
`tools/cas/cloud_sync.py`는 아직 서버 통신을 하지 않고, 로컬 manifest 생성과 향후 cloud cache 경로 정책만 정의한다.
Phase 6 기준 서버 구현은 `tools/cas/server/carrot_upload_server.py`에 두고, LXC의 `/opt/carrot-upload/server.py`로 배포한다.

---

## Params 키 일람 (CAS 관련)

| 키 | 타입 | 용도 |
|---|---|---|
| `CAS` | bool | 메인 토글 |
| `CASDebug` | bool | HUD 위젯 표시 |
| `CASModelName` | str | 매칭된 모델 이름 (런타임이 기록) |
| `CASModelHours` | str | 현재 적용 모델 학습 시간 (차량명 `,CAS 6h` 및 HUD용) |
| `CASAlphaOverride` | int | 0=JSON default, 1~50=0.01~0.50 override |
| `CarrotDataUpload` | bool | 업로더 토글 |
| `CarrotUploadWifiOnly` | bool | WiFi 한정 게이트 |
| `CarrotUploadOnlyOffroad` | bool | offroad 한정 게이트 |
| `CarrotUploadEndpoint` | str | 엔드포인트 override |
| `CarrotDeviceId` | str | 캐시된 디바이스 ID (DongleId/HardwareSerial/UUID 중 첫 발견값) |

---

## 안전 불변 (I1)

다음 중 하나라도 성립하면 lateral 출력은 base와 완전히 동일:

1. `Params.get_bool("CAS") == False`
2. 차종/kind 매칭 모델 없음 (`runtime.model is None`)
3. α 곱셈 결과 0 (steeringPressed / NaN / `|δ|>3` / vEgo<vego_min 또는 ≥vego_max / `|z|≥3.5`)
4. `alpha_max == 0` (예: dummy JSON)

PID error는 어떤 경우에도 CAS가 건드리지 않음. 잔차는 오직 `ff += α·δ`로만 합성.

### α 게이트 임계값 (runtime.py:_alpha)

| 게이트 | full | taper | zero |
|---|---|---|---|
| 분포 `|z|` | `≤2.5` | `2.5~3.5` | `≥3.5` |
| 속도 하한 ramp | `vEgo ≥ vego_min+2` | `vego_min ~ +2` | `<vego_min` |
| 속도 상한 taper | `vEgo ≤ vego_max-5` | `vego_max-5 ~ vego_max` | `≥vego_max` |
| `steeringPressed` | — | — | true 즉시 |
| `|δ|>3` 또는 NaN | — | — | 즉시 |

---

## CAS 완전 제거 가이드

CAS를 폐기하려면 다음 순서로 정리. 모든 변경은 file/line 단위로 격리되어 있음.

1. **Python 런타임 측**
   - `selfdrive/carrot/cas/` 디렉토리 전체 삭제
   - `selfdrive/controls/lib/latcontrol_torque.py`: CASRuntime import + L90 init + L291-312 합성 부분 제거
   - `selfdrive/controls/lib/latcontrol_angle.py`: 동일
   - `system/manager/process_config.py:147`: `cas_uploader` 등록 1줄 제거

2. **UI 측 (HUD만 제거하고 런타임은 유지하고 싶을 때도 동일)**
   - `selfdrive/ui/cas_debug.{h,cc}` 삭제
   - `selfdrive/ui/SConscript`: `"cas_debug.cc"` 1줄 제거
   - `selfdrive/ui/carrot.cc:3031`: `#include cas_debug.h` 4줄(주석 포함) 제거
   - `selfdrive/ui/carrot.cc:3094`: `ui_draw_cas_overlay(s);` 호출 1줄 제거
   - `selfdrive/ui/carrot.cc`: `,CAS 6h` 차량명 접미 제거

3. **cereal 측 (옵션)**
   - `cereal/log.capnp`의 `LateralTorqueState.casLog` 필드 → 그대로 둬도 무해(없으면 빈 list)
   - `common/params_keys.h`의 `CAS*` 키들 → 사용 코드 사라지면 키만 남아 있어도 무해

→ UI만 제거 = **5분 작업**, 전체 제거 = **30분 작업**.

---

## 문서 인덱스

| 문서 | 줄수 | 역할 |
|---|---:|---|
| `README.md` | 186 | 진입점·운영 명령·데이터 양 표 |
| `STRUCTURE.md` | — | 본 문서 (구조 인덱스) |
| `docs/cas_design.md` | 1727 | 설계 윤곽 (P1~P10 원칙, 블록도, §6 트리아지 T1~T5, §23 NNFF 노하우) |
| `docs/cas_roadmap.md` | 375 | Phase 0~5+ 체크리스트·검증 기준·위험 |
| `docs/cas_handoff_20260520.md` | 502 | 가장 최근 운영 상태 핸드오프 |
| `docs/cas_conversation.md` | 208 | 의사결정/패러다임 전환 이력 |
| `docs/cas_data_upload_design.md` | 725 | 업로더 + NAS 서버 + Cloudflare Tunnel 설계 |
| `docs/cas_server_operations.md` | 434 | **서버 운영 종합 가이드** — 인프라/폴더구조/명명규칙/API/배포/마이그레이션/런북 |
