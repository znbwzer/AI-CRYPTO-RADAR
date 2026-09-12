from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import requests
import time
import math
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from pathlib import Path

APP_VERSION = "V2.1-MTF-ACCUMULATION-FIXED"
BINANCE_API = "https://data-api.binance.vision"
TIMEOUT = 10
CACHE_SECONDS = 45
UNIVERSE_LIMIT = 0  # 0 = scan every eligible Spot USDT pair
STRUCTURE_LIMIT = 30
DEEP_LIMIT = 15
MAX_WORKERS = 12

app = FastAPI(title="AI CRYPTO RADAR", version=APP_VERSION)
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

SCAN_LOCK = Lock()
CACHE_LOCK = Lock()
RADAR_CACHE = {"status": "warming_up", "data": [], "scan_seconds": 0, "updated_at": 0}
KLINE_CACHE = {}
KLINE_ERRORS = {}
EXCHANGE_CACHE = {"data": None, "ts": 0}
TICKER_CACHE = {"data": None, "ts": 0}

STABLE_BASES = {
    "USDT", "USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "EUR", "TRY",
    "BRL", "GBP", "AUD", "RUB", "UAH", "NGN", "PLN", "RON", "ZAR"
}
LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")


def clamp(v, lo=0.0, hi=100.0):
    try:
        return max(lo, min(hi, float(v)))
    except Exception:
        return lo


def mean(values, default=0.0):
    vals = [float(x) for x in values if x is not None]
    return statistics.mean(vals) if vals else default


def pct(a, b):
    return ((a - b) / b * 100.0) if b else 0.0


def sma(values, n):
    return mean(values[-n:]) if values else 0.0


def ema(values, n):
    if not values:
        return 0.0
    n = min(n, len(values))
    k = 2 / (n + 1)
    e = mean(values[:n])
    for v in values[n:]:
        e = v * k + e * (1 - k)
    return e


def rsi(values, n=14):
    if len(values) <= n:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = mean(gains[-n:])
    al = mean(losses[-n:])
    if al == 0:
        return 100.0
    return 100 - (100 / (1 + ag / al))


def request_json(path, params=None, timeout=TIMEOUT):
    url = BINANCE_API + path
    last_error = None
    for attempt in range(2):
        try:
            r = requests.get(url, params=params or {}, timeout=timeout)
            if r.status_code == 429:
                time.sleep(min(3, int(r.headers.get("Retry-After", "1"))))
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_error = str(e)
            if attempt == 0:
                time.sleep(0.35)
    raise RuntimeError(last_error or "request failed")


def get_exchange_info():
    now = time.time()
    if EXCHANGE_CACHE["data"] and now - EXCHANGE_CACHE["ts"] < 3600:
        return EXCHANGE_CACHE["data"]
    data = request_json("/api/v3/exchangeInfo", timeout=15)
    EXCHANGE_CACHE.update(data=data, ts=now)
    return data


def get_24h_tickers():
    now = time.time()
    if TICKER_CACHE["data"] and now - TICKER_CACHE["ts"] < 20:
        return TICKER_CACHE["data"]
    data = request_json("/api/v3/ticker/24hr", timeout=15)
    TICKER_CACHE.update(data=data, ts=now)
    return data


