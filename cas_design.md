# Carrot Adaptive Steering (CAS) — 설계 윤곽서

> carrot 포크용 학습 기반 조향 시스템의 구조/구현 원리 윤곽.
> 상세 논의·웹 조사·참고문헌은 [cnlt_design.md](cnlt_design.md) 참조.
> 이 문서는 "무엇을 만들 것인가"의 청사진.

---

## 0. 메인 목표 (사용자 확정 2026-05-19)

> **차선 중앙 유지 강화 / 쏠림 방지**가 최우선.
> 큰 코너·속도 변화·다양한 노면에서 차가 차선 중앙에서 미세하게 벗어나는 현상을 학습으로 보정한다.

이 목표가 §1 한 줄 요약·§4 출력 합성·§6 학습 신호 전부를 지배한다.
**NNFF처럼 "사람을 흉내내는 조향"이 아니라 "차선 중앙 오차를 줄이는 조향"이 학습의 본질.**

---

## 1. 한 줄 요약

**"속도·코너·노면이 어떻든 차를 차선 중앙에 머무르게"** 하는 carrot 전용 조향 학습 시스템.

- **토크/앵글 차량 둘 다 지원** (내부 코드 경로 분리)
- **NNFF의 단순함 계승**: JSON 가중치 + 순수 numpy 추론, 외부 의존성 0
- **물리 base + α·NN 잔차** 구조 → 학습 실패해도 차는 굴러감
- **데이터 자동 트리아지** (§6): rlog만 던지면 사용자 개입·쏠림·양호 구간 알아서 분류

---

## 2. 핵심 원칙

| # | 원칙 | 의미 |
|---|---|---|
| P1 | **기기 = 추론 + 로그 수집만** | 학습 코드 0줄, 그래디언트 0회. 안전성 확보. |
| P2 | **학습 = 사용자 PC** | rlog → PC → JSON. NNFF 워크플로우 그대로. |
| P3 | **추론 = 순수 numpy** | onnx/torch/tinygrad 의존성 0. NNFF `FluxModel` 패턴 확장. |
| P4 | **가중치 = JSON 파일** | 깃 푸시 or hot-swap. |
| P5 | **토크/앵글 내부 분리** | 둘 다 지원하되 모델·코드 경로 완전 분리. JSON도 따로. |
| P6 | **물리 base + α·NN δ** | base 컨트롤러는 그대로. NN은 잔차만. |
| P7 | **데이터 종류 무관** | 어떤 rlog든 자동 트리아지로 양질 학습 (§6). |
| P8 | **장기 누적 친화** | 데이터가 쌓일수록 개선 (§11). |
| P9 | **개발자가 학습·배포, 사용자는 켜기만** | NNFF처럼 jominki354가 차종별 .json 만들어 깃 푸시. 사용자는 ON/OFF 토글 하나. |
| P10 | **모델은 JSON 파일 하나** | NNFF와 같은 방식. 사람이 열어볼 수 있고, 깃에서 변경 추적됨 (§19.6). |

---

## 3. 시스템 블록 다이어그램

```
┌─────────────────────────────────────────────────────────────┐
│ [기기 측 — comma3X 등]                                       │
│                                                              │
│  carState ─┐                                                 │
│  modelV2 ──┤    ┌──────────────┐                             │
│  cState  ──┼──► │ feature      │                             │
│  liveCal ──┤    │ builder      │                             │
│  latPlan ──┘    └──────┬───────┘                             │
│                        │ x (벡터 ~20d)                       │
│                        ▼                                     │
│                 ┌──────────────┐                             │
│                 │ CASModel     │   (numpy MLP)               │
│                 │ (toq or ang) │ ◄── JSON 가중치             │
│                 └──────┬───────┘                             │
│                        │ δ                                   │
│   ┌────────────────────┴──────────────────┐                  │
│   ▼                                       ▼                  │
│ [토크 차량]                              [앵글 차량]          │
│ base_FF + α·δ → torque              VM_angle + α·δ → angle  │
│                                                              │
│  (병렬) Lateral Data Marker → 매 프레임 구간 유형 라벨        │
└──────────────────────────────────┬───────────────────────────┘
                                   │ rlog (개입/오프셋 마킹 포함)
                                   │ (USB or comma connect)
                                   ▼
┌─────────────────────────────────────────────────────────────┐
│ [사용자 PC]                                                  │
│                                                              │
│  $ python tools/cas_train.py --rlogs ... --car ...           │
│                                                              │
│  rlog 파싱 → 100Hz align                                     │
│      → 자동 트리아지 (5종 구간 유형 + 가중치)               │
│      → (X, y, w) 데이터셋                                    │
│      → PyTorch 학습 (CPU OK, 10~60분)                        │
│      → 검증 지표 출력 (mean|offset|, 사용자개입 빈도 등)    │
│      → cas_<car>_<eps>.json                                  │
└──────────────────────────────────┬───────────────────────────┘
                                   │ JSON 복사
                                   ▼
┌─────────────────────────────────────────────────────────────┐
│ [기기에 다시] params/d/CASWeights or torque_data/cas/        │
│  hot-swap or 재시작 → 적용                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 모델 구조

### 4.0 원칙: 토크/앵글 완전 분리

> 토크 차량용 JSON과 앵글 차량용 JSON은 **별도 파일·별도 로더**. 같은 모델로 묶지 않는다. 사용자는 자기 차에 맞는 것 하나만 받는다.

### 4.1 입력 벡터 x (≈ 20차원)

| 그룹 | 신호 | 차원 |
|---|---|---|
| 속도/가속 | vEgo, aEgo | 2 |
| 미래 plan | desired_lat_accel(t=0, +0.3, +0.6, +1.0, +1.5s) | 5 |
| 측정 | measured_lat_accel, steeringAngle, steeringRate | 3 |
| jerk | lateral_jerk_lookahead | 1 |
| 자세 | roll(t=0, +0.5, +1.0), pitch | 4 |
| 비대칭 | sign(desired_curvature) | 1 |
| **센터링 신호** | lateral_offset_now, lateral_offset_avg_5s | **2** |
| (옵션) | 과거 desired_lat_accel × 2 | 2 |

총 18~20차원. NNFF의 4~16차원보다 풍부하지만 여전히 작음.

**§4.1 핵심**: 마지막 그룹 "센터링 신호"가 NNFF에 없던 영역. 모델이 "지금 한쪽으로 쏠렸으니 반대 보정"을 직접 학습 가능.

### 4.2 백본 (1단계: MLP — NNFF 호환)

```
Linear(20 → 32) → tanh
Linear(32 → 16) → tanh
Linear(16 → 1)        ← δ (residual)
```

NNFF의 `FluxModel` 포맷 그대로. JSON 구조:

```json
{
  "model_type": "cas_torque" | "cas_angle",
  "car": "HYUNDAI_IONIQ_5",
  "eps_firmware_hash": "...",
  "trained_on_hours": 32.4,
  "trained_at": "2026-06-15T10:00:00",
  "input_size": 20,
  "output_size": 1,
  "input_mean":  [...],
  "input_std":   [...],
  "layers": [
    {"W_0": [[...]], "b_0": [...], "activation": "tanh"},
    {"W_1": [[...]], "b_1": [...], "activation": "tanh"},
    {"W_2": [[...]], "b_2": [...], "activation": "identity"}
  ],
  "alpha_max": 1.0,
  "feature_spec": ["vEgo", "aEgo", "lat_accel_now", ...]
}
```

### 4.3 백본 (2단계, 선택: Mini-TCN)

MLP가 부족하면 입력 앞에 1D causal conv 2~3층 (channel 16) 추가. numpy 30줄로 구현. 같은 JSON 포맷에 `{"type": "conv1d_causal", ...}` 레이어 추가.

### 4.4 출력 합성

CAS는 **그 시점의 base FF**에 residual δ를 더한다. base가 무엇이든 무관(§9 참조).

- 토크 차량:
  ```
  ff_base = NNFF(...) if NNFF_on else classical_FF(lat_accel, friction)
  output_torque = ff_base + α · δ_CAS
  ```
- 앵글 차량:
  ```
  output_angle = VM.get_steer_from_curvature(...) + α · δ_CAS
  ```

α (∈ [0, 1])는 §5 신뢰도 게이트. 학습 미숙·이상 입력 시 0으로 떨어져 base만 사용.

---

## 5. α 신뢰도 게이트 (안전 핵심)

α 감쇠 트리거:
1. 입력 정규화 후 |z| > 3 (학습 분포 밖)
2. vEgo < 5 (저속, 학습 데이터 적음)
3. 차종/EPS firmware mismatch
4. 사용자 UI에서 끔
5. δ가 비정상적으로 큼 (>3σ) → 클리핑

상황 적응적 α (NNFF는 always-on):
- 직진 + 사용자 손 안 댐 + 모델 신뢰 높음 → α 충분히 높임 (센터링 활성)
- 큰 코너 진입 → α 약간 낮춤 (base 우선)
- 사용자 개입 감지 → α = 0 즉시

→ **최악의 경우 α=0이면 CAS 없는 기존 컨트롤러와 동일하게 동작**.

---

## 6. 학습 파이프라인 (F안: 자동 트리아지 + 가중 supervised)

### 6.0 핵심 사상

**사람이 직접 운전한 데이터가 필요한 게 아니다.** openpilot이 자기 자신을 운전하는 평소 rlog가 가장 가치 있다. 이유:
- base가 정해져 있어 residual 신호 추출이 깔끔
- 사용자 개입 = 가장 강력한 무료 라벨 ("openpilot이 여기서 틀렸다" 신호)
- 데이터 양 압도적

→ **"openpilot 자기개선 학습"**. 사용자는 평소처럼 운전만 하면 됨.

### 6.1 자동 트리아지 (구간 유형 + 가중치)

PC 학습 스크립트가 rlog의 매 구간을 5종으로 자동 분류:

| Type | 조건 | 가중치 w | 학습 신호(타겟 δ_target) |
|---|---|---|---|
| **T1** 양호·모방 | op ON, \|offset\| 작음, 미개입 | 0.3 | δ_target ≈ 0 (현재 op 토크가 정답) |
| **T2** 쏠림·보정 | op ON, \|offset\| 큼, 미개입 | 0.6 | 미래 offset의 반대 방향 (보정 신호) |
| **T3** 강한 개입 ★ | op ON, 사용자 강한 개입 | **1.0** | 사용자 추가 토크 = δ_target |
| **T4** 약한 개입 | op ON, 사용자 약한 개입 | 0.5 | 사용자 추가 토크 (소량) |
| **T5** 수동 운전 | op OFF + 사람 운전 | 0.1 | 참고용 모방 (선택) |
| **제외** | 카메라 오류, vEgo<5, 비활성 등 | 0 | — |

**T3가 가장 강력**한 신호 — 사용자가 손 댄 그 순간이 "openpilot이 여기서 틀렸다"는 무료 라벨.

### 6.2 파이프라인 단계

```
[rlog 파일들]
        ↓
