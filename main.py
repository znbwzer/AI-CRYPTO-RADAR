from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def home():
    return {
        "status": "online",
        "app": "AI CRYPTO RADAR",
        "version": "V1"
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok"
    }
