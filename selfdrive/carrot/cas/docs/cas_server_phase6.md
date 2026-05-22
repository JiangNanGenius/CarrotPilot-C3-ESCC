# CAS Server Phase 6

이 문서는 `carrot-nas` LXC의 업로드 서버를 repo 기준으로 관리하기 위한 배포/검증 메모다.

## 현재 확인된 서버 구조

```text
LXC 205: carrot-nas (Ubuntu 24.04)

cloudflared
  casroute.jominki354.live  -> http://localhost:8000
  casrouter.jominki354.live -> http://localhost:5244

carrot-upload.service
  WorkingDirectory=/opt/carrot-upload
  ExecStart=/opt/carrot-upload-venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000

alist.service
  /opt/alist/alist server

data
  /srv/carrot_rlogs/by-device/<device_id>/<route_id>/<seg>/{rlog.zst,qlog.zst}
  /srv/carrot_rlogs/by-device/<device_id>/<route_id>/route_meta.json
  /srv/carrot_rlogs/by-car/<car>/<device_id>__<route_id> -> symlink
```

구버전 `route_meta.json`은 `car`/`kind`가 비어 있을 수 있다. Phase 6 서버는 이 경우 `car.txt`를 보조로 보고, 그래도 없으면 `UNKNOWN_CAR / torque`로 manifest에 노출한다.

## Repo 기준 서버 파일

기준본:

```text
tools/cas/server/carrot_upload_server.py
```

배포 위치:

```text
/opt/carrot-upload/server.py
```

기존 업로드 API는 유지한다.

```text
POST /upload/{device_id}/{route_id}/{segment}/{filename}
```

추가 API:

```text
GET  /api/datasets?car_key=HYUNDAI_CASPER_EV&kind=torque
GET  /api/datasets/summary?car_key=HYUNDAI_CASPER_EV&kind=torque
GET  /api/routes?car_key=HYUNDAI_CASPER_EV&kind=torque&limit=500
GET  /api/devices/{device_id}/routes
GET  /download/{device_id}/{route_id}/{seg}/rlog.zst
GET  /download/{device_id}/{route_id}/{seg}/qlog.zst
POST /api/train-runs
GET  /api/train-runs/latest?car_key=HYUNDAI_CASPER_EV&kind=torque
```

## Read API 인증

업로드는 기존 HMAC secret을 그대로 사용한다.

Read API는 다음 파일이 있으면 bearer token을 요구한다.

```text
/etc/carrot-upload/read_token
```

권장:

```bash
pct exec 205 -- bash -lc 'install -d -m 700 /etc/carrot-upload && openssl rand -hex 32 > /etc/carrot-upload/read_token && chmod 600 /etc/carrot-upload/read_token'
```

파일이 없으면 read API는 열린다. 기존 AList 공개 운영과 맞추기 위한 호환 모드다.

## 배포

Proxmox host에서:

```bash
pct exec 205 -- bash -lc 'cp /opt/carrot-upload/server.py /opt/carrot-upload/server.py.bak.$(date +%Y%m%d_%H%M%S)'
```

repo의 `tools/cas/server/carrot_upload_server.py` 내용을 `/opt/carrot-upload/server.py`로 복사한다.

복사 후 문법 확인:

```bash
pct exec 205 -- bash -lc 'cd /opt/carrot-upload && /opt/carrot-upload-venv/bin/python3 -m py_compile server.py'
```

재시작:

```bash
pct exec 205 -- systemctl restart carrot-upload.service
pct exec 205 -- systemctl status carrot-upload.service --no-pager
```

## 서버 내부 검증

```bash
pct exec 205 -- curl -s http://127.0.0.1:8000/health
pct exec 205 -- curl -s 'http://127.0.0.1:8000/api/datasets?include_routes=false'
pct exec 205 -- curl -s 'http://127.0.0.1:8000/api/routes?device_id=ac960474&limit=3'
```

`read_token`을 만들었다면:

```bash
pct exec 205 -- bash -lc 'TOKEN=$(cat /etc/carrot-upload/read_token); curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8000/api/datasets?include_routes=false"'
```

외부 PC에서:

```powershell
curl.exe https://casroute.jominki354.live/health
curl.exe "https://casroute.jominki354.live/api/datasets?include_routes=false"
```

token 사용 시:

```powershell
curl.exe -H "Authorization: Bearer <token>" "https://casroute.jominki354.live/api/datasets?include_routes=false"
```

## 삭제 정책

서버 API는 GUI 학습 흐름에서 route 원본을 삭제하지 않는다.
PC GUI의 `delete_after_success`는 향후 다운로드된 PC 로컬 raw 파일에만 적용한다.

