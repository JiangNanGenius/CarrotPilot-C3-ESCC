# Carrot Adaptive Steering (CAS) — 개발 로드맵

> 실행 계획서. 설계 윤곽은 [cas_design.md](cas_design.md), 상세 논의/참고문헌은 [cnlt_design.md](cnlt_design.md),
> 학습 환경 준비는 [cas_training_setup.md](cas_training_setup.md).
> 단계별 목표·산출물·체크리스트·검증 기준·위험을 한 문서에 정리.

---

## 0. 운영 모델 (재확인)

- **개발자**: jominki354 (혼자, 또는 협조자 N명)
- **사용자**: ON/OFF 토글만, 설정 0, 학습 0
- **PC OS**: Linux (Ubuntu 22.04+) 또는 Windows WSL2 권장
- **언어**: Python 3.11+, PyTorch (CPU), numpy
- **저장 포맷**: JSON
- **모든 코드**: `selfdrive/carrot/cas/` + `tools/cas/` (§20 in cas_design.md)

---

## 1. Phase별 한눈에

| Phase | 한 줄 목표 | 상태 | 진입 조건 |
|---|---|---|---|
| **Phase 0** | 인프라 골격, 빈 모델로 파이프라인 끝까지 동작 | ⏳ | — |
| **Phase 1** | 토크 차량 1대(jominki354 차) 실증, NNFF 대비 측정 | ⏳ | Phase 0 완료 |
| **Phase 2** | 토크 2~5종 확장, PPL/멀티태스크 등 정교화 | ⏳ | Phase 1에서 mean_offset ≤ 0.25m |
| **Phase 3** | 앵글 차량 진입 (Tesla/Ford 등) | ⏳ | Phase 2 토크 안정 |
| **Phase 4** | Mini-TCN/앙상블/Active Learning, 1000h+ 누적 | ⏳ | Phase 2~3 데이터 충분 |
| **Phase 5+** | 차종 10+ 확장, 커뮤니티 풀링, 입력 신호 추가 | ⏳ | 사용자 기반 형성 |

각 Phase는 결과 OK일 때만 다음으로. 안 되면 그 Phase 안에서 반복.

---

## Phase 0 — 인프라 골격

### 0.1 목표
**빈 모델(랜덤 가중치)로 파이프라인이 기기→PC→기기 끝까지 동작 확인**. 학습 품질은 아직 검증 안 함.

### 0.2 산출물
- `selfdrive/carrot/cas/` 디렉토리 + 모든 모듈
- `tools/cas/` 디렉토리 + 학습 스크립트 골격
- cereal 메시지 추가 (`lateralLearningInfo`, `casLog`)
- params 키 등록
- UI 토글, 차종명 표기
- `latcontrol_torque.py` / `latcontrol_angle.py` 패치
- 더미 `cas_HYUNDAI_IONIQ_5.json` (랜덤 가중치)

### 0.3 체크리스트

#### 0.3.1 디렉토리 / 파일 골격
- [ ] `selfdrive/carrot/cas/__init__.py`
- [ ] `selfdrive/carrot/cas/model.py` — `CASModel` 클래스 (NNFF `FluxModel` 확장)
- [ ] `selfdrive/carrot/cas/runtime.py` — `CASRuntime` 클래스 (JSON 로드, 차종 매칭, α 게이트)
- [ ] `selfdrive/carrot/cas/features.py` — 입력 벡터 빌더 (PC와 기기 공유)
- [ ] `selfdrive/carrot/cas/weights/.gitkeep`
- [ ] `selfdrive/carrot/cas/README.md`
- [ ] `tools/cas/__init__.py`
- [ ] `tools/cas/train.py` — 단일 진입점 (argparse)
- [ ] `tools/cas/triage.py` — T1~T5 자동 분류
- [ ] `tools/cas/validate.py` — 검증 지표
- [ ] `tools/cas/export_json.py` — torch → JSON
- [ ] `tools/cas/README.md`

