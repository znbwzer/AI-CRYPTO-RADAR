/* ═══════════════════════════════════════════════════
   AI CRYPTO RADAR V4.0 — Premium Dashboard Logic
   ═══════════════════════════════════════════════════ */

const $=id=>document.getElementById(id);
let DATA=[], STRATS={}, ACTIVE='scalp';
let SONAR={symbols:[],global:{},timeline_global:[]};
let SONAR_PREV={};

/* ═══ utils ═══ */
async function j(u){const r=await fetch(u);if(!r.ok)throw Error('HTTP '+r.status);return r.json()}
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function n(v,d=1){return v==null?'—':Number(v).toFixed(d)}
function money(v){
  v=+v||0;
  if(v>=1e12)return '$'+(v/1e12).toFixed(2)+'T';
  if(v>=1e9)return '$'+(v/1e9).toFixed(2)+'B';
  if(v>=1e6)return '$'+(v/1e6).toFixed(2)+'M';
  if(v>=1e3)return '$'+(v/1e3).toFixed(1)+'K';
  return '$'+v.toLocaleString(undefined,{maximumFractionDigits:8});
}
function moneySigned(v){
  v=+v||0;const a=Math.abs(v);const s=v>=0?'+':'-';
  if(a>=1e9)return s+'$'+(a/1e9).toFixed(2)+'B';
  if(a>=1e6)return s+'$'+(a/1e6).toFixed(2)+'M';
  if(a>=1e3)return s+'$'+(a/1e3).toFixed(1)+'K';
  return s+'$'+a.toFixed(0);
}
function arrow(d){return d==='↑'?'<span class="up">↑</span>':d==='↓'?'<span class="down">↓</span>':'<span class="flat">→</span>'}
function stat(a,b,cls=''){return `<div class="stat ${cls}"><span>${a}</span><b>${b??'—'}</b></div>`}
function stageAr(c){return c.stage==='CONFIRMED_EXPANSION'?'🟢 توسع مؤكد':c.stage==='PRE_BREAKOUT'?'🟨 قبل الاختراق':c.stage==='STEALTH_ACCUMULATION'?'🟦 تجميع خفي':'👀 مراقبة'}

/* ═══ MOON & TIER ═══ */
function moonScore(c){
  const e=+c.early_moon_ratio||0;
  const f=+c.freshness||55;
  const a=+c.accumulation||0;
  const flow=((+c.cvd||0)+(+c.whale_hunter||0))/2;
  const mom=+c.momentum||50;
  const pen=Math.max(0,mom-60)*0.55;
  return Math.max(0,Math.min(100,e*0.52+a*0.15+flow*0.18+f*0.15-pen));
}
function tierOf(s){
  s=+s||0;
  if(s>=72)return{t:'S',label:'🌙🌙🌙 إلى القمر'};
  if(s>=62)return{t:'A',label:'🌙🌙 قريب جدًا'};
  if(s>=52)return{t:'B',label:'🌙 واعدة'};
  return{t:'C',label:'👀 مراقبة'};
}
function signalOf(c){
  const m=moonScore(c);
  if(m>=62 && (c.stage==='PRE_BREAKOUT'||c.stage==='CONFIRMED_EXPANSION'))return'buy';
  if(m>=52)return'watch';
  return'sell';
}
function sigLabel(sig){
  return sig==='buy'?'BUY':sig==='sell'?'SELL':'WATCH';
}