[1] cereal 파싱 → carState, modelV2, controlsState,
                   liveCalibration, lateralPlan, lateralLearningFlag
        ↓
[2] 100Hz 타임라인으로 정렬
        ↓
[3] 차량 타입 자동 감지 (CP.steerControlType)
    → 토크용 / 앵글용 데이터셋 분기
        ↓
[4] 자동 트리아지 (§6.1)
    - 매 프레임에 type ∈ {T1..T5, 제외} 라벨
    - 가중치 w 부여
        ↓
[5] 특징 + 타겟 계산
    - 입력 x: §4.1
    - 타겟 δ_target: §6.1 표대로 type별로 다르게
    - 미래 offset 측정용 lookahead window: 1~2초
        ↓
[6] PyTorch 학습
    - MLP 3층, Adam, 50~200 epoch
    - loss = w · (δ - δ_target)² + λ_smooth·smoothness + λ_reg·|δ|
    - 검증셋 (timewise split) early stop
        ↓
[7] 검증 지표 출력
    - mean(|lateral_offset|) — 핵심
    - std(lateral_offset)
    - max(|lateral_offset|)
    - 사용자 개입 빈도
    - base만 / 기존NNFF / CAS 비교
        ↓
[8] JSON export
    - cas_<car>_<eps>.json
    - trained_on_hours, trained_at 메타 포함
```

### 6.3 "사용자 개입" 정의 (T3/T4 분류 기준)

기기 측 [lateral_data_marker]에서 매 프레임 계산:
- carState.steeringPressed && |steeringTorqueDriver| > threshold_strong → T3
- carState.steeringPressed && |steeringTorqueDriver| > threshold_weak → T4
- 외에 미개입

threshold는 차종별/사용자별 1~2σ 범위로 자동 조정. 너무 잦은 작은 보정은 무시.

### 6.4 T2 "미래 offset 반대 방향" 보정 신호

```
t 시점: op가 토크 T_op를 가함 → 그 결과 t+Δ 시점 lateral_offset = ε
δ_target(t) = -k · ε  (단순 비례 보정. k는 차종별 캘리브레이션)
```

핵심: 사후적으로 "이때 ε만큼 쏠렸으니 그때 -k·ε만큼 보정했어야 했다" 라고 학습. 미래 정보 없이는 못 함 → **오프라인 학습의 강점** (기기에서는 불가능).

---

## 7. 기기 측 추가 코드 (학습 0줄)

### 7.1 추론 측

- `opendbc_repo/opendbc/car/cas_model.py` (≈ 100줄)
  - `CASModel` 클래스 — FluxModel 확장, conv1d 옵션
- `selfdrive/controls/lib/latcontrol_torque.py` 패치
  - NNFF 로딩 코드 옆에 CAS 로딩 추가
  - α 게이트 + residual 합산
- `selfdrive/controls/lib/latcontrol_angle.py` 패치 (변화 큼)
  - 현재 패스스루 → α·δ_angle 추가

### 7.2 데이터 수집 측 (개발자 측만, 사용자 측은 평소 rlog)

- 사용자 측에 별도 마커 코드 **불필요**. carrot이 평소 쌓는 rlog 그대로 사용.
- 개발자(jominki354)가 본인 차/협조자 rlog 모아 PC에서 트리아지.
- 트리아지는 PC 학습 스크립트 안에서 (§19 참조).

### 7.3 사용자 UI

- 토글 단 하나: **"CAS ON/OFF"**.
- 추가 설정 0. NNFF 토글 옆에 나란히.

### 7.4 차종 매칭 상태 표시 (NNFF 패턴 그대로)

NNFF는 매칭된 차량의 이름 옆에 ",NNFF"를 붙여 표시 ([carrot.cc:3198](selfdrive/ui/carrot.cc#L3198)):
```cpp
QString NNFFModelName = QString::fromStdString(params.get("NNFFModelName"));
if (NNFFModelName.length() > 0) carName += ",NNFF";
```

**CAS도 동일하게**:
```cpp
QString CASModelName = QString::fromStdString(params.get("CASModelName"));
if (CASModelName.length() > 0) carName += ",CAS";
```

- 매칭되면: 차량 이름이 `"HYUNDAI IONIQ 5,NNFF,CAS"`처럼 표시
- 매칭 안 되면: 표시 안 됨 → 사용자가 자기 차종 미지원임을 자연스레 인지
- 별도 알림/HUD 위젯 만들 필요 없음 — 기존 차량명 표시 자리 활용

---

## 8. 가중치 배포 (NNFF 패턴 그대로)

- 위치: `opendbc_repo/opendbc/car/torque_data/cas/<car>.json`
- 배포 경로: 깃 푸시 → carrot 업데이트 → 사용자 자동 적용
- 사용자 hot-swap, params 저장 등 **없음** — NNFF처럼 정적 파일.
- 차종 매칭: NNFF의 `get_nn_model_path` 패턴 그대로 (차종 + EPS firmware 해시)

---

## 9. NNFF와의 관계

> **CAS는 NNFF와 무관한 독립 시스템**이다. 슈퍼셋도 호환도 아니다.
> 다만 같은 lateral 경로에 두 NN이 영향을 줄 수 있으므로 **동시 사용 시 충돌만 회피**하면 된다.

### 9.1 동시 사용 보장 — 자동 공존

핵심: CAS는 "그 시점의 base FF"에 residual δ를 더하기만 한다. **base가 classical이든 NNFF든 무관**.

코드 분기 (개념):

```python
# 1) base FF 결정 — NNFF가 켜져 있으면 NNFF가, 아니면 classical
if nnff_enabled:
    ff_base = torque_from_nn(...)         # NNFF
else:
    ff_base = torque_from_lateral_accel(...)   # classical

# 2) CAS는 base 위에 δ만 더함
if cas_enabled:
    delta = cas_model(x)
    ff_output = ff_base + alpha * delta
else:
    ff_output = ff_base
```

→ **모든 조합 자동 공존**:

| NNFF | CAS | 동작 |
|---|---|---|
| OFF | OFF | classical FF만 (stock) |
| ON | OFF | NNFF만 (현재 NNFF 사용자 그대로) |
| OFF | ON | classical + CAS δ |
| ON | ON | NNFF + CAS δ |

### 9.2 UI 토글

`NNFF` 토글과 `CAS` 토글이 **별개**. 사용자는 둘 다 OFF/하나만 ON/둘 다 ON 자유 선택.

기본값:
- 토크 차량: NNFF 기본 ON (현재 사용자 그대로), CAS 검증 후 기본 ON
- 앵글 차량: CAS만 (NNFF는 토크 전용)

### 9.3 개발자 학습 시 NNFF 일관성

개발자가 rlog 수집 시:
- NNFF on/off 혼용 → base 정의 흔들림 → 학습 신호 노이즈↑
- 권장: 수집 구간에서 NNFF **고정** (ON 또는 OFF). 학습 스크립트가 rlog 메타 자동 감지 후 경고.

---

## 10. 구현 로드맵

### Phase 0 — 인프라
- [ ] `CASModel` 클래스 (FluxModel 확장)
- [ ] cereal에 `lateralLearningFlag` 필드 추가
- [ ] `lateral_data_marker.py` 작성 (5종 자동 분류)
- [ ] UI 토글 추가

### Phase 1 — 토크 차량 (NNFF 상위호환)
- [ ] PC 측 `cas_train.py` 작성 (자동 트리아지 + F안 학습)
- [ ] 1대 차량(사용자 차)에서 20~40시간 데이터 수집
- [ ] PC 학습 → JSON 생성
- [ ] `latcontrol_torque.py`에 CAS 로딩 + α 게이트
- [ ] A/B 테스트: base / NNFF / CAS

### Phase 2 — 앵글 차량 (신영역)
- [ ] 앵글 차량 응답 데이터 수집
- [ ] `latcontrol_angle.py`에 α·δ 추가
- [ ] Tesla/Ford 등 앵글 차량에서 검증

### Phase 3 — 정착
- [ ] Mini-TCN 도입 여부 결정 (Phase 1·2 결과)
- [ ] 차종별 기본 JSON 묶음 배포
- [ ] 사용자 가이드 문서

---

## 11. 운영 모델 — NNFF 그대로 (사용자 확정 2026-05-19)

> **개발자(jominki354)가 학습/배포, 사용자는 ON/OFF만.** NNFF 운영 모델 그대로.

### 11.1 역할 분리

| 주체 | 역할 |
|---|---|
| **개발자 (jominki354)** | rlog 수집, PC에서 차종별 학습, `cas_<car>.json` 생성, 깃 푸시 |
| **사용자** | carrot 업데이트 받음, UI 토글 ON/OFF, 끝 |

사용자 측에서:
- 학습 시간 = **0h**
- 설정 = **CAS ON/OFF 토글 하나**
- α 조정, 가중치 선택 등 **0개**

### 11.2 차종 지원 리스트 (NNFF 패턴)

```
opendbc_repo/opendbc/car/torque_data/cas/
  HYUNDAI_IONIQ_5.json
  HYUNDAI_SONATA.json
  TOYOTA_RAV4_TSS2.json
  TESLA_MODEL_3.json    # 앵글 차량
  ...
