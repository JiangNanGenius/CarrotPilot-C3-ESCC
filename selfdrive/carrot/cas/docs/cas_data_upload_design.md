# CAS 데이터 업로드 — 설계 문서

> carrot CAS의 firehose식 옵트인 주행 데이터 수집/업로드 파이프라인 설계.
> 사용자 입장: 토글 1개. 시스템 입장: 자동 업로드 → NAS 저장 → 학습 입력.
>
> 관련 문서: [cas_design.md](cas_design.md), [cas_roadmap.md](cas_roadmap.md), [../README.md](../README.md)

---

## 0. 핵심 원칙

- **사용자는 토글 1개만**. host/계정/키 설정 없음.
- **인증은 가볍게**: carrot 바이너리에 박힌 HMAC secret으로 봇 차단 수준.
- **차종/사용자 통합 학습**: 여러 사용자가 같은 차종 운전 시 데이터 자동 통합.
- **개인정보 최소화**: qcamera는 안 보냄. rlog만.
- **서버 저예산 운영**: NAS LXC + Cloudflare Tunnel. 외부 호스팅 비용 0.
- **클론 기기 호환**: comma `DongleId` 의존 X. 자체 `CarrotDeviceId`를 첫 부팅 시 생성/저장.

### 식별자 — CarrotDeviceId

`DongleId`는 comma 정품 + 서버 등록 거친 기기만 있는 값. 클론/사이드로드 기기엔 없거나 신뢰 불가.

→ 자체 식별자 사용:

```python
# selfdrive/carrot/cas/data_uploader.py 초기화
from openpilot.common.params import Params
import uuid

def get_device_id() -> str:
    p = Params()
    did = (p.get("CarrotDeviceId") or "").strip()
    if not did:
        did = uuid.uuid4().hex[:16]   # 16자 hex
        p.put("CarrotDeviceId", did)
    return did
```

- PERSISTENT 파라미터로 한 번만 생성, 이후 영구 사용
- 기기 와이프하면 새로 생성됨 (의도된 동작)
- comma `DongleId`가 있으면 그것도 메타에 같이 보냄 (둘 다 기록), 매칭은 `CarrotDeviceId`로

---

## 1. 전체 흐름

```
[기기]
  CarrotDataUpload=1
  루트 완료 또는 offroad 진입 시
  WiFi/배터리 조건 만족
        ↓
  selfdrive/carrot/cas/data_uploader.py
  HTTPS POST + HMAC 헤더
        ↓
[Cloudflare Tunnel]
  casroute.jominki354.live → NAS LXC :8000
        ↓
[NAS LXC carrot-nas (205)]
  FastAPI 서버 (HMAC 검증)
  /srv/carrot_rlogs/by-device/<device_id>/<route>/<segment>/rlog.zst
  심볼릭 링크 자동 생성:
  /srv/carrot_rlogs/by-car/<car>/<device_id>__<route>/ → ...
        ↓
[PC 학습]
  gui.py "Pull from NAS" 또는 SMB 마운트
  tools/cas/train.py --rlogs /pulled/by-car/HYUNDAI_CASPER_EV
```

---

## 2. 기기 측 — selfdrive/carrot/cas/data_uploader.py

### 2.1 파일 위치

```
selfdrive/carrot/cas/
  data_uploader.py          ← 메인 데몬
  uploader_state.py         ← 이미 올린 라우트 기록 / 큐 관리
```

CAS 관련은 cas/ 폴더 안에 모두 모음.

### 2.2 업로드 트리거

| 시점 | 동작 |
|---|---|
| 새 세그먼트 시작 | 이전 세그먼트 완성 인지 → 큐 추가 |
| **시동 종료 (offroad 진입)** ★ | 현재 라우트 마감 → 미업로드분 일괄 처리 |
| 부팅 시 | 이전 종료 시 못 올린 큐 이어서 처리 |

기본은 **offroad 진입 시 일괄 업로드** (주행 중 네트워크/CPU 부담 최소화).
`CarrotUploadOnlyOffroad=0`이면 주행 중 실시간 업로드도 가능 (배경 우선순위).

### 2.3 업로드 조건 (Params)

