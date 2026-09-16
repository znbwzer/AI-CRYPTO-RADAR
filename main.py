from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import requests, time, math, statistics, json, threading, queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from pathlib import Path
try:
    import websocket
except Exception:
    websocket = None

APP_VERSION = "V3.7-ACC-FLOW-QUALITY"
BINANCE_API = "https://data-api.binance.vision"
TIMEOUT = 12
CACHE_SECONDS = 70
MIN_QUOTE_VOLUME = 100_000
UNIVERSE_LIMIT = 0
BASE_LIMIT = 100
DEEP_LIMIT = 30
MAX_WORKERS = 16
VP_BINS = 24
BACKTEST_TOP_N = 50
BACKTEST_DAYS = 30
BACKTEST_TARGETS = (0.02, 0.05, 0.10)
BACKTEST_STOP = 0.015
BACKTEST_HORIZON = 16
WS_SYMBOL_LIMIT = 120
WS_RECONNECT_SECONDS = 5
COINGECKO_API = "https://api.coingecko.com/api/v3"
COINGECKO_CACHE = {"data":None,"ts":0}
CORE_MARKET_CAP_USD = 5_000_000_000
CORE_MIN_VOL_MCAP = 0.005
ACC_FLOW_DEEP_LIMIT = 60

app = FastAPI(title="AI CRYPTO RADAR V3", version=APP_VERSION)
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

SCAN_LOCK, CACHE_LOCK = Lock(), Lock()
RADAR_CACHE = {"status":"warming_up","results":[],"top5":[],"updated_at":0}
KLINE_CACHE, KLINE_ERRORS = {}, {}
EXCHANGE_CACHE, TICKER_CACHE = {"data":None,"ts":0}, {"data":None,"ts":0}
HIST_CACHE = {}
BACKTEST_CACHE = {}
WS_STATE = {"running": False, "connected": False, "symbols": 0, "events": 0, "last_event": 0, "connections": 0, "last_error": None, "started_at": 0}
WS_FLOW = {}
WS_LOCK = Lock()

STABLE_BASES = {"USDT","USDC","FDUSD","TUSD","USDP","DAI","BUSD","EUR","TRY","BRL","GBP","AUD","RUB","UAH","NGN","PLN","RON","ZAR"}
LEVERAGED_SUFFIXES = ("UP","DOWN","BULL","BEAR")


def clamp(v, lo=0.0, hi=100.0):
    try: return max(lo, min(hi, float(v)))
    except Exception: return lo

def mean(a, default=0.0):
    x=[float(v) for v in a if v is not None]
    return statistics.mean(x) if x else default

def pct(a,b): return ((a-b)/b*100.0) if b else 0.0

def ema(a,n):
    if not a: return 0.0
    n=min(n,len(a)); k=2/(n+1); e=mean(a[:n])
    for v in a[n:]: e=v*k+e*(1-k)
    return e

def rsi(a,n=14):
    if len(a)<=n: return 50.0
    d=[a[i]-a[i-1] for i in range(1,len(a))]
    g=mean([max(x,0) for x in d[-n:]]); l=mean([max(-x,0) for x in d[-n:]])
    return 100.0 if l==0 else 100-(100/(1+g/l))

def request_json(path, params=None, timeout=TIMEOUT):
    last=None
    for attempt in range(3):
        try:
            r=requests.get(BINANCE_API+path,params=params or {},timeout=timeout)
            if r.status_code in (418,429):
                time.sleep(min(5,1.2*(attempt+1))); continue
            r.raise_for_status(); return r.json()
        except Exception as e:
            last=str(e); time.sleep(0.25*(attempt+1))
    raise RuntimeError(last or "request failed")

def get_exchange_info():
    now=time.time()
    if EXCHANGE_CACHE["data"] and now-EXCHANGE_CACHE["ts"]<3600: return EXCHANGE_CACHE["data"]
    d=request_json("/api/v3/exchangeInfo",timeout=18); EXCHANGE_CACHE.update(data=d,ts=now); return d

def get_24h_tickers():
    now=time.time()
    if TICKER_CACHE["data"] and now-TICKER_CACHE["ts"]<20: return TICKER_CACHE["data"]
    d=request_json("/api/v3/ticker/24hr",timeout=18); TICKER_CACHE.update(data=d,ts=now); return d

def get_klines(symbol, interval, limit=100, start_time=None, end_time=None):
    key=(symbol,interval,limit,start_time,end_time)
    now=time.time(); old=KLINE_CACHE.get(key)
    ttl=7 if interval in ("1m","3m","5m") else 25
    if old and now-old[0]<ttl: return old[1]
    params={"symbol":symbol,"interval":interval,"limit":limit}
    if start_time is not None: params["startTime"]=int(start_time)
    if end_time is not None: params["endTime"]=int(end_time)
    try:
        d=request_json("/api/v3/klines",params); KLINE_CACHE[key]=(now,d); return d
    except Exception as e:
        KLINE_ERRORS[f"{symbol}:{interval}:{start_time or ''}"]={"error":str(e),"time":int(now*1000)}; return []

def get_historical_klines(symbol, interval="15m", days=30):
    """Fetch closed historical candles in pages, without look-ahead."""
    days=max(1,min(int(days),90))
    cache_key=(symbol,interval,days)
    old=HIST_CACHE.get(cache_key)
    if old and time.time()-old[0]<300: return old[1]
    now_ms=int(time.time()*1000)
    start=now_ms-days*86400000
    out=[]; cursor=start
    for _ in range(10):
        page=get_klines(symbol,interval,1000,start_time=cursor,end_time=now_ms)
        if not page: break
        out.extend(page)
        last=int(page[-1][0])
        if len(page)<1000 or last<=cursor: break
        cursor=last+1
        if cursor>=now_ms: break
        time.sleep(0.05)
    dedup={int(x[0]):x for x in out}
    arr=[dedup[k] for k in sorted(dedup)]
    if arr and int(arr[-1][0])+1 > now_ms-120000: arr=arr[:-1]
    HIST_CACHE[cache_key]=(time.time(),arr)
    return arr

