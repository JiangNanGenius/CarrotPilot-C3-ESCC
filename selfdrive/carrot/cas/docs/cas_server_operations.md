# CAS Server — 운영 / 구조 / 지침

> CAS 서버 측 (LXC 205 `carrot-nas`)의 운영 문서.
> 코드 구조, 폴더 구조, 명명 규칙, API 명세, 인증, 배포 방법, 마이그레이션 절차까지.
>
> 관련 문서:
> - [cas_data_upload_design.md](cas_data_upload_design.md) — 업로드 파이프라인 초기 설계
> - [cas_server_phase6.md](cas_server_phase6.md) — Phase 6 (이 문서가 후속)
> - [cas_design.md](cas_design.md) — CAS 시스템 전체 설계

---

## 0. 한눈에

```
[기기]                  [서버 (LXC 205)]                 [PC]
data_uploader      ──→  carrot-upload (FastAPI)   ←──  cloud_sync / gui_flet
model_puller       ←──  /api/models/...           ←──  publish (학습 끝나면 자동)
```

- **목적**: 차량 rlog 수집 + 차종별 모델 OTA 배포
- **저장소**: 1TB ZFS (LXC 205 mount /srv/carrot_rlogs)
- **외부 접근**: Cloudflare Tunnel → `casroute.jominki354.live`
- **인증**: HMAC-SHA256, 동일 시크릿 디바이스/PC 공용
- **분류 기준**: `CarSelected3` 정규화 (CarrotWeb 표시명 기준, year 포함)

---

## 1. 인프라

### 1.1 Proxmox 호스트

| 항목 | 값 |
|---|---|
| 호스트명 | `mk1` |
| Proxmox 버전 | 9.1.4 |
| 스토리지 | `datapool-storage` (ZFS, 데이터) + `local-lvm` (시스템) |

### 1.2 LXC 컨테이너 (CTID 205)

| 항목 | 값 |
|---|---|
| Hostname | `carrot-nas` |
| Distro | Ubuntu 24.04 LTS |
| 시스템 디스크 | `local-lvm:vm-205-disk-0` 8GB rootfs |
| 데이터 디스크 | `datapool-storage:subvol-205-disk-0` **1TB**, mp=`/srv/carrot_rlogs` |
| onboot | 1 (호스트 부팅 시 자동) |

### 1.3 systemd 서비스 (LXC 205 안)

| 서비스 | 실행 | 메모리 cap |
|---|---|---|
| `cloudflared` | `/usr/bin/cloudflared` (apt deb) | ~16MB |
| `carrot-upload` | `/opt/carrot-upload-venv/bin/uvicorn server:app` | 256MB |
| `alist` | `/opt/alist/alist` (Go 단일 바이너리, 5244 포트) | 256MB |

`carrot-upload` 서비스 정의:
```ini
# /etc/systemd/system/carrot-upload.service
[Unit]
Description=carrot CAS upload server
After=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/carrot-upload
ExecStart=/opt/carrot-upload-venv/bin/uvicorn server:app \
  --host 127.0.0.1 --port 8000 \
  --workers 1 --limit-concurrency 4 \
  --limit-max-requests 10000 --timeout-keep-alive 5
Restart=on-failure
RestartSec=5
LimitNOFILE=4096
MemoryMax=256M
```

### 1.4 Cloudflare Tunnel

| 경로 | 내부 |
|---|---|
| `casroute.jominki354.live` | `http://localhost:8000` (carrot-upload) |
| `casrouter.jominki354.live` | `http://localhost:5244` (alist) |

---

## 2. 폴더 구조 (Phase 6 — 신규)

### 2.1 신규 구조 (적용 후)

```
/srv/carrot_rlogs/                              ← BASE
│
├── device/                                     ← (1) 디바이스 기준 raw 데이터 정본
│   └── <device_id>/                            예: ac960474
│       ├── routes/
│       │   └── <route_id>/                     예: 00000049--2c4e3d1cc2
│       │       ├── route_meta.json
│       │       ├── car.txt
│       │       └── <segment>/                  예: 0, 1, 2, ...
│       │           ├── rlog.zst
│       │           └── qlog.zst
│       ├── personal_models/                    ← 🟡 FUTURE: 디바이스 개인화
│       │   └── <kind>/
│       │       ├── latest.json
│       │       └── <YYYYMMDD_HHMMSS>.json
│       └── device_meta.json                    ← 🟡 FUTURE
│
├── car/                                        ← (2) 차종 집계 (심볼릭 + 요약)
│   └── <car_key>/                              예: HYUNDAI_CASPER_EV_2024
│       ├── routes/
│       │   └── <device_id>__<route_id>         → 심볼릭 ../../../device/.../routes/...
│       └── car_summary.json                    ← 🟡 FUTURE: 차종 총계
│
├── model/                                      ← (3) OTA 배포용 학습 모델
│   └── <car_key>/
│       └── <kind>/                             torque 또는 angle
│           ├── latest.json                     ← 포인터
│           └── <YYYYMMDD_HHMMSS>.json          ← 버전별 (역사 자동 보존)
│
└── server_train_runs.json                      ← PC 학습 이력 모음
```

