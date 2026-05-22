# CAS Dataset Sync 작업계획서

이 문서는 CAS 업로드/학습 흐름을 "기기에서 조용히 업로드 → PC GUI가 자동으로 학습 준비 → 모델에 학습 시간 표시" 구조로 정리하기 위한 단계별 작업 계획이다.

서버 작업은 후순위로 둔다. 먼저 openpilot repo 안에서 가능한 메타 정리, torque/angle 분리, GUI 로컬 준비 상태, 기기 표시를 순차적으로 진행한다.

---

## 0. 목표

현재 상태:

- 기기는 `CarrotDataUpload=1`이면 route의 `rlog.zst`/`qlog.zst`를 서버로 업로드한다.
- PC `tools/cas/gui.py`는 로컬 RLOG 폴더를 기준으로 인덱싱/학습/검증을 수행한다.
- 서버에 이미 route가 쌓여도, 어떤 PC에서 어디까지 학습에 썼는지 공유하는 구조는 아직 없다.
- 기기 화면에는 현재 적용 CAS 모델이 몇 시간 데이터로 학습됐는지 짧게 보여주는 UX가 부족하다.

최종 방향:

```text
기기
  route 업로드는 조용히 자동 수행
  CAS 표시는 현재 적용 모델의 학습 시간만 짧게 표시

PC GUI
  실행 시 로컬/서버 route 상태를 자동 확인
  car_key + kind 단위로 학습 후보를 정리
  준비되면 사용자는 기존 학습 시작 흐름만 누름

서버
  후속 Phase에서 manifest/download/train-run API 제공
```

---

## 1. 기준 개념

### 1.1 Dataset 키

CAS 학습 데이터셋의 기본 단위는 다음 둘을 합친 값이다.

```text
car_key + kind
```

예:

```text
HYUNDAI_CASPER_EV / torque
HYUNDAI_CASPER_EV / angle
```

`car_key`는 fingerprint 수준의 엄격한 지문이 아니라, carrot/openpilot에서 쓰는 차량명 기반 canonical key다.

후보:

- `carParams.carFingerprint`
- `Params("CarName")`
- `Params("CarSelected3")`
- 학습 GUI의 수동 입력 car 값

정규화 규칙은 런타임의 `_norm_name()`과 같은 방향으로 간다. 사람이 읽고 파일명으로 쓰는 값은 `HYUNDAI_CASPER_EV`처럼 유지한다.

### 1.2 kind

`kind`는 차량명이 아니라 `carParams.steerControlType` 기준으로 판단한다.

```text
SteerControlType.angle -> kind="angle"
그 외                   -> kind="torque"
```

이유:

- 같은 차량명이라도 angle/torque 모델은 출력 의미가 다르다.
- torque CAS는 `ff += alpha * delta`로 적용된다.
- angle CAS는 `angle_steers_des += alpha * delta`로 적용된다.
- 따라서 학습 데이터, candidate, weight 파일은 서로 섞이면 안 된다.

### 1.3 기기 표시 원칙

업로드 설정 항목에는 학습/시간 정보를 붙이지 않는다.

업로드는 사용자가 켜면 조용히 route를 보내는 기능으로 둔다.

기기에서 표시할 시간은 오직 "현재 적용된 CAS 모델의 학습 시간"이다.

예:

```text
CAS 6h
CAS 152h
```

서버 보유 시간, 업로드 완료 시간, 새 로그 시간은 GUI 또는 CASDebug 상세 화면에서만 다룬다.

### 1.4 모델 JSON 메타 원칙

기기에 배포되는 weight JSON에는 요약만 넣는다.

route id 전체 목록은 넣지 않는다. 수백/수천 route가 쌓이면 모델 파일이 불필요하게 커지고 관리가 어려워진다.

모델 JSON 권장 요약:

```json
{
  "car": "HYUNDAI_CASPER_EV",
  "car_names": ["HYUNDAI_CASPER_EV", "Hyundai Casper EV 2024"],
  "kind": "torque",
  "model_type": "cas_torque",
  "trained_on_hours": 152.4,
  "trained_route_count": 184,
  "trained_segment_count": 2760,
  "dataset_id": "HYUNDAI_CASPER_EV_torque_20260522_152h"
}
```

