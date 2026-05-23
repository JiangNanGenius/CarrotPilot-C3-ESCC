# CAS v2 전략 메모 — NNFF 대비 고점 / 검증 로드맵

작성일: 2026-05-23  
상태: 현재 구현은 `강한 residual CAS v1`, full-FF/hybrid CAS v2는 보류

---

## 1. 이번 논의의 핵심

사용자 요구는 단순히 “CAS가 조금 보정”이 아니라:

- NNFF와 같거나 더 강한 체감
- 정지 상태가 아니면 가능한 한 계속 개입
- 한쪽 쏠림/중앙 유지뿐 아니라 기본 조향 품질 고점도 높이기
- 혼자 실차 검증해야 하므로 실패 비용은 낮게 유지

현재 CAS 구현은 이 요구 중 “중앙 유지 residual 보정”에는 맞지만, “NNFF보다 조향 전체 고점이 높아야 한다”는 목표에는 아직 완성형이 아니다.

---

## 2. 현재 구현의 정체

현재 CAS는 기본적으로 다음 구조다.

```text
torque car:
  ff = base_ff + alpha * cas_delta * residual_gain

angle car:
  angle_des = base_angle_des + alpha * cas_delta * residual_gain
```

즉 CAS는 base controller를 대체하지 않고, 그 위에 residual을 얹는다.

장점:

- 기존 openpilot/NNFF/base 조향을 완전히 깨지 않는다.
- 위험한 상황에서 끄기 쉽다.
- 쏠림, 중앙 오차, 반복되는 미세 개입을 직접 겨냥한다.
- 혼자 검증할 때 실패 비용이 낮다.

한계:

- FF 전체를 대체하지 않으므로 NNFF처럼 조향 질감 전체를 바꾸는 고점은 낮다.
- `cas_delta` 자체가 작게 학습되면 alpha/residual gain을 올려도 체감이 제한된다.
- PID error response는 건드리지 않으므로, NNFF가 만지는 영역 일부는 CAS v1이 못 건드린다.

---

## 3. NNFF와 CAS의 차이

NNFF는 조향 feedforward 자체를 neural model로 계산한다.

```text
NNFF:
  ff = neural_ff(...)
  pid_error도 일부 NN 기반으로 재계산
```

CAS v1은 residual이다.

```text
CAS v1:
  ff = base_ff + learned_residual
```

따라서 현재 구현 기준 고점은:

```text
전체 조향 FF 고점: NNFF > CAS v1
중앙/쏠림 보정 직접성: CAS v1 > NNFF
최종 고점 후보: NNFF + CAS residual 또는 CAS hybrid/full-FF
```

사용자가 원래 요구한 “NNFF보다 고점 높은 CAS”는 CAS v1이 아니라 CAS v2 영역이다.

---

## 4. 관련 연구/실무 관점

### 4.1 Residual 방식은 타당하다

Residual Reinforcement Learning / Residual Policy Learning 계열은 기존 controller 위에 학습 residual을 더해, 기존 제어기의 안정성과 학습 제어기의 적응성을 합치는 방향을 제안한다.

- Residual Reinforcement Learning for Robot Control: 기존 feedback control이 잘하는 부분과 RL residual을 더하는 구조를 사용한다.  
  https://arxiv.org/abs/1812.03201
- Residual Policy Learning: 좋은데 불완전한 controller가 있을 때 residual policy를 학습하면 controller 단독보다 개선 가능하다고 주장한다.  
  https://arxiv.org/abs/1812.06298

CAS v1은 이 방향과 잘 맞는다. 즉 “기존 조향 + residual 보정”은 보수적이지만 학술적으로도 자연스러운 선택이다.

### 4.2 Full policy / full-FF는 검증 난도가 높다

DAgger 계열 imitation learning 논문은, 학습된 policy가 자기 행동 때문에 훈련 때와 다른 상태 분포를 만나고 오차가 누적될 수 있음을 지적한다.

- A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning  
  https://users.cs.utah.edu/~dsbrown/readings/dagger.pdf

ChauffeurNet도 단순 behavior cloning만으로는 부족하고, perturbation/추가 loss/나쁜 상황 합성이 robust driving에 중요하다고 보고한다.

- ChauffeurNet: Learning to Drive by Imitating the Best and Synthesizing the Worst  
  https://arxiv.org/abs/1812.03079

따라서 CAS를 NNFF처럼 full-FF 또는 full policy에 가깝게 만들수록, 로그 검증과 실차 shadow 검증이 훨씬 중요해진다.

