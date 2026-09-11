from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import requests
import time
from pathlib import Path


app = FastAPI(
    title="AI CRYPTO RADAR",
    version="V1.1"
)


# =========================================================
# CONFIG
# =========================================================

BINANCE_API = "https://data-api.binance.vision"

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"


# =========================================================
# CACHE
# =========================================================

_exchange_cache = {
    "data": None,
    "time": 0
}

CACHE_SECONDS = 900


# =========================================================
# BINANCE REQUEST
# =========================================================

def binance_get(endpoint, params=None):

    url = BINANCE_API + endpoint

    response = requests.get(
        url,
        params=params,
        timeout=15,
        headers={
            "User-Agent": "AI-CRYPTO-RADAR/1.0"
        }
    )

    response.raise_for_status()

    return response.json()


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def home():

    index_file = FRONTEND_DIR / "index.html"

    if index_file.exists():
        return FileResponse(index_file)

    return {
        "status": "online",
        "app": "AI CRYPTO RADAR",
        "version": "V1.1"
    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/api/health")
def health():

    return {
        "status": "ok",
        "app": "AI CRYPTO RADAR",
        "version": "V1.1"
    }


# =========================================================
# SYSTEM STATUS
# =========================================================

@app.get("/api/status")
def status():

    return {
        "status": "online",
        "app": "AI CRYPTO RADAR",
        "version": "V1.1",
        "binance": "testing"
    }


# =========================================================
# BINANCE CONNECTION TEST
# =========================================================

@app.get("/api/binance-test")
def binance_test():

    try:

        ping_start = time.time()

        binance_get("/api/v3/ping")

        ping_ms = round(
            (time.time() - ping_start) * 1000
        )

        server_time = binance_get(
            "/api/v3/time"
        )

        return {
            "status": "ok",
            "binance": "connected",
            "ping_ms": ping_ms,
            "server_time": server_time.get(
                "serverTime"
            )
        }

    except Exception as e:

        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "binance": "not_connected",
                "error": str(e)
            }
        )


# =========================================================
# BINANCE EXCHANGE INFO
# =========================================================

def get_exchange_info():

    now = time.time()

    if (
        _exchange_cache["data"] is not None
        and now - _exchange_cache["time"] < CACHE_SECONDS
    ):
        return _exchange_cache["data"]

    data = binance_get(
        "/api/v3/exchangeInfo"
    )

    _exchange_cache["data"] = data
    _exchange_cache["time"] = now

    return data


# =========================================================
# MARKET DATA
# =========================================================

@app.get("/api/market")
def market():

    try:

        exchange_info = get_exchange_info()

        allowed_symbols = set()

        for symbol in exchange_info.get(
            "symbols",
            []
        ):

            if (
                symbol.get("status") == "TRADING"
                and symbol.get("quoteAsset") == "USDT"
                and symbol.get("isSpotTradingAllowed", True)
            ):
                allowed_symbols.add(
                    symbol.get("symbol")
                )

        tickers = binance_get(
            "/api/v3/ticker/24hr"
        )

        market_data = []

        for ticker in tickers:

            symbol = ticker.get("symbol")

            if symbol not in allowed_symbols:
                continue

            try:

                price = float(
                    ticker.get("lastPrice", 0)
                )

                change = float(
                    ticker.get("priceChangePercent", 0)
                )

                volume = float(
                    ticker.get("volume", 0)
                )

                quote_volume = float(
                    ticker.get("quoteVolume", 0)
                )

            except:

                continue

            market_data.append({
                "symbol": symbol,
                "price": price,
                "change_24h": change,
                "volume": volume,
                "quote_volume": quote_volume
            })


        # Sort by USDT trading volume

        market_data.sort(
            key=lambda x: x["quote_volume"],
            reverse=True
        )


        # Top 30 only for dashboard

        top = market_data[:30]


        return {
            "status": "ok",
            "count": len(market_data),
            "showing": len(top),
            "coins": top,
            "updated": int(time.time())
        }


    except Exception as e:

        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "error": str(e)
            }
        )


# =========================================================
# STATIC FILES
# =========================================================

if FRONTEND_DIR.exists():

    app.mount(
        "/static",
        StaticFiles(
            directory=FRONTEND_DIR
        ),
        name="static"
    )