def parse(raw):
    out=[]
    for x in raw or []:
        try: out.append({"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5]),"tb":float(x[9]),"t":int(x[0]),"qv":float(x[7]),"n":int(x[8])})
        except Exception: pass
    return out

def completed(raw): return raw[:-1] if len(raw)>3 else raw

def basic_15m(raw, price):
    k=completed(parse(raw));
    if len(k)<30: return None
    c=[x["c"] for x in k]; h=[x["h"] for x in k]; l=[x["l"] for x in k]; v=[x["v"] for x in k]; tb=[x["tb"] for x in k]
    e20,e50=ema(c,20),ema(c,50)
    recent=max(h[-8:])-min(l[-8:]); prior=max(h[-24:-8])-min(l[-24:-8]) if len(h)>=24 else recent
    compression=clamp((1-(recent/(prior or recent)))*150+50)
    vr=mean(v[-5:])/mean(v[-25:-5]) if mean(v[-25:-5]) else 1
    dryup=clamp((1.45-vr)/0.85*100)
    higher=sum(1 for i in range(-6,-1) if l[i]>l[i-1])/5*100
    base_low,base_high=min(l[-32:]),max(h[-32:]); pos=(price-base_low)/(base_high-base_low) if base_high>base_low else .5
    position=clamp(100-abs(pos-.68)*190)
    taker=sum(tb[-10:])/sum(v[-10:]) if sum(v[-10:]) else .5
    buy_pressure=clamp((taker-.45)/.12*100)
    r=rsi(c); rprev=rsi(c[:-3]) if len(c)>20 else r
    resistance=max(h[-25:-1]); dist=max(0,(resistance-price)/price*100) if price else 0
    resistance_score=clamp(100-dist*28)
    mom5=pct(c[-1],c[-5]); mom20=pct(c[-1],c[-21])
    accumulation=clamp(compression*.22+dryup*.12+higher*.13+position*.12+buy_pressure*.16+resistance_score*.15+(clamp(100-abs(r-48)*2))*.10)
    overextended=mom5>4.5 or mom20>10 or price>resistance*1.02
    if overextended: accumulation=clamp(accumulation-18)
    return {"accumulation":round(accumulation,1),"compression":round(compression,1),"dryup":round(dryup,1),"higher_lows":round(higher,1),"position":round(position,1),"buy_pressure":round(buy_pressure,1),"taker_buy_ratio":round(taker,4),"rsi":round(r,1),"rsi_rising":r>rprev,"resistance":resistance,"resistance_distance":round(dist,3),"resistance_score":round(resistance_score,1),"momentum5":round(mom5,3),"momentum20":round(mom20,3),"overextended":overextended,"closes":c[-60:]}

def trend(raw):
    k=completed(parse(raw)); c=[x["c"] for x in k]
    if len(c)<30:return 50.0
    e20,e50=ema(c,20),ema(c,50); ch=pct(c[-1],c[-25])
    return clamp(50+(20 if e20>e50 else -15)+(15 if c[-1]>e20 else -10)+(min(15,ch*2) if ch>0 else -min(20,abs(ch)*2)))

def short_tf(raw):
    k=completed(parse(raw));
    if len(k)<20:return {"score":50.0,"vr":1.0,"mom":0.0,"breakout":False,"taker":.5}
    c=[x["c"] for x in k]; h=[x["h"] for x in k]; v=[x["v"] for x in k]; tb=[x["tb"] for x in k]
    vr=v[-1]/mean(v[-13:-1]) if mean(v[-13:-1]) else 1; mom=pct(c[-1],c[-4]); taker=sum(tb[-6:])/sum(v[-6:]) if sum(v[-6:]) else .5; br=c[-1]>max(h[-13:-1])
    score=45+clamp((vr-1)*28,-20,35)+clamp((taker-.5)*180,-20,25)+(20 if br else 0)+(min(10,mom*3) if mom>0 else 0)
    return {"score":round(clamp(score),1),"vr":round(vr,2),"mom":round(mom,3),"breakout":br,"taker":round(taker,4)}

def volume_profile_from_klines(raw, bins=VP_BINS):
    k=completed(parse(raw))
    if len(k)<10:return {"mode":"kline","bins":[],"poc":0.0,"hvn":0.0,"lvn":0.0,"score":50.0,"price_position":50.0}
    lo=min(x["l"] for x in k); hi=max(x["h"] for x in k)
    if hi<=lo:return {"mode":"kline","bins":[],"poc":lo,"hvn":lo,"lvn":lo,"score":50.0,"price_position":50.0}
    step=(hi-lo)/bins; vols=[0.0]*bins
    # Klines provide total traded volume, not its exact intrabar price distribution.
    # Allocate each candle's volume across the price bins intersected by its range.
    for x in k:
        a=max(0,int((x["l"]-lo)/step)); b=min(bins-1,int((x["h"]-lo)/step))
        span=max(1,b-a+1); w=x["v"]/span
        for j in range(a,b+1): vols[j]+=w
    order=sorted(range(bins),key=lambda i:vols[i],reverse=True); poc_i=order[0]; lvn_i=min(range(bins),key=lambda i:vols[i])
    centers=[lo+(i+.5)*step for i in range(bins)]; mx=max(vols) or 1
    return {"mode":"kline","bins":[{"price":round(centers[i],12),"volume":round(vols[i],6),"relative":round(vols[i]/mx,3)} for i in range(bins)],"poc":centers[poc_i],"hvn":centers[order[min(2,len(order)-1)]],"lvn":centers[lvn_i],"score":50.0,"price_position":50.0}

def volume_profile_from_trades(trades, bins=VP_BINS):
    rows=[]
    for t in trades or []:
        try: rows.append((float(t["p"]),float(t["q"]),bool(t["m"])))
        except Exception: pass
    if len(rows)<20:return None
    lo=min(x[0] for x in rows); hi=max(x[0] for x in rows)
    if hi<=lo:return None
    step=(hi-lo)/bins; vols=[0.0]*bins; bid=[0.0]*bins; ask=[0.0]*bins
    for p,q,is_sell in rows:
        i=min(bins-1,max(0,int((p-lo)/step))); n=p*q; vols[i]+=n
        (ask if is_sell else bid)[i]+=n
    order=sorted(range(bins),key=lambda i:vols[i],reverse=True); poc_i=order[0]; lvn_i=min(range(bins),key=lambda i:vols[i])
    centers=[lo+(i+.5)*step for i in range(bins)]; mx=max(vols) or 1; price=rows[-1][0]
    ppos=clamp((price-lo)/(hi-lo)*100)
    poc=centers[poc_i]; near=max(0,1-abs(price-poc)/(hi-lo))*100
    total_bid=sum(bid); total_ask=sum(ask); imb=(total_bid-total_ask)/(total_bid+total_ask or 1)
    score=clamp(50+imb*55+max(0,near-50)*.35)
    return {"mode":"trades","bins":[{"price":round(centers[i],12),"volume":round(vols[i],6),"relative":round(vols[i]/mx,3),"bid":round(bid[i],6),"ask":round(ask[i],6)} for i in range(bins)],"poc":poc,"hvn":centers[order[min(2,len(order)-1)]],"lvn":centers[lvn_i],"score":round(score,1),"price_position":round(ppos,1),"trade_count":len(rows),"bid_notional":round(total_bid,2),"ask_notional":round(total_ask,2)}

def order_flow(symbol):
    out={"cvd":50.0,"whale":50.0,"depth":50.0,"spread":50.0,"volume_profile":50.0,"vp_mode":"none"}
    try:
        tr=request_json("/api/v3/aggTrades",{"symbol":symbol,"limit":500}); buys=sells=0.0; notionals=[]; bwh=swh=0.0
        for t in tr:
            n=float(t["p"])*float(t["q"]); notionals.append(n)
            if bool(t["m"]): sells+=n
            else: buys+=n
        total=buys+sells; ratio=buys/total if total else .5; out["cvd"]=round(clamp((ratio-.42)/.18*100),1)
        if notionals:
            th=sorted(notionals)[max(0,int(len(notionals)*.95)-1)]
            for t in tr:
                n=float(t["p"])*float(t["q"])
                if n>=th:
                    if bool(t["m"]): swh+=n
                    else:bwh+=n
            out["whale"]=round(clamp((bwh/(bwh+swh)-.30)/.40*100) if bwh+swh else 50,1)
        vp=volume_profile_from_trades(tr)
        if vp:
            out["volume_profile"]=vp["score"]; out["vp_mode"]="trades"; out["vp_poc"]=vp["poc"]; out["vp_hvn"]=vp["hvn"]; out["vp_lvn"]=vp["lvn"]; out["vp_price_position"]=vp["price_position"]
    except Exception: pass
    try:
        d=request_json("/api/v3/depth",{"symbol":symbol,"limit":50}); bids=d.get("bids",[]); asks=d.get("asks",[])
        bv=sum(float(x[1]) for x in bids); av=sum(float(x[1]) for x in asks); total=bv+av; imb=(bv-av)/total if total else 0
        out["depth"]=round(clamp((imb+.22)/.44*100),1)
        if bids and asks:
            bid,ask=float(bids[0][0]),float(asks[0][0]); mid=(bid+ask)/2; sp=(ask-bid)/mid*100 if mid else 1; out["spread_pct"]=round(sp,4)
            out["spread"]=100 if sp<=.03 else 90 if sp<=.08 else 70 if sp<=.20 else 45 if sp<=.5 else 20
    except Exception: pass
    out["smart_money"]=round(clamp(out["cvd"]*.35+out["whale"]*.30+out["depth"]*.25+out["volume_profile"]*.10),1)
    return out

def liquidity(t, spread):
    q=float(t.get("quoteVolume",0) or 0)
    vs=100 if q>=50e6 else 90 if q>=10e6 else 78 if q>=3e6 else 65 if q>=1e6 else 50 if q>=3e5 else 25
    return round(clamp(vs*.72+spread*.28),1)


def _ws_update(symbol, price, qty, is_sell, event_time):
    now=time.time()
    with WS_LOCK:
        x=WS_FLOW.setdefault(symbol,{"buy_notional":0.0,"sell_notional":0.0,"trades":0,"whale_buy":0.0,"whale_sell":0.0,"last_price":price,"last_event":0,"window_start":now,"recent":[]})
        # Rolling 5-minute order-flow window. Keep memory bounded.
        if now-x["window_start"]>=300:
            x["buy_notional"]=x["sell_notional"]=x["trades"]=x["whale_buy"]=x["whale_sell"]=0.0
            x["recent"]=[]; x["window_start"]=now
        n=price*qty
        if is_sell: x["sell_notional"]+=n
        else: x["buy_notional"]+=n
        x["trades"]+=1; x["last_price"]=price; x["last_event"]=event_time
        x["recent"].append((now,n,is_sell))
        if len(x["recent"])>5000: x["recent"]=x["recent"][-3000:]
        # Dynamic whale threshold: large relative trades are flagged, not identity of a wallet.
        vals=[z[1] for z in x["recent"][-500:]]
        if len(vals)>=20:
            th=sorted(vals)[max(0,int(len(vals)*0.95)-1)]
            if n>=th:
                if is_sell: x["whale_sell"]+=n
                else: x["whale_buy"]+=n

def ws_snapshot(symbol):
    with WS_LOCK:
        x=WS_FLOW.get(symbol)
        if not x: return None
        b=x["buy_notional"]; a=x["sell_notional"]; total=b+a
        cvd=clamp((b/(total or 1)-.42)/.18*100)
        wt=x["whale_buy"]+x["whale_sell"]
        whale=clamp((x["whale_buy"]/(wt or 1)-.30)/.40*100) if wt else 50
        return {"symbol":symbol,"cvd":round(cvd,1),"whale":round(whale,1),"buy_notional":round(b,2),"sell_notional":round(a,2),"trades":x["trades"],"last_price":x["last_price"],"last_event":x["last_event"],"window_seconds":min(300,int(time.time()-x["window_start"]))}

def ws_worker(symbols):
    if websocket is None:
        with WS_LOCK: WS_STATE.update(running=False,connected=False,last_error="websocket-client not installed")
        return
    streams='/'.join(f'{s.lower()}@aggTrade' for s in symbols)
    url='wss://stream.binance.com:9443/stream?streams='+streams
    with WS_LOCK: WS_STATE.update(running=True,connected=False,symbols=len(symbols),connections=WS_STATE.get("connections",0)+1,started_at=int(time.time()*1000))
    while True:
        try:
            def on_open(ws):
                with WS_LOCK: WS_STATE["connected"]=True; WS_STATE["last_error"]=None
            def on_message(ws,msg):
                try:
                    d=json.loads(msg); e=d.get("data",d)
                    if e.get("e")!='aggTrade': return
                    sym=e.get("s",""); price=float(e.get("p",0)); qty=float(e.get("q",0)); maker=bool(e.get("m",False)); et=int(e.get("E",0))
                    if price>0 and qty>0:
                        _ws_update(sym,price,qty,maker,et)
                        with WS_LOCK: WS_STATE["events"]+=1; WS_STATE["last_event"]=et
                except Exception as ex:
                    with WS_LOCK: WS_STATE["last_error"]=str(ex)
            def on_error(ws,err):
                with WS_LOCK: WS_STATE["last_error"]=str(err)
            def on_close(ws,code,msg):
                with WS_LOCK: WS_STATE["connected"]=False
            ws=websocket.WebSocketApp(url,on_open=on_open,on_message=on_message,on_error=on_error,on_close=on_close)
            ws.run_forever(ping_interval=120,ping_timeout=30)
        except Exception as e:
            with WS_LOCK: WS_STATE["connected"]=False; WS_STATE["last_error"]=str(e)
        time.sleep(WS_RECONNECT_SECONDS)
        # Reconnect is intentional: Binance market-stream connections are time-limited.

def start_ws_monitor(symbols):
    if not symbols or WS_STATE.get("running"): return
    # Keep the live order-flow tier bounded. The broad scanner still covers the whole eligible universe.
    selected=[x["symbol"] if isinstance(x,dict) else x for x in symbols[:WS_SYMBOL_LIMIT]]
    th=threading.Thread(target=ws_worker,args=(selected,),daemon=True)
    th.start()

def adaptive_orderflow(symbol):
    return ws_snapshot(symbol) or {"symbol":symbol,"cvd":50.0,"whale":50.0,"trades":0,"buy_notional":0.0,"sell_notional":0.0,"window_seconds":0}

def get_coingecko_markets():
    """Optional market-cap enrichment. Binance remains the trading-data source."""
    now=time.time()
    if COINGECKO_CACHE["data"] is not None and now-COINGECKO_CACHE["ts"]<600:
        return COINGECKO_CACHE["data"]
    try:
        out=[]
        for page in (1,2):
            r=requests.get(COINGECKO_API+"/coins/markets",params={"vs_currency":"usd","order":"market_cap_desc","per_page":250,"page":page,"sparkline":"false"},timeout=15)
            r.raise_for_status(); out.extend(r.json())
        # Keep the highest market-cap entry for each ticker symbol.
        mp={}
        for x in out:
            sym=str(x.get("symbol","")).upper()
            if not sym: continue
            if sym not in mp or float(x.get("market_cap",0) or 0)>float(mp[sym].get("market_cap",0) or 0): mp[sym]=x
        COINGECKO_CACHE.update(data=mp,ts=now)
        return mp
    except Exception:
        return COINGECKO_CACHE.get("data") or {}

# A conservative metadata-based utility classification. It is not a claim that a token is safe.
UTILITY_HINTS={
    "BTC":"Store of value / settlement",
    "ETH":"Smart-contract platform",
    "BNB":"Exchange + smart-contract ecosystem",
    "SOL":"Smart-contract platform",
    "XRP":"Payments / settlement",
    "ADA":"Smart-contract platform",
    "AVAX":"Smart-contract platform",
    "LINK":"Oracle infrastructure",
    "DOT":"Interoperability / blockchain network",
    "TRX":"Smart-contract / payments ecosystem",
    "TON":"Smart-contract / payments ecosystem",
    "SUI":"Smart-contract platform",
    "LTC":"Payments / settlement",
    "BCH":"Payments / settlement",
    "XLM":"Payments / settlement",
    "UNI":"Decentralized exchange protocol",
    "AAVE":"Decentralized lending protocol",
}

def utility_class(symbol, meta):
    base=symbol.replace("USDT","").upper()
    if base in UTILITY_HINTS:
        return "STRONG_UTILITY", "🟢 Strong Utility", UTILITY_HINTS[base]
    cats=[]
    if meta: cats=meta.get("categories") or []
    text=" ".join(str(x).lower() for x in cats)
    if any(k in text for k in ("smart contract","decentralized finance","defi","oracle","payments","layer 1","layer-1")):
        return "ESTABLISHED_MIXED", "🟡 Established / Mixed", "Category metadata indicates practical ecosystem use"
    return "UNVERIFIED", "⚪ Utility Unverified", "No conservative utility classification in this scanner"

def core_quality(symbol, ticker, cg):
    base=symbol[:-4] if symbol.endswith("USDT") else symbol
    meta=cg.get(base.upper(),{}) if cg else {}
    cap=float(meta.get("market_cap",0) or 0)
    vol=float(ticker.get("quoteVolume",0) or 0)
    vol_mcap=(vol/cap) if cap>0 else 0.0
    util_code,util_label,util_note=utility_class(symbol,meta)
    cap_score=clamp(cap/CORE_MARKET_CAP_USD*100)
    liq_score=clamp((vol_mcap/0.10)*100)
    # Quality is deliberately descriptive: it does not mean safety or expected return.
    quality=clamp(cap_score*.45+liq_score*.35+(100 if util_code=="STRONG_UTILITY" else 65 if util_code=="ESTABLISHED_MIXED" else 30)*.20)
    eligible=cap>=CORE_MARKET_CAP_USD and vol>0 and vol_mcap>=CORE_MIN_VOL_MCAP
    return {"market_cap_usd":round(cap,0),"volume_24h_usd":round(vol,0),"volume_mcap_ratio":round(vol_mcap*100,3),"utility_code":util_code,"utility":util_label,"utility_note":util_note,"core_quality_score":round(quality,1),"core_eligible":eligible,"core_reason":"≥$5B market cap + volume/market-cap liquidity filter" if eligible else "Fails one or more core filters"}

def acc_flow_score(x):
    # Works with deep radar fields and gracefully falls back to base fields.
    acc=float(x.get("accumulation",50) or 50); buy=float(x.get("taker_buy_ratio",0.5) or 0.5)*100
    cvd=float(x.get("cvd",50) or 50); whale=float(x.get("whale_hunter",50) or 50)
    vol=float(x.get("volume_pressure",50) or 50); fresh=float(x.get("freshness",50) or 50)
    momentum=float(x.get("momentum",50) or 50); ch=float(x.get("change24h",0) or 0)
    flow=clamp(buy*.28+cvd*.27+whale*.17+vol*.18+fresh*.10)
    late=clamp(max(0,ch-8)*4 + max(0,momentum-65)*1.2)
    score=clamp(acc*.46+flow*.54-late)
    if acc>=65 and flow>=60 and ch<8 and momentum<70: state="EARLY_ACC_FLOW"
    elif acc>=60 and flow>=58 and ch<15: state="ACC_FLOW_BUILDING"
    elif flow>=65 and ch>=15: state="LATE_FLOW"
    else: state="WATCH"
    return round(score,1),round(flow,1),state

def run_accflow_scan(core_only=True):
    started=time.time(); d=get_data(); results=d.get("results",[])
    ticks={x.get("symbol"):x for x in get_24h_tickers()}
    cg=get_coingecko_markets()
    enriched=[]
    for x in results:
        q=core_quality(x["symbol"],ticks.get(x["symbol"],{}),cg)
        if core_only and not q["core_eligible"]: continue
        score,flow,state=acc_flow_score(x)
        enriched.append({**x,**q,"acc_flow_score":score,"flow_score":flow,"acc_flow_state":state})
    # Deepen the strongest emerging candidates so CVD/Whale/VP are not just placeholders.
    candidates=sorted(enriched,key=lambda z:(z["acc_flow_score"],z.get("early_moon_ratio",0)),reverse=True)[:ACC_FLOW_DEEP_LIMIT]
    by={x["symbol"]:x for x in candidates}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fs={ex.submit(deep,{"symbol":x["symbol"],"price":x["price"],"change24h":x["change24h"],"quoteVolume24h":x["quoteVolume24h"],"f":{
            "accumulation":x.get("accumulation",50),"buy_pressure":x.get("volume_pressure",50),"compression":50,"dryup":50,"higher_lows":50,"taker_buy_ratio":x.get("taker_buy_ratio",.5),"resistance":x.get("resistance",x["price"]),"resistance_distance":x.get("distance_to_resistance",10),"resistance_score":x.get("breakout_ready",50),"momentum5":0,"overextended":x.get("change24h",0)>20,"closes":x.get("closes",[])}}):x["symbol"] for x in candidates if x["symbol"] in by}
        # Only use successful deep results when available; current radar data remains authoritative otherwise.
        for fut in as_completed(fs):
            sym=fs[fut]
            try:
                deep_x=fut.result(); old=by[sym]
                q={k:old[k] for k in ("market_cap_usd","volume_24h_usd","volume_mcap_ratio","utility_code","utility","utility_note","core_quality_score","core_eligible","core_reason") if k in old}
                sc,fl,st=acc_flow_score(deep_x)
                by[sym]={**deep_x,**q,"acc_flow_score":sc,"flow_score":fl,"acc_flow_state":st}
            except Exception: pass
    out=sorted(by.values(),key=lambda z:(z["acc_flow_score"],z.get("core_quality_score",0)),reverse=True)
    return {"status":"ok","version":APP_VERSION,"core_only":core_only,"core_filter":{"market_cap_usd":CORE_MARKET_CAP_USD,"min_volume_mcap_pct":CORE_MIN_VOL_MCAP*100},"source":"Binance Spot + CoinGecko market-cap metadata","universe_from_radar":len(results),"matched":len(enriched),"deep_checked":len(candidates),"results":out[:100],"top10":out[:10],"seconds":round(time.time()-started,2),"updated_at":int(time.time()*1000),"note":"Core Quality is a screening filter, not a safety or profit guarantee. Utility labels are conservative metadata classifications."}

def universe():
    info=get_exchange_info(); ticks={x.get("symbol"):x for x in get_24h_tickers() if x.get("symbol")}; arr=[]
    for s in info.get("symbols",[]):
        sym=s.get("symbol",""); base=s.get("baseAsset","")
        if s.get("status")!="TRADING" or s.get("quoteAsset")!="USDT" or base in STABLE_BASES or base.endswith(LEVERAGED_SUFFIXES): continue
        t=ticks.get(sym); q=float(t.get("quoteVolume",0) or 0) if t else 0
        if t and q>=MIN_QUOTE_VOLUME: arr.append(t)
    arr.sort(key=lambda x:float(x.get("quoteVolume",0) or 0),reverse=True)
    return arr[:UNIVERSE_LIMIT] if UNIVERSE_LIMIT else arr

def base_item(t):
    sym=t["symbol"]; price=float(t.get("lastPrice",0) or 0); f=basic_15m(get_klines(sym,"15m",BASE_LIMIT),price)
    if not f:return None
    pre=clamp(f["accumulation"]*.62+f["buy_pressure"]*.14+f["compression"]*.10+f["resistance_score"]*.14)
    return {"symbol":sym,"price":price,"change24h":round(float(t.get("priceChangePercent",0) or 0),2),"quoteVolume24h":round(float(t.get("quoteVolume",0) or 0)),"f":f,"pre":pre}

def early_moon_stage(f, flow, s5, volume_pressure, breakout, early, price):
    """Classify opportunity by *where it is in the move*, not by one score."""
    dist=f["resistance_distance"]
    momentum=f["momentum5"]
    fresh=clamp(100 - max(0.0,momentum)*10 - max(0.0,momentum-2.0)*4)
    if f["overextended"]:
        fresh=clamp(fresh-35)
    early_quality=clamp(
        f["accumulation"]*.24 + f["compression"]*.12 + f["buy_pressure"]*.12 +
        flow["cvd"]*.14 + flow["whale"]*.10 + flow["volume_profile"]*.08 +
        flow["depth"]*.08 + volume_pressure*.07 + breakout*.05
    )
    # EARLY-MOON RATIO rewards setup quality while penalising already-expanded moves.
    ratio=clamp(early_quality*(0.55+0.45*fresh/100.0))
    confirmed=(price > f["resistance"]*1.005 and s5["score"]>=64 and volume_pressure>=64)
    pre=(not f["overextended"] and f["accumulation"]>=58 and breakout>=60 and
         volume_pressure>=56 and dist<=4.0 and (flow["cvd"]>=54 or f["buy_pressure"]>=58))
    stealth=(not f["overextended"] and f["accumulation"]>=58 and f["compression"]>=62 and
             momentum<3.5 and breakout<76 and dist<=8.0 and ratio>=58)
    if confirmed:
        return "CONFIRMED_EXPANSION", "🟢 CONFIRMED EXPANSION", ratio, fresh, early_quality
    if pre:
        return "PRE_BREAKOUT", "🟨 PRE-BREAKOUT", ratio, fresh, early_quality
    if stealth:
        return "STEALTH_ACCUMULATION", "🟦 STEALTH ACCUMULATION", ratio, fresh, early_quality
    return "WATCH", "👀 WATCH", ratio, fresh, early_quality

def deep(item):
    s=item["symbol"]; t=item; p=item["price"]; f=item["f"]
    s1=short_tf(get_klines(s,"1m",80)); s3=short_tf(get_klines(s,"3m",80)); s5=short_tf(get_klines(s,"5m",80)); tr1=trend(get_klines(s,"1h",80)); tr4=trend(get_klines(s,"4h",80)); flow=order_flow(s)
    live=adaptive_orderflow(s)
    if live.get("trades",0)>=20:
        flow["cvd"]=round(flow["cvd"]*.55+live["cvd"]*.45,1)
        flow["whale"]=round(flow["whale"]*.55+live["whale"]*.45,1)
    liq=liquidity(t,flow["spread"]); cvd=flow["cvd"]; whale=flow["whale"]
    volume_pressure=clamp(f["buy_pressure"]*.28+s5["score"]*.22+s3["score"]*.12+s1["score"]*.08+cvd*.16+whale*.14)
    breakout=clamp(f["resistance_score"]*.28+f["compression"]*.16+volume_pressure*.22+s5["score"]*.14+flow["depth"]*.10+flow["volume_profile"]*.10)
    early=clamp(f["accumulation"]*.22+flow["smart_money"]*.17+flow["whale"]*.12+cvd*.10+volume_pressure*.14+liq*.10+breakout*.10+tr1*.03+tr4*.02)
    ai=clamp(early*.55+breakout*.18+flow["smart_money"]*.12+liq*.08+((tr1+tr4)/2)*.07)
    momentum=clamp(50+f["momentum5"]*7+s5["mom"]*8)
    risk=clamp(liq*.45+flow["spread"]*.25+(100 if not f["overextended"] else 30)*.20+((tr1+tr4)/2)*.10)
    trigger=p>f["resistance"]*1.002 and s5["score"]>=62 and volume_pressure>=58 and (cvd>=56 or f["buy_pressure"]>=62)
    expansion=f["overextended"] or (p>f["resistance"]*1.012 and s5["score"]>60)
    stage,stage_ar,early_ratio,freshness,early_quality=early_moon_stage(f,flow,s5,volume_pressure,breakout,early,p)
    # Do not let an already-expanded coin win simply because its raw AI score is high.
    if expansion and stage!="CONFIRMED_EXPANSION":
        early_ratio=clamp(early_ratio-18)
    reasons=[]
    checks=[(f["compression"]>=60,"انضغاط"),(f["dryup"]>=55,"جفاف حجم"),(f["higher_lows"]>=60,"قيعان أعلى"),(f["buy_pressure"]>=60,"ضغط شراء"),(cvd>=58,"CVD موجب"),(whale>=60,"Whale Buy"),(flow["depth"]>=60,"دعم طلبات"),(flow["volume_profile"]>=60,"Volume Profile"),(f["resistance_distance"]<=2.5,"قرب المقاومة"),(s5["breakout"],"اختراق 5m")]
    reasons=[x for ok,x in checks if ok]
    if not reasons: reasons=["مراقبة — لا توجد إشارة حاسمة بعد"]
    return {"symbol":s,"price":p,"change24h":item["change24h"],"quoteVolume24h":item["quoteVolume24h"],"stage":stage,"stage_ar":stage_ar,"ai_confidence":round(ai,1),"early_score":round(early,1),"early_moon_ratio":round(early_ratio,1),"early_quality":round(early_quality,1),"freshness":round(freshness,1),"accumulation":f["accumulation"],"smart_money":flow["smart_money"],"whale_hunter":whale,"cvd":cvd,"taker_buy_ratio":f["taker_buy_ratio"],"volume_profile":flow["volume_profile"],"volume_profile_mode":flow.get("vp_mode"),"vp_poc":flow.get("vp_poc"),"vp_hvn":flow.get("vp_hvn"),"vp_lvn":flow.get("vp_lvn"),"vp_price_position":flow.get("vp_price_position"),"volume_pressure":round(volume_pressure,1),"liquidity":liq,"breakout_ready":round(breakout,1),"momentum":round(momentum,1),"risk_safety":round(risk,1),"resistance":f["resistance"],"distance_to_resistance":f["resistance_distance"],"tf_1h":round(tr1,1),"tf_4h":round(tr4,1),"spread_pct":flow.get("spread_pct"),"live_cvd":live.get("cvd",50),"live_whale":live.get("whale",50),"live_trades":live.get("trades",0),"volume_1m_ratio":s1["vr"],"volume_5m_ratio":s5["vr"],"why":reasons[:8],"closes":f["closes"],"flags":{"compression":f["compression"]>=60,"dryup":f["dryup"]>=55,"buy_pressure":f["buy_pressure"]>=60,"cvd":cvd>=58,"whale":whale>=60,"volume_profile":flow["volume_profile"]>=60,"absorption":flow["depth"]>=60 and f["compression"]>=55,"breakout":trigger}}

def fallback(item):
    f=item["f"]; score=clamp(f["accumulation"]*.70+f["buy_pressure"]*.15+f["resistance_score"]*.15); stage="ACCUMULATION" if score>=52 else "WATCH"
    return {"symbol":item["symbol"],"price":item["price"],"change24h":item["change24h"],"quoteVolume24h":item["quoteVolume24h"],"stage":stage,"stage_ar":"🟦 ACCUMULATION" if stage=="ACCUMULATION" else "👀 WATCH","ai_confidence":round(score,1),"early_score":round(score,1),"early_moon_ratio":round(clamp(score*.85),1),"early_quality":round(score,1),"freshness":round(clamp(100-max(0,f["momentum5"])*10),1),"accumulation":f["accumulation"],"smart_money":50.0,"whale_hunter":50.0,"cvd":50.0,"taker_buy_ratio":f["taker_buy_ratio"],"volume_profile":50.0,"volume_profile_mode":"pending","vp_poc":None,"vp_hvn":None,"vp_lvn":None,"vp_price_position":None,"volume_pressure":round(f["buy_pressure"],1),"liquidity":0.0,"breakout_ready":round(f["resistance_score"],1),"momentum":round(50+f["momentum5"]*5,1),"risk_safety":50.0,"resistance":f["resistance"],"distance_to_resistance":f["resistance_distance"],"tf_1h":50.0,"tf_4h":50.0,"spread_pct":None,"live_cvd":50.0,"live_whale":50.0,"live_trades":0,"volume_1m_ratio":1.0,"volume_5m_ratio":1.0,"why":["تحليل أساسي 15m — التحليل العميق مؤجل"],"closes":f["closes"],"flags":{"compression":f["compression"]>=60,"dryup":f["dryup"]>=55,"buy_pressure":f["buy_pressure"]>=60,"cvd":False,"whale":False,"volume_profile":False,"absorption":False,"breakout":False}}

def run_scan():
    started=time.time(); KLINE_ERRORS.clear(); uni=universe(); bases=[]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fs=[ex.submit(base_item,t) for t in uni]
        for f in as_completed(fs):
            try:
                x=f.result()
                if x:bases.append(x)
            except Exception: pass
    bases.sort(key=lambda x:x["pre"],reverse=True)
    # V3.6: live order-flow tier follows both liquidity and emerging candidates.
    liquid=sorted(uni,key=lambda x:float(x.get("quoteVolume",0) or 0),reverse=True)[:80]
    emerging=bases[:40]
    ws_candidates={x["symbol"]:x for x in liquid}
    for x in emerging: ws_candidates.setdefault(x["symbol"],x)
    start_ws_monitor(list(ws_candidates.values()))
    selected=bases[:DEEP_LIMIT]; deep_map={}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fs={ex.submit(deep,x):x["symbol"] for x in selected}
        for f in as_completed(fs):
            sym=fs[f]
            try: deep_map[sym]=f.result()
            except Exception: pass
    results=[deep_map.get(x["symbol"],fallback(x)) for x in bases]
    results.sort(key=lambda x:(x.get("early_moon_ratio",0),x.get("ai_confidence",0),x.get("early_score",0)),reverse=True)
    return {"status":"ok","version":APP_VERSION,"scanned_universe":len(uni),"base_success":len(bases),"base_failed":max(0,len(uni)-len(bases)),"deep_analyzed":len(deep_map),"deep_failed":max(0,len(selected)-len(deep_map)),"results":results,"top5":results[:5],"kline_errors":dict(list(KLINE_ERRORS.items())[-30:]),"scan_seconds":round(time.time()-started,2),"updated_at":int(time.time()*1000)}


def _historical_score(k, i):
    # Signal features use only candles before index i.
    window=k[max(0,i-100):i]
    if len(window)<60: return None
    raw=[[x["t"],x["o"],x["h"],x["l"],x["c"],x["v"],0,x["qv"],x["n"],x["tb"]] for x in window]
    f=basic_15m(raw,window[-1]["c"]); vp=volume_profile_from_klines(raw)
    if not f or not vp:return None
    taker=f["taker_buy_ratio"]
    return {"acc":f["accumulation"],"buy":f["buy_pressure"],"compress":f["compression"],"taker":taker*100,"vp":vp["score"],"res":f["resistance_score"],"rsi":f["rsi"],"overextended":f["overextended"]}

def eval_combo(k, features, target=0.02, stop=0.015, horizon=16):
    signals=wins=losses=amb=0; rets=[]; mfe=[]
    for i,f in features:
        score=0.0
        # Three complementary families: accumulation, flow, location/VP.
        score=(f["acc"]*.34+f["buy"]*.14+f["taker"]*.16+f["vp"]*.14+f["compress"]*.10+f["res"]*.12)
        if score<65: continue
        signals+=1; entry=k[i]["o"]; tp=entry*(1+target); sl=entry*(1-stop); out=None; mh=entry
        for j in range(i,min(i+horizon+1,len(k))):
            mh=max(mh,k[j]["h"]); hit_tp=k[j]["h"]>=tp; hit_sl=k[j]["l"]<=sl
            if hit_tp and hit_sl: out="ambiguous"; amb+=1; exitp=sl; break
            if hit_tp: out="win"; wins+=1; exitp=tp; break
            if hit_sl: out="loss"; losses+=1; exitp=sl; break
        if out is None: exitp=k[min(i+horizon,len(k)-1)]["c"]
        rets.append((exitp-entry)/entry*100); mfe.append((mh-entry)/entry*100)
    evaluated=wins+losses+amb
    return {"signals":signals,"wins":wins,"losses":losses,"ambiguous":amb,"evaluated":evaluated,"win_rate":round(wins/evaluated*100,2) if evaluated else 0,"avg_return_pct":round(mean(rets,0),3),"avg_mfe_pct":round(mean(mfe,0),3),"score":round((wins/evaluated*100 if evaluated else 0)*0.65+mean(rets,0)*3+min(mean(mfe,0),10)*1.5,2)}

def backtest_multi_symbol(symbol, days=BACKTEST_DAYS):
    raw=get_historical_klines(symbol,"15m",days); k=parse(raw)
    if len(k)<180:return {"symbol":symbol,"status":"insufficient","signals":0}
    features=[]
    for i in range(100,len(k)-BACKTEST_HORIZON-1):
        f=_historical_score(k,i)
        if f: features.append((i,f))
    combos={
      "ACC+FLOW+VP": (0,),
      "ACC+FLOW": (1,),
      "ACC+VP": (2,),
      "FLOW+VP": (3,),
    }
    # Explicit thresholds create interpretable pattern families rather than a black box.
    definitions={
      "ACC+FLOW+VP": lambda f: f["acc"]>=65 and f["taker"]>=53 and f["vp"]>=55,
      "ACC+FLOW": lambda f: f["acc"]>=65 and f["taker"]>=53,
      "ACC+VP": lambda f: f["acc"]>=65 and f["vp"]>=55,
      "FLOW+VP": lambda f: f["taker"]>=53 and f["vp"]>=55,
      "EARLY_COMPRESSION": lambda f: f["compress"]>=65 and f["acc"]>=60 and f["res"]>=70,
    }
    results=[]
    for name,fn in definitions.items():
        subset=[(i,f) for i,f in features if fn(f)]
        r=eval_combo(k,subset,target=.02,stop=BACKTEST_STOP,horizon=BACKTEST_HORIZON)
        r.update({"pattern":name,"symbol":symbol})
        results.append(r)
    best=max(results,key=lambda x:x.get("score",0)) if results else {"pattern":"none","score":0,"win_rate":0,"signals":0,"avg_return_pct":0,"avg_mfe_pct":0}
    return {"symbol":symbol,"status":"ok","candles":len(k),"days":days,"best":best,"patterns":results}

def run_multi_backtest(top_n=BACKTEST_TOP_N,days=BACKTEST_DAYS):
    data=get_data(); candidates=data.get("results",[])[:max(30,min(50,int(top_n)))]
    started=time.time(); rows=[]
    with ThreadPoolExecutor(max_workers=8) as ex:
        fs={ex.submit(backtest_multi_symbol,c["symbol"],days):c["symbol"] for c in candidates}
        for f in as_completed(fs):
            try: rows.append(f.result())
            except Exception as e: rows.append({"symbol":fs[f],"status":"error","error":str(e)})
    ok=[r for r in rows if r.get("status")=="ok"]
    leaderboard=[]
    for r in ok: leaderboard.append(r["best"])
    leaderboard.sort(key=lambda x:(x.get("score",0),x.get("win_rate",0),x.get("avg_return_pct",0)),reverse=True)
    patterns={}
    for r in ok:
        for p in r.get("patterns",[]):
            a=patterns.setdefault(p["pattern"],{"pattern":p["pattern"],"signals":0,"evaluated":0,"wins":0,"avg_returns":[],"win_rates":[]})
            a["signals"]+=p.get("signals",0); a["evaluated"]+=p.get("evaluated",0); a["wins"]+=p.get("wins",0); a["avg_returns"].append(p.get("avg_return_pct",0))
    for a in patterns.values():
        a["win_rate"]=round(a["wins"]/a["evaluated"]*100,2) if a["evaluated"] else 0
        a["avg_return_pct"]=round(mean(a.pop("avg_returns"),0),3)
        a["score"]=round(a["win_rate"]*.7+a["avg_return_pct"]*3,2)
    pattern_board=sorted(patterns.values(),key=lambda x:(x["score"],x["win_rate"]),reverse=True)
    result={"status":"ok","version":APP_VERSION,"top_n":len(candidates),"days":days,"tested":len(ok),"failed":len(candidates)-len(ok),"leaderboard":leaderboard[:50],"pattern_leaderboard":pattern_board,"details":rows,"seconds":round(time.time()-started,2),"updated_at":int(time.time()*1000)}
    BACKTEST_CACHE["last"]=result
    return result

def get_data():
    now=time.time()
    with CACHE_LOCK:
        if RADAR_CACHE.get("status")=="ok" and now-RADAR_CACHE.get("updated_at",0)/1000<CACHE_SECONDS:return RADAR_CACHE
    if not SCAN_LOCK.acquire(False):
        with CACHE_LOCK:return RADAR_CACHE
    try:
        d=run_scan()
        with CACHE_LOCK: RADAR_CACHE.clear(); RADAR_CACHE.update(d)
        return d
    finally: SCAN_LOCK.release()

def backtest_symbol(symbol, days=30, interval="15m", target=0.02, stop=0.015, horizon=16, threshold=70):
    symbol=symbol.upper().strip(); raw=get_historical_klines(symbol,interval,days); k=parse(raw)
    if len(k)<140: raise RuntimeError(f"بيانات تاريخية غير كافية: {len(k)} شمعة")
    signals=[]; wins=losses=ambiguous=0; returns=[]; mfe=[]
    warm=100; last_i=len(k)-horizon-1
    for i in range(warm,last_i+1):
        window=k[i-100:i]
        # Use only candles strictly BEFORE the signal candle.
        f=basic_15m([[x["t"],x["o"],x["h"],x["l"],x["c"],x["v"],0,0,0, x["tb"]] for x in window],window[-1]["c"])
        vp=volume_profile_from_klines([[x["t"],x["o"],x["h"],x["l"],x["c"],x["v"],0,x["qv"],x["n"],x["tb"]] for x in window])
        if not f: continue
        score=clamp(f["accumulation"]*.60+f["buy_pressure"]*.14+f["resistance_score"]*.10+vp["score"]*.10+(f["compression"]*.06))
        if score<threshold: continue
        entry=k[i]["o"]
        tp=entry*(1+target); sl=entry*(1-stop); outcome=None; exit_price=entry; bars=0
        max_high=entry; min_low=entry
        for j in range(i,min(i+horizon,len(k)-1)):
            bar=k[j]; max_high=max(max_high,bar["h"]); min_low=min(min_low,bar["l"]); bars+=1
            hit_tp=bar["h"]>=tp; hit_sl=bar["l"]<=sl
            if hit_tp and hit_sl:
                outcome="loss_ambiguous"; exit_price=sl; ambiguous+=1; break
            if hit_tp:
                outcome="win"; exit_price=tp; wins+=1; break
            if hit_sl:
                outcome="loss"; exit_price=sl; losses+=1; break
        if outcome is None:
            outcome="expired"; exit_price=k[min(i+horizon,len(k)-1)]["c"]; bars=horizon
        ret=(exit_price-entry)/entry*100
        returns.append(ret); mfe.append((max_high-entry)/entry*100)
        signals.append({"time":k[i]["t"],"entry":entry,"score":round(score,1),"outcome":outcome,"return_pct":round(ret,3),"mfe_pct":round((max_high-entry)/entry*100,3),"bars":bars})
    evaluated=wins+losses+ambiguous
    win_rate=(wins/evaluated*100) if evaluated else 0
    avg_ret=mean(returns,0)
    return {"symbol":symbol,"interval":interval,"days":days,"target_pct":target*100,"stop_pct":stop*100,"horizon_bars":horizon,"threshold":threshold,"candles":len(k),"signals":len(signals),"evaluated":evaluated,"wins":wins,"losses":losses,"ambiguous":ambiguous,"expired":len(signals)-evaluated,"win_rate":round(win_rate,2),"avg_return_pct":round(avg_ret,3),"median_return_pct":round(statistics.median(returns),3) if returns else 0,"avg_mfe_pct":round(mean(mfe,0),3),"best_return_pct":round(max(returns),3) if returns else 0,"worst_return_pct":round(min(returns),3) if returns else 0,"recent_signals":signals[-20:]}

@app.get("/")
def root(): return FileResponse(str(FRONTEND_DIR/"index.html"))
@app.get("/api/health")
def health():
    return {"status":"online","app":"AI CRYPTO RADAR","version":APP_VERSION,"websocket":bool(websocket is not None)}
@app.get("/api/binance-test")
def binance_test():
    st=time.time()
    try:
        request_json("/api/v3/ping"); tm=request_json("/api/v3/time")
        return {"status":"ok","binance":"connected","ping_ms":round((time.time()-st)*1000),"server_time":tm.get("serverTime")}
    except Exception as e:return {"status":"error","binance":"not_connected","error":str(e)}
@app.get("/api/radar")
def radar(): return get_data()
@app.get("/api/debug")
def debug():
    try:
        info=get_exchange_info(); ticks=get_24h_tickers(); mp={x.get("symbol"):x for x in ticks}; samples={}
        for s in ("BTCUSDT","ETHUSDT","SOLUSDT"):
            raw=get_klines(s,"15m",10); samples[s]={"klines":len(raw),"error":KLINE_ERRORS.get(s+":15m:") or KLINE_ERRORS.get(s+":15m")}
        eligible=[x for x in info.get("symbols",[]) if x.get("status")=="TRADING" and x.get("quoteAsset")=="USDT" and x.get("baseAsset") not in STABLE_BASES and not x.get("baseAsset","").endswith(LEVERAGED_SUFFIXES) and float(mp.get(x.get("symbol"),{}).get("quoteVolume",0) or 0)>=MIN_QUOTE_VOLUME]
        return {"status":"ok","version":APP_VERSION,"exchange_symbols":len(info.get("symbols",[])),"ticker_rows":len(ticks),"eligible_spot_usdt":len(eligible),"sample_symbols":[x.get("symbol") for x in eligible[:10]],"sample_15m":samples,"recent_kline_errors":dict(list(KLINE_ERRORS.items())[-30:])}
    except Exception as e:return {"status":"error","version":APP_VERSION,"error":str(e)}
@app.get("/api/orderflow/status")
def orderflow_status():
    with WS_LOCK:
        return {**WS_STATE,"live_symbols":sum(1 for x in WS_FLOW.values() if x.get("trades",0)>0),"samples":[ws_snapshot(s) for s in list(WS_FLOW.keys())[:10]]}

@app.get("/api/orderflow/{symbol}")
def orderflow_symbol(symbol: str):
    s=adaptive_orderflow(symbol.upper().strip())
    return {"status":"ok","data":s}

@app.get("/api/backtest/top")
def backtest_top(top_n:int=Query(50,ge=30,le=50),days:int=Query(30,ge=7,le=90)):
    try:
        return run_multi_backtest(top_n,days)
    except Exception as e:
        return {"status":"error","error":str(e)}

@app.get("/api/backtest/last")
def backtest_last():
    return BACKTEST_CACHE.get("last",{"status":"empty"})

@app.get("/api/accflow")
def accflow(core_only: bool=Query(True)):
    try:return run_accflow_scan(core_only=core_only)
    except Exception as e:return {"status":"error","version":APP_VERSION,"error":str(e)}

@app.get("/api/status")
def status():
    with CACHE_LOCK:return {"status":RADAR_CACHE.get("status"),"version":APP_VERSION,"last_update":RADAR_CACHE.get("updated_at"),"scan_seconds":RADAR_CACHE.get("scan_seconds",0),"results":len(RADAR_CACHE.get("results",[])),"universe":RADAR_CACHE.get("scanned_universe",0),"deep_analyzed":RADAR_CACHE.get("deep_analyzed",0)}
@app.get("/api/volume-profile/{symbol}")
def volume_profile(symbol: str):
    symbol=symbol.upper().strip()
    tr=request_json("/api/v3/aggTrades",{"symbol":symbol,"limit":1000})
    vp=volume_profile_from_trades(tr,VP_BINS)
    if not vp:
        raw=get_klines(symbol,"15m",200); vp=volume_profile_from_klines(raw,VP_BINS); vp["mode"]="kline"
    return {"status":"ok","symbol":symbol,"profile":vp,"note":"trades = exact recent trade-price profile; kline = range-allocated volume profile"}
@app.get("/api/backtest")
def backtest(symbol: str=Query(...), days:int=Query(30,ge=7,le=90), interval:str=Query("15m"), target:float=Query(0.02,gt=0.001,le=0.20), stop:float=Query(0.015,gt=0.001,le=0.20), horizon:int=Query(16,ge=2,le=96), threshold:float=Query(70,ge=40,le=95)):
    if interval not in ("5m","15m","1h"): return {"status":"error","error":"interval must be 5m, 15m or 1h"}
    try:return {"status":"ok",**backtest_symbol(symbol,days,interval,target,stop,horizon,threshold)}
    except Exception as e:return {"status":"error","error":str(e),"symbol":symbol.upper()}
