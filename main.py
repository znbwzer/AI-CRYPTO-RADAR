from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import requests, time, math, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from pathlib import Path

APP_VERSION = "V2.2-AI-CRYPTO-RADAR"
BINANCE_API = "https://data-api.binance.vision"
TIMEOUT = 12
CACHE_SECONDS = 70
MIN_QUOTE_VOLUME = 100_000
UNIVERSE_LIMIT = 0  # 0 = every eligible Spot USDT pair above MIN_QUOTE_VOLUME
BASE_LIMIT = 100
DEEP_LIMIT = 30
MAX_WORKERS = 16

app = FastAPI(title="AI CRYPTO RADAR", version=APP_VERSION)
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

SCAN_LOCK, CACHE_LOCK = Lock(), Lock()
RADAR_CACHE = {"status":"warming_up","results":[],"top5":[],"updated_at":0}
KLINE_CACHE, KLINE_ERRORS = {}, {}
EXCHANGE_CACHE, TICKER_CACHE = {"data":None,"ts":0}, {"data":None,"ts":0}

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
                time.sleep(min(4,1.2*(attempt+1))); continue
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

def get_klines(symbol, interval, limit=100):
    key=(symbol,interval,limit); now=time.time(); old=KLINE_CACHE.get(key)
    ttl=7 if interval in ("1m","3m","5m") else 25
    if old and now-old[0]<ttl: return old[1]
    try:
        d=request_json("/api/v3/klines",{"symbol":symbol,"interval":interval,"limit":limit})
        KLINE_CACHE[key]=(now,d); return d
    except Exception as e:
        KLINE_ERRORS[f"{symbol}:{interval}"]={"error":str(e),"time":int(now*1000)}; return []

