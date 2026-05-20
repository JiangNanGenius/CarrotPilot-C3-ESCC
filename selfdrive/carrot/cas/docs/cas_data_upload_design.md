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

### 식별자 — CarrotDeviceId (콤마 기본 ID 우선)

기기에 이미 있는 하드웨어 고정 ID를 우선 사용. 둘 다 없을 때만 UUID 생성.

**우선순위**:
1. **`DongleId`** — 콤마 정품 + 서버 등록 시 발급. 가장 안정적.
2. **`HardwareSerial`** — 하드웨어 (CPU 시리얼/IMEI) 유래. flash 해도 유지. 클론 포함 대부분 기기 보유.
3. **UUID 생성** — 1, 2 다 없으면 fallback.

최종 선택값은 `CarrotDeviceId` 에 캐싱. 한 번 정해지면 `DongleId`가 나중에 활성화돼도 안 바뀜 (같은 데이터 다른 id로 중복 업로드 방지).

```python
# selfdrive/carrot/cas/data_uploader.py
def get_device_id(params: Params) -> str:
    cached = _read_param_str(params, "CarrotDeviceId")
    if cached:
        return cached

    for source in ("DongleId", "HardwareSerial"):
        v = _read_param_str(params, source)
        if v and v.lower() not in ("unregistered", "none", "n/a"):
            params.put("CarrotDeviceId", v)
            return v

    new_id = uuid.uuid4().hex[:16]
    params.put("CarrotDeviceId", new_id)
    return new_id
```

- PERSISTENT 파라미터로 영구 캐싱
- 기기 와이프하면 다시 결정 (의도된 동작)
- 정품 콤마 → `DongleId` 사용
- 클론 → `HardwareSerial` 사용
- 둘 다 없는 특수 환경 → UUID

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

# 부록 A — 실제 구축된 환경 (2026-05-21 기준)

이 절은 청사진이 아니라 **실제로 박혀있는 상태 스냅샷**. 운영/디버깅/이전 시 참고.

## A.1 NAS 호스트 (Proxmox)

| 항목 | 값 |
|---|---|
| Proxmox 호스트명 | `mk1` |
| Proxmox 버전 | 9.1.4 |
| ZFS 풀 | `datapool` (RAIDZ1, 3×1TB WDC) — ⚠️ **DEGRADED** (1 디스크 FAULTED, redundancy 0) |
| Pool 용량 | 2.72TB raw / 1.86TB usable |
| Proxmox 스토리지 alias | `datapool-storage` (ZFS), `local-lvm` (시스템) |

### ZFS DEGRADED 상황

```
NAME                     STATE     READ WRITE CKSUM
datapool                 DEGRADED
  raidz1-0               DEGRADED
    sdb                  ONLINE
    7705461285373609670  FAULTED   was /dev/sdc1   ← 사라진 디스크
    sdc                  ONLINE
```

- 데이터 무결성은 OK (recent scrub 통과)
- 다음 디스크 1개 죽으면 풀 전체 손실
- 복구: 1TB SATA HDD 1개 추가 후 `zpool replace datapool 7705461285373609670 /dev/<new>`
- CAS rlog는 기기 원본에 남아있어 재업로드 가능 → 운영은 진행 가능

## A.2 LXC 컨테이너

| 항목 | 값 |
|---|---|
| CTID | **205** |
| Hostname | **carrot-nas** |
| OS | Ubuntu 24.04 LTS (template `ubuntu-24.04-standard_24.04-2_amd64.tar.zst`) |
| IP | **192.168.50.121** (정적, `gw=192.168.50.1`) |
| CPU | 2 코어 |
| RAM | 2GB (swap 512MB) |
| 시스템 디스크 | `local-lvm:vm-205-disk-0`, 8GB rootfs |
| 데이터 디스크 | `datapool-storage:subvol-205-disk-0`, **1TB**, `mp=/srv/carrot_rlogs` |
| unprivileged | 1 (보안상 권장) |
| onboot | 1 (Proxmox 부팅 시 자동 시작) |

생성 명령 기록:

```bash
pct create 205 local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst \
  --hostname carrot-nas \
  --cores 2 --memory 2048 --swap 512 \
  --rootfs local-lvm:8 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.50.121/24,gw=192.168.50.1 \
  --features nesting=1 \
  --unprivileged 1 \
  --onboot 1 \
  --password <비번>

pct set 205 -mp0 datapool-storage:1000,mp=/srv/carrot_rlogs
```

## A.3 도메인 / Cloudflare

| 항목 | 값 |
|---|---|
| Zone | `jominki354.live` (Cloudflare 관리, 무료 Plan) |
| Tunnel 이름 | `carrot-upload` |
| Tunnel ID | `3ec8aec7-f2d1-4e34-aa46-1bcf7b98f4dc` |
| Credentials | `/etc/cloudflared/3ec8aec7-...json` |
| Config | `/etc/cloudflared/config.yml` |
| 서브도메인 1 | **`casroute.jominki354.live`** → 업로드 API (`:8000`) |
| 서브도메인 2 | **`casrouter.jominki354.live`** → AList 관리 (`:5244`) |

Cloudflare DNS 레코드 (자동 생성):
- `casroute` CNAME → `<tunnel_id>.cfargotunnel.com` (Proxied ON)
- `casrouter` CNAME → 동일 (Proxied ON)

`config.yml` 내용:

```yaml
tunnel: 3ec8aec7-f2d1-4e34-aa46-1bcf7b98f4dc
credentials-file: /etc/cloudflared/3ec8aec7-f2d1-4e34-aa46-1bcf7b98f4dc.json

ingress:
  - hostname: casroute.jominki354.live
    service: http://localhost:8000
  - hostname: casrouter.jominki354.live
    service: http://localhost:5244
  - service: http_status:404
```

## A.4 인증 — HMAC secret

| 항목 | 값 |
|---|---|
| 위치 | `/etc/carrot-upload/secret` (root:root 0600) |
| 길이 | 64자 hex (32바이트) |
| 생성 명령 | `python3 -c "import secrets; print(secrets.token_hex(32))" > /etc/carrot-upload/secret` |
| 기기 측 박힘 | `selfdrive/carrot/cas/upload_config.py` `DEFAULT_SECRET` (소스 인라인) |
| 사용자 override | `/data/carrot_upload_secret` 파일로 기기에서 덮어쓰기 가능 |
| 회전 정책 | 현재 없음. 향후 필요 시 carrot 빌드 + 서버 양쪽 동시 갱신 |

서명 방식: `HMAC-SHA256(secret, f"{device_id}|{timestamp}")`. timestamp ±5분 윈도우.

## A.5 서비스 인벤토리

LXC 205 안에서 돌고 있는 서비스 3개 (systemd):

### A.5.1 `cloudflared` (Cloudflare tunnel 클라이언트)
- Binary: `/usr/bin/cloudflared` (apt deb 설치)
- Config: `/etc/cloudflared/config.yml`
- 메모리: ~16MB
- 자동 업데이트: 비활성화 (`--no-autoupdate`)
- 외부 트래픽 흐름: 모든 HTTPS → 4개 connection (QUIC, ICN icn01/icn06)
- 재시작: `systemctl restart cloudflared`

### A.5.2 `carrot-upload` (FastAPI 업로드 서버)
- 실행: `/opt/carrot-upload-venv/bin/uvicorn server:app`
- 코드: `/opt/carrot-upload/server.py`
- venv: `/opt/carrot-upload-venv/` (Python 3.12, fastapi + uvicorn + python-multipart)
- 포트: 127.0.0.1:8000 (외부 직접 노출 X, cloudflared만 닿음)
- 메모리: ~33MB 평상시 (cap **256MB**)
- 동시 처리: workers=1, `--limit-concurrency 4` (보수적)
- Max request body: 50MB
- 재시작: `systemctl restart carrot-upload`

