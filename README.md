# Framie Image Server

Framie의 배경 제거 전용 마이크로서비스. FastAPI + [rembg](https://github.com/danielgatis/rembg)로 인물 누끼(`u2net_human_seg`)를 처리해 투명 PNG를 반환합니다.

---

## 주요 기능

- **`POST /remove-bg`** — 이미지 업로드 시 인물 배경을 제거한 PNG를 응답
- **`GET /health`** — 헬스 체크
- **모델 사전 로딩 & 워밍업** — 앱 시작 시 세션을 1회 로드하고 더미 이미지로 추론을 한 번 돌려 첫 요청 지연 제거
- **스레드풀 실행** — CPU 바운드 작업을 `def` 엔드포인트로 선언해 FastAPI가 자동으로 threadpool에서 실행, 이벤트 루프 블로킹 방지
- **무손실 경량화** — `rembg.remove`가 반환한 PNG 바이트를 재인코딩 없이 그대로 응답

---

## 기술 스택

| 분류 | 사용 기술 |
|------|----------|
| Framework | FastAPI |
| 모델 | rembg (`u2net_human_seg`, ONNX Runtime) |
| 서버 | Uvicorn |

`requirements.txt`:
```
fastapi
uvicorn
python-multipart
rembg
Pillow
onnxruntime
```

---

## 시작하기

### 사전 요구사항
- Python 3.10+
- 첫 실행 시 `u2net_human_seg` 모델이 자동으로 다운로드됩니다 (`~/.u2net/`).

### 설치 & 실행

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

또는 모듈로 직접 실행:

```bash
python main.py
```

기본 주소: `http://localhost:8001`

---

## 환경 변수

| 키 | 설명 | 기본값 |
|----|------|--------|
| `HOST` | 바인딩 호스트 | `0.0.0.0` |
| `PORT` | 포트 | `8001` |

---

## API

### `GET /health`
헬스 체크.

**응답**
```json
{ "status": "ok" }
```

### `POST /remove-bg`
이미지에서 배경을 제거한 PNG를 반환합니다.

**요청**
- `Content-Type: multipart/form-data`
- 필드: `image` (이미지 파일, `image/*`)

**응답**
- `Content-Type: image/png`
- 본문: 배경이 제거된 PNG 바이트

**예시 (curl)**
```bash
curl -X POST http://localhost:8001/remove-bg \
  -F "image=@input.jpg" \
  --output removed_bg.png
```

**에러**
- `400` — 이미지가 아닌 파일을 업로드한 경우
- `500` — 처리 중 내부 오류

---

## 성능 최적화 노트

1. **세션 재사용** — `new_session("u2net_human_seg")`를 모듈 로드 시점에 1회 생성하고 모든 요청에서 재사용.
2. **시작 워밍업** — `@app.on_event("startup")`에서 1×1 더미 PNG로 한 번 추론해 ONNX 세션 초기화를 미리 완료.
3. **동기 엔드포인트** — `/remove-bg`를 `def`로 선언해 FastAPI가 자동으로 threadpool에서 실행 → 다른 요청이 블로킹되지 않음.
4. **불필요한 재인코딩 제거** — `remove()`가 이미 PNG 바이트를 반환하므로 PIL로 다시 열었다 저장하는 과정을 생략.

---

## 폴더 구조

```
framie_image_server/
├── main.py              # FastAPI 앱 · 엔드포인트 정의
├── requirements.txt
└── .gitignore
```

---

## 프로덕션 참고

- 모델이 CPU 기반 ONNX 추론이라 동시 처리량이 코어 수에 종속됩니다. 트래픽이 많다면 `uvicorn --workers N` 또는 `gunicorn -k uvicorn.workers.UvicornWorker -w N`로 워커 수를 늘리세요.
- GPU onnxruntime(`onnxruntime-gpu`)을 사용하면 추론 속도가 크게 향상됩니다.
- 모델 파일은 첫 호출 시 `~/.u2net/`에 다운로드되므로, 컨테이너 이미지에 포함해두면 콜드 스타트를 줄일 수 있습니다.