### 2.2 폴더 책임

| 폴더 | 역할 | 데이터 손실 시 영향 |
|---|---|---|
| **`device/`** | rlog 정본 | 큼 (서버에서 데이터 사라짐, 재업로드 필요) |
| **`car/`** | 심볼릭 집계 뷰 | 작음 (자동 재생성 가능) |
| **`model/`** | OTA 배포 산출물 | 중간 (PC에서 재발행 가능) |

---

## 3. 명명 규칙

### 3.1 차량 식별자 (`car_key`)

**원천**: CarrotWeb의 `CarSelected3` → 정규화.

```
CarrotWeb 표시명             →  car_key (서버 정규화)
─────────────────────────────────────────────────────
"Hyundai Casper EV 2024"     →  HYUNDAI_CASPER_EV_2024
"Hyundai Elantra 2017-18"    →  HYUNDAI_ELANTRA_2017_18
"Hyundai Elantra 2019"       →  HYUNDAI_ELANTRA_2019
"Hyundai Elantra 2021-23"    →  HYUNDAI_ELANTRA_2021_23
"Hyundai Ioniq 5 2022-24"    →  HYUNDAI_IONIQ_5_2022_24
```

**정규화 규칙** (서버 `_norm_car_key`):
- 영숫자만 남기고 나머지는 `_`로 변환
- 연속 `_`는 하나로 합침
- 앞뒤 `_` 제거
- 결과가 `[A-Z0-9_]{2,64}$` 정규식 통과해야 유효

### 3.2 카키 우선순위 체인 (디바이스 `build_route_meta`)

```
car_key = CarSelected3        ← 1순위 (CarrotWeb 사용자 명시 선택, year 포함)
       or carFingerprint     ← 2순위 (carParams.carFingerprint)
       or CarName            ← 3순위 (Params CarName)
       or CarrotLastCarName  ← 4순위 (직전 부팅의 마지막 식별값)
```

### 3.3 카키 lookup 체인 (서버 `_car_key_from_meta`)

```
("car_key", "car", "car_name_raw", "last_known_car", "car_selected")
```

- `car_key`: 디바이스가 이미 정규화한 결과 (1순위)
- 나머지는 fallback (디바이스가 정규화 못 했거나 옛 클라이언트)

### 3.4 모델 버전

```
trained_at ISO "2026-05-22T15:30:00+00:00"  →  version "20260522_153000"
```

파일명: `<YYYYMMDD_HHMMSS>.json`. 시간순 자연 정렬.

### 3.5 EPS 펌웨어 해시

**참고용만**. 매칭/분류 기준 X. 서버 `_car_key_from_meta` 체인에 절대 포함 안 함.

---

## 4. API 명세

### 4.1 데이터 업로드 (HMAC 필요)

```
POST /upload/{device_id}/{route_id}/{segment}/{filename}
Headers:
  X-Carrot-TS:      <unix_timestamp>
  X-Carrot-Sig:     HMAC-SHA256(secret, "<device_id>|<ts>")
  X-Carrot-Version: <carrot_git_commit_12char>
  X-Carrot-Car:     <car_key>       (optional)
  X-Carrot-EpsHash: <eps_hash>      (optional, 참고용)
  X-Carrot-CasModel: <model_name>   (optional, 참고용)
Body: 파일 raw bytes (max 50MB)

segment="meta" 일 때는 route 단위 메타 (filename=route_meta.json)
```

### 4.2 데이터 조회 (read token 옵션)

```
GET /api/datasets?car_key=&kind=&device_id=&include_routes=true
GET /api/routes?car_key=&kind=&device_id=&limit=500
GET /download/{device_id}/{route_id}/{segment}/{filename}
POST /api/train-runs                              ← PC가 학습 끝나면 이력 등록
```

### 4.3 모델 OTA (Phase A-C에서 추가)