def parse(raw):
    out=[]
    for x in raw or []:
        try: out.append({"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5]),"tb":float(x[9]),"t":int(x[0])})
        except Exception: pass
    return out

def completed(raw):
    return raw[:-1] if len(raw)>3 else raw

def basic_15m(raw, price):
    k=completed(parse(raw))
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
    compression=clamp(compression)
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

def order_flow(symbol):
    out={"cvd":50.0,"whale":50.0,"depth":50.0,"spread":50.0,"volume_profile":50.0}
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
                    if bool(t["m"]):swh+=n
                    else:bwh+=n
            out["whale"]=round(clamp((bwh/(bwh+swh)-.30)/.40*100) if bwh+swh else 50,1)
    except Exception: pass
    try:
        d=request_json("/api/v3/depth",{"symbol":symbol,"limit":50}); bids=d.get("bids",[]); asks=d.get("asks",[])
        bv=sum(float(x[1]) for x in bids); av=sum(float(x[1]) for x in asks); total=bv+av; imb=(bv-av)/total if total else 0
        out["depth"]=round(clamp((imb+.22)/.44*100),1)
        if bids and asks:
            bid,ask=float(bids[0][0]),float(asks[0][0]); mid=(bid+ask)/2; sp=(ask-bid)/mid*100 if mid else 1; out["spread_pct"]=round(sp,4)
            out["spread"]=100 if sp<=.03 else 90 if sp<=.08 else 70 if sp<=.20 else 45 if sp<=.5 else 20
        # Simple visible order-book concentration proxy near mid.
        near_b=sum(float(q) for p,q in bids[:10]); near_a=sum(float(q) for p,q in asks[:10]); nt=near_b+near_a
        out["volume_profile"]=round(clamp((near_b/nt-.35)/.30*100) if nt else 50,1)
    except Exception: pass
    out["smart_money"]=round(clamp(out["cvd"]*.35+out["whale"]*.30+out["depth"]*.25+out["volume_profile"]*.10),1)
    return out

def liquidity(t, spread):
    q=float(t.get("quoteVolume",0) or 0)
    vs=100 if q>=50e6 else 90 if q>=10e6 else 78 if q>=3e6 else 65 if q>=1e6 else 50 if q>=3e5 else 25
    return round(clamp(vs*.72+spread*.28),1)

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

def deep(item):
    s=item["symbol"]; t=item; p=item["price"]; f=item["f"]
    s1=short_tf(get_klines(s,"1m",80)); s3=short_tf(get_klines(s,"3m",80)); s5=short_tf(get_klines(s,"5m",80)); tr1=trend(get_klines(s,"1h",80)); tr4=trend(get_klines(s,"4h",80)); flow=order_flow(s)
    liq=liquidity(t,flow["spread"])
    cvd=flow["cvd"]; whale=flow["whale"]
    volume_pressure=clamp(f["buy_pressure"]*.28+s5["score"]*.22+s3["score"]*.12+s1["score"]*.08+cvd*.16+whale*.14)
    breakout=clamp(f["resistance_score"]*.28+f["compression"]*.16+volume_pressure*.22+s5["score"]*.14+flow["depth"]*.10+flow["volume_profile"]*.10)
    early=clamp(f["accumulation"]*.22+flow["smart_money"]*.17+flow["whale"]*.12+cvd*.10+volume_pressure*.14+liq*.10+breakout*.10+tr1*.03+tr4*.02)
    ai=clamp(early*.55+breakout*.18+flow["smart_money"]*.12+liq*.08+((tr1+tr4)/2)*.07)
    momentum=clamp(50+f["momentum5"]*7+s5["mom"]*8)
    risk=clamp(liq*.45+flow["spread"]*.25+(100 if not f["overextended"] else 30)*.20+((tr1+tr4)/2)*.10)
    trigger=p>f["resistance"]*1.002 and s5["score"]>=62 and volume_pressure>=58 and (cvd>=56 or f["buy_pressure"]>=62)
    expansion=f["overextended"] or (p>f["resistance"]*1.012 and s5["score"]>60)
    if trigger: stage,stage_ar="TRIGGER","🟩 TRIGGER"
    elif expansion: stage,stage_ar="EXPANSION","🚀 EXPANSION"
    elif early>=62 and breakout>=62: stage,stage_ar="READY","🟨 READY"
    elif f["accumulation"]>=52: stage,stage_ar="ACCUMULATION","🟦 ACCUMULATION"
    else: stage,stage_ar="WATCH","👀 WATCH"
    if expansion: early=clamp(early-15)
    if trigger: early=clamp(early-3)
    reasons=[]
    checks=[(f["compression"]>=60,"انضغاط"),(f["dryup"]>=55,"جفاف حجم"),(f["higher_lows"]>=60,"قيعان أعلى"),(f["buy_pressure"]>=60,"ضغط شراء"),(cvd>=58,"CVD موجب"),(whale>=60,"Whale Buy"),(flow["depth"]>=60,"دعم طلبات"),(flow["volume_profile"]>=60,"Volume Profile"),(f["resistance_distance"]<=2.5,"قرب المقاومة"),(s5["breakout"],"اختراق 5m")]
    reasons=[x for ok,x in checks if ok]
    if not reasons: reasons=["مراقبة — لا توجد إشارة حاسمة بعد"]
    return {"symbol":s,"price":p,"change24h":item["change24h"],"quoteVolume24h":item["quoteVolume24h"],"stage":stage,"stage_ar":stage_ar,"ai_confidence":round(ai,1),"early_score":round(early,1),"accumulation":f["accumulation"],"smart_money":flow["smart_money"],"whale_hunter":whale,"cvd":cvd,"taker_buy_ratio":f["taker_buy_ratio"],"volume_profile":flow["volume_profile"],"volume_pressure":round(volume_pressure,1),"liquidity":liq,"breakout_ready":round(breakout,1),"momentum":round(momentum,1),"risk_safety":round(risk,1),"resistance":f["resistance"],"distance_to_resistance":f["resistance_distance"],"tf_1h":round(tr1,1),"tf_4h":round(tr4,1),"spread_pct":flow.get("spread_pct"),"volume_1m_ratio":s1["vr"],"volume_5m_ratio":s5["vr"],"why":reasons[:8],"closes":f["closes"],"flags":{"compression":f["compression"]>=60,"dryup":f["dryup"]>=55,"buy_pressure":f["buy_pressure"]>=60,"cvd":cvd>=58,"whale":whale>=60,"volume_profile":flow["volume_profile"]>=60,"absorption":flow["depth"]>=60 and f["compression"]>=55,"breakout":trigger}}

def fallback(item):
    f=item["f"]
    score=clamp(f["accumulation"]*.70+f["buy_pressure"]*.15+f["resistance_score"]*.15)
    stage="ACCUMULATION" if score>=52 else "WATCH"
    return {"symbol":item["symbol"],"price":item["price"],"change24h":item["change24h"],"quoteVolume24h":item["quoteVolume24h"],"stage":stage,"stage_ar":"🟦 ACCUMULATION" if stage=="ACCUMULATION" else "👀 WATCH","ai_confidence":round(score,1),"early_score":round(score,1),"accumulation":f["accumulation"],"smart_money":50.0,"whale_hunter":50.0,"cvd":50.0,"taker_buy_ratio":f["taker_buy_ratio"],"volume_profile":50.0,"volume_pressure":round(f["buy_pressure"],1),"liquidity":0.0,"breakout_ready":round(f["resistance_score"],1),"momentum":round(50+f["momentum5"]*5,1),"risk_safety":50.0,"resistance":f["resistance"],"distance_to_resistance":f["resistance_distance"],"tf_1h":50.0,"tf_4h":50.0,"spread_pct":None,"volume_1m_ratio":1.0,"volume_5m_ratio":1.0,"why":["تحليل أساسي 15m — التحليل العميق مؤجل"],"closes":f["closes"],"flags":{"compression":f["compression"]>=60,"dryup":f["dryup"]>=55,"buy_pressure":f["buy_pressure"]>=60,"cvd":False,"whale":False,"volume_profile":False,"absorption":False,"breakout":False}}

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
    selected=bases[:DEEP_LIMIT]; deep_map={}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fs={ex.submit(deep,x):x["symbol"] for x in selected}
        for f in as_completed(fs):
            sym=fs[f]
            try: deep_map[sym]=f.result()
            except Exception: pass
    # Never show an empty radar merely because deep analysis had a transient error.
    results=[deep_map.get(x["symbol"],fallback(x)) for x in bases]
    results.sort(key=lambda x:(x["ai_confidence"],x["early_score"]),reverse=True)
    return {"status":"ok","version":APP_VERSION,"scanned_universe":len(uni),"base_success":len(bases),"base_failed":max(0,len(uni)-len(bases)),"deep_analyzed":len(deep_map),"deep_failed":max(0,len(selected)-len(deep_map)),"results":results,"top5":results[:5],"kline_errors":dict(list(KLINE_ERRORS.items())[-30:]),"scan_seconds":round(time.time()-started,2),"updated_at":int(time.time()*1000)}

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

@app.get("/")
def root(): return FileResponse(str(FRONTEND_DIR/"index.html"))
@app.get("/api/health")
def health(): return {"status":"online","app":"AI CRYPTO RADAR","version":APP_VERSION}
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
            raw=get_klines(s,"15m",10); samples[s]={"klines":len(raw),"error":KLINE_ERRORS.get(s+":15m")}
        eligible=[x for x in info.get("symbols",[]) if x.get("status")=="TRADING" and x.get("quoteAsset")=="USDT" and x.get("baseAsset") not in STABLE_BASES and not x.get("baseAsset","").endswith(LEVERAGED_SUFFIXES) and float(mp.get(x.get("symbol"),{}).get("quoteVolume",0) or 0)>=MIN_QUOTE_VOLUME]
        return {"status":"ok","version":APP_VERSION,"exchange_symbols":len(info.get("symbols",[])),"ticker_rows":len(ticks),"eligible_spot_usdt":len(eligible),"sample_symbols":[x.get("symbol") for x in eligible[:10]],"sample_15m":samples,"recent_kline_errors":dict(list(KLINE_ERRORS.items())[-30:])}
    except Exception as e:return {"status":"error","version":APP_VERSION,"error":str(e)}
@app.get("/api/status")
def status():
    with CACHE_LOCK:return {"status":RADAR_CACHE.get("status"),"version":APP_VERSION,"last_update":RADAR_CACHE.get("updated_at"),"scan_seconds":RADAR_CACHE.get("scan_seconds",0),"results":len(RADAR_CACHE.get("results",[])),"universe":RADAR_CACHE.get("scanned_universe",0),"deep_analyzed":RADAR_CACHE.get("deep_analyzed",0)}
