# CAS 설계 대화 요약

> jominki354와 Claude의 CAS(Carrot Adaptive Steering) 설계 대화 기록.
> 관련 문서: [cas_design.md](cas_design.md) (설계 윤곽), [cas_roadmap.md](cas_roadmap.md) (개발 계획), [../README.md](../README.md) (운영 가이드)

---

## 1. 한 줄 결론 (현재 상태)

**CAS = "베테랑 코치가 옆에서 핸들을 살짝 보정해주는" 잔차 학습형 조향 시스템**. NNFF처럼 개발자가 학습/배포, 사용자는 ON/OFF만. 토크/앵글 둘 다 지원. 메인 타겟은 **NNFF 미지원 차량의 중앙 유지 강화**.

---

## 2. 주요 결정 사항 한눈에

| # | 결정 | 일시 |
|---|---|---|
| Q1 | **토크/앵글 둘 다** 지원 | 2026-05-19 |
| Q2 | **PC에서만 학습**, 기기는 추론+로그만 | 2026-05-19 |
| Q3 | **F안: 자동 트리아지 + 가중 supervised** (T1~T5) | 2026-05-19 |
| Q4 | 백본: **MLP 시작 → 부족시 mini-TCN** | (잠정) |
| Q5 | 학습 데이터: **openpilot 자체 운전 데이터 메인** | 2026-05-19 |
| Q6 | 데이터 양: **하한 ~20h, 상한 없음** | 2026-05-19 |
| Q7 | 추론 런타임: **순수 numpy** (onnx/torch 안 씀) | 2026-05-19 |
| Q8 | 가중치 포맷: **JSON** (safetensors 검토 후 기각) | 2026-05-19 |
| Q9 | 운영 모델: **NNFF 그대로** — jominki354가 학습/배포 | 2026-05-19 |
| Q10 | 학습 OS: **Linux/WSL2 권장, Windows native 가능** | 2026-05-19 |
| Q11 | 가중치 포맷: **JSON** (이식률 + 의존성 0) | 2026-05-19 |
| 이름 | **CAS** (Carrot Adaptive Steering) | 2026-05-19 |
| 메인 목표 | **차선 중앙 유지 / 쏠림 방지** | 2026-05-19 |
| 코드 위치 | **`selfdrive/carrot/cas/`** (한 폴더에 모음) | 2026-05-19 |

---

## 3. 주요 Q&A 요약

### Q: "NNFF 같은 조향 튜닝 만들고 싶어"
**A**: 현황 파악 — NNFF는 carrot에 이미 통합됨([latcontrol_torque.py](../../../../selfdrive/controls/lib/latcontrol_torque.py)), 앵글 차량용은 비어있음. NNFF의 한계(토크만, BC만, 안전망 없음) 위에 CAS 설계 시작.

### Q: "학습은 NNFF처럼 로그/PC/서버에서?"
**A**: 확정. **기기 학습 0줄, PC만**. NNFF 워크플로우 그대로. 안전성↑.

### Q: "ONNX 같은 거 아니지?"
**A**: 사용자 지적 맞음. NNFF의 `FluxModel`은 **JSON + 60줄 numpy**. CAS도 동일 — 외부 런타임 의존성 0.

### Q: "구조랑 NNFF와의 차이는?"
**A**: NNFF와의 차별점 5가지:
1. **앵글 차량 지원** (NNFF는 토크만)
2. **Residual + α 게이트** — base 위 잔차만 더함, 안전성↑
3. **자동 트리아지** — 사용자 부담 0
4. **사용자 개입 = 최강 학습 신호**
5. **장기 누적 친화** — continual re-training

### Q: "기존에 작성된 건 NNFF 같은 느낌이었어?"
**A**: 솔직히 그랬음. §11까지는 NNFF 후예. 사용자의 "**중앙 유지 메인 목표**" 알려준 덕에 §0/§12 추가하면서 패러다임 전환:
- 사람 운전 흉내(imitation) → **차선 중앙 오차 최소화 (outcome-based)**
- 이게 진짜 CAS 정체성

### Q: "어떤 방향으로 갈까 (A imitation vs D centering loss)?"
**A**: 두 옵션 정직 비교 후 **제3의 길 E안(Outcome-Filtered Imitation)** 추천 → 더 진화해서 **F안 확정**:
- 사람 직접 운전 데이터 불필요
- openpilot 자체 운전 데이터로 자기개선
- 사용자 개입 = 무료 라벨 (T3 최강)
- 양호/쏠림/개입 자동 분류 (T1~T5)