/* ═══ SIGNAL CARD (like AI Signals app) ═══ */
function signalCard(c,rank,i){
  const m=moonScore(c);
  const tier=tierOf(m);
  const sig=signalOf(c);
  const ch=+c.change24h||0;
  const isTop=i===0;
  const timeStr=new Date().toLocaleTimeString('ar-EG',{hour12:false}).slice(0,5);
  const res=+c.distance_to_resistance||0;
  const risk=+c.risk_safety||50;
  const liq=+c.liquidity||0;
  const conf=+c.ai_confidence||m;

  return `<article class="signal-card ${isTop?'top1':''}" data-symbol="${esc(c.symbol)}">
    <span class="sig-tier ${tier.t}">${tier.t}</span>
    <div class="sig-head">
      <span class="sig-badge ${sig}">${sigLabel(sig)}</span>
      <div class="sig-pair">
        <div style="text-align:right;min-width:0;flex:1">
          <div class="sig-symbol">${esc(c.symbol)}</div>
          <div class="sig-sub">${timeStr} • ${esc(c.stage_ar||stageAr(c))}</div>
        </div>
        <div class="sig-icon">${sig==='buy'?'🚀':sig==='sell'?'📉':'👀'}</div>
      </div>
    </div>
    <div class="sig-metrics">
      <div class="sig-metric">
        <div class="lbl">PRICE</div>
        <div class="val">${money(c.price)}</div>
      </div>
      <div class="sig-metric">
        <div class="lbl">24H</div>
        <div class="val ${ch>=0?'up':'down'}">${ch>=0?'+':''}${n(ch,2)}%</div>
      </div>
      <div class="sig-metric">
        <div class="lbl">ACC</div>
        <div class="val gold">${n(c.accumulation)}</div>
      </div>
      <div class="sig-metric">
        <div class="lbl">CVD</div>
        <div class="val ${+c.cvd>=55?'up':'down'}">${n(c.cvd)}</div>
      </div>
    </div>
    <div class="sig-foot">
      <div class="sig-reason">${esc((c.why||[]).slice(0,2).join(' • ')||'مراقبة مستمرة')}</div>
      <button class="sig-open">تفاصيل ›</button>
    </div>
  </article>`;
}

function renderTopSignals(){
  const box=$('topSignals');
  const sorted=DATA.slice().sort((a,b)=>moonScore(b)-moonScore(a)).slice(0,5);
  if(!sorted.length){
    box.innerHTML='<div class="empty">اضغط فحص جديد لتحميل الإشارات.</div>';
    return;
  }
  box.innerHTML=sorted.map((c,i)=>signalCard(c,'#'+(i+1),i)).join('');
  bindCards();
}

/* ═══ MINI CARD (grid-5 + phases) ═══ */
function card(c,rank='',score=null){
  const m=moonScore(c);
  const useScore=score==null?m:score;
  const ch=+c.change24h||0;
  return `<article class="coin" data-symbol="${esc(c.symbol)}">
    <div class="coin-top">
      <span class="rank">${rank||stageAr(c)}</span>
      <span class="symbol">${esc(c.symbol)}</span>
    </div>
    <div class="price">${money(c.price)} <small>${ch>=0?'+':''}${n(ch,2)}%</small></div>
    <div class="score"><span>قوة الإشارة</span><b>${n(useScore)}</b></div>
    <div class="bar"><i style="width:${Math.max(0,Math.min(100,useScore))}%"></i></div>
    <div class="stats">
      ${stat('التجميع',n(c.accumulation))}
      ${stat('CVD',n(c.cvd))}
      ${stat('السيولة',n(c.liquidity))}
      ${stat('الحيتان',n(c.whale_hunter))}
    </div>
    <span class="tag">${esc(c.stage_ar||stageAr(c))}</span>
    <p class="why">${esc((c.why||[]).slice(0,2).join(' • '))}</p>
    <button class="more">🔎 تفاصيل</button>
  </article>`;
}

/* ═══ CONNECTION BANNER ═══ */
function showBanner(msg,cls){
  const b=$('errBanner');
  $('errBannerText').textContent=msg;
  b.className='err-banner'+(cls?' '+cls:'');
  b.classList.remove('hidden');
}
function hideBanner(){
  $('errBanner').classList.add('hidden');
}