```

- 차종 + EPS firmware 해시 매핑 (NNFF의 `get_nn_model_path` 패턴 그대로)
- 미지원 차종은 자동 fallback → CAS off, classical/NNFF 그대로
- 새 차종 추가 = 개발자가 데이터 모아서 학습 → 깃 푸시 → 사용자 업데이트 시 자동 적용

### 11.3 개발자 학습 데이터 양

개발자가 모으는 데이터는 차종별로 최대한 다양하게:
- 최소 ~20h 이상 (cold start 안정선)
- 권장 100h+ (다양한 노면/속도/날씨)
- 여러 사용자 rlog 풀링 가능 (사용자가 자발 제공 시)
- 상한 없음 — 많을수록 일반화 강함

### 11.4 학습 누적 방식 — 데이터 보관 + 매번 전체 재학습

**핵심 결정**: 데이터를 차종별 폴더에 계속 쌓고, 학습 명령 실행할 때마다 **처음부터 전체 데이터로 다시 학습**.

이유:
- 단순함 (warm-start 안 함 → 옛 데이터 잊을 위험 0)
- 모델 작아 학습 5~30분 → 매번 다시 해도 부담 없음
- 재현 가능 (같은 rlog 집합 → 같은 모델)

대안(warm-start)을 안 쓰는 이유: catastrophic forgetting. 우리 모델 크기에서 굳이 위험 감수 안 함.

### 11.5 차량별 데이터/학습 기록 — 디렉토리 구조

```
~/.cas_train/                                  ← 개발자 PC
  HYUNDAI_IONIQ_5/
    rlogs/                                     ← rlog 누적 보관
      2026-05-19_a.rlog
      2026-05-20_b.rlog
      ...
    history.json                               ← 학습 이력
    checkpoints/                               ← 과거 모델 (롤백용)
      v1_2026-05-19_21h.json
      v2_2026-05-25_45h.json
      ...
  TESLA_MODEL_3/
    ...
```

**history.json 예시**:
```json
[
  {
    "version": 1,
    "trained_at": "2026-05-19T10:00:00Z",
    "rlog_count": 12,
    "total_hours": 21.3,
    "validation": {"mean_offset_m": 0.31, "max_offset_m": 0.72}
  },
  {
    "version": 2,
    "trained_at": "2026-05-25T14:30:00Z",
    "rlog_count": 28,
    "total_hours": 45.1,
    "validation": {"mean_offset_m": 0.24, "max_offset_m": 0.58},
    "improvement_vs_prev": {"mean_offset_m": -0.07}
  }
]
```

**검증 지표가 악화되면 어떻게?**:
- 학습 스크립트가 자동 비교, 악화 시 경고
- 개발자가 깃 푸시 전에 검토
- 필요하면 checkpoints/에서 이전 버전으로 롤백 (수동)

### 11.6 배포 측 — 최신 버전 하나만 덮어쓰기

```
opendbc_repo/opendbc/car/torque_data/cas/HYUNDAI_IONIQ_5.json    ← 항상 최신
```

- 사용자는 깃 업데이트 받으면 자동으로 최신 .json 적용
- 버전 관리는 **깃 히스토리가 자동**으로 함 (`git log -- .../HYUNDAI_IONIQ_5.json`)
- JSON 메타(§19.6)에 trained_at, total_hours, validation 들어가 사용자도 확인 가능

### 11.3 장기 누적 운영 — "Continual Re-training"

**기기에서 학습은 안 함 (P1)**. 하지만 PC에서는 누적 가능:

```
초기 학습 (20~40h rlog)
   ↓
배포 → 사용자 운전 (또 데이터 쌓임)
   ↓
N개월 후, 사용자 rlog 더 모아서 PC 재학습
   ↓
새 JSON 배포 → 더 좋아진 모델
   ↓ ...