상세 route 목록은 로컬 또는 서버 manifest에만 둔다.

---

## 2. Phase 1 - 로컬/기기 메타 정리

목표: 서버 연동 전에 모든 메타가 `car_key + kind` 기준을 담도록 만든다.

### 작업

1. `selfdrive/carrot/cas/data_uploader.py`
   - `route_meta.json` 생성 내용을 보강한다.
   - 가능한 값:
     - `device_id`
     - `route_id`
     - `car_key`
     - `car_name_raw`
     - `kind`
     - `steer_control_type`
     - `segments`
     - `duration_sec`
     - `uploaded_at`
     - `rlog_bytes`
     - `qlog_bytes`
   - 기기에서 정확히 모르는 값은 빈 문자열 또는 생략 가능하게 둔다.

2. `tools/cas/gui.py`
   - rlog 인덱싱 시 `carParams.steerControlType`을 읽어 `kind`를 저장한다.
   - 기존 `car`/`eps_hash` 감지 로직에 `kind`를 추가한다.
   - 그룹 key를 `car_key + kind`로 확장한다.

3. `tools/cas/train.py`
   - rlog 수집 중 `carParams.steerControlType`을 감지한다.
   - `--kind`가 수동 지정되지 않거나 `auto`일 때 rlog에서 자동 결정할 수 있게 준비한다.
   - 여러 kind가 섞이면 경고 또는 실패하도록 한다.

4. 문서
   - `README.md`, `STRUCTURE.md`에 dataset 단위가 `car_key + kind`임을 반영한다.
   - EPS hash는 필수 매칭 기준이 아니라 보조 정보임을 명확히 한다.

### 완료 기준

- 로컬 인덱스에 각 rlog의 `car_key`, `car_name_raw`, `kind`가 남는다.
- route meta에 `kind`가 들어갈 수 있다.
- GUI가 같은 차량의 torque/angle을 별도 그룹으로 볼 수 있다.

---

## 3. Phase 2 - torque/angle 학습 파일 분리

목표: 같은 차량의 torque 모델과 angle 모델이 파일명/메타/검증에서 섞이지 않게 한다.

### 작업

1. `tools/cas/gui.py`
   - candidate/validate 기본 파일명에 kind를 포함한다.

   예:

   ```text
   HYUNDAI_CASPER_EV_torque_candidate.json
   HYUNDAI_CASPER_EV_torque_validate.json
   HYUNDAI_CASPER_EV_angle_candidate.json
   HYUNDAI_CASPER_EV_angle_validate.json
   ```

2. `tools/cas/promote.py`
   - 출력 weight 파일명에도 kind를 포함하도록 기본값을 바꾼다.

   예:

   ```text
   selfdrive/carrot/cas/weights/HYUNDAI_CASPER_EV_torque.json
   selfdrive/carrot/cas/weights/HYUNDAI_CASPER_EV_angle.json
   ```

3. `selfdrive/carrot/cas/runtime.py`
   - 현재도 `model_type == cas_torque/cas_angle` 필터가 있으므로 구조는 유지한다.
   - 기존 `HYUNDAI_CASPER_EV.json` 같은 구형 파일명도 당분간 호환한다.

4. `tools/cas/export_json.py`
   - 모델 JSON에 `kind`, `dataset_id`, `trained_route_count`, `trained_segment_count`를 넣을 수 있게 한다.

### 완료 기준

- torque 학습 결과와 angle 학습 결과가 다른 파일로 생성된다.
- promote가 `model_type`/`kind` 불일치 파일을 거부한다.
- 런타임은 해당 컨트롤러 kind와 맞는 모델만 로드한다.

---

## 4. Phase 3 - 기기 CAS 학습 시간 표시

목표: 운전자가 현재 적용된 CAS 모델의 학습량을 간단히 확인할 수 있게 한다.

### 작업

1. `selfdrive/carrot/cas/runtime.py`
   - 현재 `CASModelHours` param 기록을 유지한다.
   - 필요하면 소수점 표시를 UX용으로 정리한다.

   예:

   ```text
   5.98 -> 6h
   152.4 -> 152h
   ```