/* ═══ MARKET SUMMARY ═══ */
function renderMarketSummary(){
  const arr=DATA||[];
  if(!arr.length)return; // keeps the "—" placeholders until real data arrives

  const totalVol=arr.reduce((s,c)=>s+(+c.quoteVolume24h||0),0);
  const up=arr.filter(c=>(+c.change24h||0)>0).length;
  const down=arr.length-up;
  const upPct=Math.round(up/arr.length*100);
  const downPct=100-upPct;
  const avgChange=arr.reduce((s,c)=>s+(+c.change24h||0),0)/arr.length;

  // Net flow from sonar if available, else approximation
  const net=+(SONAR.global?.net_flow||0);
  const sentiment=SONAR.global?.sentiment||
    (avgChange>1?'BULLISH':avgChange<-1?'BEARISH':'NEUTRAL');

  // BTC dominance proxy
  const btc=arr.find(c=>c.symbol==='BTCUSDT');
  const btcVol=+(btc?.quoteVolume24h||0);
  const btcDom=totalVol>0?Math.round(btcVol/totalVol*100):0;

  // Fear & Greed proxy (0-100)
  const fg=Math.round(Math.max(0,Math.min(100,50+avgChange*8+upPct*0.4-30)));

  $('msVol').textContent=money(totalVol);
  $('msVolChange').innerHTML=`<span class="${avgChange>=0?'up':'down'}">${avgChange>=0?'+':''}${n(avgChange,2)}% متوسط</span>`;

  const netEl=$('msNet');
  netEl.textContent=moneySigned(net);
  netEl.style.color=net>0?'var(--up)':net<0?'var(--down)':'#fff';
  $('msNetSub').innerHTML=`<span class="${net>=0?'up':'down'}">${net>=0?'🟢 شراء':'🔴 بيع'}</span>`;

  const sentEl=$('msSent');
  const sentLabel=sentiment==='BULLISH'?'إيجابي 🐂':sentiment==='BEARISH'?'سلبي 🐻':'محايد ⚖️';
  sentEl.textContent=sentLabel;
  sentEl.style.color=sentiment==='BULLISH'?'var(--up)':sentiment==='BEARISH'?'var(--down)':'#fff';
  $('msSentBar').style.width=Math.min(100,upPct)+'%';

  $('msBtcDom').textContent=btcDom+'%';
  $('msBtcBar').style.width=btcDom+'%';

  $('msUp').textContent=upPct+'%';
  $('msDown').textContent=downPct+'%';
  $('msUpBar').style.width=upPct+'%';
  $('msDownBar').style.width=downPct+'%';

  $('msFg').textContent=fg;
  $('msFgLabel').textContent=fg>=75?'جشع شديد':fg>=55?'جشع':fg>=45?'محايد':fg>=25?'خوف':'خوف شديد';
}

/* ═══ SONAR ═══ */
function flash(el,key,val){
  if(!el)return;
  const prev=SONAR_PREV[key];
  if(prev!==undefined&&prev!==val){
    const cls=val>prev?'flash-up':'flash-down';
    el.classList.remove('flash-up','flash-down');
    void el.offsetWidth;
    el.classList.add(cls);
    setTimeout(()=>el.classList.remove(cls),850);
  }
  SONAR_PREV[key]=val;
}

function renderSonarStrip(g,tl){
  const net=g.net_flow||0;
  const netEl=$('ssNet');
  netEl.textContent=moneySigned(net);
  netEl.className=net>0?'up':net<0?'down':'';
  flash(netEl,'net',net);

  $('ssBuy').textContent=money(g.total_buy||0);
  $('ssSell').textContent=money(g.total_sell||0);

  const moodEl=$('ssMood');
  const s=g.sentiment||'NEUTRAL';
  moodEl.textContent=s==='BULLISH'?'🐂':s==='BEARISH'?'🐻':'⚖️';
  moodEl.className=s==='BULLISH'?'up':s==='BEARISH'?'down':'';

  const box=$('tlStrip');
  if(!tl||!tl.length){
    box.innerHTML='<div class="empty" style="padding:6px;font-size:10px;border:0;background:transparent;width:100%">لا توجد بيانات كافية بعد</div>';
    return;
  }
  const mx=Math.max(1,...tl.map(b=>b.total||0));
  box.innerHTML=tl.map(b=>{
    const h=Math.max(2,(b.total/mx)*100);
    const cls=b.net>0.001?'buy':b.net<-0.001?'sell':'';
    const t=new Date(b.t).toLocaleTimeString('ar-EG',{hour12:false}).slice(-5);
    return `<div class="tl-bar ${cls}" style="height:${h}%" title="${t}"></div>`;
  }).join('');
}

