# CAS Independent Migration Plan

> 목적: 기존 조향 NN 구현에서 검증된 운영 장점을 CAS로 흡수하되, CAS의 코드/JSON/로그/사용자 UX는 독립 시스템으로 유지한다.
> 이 문서는 `cas_design.md`, `cas_roadmap.md`, `cas_handoff_20260520.md`, `cnlt_design.md`, `cas_conversation.md`, `cas_training_setup.md`를 읽은 뒤 정리한 마이그레이션 계획이다.

---

## 1. 결론

CAS는 다른 조향 NN의 하위 기능이나 호환 레이어가 아니다.

CAS가 가져올 것은 이름이나 상태가 아니라 다음 네 가지 운영 원리다.

1. 차량/EPS 단위의 정밀한 모델 선택
2. JSON + numpy 기반의 가벼운 추론
3. 과거/미래 조향 문맥을 쓰는 입력 설계
4. 모델 실패 시 base controller로 돌아가는 보수적 운영

CAS에 남길 정체성은 다음이다.

1. `base + alpha * residual` 구조
2. 차선 중앙 유지와 쏠림 보정을 목표로 하는 학습
3. 토크/앵글 차량 모두 지원
4. `alpha` gate로 분포 밖 입력, 속도 범위 밖, 운전자 개입을 약화/차단
5. CAS weight/log에는 CAS 독립 metadata만 기록

---

## 2. 이름/의존성 원칙

CAS 파일에는 특정 외부 조향 NN 이름을 metadata로 저장하지 않는다.

금지:

```json
{
  "nnff": true,
  "nnff_model_name": "...",
  "base_ff": "nnff",
  "nnff_lite": false
}
```

허용:

```json
{
  "format_version": 2,
  "model_type": "cas_torque",
  "car": "HYUNDAI_CASPER_EV",
  "car_names": ["HYUNDAI_CASPER_EV", "Hyundai Casper EV 2024"],
  "eps_firmware_hash": "short_hash",
  "feature_schema": "cas_v2",
  "target_kind": "residual_torque",
  "control_mode": "torque",
  "alpha_max": 0.5
}
```

의미:

- `car_names`: `CarName`/`CarSelected3` 계열 표시명을 담는 CAS 차량 매칭 키
- `eps_firmware_hash`: EPS 펌웨어별 응답 차이를 구분하는 키
- `feature_schema`: 입력 벡터 의미와 순서의 버전
- `target_kind`: 모델 출력이 무엇을 뜻하는지
- `control_mode`: 토크용/앵글용 분리

---

## 3. 현재 문서에서 정리할 표현

기존 문서에는 초기 설계 흔적 때문에 다음 표현이 많다.

| 기존 표현 | 권장 표현 |
|---|---|
| NNFF 패턴 그대로 | JSON/numpy 정적 모델 운영 |
| FluxModel 확장 | CASModel JSON MLP 로더 |
| NNFF 노하우 반영 | 기존 실전 구현에서 확인된 안정화 기법을 CAS식으로 적용 |
| NNFF on/off 일관성 | 학습 당시 base controller 조건 일관성 |
| NNFF 미지원 차량 | 기존 학습형 FF가 없는 차량 |
| NNFF + CAS | base controller + CAS residual |

문서에서는 비교를 위해 외부 구현 이름을 언급할 수 있지만, 구현 metadata와 runtime log에서는 CAS 독립 용어만 사용한다.

---

## 4. 가져올 기능과 CAS식 변환

### 4.1 차량/EPS 모델 매칭

현재 상태:

- `CASModel`은 v2 기준으로 `car_names`, `eps_firmware_hash`, `feature_schema`를 읽는다.
- `CASRuntime.load_model()`은 fingerprint 기반 매칭을 사용하지 않고, `CarName`/`CarSelected3`와 `eps_firmware_hash`를 사용한다.
- 새 v2 weight는 `feature_schema`가 맞을 때만 로드된다.

개선:

1. runtime에서 현재 차량 후보 이름을 만든다.
   - `CarName`
   - `CarSelected3` 또는 UI 표시명 계열 값