2. `selfdrive/ui/carrot.cc`
   - 차량명 옆 `,CAS`를 `,CAS 6h` 또는 `,CAS 152h`로 확장한다.
   - 표시 대상은 `CASModelHours`다.

3. `selfdrive/ui/cas_debug.cc`
   - 헤더의 학습 시간 표시를 동일 기준으로 맞춘다.
   - debug 모드에서는 필요 시 `kind`도 표시할 수 있다.

### 표시 원칙

- 업로드 설정 줄에는 표시하지 않는다.
- 일반 화면에는 짧게 표시한다.
- 자세한 정보는 CASDebug에 둔다.

### 완료 기준

- 모델 매칭 시 차량명/상단 표시에서 `CAS 6h`처럼 보인다.
- CAS가 꺼져 있거나 모델이 없으면 표시하지 않는다.

---

## 5. Phase 4 - GUI 자동 준비 상태

목표: 버튼을 늘리지 않고 GUI가 자동으로 학습 준비 상태를 만든다.

### 작업

1. `tools/cas/gui.py`
   - 실행 시 기존처럼 RLOG 폴더를 자동 인덱싱한다.
   - 인덱싱 결과를 `car_key + kind` 그룹으로 보여준다.
   - 그룹별 상태 문구를 추가한다.

   예:

   ```text
   HYUNDAI_CASPER_EV / torque
   총 152h · 이전 학습 120h · 새 로그 32h
   상태: 학습 준비됨
   ```

2. 로컬 학습 run 기록
   - `<RLOG>/.cas/train_runs.json` 추가.
   - 각 학습 run에 다음 요약을 저장한다.

   ```json
   {
     "train_run_id": "20260522_153000_HYUNDAI_CASPER_EV_torque",
     "car_key": "HYUNDAI_CASPER_EV",
     "kind": "torque",
     "trained_on_hours": 152.4,
     "trained_route_count": 184,
     "trained_segment_count": 2760,
     "candidate": "...",
     "validate_json": "...",
     "created_at": "2026-05-22T15:30:00+09:00"
   }
   ```

3. 새 로그 판단
   - route 전체 목록을 모델 JSON에 넣지 않는다.
   - 로컬 index/train_runs 기준으로 이전 학습 이후 추가된 시간만 계산한다.
   - 정확한 route-level 추적은 Phase 5/6의 manifest 구조로 넘긴다.

### 완료 기준

- GUI가 시작되면 별도 sync 버튼 없이 인덱싱 상태와 학습 가능 상태를 보여준다.
- 사용자는 기존 학습 시작 버튼만 누르면 된다.
- 이전 학습 이후 새 로그 시간을 확인할 수 있다.

---

## 6. Phase 5 - 서버 연동 준비용 클라이언트 껍데기

목표: 서버 API를 붙이기 전에 GUI 내부 구조를 local/server 양쪽 소스에 대응 가능하게 만든다.

서버는 원본 route 저장소로 유지한다. 학습 PC는 필요한 route만 임시로 내려받아 학습하고, 학습/검증이 끝난 뒤 PC 로컬 원본만 삭제할 수 있다. 서버 원본은 이 흐름에서 삭제하지 않는다.

### 작업

1. `tools/cas/cloud_sync.py` 신규 파일 후보
   - 지금은 local manifest만 다룬다.
   - 나중에 서버 manifest API가 생기면 같은 인터페이스로 교체한다.
   - GUI 인덱싱 후 `<RLOG>/.cas/local_manifest.json`을 생성한다.

2. 공통 데이터 구조

   예:

   ```json
   {
     "car_key": "HYUNDAI_CASPER_EV",
     "kind": "torque",
     "routes": [],
     "summary": {
       "route_count": 184,
       "segment_count": 2760,
       "total_hours": 152.4
     }
   }
   ```

3. GUI 연결
   - local index에서 온 데이터와 server manifest에서 온 데이터를 같은 형태로 처리하도록 정리한다.
   - 이 Phase에서는 실제 서버 통신은 하지 않아도 된다.

