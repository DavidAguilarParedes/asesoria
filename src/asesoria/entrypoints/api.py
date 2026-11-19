from fastapi import FastAPI

app = FastAPI(title="AsesorIA")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