| Param | 기본값 | 설명 |
|---|---|---|
| `CarrotDataUpload` | 0 | ★ 마스터 토글 (사용자가 만지는 유일한 것) |
| `CarrotUploadWifiOnly` | 1 | WiFi가 아니면 업로드 X |
| `CarrotUploadMinBattery` | 50 | 배터리 % 이하면 X (USB 미연결 시) |
| `CarrotUploadOnlyOffroad` | 1 | offroad에서만 업로드 (주행 중 부담 X) |
| `CarrotUploadEndpoint` | `https://casroute.jominki354.live` | 서버 URL (배포 시 고정) |

UI 메뉴엔 `CarrotDataUpload` 1개만 노출, 나머지는 advanced.

### 2.4 보낼 파일

기기 저장 경로: `/data/media/0/realdata/<route_id>--<segment>/`

| 파일 | 보냄 | 비고 |
|---|---|---|
| `rlog.zst` | ✅ | ~3MB, CAS 학습 핵심 |
| `qlog.zst` | △ 옵션 | ~200KB, 가벼움 — 같이 보내도 무방 |
| `qcamera.ts` | ❌ | ~50MB, CAS엔 불필요. 개인정보 노출 위험 |
| `route_meta.json` | ✅ (자동 생성) | 라우트당 1개 메타 |

`route_meta.json`은 업로더가 생성:

```json
{
  "device_id": "ac960474",
  "route_id": "2026-05-20--09-12-34",
  "car": "HYUNDAI_CASPER_EV",
  "eps_firmware_hash": "215ef677b75f",
  "carrot_version": "0.1.2",
  "cas_model_used": "HYUNDAI_CASPER_EV",
  "cas_alpha_max": 0.20,
  "started_at": "2026-05-20T09:12:34Z",
  "duration_s": 2340,
  "segments": 39
}
```

### 2.5 HTTP 요청

```
POST <endpoint>/upload/<device_id>/<route_id>/<segment>/<filename>
Headers:
  X-Carrot-TS: 1716000000
  X-Carrot-Sig: <hmac_sha256(secret, "<device_id>|<ts>")>
  X-Carrot-Version: 0.1.2
  X-Carrot-Car: HYUNDAI_CASPER_EV
  X-Carrot-EpsHash: 215ef677b75f
  X-Carrot-CasModel: HYUNDAI_CASPER_EV
Body: 파일 바이트
```

- `<segment>` = 세그먼트 번호 (`0`, `1`, ...)
- `<filename>` = `rlog.zst`, `qlog.zst`, 또는 라우트 메타면 `route_meta.json` (segment=-1 또는 별도 path)

### 2.6 인증 — HMAC

```python
# carrot 바이너리에 박힌 secret (32바이트, 빌드시 git ignore된 파일에서 읽음)
secret = b"..."

ts = int(time.time())
sig = hmac.new(secret, f"{device_id}|{ts}".encode(), "sha256").hexdigest()
```

서버는 동일 secret으로 검증, ±5분 안에 ts 있어야 함.

### 2.7 상태 관리 — uploader_state.py

```
/data/cas_upload_state.json
{
  "uploaded_routes": {
    "2026-05-20--09-12-34": { "at": 1716000000, "bytes": 117440000, "segments": 39 },
    ...
  },
  "last_attempt": 1716003600,
  "failed_attempts": { "2026-05-20--09-12-34": { "count": 2, "last_error": "..." } }
}
```

- 이미 올린 라우트는 재시도 X
- 실패 시 다음 부팅/주기에 자동 재시도

### 2.8 manager 등록

`selfdrive/manager/process_config.py`에 `data_uploader.py` 등록 → 부팅 시 자동 시작 / 종료 시 정상 종료.

`CarrotDataUpload=0`이면 데몬은 동작하되 sleep 만 (실제 업로드 X).

---

## 3. 서버 측 — FastAPI 업로드 서버

### 3.1 파일 위치 (NAS LXC 내부)

```
/opt/carrot-upload/
  server.py                ← FastAPI 메인
  config.py                ← secret, paths
  cleanup.py               ← 디스크 풀 시 오래된 라우트 삭제
/etc/carrot-upload/
  secret                   ← HMAC secret (mode 600)
/srv/carrot_rlogs/
  by-device/<device>/<route>/<segment>/rlog.zst
  by-car/<car>/<device>__<route>/ → ../../by-device/...
```