---

## 5. 2026-05-23에 반영한 현 단계 변경

현재는 “full-FF 전환”이 아니라, residual CAS v1을 강하게 만드는 쪽으로 반영했다.

### 5.1 Runtime

- speed gate를 hard off에서 soft gate로 완화
- distribution gate를 `z>=3.5 off`에서 `z>=5.0 off`로 완화
- `CASResidualGain` 추가
  - 기본 150 = 1.5x
  - 설정 범위 50~300
- `CASAlphaOverride` cap을 50%에서 100%로 확장

### 5.2 Training / GUI

강한 residual 학습 기본값:

```text
alpha_max = 1.0
offset_gain = 0.55
driver_torque_scale = 0.35
target_clip = 0.8
residual_gain = 1.5
```

### 5.3 Validation

`tools/cas/validate.py`의 적용 게이트를 runtime과 맞춤.  
기존 validate는 예전 hard gate 기준이라 실제 runtime보다 과도하게 block 판정할 수 있었다.

---

## 6. 지금 당장 full-FF CAS로 가지 않는 이유

혼자 검증 + 바이브코딩 환경에서는 full-FF 전환의 실패 비용이 크다.

위험:

- 조향 전체가 바뀌므로 이상 체감 원인 분리가 어려움
- 로그상 좋아 보여도 실차 분포에서 다르게 행동할 수 있음
- base/NNFF/PID error와 상호작용이 커짐
- 한 번에 구조를 바꾸면 “학습 문제인지, 적용 문제인지, 게이트 문제인지” 구분이 어려움

따라서 현재 판단:

```text
지금은 강한 residual CAS 유지.
13h 로그로 재학습 후 실차 평가.
full-FF/hybrid는 shadow부터 시작.
```

---

## 7. 권장 로드맵

### Phase A — 강한 residual CAS v1 평가

목표:

- 현재 변경된 강한 residual CAS로 13h 로그 재학습
- 실차에서 CASDEBUG 확인

확인 항목:

- `적용`이 0%에 머무는가?
- 적용값이 너무 작은가?
- `방향 일치`가 60~70% 이상인가?
- 중앙 유지 점수가 개선되는가?
- 과보정/불안정이 생기는가?

판단:

```text
적용 거의 0%     -> 모델 로딩/gate 문제
적용 작음        -> residual_gain/target_clip/scale 추가 조정
방향 일치 낮음   -> 학습 타깃/부호/데이터 문제
강하지만 불안정  -> gain 낮추고 필터 강화
```

### Phase B — full-FF shadow

목표:

- 차에는 적용하지 않고, CAS full-FF 후보 출력만 계산/로그
- base/NNFF/CAS residual/CAS full 후보를 같은 로그에서 비교

필요 작업:

- train target에 base FF 또는 output torque 계열 추가
- 모델 출력 2개 또는 3개로 확장
  - `full_ff`
  - `centering_residual`
  - optional confidence/blend
- runtime에서 shadow 계산만 수행
- casLog에 shadow output 기록

실차 영향:

- 없음. 적용하지 않으므로 안전.

### Phase C — hybrid blend 10~30%

목표:

```text
ff = (1 - blend) * base_ff + blend * cas_full_ff + residual
```

처음은 10%, 그 다음 20~30%만.

진입 조건:

- shadow 검증에서 full-FF 후보가 base/NNFF보다 안정적으로 좋음
- 과보정 구간이 로그상 드물다
- residual CAS v1이 실차에서 안정적이다

### Phase D — higher blend / full-FF

목표:

- 50% 이상 blend 또는 full CAS FF

진입 조건:

- 다양한 도로/속도/곡률에서 shadow와 low blend 모두 안정
- 실차에서 불안정/과보정이 없다
- 충분한 데이터 누적

---

## 8. 현재 결론

지금 더 가야 할 방향은 “바로 full-FF로 갈아엎기”가 아니다.

현재 최선:

```text
1. 강한 residual CAS v1 유지
2. 13h 로그로 재학습
3. 실차에서 CASDEBUG 지표 확인
4. 부족하면 residual 쪽을 한 번 더 조정
5. 그 다음 full-FF shadow를 별도 Phase로 시작
```

이 방식이 혼자 검증하는 환경에서 가장 실패 비용이 낮고, NNFF보다 높은 고점으로 갈 수 있는 현실적인 경로다.

