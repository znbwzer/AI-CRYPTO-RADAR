from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from contextlib import asynccontextmanager

from pathlib import Path

import asyncio
import threading
import time


from database import (
    create_db,
    save_signal,
    get_signals,
    clear_old_signals
)

from scanner import scan_market


BASE_DIR = Path(__file__).resolve().parent

FRONTEND_DIR = (
    BASE_DIR / "frontend"
)


latest_results = []

scanner_status = {
    "running": False,
    "last_scan": None,
    "last_error": None,
    "coins_found": 0
}


def scanner_worker():

    global latest_results

    scanner_status["running"] = True


    while True:

        try:

            print(
                "🐋 Starting market scan..."
            )

            results = scan_market(
                max_symbols=100
            )

            latest_results = results


            for item in results:

                if item["score"] >= 70:

                    save_signal(
                        symbol=item["symbol"],
                        score=item["score"],
                        price=item["price"],
                        reasons=", ".join(
                            item["reasons"]
                        )
                    )


            clear_old_signals()


            scanner_status[
                "last_scan"
            ] = time.strftime(
                "%Y-%m-%d %H:%M:%S UTC",
                time.gmtime()
            )

            scanner_status[
                "coins_found"
            ] = len(results)

            scanner_status[
                "last_error"
            ] = None


            print(
                f"✅ Scan complete. "
                f"Found {len(results)} opportunities."
            )


        except Exception as error:

            scanner_status[
                "last_error"
            ] = str(error)

            print(
                f"❌ Scanner Error: {error}"
            )


        # Wait 60 seconds
        time.sleep(60)


@asynccontextmanager
async def lifespan(app):

    create_db()


    thread = threading.Thread(
        target=scanner_worker,
        daemon=True
    )

    thread.start()


    yield


app = FastAPI(
    title="AI CRYPTO RADAR",
    lifespan=lifespan
)


# =============================
# API
# =============================

@app.get("/api/status")

def get_status():

    return scanner_status


@app.get("/api/results")

def get_results():

    return latest_results


@app.get("/api/signals")

def signals():

    return get_signals(100)


@app.get("/api/health")

def health():

    return {
        "status": "online",
        "message":
        "AI CRYPTO RADAR is running"
    }


# =============================
# FRONTEND
# =============================

app.mount(
    "/static",
    StaticFiles(
        directory=str(FRONTEND_DIR)
    ),
    name="static"
)


@app.get("/")

def home():

    return FileResponse(
        FRONTEND_DIR / "index.html"
    )
