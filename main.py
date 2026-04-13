import asyncio
import os

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from rembg import remove, new_session

app = FastAPI(title="Framie Image Server", version="1.0.0")

# rembg 처리 동시성을 제한해 CPU/메모리 급증을 완화한다.
REMBG_MAX_CONCURRENCY = int(os.getenv("REMBG_MAX_CONCURRENCY", "2"))
rembg_semaphore = asyncio.Semaphore(value=REMBG_MAX_CONCURRENCY)
inflight = 0
waiting = 0
counter_lock = asyncio.Lock()

# 사람 누끼 품질을 위해 u2net_human_seg 모델 사용.
# 앱 시작 시 한 번만 로드하고 모든 요청에서 재사용.
rembg_session = new_session("u2net_human_seg")


@app.on_event("startup")
def warmup_rembg():
    # ONNX 추론 세션은 실제 첫 호출 시 초기화되므로,
    # 더미 이미지로 한 번 돌려 첫 사용자 지연을 제거한다.
    try:
        # 최소 크기 PNG (1x1 투명)
        dummy_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05"
            b"\x00\x01\xff\xa7\xc5\x91\xc3\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        remove(dummy_png, session=rembg_session)
    except Exception as e:
        print(f"[warmup] rembg warmup skipped: {e}")


@app.get("/health")
async def health_check():
    return {"status": "ok", "inflight": inflight, "waiting": waiting}


@app.post("/remove-bg")
async def remove_background(image: UploadFile = File(...)):
    global inflight, waiting

    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="이미지 파일만 업로드할 수 있습니다.")

    acquired = False
    try:
        input_bytes = await image.read()
        async with counter_lock:
            waiting += 1
        try:
            await asyncio.wait_for(rembg_semaphore.acquire(), timeout=20)
            acquired = True
        except TimeoutError as e:
            raise HTTPException(
                status_code=503,
                detail="서버가 처리 중입니다. 잠시 후 다시 시도해주세요.",
            ) from e
        finally:
            async with counter_lock:
                waiting -= 1

        async with counter_lock:
            inflight += 1

        # rembg는 CPU-bound라 이벤트 루프를 막지 않도록 threadpool로 위임한다.
        output_bytes = await run_in_threadpool(remove, input_bytes, session=rembg_session)

        return Response(
            content=output_bytes,
            media_type="image/png",
            headers={"Content-Disposition": "inline; filename=removed_bg.png"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"배경 제거 처리 중 오류: {str(e)}")
    finally:
        if acquired:
            rembg_semaphore.release()
            async with counter_lock:
                inflight -= 1


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
