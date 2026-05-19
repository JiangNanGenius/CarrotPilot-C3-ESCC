# Carrot Neural Lateral Tuner (CNLT) — 설계 논의 문서

> 이 문서는 사용자(jominki354)와 Claude가 carrot 포크용 신경망 기반 조향 튜너를 설계하기 위해 진행하는 대화/결정 기록이다. 결정 사항은 위쪽, 열린 논의는 아래쪽에 둔다.

---

## 0. 문서 목적

- NNFF의 장점을 가져오면서, 2026년 5월 기준 더 나은 기법으로 carrot만의 조향 학습 시스템을 만든다.
- **토크 차량과 앵글 차량 모두**를 다룬다 (NNFF가 못 한 영역).
- rlog로 학습이 쉽고, openpilot에 적용도 쉬워야 한다.
- 센터링/저속/비대칭 등 조향 전반의 품질 향상을 목표로 한다.

---

## 1. 현황 파악 (2026-05-19 기준)

### 1.1 carrot에 이미 있는 것

- **NNFF 통합 완료**: [latcontrol_torque.py:86-131](../../../../selfdrive/controls/lib/latcontrol_torque.py#L86-L131). twilsonco의 `neural_ff_weights.json` 사용. **토크 차량 전용.**
- **NNFF Lite**: 모델 없는 차량용 폴백, friction 입력만 확장.
- **Classical Auto-Tuner**: [carrot_learning.py](../../../../selfdrive/carrot/carrot_learning.py) (593 LOC). `latAccelFactor`, `friction` 등 스칼라 파라미터 온라인 추정. NN 아님.
- **저속 NN 보정**: `LOW_SPEED_Y_NN = [12, 3, 1, 0]` — NNFF용 별도 저속 게인.

### 1.2 비어있는 곳

- **LatControlAngle**: [latcontrol_angle.py](../../../../selfdrive/controls/lib/latcontrol_angle.py) 30줄짜리 깡통. VM 변환 외 학습 요소 0.
- **앵글 차량의 EPS 응답 보정** (데드존, hysteresis, 지연) 자동화 없음.

---

## 2. NNFF의 한계 분석

| 항목 | NNFF | 개선 가능성 |
|---|---|---|
| 모델 | MLP (고정 윈도우) | 시계열 모델 (TCN/GRU)로 응답 추세 학습 |
| 대상 | 토크 차량만 | 앵글 차량까지 확장 |
| 학습 신호 | 사람 운전 모방 (BC) | 모방 + 응답 추적 잔차 (하이브리드) |
| 개체차 | 차종별 모델만 존재 | 차량 개체별 last-layer 온라인 적응 |
| 안전성 | NN 통째로 신뢰 | residual + 신뢰도 게이트 α |

---

## 3. 2026년 기준 채택할 기법

| 기법 | 채택 | 이유 |
|---|---|---|
| **Residual learning** (physics + NN δ) | ✅ | NN 실패 시 base가 살림. 이식 쉬움. |
| **TCN/1D-Conv 백본** | ✅ | MLP보다 시계열 강함. Transformer보다 가벼움. |
| **Online last-layer adaptation** | ✅ | 차량 개체차 흡수. Auto-Tuner와 결합 자연스러움. |
| **Inverse dynamics (system ID)** | ✅ | 명령→응답 함수 명시 학습. **앵글 차량의 핵심.** |
| Diffusion Policy / Implicit BC | ❌ | 100Hz 실시간 추론 부적합. |
| Transformer encoder | ❌ (보류) | TCN으로 충분. |
| Online RL (TD3/SAC) | ❌ | 차에서 보상 신호 위험. |

---

## 4. 아키텍처

### 4.0 원칙 (2026-05-19 사용자 확정)

> **토크와 앵글은 내부적으로 완전히 분리된 모델/코드 경로로 다룬다.** 둘 다 지원하되 하나의 통합 모델로 묶지 않는다. 사용자는 자기 차에 맞는 JSON 하나만 받아 넣는다.

이유:
- 출력 단위가 다름 (Nm vs deg). 같은 모델에 묶을 이유 없음.
- 토크 차량과 앵글 차량은 학습 신호(타겟 y)의 의미도 다름.
- 분리하면 코드도 단순 — `latcontrol_torque.py`는 토크용 JSON만, `latcontrol_angle.py`는 앵글용 JSON만 로드.
- 차량 종류가 바뀔 가능성 0 → 런타임에 어느 모델 쓸지 분기할 필요 없음.

### 4.1 모델 구조 (토크용 / 앵글용 둘 다 동일 골격)

```
입력 벡터 x (≈ 18~22차원, MLP+context):
  [vEgo, aEgo,
   desired_lat_accel(t=0, +0.3, +0.6, +1.0, +1.5),     # 미래 plan 5개
   measured_lat_accel,
   lateral_jerk_lookahead,
   roll(t=0, +0.5, +1.0),                              # roll 시퀀스
   pitch,
   steeringAngle, steeringRate,
   sign(desired_curvature),                            # 좌우 비대칭 학습용
   (필요시 과거 desired_lat_accel 2~3개)]

       ↓
  MLP (NNFF의 FluxModel 포맷 그대로):
    Linear(N → 32) → tanh
    Linear(32 → 16) → tanh
    Linear(16 → 1)         ← residual δ

       ↓
  토크 차량용 JSON  →  output_torque = base_FF(lat_accel, friction) + α · δ
  앵글 차량용 JSON  →  output_angle  = VM_angle                   + α · δ
```

- **α ∈ [0,1]**: 신뢰도 게이트. 데이터 부족/이상 입력 감지 시 0으로 떨어져 기존 동작.
- **백본은 MLP**: NNFF와 동일 구조 → `FluxModel` 그대로 재사용 가능. Mini-TCN은 효과 부족 시 옵션.

### 4.2 모델 크기 목표

- 가중치 ≤ 50~100KB **JSON 파일** (NNFF 포맷 확장)
- 추론 ≤ 1ms / step (100Hz), **순수 numpy**
- 백본 후보 (단순한 순):
  1. **MLP + 컨텍스트 윈도우** (NNFF와 동일 구조, 입력만 확장) — 가장 쉬움
  2. **Mini-TCN** (causal 1D conv 2~3층, ch 16) — numpy로 30줄 가능
  3. GRU — hidden state 관리 부담, 권장 안 함
- 추천: **1번부터 시작, 부족하면 2번으로**. NNFF가 1번 계열이라 호환성/이식성 최고.

### 4.3 입력 신호 비교: NNFF vs CNLT

| 신호 | NNFF | CNLT |
|---|---|---|
| vEgo | ✓ | ✓ |
| desired/measured lat_accel | ✓ | ✓ |
| lat_jerk (look-ahead) | ✓ | ✓ |
| roll (과거/미래) | ✓ (3+4) | ✓ (간소화 1+2) |
| pitch | (roll에 합성) | ✓ (독립) |
| 미래 plan lat_accel | ✓ (4점) | ✓ (5점) |
| 과거 desired lat_accel | ✓ (3점) | (옵션) |
| **steeringAngle / Rate** | ✗ | **✓** |
| **sign(curvature)** | ✗ | **✓ (좌우 비대칭)** |
| **aEgo** | ✗ (미래시간 보정에만) | **✓ (직접 입력)** |

---

## 5. 학습 파이프라인

> ⚠️ **2026-05-19 수정**: 디바이스 추론은 NNFF처럼 **순수 numpy + JSON 가중치**로 간다. onnx/torch/tinygrad **사용 안 함**. 사용자 지적 반영.

```
[rlog 파일들]
    ↓ extract (carrot/learning/extract.py)
[parquet/npz]
  carState, modelV2, liveCalibration, controlsState, lateralPlan
    ↓ align (100Hz) + featurize
[(X_seq, y) 페어]
    ↓ PyTorch 학습 (PC, GPU 없어도 됨)
[JSON export] ≤ 50~100KB, NNFF의 FluxModel 포맷 확장
    ↓ 배포: 깃 푸시 or params/d/CNLTWeights에 hot-swap
[디바이스에서 순수 numpy 추론]  ← 외부 런타임 의존성 0
```

### 5.0 NNFF의 추론 코드를 본받아야 하는 이유

NNFF의 [FluxModel](../../../../opendbc_repo/opendbc/car/interfaces.py#L98) 실체:
- JSON: `{layers: [{Wxx_W, Wxx_b, activation}, ...], input_mean, input_std}`
- forward: `x = activation(x.dot(W) + b)` 반복, **60줄**
- 의존성: `numpy`, `json`만

CNLT도 동일한 정신:
- 가중치 = JSON
- 런타임 = numpy (TCN의 1D causal conv도 numpy 30줄로 가능)
- 새 활성화 함수가 필요하면 FluxModel처럼 클래스 메서드에 이름 매핑 추가

### 5.1 타겟(y) 선택 — **하이브리드(C) 잠정 채택**

- (A) 사람 운전 모방: y = 측정 steerTorque/Angle
- (B) 응답 역모델: y = 명령 → 실제 lat_accel의 역함수
- **(C) 하이브리드: A + 모델 예측 lat_accel과의 잔차 페널티** ← 추천

C가 좋은 이유: 사람 흉내(부드러움)와 추적 오차 최소화(정확성)를 동시에 가져감. NNFF는 사실상 A.

---

## 6. Auto-Tuner와의 통합

```
Cold start  →  Classical Auto-Tuner (현재 carrot_learning.py)
                    ↓ 데이터 누적
Warm        →  Hybrid: classical 파라미터 + NN δ (α 점진 증가)
Mature      →  Neural residual 주도, classical은 안전망
```

UI 토글 4단계: `Off` / `Classical (현재)` / `Hybrid` / `Neural`.

---

## 7. NN 밖에서도 다듬을 것

- `angleOffsetDeg` 추정 (paramsd 기존 동작 검토)
- 좌우 비대칭 friction (입력에 `sign(curvature)` 포함하면 자연 학습)
- 저속 영역 통일 (`LOW_SPEED_Y` vs `LOW_SPEED_Y_NN`)
- `steerActuatorDelay` 자동 추정 (cross-correlation)

---

## 8. 운영 측면

- 가중치: **JSON 파일** 하나. NNFF처럼 `opendbc_repo/opendbc/car/torque_data/`에 둘 수도 있고, 차량별로 `params/d/`에 둘 수도 있음.
- 배포: 깃 푸시 or params hot-swap (재시작 없이).
- 학습 결과 공유 (선택): `(차종, EPS firmware 해시) → .json` 매핑 — NNFF가 이미 쓰는 방식 그대로.
- 사용자 단독 모드: PC에서 자기 rlog로 학습 → JSON 한 개 받음 → 디바이스에 복사.

---

## 9. 열린 논의

| # | 질문 | Claude 추천 | 사용자 답 |
|---|---|---|---|
| Q1 | 앵글 차량 우선순위 — NNFF 없는 앵글 차부터 먼저? | **앵글 우선** (차별화 큼) | _대기_ |
| Q2 | 학습 위치 — PC 사용자 직접 / 디바이스 온라인 / 둘 다? | ~~둘 다~~ | ✅ **확정: off-device 학습** (NNFF처럼 PC/서버). 디바이스는 추론만. |
| Q3 | 타겟(y) — A/B/C? | **C (하이브리드)** | _대기_ |
| Q4 | 백본 — TCN / GRU / MLP+context? | **MLP+context 우선, 부족하면 Mini-TCN** (간편성 우선, NNFF 호환) | _대기_ |

### 9.1 Q2 확정의 함의 (2026-05-19, 재확정)

- **기기는 추론과 로그 수집만**. 학습 코드 0줄. 그래디언트 계산 0회.
- 학습 파이프라인 = **rlog → 사용자 PC → JSON → 기기 복붙**. 완전 단방향.
- "차량 개체별 미세조정"은 사용자가 자기 rlog로 자기 PC에서 last-layer만 재학습하는 방식 (§11.3).
- 안전성: 기기에는 사용자가 검증하고 넣은 JSON만 존재. 학습 중 모델이 망가져서 즉시 차로 흘러갈 경로 없음.

---

## 11. 관련 연구 조사 (2026-05-19)

### 11.1 핵심 reference 4편

#### [1] Residual Policy Learning for Racing (Trumpp et al., arXiv:2302.07035)
- **결론**: classical 컨트롤러 + 학습된 residual controller가 12개 트랙 평균 **랩타임 4.55% 단축**. 미지 트랙에서도 이득.
- **의미**: 우리 §4.1 "physics base + α·NN_δ" 구조의 정량적 근거. residual 방식이 안전성-성능 트레이드오프에서 우월하다는 게 데이터로 검증됨.
- **적용**: α 게이트 신뢰 가능. base controller만으로도 안전이 보장됨.

#### [2] EPS NN System Identification (IEEE 10496684, 2024)
- **결론**: ANN+backprop으로 EPS 비선형 동역학을 **99.6% 정확도** 식별. Levenberg-Marquardt로 컨트롤러까지.
- **의미**: 우리가 §5.1에서 "응답 역모델(B)"이라 부른 접근의 가능성 입증. 특히 **앵글 차량**의 EPS 응답(데드존, hysteresis, 지연) 학습이 실증적으로 됨.
- **적용**: 앵글 차량용 head는 명령각도→실제차량응답 역함수를 학습하는 것으로 구체화.

#### [3] Physics-Guided NN for Feedforward Control (arXiv:2204.00431)
- **결론**: 물리 모델 + NN 잔차 형태의 PGNN으로 inverse dynamics 식별. 정확하고 데이터 효율적.
- **의미**: pure black-box NN보다 **물리 prior가 들어간 NN**이 일반화/안전성 모두 우수. carrot의 `VehicleModel` 위에 NN을 얹는 우리 구조와 일치.

#### [4] Online Adaptation of Vehicle Dynamics via Meta-Learning (arXiv:2409.14950)
- **결론**: **Bayesian last-layer meta-learning** + **Kalman filter**로 온라인 적응. 오프라인은 basis function/Kalman 파라미터를 메타학습, 온라인은 last-layer weight를 KF로 업데이트.
- **의미**: Q2를 off-device 학습으로 확정했지만, **last-layer만 차량별로 PC에서 빠르게 재학습**하는 방식의 이론적 토대. 같은 backbone에 차량별 마지막 레이어만 갈아끼우는 구조가 정당화됨.
- **적용**: 우리 모델을 `frozen_backbone(공통) + per-car_head(개체별)`로 분리. NNFF의 "차량별 .json"보다 효율적.

### 11.2 보조 reference

- **TCN for lateral dynamics** (Sage 2025): TCN이 lateral position/steering angle 시계열 예측에서 CNN/LSTM 대비 우수. 우리 백본 선택(Q4)의 근거.
- **Physics-informed TCN for lane change** (Sage 2025): 물리 + TCN 결합 가능성 확인.
- **Data-driven feedforward for nonlinear systems** (arXiv:2303.11197): control-oriented system ID 일반론.

### 11.3 위 연구가 §3 표에 미친 갱신

| 기법 | 이전 채택 | 갱신 후 |
|---|---|---|
| Residual learning | ✅ | ✅ (강화: [1] 정량 근거) |
| TCN 백본 | ✅ | ✅ (강화: [Sage 2025]) |
| Online last-layer adaptation | ✅ (디바이스) | 🔄 **수정: PC에서 차량별 last-layer만 재학습**. 디바이스 온라인 학습 제거 (Q2 결정). |
| Inverse dynamics (system ID) | ✅ | ✅ (강화: [2] 99.6% 정확도) |
| **Physics-guided NN (PGNN)** | (언급 없음) | ✅ **신규 채택**: `VehicleModel` 기반 prior + NN 잔차로 구성. |

### 11.4 1차 비교 — 기존 NNFF vs CNLT (갱신본)

| 항목 | NNFF (twilsonco) | CNLT (안) |
|---|---|---|
| 백본 | MLP, 고정 윈도우 | TCN, 시계열 |
| Physics prior | 없음 (pure FF 대체) | PGNN: VehicleModel 위에 residual |
| 토크/앵글 | 토크만 | 공통 인코더 + 분기 헤드 (앵글 포함) |
| 차량별 파라미터 | 통째로 .json | frozen backbone + per-car last-layer |
| 학습 신호 | 사람 모방 (BC) | 모방 + 추적 잔차 (C-하이브리드) |
| 안전 게이트 | 없음 (전체 사용) | α ∈ [0,1] 신뢰도 게이트 |
| 학습 위치 | 오프라인 (PC/Colab) | 동일 (Q2 확정) |
| 적응성 | 모델 새로 학습해야 함 | last-layer만 갈아끼움 (가벼움) |
| **추론 런타임** | **순수 numpy, 외부 의존성 0** | **동일 (NNFF 정신 계승)** |
| **가중치 포맷** | **JSON** | **동일 — FluxModel 포맷 확장** |

---

## 10. 대화 로그

### 2026-05-19

**사용자**: nnff 같은 조향튜닝 만들고 싶다. 토크/앵글 둘 다, 2026년 더 좋은 방식 있으면, carrot만의 새로움, rlog 학습 쉽게, 센터링/조향 전반, 적용 쉽게.

**Claude**: 현황 파악 → NNFF는 carrot에 이미 통합됨, 앵글은 비어있음. 위 1~9절 초안 제시. Q1~Q4 답변 요청.

**사용자**: 문서 하나 만들어서 대화를 거기서 계속하자.

**Claude**: 이 문서(`cnlt_design.md`) 생성.

**사용자**: (1) 학습은 NNFF처럼 로그로 별도 시스템/내 컴퓨터/서버에서 학습이 맞다. (2) 도움될 논문/자료를 웹에서 더 찾아봐라.

**Claude**: Q2 = off-device 학습으로 확정 (§9.1). 웹 조사 6개 주제 병렬 검색, 핵심 reference 4편 확보:
- [1] Trumpp 2302.07035: residual policy 검증 (랩타임 -4.55%)
- [2] IEEE 10496684: EPS ANN system ID 99.6% 정확도
- [3] arXiv 2204.00431: Physics-guided NN feedforward
- [4] arXiv 2409.14950: Bayesian last-layer meta-learning + KF

§11에 정리. §3 표 갱신: **PGNN 신규 채택**, 디바이스 온라인 학습 제거, last-layer 재학습은 PC에서.

**사용자**: "onnx 이런 거 아니고 nnff처럼 간편하게 적용해야 하는 거 아냐? onnx로 한다는 거 아니지?"

**Claude**: 사용자 지적 맞음. NNFF 실체 확인:
- 가중치 = JSON 파일 (`neural_ff_weights.json`)
- 추론 = 60줄짜리 `FluxModel` 클래스, **순수 numpy**
- 외부 런타임 의존성 0

§5에 5.0절 추가, §4.2/§8/§11.4 갱신: **onnx/torch/tinygrad 사용 안 함**. JSON + numpy로 NNFF 정신 계승. Q4도 갱신: **MLP+컨텍스트 우선** (NNFF 호환), 필요하면 mini-TCN.

**사용자**: "기기에선 절대 학습 안 함, 그냥 로그만 쌓고 주면 되는 식임. 그럼 어떤 구조나 그런 걸 하게 할 거야? NNFF와 차이/특징은?"

**Claude**: §9.1 재확정(기기는 추론+로그만, 학습 코드 0줄). §4를 §4.0/4.1/4.3로 재구성:
- 4.0 원칙: 토크/앵글 **내부적으로 완전 분리** (사용자 추가 지시 반영)
- 4.1 모델 구조: 토크용/앵글용 같은 골격, JSON만 다름
- 4.3 입력 신호 NNFF 대비표

§12에 NNFF vs CNLT 비교 요약, §13에 데이터 수집 흐름.

---

_(다음 응답부터는 이 문서를 갱신하며 진행)_

## 12. NNFF vs CNLT — 핵심 차이/특징 요약

### 12.1 한 줄 요약
- **NNFF** = 토크 차량 한정 + FF 전체를 NN으로 대체 + 입력 비교적 단순
- **CNLT** = 토크/앵글 둘 다 + 물리 base + α·NN 잔차 + 입력 확장 + 좌우비대칭/저속 강화

### 12.2 비교표 (최종)

| 항목 | NNFF (twilsonco) | CNLT (carrot) |
|---|---|---|
| **대상 차량** | 토크 차량만 | 토크 + 앵글 (코드 경로 분리) |
| **출력 의미** | torque 절대값 (FF 전체 대체) | residual δ (base에 더해짐) |
| **base 컨트롤러** | 없음 (NN이 100% 결정) | classical FF / VM_angle 유지 |
| **안전 게이트** | 없음 | α ∈ [0,1] — 신뢰도 낮으면 0 |
| **고장 모드** | NN 망가지면 차도 망가짐 | NN 망가져도 base가 살림 |
| **입력 특징** | lataccel, jerk, roll, vEgo + 시퀀스 | + steeringAngle/Rate, sign(curv), aEgo, pitch |
| **좌우 비대칭** | 데이터로만 학습 | sign(curvature) 명시 입력 |
| **저속 영역** | 별도 LOW_SPEED_Y_NN 게인 보정 | 입력에 vEgo + aEgo 들어가 자연 학습 |
| **모델 백본** | MLP 4층, 고정 입력 | MLP + 컨텍스트 (NNFF 호환), 필요시 mini-TCN |
| **차량별 모델** | 차종별 전체 .json | 동일 (단순함 유지) |
| **가중치 포맷** | JSON | JSON (FluxModel 포맷 확장) |
| **추론 런타임** | 순수 numpy | 순수 numpy (외부 의존성 0) |
| **학습 위치** | 사용자 PC (Colab 등) | 사용자 PC |
| **기기 학습 코드** | 없음 | 없음 (확정) |
| **기기 역할** | 추론만 | 추론 + 로그 수집 |
| **데이터 수집** | 사용자가 알아서 | carrot UI 토글로 자동 마킹 |

### 12.3 CNLT만의 차별점 5가지

1. **앵글 차량 지원** — NNFF가 못 한 영역. EPS 응답(데드존, hysteresis, 지연)을 학습.
2. **Residual + α 게이트** — base가 살아 있어 안전성↑. 학습이 부족해도 최악은 기존 동작.
3. **좌우 비대칭 명시** — `sign(curvature)` 입력으로 캠버/얼라인먼트 영향을 학습.
4. **수집 표준화** — carrot에서 학습용 로그를 자동으로 라벨링/추출. 사용자가 "어떤 로그가 학습에 필요한지" 고민 안 해도 됨.
5. **차량 개체 적응** — 같은 차종이라도 PC에서 자기 rlog로 last-layer만 빠르게 재학습 가능 (백본 freeze).

### 12.4 NNFF에서 의도적으로 가져온 것

- JSON 가중치 + numpy 추론 (FluxModel 그대로 활용)
- 차종별 모델 매핑 방식 (`get_nn_model_path`)
- look-ahead lateral jerk 입력
- EPS firmware별 모델 구분 (`neural_ff_weights` 키 컨벤션)

---

## 13. 데이터 수집 워크플로우

```
[기기 측]
  운전 → carState/modelV2/controlsState/liveCalibration/lateralPlan
       → rlog (이미 평소대로 쌓이고 있음)
  추가: carrot UI 토글 "Lateral 학습 데이터 마킹" (선택)
       → 양호 구간에 플래그 (직선/완만 코너, 사용자 미개입, 가속도 적당)

[사용자 PC로 이동]
  USB or comma connect → rlog 파일들 PC로 복사

[PC에서 학습]
  $ python tools/carrot_learn_lateral.py \
      --rlogs /path/to/rlogs --car HYUNDAI_IONIQ_5 --eps_fw <hash>
  → 자동:
    - rlog 파싱, 100Hz align
    - 양호 구간 필터 (사용자 개입 제외, vEgo > 5 등)
    - 토크/앵글 자동 감지
    - PyTorch 학습 (CPU로도 5~30분)
    - cnlt_<car>_<eps>.json 생성

[기기로 다시]
  JSON을 opendbc_repo/.../torque_data/ or params/d/CNLTWeights에 복사
  재시작 → 끝
```

### 13.1 기기에 추가할 코드 (학습 아님, 수집 보조)

- carrot UI에 토글 1개: "Lateral 학습 데이터 수집 모드"
- `selfdrive/carrot/lateral_data_marker.py` (가벼움, 100줄 이내):
  - 매 프레임 양호 여부 판단 (사용자 미개입, 정상 ranges, 카메라 정상)
  - 양호하면 별도 cereal 필드 또는 별도 로그 토픽에 마크
- **학습 그 자체는 0줄**

---

## Sources

- [Residual Policy Learning for Vehicle Control of Autonomous Racing Cars (Trumpp et al.)](https://arxiv.org/pdf/2302.07035)
- [Design of EPS System Identification and Control for Autonomous Vehicles Based on ANN (IEEE)](https://ieeexplore.ieee.org/document/10496684/)
- [Physics-guided neural networks for feedforward control](https://arxiv.org/pdf/2204.00431)
- [Online Adaptation of Learned Vehicle Dynamics Model with Meta-Learning Approach](https://arxiv.org/pdf/2409.14950)
- [Meta-Learning Online Dynamics Model Adaptation in Off-Road Autonomous Driving](https://arxiv.org/abs/2504.16923)
- [Data-driven feedforward control design for nonlinear systems](https://arxiv.org/pdf/2303.11197)
- [Physics-informed TCN model for vehicle lane-changing trajectory prediction](https://journals.sagepub.com/doi/10.1177/09544070251387176)
- [twilsonco/openpilot (NNFF reference)](https://github.com/twilsonco/openpilot)
- [FrogPilot Wiki — Controls](https://frogpilot.wiki.gg/wiki/Controls)
- [sunnypilot — CommaGuide](https://commaguide.com/sunnypilot-features-and-updates)