```

설계 트릭:
- **rlog 시간 분할 학습**: 최근 50% + 과거 50% 가중평균 → 최근 변화 반영하되 과거 다양성 유지
- **이전 JSON 워밍업**: 새 학습 시 이전 모델 가중치를 초기값으로 사용 → 빠른 수렴, 점진적 개선
- **재학습 주기**: 사용자가 원할 때. 자동화 안 함 (사용자 통제권).

### 11.4 다중 사용자/차량 시나리오

장기적으로 가능한 그림:
- 사용자별 자기 JSON (개체 모델)
- 차종별 공통 JSON (커뮤니티 모델, 깃에 푸시)
- 커뮤니티 풀링: 여러 사용자의 rlog 합쳐서 더 큰 차종 모델 학습 (선택)

이건 Phase 4+ 영역. 1차 목표는 개인 사용자 1명의 데이터로 자기 차 학습.

---

## 12. 중앙 유지 구현 디테일

### 12.1 "쏠림"의 가능한 원인 vs CAS 해결력

| 원인 | 현재 시스템 | CAS가 학습으로 잡나 |
|---|---|---|
| 도로 캠버 | 부분적 | ✓ sign(curvature) + lateral_offset 평균 |
| 휠 얼라인먼트 (좌우 비대칭) | ✗ | ✓ T2/T3 신호로 자연 학습 |
| EPS 응답 비선형 | 부분적 (friction) | ✓ NN의 강점 영역 |
| 속도 의존성 | 부분적 (LOW_SPEED_Y) | ✓ vEgo 입력으로 자연 학습 |
| 코너 진입 늦음 (steerActuatorDelay) | 부분적 | ✓ 미래 plan 입력으로 보상 |
| roll 부정확 | 부분적 (roll_pitch_adjust) | ✓ roll 시퀀스 입력 |
| lat_jerk 보상 부족 | 부분적 | ✓ jerk 입력 유지 |
| 모델의 lane 인식 오차 | ✗ | ✗ (CAS 범위 밖) |

→ 모델 자체 오차 빼고 거의 모든 원인을 CAS가 학습으로 잡음. 단 **모델이 보는 lane이 정답**이라는 가정 — 모델 lane이 틀리면 CAS도 같이 틀림.

### 12.2 검증 지표

학습 끝에 PC 스크립트가 자동 출력:
- `mean(|lateral_offset|)` — 핵심 지표
- `std(lateral_offset)` — 일관성
- `max(|lateral_offset|)` — 최악 케이스
- `사용자 개입 빈도` — 운전자 보정 횟수
- 비교: base만 / NNFF / CAS

---

## 13. 솔직한 한계

1. **lane 인식 자체 오차**: offset 측정이 모델에 의존. 모델이 틀리면 CAS도 틀림. 해결책: α 게이트로 모델 저신뢰 구간 회피.
2. **사용자 개입이 거의 없는 사용자**: T3 신호 부족 → T1/T2만으로 학습. 효과 약함. 해결책: 데이터 양으로 보완 (40h+).
3. **도로 다양성**: 출퇴근만 다니면 그 경로 과적합. 해결책: 정규화 강도 조정, 입력 분포 모니터링.
4. **차량 개체차**: 같은 차종이라도 타이어/얼라인먼트 차이. → 개체 모델로 흡수 (§8).
5. **초기 학습 데이터 부족 (<10h)**: α_max = 0으로 자동 비활성 (§11.2).
6. **자기강화 위험**: T1(현재 op 토크 = 정답) 가중치가 너무 높으면 자기복사 → 새 차별점 0. 가중치 0.3으로 보수적 설정.

---

## 14. 결정 테이블

| # | 항목 | 상태 | 결정 |
|---|---|---|---|
| Q1 | 토크/앵글 어디부터? | ✅ | **둘 다** (내부 분리) |
| Q2 | 학습 위치 | ✅ | **PC 전용**, 기기는 로그만 |
| Q3 | 학습 타겟 | ✅ | **F안**: 자동 트리아지 + 가중 supervised (T1~T5) |
| Q4 | 백본 | 🔄 | **1단계 MLP → 부족시 mini-TCN** |
| Q5 | 학습 데이터 종류 | ✅ | **openpilot 자체 운전 데이터 메인** (사람 수동은 참고만) |
| Q6 | 데이터 양 | ✅ | **개발자가 차종당 20h+ 수집 (사용자 학습 0h)** |
| Q9 | 운영 모델 | ✅ | **NNFF 그대로**: 개발자 학습/배포, 사용자 ON/OFF |
| Q10 | 학습 OS | ✅ | **Linux/WSL2 권장, Windows native 가능** |
| Q11 | 가중치 포맷 | ✅ | **JSON** (safetensors 검토 후 기각) |
| Q7 | 추론 런타임 | ✅ | **순수 numpy**, onnx/torch 안 씀 |
| Q8 | 가중치 포맷 | ✅ | **JSON** (FluxModel 호환 확장) |
| Q-name | 프로젝트 이름 | ✅ 잠정 | **CAS (Carrot Adaptive Steering)** |

---

## 15. NNFF vs CAS — 솔직한 장단점 비교

### 15.1 NNFF의 장점 (우리가 인정해야 할 부분)

| 장점 | 상세 |
|---|---|
| **검증됨** | 수많은 사용자가 실제 도로에서 잘 쓰고 있음. CAS는 미검증. |
| **공유 자산 풍부** | 차종별 `.json`이 이미 많음. CAS는 0부터 모아야 함. |
| **단순함** | 모델 작음, 1회 학습, always-on. CAS는 트리아지/α 게이트 등 복잡도↑. |
| **데이터 양 적음** | 1~5시간으로도 학습 가능. CAS는 20~40h 권장. |
| **lane 인식 무관** | 모델 lane 출력 안 봐도 됨. CAS는 lane이 정답이라는 가정 깊음. |
| **사람 운전 부드러움** | 사람 운전 흉내라 부드러운 게 자연스러움. |

### 15.2 NNFF의 단점 (CAS가 노리는 빈틈)

| 단점 | CAS 대응 |
|---|---|
| 토크 차량만 지원 | ✅ CAS는 앵글까지 |
| 사람 운전 모방 → 사람 쏠림까지 답습 | ✅ outcome 기반 + T3 신호 |
| base 컨트롤러 없음 → 학습 실패 시 위험 | ✅ residual + α 게이트 |
| 좌우 비대칭 직접 학습 못 함 | ✅ sign(curvature) + 센터링 입력 |
| **사용자 개입 = 데이터 제외**로 처리 | ✅ T3 최강 신호로 활용 |
| 사용자가 데이터 큐레이션 부담 | ✅ 자동 트리아지 |
| 장기 누적 일관성 약함 | ✅ continual re-training + 이전 JSON 워밍업 |

### 15.3 CAS의 단점 (정직하게)

| 단점 | 대응 가능성 |
|---|---|
| **미검증** | Phase 1에서 1대로 검증 후 확장 |
| **복잡도 ↑** | 코드 늘어남. 자동 트리아지·α 게이트 로직 필요. |
| **lane 정답 가정** | α 게이트로 모델 저신뢰 구간 회피 |
| **데이터 양 ↑** | NNFF 1~5h vs CAS 20~40h. 사용자 운전 시간 필요. |
| **가중치 튜닝 어려움** | T1~T5 가중치 0.3/0.6/1.0/0.5/0.1 초기값 설정 후 실험으로 조정 |
| **개입 적은 사용자** | T3 신호 부족 → 효과 약함. 데이터 양으로 보완. |
| **카메라 캘리브 의존성** | offset 측정이 cal 영향. 부정확하면 학습도 부정확. |

### 15.4 결정적 차별 5가지 (요약)

1. **앵글 차량 지원**
2. **Residual + α 게이트** — 안전성
3. **자동 트리아지** — 사용자 부담 0
4. **사용자 개입 = 무료 라벨**
5. **장기 누적 친화** — continual re-training

---

## 16. openpilot 코드에서 참고/반영할 것

openpilot 자체 코드를 검토한 결과, CAS가 활용할 인프라가 이미 상당히 있음.

### 16.0 NNFF가 openpilot에 의존하는 정도 (참고용)

NNFF는 openpilot 신호 위에 NN 출력을 얹는 구조:

| 활용 | 내용 |
|---|---|
| openpilot에서 받아씀 | `model_data.acceleration.y/orientation.x/y` (미래 plan), `CP.steerActuatorDelay`, `ModelConstants.T_IDXS`, `params.roll`, `CS.vEgo/aEgo/steeringRateDeg`, `VehicleModel` |
| 무시함 | **liveTorqueParameters** (FF를 통째 대체하니 friction/factor 무의미) |
| 자체 구현 | `FluxModel` (60줄 numpy MLP), lookahead jerk, future/past time offsets, 입력 벡터 빌딩 |

→ NNFF = "**openpilot 신호 + 자체 NN으로 FF 전체 대체**". 사용자 학습 0h (twilsonco가 배포).

CAS와의 의존 패턴 차이:
- NNFF: 입력 의존, **출력 통째 대체** → liveTorqueParameters 무시
- CAS: 입력 의존, **출력은 base 위 잔차** → liveTorqueParameters와 자연 공존

### 16.1 [torqued.py (stock의 liveTorqueParameters)](selfdrive/locationd/torqued.py)

이미 운영 중인 온라인 토크 파라미터 추정 시스템:
- `latAccelFactor`, `latAccelOffset`, `frictionCoefficient`을 SVD로 추정 (PointBuckets + slope2rot)
- `LiveTorqueParameters` params로 캐시 — 다음 부팅 때 복원
- **양호 데이터 정의** (그대로 차용 가능):
  ```
  all(lat_active) and not any(steer_override)
    and vego > MIN_VEL(15)
    and abs(steer) > STEER_MIN_THRESHOLD(0.02)
    and abs(lateral_acc) > LAT_ACC_THRESHOLD(1)
  ```
  → **CAS의 T1 양호 구간 필터 그대로 채택**.

**CAS와의 관계**: liveTorqueParameters가 friction/factor를 자동 수렴시킴 → CAS의 base는 이미 자동 튜닝된 값 사용 → CAS는 그 위 residual δ만 학습. **충돌 0, 자연 공존**.

### 16.2 [lateral_planner.py + lane_planner_2.py — carrot의 기존 센터링](selfdrive/controls/lib/lateral_planner.py)

이미 룰베이스 센터링 보정이 있음:
- **`PathOffset`** (사용자 수동 cm): `path_xyz[:, 1] += self.pathOffset`
- **`LP.offset_total`** ([lane_planner_2.py:251](selfdrive/controls/lib/lane_planner_2.py#L251)): 차선폭/곡률 의존 자동 보정
  - `offset_curve` (코너에서)
  - `offset_lane` (차선폭 좁/넓)
  - `diff_center` (좌우 차선 차이)
  - `FirstOrderFilter(0.0, 2.0, DT_MDL)`로 2초 평활

**CAS와의 관계** (충돌 회피 전략):
- CAS는 **토크/앵글 단계**에서만 작동. **path는 손 안 댐**.
- 즉 `lateral_planner`의 `PathOffset`/`offset_total`은 그대로 두고, 그 후단 컨트롤러에서 CAS의 δ가 더해짐.
- 사용자가 `PathOffset`을 직접 만지는 의도는 존중.
- 향후 옵션: `PathOffset`도 CAS가 동적 출력 (Phase 4+).

### 16.3 PointBuckets 아이디어 차용

torqued가 steer torque 범위별 버킷으로 데이터 분포 균형을 잡음. CAS 학습 시에도 유용:
- **(curvature × vEgo) 2D 버킷**: 직진/완만/급코너 × 저속/중속/고속
- 빈 버킷은 over-sampling, 과밀은 sub-sampling
- 결과: 사용자가 매일 같은 길만 다녀도 학습 분포가 골고루

### 16.4 [liveDelay.lateralDelay](selfdrive/locationd/) — 토크 응답 지연

openpilot이 이미 actuator delay를 추정 중. CAS는:
- 입력 신호로 받음 (또는)
- 미래 plan 시간 오프셋 계산에 사용 (NNFF가 이미 함)
- 학습이 자체적으로 흡수 가능

### 16.5 lateralPlan 메시지 — CAS 입력 소스

| 신호 | CAS 입력 활용 |
|---|---|
| `dPathPoints` | MPC가 푼 미래 path 33점 |
| `curvatures` | 미래 desired curvature 시계열 |
| `curvatureRates` | curvature 변화율 = jerk 소스 |
| `position.x/y/z` | MPC 솔루션 경로 |
| `useLaneLines` | 모델 신뢰도 게이트의 한 축 |
| `laneWidth` | 차선폭 정규화 |
| `latDebugText` | 디버깅 |

### 16.6 카메라 캘리브레이션 (PoseCalibrator)

torqued가 사용하는 `PoseCalibrator`를 CAS도 활용. lateral_offset 계산 정확도의 핵심.

### 16.7 MPC cost 구조 참고

`LATERAL_MOTION_COST=0.11`, `LATERAL_JERK_COST=0.04`, `STEERING_RATE_COST=700` — 학습 loss의 smoothness 페널티 weight 잡을 때 참고 가능. MPC와 같은 스케일로 잡으면 일관성↑.

### 16.8 cereal 메시지 추가 위치

`lateralLearningFlag`를 어디에 둘지:
- **옵션 A**: `lateralPlan`에 한 필드 추가 (가장 가볍지만 의미 살짝 어긋남)
- **옵션 B**: 별도 메시지 `lateralLearningInfo` 신설 (가장 명확, 다른 정보도 같이 넣기 좋음)
- **옵션 C**: 기존 carrot 메시지에 묻힘

**추천: B** — 향후 확장 여지 큼.

### 16.9 carrot의 carrot_learning.py와의 관계

기존 carrot Auto-Tuner (614 LOC, classical):
- 스칼라 파라미터 (latAccelFactor, friction) 온라인 추정
- 추정 위치: 기기에서 실시간

**CAS와의 관계**:
- carrot_learning.py = 1차원 스칼라 파라미터 추정 (보수적)
- CAS = 다차원 residual 보정 (적극적)
- **둘은 직교**. 공존. UI 토글로 사용자가 선택:
  - `Off` / `Classical Auto-Tuner만` / `CAS만` / `둘 다`

---

## 17. CAS 설계에 §16을 반영한 갱신점

§16의 발견을 반영해 다음을 갱신:

1. **§6.1 T1 필터 정의 강화**: torqued의 양호 데이터 정의 그대로 채택
   - `lat_active + ~steer_override + vego > 15 + |steer| > 0.02 + |lat_acc| > 1`

2. **§6 학습 데이터 분포**: (curvature × vEgo) 2D 버킷화 추가 (§6.7 신설 예정)

3. **§4.4 base 정의 명시**: base = liveTorqueParameters의 수렴값을 사용한 classical FF (이미 그렇게 동작 중이라 자연 채택)

4. **§7.2 cereal 필드**: `lateralLearningInfo` 신규 메시지 (옵션 B)

5. **§4.1 입력에 lateralPlan 신호 추가 검토**: `useLaneLines`, `laneWidth` (정규화용)

6. **§5 α 게이트에 모델 신뢰도 축 추가**: `useLaneLines == False`거나 `LP.d_prob < 0.3`이면 α 감쇠

7. **carrot_learning.py와 명시적 직교**: §10 로드맵 Phase 0에 "UI 토글로 공존 보장" 추가

---

## 18. 2026년 5월 기준 추가 조사 — 적용할 최신 기법

§11(이전 조사: cnlt_design.md §11)에서 4편 reference를 확보했고, 이번엔 CAS 컴포넌트별로 다시 깊게 조사. 핵심 6개 발견.

### 18.1 ⭐ Predictive Preference Learning from Human Interventions (PPL) — arXiv 2510.01545

**가장 강력한 추가 후보.** 우리 F안의 T3(사용자 개입)을 훨씬 효율적으로 활용.

원 논문 핵심 (abstract 확인):
- 사용자 개입 1회를 **L개의 미래 스텝(preference horizon L)** 으로 부트스트래핑
- 가정: "에이전트가 같은 행동을 계속하면, 사용자도 L 스텝 동안 같은 개입을 했을 것"
- **이론적 trade-off**: L 크면 risky-state coverage ↑, 하지만 label correctness ↓ (멀어질수록 가정이 약해짐)
- 결과: 개입 횟수 적어도 정책 개선 가속

CAS 적용:
- 우리 T3 신호는 1프레임 → **개입 직후 L 스텝까지 확장**
- 차량 동역학 시간 스케일 고려: **L ≈ 0.5~1.0초 분량** (100Hz면 50~100 스텝)
- 두 가지 가중 방식 선택 가능:
  1. **균일 가중** (원 논문 방식): L 스텝 동안 w=1.0 동일
  2. **부드러운 감쇠** (우리 변형): `w_t = exp(-t² / 2σ²)`, σ ≈ 0.3s — label correctness 보호

§6.1 갱신:
```
T3 (기본): 개입 순간 1프레임, w=1.0
T3 (PPL):  개입 직후 L 스텝 확장 (L = 50~100 @ 100Hz)
           가중치 w_t = uniform 또는 exp(-t²/2σ²)

