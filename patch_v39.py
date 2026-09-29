from pathlib import Path
p=Path('/mnt/data/v39/main.py')
s=p.read_text()
s=s.replace('APP_VERSION = "V3.8-ARABIC-STRATEGY-HUNTER"','APP_VERSION = "V3.9-EARLY-ACCUMULATION-ANALYZER"')
start=s.index('def obv_from_klines(raw):')
end=s.index('\ndef atr_pct', start)
new=r'''def obv_series(raw):
    k=completed(parse(raw)); vals=[]; obv=0.0
    for i in range(1,len(k)):
        if k[i]["c"]>k[i-1]["c"]: obv+=k[i]["v"]
        elif k[i]["c"]<k[i-1]["c"]: obv-=k[i]["v"]
        vals.append(obv)
    return k, vals

def obv_from_klines(raw):
    k,vals=obv_series(raw)
    if len(vals)<10:return 50.0
    base=mean([abs(x) for x in vals[-20:]]) or 1.0
    slope=(vals[-1]-vals[-6])/base*100.0 if len(vals)>=6 else 0
    return round(clamp(50+slope*2.0),1)

def obv_detail(raw, window=15):
    k,vals=obv_series(raw)
    if len(vals)<max(8,window+2): return {"score":50.0,"trend_pct":0.0,"direction":"→","window":window,"raw":vals[-1] if vals else 0}
    end=vals[-1]; prev=vals[-1-window]
    denom=max(abs(prev), mean([abs(x) for x in vals[-min(30,len(vals)):]])*0.08, 1e-12)
    change=(end-prev)/denom*100.0
    direction="↑" if change>2 else "↓" if change<-2 else "→"
    base=mean([abs(x) for x in vals[-20:]]) or 1.0
    score=clamp(50+((end-vals[-6])/base*2 if len(vals)>=6 else 0))
    return {"score":round(score,1),"trend_pct":round(change,2),"direction":direction,"window":window,"raw":round(end,4)}

def volume_detail(raw, window=15):
    k=completed(parse(raw)); v=[x["v"] for x in k]
    if len(v)<10:return {"current":1.0,"trend_pct":0.0,"direction":"→","sequence":[]}
    ref=mean(v[-25:-5]) or mean(v[:-1]) or 1.0
    current=v[-1]/ref
    samples=[]
    for off in [4,3,2,1,0]:
        idx=len(v)-1-off
        if idx>=0:
            local=mean(v[max(0,idx-4):idx]) or ref
            samples.append(round(v[idx]/local,2))
    old=mean(v[-min(len(v),window+5):-5]) or ref
    new=mean(v[-5:]) or ref
    ch=(new-old)/old*100 if old else 0
    return {"current":round(current,2),"trend_pct":round(ch,1),"direction":"↑" if ch>10 else "↓" if ch<-10 else "→","sequence":samples}

def flow_history(raw, window=15):
    k=completed(parse(raw)); deltas=[]; ratios=[]
    for x in k:
        q=x["v"]*x["c"]; buy=x["tb"]*x["c"]; sell=max(0,q-buy); deltas.append(buy-sell); ratios.append(buy/q if q else .5)
    if len(deltas)<10:return {"delta_now":0.0,"delta_change_pct":0.0,"taker_buy_ratio":0.5,"taker_trend_pct":0.0,"direction":"→"}
    recent=sum(deltas[-5:]); prior=sum(deltas[-20:-5]) or 1e-9
    tr=sum(deltas[-15:]); old=sum(deltas[-30:-15]) if len(deltas)>=30 else sum(deltas[:-15])
    dch=(tr-old)/abs(old)*100 if old else (100 if tr>0 else -100 if tr<0 else 0)
    rb=mean(ratios[-5:]); ob=mean(ratios[-20:-5]) or .5
    rch=(rb-ob)*100
    return {"delta_now":round(recent,2),"delta_change_pct":round(dch,1),"taker_buy_ratio":round(rb,4),"taker_trend_pct":round(rch,1),"direction":"↑" if dch>10 or rch>2 else "↓" if dch<-10 or rch<-2 else "→"}
'''
s=s[:start]+new+s[end:]
# Replace tf_metrics
start=s.index('def tf_metrics(symbol, interval, limit=100):')
end=s.index('\ndef strategy_scan',start)
new=r'''def tf_metrics(symbol, interval, limit=100):
    raw=get_klines(symbol,interval,limit); k=completed(parse(raw))
    if len(k)<30:return {"interval":interval,"rsi":50.0,"obv":50.0,"volume_ratio":1.0,"atr_pct":0.0,"momentum":0.0,"obv_detail":obv_detail(raw),"volume_detail":volume_detail(raw),**sr_levels(raw)}
    c=[x['c'] for x in k]; v=[x['v'] for x in k]
    return {"interval":interval,"rsi":round(rsi(c),1),"obv":obv_from_klines(raw),"obv_detail":obv_detail(raw,15),"volume_ratio":round(v[-1]/(mean(v[-21:-1]) or v[-1]),2),"volume_detail":volume_detail(raw,15),"flow_history":flow_history(raw,15),"atr_pct":atr_pct(raw),"momentum":round(pct(c[-1],c[-6]),3),**sr_levels(raw)}

def multi_period_change(raw, bars):
    k=completed(parse(raw)); c=[x["c"] for x in k]
    if len(c)<=bars:return 0.0
    return round((c[-1]/c[-1-bars]-1)*100,2) if c[-1-bars] else 0.0

def confirmation_engine(d, m1, m5):
    obv=m5["obv_detail"]; vol=m5["volume_detail"]; fh=m5["flow_history"]
    cvd=float(d.get("cvd",50)); flow=float(d.get("flow",50)); whale=float(d.get("whale",50)); liq=float(d.get("liquidity",50))
    dist=float(d.get("resistance_distance") or 99); price=float(d.get("price") or 0); res=d.get("resistance")
    rsi15=float(d.get("rsi") or 50)
    checks=[]; missing=[]
    def ck(ok,label): (checks if ok else missing).append(label)
    ck(obv["trend_pct"]>2,"OBV صاعد")
    ck(vol["current"]>=0.70 and vol["trend_pct"]>5,"الحجم يرتفع")
    ck(cvd>=55 or fh["delta_change_pct"]>10,"CVD/Flow يتحسن")
    ck(flow>=60,"Flow جيد")
    ck(rsi15>=55 and rsi15<=70,"RSI ضمن النطاق")
    ck(liq>=45,"السيولة مقبولة")
    breakout=bool(res and price>res*1.005 and vol["current"]>=1.2 and cvd>=65 and flow>=70 and obv["trend_pct"]>5)
    if breakout:
        stage="CONFIRMED_EXPANSION"; label="🟢 CONFIRMED EXPANSION"; status="CONFIRMED"; reason="اختراق + حجم + CVD/Flow + OBV يؤكدون توسع الحركة"
    elif d.get("stage")=="PRE_BREAKOUT" and cvd>=55 and obv["trend_pct"]>2 and vol["current"]>=0.7:
        stage="PRE_BREAKOUT"; label="🟨 PRE-BREAKOUT"; status="WAIT_BREAKOUT"; reason="العملة تقترب من الاختراق لكن نحتاج تأكيد الحجم/التدفق والثبات"
    elif float(d.get("early_moon_ratio",0))>=65 and float(d.get("accumulation",0))>=58 and obv["trend_pct"]>2 and not d.get("overextended",False):
        stage="STEALTH_ACCUMULATION"; label="🟦 STEALTH ACCUMULATION"; status="WATCH_EARLY"; reason="تجميع مبكر مع تحسن OBV/Flow دون توسع سعري واضح"
    else:
        stage=d.get("stage","WATCH"); label=d.get("stage_ar","👀 WATCH"); status="WAIT"; reason="لا تزال شروط التأكيد غير مكتملة"
    return {"status":status,"stage":stage,"label":label,"reason":reason,"checks":checks,"missing":missing,"obv_trend_pct":obv["trend_pct"],"volume_trend_pct":vol["trend_pct"],"volume_current":vol["current"],"flow_direction":fh["direction"]}
'''
s=s[:start]+new+s[end:]
# Replace detailed_symbol
start=s.index('def detailed_symbol(symbol):')
end=s.index('\ndef get_exchange_info',start)
new=r'''def detailed_symbol(symbol):
    symbol=symbol.upper().strip(); d=get_data(); current=next((x for x in d.get('results',[]) if x.get('symbol')==symbol),None)
    if not current: raise RuntimeError('العملة غير موجودة في قائمة الرادار الحالية')
    m1=tf_metrics(symbol,'1m',180); m5=tf_metrics(symbol,'5m',180); m15=tf_metrics(symbol,'15m',180); h1=tf_metrics(symbol,'1h',120); h4=tf_metrics(symbol,'4h',120); day=tf_metrics(symbol,'1d',120)
    fnd=funding(symbol)
    risk=clamp(100-(m15['atr_pct']*8)-max(0,float(current.get('change24h',0))-8)*3-(0 if (current.get('liquidity',50)>=60) else 12))
    if fnd is not None and fnd>0.03:risk-=8
    # Detailed order-flow history from 1m candles: taker-buy delta is a transparent proxy for CVD trend.
    fh=m1['flow_history']; od=m5['obv_detail']; vd=m5['volume_detail']
    cvd=float(current.get('cvd',50)); flow=float(current.get('volume_pressure',50)); whale=float(current.get('whale_hunter',50))
    # Human-readable confirmation should explain what is missing rather than issuing a buy/sell instruction.
    tmp={'cvd':cvd,'flow':flow,'whale':whale,'liquidity':current.get('liquidity',50),'resistance_distance':m15.get('resistance_distance'),'resistance':m15.get('resistance'),'price':current.get('price'),'rsi':m15.get('rsi'),'early_moon_ratio':current.get('early_moon_ratio'),'accumulation':current.get('accumulation'),'stage':current.get('stage'),'stage_ar':current.get('stage_ar')}
    conf=confirmation_engine(tmp,m1,m5)
    return {'status':'ok','version':APP_VERSION,'symbol':symbol,'price':current.get('price'),'change24h':current.get('change24h'),'quoteVolume24h':current.get('quoteVolume24h'),'funding_pct':round(fnd,5) if fnd is not None else None,'funding_label':'تمويل سالب' if fnd is not None and fnd<0 else ('تمويل موجب' if fnd is not None else 'غير متاح'),'risk':round(clamp(risk),1),'accumulation':current.get('accumulation'),'early_moon_ratio':current.get('early_moon_ratio'),'stage':conf['label'],'stage_code':conf['stage'],'cvd':cvd,'flow':flow,'whale':whale,'liquidity':current.get('liquidity'),'volume_profile':current.get('volume_profile'),'support':m15.get('support'),'resistance':m15.get('resistance'),'support_distance':m15.get('support_distance'),'resistance_distance':m15.get('resistance_distance'),'rsi':m15.get('rsi'),'obv':m15.get('obv'),'obv_raw':od.get('raw'),'obv_trend_pct':od.get('trend_pct'),'obv_direction':od.get('direction'),'volume_ratio':m15.get('volume_ratio'),'volume_current_ratio':vd.get('current'),'volume_trend_pct':vd.get('trend_pct'),'volume_direction':vd.get('direction'),'volume_sequence':vd.get('sequence'),'taker_buy_ratio':fh.get('taker_buy_ratio'),'taker_buy_trend_pct':fh.get('taker_trend_pct'),'cvd_proxy_change_pct':fh.get('delta_change_pct'),'flow_direction':fh.get('direction'),'atr_pct':m15.get('atr_pct'),'confirmation':conf,'change_5m':multi_period_change(get_klines(symbol,'5m',80),1),'change_15m':multi_period_change(get_klines(symbol,'5m',80),3),'change_30m':multi_period_change(get_klines(symbol,'5m',80),6),'timeframes':{'1m':m1,'5m':m5,'15m':m15,'1h':h1,'4h':h4,'1d':day},'why':current.get('why',[])}
'''
s=s[:start]+new+s[end:]
p.write_text(s)