def get_klines(symbol, interval, limit=100):
    key = (symbol, interval, limit)
    now = time.time()
    cached = KLINE_CACHE.get(key)
    ttl = 8 if interval in ("1m", "3m", "5m") else 30
    if cached and now - cached[0] < ttl:
        return cached[1]
    try:
        data = request_json("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
        KLINE_CACHE[key] = (now, data)
        return data
    except Exception as e:
        KLINE_ERRORS[f"{symbol}:{interval}"] = {"error": str(e), "time": int(time.time()*1000)}
        return []


def parse_klines(raw):
    out = []
    for x in raw or []:
        try:
            out.append({
                "open": float(x[1]), "high": float(x[2]), "low": float(x[3]),
                "close": float(x[4]), "volume": float(x[5]),
                "taker_buy": float(x[9]), "trades": int(x[8]),
                "time": int(x[0])
            })
        except Exception:
            pass
    return out


def completed(klines):
    return klines[:-1] if len(klines) > 3 else klines


def tf_trend(klines):
    k = completed(klines)
    if len(k) < 30:
        return {"score": 50.0, "change": 0.0, "ema_fast": 0.0, "ema_slow": 0.0}
    c = [x["close"] for x in k]
    e20, e50 = ema(c, 20), ema(c, 50)
    change = pct(c[-1], c[-25]) if len(c) >= 25 else 0.0
    score = 50
    if e20 > e50: score += 20
    if c[-1] > e20: score += 15
    if change > 0: score += min(15, change * 2)
    else: score -= min(20, abs(change) * 2)
    return {"score": clamp(score), "change": change, "ema_fast": e20, "ema_slow": e50}


def structure_features(raw15, current_price):
    k = completed(parse_klines(raw15))
    if len(k) < 30:
        return None
    c = [x["close"] for x in k]
    h = [x["high"] for x in k]
    l = [x["low"] for x in k]
    v = [x["volume"] for x in k]
    tb = [x["taker_buy"] for x in k]

    base_h = h[-24:]
    base_l = l[-24:]
    base_low, base_high = min(base_l), max(base_h)
    base_range = (base_high - base_low) / current_price * 100 if current_price else 0

    recent_range = (max(h[-8:]) - min(l[-8:])) / current_price * 100 if current_price else 0
    prior_range = (max(h[-20:-8]) - min(l[-20:-8])) / current_price * 100 if current_price else recent_range
    ratio = recent_range / prior_range if prior_range > 0 else 1.0
    compression = clamp((1.15 - ratio) / 0.65 * 100)

    recent_vol = mean(v[-5:])
    prior_vol = mean(v[-20:-5])
    dry_ratio = recent_vol / prior_vol if prior_vol else 1.0
    dryup = clamp((1.35 - dry_ratio) / 0.9 * 100)

    hl_pairs = 0
    for i in range(-6, -1):
        if l[i] > l[i - 1]:
            hl_pairs += 1
    higher_lows = clamp(hl_pairs / 5 * 100)

    support_dist = pct(current_price, min(l[-24:]))
    support_score = clamp(100 - max(0, support_dist) * 30)

    pos = (current_price - base_low) / (base_high - base_low) if base_high > base_low else 0.5
    position_score = clamp(100 - abs(pos - 0.72) * 170)

    taker_ratio = sum(tb[-8:]) / sum(v[-8:]) if sum(v[-8:]) else 0.5
    buy_pressure = clamp((taker_ratio - 0.45) / 0.13 * 100)

    resistance = max(h[-24:-1]) if len(h) > 24 else max(h[:-1])
    resistance_distance = pct(resistance, current_price) * -1  # overwritten below for clarity
    resistance_distance = (resistance - current_price) / current_price * 100 if current_price else 0
    if resistance_distance >= 0:
        resistance_score = clamp(100 - resistance_distance * 32)
    else:
        resistance_score = clamp(100 + resistance_distance * 25)

    momentum15 = pct(c[-1], c[-4]) if len(c) >= 4 else 0
    momentum6 = pct(c[-1], c[-13]) if len(c) >= 13 else 0
    overextended = momentum15 > 4.5 or momentum6 > 9 or current_price > resistance * 1.018

    # Prefer quiet bases, but do not reward a dead/illiquid market.
    accumulation = (
        compression * 0.27 + dryup * 0.15 + higher_lows * 0.14 +
        support_score * 0.12 + position_score * 0.10 +
        buy_pressure * 0.10 + resistance_score * 0.12
    )
    if overextended:
        accumulation -= 18

    return {
        "accumulation": round(clamp(accumulation), 1),
        "compression": round(compression, 1),
        "dryup": round(dryup, 1),
        "higher_lows": round(higher_lows, 1),
        "support": round(support_score, 1),
        "position": round(position_score, 1),
        "taker_ratio": round(taker_ratio, 4),
        "buy_pressure": round(buy_pressure, 1),
        "resistance": resistance,
        "resistance_distance": round(resistance_distance, 3),
        "resistance_score": round(resistance_score, 1),
        "base_range_pct": round(base_range, 3),
        "momentum15": round(momentum15, 3),
        "momentum6": round(momentum6, 3),
        "overextended": bool(overextended),
    }


def short_features(raw):
    k = completed(parse_klines(raw))
    if len(k) < 20:
        return {"score": 50.0, "volume_ratio": 1.0, "momentum": 0.0, "breakout": False, "taker_ratio": 0.5}
    c = [x["close"] for x in k]
    h = [x["high"] for x in k]
    v = [x["volume"] for x in k]
    tb = [x["taker_buy"] for x in k]
    vr = v[-1] / mean(v[-13:-1]) if mean(v[-13:-1]) else 1.0
    mom = pct(c[-1], c[-4])
    taker = sum(tb[-6:]) / sum(v[-6:]) if sum(v[-6:]) else 0.5
    prev_high = max(h[-13:-1])
    breakout = c[-1] > prev_high
    score = 45 + clamp((vr - 1) * 30, -20, 35) + clamp((taker - 0.5) * 180, -20, 25)
    if breakout: score += 20
    if mom > 0: score += min(10, mom * 3)
    return {
        "score": round(clamp(score), 1), "volume_ratio": round(vr, 2),
        "momentum": round(mom, 3), "breakout": bool(breakout),
        "taker_ratio": round(taker, 4)
    }


def get_agg_and_depth(symbol):
    result = {"cvd_score": 50.0, "large_trade_score": 50.0, "depth_score": 50.0, "spread_score": 50.0}
    try:
        trades = request_json("/api/v3/aggTrades", {"symbol": symbol, "limit": 500})
        buys = sells = 0.0
        notionals = []
        buy_large = sell_large = 0.0
        for t in trades:
            q = float(t["q"])
            p = float(t["p"])
            n = p * q
            notionals.append(n)
            if bool(t["m"]):
                sells += q
            else:
                buys += q
        total = buys + sells
        cvd_ratio = (buys - sells) / total if total else 0
        result["cvd_score"] = round(clamp((cvd_ratio + 0.12) / 0.24 * 100), 1)
        if notionals:
            s = sorted(notionals)
            threshold = s[max(0, int(len(s) * 0.95) - 1)]
            for t in trades:
                q, p = float(t["q"]), float(t["p"])
                n = p * q
                if n >= threshold:
                    if bool(t["m"]): sell_large += n
                    else: buy_large += n
            lt = buy_large + sell_large
            result["large_trade_score"] = round(clamp((buy_large / lt - 0.35) / 0.3 * 100) if lt else 50, 1)
    except Exception:
        pass

    try:
        depth = request_json("/api/v3/depth", {"symbol": symbol, "limit": 20})
        bids = sum(float(x[1]) for x in depth.get("bids", []))
        asks = sum(float(x[1]) for x in depth.get("asks", []))
        total = bids + asks
        imbalance = (bids - asks) / total if total else 0
        result["depth_score"] = round(clamp((imbalance + 0.25) / 0.5 * 100), 1)
        if depth.get("bids") and depth.get("asks"):
            bid = float(depth["bids"][0][0]); ask = float(depth["asks"][0][0])
            mid = (bid + ask) / 2
            spread = (ask - bid) / mid * 100 if mid else 1
            result["spread_pct"] = round(spread, 4)
            if spread <= 0.03: result["spread_score"] = 100.0
            elif spread <= 0.08: result["spread_score"] = 90.0
            elif spread <= 0.20: result["spread_score"] = 70.0
            elif spread <= 0.50: result["spread_score"] = 45.0
            else: result["spread_score"] = 20.0
    except Exception:
        pass
    result["smart_money"] = round(clamp(result["cvd_score"] * 0.45 + result["depth_score"] * 0.30 + result["large_trade_score"] * 0.25), 1)
    return result


def liquidity_score(ticker, spread_score=50):
    qv = float(ticker.get("quoteVolume", 0) or 0)
    if qv >= 50_000_000: vol_score = 100
    elif qv >= 10_000_000: vol_score = 90
    elif qv >= 3_000_000: vol_score = 78
    elif qv >= 1_000_000: vol_score = 65
    elif qv >= 300_000: vol_score = 50
    else: vol_score = 25
    return round(clamp(vol_score * 0.72 + spread_score * 0.28), 1)


def candidate_universe():
    info = get_exchange_info()
    tickers = {x["symbol"]: x for x in get_24h_tickers() if x.get("symbol")}
    eligible = []
    for s in info.get("symbols", []):
        symbol = s.get("symbol", "")
        if s.get("status") != "TRADING" or s.get("quoteAsset") != "USDT":
            continue
        base = s.get("baseAsset", "")
        if base in STABLE_BASES or base.endswith(LEVERAGED_SUFFIXES):
            continue
        t = tickers.get(symbol)
        if not t:
            continue
        qv = float(t.get("quoteVolume", 0) or 0)
        if qv < 250_000:
            continue
        eligible.append(t)
    top_liq = sorted(eligible, key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)[:120]
    top_move = sorted(eligible, key=lambda x: float(x.get("priceChangePercent", 0)), reverse=True)[:80]
    merged = {x["symbol"]: x for x in eligible}
    values = list(merged.values())
    values.sort(key=lambda x: float(x.get("quoteVolume", 0) or 0), reverse=True)
    if UNIVERSE_LIMIT and len(values) > UNIVERSE_LIMIT:
        values = values[:UNIVERSE_LIMIT]
    return values


def base_scan_item(ticker):
    symbol = ticker["symbol"]
    price = float(ticker.get("lastPrice", 0) or 0)
    raw = get_klines(symbol, "15m", 80)
    f = structure_features(raw, price)
    if not f:
        return None
    pre = f["accumulation"] * 0.7 + f["resistance_score"] * 0.15 + f["buy_pressure"] * 0.15
    return {"symbol": symbol, "ticker": ticker, "price": price, "f": f, "pre": pre}


def deep_analyze(item):
    symbol, ticker, price, f = item["symbol"], item["ticker"], item["price"], item["f"]
    raw5 = get_klines(symbol, "5m", 80)
    raw1h = get_klines(symbol, "1h", 80)
    raw4h = get_klines(symbol, "4h", 80)
    s5 = short_features(raw5)
    t1h = tf_trend(raw1h)
    t4h = tf_trend(raw4h)

    # Deep order-flow is intentionally limited to a small candidate set to protect Binance rate limits.
    flow = get_agg_and_depth(symbol)

    s3 = {"score": 50.0, "volume_ratio": 1.0, "momentum": 0.0, "breakout": False, "taker_ratio": 0.5}
    s1 = {"score": 50.0, "volume_ratio": 1.0, "momentum": 0.0, "breakout": False, "taker_ratio": 0.5}
    if len(raw5) >= 20:
        s3 = short_features(get_klines(symbol, "3m", 80))
        s1 = short_features(get_klines(symbol, "1m", 80))

    volume_pressure = clamp(
        f["buy_pressure"] * 0.30 + s5["score"] * 0.28 + s3["score"] * 0.20 + s1["score"] * 0.12 + flow["cvd_score"] * 0.10
    )
    tf_alignment = clamp(t1h["score"] * 0.45 + t4h["score"] * 0.30 + s5["score"] * 0.25)

    breakout_ready = clamp(
        f["resistance_score"] * 0.32 + f["compression"] * 0.18 + volume_pressure * 0.22 +
        s5["score"] * 0.13 + s3["score"] * 0.08 + flow["depth_score"] * 0.07
    )

    momentum = clamp(
        50 + f["momentum15"] * 7 + s5["momentum"] * 8 + s3["momentum"] * 5
    )
    if f["overextended"]:
        momentum = min(momentum, 65)

    liq = liquidity_score(ticker, flow["spread_score"])
    risk_safety = clamp(flow["spread_score"] * 0.45 + liq * 0.35 + (100 if not f["overextended"] else 25) * 0.20)

    radar = clamp(
        f["accumulation"] * 0.25 + flow["smart_money"] * 0.15 + volume_pressure * 0.15 +
        liq * 0.12 + breakout_ready * 0.18 + momentum * 0.07 + tf_alignment * 0.08
    )

    trigger = (
        price > f["resistance"] * 1.002 and
        s5["score"] >= 65 and
        volume_pressure >= 62 and
        (flow["cvd_score"] >= 58 or f["buy_pressure"] >= 65)
    )
    expansion = f["overextended"] or (price > f["resistance"] * 1.015 and f["momentum15"] > 2.5)
    if trigger:
        stage = "TRIGGER"
        stage_ar = "🟩 TRIGGER"
    elif expansion:
        stage = "EXPANSION"
        stage_ar = "🚀 EXPANSION"
    elif f["accumulation"] >= 72 and breakout_ready >= 68:
        stage = "READY"
        stage_ar = "🟨 READY"
    elif f["accumulation"] >= 65:
        stage = "ACCUMULATION"
        stage_ar = "🟦 ACCUMULATION"
    else:
        stage = "WATCH"
        stage_ar = "👀 WATCH"

    early = radar
    if stage == "EXPANSION": early -= 22
    if stage == "TRIGGER": early -= 5
    if risk_safety < 45: early -= 8
    early = clamp(early)

    why = []
    if f["compression"] >= 65: why.append("COMPRESSION")
    if f["dryup"] >= 60: why.append("VOLUME DRY-UP")
    if f["higher_lows"] >= 60: why.append("HIGHER LOWS")
    if f["buy_pressure"] >= 62: why.append("BUY PRESSURE")
    if flow["cvd_score"] >= 60: why.append("POSITIVE CVD")
    if flow["depth_score"] >= 60: why.append("BID SUPPORT")
    if f["resistance_distance"] <= 2.5: why.append("NEAR RESISTANCE")
    if s5["breakout"]: why.append("5M BREAKOUT")
    if trigger: why.append("TRIGGER CONFIRMED")
    if not why: why.append("STRUCTURE UNDER WATCH")

    return {
        "symbol": symbol,
        "price": price,
        "change24h": round(float(ticker.get("priceChangePercent", 0) or 0), 2),
        "quoteVolume24h": round(float(ticker.get("quoteVolume", 0) or 0), 0),
        "stage": stage,
        "stage_ar": stage_ar,
        "radar_score": round(radar, 1),
        "early_score": round(early, 1),
        "accumulation": f["accumulation"],
        "smart_money": flow["smart_money"],
        "volume_pressure": round(volume_pressure, 1),
        "liquidity": liq,
        "breakout_ready": round(breakout_ready, 1),
        "momentum": round(momentum, 1),
        "risk_safety": round(risk_safety, 1),
        "resistance": f["resistance"],
        "distance_to_resistance": f["resistance_distance"],
        "cvd_score": flow["cvd_score"],
        "depth_score": flow["depth_score"],
        "large_trade_score": flow["large_trade_score"],
        "spread_pct": flow.get("spread_pct", None),
        "taker_buy_ratio": f["taker_ratio"],
        "volume_5m_ratio": s5["volume_ratio"],
        "volume_1m_ratio": s1["volume_ratio"],
        "tf_1h": round(t1h["score"], 1),
        "tf_4h": round(t4h["score"], 1),
        "why": why[:8],
        "flags": {
            "compression": f["compression"] >= 65,
            "dryup": f["dryup"] >= 60,
            "buy_pressure": f["buy_pressure"] >= 62,
            "cvd": flow["cvd_score"] >= 60,
            "absorption_proxy": flow["depth_score"] >= 60 and f["compression"] >= 60,
            "breakout": bool(trigger),
        }
    }


def run_radar_scan():
    started = time.time()
    universe = candidate_universe()
    bases = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(base_scan_item, t) for t in universe]
        for fut in as_completed(futures):
            try:
                x = fut.result()
                if x:
                    bases.append(x)
            except Exception:
                pass
    bases.sort(key=lambda x: x["pre"], reverse=True)
    selected = bases[:STRUCTURE_LIMIT]

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(deep_analyze, x) for x in selected[:DEEP_LIMIT]]
        for fut in as_completed(futures):
            try:
                x = fut.result()
                if x:
                    results.append(x)
            except Exception:
                pass
    results.sort(key=lambda x: x["early_score"], reverse=True)
    elapsed = round(time.time() - started, 2)
    return {
        "status": "ok",
        "version": APP_VERSION,
        "scanned_universe": len(universe),
        "structure_candidates": len(selected),
        "deep_analyzed": len(results),
        "base_success": len(bases),
        "base_failed": max(0, len(universe) - len(bases)),
        "kline_errors": dict(list(KLINE_ERRORS.items())[-20:]),
        "results": results,
        "top5": results[:5],
        "scan_seconds": elapsed,
        "updated_at": int(time.time() * 1000)
    }