```
POST /api/models/upload/{car}/{kind}              ← PC publish
Headers:
  X-Carrot-TS:  <ts>
  X-Carrot-Sig: HMAC-SHA256(secret, "model|<ts>")
Body: 모델 JSON (CAS feature_schema 검증 필수)

GET /api/models/{car}/{kind}/latest               ← 최신 정보
GET /api/models/{car}/{kind}/download/{version}   ← 다운로드
GET /api/models                                    ← 전체 카탈로그
```

### 4.4 헬스

```
GET /health     → {"ok": true, "disk_pct": ..., "routes": ...}
```

---

## 5. 인증

### 5.1 업로드 인증 (HMAC)

| 키 위치 | 권한 |
|---|---|
| 서버 | `/etc/carrot-upload/secret` (root:root 0600) |
| 디바이스 | `selfdrive/carrot/cas/upload_config.py` `DEFAULT_SECRET` (코드 박힘) |
| PC | 위 코드 import로 사용 |

**시그니처 메시지**:
- 데이터 업로드: `"<device_id>|<ts>"`
- 모델 publish: `"model|<ts>"`
- 시간 윈도우: ±5분 (`TS_WINDOW = 300`)

### 5.2 읽기 API 인증 (옵션)

`/etc/carrot-upload/read_token` 파일 있으면 `/api/*`와 `/download/*`가 `Authorization: Bearer <token>` 요구. 없으면 read 무인증.

---

## 6. 접근 방법

### 6.1 SSH (LXC 직접 또는 호스트 경유)

```bash
# 옵션 A: LXC IP 직접 (LXC에 SSH server 있을 때)
ssh root@<lxc-205-ip>

# 옵션 B: Proxmox 호스트 경유
ssh root@mk1
pct enter 205
```

### 6.2 파일 편집 — 드래그앤드롭 방식

| 도구 | 설치 | 사용 |
|---|---|---|
| **VS Code Remote-SSH** ⭐ | "Remote - SSH" 확장 (이미 VS Code 있으면 1분) | 좌측 `><` → Connect → 폴더 열기 |
| **WinSCP** | 무료 | SFTP 접속 → 좌우 양창 드래그드롭 |
| **FileZilla** | 무료, 크로스 플랫폼 | SFTP 접속 |
| **PowerShell scp** | Windows 기본 내장 | `scp file root@lxc:/opt/...` |
| **AList 업로드** | 이미 떠있음 (5244) | 웹 UI에서 업로드 (관리자 설정 필요) |

**가장 추천: VS Code Remote-SSH**. nano보다 훨씬 편하고, 같은 SSH 통로로 작동, 변경 즉시 LXC 파일에 반영.

### 6.3 AList (브라우저 탐색)

`https://casrouter.jominki354.live` → `/srv/carrot_rlogs/` 전체 트리 브라우저로 확인. 읽기 전용 권장.

---

## 7. 배포 (코드 변경 → 서버 반영)

### 7.1 권장 순서

1. **PC에서 코드 변경 + git commit + push** (이 repo)
2. **LXC 측 코드 갱신** (옵션 중 택 1):
   - **VS Code Remote-SSH로 편집** ← 권장
   - **WinSCP로 파일 업로드**
   - **PowerShell scp**: `scp tools/cas/server/carrot_upload_server.py root@<lxc-ip>:/opt/carrot-upload/server.py`
   - **Proxmox 호스트에서 `pct push`**: `pct push 205 /tmp/server.py /opt/carrot-upload/server.py`
   - **nano로 직접 편집** (작은 변경만)
3. **서비스 재시작**: `systemctl restart carrot-upload`
4. **검증**:
   ```bash
   systemctl status carrot-upload --no-pager
   curl -s http://localhost:8000/health
   ```

### 7.2 코드 위치 매핑

| repo 경로 | LXC 경로 |
|---|---|
| `tools/cas/server/carrot_upload_server.py` | `/opt/carrot-upload/server.py` |
| `selfdrive/carrot/cas/upload_config.py` | (LXC엔 없음, 디바이스 코드만) |

---

## 8. 마이그레이션 (Phase 5 → Phase 6, by-device → device)

### 8.1 사전 조건
- PC repo 최신 (서버 코드 변경 commit 됨)
- LXC root 접근

### 8.2 절차