function renderRadarLive(coin){
  const box=$('radarViz');
  if(!coin){
    box.innerHTML='<div style="padding:20px;text-align:center;color:var(--text-muted);font-size:11px">بانتظار البيانات...</div>';
    $('radarSymbol').textContent='—';
    $('radarLegend').innerHTML='';
    return;
  }
  const rings=[
    {r:98,val:coin.liquidity_score||0,col:'#4a9eff',label:'السيولة'},
    {r:80,val:coin.cvd_score||0,col:'#00e08a',label:'CVD Live'},
    {r:62,val:coin.whale_score||0,col:'#9d7bff',label:'الحيتان'},
    {r:44,val:coin.depth_score||0,col:'#ffc857',label:'Order Book'},
  ];
  const C=r=>2*Math.PI*r;
  const svgW=220, svgH=220, cx=110, cy=110;
  const scale=0.9;
  const ringsSvg=rings.map(x=>{
    const rr=x.r*scale;
    const cc=C(rr);
    const p=Math.max(0,Math.min(100,x.val))/100;
    const off=cc-(p*cc);
    return `<circle cx="${cx}" cy="${cy}" r="${rr}"
      fill="none" stroke="${x.col}" stroke-width="6"
      stroke-linecap="round"
      stroke-dasharray="${cc.toFixed(2)}" stroke-dashoffset="${off.toFixed(2)}"
      transform="rotate(-90 ${cx} ${cy})"
      opacity="0.9"/>`;
  }).join('');
  const sc=Math.round(coin.sonar_score||0);
  const color=sc>=65?'#00e08a':sc>=50?'#ffc857':'#ff4966';
  box.innerHTML=`<svg viewBox="0 0 ${svgW} ${svgH}">
    ${ringsSvg}
    <text x="${cx}" y="${cy-2}" text-anchor="middle" font-size="10" fill="#8fa3bf">Sonar</text>
    <text x="${cx}" y="${cy+22}" text-anchor="middle" font-size="30" font-weight="900" fill="${color}">${sc}</text>
  </svg>`;
  $('radarSymbol').textContent=coin.symbol;
  $('radarLegend').innerHTML=rings.map(x=>`
    <div class="row-l">
      <span class="swatch" style="background:${x.col}"></span>
      <span>${x.label}</span>
      <b>${Math.round(x.val)}</b>
    </div>`).join('');
}

function renderWhaleFlowLive(symbols){
  const box=$('whaleFlow');
  const arr=(symbols||[]).slice(0,8);
  if(!arr.length){
    box.innerHTML='<div class="empty" style="border:0;background:transparent">بانتظار البيانات...</div>';
    return;
  }
  box.innerHTML=arr.map(c=>{
    const b=+c.buy_notional||0, s=+c.sell_notional||0, tot=b+s;
    const buyPct=tot>0?Math.round(b/tot*100):50;
    const net=+(c.net_flow||0);
    const cls=net>0.001?'pos':net<-0.001?'neg':'zero';
    return `<div class="wf-row" data-symbol="${esc(c.symbol)}">
      <span class="sym">${esc(c.symbol.replace('USDT',''))}</span>
      <div class="wf-bar">
        <i class="buy" style="right:${100-buyPct}%"></i>
        <i class="sell" style="left:${buyPct}%"></i>
        <i class="mid"></i>
      </div>
      <span class="net ${cls}">${moneySigned(net)}</span>
    </div>`;
  }).join('');
}

function renderSmartMapLive(symbols){
  const box=$('smartMap');
  const arr=(symbols||[]).slice().sort((a,b)=>(b.sonar_score||0)-(a.sonar_score||0)).slice(0,20);
  if(!arr.length){
    box.innerHTML='<div class="empty" style="border:0;background:transparent;grid-column:1/-1">بانتظار البيانات...</div>';
    return;
  }
  box.innerHTML=arr.map(c=>{
    const wh=+c.whale_score||50, sc=+c.sonar_score||0;
    const hue=wh>=70?42:wh>=55?200:wh>=40?220:0;
    const sat=wh>=70?85:wh>=55?70:wh>=40?55:45;
    const light=wh>=70?50:wh>=55?36:wh>=40?24:18;
    const alpha=(0.28+wh/220).toFixed(2);
    const bg=`hsl(${hue} ${sat}% ${light}% / ${alpha})`;
    const cls=wh>=70?'hot':wh<40?'neg':'';
    const sigIcon=c.signal==='ACCUMULATION'?'▲':c.signal==='DISTRIBUTION'?'▼':'·';
    return `<div class="sm-cell ${cls}" data-symbol="${esc(c.symbol)}" style="background:${bg}" title="${esc(c.symbol)} • ${c.signal}">
      <span class="sm-sym">${esc(c.symbol.replace('USDT',''))} ${sigIcon}</span>
      <span class="sm-val">${Math.round(sc)}</span>
    </div>`;
  }).join('');
}