#### 0.3.2 cereal / params
- [ ] `cereal/log.capnp`에 `lateralLearningInfo` 메시지 추가
  - `lateralLearningFlag` (uint8: 0=제외, 1=T1, 2=T2, ...)
  - `lateralOffset` (float, 차선 중앙 오프셋)
  - `latActive` (bool, 명시적 기록)
- [ ] `cereal/log.capnp`의 `LateralTorqueState`에 `casLog` 필드 (디버깅용 입력+출력)
- [ ] `common/params_keys.h`에 `CAS`, `CASModelName` 추가
- [ ] services.h 등 publish/subscribe 설정

#### 0.3.3 UI / 표기
- [ ] `selfdrive/ui/qt/offroad/settings.cc`에 CAS 토글 (NNFF 옆)
- [ ] `selfdrive/ui/carrot.cc` 차량명 표기 (`,CAS`)
- [ ] 토글 한국어/영어 라벨

#### 0.3.4 컨트롤러 패치
- [ ] `selfdrive/controls/lib/latcontrol_torque.py` — `CASRuntime` import, NNFF 분기 뒤 α·δ 합산 (§23.1)
- [ ] `selfdrive/controls/lib/latcontrol_angle.py` — `CASRuntime` import, α·δ 합산
- [ ] 두 컨트롤러에 casLog 작성

#### 0.3.5 features.py 핵심 로직 (§23 노하우 다 반영)
- [ ] vEgo, aEgo, desired_lat_accel × 5(미래), measured_lat_accel
- [ ] steeringAngle, steeringRate
- [ ] roll × 3 (현재+미래), pitch (또는 합성 옵션)
- [ ] lat_jerk_lookahead (`get_lookahead_value` 부호 일치 검증 §23.4)
- [ ] sign(desired_curvature)
- [ ] lateral_offset_now, lateral_offset_avg_5s
- [ ] adjusted_future_times (aEgo 보정 §23.5)
- [ ] lateralDelay 동적 반영 (§23.7)
- [ ] use_steering_angle 옵션 (§23.8)

#### 0.3.6 데이터 수집 — 사용자 측 마커 (간소화)
- [ ] `selfdrive/carrot/lateral_data_marker.py` (~100줄)
  - 매 프레임 T1~T5 자동 분류
  - cereal `lateralLearningInfo`에 기록
- [ ] carrot 메인 루프에서 호출

#### 0.3.7 PC 학습 스크립트 골격
- [ ] `tools/cas/train.py` argparse: `--rlogs`, `--car`, `--output`
- [ ] `LogReader`로 rlog 읽기
- [ ] features.py로 입력 벡터 (기기와 공유)
- [ ] triage.py로 T1~T5 라벨
- [ ] PyTorch MLP (20→32→16→1) 학습
- [ ] export_json.py로 JSON 출력
- [ ] validate.py로 지표 출력

#### 0.3.8 더미 JSON 생성 + 끝-끝 테스트
- [ ] 랜덤 가중치 JSON 생성 (`tools/cas/make_dummy.py`)
- [ ] 기기 실행 → 더미 JSON 로드 → 추론 동작 확인
- [ ] α 게이트로 출력 0 보장 (안전)
- [ ] cas/README.md 작성

### 0.4 검증 기준 (Phase 0 완료 조건)
- [ ] 더미 가중치로 기기 부팅, 충돌 없음
- [ ] UI에서 CAS 토글 보이고 동작
- [ ] 차량명에 `,CAS` 매칭 표시 (HYUNDAI_IONIQ_5만 더미 등록)
- [ ] α=0 강제 시 출력 토크 변화 0 (회귀 없음)
- [ ] cas_train.py가 더미 rlog 1개로 끝까지 돌고 JSON 출력
- [ ] casLog cereal로 입력/출력 확인 가능

### 0.5 위험 / 의존성
- cereal 메시지 추가는 빌드 영향. process_replay 테스트 필수.
- params 키 충돌 없는지 확인.
- 컨트롤러 패치는 회귀 위험 가장 큼 → α=0 폴백 철저히.

### 0.6 산출 LOC 추정
| 영역 | LOC |
|---|---|
| `selfdrive/carrot/cas/` | ~400 |
| `tools/cas/` | ~600 |
| 기존 파일 패치 | ~30 |
| cereal | ~20 |
| **합계** | **~1050** |