**1) 전체 데이터 삭제** (재업로드할 거라서):
```bash
# LXC 205
systemctl stop carrot-upload
rm -rf /srv/carrot_rlogs/by-device/* /srv/carrot_rlogs/by-car/*
rm -rf /srv/carrot_models/*
rm -f /srv/carrot_rlogs/server_train_runs.json

# 새 구조 생성
mkdir -p /srv/carrot_rlogs/{device,car,model}
# 옛 폴더 삭제 (코드 변경 후 미사용)
rmdir /srv/carrot_rlogs/by-device /srv/carrot_rlogs/by-car 2>/dev/null
rm -rf /srv/carrot_models 2>/dev/null
```

**2) 서버 코드 갱신** (VS Code Remote-SSH 또는 WinSCP로):
- `/opt/carrot-upload/server.py` 신규본 덮어쓰기 (path 상수 변경 반영본)

**3) 서비스 재시작**:
```bash
systemctl start carrot-upload
systemctl status carrot-upload --no-pager
```

**4) 디바이스 리셋 + 재업로드** (디바이스 측):
```bash
# comma device
cd /data/openpilot && git pull
rm -f /data/cas_upload_state.json
rm -rf /data/cas_weights/*
sudo reboot
```

**5) PC 캐시 정리**:
```powershell
rm -r D:\rlog\.cas\cloud_cache -Recurse -Force
rm D:\rlog\.cas\train_runs.json -Force
```

**6) 검증**:
- AList에서 `/srv/carrot_rlogs/device/`에 데이터 누적 시작 확인
- `/srv/carrot_rlogs/car/`에 차종별 심볼릭 생성 확인
- PC GUI 새로고침 → 데이터셋 표시 확인

---

## 9. 운영 런북

### 9.1 일상 점검

```bash
# 서비스 상태
systemctl status carrot-upload --no-pager

# 최근 로그
journalctl -u carrot-upload -n 100 --no-pager

# 디스크 사용
df -h /srv/carrot_rlogs

# 업로드 카운트
ls /srv/carrot_rlogs/device/ | wc -l               # 디바이스 수
find /srv/carrot_rlogs/device/ -name "rlog.zst" | wc -l   # 세그먼트 수
```

### 9.2 자동 클린업

서버 `_cleanup_if_needed`가 디스크 사용률 추적:
- `DISK_WARN_PCT = 85` 넘으면 cleanup 시작
- `DISK_TARGET_PCT = 75`까지 가장 오래된 route 삭제
- 100개 업로드마다 한 번 체크 (`CLEANUP_EVERY_N`)

### 9.3 백업

| 데이터 | 백업 권장 빈도 | 방법 |
|---|---|---|
| `server_train_runs.json` | 매일 (cron) | rsync to remote |
| `/srv/carrot_rlogs/model/` | 매 발행 시 (트리거) | PC가 publish 후 로컬 사본 보관 (이미 됨) |
| `/srv/carrot_rlogs/device/` | 주간 (선택) | rsync — 크기 크므로 선택적 |

### 9.4 트러블슈팅

| 증상 | 진단 | 해결 |
|---|---|---|
| HTTP 401 bad signature | 시각/시크릿 불일치 | 디바이스 시계 + secret 파일 확인 |
| HTTP 413 too large | 파일 50MB 초과 | rlog가 비정상 크기 — 디바이스 점검 |
| 서비스 OOM | 동시 큰 업로드 | `MemoryMax`/`limit-concurrency` 조정 |
| 디스크 가득 | rlog 누적 | `_cleanup_if_needed` 동작 확인, `DISK_TARGET_PCT` 낮춤 |
| SSL "not yet valid" | 클라이언트 클록 회귀 | 클라이언트 NTP 동기화 |

---

## 10. 변경 이력

| 일자 | 변경 |
|---|---|
| 2026-05-20 | Phase 0 인프라 (data_uploader + 서버 초기) |
| 2026-05-21 | upload sync 정착 (cloud_sync, 사용자 토글) |
| 2026-05-22 | Phase A/B/C OTA — 모델 publish + device puller |
| 2026-05-23 | **Phase 6 폴더 재구성** — `device/`/`car/`/`model/` 3분할, CarSelected3 기준 명명 (이 문서) |

---

## 11. TODO (Phase 6 이후)

- [ ] `device/<dev>/personal_models/` 구조 활용 — 사용자별 개인화 학습
- [ ] `car/<key>/car_summary.json` 자동 생성 — 차종별 누적 메트릭
- [ ] 모델 롤백 UI (PC GUI에서 이전 버전 클릭)
- [ ] 디바이스 puller 알림 (HUD에 "새 모델 적용됨")
- [ ] EPS 펌웨어별 모델 분리 정책 (필요시)
- [ ] 차종 alias 테이블 (CarSelected3 신·구 표시명 매핑)