2. weight의 `car`/파일명 또는 v2의 `car_names`와 정규화 비교한다.
3. EPS firmware hash가 둘 다 있으면 exact match를 우선한다.
4. EPS hash mismatch는 alpha 제한 또는 모델 비활성으로 처리한다.

권장 정책:

| 매칭 상태 | 동작 |
|---|---|
| car exact + eps exact | 정상 alpha |
| car exact + weight eps empty | fallback 허용, 필요시 alpha 70~100% |
| car exact + runtime eps unknown | fallback 허용, 로그에 unknown |
| car exact + eps mismatch | alpha 제한 또는 CAS off |
| car mismatch | CAS off |

CAS 장점:

- 같은 차종 안에서도 EPS 펌웨어 차이로 다른 조향 응답을 안전하게 분리한다.
- 잘못된 모델이 로드되는 위험을 줄인다.

---

### 4.2 JSON + numpy 추론 유지

현재 상태:

- `selfdrive/carrot/cas/model.py`의 `CASModel`은 이미 JSON MLP + numpy 추론 구조다.
- `tools/cas/export_json.py`가 weight JSON을 만든다.
- device에는 torch/onnx/tinygrad 의존성이 없다.

개선:

1. `format_version`을 2로 올릴 때도 backward compatibility 유지
2. layer type은 우선 `linear`만 유지
3. Mini-TCN은 실측 필요성이 생길 때 별도 `format_version`에서 추가
4. output clip, input z-score, speed range gate는 metadata 기반으로 유지

CAS 장점:

- 작은 모델을 git diff로 추적할 수 있다.
- 실패 시 로딩 실패 또는 alpha 0으로 base controller가 그대로 동작한다.

---

### 4.3 입력 특징 강화

이미 반영된 항목:

- `lateralJerkLookahead`
- `roll0/roll05/roll10`
- `pitch`
- `aEgo`
- `signDesiredCurvature`
- `steeringAngleDeg`, `steeringRateDeg`
- `lateralOffsetNow`, `lateralOffsetAvg5s`
- 과거 desired lateral accel
- `lateralDelay`와 `aEgo`를 이용한 미래 시점 보정
- jerk 부호 변경 시 0 처리

추가 검토:

1. 학습/런타임 sample rate 시간축 일치
   - 현재 runtime은 100Hz deque, training은 `sample_stride=5`가 기본이라 `lateralOffsetAvg5s`, past accel의 실제 시간 길이가 달라질 수 있다.
   - `CASFeatureState`를 frame count가 아니라 timestamp 기반 buffer로 바꾸는 것이 좋다.
2. `lateral_delay_at_train` 자동 평균 기록
3. feature schema version 고정
   - 예: `"feature_schema": "cas_v2_20d"`
4. feature mismatch 시 load fail 또는 alpha 0

CAS 장점:

- 단순 feedforward 예측이 아니라 쏠림, 차선 중앙 offset, 좌우 비대칭까지 직접 학습한다.

---

### 4.4 friction 보완

현재 상태:

- JSON에 `friction_override` 필드는 있다.
- 기본값은 false이고 자동 판정은 아직 없다.

개선:

1. 학습 완료 후 모델 sanity check로 friction 반응을 확인한다.
2. 반응이 약하면 CAS metadata에 독립 용어로 기록한다.

권장 이름:

```json
{
  "friction_compensation_required": true
}
```

기존 `friction_override`는 backward compatible로 읽되, 새 문서/코드에서는 CAS 독립 이름을 우선한다.

CAS 적용 방식:

- CAS residual 자체가 friction 전체를 대체하지 않는다.
- base controller의 friction 처리는 그대로 두고, CAS는 residual만 추가한다.
- 필요하면 alpha gate나 validation warning에만 사용한다.

---

### 4.5 고횡가속 영역 처리

현재 문서에는 큰 코너에서 적극적으로 할지 보수적으로 할지 옵션이 남아 있다.

권장:

1. Phase 1/2에서는 큰 코너에서 alpha를 무조건 키우지 않는다.
2. 학습 분포 안에서만 alpha가 살아남도록 z-score gate와 speed gate를 우선한다.
3. validation에서 고횡가속 bucket 성능이 확인되면 `"alpha_profile": "v2"`로 분리한다.

CAS 장점:

- 큰 코너에서 성능을 노리되, 검증 전에는 base controller 우선 원칙을 유지한다.

---

### 4.6 PID error는 건드리지 않기

CAS의 현재 결정은 옳다.

CAS는 FF/residual에만 영향을 준다.

```text
final = base_controller_output + alpha * cas_delta
```

PID error, integrator freeze, angle offset, base friction은 기존 lateral controller의 책임으로 둔다.

CAS 장점:

- 검증 범위가 작다.
- alpha 0이면 기존 제어와 동일하다는 안전 불변식이 유지된다.

---

### 4.7 로그와 UI

현재 상태:

- `CASModelName` param으로 UI에 `,CAS` 표시 가능
- `casLog`는 feature + extras를 기록
- `extras[-10]`의 applied delta는 실제 적용량 `alpha * delta`가 아니라 gate 후 delta라 이름이 애매하다.

개선:

1. `casLog`에 `applied_delta = alpha * raw_delta`를 명확히 기록
2. `model_match_quality` 또는 `match_status`를 숫자로 기록
3. EPS hash 자체는 로그에 직접 쓰지 않아도 된다. 필요하면 짧은 status만 기록한다.
4. UI 표기는 `,CAS`만 유지한다.

권장 extras:

```text
raw_delta
applied_delta
alpha
max_abs_z
match_status
offset_now
offset_5s_avg
offset_60s_avg
mean_abs_5s
centering_score
intervention_count
sec_since_intervention
```

---

## 5. Phase별 마이그레이션

### Phase A: 문서/용어 정리

- [ ] `cas_design.md`의 "NNFF 패턴 그대로" 표현을 "JSON/numpy 정적 모델 운영"으로 정리
- [ ] `cas_roadmap.md`의 "NNFF 노하우" 표현을 "CAS 독립 개선"으로 정리
- [ ] `cnlt_design.md`는 초기 논의 archive로 유지하되, 현재 결정은 이 문서를 우선한다고 표시
- [ ] `cas_conversation.md`에 "JSON/log에는 외부 구현 상태를 기록하지 않음" 결정 추가

### Phase B: weight metadata v2

- [x] `format_version: 2`
- [x] `feature_schema`
- [ ] `target_kind`
- [ ] `control_mode`
- [x] `car_names` alias 추가 (`CarName`/`CarSelected3` 기준)
- [x] `eps_firmware_hash` 자동 추출
- [ ] `lateral_delay_at_train` 평균 기록
- [ ] `friction_compensation_required`

기존 v1 weight는 계속 읽는다.

### Phase C: runtime 매칭 강화

- [x] `CarName`/`CarSelected3` 계열 이름 비교
- [x] EPS hash exact 우선
- [ ] EPS mismatch 시 alpha 제한 또는 off
- [ ] `CASModelName`은 match 성공 시에만 표시

### Phase D: feature 시간축 일치

- [x] `CASFeatureState`를 timestamp 기반 buffer로 변경
- [ ] training/runtime 모두 같은 시간 길이를 보장
- [ ] validation에서 feature_schema와 input_size 검사

### Phase E: validation/report 개선

- [ ] speed bucket
- [ ] curvature bucket
- [ ] high lateral accel bucket
- [ ] car/EPS match report
- [ ] 이전 weight 대비 regression report

---

## 6. 최종 구조

CAS가 목표로 하는 형태:

```text
openpilot lateral controller
  -> base steering command
  -> CAS feature builder
  -> CASModel JSON/numpy inference
  -> alpha gate
  -> base + alpha * residual
```

CAS weight는 이렇게 설명된다.

```text
이 차종/이 EPS/이 feature schema에서 학습된
차선 중앙 유지용 residual 조향 보정 모델
```

외부 구현과의 관계는 문서상 참고일 뿐이다.

```text
구현/JSON/log/UX 기준으로 CAS는 독립 시스템이다.
```