4. PC 로컬 작업공간 정책
   - 서버 route를 내려받는 위치를 별도 cache/workspace로 둔다.

   예:

   ```text
   <RLOG>/.cas/cloud_cache/<device_id>/<route_id>--<seg>/rlog.zst
   <RLOG>/.cas/cloud_cache/<device_id>/<route_id>--<seg>/qlog.zst
   ```

   - 다운로드 상태는 local state에만 저장한다.
   - 서버 파일 삭제 API는 호출하지 않는다.
   - GUI 옵션으로 학습 PC의 원본 rlog/qlog 처리 방식을 둔다.

   ```text
   보관        : 다운로드한 rlog/qlog 유지
   학습 후 삭제 : Train + Validate 성공 후 PC 로컬 rlog/qlog만 삭제
   ```

   - 기본값은 `보관`으로 둔다.
   - `학습 후 삭제`를 켜도 다음 항목은 남긴다.
     - feature cache
     - index/train run metadata
     - candidate/validate JSON
     - raw execution logs

5. 자동 흐름

   목표 UX:

   ```text
   GUI 실행
     -> 서버 manifest 확인
     -> 로컬에 없는 route만 PC로 다운로드
     -> 인덱싱
     -> 학습 준비 상태 표시
     -> 사용자가 학습 시작
     -> 학습/검증 성공
     -> 옵션에 따라 PC 로컬 rlog/qlog만 삭제
   ```

### 완료 기준

- GUI 내부가 "로컬 폴더만" 전제로 강하게 묶여 있지 않다.
- 서버 API 추가 시 다운로드/manifest 함수만 채우면 된다.
- 서버 원본과 PC 로컬 작업 파일의 생명주기가 분리되어 있다.
- 학습 PC에서 원본을 삭제해도 서버에는 route가 남는다.
- 현재 Phase에서는 실제 서버 통신/다운로드는 하지 않는다.

---

## 7. Phase 6 - 서버 작업

확인된 서버는 LXC 205 `carrot-nas`의 FastAPI 업로드 서버다.

```text
/opt/carrot-upload/server.py
/srv/carrot_rlogs/by-device/<device_id>/<route_id>/<seg>/{rlog.zst,qlog.zst}
/srv/carrot_rlogs/by-device/<device_id>/<route_id>/route_meta.json
```

repo 기준 서버 파일은 `tools/cas/server/carrot_upload_server.py`로 둔다.
배포/검증 메모는 `docs/cas_server_phase6.md`에 둔다.

### 필요한 서버 기능

1. 업로드 route meta 수집
   - 업로드된 `route_meta.json`을 읽어 서버 manifest에 누적한다.
   - 구버전 meta에 `car_key`/`kind`가 없으면 `car.txt`, `UNKNOWN_CAR`, `torque` fallback을 사용한다.

2. manifest API

   ```text
   GET /api/routes?car_key=HYUNDAI_CASPER_EV&kind=torque
   GET /api/devices/<device_id>/routes
   ```

3. 다운로드 API

   ```text
   GET /download/<device_id>/<route_id>/<seg>/rlog.zst
   GET /download/<device_id>/<route_id>/<seg>/qlog.zst
   ```

4. dataset summary API

   ```text
   GET /api/datasets/summary?car_key=HYUNDAI_CASPER_EV&kind=torque
   ```

5. train-run 기록 API

   ```text
   POST /api/train-runs
   GET /api/train-runs/latest?car_key=HYUNDAI_CASPER_EV&kind=torque
   ```

6. PC 클라이언트 함수
   - `tools/cas/cloud_sync.py`에서 서버 manifest fetch와 segment download 함수를 제공한다.
   - 실제 GUI 자동 다운로드 연결은 후속 단계에서 진행한다.

### 서버 삭제 정책

- GUI 학습 흐름에서 서버 route는 삭제하지 않는다.
- 서버는 장기 원본 저장소 역할을 한다.
- 학습 PC의 `학습 후 삭제` 옵션은 PC 로컬에 다운로드한 rlog/qlog만 대상으로 한다.
- 서버 정리/보존 기간 정책이 필요하면 별도 관리자 작업으로 분리한다.

### 완료 기준

- 어떤 PC에서 GUI를 열어도 서버 manifest 기준으로 새 route를 확인할 수 있다.
- 학습에 사용된 마지막 dataset 상태를 서버에서 이어받을 수 있다.
- 서버 원본 삭제 없이 `/download/...`로 PC 로컬 cache에 내려받을 수 있다.