---

## Phase 1 — 토크 차량 1대 실증 (jominki354 차)

### 1.1 목표
**실제 학습된 모델이 base/NNFF 대비 측정 가능한 개선을 내는지 확인.**

### 1.2 산출물
- `cas_HYUNDAI_IONIQ_5.json` (or 사용자 차종) — 실 학습
- 검증 리포트 (base vs NNFF vs CAS)
- `~/.cas_train/<car>/history.json` 첫 엔트리

### 1.3 체크리스트

#### 1.3.1 데이터 수집
- [ ] jominki354 차에서 rlog 20~40h 수집 (다양한 조건)
- [ ] NNFF on/off 일관성 유지 (수집 메타 기록)
- [ ] rlog를 `~/.cas_train/<car>/rlogs/`에 보관

#### 1.3.2 트리아지 검증
- [ ] T1~T5 분포 확인 (T3 비율 1~5% 권장)
- [ ] 카메라 오류 / 비활성 구간 제외 확인
- [ ] 분포 시각화 (vEgo, curvature 히스토그램)

#### 1.3.3 학습 실행
- [ ] `python tools/cas/train.py --car <car>` 실행
- [ ] CPU 5~30분 학습 완료 확인
- [ ] 학습 곡선 확인 (overfit 아닌지)
- [ ] friction_override 자동 감지 동작 확인 (§23.2)
- [ ] use_steering_angle 메타 기록 확인 (§23.8)

#### 1.3.4 검증 지표
- [ ] mean_lateral_offset, std, max 출력
- [ ] base / NNFF / CAS 비교 표
- [ ] 사용자 개입 빈도 비교
- [ ] history.json 자동 생성

#### 1.3.5 기기 배포 & 도로 테스트
- [ ] JSON을 `selfdrive/carrot/cas/weights/`에 복사 + 깃 commit
- [ ] 기기에서 CAS ON으로 도로 주행
- [ ] 주관 평가: 쏠림 개선, 코너 개선 등
- [ ] 새 rlog 수집 후 validation 재측정

### 1.4 검증 기준 (Phase 2 진입 조건)
- [ ] mean_lateral_offset ≤ **0.25m** (베이스라인 ~0.40m, NNFF ~0.30m 대비)
- [ ] 사용자 개입 빈도 base 대비 **-30% 이상**
- [ ] 주관 평가: NNFF보다 같거나 나음
- [ ] α=0 강제 시 base와 동일 동작 (회귀 0)

### 1.5 위험 / 의존성
- 학습 데이터 분포 부족 (직선만 많고 코너 적음) → 의도적 다양한 주행 필요
- T3 신호 부족 → PPL preference horizon으로 보완 (Phase 2)
- 차종 EPS 응답 특이 → NNFF가 못 잡은 부분 우선 잡혀야 정당화

### 1.6 실패 시 대응
- mean_offset 개선 < 0.05m → 입력 신호 부족 의심, §4.1 입력 확장
- 진동/이상 거동 → α_max 낮춤, base 비중 ↑
- 회귀 발생 → 즉시 깃 롤백, history.json 이전 버전으로

---

## Phase 2 — 토크 확장 + 정교화

### 2.1 목표
**차종 2~5종 지원 + NNFF 노하우 + 2026 최신 기법 본격 적용**.

### 2.2 산출물
- `cas_<car_2>.json`, `cas_<car_3>.json` ... 추가
- PPL, 멀티태스크 보조 loss 등 §18 항목 반영된 학습 스크립트
- 데이터 분포 자동 리포트

### 2.3 체크리스트

#### 2.3.1 차종 확장
- [ ] 협조자 또는 다른 차종 rlog 확보 (TOYOTA, HYUNDAI 변형 등)
- [ ] 차종별 EPS firmware 해시 매핑 정착
- [ ] 매칭 안 되는 차량은 자동 fallback 동작 확인

#### 2.3.1a Phase 1 점검에서 발견된 자동 추출 미구현 항목 (2026-05-20)

