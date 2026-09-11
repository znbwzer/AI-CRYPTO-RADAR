from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import requests
import time
import statistics
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


app = FastAPI(
    title="AI CRYPTO RADAR",
    version="1.2"
)


# =========================================================
# CONFIG
# =========================================================

BINANCE_API = "https://data-api.binance.vision"

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

SCAN_LIMIT = 80
KLINE_LIMIT = 100

REQUEST_TIMEOUT = 12


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
        timeout=REQUEST_TIMEOUT,
        headers={
            "User-Agent": "AI-CRYPTO-RADAR/1.2"
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
        "version": "1.2"
    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/api/health")
def health():

    return {
        "status": "ok",
        "app": "AI CRYPTO RADAR",
        "version": "1.2"
    }


# =========================================================
# STATUS
# =========================================================

@app.get("/api/status")
def status():

    return {
        "status": "online",
        "app": "AI CRYPTO RADAR",
        "version": "1.2",
        "binance": "connected"
    }


# =========================================================
# BINANCE TEST
# =========================================================

@app.get("/api/binance-test")
def binance_test():

    try:

        start = time.time()

        binance_get("/api/v3/ping")

        ping_ms = round(
            (time.time() - start) * 1000
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
# EXCHANGE INFO
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
# EMA
# =========================================================

def calculate_ema(values, period):

    if len(values) < period:
        return values[-1]

    multiplier = 2 / (period + 1)

    ema = sum(values[:period]) / period

    for price in values[period:]:

        ema = (
            (price - ema) * multiplier
        ) + ema

    return ema


# =========================================================
# RSI
# =========================================================

def calculate_rsi(values, period=14):

    if len(values) <= period:
        return 50

    gains = []
    losses = []

    for i in range(1, len(values)):

        change = values[i] - values[i - 1]

        if change > 0:
            gains.append(change)
            losses.append(0)

        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(
        gains[:period]
    ) / period

    avg_loss = sum(
        losses[:period]
    ) / period

    for i in range(period, len(gains)):

        avg_gain = (
            (avg_gain * (period - 1))
            + gains[i]
        ) / period

        avg_loss = (
            (avg_loss * (period - 1))
            + losses[i]
        ) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (
        100 / (1 + rs)
    )


# =========================================================
# NORMALIZE
# =========================================================

def clamp(value, minimum=0, maximum=100):

    return max(
        minimum,
        min(maximum, value)
    )


# =========================================================
# ANALYZE ONE COIN
# =========================================================

def analyze_symbol(symbol, ticker):

    try:

        klines = binance_get(
            "/api/v3/klines",
            {
                "symbol": symbol,
                "interval": "15m",
                "limit": KLINE_LIMIT
            }
        )

        if len(klines) < 50:
            return None

        closes = [
            float(k[4])
            for k in klines
        ]

        volumes = [
            float(k[5])
            for k in klines
        ]

        quote_volumes = [
            float(k[7])
            for k in klines
        ]

        highs = [
            float(k[2])
            for k in klines
        ]

        lows = [
            float(k[3])
            for k in klines
        ]


        # =================================================
        # PRICE
        # =================================================

        price = closes[-1]

        change_24h = float(
            ticker.get(
                "priceChangePercent",
                0
            )
        )

        quote_volume_24h = float(
            ticker.get(
                "quoteVolume",
                0
            )
        )


        # =================================================
        # EMA
        # =================================================

        ema9 = calculate_ema(
            closes,
            9
        )

        ema21 = calculate_ema(
            closes,
            21
        )

        ema50 = calculate_ema(
            closes,
            50
        )


        # =================================================
        # RSI
        # =================================================

        rsi = calculate_rsi(
            closes,
            14
        )


        # =================================================
        # VOLUME RATIO
        # =================================================

        recent_volumes = volumes[-20:-1]

        average_volume = (
            sum(recent_volumes)
            / len(recent_volumes)
        )

        current_volume = volumes[-1]

        volume_ratio = (
            current_volume
            / average_volume
            if average_volume > 0
            else 1
        )


        # =================================================
        # MOMENTUM
        # =================================================

        price_5 = closes[-6]

        momentum_5 = (
            ((price - price_5)
             / price_5) * 100
            if price_5 > 0
            else 0
        )


        price_20 = closes[-21]

        momentum_20 = (
            ((price - price_20)
             / price_20) * 100
            if price_20 > 0
            else 0
        )


        # =================================================
        # TREND
        # =================================================

        trend_score = 0

        if price > ema9:
            trend_score += 25

        if ema9 > ema21:
            trend_score += 30

        if ema21 > ema50:
            trend_score += 25

        if momentum_5 > 0:
            trend_score += 10

        if momentum_20 > 0:
            trend_score += 10


        # =================================================
        # RSI SCORE
        # =================================================

        if 50 <= rsi <= 65:

            rsi_score = 100

        elif 65 < rsi <= 72:

            rsi_score = 85

        elif 45 <= rsi < 50:

            rsi_score = 65

        elif rsi > 72:

            rsi_score = 45

        else:

            rsi_score = 35


        # =================================================
        # VOLUME SCORE
        # =================================================

        if volume_ratio >= 4:
            volume_score = 100

        elif volume_ratio >= 3:
            volume_score = 90

        elif volume_ratio >= 2:
            volume_score = 75

        elif volume_ratio >= 1.5:
            volume_score = 60

        elif volume_ratio >= 1:
            volume_score = 40

        else:
            volume_score = 20


        # =================================================
        # MOMENTUM SCORE
        # =================================================

        momentum_score = 50

        if momentum_5 >= 3:
            momentum_score = 100

        elif momentum_5 >= 2:
            momentum_score = 90

        elif momentum_5 >= 1:
            momentum_score = 75

        elif momentum_5 > 0:
            momentum_score = 60

        elif momentum_5 < -3:
            momentum_score = 15

        elif momentum_5 < 0:
            momentum_score = 35


        # =================================================
        # LIQUIDITY SCORE
        # =================================================

        if quote_volume_24h >= 100000000:
            liquidity_score = 100

        elif quote_volume_24h >= 50000000:
            liquidity_score = 95

        elif quote_volume_24h >= 10000000:
            liquidity_score = 85

        elif quote_volume_24h >= 5000000:
            liquidity_score = 75

        elif quote_volume_24h >= 1000000:
            liquidity_score = 60

        else:
            liquidity_score = 35


        # =================================================
        # EARLY EXPLOSION SCORE
        # =================================================

        explosion_score = (
            trend_score * 0.25
            + volume_score * 0.25
            + momentum_score * 0.20
            + rsi_score * 0.15
            + liquidity_score * 0.15
        )

        explosion_score = round(
            clamp(explosion_score)
        )


        # =================================================
        # SIGNAL
        # =================================================

        if explosion_score >= 85:

            signal = "🚀 انفجار محتمل"

        elif explosion_score >= 75:

            signal = "🟢 تجميع قوي"

        elif explosion_score >= 65:

            signal = "🟡 مراقبة"

        elif explosion_score >= 50:

            signal = "⚪ ضعيف"

        else:

            signal = "🔴 لا توجد طاقة كافية"


        # =================================================
        # RANGE / VOLATILITY
        # =================================================

        recent_ranges = []

        for i in range(
            max(0, len(klines) - 20),
            len(klines)
        ):

            high = highs[i]
            low = lows[i]

            if low > 0:

                recent_ranges.append(
                    ((high - low) / low) * 100
                )

        volatility = (
            statistics.mean(
                recent_ranges
            )
            if recent_ranges
            else 0
        )


        return {

            "symbol": symbol,

            "price": price,

            "change_24h": change_24h,

            "quote_volume": quote_volume_24h,

            "ema9": ema9,

            "ema21": ema21,

            "ema50": ema50,

            "rsi": round(rsi, 2),

            "volume_ratio": round(
                volume_ratio,
                2
            ),

            "momentum_5m": round(
                momentum_5,
                2
            ),

            "momentum_20": round(
                momentum_20,
                2
            ),

            "trend_score": round(
                trend_score
            ),

            "volume_score": round(
                volume_score
            ),

            "momentum_score": round(
                momentum_score
            ),

            "liquidity_score": round(
                liquidity_score
            ),

            "explosion_score":
                explosion_score,

            "confidence":
                explosion_score,

            "volatility":
                round(
                    volatility,
                    2
                ),

            "signal": signal
        }


    except Exception:

        return None


# =========================================================
# RADAR
# =========================================================

@app.get("/api/radar")
def radar():

    try:

        exchange_info = get_exchange_info()

        allowed_symbols = set()

        for item in exchange_info.get(
            "symbols",
            []
        ):

            if (
                item.get("status") == "TRADING"
                and item.get("quoteAsset") == "USDT"
                and item.get(
                    "isSpotTradingAllowed",
                    True
                )
            ):

                allowed_symbols.add(
                    item.get("symbol")
                )


        # =================================================
        # GET 24H TICKERS
        # =================================================

        tickers = binance_get(
            "/api/v3/ticker/24hr"
        )

        ticker_map = {}

        for ticker in tickers:

            symbol = ticker.get(
                "symbol"
            )

            if symbol in allowed_symbols:

                try:

                    ticker_map[symbol] = ticker

                except:

                    pass


        # =================================================
        # TOP LIQUID COINS
        # =================================================

        symbols = sorted(
            ticker_map.keys(),
            key=lambda s:
                float(
                    ticker_map[s].get(
                        "quoteVolume",
                        0
                    )
                ),
            reverse=True
        )

        symbols = symbols[
            :SCAN_LIMIT
        ]


        results = []


        # =================================================
        # PARALLEL ANALYSIS
        # =================================================

        with ThreadPoolExecutor(
            max_workers=8
        ) as executor:

            futures = {

                executor.submit(
                    analyze_symbol,
                    symbol,
                    ticker_map[symbol]
                ): symbol

                for symbol in symbols
            }


            for future in as_completed(
                futures
            ):

                result = future.result()

                if result:

                    results.append(
                        result
                    )


        # =================================================
        # SORT BY CONFIDENCE
        # =================================================

        results.sort(
            key=lambda x:
                x["confidence"],
            reverse=True
        )


        top5 = results[:5]


        return {

            "status": "ok",

            "version": "1.2",

            "timeframe": "15m",

            "scanned": len(symbols),

            "analyzed": len(results),

            "top5": top5,

            "coins": results,

            "updated": int(
                time.time()
            )

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
# SIMPLE MARKET
# =========================================================

@app.get("/api/market")
def market():

    try:

        exchange_info = (
            get_exchange_info()
        )

        allowed = set()

        for symbol in exchange_info.get(
            "symbols",
            []
        ):

            if (
                symbol.get("status") == "TRADING"
                and symbol.get("quoteAsset") == "USDT"
                and symbol.get(
                    "isSpotTradingAllowed",
                    True
                )
            ):

                allowed.add(
                    symbol.get("symbol")
                )


        tickers = binance_get(
            "/api/v3/ticker/24hr"
        )

        data = []

        for ticker in tickers:

            symbol = ticker.get(
                "symbol"
            )

            if symbol not in allowed:
                continue

            data.append({

                "symbol": symbol,

                "price": float(
                    ticker.get(
                        "lastPrice",
                        0
                    )
                ),

                "change_24h": float(
                    ticker.get(
                        "priceChangePercent",
                        0
                    )
                ),

                "quote_volume": float(
                    ticker.get(
                        "quoteVolume",
                        0
                    )
                )

            })


        data.sort(
            key=lambda x:
                x["quote_volume"],
            reverse=True
        )


        return {

            "status": "ok",

            "count": len(data),

            "showing": min(
                30,
                len(data)
            ),

            "coins": data[:30],

            "updated": int(
                time.time()
            )

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
# STATIC
# =========================================================

if FRONTEND_DIR.exists():

    app.mount(
        "/static",
        StaticFiles(
            directory=FRONTEND_DIR
        ),
        name="static"
    )