### 3.2 동작

| 메서드 | 경로 | 동작 |
|---|---|---|
| `POST` | `/upload/<device>/<route>/<segment>/<filename>` | 헤더 검증 → 디스크 검사 → 저장 → by-car symlink 갱신 |
| `GET` | `/health` | 단순 상태 (OK 200) |
| `GET` | `/stats` | (선택, 인증 필요) 전체 통계 |

### 3.3 보안

- **HMAC 검증** (timestamp ±5분, 동일 secret)
- **device_id 형식 검증**: 16자 hex
- **파일명 검증**: `rlog.zst` / `qlog.zst` / `route_meta.json`만 허용. 경로 traversal 차단.
- **파일 크기 cap**: rlog 50MB까지. 초과 시 413.
- **rate limit 없음** (사용자 요청)

### 3.4 메모리/동시성 (서버 RAM 절약)

- `uvicorn --workers 1` (싱글 워커)
- `--limit-concurrency 4` (동시 요청 4개까지)
- streaming upload (전체 메모리 로드 X, chunk 단위 디스크 직접 쓰기)
- max request body 50MB

### 3.5 디스크 풀 처리 — cleanup.py

```python
DISK_WARN_PCT = 85    # 85% 넘으면 cleanup 시작
DISK_TARGET_PCT = 75  # 75% 까지 줄임

def cleanup_if_needed():
    used_pct = disk_usage(BASE_PATH).percent
    if used_pct < DISK_WARN_PCT: return
    
    # 가장 오래된 라우트부터 삭제
    routes = list_routes_by_age(BASE_PATH)   # mtime 기준 오래된 순
    for route in routes:
        if disk_usage(BASE_PATH).percent < DISK_TARGET_PCT: break
        delete_route(route)  # by-device 폴더 + by-car symlink 모두
        log(f"[cleanup] deleted {route}")
```

매 업로드마다 1회 호출 (또는 매 100회마다 호출하여 부담 감소).

### 3.6 메타 + symlink 생성

업로드 시:
1. `/srv/carrot_rlogs/by-device/<device>/<route>/<segment>/<filename>` 으로 저장
2. 헤더의 `X-Carrot-Car`를 라우트 폴더에 기록 (`car.txt` 같은 파일)
3. `/srv/carrot_rlogs/by-car/<car>/<device>__<route>/` 심볼릭 링크 생성 (이미 있으면 skip)

`route_meta.json`이 업로드되면 그것도 같은 위치에 저장.

---

## 4. PC 학습툴 통합 — gui.py / train.py

### 4.1 gui.py 신규 UI 항목

```
[ NAS endpoint ] : https://casroute.jominki354.live    ← 신규 (외부 URL)
[ NAS pull dir ] : E:\rlogs\nas                         ← 로컬 캐시
[ Pull from NAS ]                                       ← 신규 버튼
[ Filter by car ] : HYUNDAI_CASPER_EV ▼                  ← route_meta.json 기반
[ Filter by version ] : >= 0.1.0                         ← 신규
```

### 4.2 "Pull from NAS" 동작

3가지 경로 옵션:

**A. (권장) HTTP API로 라우트 목록 받고 rsync**
- gui.py가 서버에 `GET /list?car=...&since=...` 호출 → 라우트 목록 받음
- 이어서 `rsync -avz ...` 또는 HTTPS로 파일 받음
- 외부에서도 가능 (Cloudflare Tunnel 통해)

**B. (간단) sshfs 마운트**
- WSL에서 `sshfs carrot@<internal_or_tailscale_ip>:/srv/carrot_rlogs ~/nas`
- 내부망 또는 Tailscale 같은 VPN 필요

**C. (가장 간단) Windows SMB 마운트**
- LXC에 Samba 추가 설치
- Windows에서 네트워크 드라이브 매핑
- 내부망에서만 동작

**A를 기본**, B/C는 사용자 선택.

### 4.3 train.py / validate.py 메타 활용

학습 끝 후 출력 메타에 contributor 정보:

```
detected_car_names: {'HYUNDAI_CASPER_EV': 12000}
contributing_devices: {'ac960474': 8000, 'b1c2d3e4': 4000}
carrot_versions: {'0.1.0': 3000, '0.1.2': 9000}
```

학습 reproducibility 향상.

---

## 5. 보안/프라이버시 정리

### 보호 수준

| 위협 | 대응 |
|---|---|
| 봇이 랜덤 IP 스캔 중 발견해서 쓰레기 업로드 | HMAC secret + WAF (Cloudflare) |
| timestamp replay | ±5분 윈도우 |
| 디스크 풀 공격 | 파일 크기 cap + auto cleanup |
| 악성 동글 식별 | device_id로 폴더 격리, 블랙리스트 가능 |
| 일반 사용자 → 어떻게 옵트인 강제 X 가능? | 토글 default OFF |

### 프라이버시

- **rlog만 보냄** (위치/속도/조향 등 주행 신호)
- **qcamera 안 보냄** (영상 → 차량번호/얼굴 등 노출 위험)
- **GPS 좌표는?** rlog 안에 있음. 학습에 쓰진 않지만 raw 데이터에 포함됨. 필요시 업로드 전 마스킹 옵션 추가 가능.
- **개인 식별**: device_id로 동일 기기 추적 가능. 익명성 100% 아님.

배포 시 토글에 명시:
```
"주행 데이터 업로드"
ON: 카로트 학습용으로 익명 주행 로그(rlog) 전송
설명: 영상은 보내지 않습니다. 위치 정보가 로그에 포함될 수 있습니다.
   언제든 OFF로 중단 가능. 이미 올린 데이터는 영구 보관됩니다.
```

---

## 6. 운영

### 6.1 NAS 모니터링

- `df -h /srv/carrot_rlogs` 로 용량
- `journalctl -u carrot-upload` 로 서버 로그
- `journalctl -u cloudflared` 로 tunnel 상태

### 6.2 백업 정책

- rlog는 **재생산 가능** (기기에서 다시 받기 가능)
- 학습 모델 JSON은 별도 백업 (git에 박혀있음)
- ZFS scrub 정기 실행 (이미 자동)

### 6.3 사용자 사후 관리

- 사용자가 토글 OFF → 즉시 업로드 중단
- 데이터 삭제 요청 → 해당 device_id 폴더 통째 `rm -rf`
- 악성 device 차단 → blacklist 추가

---

## 7. 구현 체크리스트 (Phase A)

### 서버 측 (NAS LXC)

- [x] LXC 컨테이너 생성 (205, carrot-nas)
- [x] 1TB 데이터 볼륨 (`/srv/carrot_rlogs`)
- [x] SSH/rsync 설치 + carrot 계정 + GitHub 키 sync
- [x] Cloudflare Tunnel (`casroute.jominki354.live`)
- [x] Python venv + FastAPI 설치
- [ ] HMAC secret 생성 (32바이트)
- [ ] FastAPI server.py 작성
- [ ] cleanup.py 작성
- [ ] systemd 서비스 등록
- [ ] curl로 가짜 업로드 테스트

### 기기 측 (carrot fork)

- [ ] `selfdrive/carrot/cas/data_uploader.py` 작성
- [ ] `selfdrive/carrot/cas/uploader_state.py` 작성
- [ ] HMAC secret 파일 빌드 인클루드
- [ ] `route_meta.json` 생성 로직
- [ ] manager 등록
- [ ] `carrot_settings.json` 토글
- [ ] 기기 빌드 + 실차 1회 업로드 테스트

### PC 학습툴

- [ ] gui.py에 NAS endpoint 입력 + Pull 버튼
- [ ] train.py contributor 통계
- [ ] HTTP API `GET /list` (선택)

---

## 8. 향후 확장 (Phase B+)

- 영상 일부 (블러처리된 thumbnail) 옵션
- 사용자가 본인 데이터 다운로드 (`GET /my-data`)
- 사용자별 통계 페이지 (web UI)
- 다중 백엔드 (Cloudflare R2 / B2 추가) — NAS 풀 차면 자동 fallback

---

_최종 갱신: 2026-05-20. 이 문서는 firehose식 분산 데이터 수집 설계의 청사진._