function renderLiqLadderLive(symbols){
  const box=$('liqLadder');
  const arr=(symbols||[]).slice(0,14);
  if(!arr.length){
    box.innerHTML='<div class="empty" style="border:0;background:transparent">بانتظار البيانات...</div>';
    return;
  }
  box.innerHTML=arr.map(c=>{
    const liq=+c.liquidity_score||0;
    const cvd=+c.cvd_score||50;
    const wh=+c.whale_score||50;
    const cvdCls=cvd>=58?'hot':cvd<=42?'cold':'';
    const whCls=wh>=58?'hot':wh<=42?'cold':'';
    return `<div class="ll-row" data-symbol="${esc(c.symbol)}">
      <span class="sym">${esc(c.symbol.replace('USDT',''))}</span>
      <div class="bar-wrap"><i style="width:${Math.max(2,liq)}%"></i></div>
      <span class="cvd ${cvdCls}">${Math.round(cvd)}</span>
      <span class="whale ${whCls}">${Math.round(wh)}</span>
    </div>`;
  }).join('');
}

function renderSonarLive(d){
  if(!d||d.status!=='ok')return;
  SONAR=d;
  const syms=d.symbols||[];
  const top=syms[0];
  renderSonarStrip(d.global||{},d.timeline_global||[]);
  renderRadarLive(top);
  renderWhaleFlowLive(syms);
  renderSmartMapLive(syms);
  renderLiqLadderLive(syms);
  bindCards();
}

let SONAR_FAILS=0;
async function pollSonar(){
  try{
    const r=await fetch('/api/sonar?top_n=15',{cache:'no-store'});
    if(!r.ok){SONAR_FAILS++;return;}
    const d=await r.json();
    if(d.status!=='ok'){
      SONAR_FAILS++;
      // Only bother the user with a sonar-specific message if the main
      // scan is otherwise fine (so we don't stack two banners for one issue).
      if(SONAR_FAILS>=3 && DATA.length>0 && $('errBanner').classList.contains('hidden')){
        showBanner('⚠️ سونار الحيتان لا يستقبل بيانات حاليًا، جاري إعادة المحاولة…','warn');
      }
      return;
    }
    SONAR_FAILS=0;
    renderSonarLive(d);
    renderMarketSummary();
  }catch(e){SONAR_FAILS++;/* keep polling silently */}
}

/* ═══ MODES ═══ */
const desc={
  scalp:'⚡ سكالب: 5m + 15m. نركز على CVD، حجم اللحظة، OBV، السيولة، RSI وموقع السعر من المقاومة.',
  day:'☀️ يومي: 15m + 1h. نركز على التجميع، اتجاه الساعة، التدفق، الحجم والاستعداد للاختراق.',
  swing:'🌊 سوينغ: 1h + 4h. نركز على الاتجاه الأعلى، OBV، التجميع، موقع السعر والسيولة.',
  invest:'🏦 استثمار: 4h + 1d. نركز على الاتجاه الأطول، OBV، التجميع، السيولة وتقليل مطاردة الحركة.'
};
function renderMode(){
  const a=STRATS[ACTIVE]||[];
  $('modeDesc').textContent=desc[ACTIVE];
  $('modeOut').innerHTML=a.length
    ?a.map((c,i)=>card(c,'#'+(i+1),c.strategy_score)).join('')
    :'<div class="empty">اضغط فحص جديد.</div>';
  bindCards();
}

/* ═══ PHASES ═══ */
function lanes(){
  [['stealth','STEALTH_ACCUMULATION'],['prebreak','PRE_BREAKOUT'],['confirmed','CONFIRMED_EXPANSION']]
  .forEach(([id,s])=>{
    const arr=DATA.filter(c=>c.stage===s).slice(0,5);
    $(id).innerHTML=arr.length
      ?arr.map((c,i)=>card(c,'#'+(i+1))).join('')
      :'<div class="empty" style="padding:14px;font-size:11px">لا توجد مطابقة.</div>';
  });
  bindCards();
}