systemd unit (`/etc/systemd/system/carrot-upload.service`):
```ini
[Unit]
Description=carrot CAS upload server
After=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/carrot-upload
ExecStart=/opt/carrot-upload-venv/bin/uvicorn server:app \
  --host 127.0.0.1 --port 8000 \
  --workers 1 \
  --limit-concurrency 4 \
  --limit-max-requests 10000 \
  --timeout-keep-alive 5
Restart=on-failure
RestartSec=5
LimitNOFILE=4096
MemoryMax=256M

[Install]
WantedBy=multi-user.target
```

### A.5.3 `alist` (파일 탐색기 / 관리자)
- Binary: `/opt/alist/alist` (v3.60.0 Go 단일 바이너리)
- 데이터: `/opt/alist/data/` (SQLite + config.json + log)
- 포트: 5244 (외부는 cloudflared 통해 casrouter 도메인)
- 메모리: ~127MB 평상시 (cap **256MB**)
- 관리자 계정: `admin` / **초기 비번 메모됨** (운영자가 안전한 곳에 보관)
- 등록된 storage: `Local` 드라이버, mount=`/`, root=`/srv/carrot_rlogs`
- WebDAV: `https://casrouter.jominki354.live/dav` (Windows 탐색기 마운트 가능)

## A.6 디렉토리 / 파일 위치

```
NAS LXC (205):
  /etc/cloudflared/
    config.yml                              ← tunnel ingress 설정
    3ec8aec7-...json                        ← tunnel credentials
  /etc/carrot-upload/
    secret                                  ← HMAC secret (mode 600)
  /etc/systemd/system/
    cloudflared.service
    carrot-upload.service
    alist.service
  /opt/carrot-upload/
    server.py                               ← FastAPI 코드 (216줄)
  /opt/carrot-upload-venv/                  ← Python venv
  /opt/alist/
    alist                                   ← Go binary
    data/
      config.json
      data.db                               ← AList 메타 SQLite
      log/
  /srv/carrot_rlogs/                        ← rlog 저장소 (1TB ZFS)
    by-device/
      <device_id>/<route>/<segment>/rlog.zst
      <device_id>/<route>/car.txt
      <device_id>/<route>/meta/route_meta.json
    by-car/
      <car>/<device_id>__<route>/           ← symlink → ../../by-device/...
```

## A.7 자원 사용 현황 (2026-05-21)

```
RAM      : 199MB / 2048MB   (9% — 1.8GB 여유)
CPU      : 모든 프로세스 0.0% (idle)
디스크    : 256KB / 1TB      (사실상 비어있음)

서비스별:
  cloudflared    16MB
  carrot-upload  33MB (cap 256MB, 12%)
  alist          127MB (cap 256MB, 50%)
  systemd 외      ~25MB
```

→ **현재 한가함. 50대 동시 클라이언트도 받음.**

## A.8 일상 운영 명령

### 상태 확인
```bash
systemctl status cloudflared carrot-upload alist --no-pager
free -h
df -h /srv/carrot_rlogs
```

### 로그 보기
```bash
journalctl -u carrot-upload -f                 # 실시간 업로드 로그
journalctl -u cloudflared -n 30 --no-pager     # tunnel 상태
journalctl -u alist -n 20 --no-pager           # AList
journalctl -u carrot-upload | grep cleanup     # 자동 정리 발동 이력
```

### Health check
```bash
# 내부
curl -s http://127.0.0.1:8000/health           # FastAPI
curl -s http://127.0.0.1:5244/                 # AList

# 외부 (Cloudflare 거쳐)
curl -s https://casroute.jominki354.live/health
curl -sI https://casrouter.jominki354.live/
```

### HMAC 테스트 업로드 (서버 검증)
```bash
SECRET=$(cat /etc/carrot-upload/secret)
DEVICE_ID="testdevice01"
TS=$(date +%s)
SIG=$(printf "%s|%s" "$DEVICE_ID" "$TS" | openssl dgst -sha256 -hmac "$SECRET" -hex | awk '{print $2}')
echo "test" > /tmp/rlog.zst
curl -s -X POST \
  -H "X-Carrot-TS: $TS" -H "X-Carrot-Sig: $SIG" \
  -H "X-Carrot-Version: test" -H "X-Carrot-Car: HYUNDAI_CASPER_EV" \
  --data-binary @/tmp/rlog.zst \
  "https://casroute.jominki354.live/upload/${DEVICE_ID}/test-route/0/rlog.zst"
```

