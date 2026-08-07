from fastapi import FastAPI

from api.routes import documents, transcription

app = FastAPI(
    title="Speech & Document Extraction",
    description="Transcribe Bengali/English audio and extract structured data from lab report images.",
    version="1.0.0",
)

app.include_router(transcription.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