Phase 1 첫 학습 후 JSON 메타 점검 결과, 다음 3개가 자동 채워지지 않음. Phase 2에서 train.py에 자동 추출 로직 추가:

- [x] **`eps_firmware_hash` 자동 추출**: rlog의 `carParams.carFw` 중 `ecu == "eps"`인 항목들의 `fwVersion` → SHA1 짧은 해시. 차종 변형 매칭에 필수 (§24).
- [ ] **`lateral_delay_at_train` 평균 추적**: 현재 `_latest_lateral_delay`로 한 번만 보고 학습 전체에 못 씀. Sample 클래스에 `lateral_delay` 필드 추가하거나 source별 평균 집계.
- [ ] **`friction_override` 자동 감지**: 학습 끝난 모델에 `evaluate([10.0, 0.0, 0.2, ...])` 호출해서 출력이 작으면 (`<0.1`) True 설정 (§23.2). 현재 항상 False.

지금은 안 막혀 있는 이유: 메타가 비어 있어도 런타임은 기본값으로 정상 동작. 다만 차종 변형 매칭 정확도(`CarName`/`CarSelected3` + `eps_firmware_hash`)와 friction 보완 동작 검증을 위해 Phase 2 안에 처리.

#### 2.3.2 학습 정교화 (§18 / §23 반영)
- [ ] **PPL preference horizon L** 자동 튜닝 (§18.1, L=50~100 그리드서치)
- [ ] **멀티태스크 보조 loss**: 미래 offset 예측 헤드 추가 (§21.3 #5)
- [ ] **하드 네거티브 마이닝**: T2/T3 over-sampling
- [ ] **error_blend_factor 옵션** 도입 검토 (§23.3)
- [ ] **friction_override** 다차종에서 동작 검증

#### 2.3.3 데이터 분포 자동 통계
- [ ] vEgo × curvature 2D 히스토그램 (§16.3)
- [ ] 부족 영역 자동 경고
- [ ] history.json에 분포 통계 누적

#### 2.3.4 검증 자동화
- [ ] base/NNFF/CAS 비교 자동 출력
- [ ] 이전 버전 대비 개선/악화 비교
- [ ] 악화 시 자동 경고 (깃 푸시 보류)

### 2.4 검증 기준 (Phase 3 진입 조건)
- [ ] 최소 3종 차량에서 mean_offset ≤ 0.22m
- [ ] 다양한 도로 분포 확보 (vEgo 30~110 km/h 커버, 곡률 분포 양호)
- [ ] history.json 운영 정착 (버전 누적 기록)

---

## Phase 3 — 앵글 차량 진입

### 3.1 목표
**Tesla/Ford 등 앵글 차량 지원 — NNFF가 닿지 못한 영역.**

### 3.2 산출물
- `cas_TESLA_MODEL_3.json` (or 다른 앵글 차량)
- `latcontrol_angle.py` 패치 정착

### 3.3 체크리스트
- [ ] 앵글 차량 rlog 수집 (협조자 필요할 가능성)
- [ ] features.py가 앵글 차량 데이터에서도 정상 동작 확인
- [ ] 토크/앵글 차종 자동 감지 (`CP.steerControlType`)
- [ ] 학습 타겟 정의 — 앵글은 단순 모방이 아니라 EPS 응답 학습 (§5.1 B안 검토)
- [ ] `latcontrol_angle.py`에 α·δ 합산
- [ ] 도로 테스트 + 검증 지표

### 3.4 검증 기준 (Phase 4 진입 조건)
- [ ] 1종 이상 앵글 차량에서 base 대비 mean_offset 개선
- [ ] 앵글 차량 특유의 응답 지연/데드존 학습으로 보완 확인

### 3.5 위험
- 앵글 차량은 차량 내부 EPS 컨트롤러 영향 큼 → CAS의 영향이 작을 수 있음
- 학습 신호 정의가 토크와 다름 → 별도 실험 필요

---

## Phase 4 — 고도화 / 고점 추구

### 4.1 목표
**§21 고점 성능 추구 — mean_offset ~0.13m 목표.**

### 4.2 산출물
- Mini-TCN 백본 옵션 (`cas/model.py`에 conv1d 지원)
- 앙상블 학습 (3~5 seed)
- Active Learning 파이프라인

### 4.3 체크리스트

#### 4.3.1 모델 용량 단계 상승 (§21.3 #1)
- [ ] Mini-TCN 구현 (numpy 30줄, JSON 호환)
- [ ] FluxModel 포맷 확장 (conv1d 레이어 타입)
- [ ] MLP vs Mini-TCN A/B 비교

#### 4.3.2 입력 신호 확장 (§21.3 #2)
- [ ] `laneLines.prob`, `position.std` 추가 검토
- [ ] 차선 폭, 도로 유형 추정
- [ ] 입력 차원 ~20 → ~30

#### 4.3.3 앙상블 (§21.3 #6)
- [ ] 같은 데이터 다른 seed로 3~5개 학습
- [ ] 추론 시 평균 (1ms × 5 = 5ms, OK)
- [ ] JSON에 ensemble 메타 지원

#### 4.3.4 Active Learning (§21.3 #8)
- [ ] 모델 불확실성 측정 (dropout / 앙상블 분산)
- [ ] 불확실 구간 우선 수집 알림
- [ ] 차종별 부족 영역 자동 식별

#### 4.3.5 데이터 다양성 캠페인 (§21.3 #3)
- [ ] 비/야간/터널/굴곡 등 의도적 수집 캠페인
- [ ] 협조자 모집 — 다른 지역/도로 환경
- [ ] 1000h+ 누적

### 4.4 검증 기준
- [ ] 주력 차종에서 mean_offset ≤ 0.13m
- [ ] 사용자 개입 -60% 이상

---

## Phase 5+ — 정착 / 확장

### 5.1 목표
**carrot의 표준 기능으로 정착. 차종 10+.**

### 5.2 가능한 작업
- [ ] 차종 리스트 10+ 확장
- [ ] 커뮤니티 .json 풀 (사용자 자발 제공)
- [ ] 차량 개체 적응 모드 (사용자 fine-tune 옵션, 기존 결정 뒤집을지는 그때)
- [ ] 추가 입력: 와이퍼/조도/시간대
- [ ] 다른 fork(sunnypilot, FrogPilot)와의 호환성 검토

---

## 진행 추적 — 라이브 보드

매 Phase 진입 시 이 표 갱신:

| Phase | 시작일 | 완료일 | 산출물 깃 commit | 검증 통과? | 메모 |
|---|---|---|---|---|---|
| 0 | — | — | — | — | — |
| 1 | — | — | — | — | — |
| 2 | — | — | — | — | — |
| 3 | — | — | — | — | — |
| 4 | — | — | — | — | — |
| 5+ | — | — | — | — | — |

---

## 부록 A — 절대 깨지면 안 되는 불변 조건

| # | 불변 | 검증 방법 |
|---|---|---|
| I1 | α=0이면 base와 완전 동일 출력 | 회귀 테스트 |
| I2 | 기기에 학습 코드 0줄 | 코드 리뷰 |
| I3 | NNFF on/off와 CAS on/off 독립 | UI 토글 별개 확인 |
| I4 | 가중치 없는 차량은 CAS 자동 비활성 | matching 실패 시 α=0 |
| I5 | JSON 포맷이 Phase 진행에도 호환 | format_version 명시 |
| I6 | PID error는 base 그대로 (§23.1) | 코드 리뷰 |

이 조건 깨면 즉시 롤백.

---

## 부록 B — 다음 액션 (지금 당장 시작 가능한 것)

1. `selfdrive/carrot/cas/` 디렉토리 생성
2. `model.py`에 `CASModel` 클래스 첫 줄 (`FluxModel` 복사 + 확장)
3. cereal/log.capnp에 `lateralLearningInfo` 메시지 prototype
4. `tools/cas/train.py` argparse 골격

Phase 0의 가장 가벼운 시작점.

---

_설계 윤곽: [cas_design.md](cas_design.md) / 상세 논의: [cnlt_design.md](cnlt_design.md)_