→ 사용자 개입 1회의 유효 학습 신호량 50~100배
→ T3 부족한 사용자도 학습 가능
```

L 자동 튜닝 (옵션):
- 검증셋 mean_offset 기준으로 L ∈ {30, 50, 70, 100} 그리드 서치
- PC 학습 스크립트가 자동 선택

### 18.2 Behavior Discriminator (BD) — arXiv 2301.11734

준지도학습으로 데이터 품질 자동 선별 (Positive-Unlabeled Learning).

CAS 적용:
- 현재 우리 T1~T5 트리아지는 **규칙 기반** (lateral_offset 크기, 개입 여부 등)
- BD는 **학습 기반**: "양호 운전" vs "비양호 운전"을 작은 분류기로 자동 학습
- Phase 2+에서 트리아지 정교화에 활용

당장은 규칙 기반 T1~T5 유지. Phase 2 이후 옵션.

### 18.3 PINN 강화 — arXiv 2503.xxxxx 외 (2025 다수)

§11에 이미 PGNN 채택했지만, 2025 최신 PINN 연구가 한 단계 더 나아감:
- **Sequential training**: 여러 PINN을 동시 학습하는 coupling 문제 해결
- **highly nonlinear lateral dynamics 커버**: 학습 분포 밖에서도 물리 제약으로 안정

CAS 적용:
- §5 α 게이트에 **물리 제약 위반 시 감쇠** 추가
- 예: `|δ| > k · |base_FF|` (residual이 base보다 크면 비정상) → α 감쇠
- 예: lat_jerk 한계 초과 → α 클리핑
- 이미 우리 §5에 부분 있음. PINN 영감을 받아 **물리 sanity check를 명시적 레이어로 분리**.

§5 갱신 예정:
```
α_final = α_data_confidence × α_physics_sanity × α_user_toggle
```

### 18.4 Reset It and Forget It — arXiv 2310.07996

Last-layer를 주기적으로 reset하면 continual/transfer learning 성능 향상.

CAS 적용:
- §11.2 전략 A (차종 base + fine-tune)에서:
  - 사용자 fine-tune 시작 시 **last-layer만 reset 후 재학습**
  - backbone은 frozen
  - 이전 사용자 학습이 backbone에 누적된 편향 제거 효과
- 주기적 재학습 시에도 유용

§11.4 갱신 예정:
```
fine-tune 시작 시:
  1. backbone 가중치 = base 모델에서 복사 (freeze)
  2. last-layer 가중치 = 랜덤 init (reset)
  3. 사용자 데이터로 last-layer만 학습 (1~5h)
```

### 18.5 Uncertainty-aware Kalman Filter NN — arXiv 2010.08397

Few-shot dynamics 적응에 KF 활용. §11(cnlt) [4]의 발전형.

CAS 적용:
- 사용자 fine-tune이 1~5h 데이터로 가능하다는 이론적 근거
- **Bayesian last-layer + KF**: last-layer 가중치를 Gaussian으로 두고 KF로 update
- 매우 적은 데이터(~1h)로도 안정 적응
- Phase 3 이후 검토 (지금은 점진 활성화로 충분)

### 18.6 SAE 2026-01-0037 (Robust Lane Centering Controller) — KPI 벤치마크

2026년 1월 발표된 LCC 연구의 성능 지표 (참고):
- **mean lateral offset ±0.35 m**
- **lateral jerk ±9 m/s³**

CAS 검증 지표(§12.2)의 벤치마크로 활용:
- CAS가 ±0.35m 이내, jerk ±9 m/s³ 이내 달성 → 산업 수준 도달
- 우리 검증 지표 표에 이 벤치마크 row 추가

### 18.7 적용 안 할 것 (참고로 기각)

| 기법 | 기각 이유 |
|---|---|
| Implicit Behavior Cloning (EBM) — IEEE 10471344 | 100Hz 실시간 추론 부적합, 너무 무거움 |
| E2E driving (Wayve/Qualcomm 2026.03) | 패러다임 자체가 다름. base+residual 아님. |
| OpenLKA dataset | 학습 데이터 다양화 시 참고 가능, 우선순위 낮음 |
| RNN Robustness Verification (arXiv 2309.08852) | 검증 자체는 별도 작업 |

### 18.8 §6.1 트리아지 표 갱신 (PPL 반영)

| Type | 조건 | 가중치 w | 학습 신호 | **갱신: 시간 윈도우** |
|---|---|---|---|---|
| T1 | op ON, offset 작음, 미개입 | 0.3 | δ_target ≈ 0 | 단일 프레임 |
| T2 | op ON, offset 큼, 미개입 | 0.6 | 미래 offset 역 | 단일 프레임 |
| **T3 (PPL)** | op ON, 강한 개입 | 1.0 → **시간 가중** | 사용자 추가 토크 | **개입 ± 1초, 가우시안 감쇠** |
| T4 | op ON, 약한 개입 | 0.5 → 시간 가중 | 사용자 추가 토크 | **개입 ± 0.5초** |
| T5 | op OFF + 사람 | 0.1 | 모방 (참고) | 단일 프레임 |

→ T3/T4가 시간축으로 확장되면서 **유효 학습 신호량이 ~10배 증폭**. 사용자 개입 적어도 학습 가능.

### 18.9 우선순위 정리

| 기법 | Phase | 영향 |
|---|---|---|
| PPL (T3 시간 윈도우) | **Phase 1** | T3 신호 증폭, 데이터 효율 ↑ |
| Last-layer reset (fine-tune) | **Phase 1** | 1~5h fine-tune 안정화 |
| 물리 sanity α 게이트 (PINN) | **Phase 1** | 안전성 ↑ |
| ±0.35m KPI 벤치마크 | **Phase 1** | 검증 표준화 |
| BD (학습 기반 트리아지) | Phase 2 | T1~T5 자동 개선 |
| Bayesian last-layer + KF | Phase 3 | 데이터 더 적게 (~1h) |

---

## 20. 코드 배치 — 한 폴더에 모음

> CAS 관련 코드/가중치를 **`selfdrive/carrot/cas/` 단일 폴더**에 모음. NNFF처럼 흩어지지 않게.

### 20.1 디렉토리 구조

```
selfdrive/carrot/cas/                  ← 메인 디렉토리 (기기 + 데이터)
  __init__.py
  model.py                             # CASModel 클래스 (numpy 추론)
  runtime.py                           # latcontrol_*.py에서 import할 헬퍼
  weights/                             # JSON 가중치 (차종 리스트)
    HYUNDAI_IONIQ_5.json
    TOYOTA_RAV4_TSS2.json
    TESLA_MODEL_3.json                 # 앵글 차량
    ...
  README.md                            # CAS 사용/배포 가이드

tools/cas/                             ← PC 학습 도구 (기기에 안 들어감)
  train.py                             # 단일 진입점 (§19.3)
  triage.py                            # T1~T5 자동 분류 로직
  features.py                          # 입력 벡터 빌더
  validate.py                          # 검증 지표 출력
  export_json.py                       # torch state → JSON
  README.md                            # 개발자(jominki354) 가이드