/* ═══ SCAN ═══ */
let SCAN_FAILS=0;
async function scan(){
  const b=$('scan');
  b.disabled=true;
  if(!DATA.length){
    $('topSignals').innerHTML='<div class="empty loading">⏳ جاري تحميل الإشارات لأول مرة… قد يستغرق هذا حتى دقيقة.</div>';
  }
  try{
    const [d,st]=await Promise.all([j('/api/radar'),j('/api/strategies')]);

    // The backend now always answers with HTTP 200 and a status field,
    // even when the underlying Binance scan failed, so we check it here
    // instead of relying on a thrown fetch error.
    if(d.status==='error'){
      SCAN_FAILS++;
      DATA=d.results||DATA||[];
      showBanner(
        DATA.length
          ? '⚠️ تعذر تحديث بيانات السوق (مشكلة اتصال بمصدر البيانات) — تُعرض آخر بيانات معروفة وسيُعاد المحاولة تلقائيًا.'
          : '⚠️ تعذر الاتصال بمصدر البيانات (Binance). جاري إعادة المحاولة تلقائيًا كل بضع ثوانٍ…'
      );
    }else{
      SCAN_FAILS=0;
      DATA=d.results||[];
      hideBanner();
    }

    STRATS=st.strategies||{};
    $('bin').innerHTML=`<i class="dot ${d.status==='error'?'err':''}"></i> Binance • ${d.scanned_universe||0} زوج`;
    $('stats').textContent=`${d.scan_seconds||0}ث • ${d.deep_analyzed||0} تحليل`;
    renderTopSignals();
    renderMarketSummary();
    lanes();
    renderMode();

    // If the scan failed and we still have nothing to show, retry sooner
    // than the normal 3-minute cycle instead of leaving the UI stuck.
    if(d.status==='error' && !DATA.length){
      setTimeout(scan, Math.min(30000, 5000*(SCAN_FAILS+1)));
    }
  }catch(e){
    // Network/server totally unreachable (not even a JSON error response).
    SCAN_FAILS++;
    showBanner('⚠️ تعذر الوصول إلى الخادم: '+esc(e.message)+' — إعادة المحاولة…');
    if(!DATA.length){
      $('topSignals').innerHTML='<div class="empty red">تعذر التحميل: '+esc(e.message)+'</div>';
    }
    setTimeout(scan, Math.min(30000, 5000*(SCAN_FAILS+1)));
  }finally{
    b.disabled=false;
    bindCards();
  }
}

/* ═══ WS STATUS ═══ */
async function ws(){
  try{
    const d=await j('/api/orderflow/status');
    const connected=d.connected;
    $('ws').innerHTML=`<i class="dot ${connected?'':'off'}"></i> WS ${connected?'🟢':'🟡'} • ${d.symbols||0}`;
  }catch{
    $('ws').innerHTML='<i class="dot err"></i> WS 🔴';
  }
}

/* ═══ AF QUALITY ═══ */
function afCard(c,i){
  const m=moonScore(c);
  return `<article class="coin" data-symbol="${esc(c.symbol)}">
    <div class="coin-top">
      <span class="rank">#${i+1} ${esc(c.acc_flow_state_ar||c.acc_flow_state||'')}</span>
      <span class="symbol">${esc(c.symbol)}</span>
    </div>
    <div class="price">${money(c.price)}</div>
    <div class="score"><span>ACC+Flow</span><b>${n(c.acc_flow_score)}</b></div>
    <div class="bar"><i style="width:${Math.min(100,+c.acc_flow_score||0)}%"></i></div>
    <div class="stats">
      ${stat('التجميع',n(c.accumulation))}
      ${stat('التدفق',n(c.flow_score))}
      ${stat('CVD',n(c.cvd))}
      ${stat('الحيتان',n(c.whale_hunter))}
    </div>
    <span class="tag">${esc(c.utility||'غير متحقق')}</span>
    <p class="why">${esc(c.core_reason||'')}</p>
    <button class="more">🔎 تفاصيل</button>
  </article>`;
}
async function af(){
  const b=$('af');b.disabled=true;b.textContent='...';
  try{
    const d=await j('/api/accflow?core_only=true');
    if(d.status!=='ok')throw Error(d.error||'خطأ');
    $('afsummary').innerHTML=`<span>مؤهل: ${d.matched}</span><span>عميق: ${d.deep_checked}</span><span>MCap ≥ $5B</span>`;
    const list=(d.top10||[]).slice(0,5).sort((a,b)=>moonScore(b)-moonScore(a));
    $('afout').innerHTML=list.length?list.map(afCard).join(''):'<div class="empty">لا توجد مطابقة.</div>';
    bindCards();
  }catch(e){
    $('afout').innerHTML='<div class="empty red">فشل: '+esc(e.message)+'</div>';
  }finally{
    b.disabled=false;b.textContent='فحص';
  }
}

