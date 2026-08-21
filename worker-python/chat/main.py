import json
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from llama_cpp import Llama
from pydantic import BaseModel

MODEL_PATH = os.environ.get("GENERATIVA_MODEL_PATH", "")
N_CTX = int(os.environ.get("GENERATIVA_N_CTX", "4096"))
N_THREADS = int(os.environ.get("GENERATIVA_N_THREADS", str(os.cpu_count() or 4)))

_llm: Llama | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _llm
    if not MODEL_PATH:
        print("[chat-worker] GENERATIVA_MODEL_PATH no está definido; el modelo se cargará bajo demanda desde /load")
    elif os.path.isfile(MODEL_PATH):
        print(f"[chat-worker] Cargando modelo desde {MODEL_PATH} (n_ctx={N_CTX}, n_threads={N_THREADS})")
        _llm = Llama(model_path=MODEL_PATH, n_ctx=N_CTX, n_threads=N_THREADS, verbose=False)
        print("[chat-worker] Modelo cargado")
    else:
        print(f"[chat-worker] ADVERTENCIA: no se encontró el archivo del modelo en {MODEL_PATH}")
    yield


app = FastAPI(title="Generativa Chat Worker", lifespan=lifespan)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    stream: bool = True
    temperature: float = 0.7
    max_tokens: int = 1024


class LoadRequest(BaseModel):
    model_path: str
    n_ctx: int = 4096
    n_threads: int | None = None


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": _llm is not None}


@app.post("/load")
def load_model(req: LoadRequest):
    global _llm
    if not os.path.isfile(req.model_path):
        raise HTTPException(status_code=400, detail=f"No existe el archivo: {req.model_path}")
    _llm = Llama(
        model_path=req.model_path,
        n_ctx=req.n_ctx,
        n_threads=req.n_threads or (os.cpu_count() or 4),
        verbose=False,
    )
    return {"status": "loaded", "model_path": req.model_path}


def _require_model() -> Llama:
    if _llm is None:
        raise HTTPException(status_code=503, detail="No hay un modelo cargado. Llama a /load primero.")
    return _llm


@app.post("/chat")
def chat(req: ChatRequest):
    llm = _require_model()
    messages = [m.model_dump() for m in req.messages]

    if not req.stream:
        result = llm.create_chat_completion(
            messages=messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            stream=False,
        )
        return result

    def event_stream():
        for chunk in llm.create_chat_completion(
            messages=messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            stream=True,
        ):
            delta = chunk["choices"][0]["delta"].get("content")
            if delta:
                yield f"data: {json.dumps({'content': delta})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8011)