### 자동 정리 임계값 조정
`/opt/carrot-upload/server.py` 상단 상수:
```python
DISK_WARN_PCT = 85       # cleanup 발동 임계
DISK_TARGET_PCT = 75     # 정리 목표
CLEANUP_EVERY_N = 100    # 매 N회 업로드마다 검사
```
변경 후 `systemctl restart carrot-upload`.

### 디스크 정리 수동 트리거 (필요 시)
```bash
# 가장 오래된 device/route 10개 보기
ls -1tr /srv/carrot_rlogs/by-device/*/ | head -20
# 특정 device 통째로 삭제
rm -rf /srv/carrot_rlogs/by-device/<device_id>/
```

### 컨테이너 재시작 (드물게 필요)
Proxmox 호스트에서:
```bash
pct reboot 205
```

## A.9 보안 운영

| 항목 | 현재 상태 |
|---|---|
| HMAC secret 노출 | 소스 코드(공개 git)에 박힘 — Phase A 한정. Phase C 시 빌드 시점 주입 검토 |
| AList admin 비번 | 초기 random, 운영자가 변경 권장 |
| SSH (carrot 계정) | GitHub 키 동기화 (`https://github.com/jominki354.keys`) |
| 외부 노출 포트 | Cloudflare Tunnel만 (직접 포트 포워딩 X) |
| Cloudflare WAF | 기본 활성 (Free plan 수준) |
| Rate limit | 미구현 (사용자 요청대로 — 운영하다 필요해지면 추가) |
| Blacklist | 미구현 (필요 시 server.py에 `BLACKLIST = {...}` 한 줄) |

## A.10 백업

| 대상 | 백업 정책 |
|---|---|
| `/srv/carrot_rlogs/` | 없음 (rlog는 기기 원본에서 재업로드 가능) |
| AList DB (`/opt/alist/data/data.db`) | 별도 백업 권장 (storage 설정/사용자) — 현재 미구성 |
| HMAC secret | 운영자가 별도 메모 권장 |
| Cloudflared credentials | `/etc/cloudflared/*.json` 분실 시 `cloudflared tunnel create` 재실행 필요 |
| Proxmox 측 백업 | PBS-backup 스토리지 존재 (LXC 205 백업 스케줄 설정 권장) |

## A.11 모니터링 — 운영 점검 주기

| 주기 | 점검 항목 |
|---|---|
| 매주 | `df -h /srv/carrot_rlogs` 디스크 사용량 추세 |
| 매주 | `systemctl status` 3개 서비스 active 여부 |
| 매월 | `journalctl --since "1 month ago" | grep -E "ERROR\|FAIL"` 오류 누적 |
| 분기 | ZFS scrub (`zpool scrub datapool`) — Proxmox에서 cron 등록 권장 |
| 분기 | AList admin 비번 회전 |
| 연 | HMAC secret 회전 (기기 빌드 + 서버 양쪽 동시 갱신) |

## A.12 알려진 이슈 / 향후 보완

- **ZFS DEGRADED**: 디스크 교체 전까지 redundancy 0. 우선순위 높음.
- **AdGuard DNS 캐싱**: PC 측이 AdGuard를 DNS로 쓰면 새 도메인의 NXDOMAIN 캐시 이슈 가능. `pct restart 103`으로 해소.
- **HMAC secret 공개**: 현재 git에 박힘. Phase C 진입 시 빌드 시점 secret 주입 방식 전환 필요.
- **클라이언트 동시 업로드**: 현재 직렬. 필요 시 데몬 측 ThreadPoolExecutor 도입.
- **server.py `GET /list` 엔드포인트 부재**: gui.py "Pull from NAS" 기능 가려면 추가 필요.

---

_부록 A 최종 갱신: 2026-05-21._
_본 문서는 firehose식 분산 데이터 수집 설계의 청사진 + 실제 구축 환경 스냅샷._