/* ═══ BACKTEST ═══ */
async function bt(){
  const b=$('bt');b.disabled=true;b.textContent='...';
  try{
    const d=await j('/api/backtest/top?top_n=50&days=30');
    const rows=(d.pattern_leaderboard||[]).slice(0,5).map(x=>
      `<div class="row">
        <b>${esc(x.pattern)}</b>
        <span>${x.signals} إشارة</span>
        <span>${x.win_rate}% نجاح</span>
        <span>${x.avg_return_pct}%</span>
      </div>`).join('');
    $('btout').innerHTML=`<p style="font-size:11px;color:var(--text-dim);margin-bottom:6px">اختُبرت ${d.tested}/${d.top_n} عملة</p>${rows}`;
  }catch(e){
    $('btout').innerHTML='<p class="red">فشل: '+esc(e.message)+'</p>';
  }finally{
    b.disabled=false;b.textContent='اختبر أفضل 50';
  }
}

/* ═══ DETAIL MODAL ═══ */
async function detail(symbol){
  $('modal').classList.remove('hidden');
  $('detail').innerHTML='<div class="loading">⏳ جاري جلب التحليل...</div>';
  document.body.style.overflow='hidden';
  try{
    const d=await j('/api/details/'+encodeURIComponent(symbol));
    if(d.status!=='ok')throw Error(d.error||'خطأ');
    const f=d.funding_pct;
    const fund=f==null?'غير متاح':(f<0?'🟢 '+n(f,4)+'%':'🔴 '+n(f,4)+'%');
    const m5=d.timeframes['5m'],m15=d.timeframes['15m'],h1=d.timeframes['1h'],h4=d.timeframes['4h'],day=d.timeframes['1d'];
    const m=moonScore({early_moon_ratio:d.early_moon_ratio,accumulation:d.accumulation,cvd:d.cvd,whale_hunter:d.whale,momentum:d.momentum,freshness:60});
    const tier=tierOf(m);

    $('detail').innerHTML=`
      <div class="detail-head">
        <div>
          <div style="font-size:10px;color:var(--text-muted);font-weight:800;letter-spacing:1px;margin-bottom:4px">V4.0 • تحليل تفصيلي</div>
          <h2>${esc(d.symbol)}</h2>
          <div class="detail-price">${money(d.price)} <small>${n(d.change24h,2)}% / 24س</small></div>
        </div>
        <div style="text-align:center">
          <span class="sig-tier ${tier.t}" style="position:static">${tier.t}</span>
        </div>
      </div>

      <div class="decision">
        <div><b>🌙 Moon Score</b><strong>${n(m)}</strong></div>
        <div><b>Early Moon</b><strong>${n(d.early_moon_ratio)}</strong></div>
        <div><b>Risk Index</b><strong>${n(d.risk)}</strong></div>
      </div>

      <div class="detail-grid">
        ${stat('التمويل',fund)}
        ${stat('التجميع',n(d.accumulation))}
        ${stat('CVD',n(d.cvd))}
        ${stat('Flow',n(d.flow))}
        ${stat('Whale',n(d.whale))}
        ${stat('السيولة',n(d.liquidity))}
        ${stat('RSI 15m',n(d.rsi))}
        ${stat('OBV',n(d.obv))}
        ${stat('OBV Trend',n(d.obv_trend_pct,1)+'% '+arrow(d.obv_direction))}
        ${stat('الحجم',n(d.volume_current_ratio,2)+'x')}
        ${stat('Vol Trend',n(d.volume_trend_pct,1)+'% '+arrow(d.volume_direction))}
        ${stat('ATR 15m',n(d.atr_pct,3)+'%')}
        ${stat('الدعم',money(d.support))}
        ${stat('المقاومة',money(d.resistance))}
        ${stat('بعد الدعم',n(d.support_distance,2)+'%')}
        ${stat('بعد المقاومة',n(d.resistance_distance,2)+'%')}
        ${stat('حجم 24س',money(d.quoteVolume24h))}
      </div>

      <div class="confirm ${d.confirmation?.status==='CONFIRMED'?'ok':''}">
        <div class="confirm-title">⚠️ Confirmation: <b>${esc(d.confirmation?.status||'WAIT')}</b></div>
        <div>${esc(d.confirmation?.reason||'لا توجد قراءة حاسمة')}</div>
        ${(d.confirmation?.missing||[]).length?`<div class="missing"><b>ما ينقص:</b> ${esc((d.confirmation.missing||[]).slice(0,5).join(' • '))}</div>`:''}
      </div>

      <div class="change">
        <h3 style="margin:0 0 10px;font-size:13px;color:#fff">🔥 ماذا تغير؟</h3>
        <div class="change-grid">
          <div><b>5 د</b><span>${n(d.change_5m,2)}%</span></div>
          <div><b>15 د</b><span>${n(d.change_15m,2)}%</span></div>
          <div><b>30 د</b><span>${n(d.change_30m,2)}%</span></div>
        </div>
        <div class="timeline">
          <div><b>📊 OBV</b><span>${n(d.obv_trend_pct,1)}% ${arrow(d.obv_direction)}</span></div>
          <div><b>📈 Vol</b><span>${n(d.volume_trend_pct,1)}% ${arrow(d.volume_direction)}</span></div>
          <div><b>🔥 CVD</b><span>${n(d.cvd_proxy_change_pct,1)}% ${arrow(d.flow_direction)}</span></div>
          <div><b>💰 Taker</b><span>${n((d.taker_buy_ratio||0)*100,1)}%</span></div>
        </div>
      </div>

      <h3 style="margin:16px 0 8px;font-size:13px;color:#fff">📊 الأطر الزمنية</h3>
      <div class="tf">
        <div><b>1د</b> · RSI ${n(d.timeframes['1m'].rsi)} · OBV ${n(d.timeframes['1m'].obv)} · Vol ${n(d.timeframes['1m'].volume_ratio,2)}x</div>
        <div><b>5د</b> · RSI ${n(m5.rsi)} · OBV ${n(m5.obv)} · Vol ${n(m5.volume_ratio,2)}x</div>
        <div><b>15د</b> · RSI ${n(m15.rsi)} · OBV ${n(m15.obv)} · Vol ${n(m15.volume_ratio,2)}x</div>
        <div><b>1س</b> · RSI ${n(h1.rsi)} · OBV ${n(h1.obv)} · Vol ${n(h1.volume_ratio,2)}x</div>
        <div><b>4س</b> · RSI ${n(h4.rsi)} · OBV ${n(h4.obv)} · Vol ${n(h4.volume_ratio,2)}x</div>
        <div><b>يومي</b> · RSI ${n(day.rsi)} · OBV ${n(day.obv)} · Vol ${n(day.volume_ratio,2)}x</div>
      </div>

      <p class="note">OBV = حجم تراكمي. CVD Proxy من Taker Buy/Sell على شموع 1m. النتائج احتمالية وليست توصية.</p>
    `;
  }catch(e){
    $('detail').innerHTML='<div class="empty red">تعذر: '+esc(e.message)+'</div>';
  }
}