### Q: "어떤 데이터든 알아서 양질 학습되나?"
**A**: F안의 핵심 강점이 정확히 그것. 5종 자동 트리아지로 사용자가 rlog 던지면 자동 분류·가중치 부여. NNFF 대비 차별점 명확.

### Q: "학습 데이터 양은?"
**A**: 처음에 20~40h라 했지만 강제 상한 아님. **하한 ~20h, 상한 없음**, 장기 누적이 자연스러움. 100h든 1000h든 OK, 다양성이 더 중요.

### Q: "NNFF는 openpilot 코드 참고? 자체 구현?"
**A**: NNFF는 **openpilot 신호는 그대로 받음** (model_data, VehicleModel, CS 등), **출력만 자체 NN으로 FF 전체 대체**. liveTorqueParameters는 무시.

### Q: "NNFF 최소 학습 시간?"
**A**: 사용자 입장 0h (twilsonco가 배포). CAS는 차종 base + fine-tune 안 쓰고 NNFF 운영 그대로 → **사용자 학습도 0h**. 개발자만 학습.

### Q: "튜닝값을 모델에 어떻게 적용?"
**A**: NNFF와 같은 단계(컨트롤러 FF), 다른 방식. NNFF는 통째 대체, CAS는 잔차. driving model(modelV2)은 안 건드림.

### Q: "사용자 체감 %?"
**A**: 정확한 % 못 말함. 추정:
- NNFF: 10~30% (있으면 약간 나음)
- CAS: 20~40% (명확히 더 좋음)
- CAS 고점(1000h+): 40~60% ("한 단계 위" 느낌)

### Q: "하드유저가 로그 수없이 주면 고점 더 올라가?"
**A**: 가능. mean_offset 현재 ~0.20m → 고점 ~0.10m. 8가지 방법 (§21.3). 가장 중요한 셋: 모델 용량↑, 데이터 다양성, 멀티태스크 보조 loss. 이론 한계는 ~0.08m (lane 인식 자체 노이즈).

### Q: "왼쪽 쏠림 / SCC 미사용 케이스?"
**A**:
- 왼쪽 쏠림: ★ CAS 핵심 영역. NNFF가 못 잡는 좌우 비대칭 자동 학습.
- SCC 미사용: 무관. `latActive`만 보고 학습.

### Q: "여러 환경 데이터 평균인가 분기인가?"
**A**: 둘 다. 입력 신호로 식별 가능하면 분기, 못 하면 평균. 트리아지가 일관성 보장.

### Q: "NNFF FluxModel 포맷 그대로 따라야 해?"
**A**: 호환만 유지, 메타 풍부화. format_version, feature_spec, validation 지표, friction_override 등 11개 필드 추가.

### Q: "JSON 단순한데 정말 튜닝되나?"
**A**: JSON 안의 ~1000개 숫자 = 학습된 차량 응답 전체. NN의 본질이 행렬곱이라 그게 다. NNFF가 99.6% EPS 식별 입증.

### Q: "의존성 0 + 이식률 좋음 최적 포맷?"
**A**: JSON 단 하나가 두 조건의 교집합. 두 번째는 JSON+gzip 또는 .py 모듈. 둘 다 단점 있어 JSON 단독 채택.

### Q: "NNFF 없는 차량은?"
**A**: ★ **CAS의 메인 타겟**. classical FF는 비선형/비대칭 거의 못 잡음 → CAS의 δ가 메울 공간 큼. NNFF 미지원 차량에서 효과 **-55%** (NNFF 차량 -27%보다 큼).

### Q: "CAS 원리는 뭐야?"
**A**: 두 가지 설명:
- **기술적**: 잔차 학습(base + α·δ) + outcome 기반 학습 + 자동 트리아지 + 신뢰도 게이트
- **비유**: "베테랑 운전 코치가 옆자리에서 핸들을 살짝 도와주는" 시스템

### Q: "rlog에 필요한 데이터 다 있어?"
**A**: 거의 모든 신호 있음 (carState, modelV2, controlsState, lateralPlan, carParams, liveDelay, liveTorqueParameters). lateral_offset만 modelV2.position에서 계산. cereal에 `lateralLearningInfo` 메시지 1개만 신규.