def get_cached_or_scan():
    now = time.time()
    with CACHE_LOCK:
        if RADAR_CACHE.get("status") == "ok" and now - RADAR_CACHE.get("updated_at", 0) / 1000 < CACHE_SECONDS:
            return RADAR_CACHE
    if not SCAN_LOCK.acquire(blocking=False):
        with CACHE_LOCK:
            return RADAR_CACHE
    try:
        data = run_radar_scan()
        with CACHE_LOCK:
            RADAR_CACHE.clear(); RADAR_CACHE.update(data)
        return data
    finally:
        SCAN_LOCK.release()


@app.get("/")
def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"status": "online", "app": "AI CRYPTO RADAR", "version": APP_VERSION}


@app.get("/api/health")
def health():
    return {"status": "online", "app": "AI CRYPTO RADAR", "version": APP_VERSION}


@app.get("/api/binance-test")
def binance_test():
    start = time.time()
    try:
        data = request_json("/api/v3/ping")
        server = request_json("/api/v3/time")
        return {"status": "ok", "binance": "connected", "ping_ms": round((time.time()-start)*1000), "server_time": server.get("serverTime"), "ping": data}
    except Exception as e:
        return {"status": "error", "binance": "not_connected", "error": str(e)}


@app.get("/api/radar")
def radar():
    return get_cached_or_scan()