---

## 8. 우선순위

즉시 시작 추천 순서:

1. Phase 1: `car_key + kind` 메타 정리
2. Phase 2: torque/angle 파일명과 모델 메타 분리
3. Phase 3: 기기 `CAS 6h` 표시
4. Phase 4: GUI 자동 준비 상태
5. Phase 5: 서버 연동 준비
6. Phase 6: 서버 구현

가장 먼저 해야 하는 것은 Phase 1이다. 이후 모든 기능이 `car_key + kind` 기준을 공유해야 torque/angle 혼합, 차량명 혼선, 모델 표시 혼선을 피할 수 있다.

---

## 9. 2026-05-22 Phase 6.5 - GUI server manifest/download bridge

- LXC 205 server internal/external API check passed.
  - Internal: `http://127.0.0.1:8000/health`
  - External: `https://casroute.jominki354.live/health`
  - `GET /api/datasets?include_routes=false` returns HTTP 200.
- GUI now fetches server manifest from `https://casroute.jominki354.live` by default.
- Server datasets are shown in the target selector as `[server] ...` groups next to local groups.
- Selecting a server group and starting training downloads only the needed `rlog.zst` files into:

  ```text
  <RLOG>/.cas/cloud_cache/<device>/<route>--<seg>/rlog.zst
  ```

- Successful train+validate runs are recorded locally in `<RLOG>/.cas/train_runs.json` and posted to `/api/train-runs` when a server URL is configured.
- Older server routes can appear as `UNKNOWN_CAR/torque` because their uploaded `route_meta.json` did not include `car_key`/`kind`. New uploads should split as `HYUNDAI_CASPER_EV/torque` etc.

---

## 10. UX Phase - non-developer app mode

목표: 사용자가 설정값을 거의 고민하지 않고 `학습 시작`만 누를 수 있는 앱 형태로 전환한다.

기본 화면 원칙:

- 화면 제목은 `CAS Learner`로 단순화한다.
- 기본 화면에는 차량 선택, 최소 메타, 큰 `학습 시작` 버튼, `차량에 적용` 버튼만 둔다.
- `RLOG`, `candidate`, `validate`, `manifest`, `torque` 같은 내부 용어는 기본 화면에서 숨긴다.
- 여러 차량은 드롭다운으로 고르되, 항목은 `차량명 · 조향 방식 · 새 데이터 시간`만 표시한다.
- `UNKNOWN_CAR`는 `차량 확인 전 데이터`로 표시한다.
- 학습 성공 후에는 로컬 이력과 서버 이력을 기록한다.
- 다음 Phase에서는 학습된 모델 JSON 자체를 서버에 업로드하고, comma/openpilot 쪽이 최신 모델을 받아 쓰는 배포 API를 추가한다.

현재 구현:

- `tools/cas/gui.py` 기본 화면을 앱 모드로 재배치했다.
- 최소 메타는 `준비된 데이터`, `학습 완료`, `새 데이터`, `데이터 위치`만 표시한다.
- `전문가 설정` 안에 기존 상세 경로/학습 옵션/수동 버튼을 유지한다.
- 학습 후 서버 `/api/train-runs`에 이력이 기록되면 화면에 서버 동기화 상태를 표시한다.

### Flet prototype note

- Added `tools/cas/gui_flet.py` as a Material-style app shell.
- It uses Flet 0.85.x, Material 3 theme, one primary card, one primary action, and hidden expert details.
- It currently fetches server datasets and shows the simplified UX only.
- Production train/validate/apply still remains in `tools/cas/gui.py` until the runner is split out of Tkinter and reused by Flet.

### Material 3 Flet redesign note

- Reworked `tools/cas/gui_flet.py` around Material 3 app structure:
  - top app bar with refresh/settings actions
  - one primary content card
  - one primary action (`학습 시작`)
  - secondary apply action disabled until enough trained hours exist
  - vehicle dropdown only when more than one dataset exists
  - technical details collapsed under `자세히`
- Default screen no longer shows logs, GPU text, file paths, or progress unless needed.
- This is the preferred UX direction for non-developer users. The next implementation step is extracting the train/validate/apply runner from `gui.py` so this Flet app can execute the real workflow.