/* ═══ BIND ═══ */
function bindCards(){
  document.querySelectorAll('[data-symbol]').forEach(x=>{
    x.onclick=()=>detail(x.dataset.symbol);
  });
}

$('scan').onclick=scan;
$('af').onclick=af;
$('bt').onclick=bt;
$('close').onclick=()=>{
  $('modal').classList.add('hidden');
  document.body.style.overflow='';
};
$('modal').onclick=e=>{
  if(e.target.id==='modal'){
    $('modal').classList.add('hidden');
    document.body.style.overflow='';
  }
};

document.querySelectorAll('.mode').forEach(x=>x.onclick=()=>{
  document.querySelectorAll('.mode').forEach(y=>y.classList.remove('active'));
  x.classList.add('active');
  ACTIVE=x.dataset.mode;
  renderMode();
});

// Bottom nav scroll
document.querySelectorAll('.bn-btn[data-scroll]').forEach(b=>{
  b.onclick=()=>{
    document.querySelectorAll('.bn-btn').forEach(y=>y.classList.remove('active'));
    b.classList.add('active');
    const target=b.dataset.scroll;
    if(target==='bottom')window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'});
    else{
      const el=$(target);
      if(el)el.scrollIntoView({behavior:'smooth',block:'start'});
    }
  };
});

/* ═══ BOOT ═══ */
scan();
ws();
pollSonar();
setInterval(ws,8000);
setInterval(pollSonar,3000);
setInterval(scan,180000);