@app.get("/api/debug")
def debug():
    try:
        info = get_exchange_info()
        tickers = get_24h_tickers()
        samples = {}
        sample_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        for symbol in sample_symbols:
            raw = get_klines(symbol, "15m", 10)
            samples[symbol] = {"klines": len(raw), "error": KLINE_ERRORS.get(f"{symbol}:15m")}
        eligible = 0
        symbols = []
        ticker_map = {x.get("symbol"): x for x in tickers if x.get("symbol")}
        for x in info.get("symbols", []):
            if x.get("status") == "TRADING" and x.get("quoteAsset") == "USDT":
                base = x.get("baseAsset", "")
                if base not in STABLE_BASES and not base.endswith(LEVERAGED_SUFFIXES):
                    t = ticker_map.get(x.get("symbol"), {})
                    if float(t.get("quoteVolume", 0) or 0) >= 100_000:
                        eligible += 1
                        if len(symbols) < 10:
                            symbols.append(x.get("symbol"))
        return {
            "status": "ok",
            "version": APP_VERSION,
            "exchange_symbols": len(info.get("symbols", [])),
            "ticker_rows": len(tickers),
            "eligible_spot_usdt": eligible,
            "sample_symbols": symbols,
            "sample_15m": samples,
            "recent_kline_errors": dict(list(KLINE_ERRORS.items())[-20:])
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/status")
def status():
    with CACHE_LOCK:
        return {
            "status": RADAR_CACHE.get("status"),
            "version": APP_VERSION,
            "last_update": RADAR_CACHE.get("updated_at"),
            "scan_seconds": RADAR_CACHE.get("scan_seconds", 0),
            "results": len(RADAR_CACHE.get("results", [])),
            "universe": RADAR_CACHE.get("scanned_universe", 0),
        }