### Q: "토크/앵글 어떻게 구분?"
**A**: `CP.steerControlType == SteerControlType.angle`이면 앵글, 아니면 토크. [controlsd.py:73-78](../../../../selfdrive/controls/controlsd.py#L73-L78)에서 이미 분기 중. CAS는 그대로 따름.

---

## 4. 패러다임 전환 시점

대화 중 가장 중요했던 전환점:

### 4.1 "사람 운전 모방"에서 "결과 기반 학습"으로
- §11까지 CAS는 사실상 "더 정교한 NNFF"였음 (Behavior Cloning)
- 사용자: "중앙 유지가 중점, 큰 코너/속도에서 쏠림 방지"
- 이 한 마디로 학습 신호 자체 변경 → **F안**으로 발전

### 4.2 "디바이스 학습" 검토에서 "PC만"으로 완전 확정
- 초기에 디바이스 last-layer 학습 옵션 고려
- 사용자: "기기에선 절대 학습 안 함, 로그만"
- 안전성/단순성 결정적 개선

### 4.3 "사용자 fine-tune"에서 "NNFF 운영 그대로"로
- 차종 base + 사용자 fine-tune 전략 검토
- 사용자: "NNFF처럼 jominki354가 학습/배포, 사용자는 ON/OFF만"
- 사용자 부담 0으로 단순화

### 4.4 "NNFF 슈퍼셋"에서 "독립 시스템"으로
- 초기에 "CAS_torque ⊃ NNFF" 표현
- 사용자: "CAS는 NNFF와 무관한데 표현 헷갈림"
- 정정: 독립 시스템, 동시 사용 시 자동 공존 (base + α·δ)

---

## 5. NNFF vs CAS 핵심 차이 (정리판)

| 항목 | NNFF | CAS |
|---|---|---|
| 출신 | 2022 twilsonco 커뮤니티 | 2026 carrot, 7편 학술 논문 기반 |
| 대상 | 토크만 | 토크 + 앵글 |
| 출력 방식 | FF 통째 대체 | base + α·δ (잔차) |
| 안전 게이트 | 없음 | α ∈ [0,1] 상황 적응 |
| 학습 패러다임 | Behavior Cloning | Outcome (centering) + 자동 트리아지 |
| 사용자 개입 | 데이터 제외 | **T3 최강 신호** |
| 좌우 비대칭 | 거의 못 잡음 | 자동 학습 |
| 메인 타겟 | 전 차종 | **NNFF 미지원 차량** |
| 가중치 | JSON | JSON (메타 풍부화) |
| 학습 위치 | PC (twilsonco) | PC (jominki354) |
| 사용자 학습 | 0h | 0h |
| 사용자 설정 | 토글만 | 토글만 |
| 결합 시스템 검증 | ✅ 실 운영 다수 | ❌ Phase 1 예정 |

---

## 6. 핵심 학술 근거 (CAS 부품)

| 컴포넌트 | 논문 |
|---|---|
| Residual Policy | [Trumpp 2302.07035](https://arxiv.org/pdf/2302.07035) (-4.55% 랩타임) |
| Physics-Guided NN | [arXiv 2204.00431](https://arxiv.org/pdf/2204.00431) |
| EPS NN System ID | [IEEE 10496684](https://ieeexplore.ieee.org/document/10496684/) (99.6% 정확도) |
| Predictive Preference Learning | [arXiv 2510.01545](https://arxiv.org/abs/2510.01545) |
| PINN Lateral Control | [SpringerLink 2024](https://link.springer.com/chapter/10.1007/978-3-031-70392-8_115) |
| Last-Layer Reset | [arXiv 2310.07996](https://arxiv.org/pdf/2310.07996) |
| Lane Centering KPI | [SAE 2026-01-0037](https://saemobilus.sae.org/papers/integrated-design-validation-a-robust-lane-centering-controller-automated-driving-2026-01-0037) |

---

## 7. 다음 단계 (대기)

문서 체계는 완성. 실 구현 진입 전 사용자 결정 필요:

1. Phase 0 시작 시점
2. 첫 번째 차종 선정 (jominki354 본인 차)
3. cereal 메시지 추가 확정 (`lateralLearningInfo`)
4. 협조자 데이터 풀링 방식 (선택)

부록 B (cas_roadmap.md)에 "지금 당장 시작 가능한 4개 액션" 정의됨.

---

## 8. 문서 체계

| 문서 | 역할 |
|---|---|
| [../README.md](../README.md) | 진입점 — 학습 환경 / 명령 / 데이터 양 / 매칭 확인 |
| [cas_design.md](cas_design.md) | 설계 윤곽 (구조, 원리, 결정 사항, NNFF 비교, CAS v2 독립화 §26) |
| [cas_roadmap.md](cas_roadmap.md) | 개발 로드맵 (Phase 0~5+, 체크리스트) |
| [cas_conversation.md](cas_conversation.md) | **이 문서**, 대화 요약 + Q&A |
| [cas_handoff_YYYYMMDD.md](.) | 날짜별 운영 상태 핸드오프 (최신 1개만 의미 있음) |

---

_생성일: 2026-05-19. 대화가 추가되면 §3 Q&A, §2 결정 표, §4 패러다임 전환에 추가._