```

→ **기기에 들어가는 것**: `selfdrive/carrot/cas/`만 (model.py, runtime.py, weights/)
→ **PC에서만 쓰는 것**: `tools/cas/` (학습 도구, 기기 빌드에 포함 안 됨)

### 20.2 파일별 역할

| 파일 | 역할 | LOC 추정 |
|---|---|---|
| `cas/model.py` | `CASModel` 클래스. NNFF `FluxModel` 확장. numpy 추론. | ~100 |
| `cas/runtime.py` | `CASRuntime` 클래스. 컨트롤러에서 호출. JSON 로드, α 게이트, 차종 매칭. | ~150 |
| `cas/weights/*.json` | 차종별 학습된 모델 (jominki354 배포) | 각 ~50KB |
| `cas/README.md` | "이게 뭐고 어떻게 동작하는지" | — |
| `tools/cas/train.py` | rlog → 트리아지 → 학습 → JSON 한 번에 | ~300 |
| `tools/cas/triage.py` | T1~T5 자동 분류 | ~150 |
| `tools/cas/features.py` | 입력 벡터 빌더 (기기와 일관성 보장 필수) | ~100 |
| `tools/cas/validate.py` | mean_offset/std/max 등 검증 지표 | ~100 |
| `tools/cas/export_json.py` | PyTorch state_dict → JSON | ~60 |

### 20.3 기존 파일 침습 최소화

CAS 도입을 위해 기존 코드에 추가되는 줄은 **합 ~30줄 이하**로 제한:

| 파일 | 추가 내용 | 라인 |
|---|---|---|
| `selfdrive/controls/lib/latcontrol_torque.py` | `CASRuntime` import, α·δ 합산 | ~10 |
| `selfdrive/controls/lib/latcontrol_angle.py` | `CASRuntime` import, α·δ 합산 | ~10 |
| `selfdrive/ui/qt/offroad/settings.cc` | CAS 토글 한 줄 | ~3 |
| `selfdrive/ui/carrot.cc` | 차종 이름에 ",CAS" 표기 (§7.4) | ~3 |
| `common/params_keys.h` | "CAS", "CASModelName" 키 등록 | ~3 |

→ 기존 파일은 거의 안 건드림. 로직은 다 `cas/` 폴더 안에.

### 20.4 features.py가 핵심 — 기기와 PC의 일관성

가장 중요한 한 가지: **입력 벡터를 만드는 코드는 PC 학습과 기기 추론이 똑같아야 함**.

해결: `cas/features.py`를 **양쪽에서 공유**.

```
selfdrive/carrot/cas/features.py        ← 기기에서 import (runtime.py가 사용)
                                        ← PC에서도 import (tools/cas/train.py가 사용)
```

PC 도구가 openpilot 레포 안에 있으므로 `from openpilot.selfdrive.carrot.cas.features import build_feature_vector`로 양쪽에서 같은 함수 호출. **버전 어긋날 일 없음**.

### 20.5 import 그래프

```
[기기 측]
  latcontrol_torque.py ──┐
                         ├─► cas.runtime ──► cas.model
  latcontrol_angle.py  ──┘                ──► cas.features
                                          ──► cas/weights/<car>.json

[PC 측 — 개발자만]
  tools/cas/train.py ──► cas.features      (기기와 동일)
                     ──► tools/cas/triage
                     ──► tools/cas/validate
                     ──► tools/cas/export_json ──► cas/weights/<car>.json (덮어쓰기)
```

기기 측은 `tools/cas/`를 전혀 모름. PC 측은 `cas/features.py`를 공유.

### 20.6 깃에 들어가는 것

```
✅ selfdrive/carrot/cas/         (전부)
✅ tools/cas/                    (전부)
❌ ~/.cas_train/                 (개발자 PC 로컬, .gitignore)
```

### 20.7 의도적으로 안 쓴 경로

| 경로 | 안 쓴 이유 |
|---|---|
| `opendbc_repo/opendbc/car/torque_data/cas/` | NNFF는 여기 있지만, opendbc는 comma 본가 영역. carrot 자체 기능은 carrot 폴더가 맞음. |
| `selfdrive/cas/` (carrot 밖) | carrot 정체성 약화. carrot 하위가 적절. |
| `tools/` 루트에 흩어 놓기 | 사용자(jominki354) 한 폴더 정신과 어긋남. |

---

## 19. 개발자 학습 환경 (jominki354 측)

### 19.1 OS 호환성

| OS | 지원 | 비고 |
|---|---|---|
| **Linux (Ubuntu 22.04+)** | ✅ 권장 | openpilot 메인 환경, cereal/rlog 도구 네이티브 |
| **Windows 11** | ✅ 가능 | **WSL2 권장** (Ubuntu) 또는 native Python |
| **macOS** | △ | cereal 빌드 까다로움, 비권장 |

→ 학습 코드는 **순수 Python**으로 작성 → OS 무관. 어려운 건 cereal 의존성뿐 (rlog 파싱). WSL2가 가장 마찰 적음.

### 19.2 의존성 (최소)

```
python>=3.11
torch>=2.0          # CPU 빌드 충분 (모델 작음)
numpy
scipy               # SVD, 보간
pyarrow             # parquet 캐시 (선택)
tqdm                # 진행 표시
zstandard, bz2      # rlog 압축 해제 (LogReader가 사용)
# cereal, openpilot.tools.lib  ← openpilot 레포에 이미 있음, pip 설치 불필요
```

이상. **CUDA 불필요** (모델 ~1000 파라미터).

### 19.2.1 rlog 읽기 — openpilot 표준 API 그대로 사용

별도 파서 작성 안 함. openpilot의 [tools/lib/logreader.py](tools/lib/logreader.py)의 `LogReader` 사용:

```python
from openpilot.tools.lib.logreader import LogReader

lr = LogReader("path/to/rlog.bz2")   # .zst, 디렉토리, comma connect URL 모두 가능
for msg in lr:
    which = msg.which()
    if which == "carState":
        v_ego = msg.carState.vEgo
        steer_pressed = msg.carState.steeringPressed
    elif which == "modelV2":
        pos_y = msg.modelV2.position.y
        accel_y = msg.modelV2.acceleration.y
    elif which == "controlsState":
        curvature = msg.controlsState.curvature
    elif which == "carParams":
        car = msg.carParams.carFingerprint
        eps_fw = msg.carParams.carFw    # EPS firmware 해시 추출 가능
```

지원 형식: 압축 자동 해제 (bz2/zstd), 로컬 파일/디렉토리/Route/comma URL.

### 19.3 단일 진입점

```bash
# Linux / WSL2
$ python tools/cas_train.py \
    --rlogs ~/rlogs/HYUNDAI_IONIQ_5/ \
    --car HYUNDAI_IONIQ_5 \
    --output opendbc_repo/opendbc/car/torque_data/cas/HYUNDAI_IONIQ_5.json

# Windows native (PowerShell)
PS> python tools\cas_train.py `
      --rlogs C:\rlogs\HYUNDAI_IONIQ_5 `
      --car HYUNDAI_IONIQ_5 `
      --output opendbc_repo\opendbc\car\torque_data\cas\HYUNDAI_IONIQ_5.json
```

스크립트가 자동으로:
1. rlog 파싱
2. 트리아지 (T1~T5)
3. PyTorch 학습
4. 검증 지표 출력 (mean_offset, ±0.35m 벤치마크 등)
5. JSON export
6. 깃 add 안내

### 19.4 의존성 관리

- **uv** 또는 **venv + requirements.txt** 권장 (둘 다 Win/Linux OK)
- conda 가능하지만 무거움
- 단순함이 핵심

### 19.5 학습 시간 추정

- 모델 작음 (1k 파라미터)
- 데이터 20h × 100Hz = 720만 프레임 → 트리아지 후 ~수십만 샘플
- **CPU만으로 5~30분** (Adam, 50~200 epoch)
- GPU 있으면 1~5분이지만 불필요

### 19.6 가중치 포맷 결정 — JSON 유지

2026-05 추가 검토 결과:

| 포맷 | 장점 | 단점 | 우리 채택 |
|---|---|---|---|
| **JSON** | 사람 읽음, 깃 diff 가능, 의존성 0 (표준 라이브러리), NNFF 호환 | ASCII로 크기 ~2-3배 (우리 모델엔 무관) | ✅ |
| safetensors | 안전, zero-copy, HuggingFace 표준 | 의존성 `safetensors` 추가, 사람 못 읽음 | ❌ |
| npz | numpy 표준, 작음 | zip bomb 위험, 메타데이터 약함, 사람 못 읽음 | ❌ |
| pickle | 간단 | **임의 코드 실행 위험** | ❌ (피해야 함) |

**결론**: 우리 모델 <100KB라 JSON의 크기 단점 무관. **읽기 가능성·깃 diff·NNFF 호환** 셋이 결정적. safetensors는 LLM처럼 큰 모델용.

확장 JSON 메타 필드 (NNFF보다 풍부):
```json
{
  "format_version": 1,
  "model_type": "cas_torque" | "cas_angle",
  "car": "HYUNDAI_IONIQ_5",
  "eps_firmware_hash": "...",
  "trained_at": "2026-06-15T10:00:00Z",
  "trained_by": "jominki354",
  "trained_on_hours": 87.3,
  "validation": {
    "mean_lateral_offset_m": 0.21,
    "std_lateral_offset_m": 0.14,
    "max_lateral_offset_m": 0.58,
    "user_intervention_rate_hz": 0.003
  },
  "input_size": 20,
  "input_mean": [...],
  "input_std": [...],
  "layers": [...],
  "alpha_max": 0.8,
  "feature_spec": [...]
}
```

### 19.7 깃 워크플로우 (반복 학습 포함)

매번 새 rlog 추가될 때마다:

```
1. 새 rlog를 ~/.cas_train/<car>/rlogs/ 에 복사
2. python tools/cas_train.py --car <car>
   → 자동: 전체 rlog로 처음부터 학습
   → ~/.cas_train/<car>/checkpoints/vN_<날짜>_<시간>.json 저장
   → ~/.cas_train/<car>/history.json 갱신
   → 검증 지표 출력 (이전 버전 대비 개선/악화 비교)
3. 지표 OK면:
   cp ~/.cas_train/<car>/checkpoints/vN_*.json \
      opendbc_repo/opendbc/car/torque_data/cas/<car>.json
4. git add opendbc_repo/.../cas/<car>.json
5. git commit -m "cas: <car> v2, 45h, mean_offset=0.24m (-0.07)"
6. push → 사용자 carrot 업데이트 시 자동 적용
```

NNFF의 `neural_ff_weights.json` 운영과 동일한 운영, 다만 학습 이력 추적이 추가됨.

`history.json`은 깃에 안 올림 (`.gitignore`). 개발자 PC 로컬에만 있음. 사용자에겐 JSON 메타로 충분.

---

## 21. 고점 성능 한계 — 하드유저 시나리오

### 21.1 한 줄

NNFF가 **"있으면 약간 나음"** 정도라면, CAS 고점은 **"있어야 함"** 으로 인식 전환 가능 — 데이터/분포/기법이 받쳐줄 때.

### 21.2 단계별 성능 추정 (이론치, Phase 1+에서 실측 갱신 예정)

| 시나리오 | mean abs offset | 개입 감소 | 체감 |
|---|---|---|---|
| base만 | ~0.40m | 기준 | — |
| NNFF | ~0.30m | -20% | 약간 부드러움 |
| **CAS 현재 안** (20~100h, MLP) | ~0.20m | -40% | 명확히 더 좋음 |
| **CAS 고점 안** (500h+ + 다양성 + 큰 모델) | **~0.10m** | **-60~-70%** | **"한 단계 위"** |
| 이론 한계 | ~0.08m | -75% | lane 인식 자체 노이즈가 한계 |

### 21.3 고점을 끌어올리는 8가지 방법

| # | 방법 | 발동 시점 |
|---|---|---|
| 1 | **모델 용량 단계적 증가** (MLP → 더 큰 MLP → Mini-TCN) | 데이터 200h, 500h, 1000h+ 누적 시 |
| 2 | **입력 신호 추가** (laneLines.prob, position.std, 도로 유형, 날씨 등) | Phase 2+ |
| 3 | **데이터 분포 다양화** (비/눈/야간/터널/캠버 등 의도적 수집) | 가장 중요. 항상. |
| 4 | **하드 네거티브 마이닝** (T2/T3 over-sampling) | 학습 단계 |
| 5 | **멀티태스크 보조 loss** (미래 offset/heading 예측 동시 학습) | Phase 2+ |
| 6 | **앙상블** (3~5개 random seed 모델 평균) | Phase 3+ (옵션) |
| 7 | **PPL preference horizon L 자동 튜닝** | Phase 2+ |
| 8 | **Active Learning** (불확실 구간 우선 수집) | Phase 3+ |

#### 가장 중요한 셋
- **#1 모델 용량**: 데이터가 받쳐주면 작은 MLP는 표현력 한계 도달. JSON 포맷 그대로 두고 레이어만 추가하면 됨.
- **#3 분포 다양화**: 같은 길 1000h ≠ 다양한 길 100h. 후자가 훨씬 좋음. history.json에 분포 통계 자동 출력해서 부족 영역 알림.
- **#5 멀티태스크**: 추가 비용 거의 0인데 학습 신호 ↑. 보조 헤드는 추론 시 안 씀.

### 21.4 데이터 양 vs 성능 곡선 (이론 추정)

```
  mean_offset(m)
  0.40 ┤█ base
       │
  0.30 ┤████ NNFF (~수십h 통합 학습 추정)
       │
  0.25 ┤██████ CAS 20h
  0.20 ┤████████ CAS 100h
  0.15 ┤██████████ CAS 300h (+다양성)
  0.10 ┤████████████ CAS 1000h+ (+모델 용량 ↑ +기법)
  0.08 ┤█████████████ 이론 한계 (lane 인식)
       │
       └──────────────────────────────────────────
       0     20    100   300   1000  10000  hours
```

→ **diminishing returns**가 있지만, 1000h대까지는 명확히 향상.
→ 10000h 이상은 같은 분포면 ROI 거의 0. **분포 다양성**이 그 시점부터 거의 유일한 향상 축.

### 21.5 천장 (saturation) — 정직한 한계

이 위로 못 가는 이유:
1. **운전 모델 lane 인식 정확도** — CAS가 modelV2 출력으로 학습하니 모델 자체 오차가 한계
2. **EPS 물리 한계** — 차량 EPS의 응답 지연/해상도
3. **데이터 다양성 saturation** — 같은 패턴 반복은 0 수렴

→ 이 한계 너머는 driving model 개선이나 차량 EPS 펌웨어 영역. CAS 범위 밖.

### 21.6 하드유저 (jominki354 + 협조자) 시나리오 — 실현 가능성

가정: jominki354 + 협조자 N명 × 1년 = 차종당 누적 1000h+ 가능

실현 가능 그림:
- Phase 1 (~Q3 2026): MLP, ~50h, mean_offset ~0.25m
- Phase 2 (~Q1 2027): +다양성, +멀티태스크, ~200h, mean_offset ~0.18m
- Phase 3 (~Q3 2027): Mini-TCN, 앙상블, ~500h+, mean_offset ~0.13m
- Phase 4+ (계속): 1000h+, ~0.10m 정착

각 단계의 JSON 포맷은 호환 (레이어 추가만). 사용자는 그냥 carrot 업데이트만 받음.

### 21.7 §10 로드맵에 추가 필요

기존 Phase 0~3 외에:

| Phase | 추가 액션 |
|---|---|
| Phase 2 | 멀티태스크 loss, PPL horizon 자동튜닝, 입력 신호 확장 |
| Phase 3 | Mini-TCN, 앙상블, Active Learning, 데이터 다양성 통계 자동화 |
| Phase 4+ | 1000h+ 누적, 분포 다양화 캠페인 |

---

## 22. 사용자 케이스 — 자주 나올 질문 답변

### 22.1 "왼쪽으로 붙는 경향" (좌우 비대칭) 보정되나?

**YES. CAS의 핵심 영역.** 댓글 사용자가 "Yaw 강제 보정"으로 우회한 그 문제가 CAS의 출발점.

메커니즘:
- 입력 `sign(curvature)` + `lateral_offset_now/avg_5s` (§4.1 센터링 신호)
- 직선에서 평균 offset이 한쪽으로 치우치면 그 신호 자체가 학습됨
- 사용자가 살짝 보정한 순간 = T3 최강 신호
- → 모델이 "현재 캠버/얼라인먼트 비대칭"을 자동 인식하고 반대로 보정

기존 carrot의 `PathOffset` (사용자 수동 cm 입력)을 **학습으로 자동화**.

### 22.2 "SCC 안 쓰고 조향만 콤마"인 조건도 학습되나?

**YES.** openpilot은 종방향/횡방향 활성 별도 플래그:
- `controlsState.longActive` (가속/브레이크)
- `controlsState.latActive` (조향) ★ CAS는 이것만 봄

→ SCC 끄고 조향만 켠 상태에서도:
- carState/modelV2/controlsState 평소대로 rlog 기록
- `latActive == True` 구간 골라 학습
- 가속/브레이크는 무관

§6.1 T1~T5 트리아지의 모든 조건은 `latActive` 기준. SCC 무관.

### 22.3 여러 환경/습관 데이터 — 평균인가 분기인가?

**둘 다 일어남.** 입력 신호로 식별 가능하면 분기, 못 하면 평균.

#### 자동 분기되는 차이 (입력으로 식별 가능)

| 차이 | 식별 입력 |
|---|---|
| 저속 vs 고속 | vEgo |
| 직선 vs 코너 | curvature, lat_accel |
| 평지 vs 경사 | roll, pitch |
| 코너 진입 vs 탈출 | lat_jerk, curvature_rate |
| 좌커브 vs 우커브 | sign(curvature) |
| 차선 폭 (입력 추가 시) | laneWidth |

→ 모델이 자동으로 다른 출력 학습. 별도 처리 불필요.

#### 평균화되는 차이 (입력에서 식별 불가)

| 차이 | 결과 |
|---|---|
| 맑음 vs 비 | 평균 (보통 무해) |
| 사용자 A vs B (둘 다 양호) | 양쪽 흉내 평균 |
| 같은 사용자 기분 좋은 날 vs 피곤한 날 | 평균 |
| 낮 vs 밤 | 평균 |

→ 양호 운전끼리의 평균은 보통 무해. 일관된 비대칭이 있다면 그건 학습으로 잡힘.

#### 트리아지가 일관성 보장

위험/이상 운전은 T1~T5 분류에서 자동 제외:
- T1: 양호 (offset 작고 미개입) → 학습
- T3: 사용자 보정 → "이때 보정 필요했다" 신호로
- 제외: 카메라 오류, 비양호 → 학습 미반영

→ **평균이지만 "잘한 운전의 평균"**.

#### 데이터 풀링 vs 단일 사용자

| 시나리오 | 결과 |
|---|---|
| 한 사용자만 데이터 | 그 사람에 매우 잘 맞음 (운전 스타일까지 흉내) |
| 여러 사용자 풀링 | 일반화 ↑, 개인화 ↓ (NNFF 차종 모델 패턴) |
| jominki354 + 협조자 N명 | 균형 잡힘 (다양성 + 잘한 운전 평균) |

#### 향후 확장 (Phase 3+)
입력에 환경 컨텍스트 추가 가능:
- 와이퍼 상태 → 비/맑음 분기
- 헤드라이트/조도 → 낮/밤 분기
- 시간대 → 보조 분기

이러면 평균화가 추가 분기로 전환. 단 입력 차원 증가 비용 vs 효용 trade-off.

---

## 23. NNFF 코드 재검토 — 미비점 보강 (2026-05-19)

[latcontrol_torque.py](selfdrive/controls/lib/latcontrol_torque.py)를 다시 깊이 본 결과, 우리 §4/§5/§6에서 단순화한 부분에 NNFF의 노하우가 많이 있음. 항목별 보강.

### 23.1 ★ PID error 처리 — CAS는 ff에만 영향

**NNFF가 하는 것** ([latcontrol_torque.py:240-256](selfdrive/controls/lib/latcontrol_torque.py#L240-L256)):
```python
torque_from_setpoint   = NN([vEgo, setpoint, jerk_setpoint, roll, ...])
torque_from_measurement = NN([vEgo, measurement, jerk_measurement, roll, ...])
pid_log.error = torque_from_setpoint - torque_from_measurement   # ← PID error도 NN!

# 고횡가속 영역에서 강화
error_blend_factor = np.interp(abs(desired_lateral_accel), [1.0, 2.0], [0.0, 1.0])
if error_blend_factor > 0.0:
    nnff_error_input = [vEgo, setpoint - measurement, ...]
    torque_from_error = NN(nnff_error_input)
    if same_sign and abs(error) < abs(torque_from_error):
        pid_log.error = blend(...)
```

NNFF는 FF만이 아니라 **PID error 항도 NN으로 계산**. 즉 PID 동작 영역까지 NN이 결정.

**CAS의 결정 (§23.1 채택)**:

| 옵션 | 설명 | 채택 |
|---|---|---|
| 1. CAS는 ff에만 잔차 | PID error는 base 그대로 (NNFF면 NNFF error, classical이면 classical error). CAS는 ff_base + α·δ만. | ✅ **채택** |
| 2. CAS도 error에 잔차 | 적극적 보정, 위험성 ↑, 복잡도 ↑ | ❌ |

이유: **단순성 + 안전성**. PID error 항까지 건드리면 안정성 검증 어려움. ff에만 영향이 보수적이고 검증 쉬움.

코드 (개념):
```python
# 1) base 결정 (NNFF on이면 NNFF가, 아니면 classical)
if nnff_enabled:
    pid_log.error = nnff_compute_error(...)  # NNFF의 PID error
    ff_base = nnff_compute_ff(...)
else:
    pid_log.error = classical_compute_error(...)  # base 그대로
    ff_base = classical_compute_ff(...)

# 2) CAS는 ff에만 추가
if cas_enabled:
    delta = cas.compute(features)
    ff = ff_base + alpha * delta
else:
    ff = ff_base

output_torque = pid.update(pid_log.error, feedforward=ff, ...)
```

### 23.2 friction_override 메커니즘 채택

**NNFF 메커니즘** ([interfaces.py:165-167](opendbc_repo/opendbc/car/interfaces.py#L165-L167)):
```python
def check_for_friction_override(self):
    y = self.evaluate([10.0, 0.0, 0.2])     # 작은 friction 입력 테스트
    self.friction_override = (y < 0.1)       # 출력 약하면 friction 학습 부족 인식
```

학습된 NN이 friction 반응이 약하면 자동 감지 → classical friction을 PID error에 더해 보완.

**CAS 채택**:
- CAS의 NN(δ)도 friction 반응이 약할 수 있음
- 학습 후 자동 sanity check
- 약하면 메타에 `friction_override: true` 저장 → 추론 시 base의 friction 항 강화

```json
{
  "validation": {...},
  "friction_override": true   // 자동 판정 결과
}
```

### 23.3 error_blend_factor — 고횡가속 영역 강화

NNFF는 desired_lat_accel > 1m/s² 영역에서 error response를 점점 강화 (코너 진입 시).

**CAS 채택 옵션**:
- α 게이트에 입력 추가: `α_high_accel = clip(|desired_lat_accel| / 2.0, 0, 1)`
- 큰 코너에선 CAS도 적극적 (단, 학습 데이터 분포 신뢰 시)
- 또는 반대로 보수적 (큰 코너에선 base 우선) — Phase 1 실측 후 결정

§5 α 게이트에 옵션 명시:
```
α_final = α_data_confidence × α_physics_sanity × α_user_toggle × α_high_accel
```

### 23.4 lookahead jerk 부호 일치 검증

**NNFF의 트릭** ([latcontrol_torque.py:48-58](selfdrive/controls/lib/latcontrol_torque.py#L48-L58)):
```python
def get_lookahead_value(future_vals, current_val):
  same_sign_vals = [v for v in future_vals if sign(v) == sign(current_val)]
  if len(same_sign_vals) < len(future_vals):  # 부호 바뀜
    return 0.0                                  # 단기 jerk는 무시
  return min(same_sign_vals + [current_val], key=lambda x: abs(x))
```

→ 미래 jerk가 부호 바뀌면 "단기 노이즈"로 보고 입력에서 0으로 처리. 안정성 ↑.

**CAS 채택**: features.py의 jerk 입력 계산에 이 로직 그대로 적용.

### 23.5 adjusted_future_times — 종방향 가속 보정

NNFF ([latcontrol_torque.py:233](selfdrive/controls/lib/latcontrol_torque.py#L233)):
```python
adjusted_future_times = [t + 0.5*CS.aEgo*(t/max(CS.vEgo, 1.0)) for t in self.nn_future_times]
```

가속/감속 중에는 미래 시간을 단순 t로 잡으면 부정확 → aEgo로 보정.

**CAS 채택**: features.py의 미래 시점 인덱스 계산에 동일 적용.

### 23.6 paramsd.angleOffsetDeg — base에 이미 포함됨

paramsd가 추정하는 angleOffsetDeg (직진 시 휠 중립 위치)는 [latcontrol_torque.py:172](selfdrive/controls/lib/latcontrol_torque.py#L172)에서 base에 이미 더해짐:
```python
angle_steers_des += params.angleOffsetDeg
```

CAS의 base = NNFF/classical이므로 angleOffsetDeg는 자동 포함. **CAS가 별도 처리 안 해도 됨**. 단 문서에 명시 필요.

### 23.7 liveDelay.lateralDelay 활용

§16.4에 언급만 했음. 명확히:

| 방식 | 설명 | 채택 |
|---|---|---|
| 입력 벡터에 포함 | features에 `lateralDelay` 명시 추가 | 보조 |
| 미래 시점 계산에 사용 | nn_future_times의 offset에 lateralDelay 반영 (NNFF 패턴) | ✅ 메인 |

NNFF 패턴: `nn_time_offset = CP.steerActuatorDelay + 0.2`. 우리도 동일 + liveDelay로 동적 갱신.

### 23.8 use_steering_angle 분기 — 학습/추론 일관성

NNFF ([latcontrol_torque.py:177-189](selfdrive/controls/lib/latcontrol_torque.py#L177-L189))는 측정 곡률을 두 방식으로 계산:
- `use_steering_angle == True`: `VM.calc_curvature(steeringAngle)` (직접)
- `use_steering_angle == False`: `angularVelocity.z / vEgo` (IMU)

**CAS 결정**:
- 학습 시점에 어느 방식을 썼는지 JSON 메타에 명시
- 추론 시 동일 방식 사용
- 메타 필드: `"use_steering_angle": true|false`

### 23.9 NNFF Lite — CAS와의 관계

NNFF Lite는 NN 모델 없는 차량용 폴백 (classical FF + 확장 friction 입력).

CAS는 그것과 별개 — 모델 없으면 α=0 (NNFF Lite처럼 별도 폴백 로직 없음, base 그대로). 단순.

### 23.10 cereal 디버깅 로그 — pid_log.nnLog 활성화

[latcontrol_torque.py:303-304](selfdrive/controls/lib/latcontrol_torque.py#L303-L304):
```python
#if nn_log is not None:
#  pid_log.nnLog = nn_log
```

주석 처리됨. CAS 디버깅용으로 활성화 가치 있음:
- `pid_log.casLog`: 입력 벡터 + δ + α 기록
- 학습 후 검증/회귀 분석에 핵심
- 로그 사이즈 부담 작음 (벡터 ~20 float + 2 float)

→ Phase 0에서 추가.

### 23.11 lat_active 정확한 정의

학습 데이터 필터링의 핵심. carrot 코드 기준:
- `controlsState.latActive` — 횡제어 실제 작동 중
- `carControl.latActive` — 횡제어 요청 (carControl 메시지)
- `steeringPressed` — 사용자 손 댐 (T3/T4 신호)

CAS T1 양호 구간 조건 (명확히):
```python
T1_condition = (
  msg.controlsState.latActive == True       # 횡제어 작동
  and msg.carState.steeringPressed == False # 사용자 미개입
  and msg.carState.vEgo > 15                # 충분한 속도
  and abs(steer_torque) > 0.02              # 의미 있는 토크
  and abs(lateral_accel) > 1.0              # 의미 있는 횡가속
)
```

torqued의 조건과 동일. 학습 스크립트가 이걸로 자동 라벨링.

### 23.12 미비점 보강 요약 표

| # | 항목 | 영향 절 | 액션 |
|---|---|---|---|
| A | PID error는 base 그대로 | §4.4 | 명시함 (§23.1) |
| B | friction_override 자동 감지 | §6, §19.6 | JSON 메타 필드 추가 |
| C | 고횡가속 α 강화 옵션 | §5 | α_final 공식 갱신 |
| D | lookahead jerk 부호 검증 | features.py | get_lookahead_value 그대로 채택 |
| E | adjusted_future_times | features.py | aEgo 보정 채택 |
| F | roll·cos(pitch) 합성 옵션 | §4.1 | 두 방식 다 가능 (실험 후 결정) |
| G | angleOffsetDeg는 base 포함 | §4.4 | 명시함 |
| H | freeze_integrator는 base 그대로 | §4.4 | 자동 적용 |
| I | lateralDelay 미래 시점 보정 | §4.4 / features.py | NNFF 패턴 채택 |
| J | use_steering_angle 일관성 | JSON 메타 | 메타 필드 추가 |
| K | NNFF Lite vs CAS 폴백 | §9 | 명시함 (CAS는 α=0 폴백) |
| L | casLog 디버깅 cereal | §7.1 / Phase 0 | 활성화 |
| M | lat_active 정의 명확화 | §6.1 | 조건 코드 명시 |

---

_상세 논의·웹 조사·참고문헌: [cnlt_design.md](cnlt_design.md)_

## Sources (§18 추가 조사 + §19 포맷 결정)

- [Safetensors, CKPT, ONNX, GGUF, and Other Key AI Model Formats (2026)](https://nednex.com/en/what-are-safetensors/)
- [HuggingFace safetensors GitHub](https://github.com/huggingface/safetensors)

- [Predictive Preference Learning from Human Interventions (PPL)](https://arxiv.org/pdf/2510.01545)
- [Improving Behavioural Cloning with Positive Unlabeled Learning (BD)](https://arxiv.org/pdf/2301.11734)
- [Reset It and Forget It: Relearning Last-Layer Weights](https://arxiv.org/pdf/2310.07996)
- [Few-shot model-based adaptation in noisy conditions (KF-NN)](https://arxiv.org/pdf/2010.08397)
- [Intelligent vehicle trajectory tracking control based on physics-informed neural network dynamics model (2025)](https://journals.sagepub.com/doi/abs/10.1177/09544070241244858)
- [A Lateral Control Based on Physics Informed Neural Networks for Autonomous Vehicles (2024)](https://link.springer.com/chapter/10.1007/978-3-031-70392-8_115)
- [Integrated Design and Validation of a Robust Lane Centering Controller (SAE 2026-01-0037)](https://saemobilus.sae.org/papers/integrated-design-validation-a-robust-lane-centering-controller-automated-driving-2026-01-0037)
- [HG-DAgger: Interactive Imitation Learning with Human Experts](https://www.researchgate.net/publication/335140291_HG-DAgger_Interactive_Imitation_Learning_with_Human_Experts)
- [Robot-Gated Interactive Imitation Learning with Adaptive Intervention Mechanism](https://arxiv.org/html/2506.09176v1)
- [Neural L1 Adaptive Control of Vehicle Lateral Dynamics](https://arxiv.org/pdf/2405.16358)
- [OpenLKA dataset](https://arxiv.org/html/2505.09092v1)
