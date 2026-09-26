const $=id=>document.getElementById(id);
let DATA=[],STRATS={},ACTIVE='scalp';

/* ---------- utils ---------- */
async function j(u){const r=await fetch(u);if(!r.ok)throw Error('HTTP '+r.status);return r.json()}
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function n(v,d=1){return v==null?'—':Number(v).toFixed(d)}
function money(v){v=+v||0;if(v>=1e12)return '$'+(v/1e12).toFixed(2)+'T';if(v>=1e9)return '$'+(v/1e9).toFixed(2)+'B';if(v>=1e6)return '$'+(v/1e6).toFixed(2)+'M';return '$'+v.toLocaleString(undefined,{maximumFractionDigits:8})}
function arrow(d){return d==='↑'?'<span class="up">↑</span>':d==='↓'?'<span class="down">↓</span>':'<span class="flat">→</span>'}
function trend(v,dir='→',d=1,suf=''){return `${n(v,d)}% ${arrow(dir)}${suf}`}
function seq(a){return (a||[]).map(x=>`<span>${n(x,2)}x</span>`).join(' → ')||'—'}
function stat(a,b,cls=''){return `<div class="stat ${cls}"><span>${a}</span><b>${b??'—'}</b></div>`}

function stage(c){
  return c.stage==='CONFIRMED_EXPANSION'?'🟢 توسع مؤكد'
    :c.stage==='PRE_BREAKOUT'?'🟨 قبل الاختراق'
    :c.stage==='STEALTH_ACCUMULATION'?'🟦 تجميع خفي'
    :'👀 مراقبة';
}

/* ---------- MOON SCORE / TIER ---------- */
function moonScore(c){
  const e=+c.early_moon_ratio||0;
  const f=+c.freshness||55;
  const a=+c.accumulation||0;
  const flow=((+c.cvd||0)+(+c.whale_hunter||0))/2;
  const mom=+c.momentum||50;
  const pen=Math.max(0,mom-60)*0.55; // عقوبة التمدد
  return Math.max(0,Math.min(100, e*0.52 + a*0.15 + flow*0.18 + f*0.15 - pen));
}
function tierOf(s){
  s=+s||0;
  if(s>=72) return {t:'S',label:'🌙🌙🌙 إلى القمر',cls:'tier-s'};
  if(s>=62) return {t:'A',label:'🌙🌙 قريب جدًا',cls:'tier-a'};
  if(s>=52) return {t:'B',label:'🌙 فرصة واعدة',cls:'tier-b'};
  return {t:'C',label:'👀 مراقبة',cls:'tier-c'};
}
function gauge(s){
  s=Math.max(0,Math.min(100,+s||0));
  const r=26,C=2*Math.PI*r,off=C-(s/100)*C;
  return `<svg class="gauge" viewBox="0 0 64 64" aria-hidden="true">
    <circle class="gauge-bg" cx="32" cy="32" r="${r}"/>
    <circle class="gauge-fg" cx="32" cy="32" r="${r}" stroke-dasharray="${C.toFixed(2)}" stroke-dashoffset="${off.toFixed(2)}" transform="rotate(-90 32 32)"/>
    <text class="gauge-num" x="32" y="37" text-anchor="middle">${Math.round(s)}</text>
  </svg>`;
}
function spark(closes){
  if(!Array.isArray(closes)||closes.length<6) return '';
  const pts=closes.slice(-30).map(Number).filter(x=>isFinite(x));
  if(pts.length<6) return '';
  const W=200,H=34,min=Math.min(...pts),max=Math.max(...pts),rng=(max-min)||1;
  const step=W/(pts.length-1);
  const d=pts.map((v,i)=>`${i?'L':'M'}${(i*step).toFixed(1)},${(H-((v-min)/rng)*(H-4)-2).toFixed(1)}`).join(' ');
  const up=pts[pts.length-1]>=pts[0];
  const col=up?'#00d68f':'#ff4d6a';
  const id='g'+Math.random().toString(36).slice(2,8);
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${col}" stop-opacity=".35"/>
      <stop offset="100%" stop-color="${col}" stop-opacity="0"/>
    </linearGradient></defs>
    <path d="${d} L${W},${H} L0,${H} Z" fill="url(#${id})"/>
    <path d="${d}" fill="none" stroke="${col}" stroke-width="1.6" stroke-linejoin="round"/>
  </svg>`;
}

/* ---------- CONFIRMATION BLOCK ---------- */
function confBox(c){
  const co=c.confirmation||{};
  const miss=(co.missing||[]).slice(0,5);
  return `<div class="confirm ${co.status==='CONFIRMED'?'ok':''}">
    <div class="confirm-title">⚠️ Confirmation: <b>${esc(co.status||'WAIT')}</b></div>
    <div>${esc(co.reason||'لا توجد قراءة حاسمة بعد')}</div>
    ${miss.length?`<div class="missing"><b>ما ينقص:</b> ${esc(miss.join(' • '))}</div>`:''}
  </div>`;
}

/* ---------- CARD (premium) ---------- */
function card(c,rank='',score=null,highlight=false){
  const m=moonScore(c);
  const useScore=score==null?m:score;
  const tier=tierOf(m);
  const ch=+c.change24h||0;
  return `<article class="coin ${highlight?'main':''}" data-symbol="${esc(c.symbol)}">
    <div class="coin-top">
      <span class="rank">${rank||stage(c)}</span>
      <span class="symbol">${esc(c.symbol)}</span>
    </div>
    <div class="moon-row">
      ${gauge(m)}
      <div class="moon-meta">
        <div class="tier-label"><span class="tier-badge ${tier.cls}">${tier.t}</span>${tier.label}</div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:4px">Moon Score • ${Math.round(m)}/100</div>
      </div>
    </div>
    ${spark(c.closes)}
    <div class="price">${money(c.price)} <small>${ch>=0?'+':''}${n(ch,2)}%</small></div>
    <div class="score"><span>قوة الإشارة</span><b>${n(useScore)}</b></div>
    <div class="bar"><i style="width:${Math.max(0,Math.min(100,useScore))}%"></i></div>
    <div class="stats">
      ${stat('التجميع',n(c.accumulation))}
      ${stat('CVD/Flow',n(c.cvd))}
      ${stat('السيولة',n(c.liquidity))}
      ${stat('الحيتان',n(c.whale_hunter))}
    </div>
    <span class="tag">${esc(c.stage_ar||stage(c))}</span>
    <p class="why">${esc((c.why||[]).slice(0,3).join(' • '))}</p>
    <button class="more">🔎 تفاصيل العملة</button>
  </article>`;
}

/* ---------- MODES ---------- */
const desc={
  scalp:'⚡ سكالب: 5m + 15m. نركز على CVD، حجم اللحظة، OBV، السيولة، RSI وموقع السعر من المقاومة.',
  day:'☀️ يومي: 15m + 1h. نركز على التجميع، اتجاه الساعة، التدفق، الحجم والاستعداد للاختراق.',
  swing:'🌊 سوينغ: 1h + 4h. نركز على الاتجاه الأعلى، OBV، التجميع، موقع السعر والسيولة مع عقوبة التمدد.',
  invest:'🏦 شهر–شهرين: 4h + 1d. نركز على الاتجاه الأطول، OBV، التجميع، السيولة وتقليل مطاردة الحركة.'
};
function renderMode(){
  const a=STRATS[ACTIVE]||[];
  $('modeDesc').textContent=desc[ACTIVE];
  $('modeOut').innerHTML=a.length
    ?a.map((c,i)=>card(c,'#'+(i+1),c.strategy_score)).join('')
    :'<div class="empty">اضغط فحص جديد لتحميل الاستراتيجيات.</div>';
  bindCards();
}

/* ---------- LANES ---------- */
function lanes(){
  [['stealth','STEALTH_ACCUMULATION'],['prebreak','PRE_BREAKOUT'],['confirmed','CONFIRMED_EXPANSION']]
  .forEach(([id,s])=>{
    const arr=DATA.filter(c=>c.stage===s).slice(0,5);
    $(id).innerHTML=arr.length
      ?arr.map((c,i)=>card(c,'#'+(i+1))).join('')
      :'<div class="empty">لا توجد مطابقة حاليًا.</div>';
  });
  bindCards();
}

/* ---------- SCAN ---------- */
async function scan(){
  const b=$('scan');
  b.disabled=true;
  $('scan .scan-text').textContent='جاري الفحص';
  try{
    const [d,st]=await Promise.all([j('/api/radar'),j('/api/strategies')]);
    DATA=d.results||[];
    STRATS=st.strategies||{};
    $('bin').innerHTML=`<i class="dot"></i> Binance 🟢 • ${d.scanned_universe||0} زوج`;
    $('stats').textContent=`آخر تحديث • ${d.scan_seconds||0}ث • ${d.deep_analyzed||0} تحليل عميق`;

    // Top 5 sorted explicitly by Moon Score (fallback to early_moon_ratio)
    const top=(d.top5||DATA.slice(0,5)).slice(0,5).slice().sort((a,b)=>moonScore(b)-moonScore(a));
    $('top5').innerHTML=top.length
      ?top.map((c,i)=>card(c,'#'+(i+1),null,i===0)).join('')
      :'<div class="empty">لا توجد إشارات قوية حاليًا.</div>';

    lanes();
    renderMode();
  }catch(e){
    $('top5').innerHTML='<div class="empty red">تعذر تحميل الرادار: '+esc(e.message)+'</div>';
  }finally{
    b.disabled=false;
    $('scan .scan-text').textContent='فحص جديد';
    bindCards();
  }
}

/* ---------- WS STATUS ---------- */
async function ws(){
  try{
    const d=await j('/api/orderflow/status');
    $('ws').innerHTML=`<i class="dot" style="${d.connected?'':'background:#f59e0b'}"></i> البيانات الحية ${d.connected?'🟢 متصلة':'🟡 انتظار'} • ${d.symbols||0} رموز`;
  }catch{$('ws').innerHTML='<i class="dot" style="background:#ff4d6a"></i> البيانات الحية 🔴'}
}

/* ---------- ACC/FLOW ---------- */
function afCard(c,i){
  const m=moonScore(c);const tier=tierOf(m);
  return `<article class="coin" data-symbol="${esc(c.symbol)}">
    <div class="coin-top">
      <span class="rank">#${i+1} • ${esc(c.acc_flow_state_ar||c.acc_flow_state||'مراقبة')}</span>
      <span class="symbol">${esc(c.symbol)}</span>
    </div>
    <div class="moon-row">
      ${gauge(m)}
      <div class="moon-meta">
        <div class="tier-label"><span class="tier-badge ${tier.cls}">${tier.t}</span>${tier.label}</div>
      </div>
    </div>
    ${spark(c.closes)}
    <div class="price">${money(c.price)}</div>
    <div class="score"><span>التجميع + التدفق</span><b>${n(c.acc_flow_score)}</b></div>
    <div class="bar"><i style="width:${Math.min(100,+c.acc_flow_score||0)}%"></i></div>
    <div class="stats">
      ${stat('التجميع',n(c.accumulation))}
      ${stat('التدفق',n(c.flow_score))}
      ${stat('CVD',n(c.cvd))}
      ${stat('الحيتان',n(c.whale_hunter))}
      ${stat('حجم/قيمة',n(c.volume_mcap_ratio,2)+'%')}
      ${stat('القيمة السوقية',money(c.market_cap_usd))}
    </div>
    <span class="tag">${esc(c.utility||'المنفعة غير متحقق منها')}</span>
    <p class="why">${esc(c.core_reason||'')}</p>
    <button class="more">🔎 تفاصيل العملة</button>
  </article>`;
}
async function af(){
  const b=$('af');b.disabled=true;b.textContent='جاري الفحص';
  try{
    const d=await j('/api/accflow?core_only=true');
    if(d.status!=='ok')throw Error(d.error||'خطأ');
    $('afsummary').innerHTML=`<span>المؤهل: ${d.matched}</span><span>التعميق: ${d.deep_checked}</span><span>القيمة السوقية ≥ $5B</span><span>حجم/قيمة ≥ ${d.core_filter.min_volume_mcap_pct}%</span>`;
    const list=(d.top10||[]).slice(0,5).slice().sort((a,b)=>moonScore(b)-moonScore(a));
    $('afout').innerHTML=list.length
      ?list.map(afCard).join('')
      :'<div class="empty">لا توجد مطابقة حاليًا.</div>';
    bindCards();
  }catch(e){
    $('afout').innerHTML='<div class="empty red">فشل الفحص: '+esc(e.message)+'</div>';
  }finally{b.disabled=false;b.textContent='فحص الجودة'}
}

/* ---------- BACKTEST ---------- */
async function bt(){
  const b=$('bt');b.disabled=true;b.textContent='جاري الاختبار';
  try{
    const d=await j('/api/backtest/top?top_n=50&days=30');
    const rows=(d.pattern_leaderboard||[]).slice(0,5).map(x=>`
      <div class="row">
        <b>${esc(x.pattern)}</b>
        <span>${x.signals} إشارة</span>
        <span>${x.win_rate}% نجاح</span>
        <span>${x.avg_return_pct}% متوسط</span>
      </div>`).join('');
    $('btout').innerHTML=`<p>اختُبرت ${d.tested}/${d.top_n} عملة.</p>${rows}`;
  }catch(e){
    $('btout').innerHTML='<p class="red">فشل الاختبار: '+esc(e.message)+'</p>';
  }finally{b.disabled=false;b.textContent='اختبر أفضل 50'}
}

/* ---------- DETAIL MODAL ---------- */
async function detail(symbol){
  $('modal').classList.remove('hidden');
  $('detail').innerHTML='<div class="loading">⏳ جاري جلب التحليل التفصيلي...</div>';
  try{
    const d=await j('/api/details/'+encodeURIComponent(symbol));
    if(d.status!=='ok')throw Error(d.error||'خطأ');
    const f=d.funding_pct;
    const fund=f==null?'غير متاح':(f<0?'🟢 '+n(f,4)+'% (سالب)':n(f,4)+'% (موجب)');
    const m5=d.timeframes['5m'],m15=d.timeframes['15m'],h1=d.timeframes['1h'],h4=d.timeframes['4h'],day=d.timeframes['1d'];
    const m=moonScore({early_moon_ratio:d.early_moon_ratio,accumulation:d.accumulation,cvd:d.cvd,whale_hunter:d.whale,momentum:d.momentum,freshness:60});
    const tier=tierOf(m);
    $('detail').innerHTML=`
      <div class="detail-head">
        <div>
          <div class="kicker">V3.9 • تحليل تفصيلي</div>
          <h2>${esc(d.symbol)}</h2>
          <div class="detail-price">${money(d.price)} <small>${n(d.change24h,2)}% خلال 24س</small></div>
        </div>
        <div style="text-align:center">
          ${gauge(m)}
          <div class="tier-label" style="margin-top:6px"><span class="tier-badge ${tier.cls}">${tier.t}</span></div>
        </div>
      </div>
      <div class="decision">
        <div><b>🌙 Moon Score</b><strong>${n(m)}</strong></div>
        <div><b>Early Moon</b><strong>${n(d.early_moon_ratio)}</strong></div>
        <div><b>Risk Index</b><strong>${n(d.risk)}</strong><small>مؤشر نسبي</small></div>
      </div>
      <div class="detail-grid">
        ${stat('التمويل',fund)}${stat('التجميع',n(d.accumulation))}${stat('CVD',n(d.cvd))}${stat('Flow',n(d.flow))}
        ${stat('Whale',n(d.whale))}${stat('السيولة',n(d.liquidity))}${stat('RSI 15m',n(d.rsi))}${stat('OBV Score',n(d.obv))}
        ${stat('OBV Trend',trend(d.obv_trend_pct,d.obv_direction,1))}${stat('الحجم الحالي',n(d.volume_current_ratio,2)+'x')}
        ${stat('Volume Trend',trend(d.volume_trend_pct,d.volume_direction,1))}${stat('ATR 15m',n(d.atr_pct,3)+'%')}
        ${stat('الدعم',money(d.support))}${stat('المقاومة',money(d.resistance))}
        ${stat('بعد الدعم',n(d.support_distance,2)+'%')}${stat('بعد المقاومة',n(d.resistance_distance,2)+'%')}
        ${stat('حجم 24س',money(d.quoteVolume24h))}
      </div>
      ${confBox(d)}
      <section class="change">
        <h3>🔥 ماذا تغير؟</h3>
        <div class="change-grid">
          <div><b>5 دقائق</b><span>${n(d.change_5m,2)}%</span></div>
          <div><b>15 دقيقة</b><span>${n(d.change_15m,2)}%</span></div>
          <div><b>30 دقيقة</b><span>${n(d.change_30m,2)}%</span></div>
        </div>
        <div class="timeline">
          <div><b>📊 OBV</b><span>${n(d.obv_trend_pct,1)}% ${arrow(d.obv_direction)}</span></div>
          <div><b>📈 Volume</b><span>${seq(d.volume_sequence)} ${arrow(d.volume_direction)}</span></div>
          <div><b>🔥 CVD Proxy</b><span>${n(d.cvd_proxy_change_pct,1)}% ${arrow(d.flow_direction)}</span></div>
          <div><b>💰 Taker Buy</b><span>${n((d.taker_buy_ratio||0)*100,1)}% • ${n(d.taker_buy_trend_pct,1)}%</span></div>
        </div>
      </section>
      <h3>📊 الأطر الزمنية</h3>
      <div class="tf">
        <div><b>1 دقيقة</b> · RSI ${n(d.timeframes['1m'].rsi)} · OBV ${n(d.timeframes['1m'].obv)} · حجم ${n(d.timeframes['1m'].volume_ratio,2)}x</div>
        <div><b>5 دقائق</b> · RSI ${n(m5.rsi)} · OBV ${n(m5.obv)} · حجم ${n(m5.volume_ratio,2)}x</div>
        <div><b>15 دقيقة</b> · RSI ${n(m15.rsi)} · OBV ${n(m15.obv)} · حجم ${n(m15.volume_ratio,2)}x</div>
        <div><b>1 ساعة</b> · RSI ${n(h1.rsi)} · OBV ${n(h1.obv)} · حجم ${n(h1.volume_ratio,2)}x</div>
        <div><b>4 ساعات</b> · RSI ${n(h4.rsi)} · OBV ${n(h4.obv)} · حجم ${n(h4.volume_ratio,2)}x</div>
        <div><b>يومي</b> · RSI ${n(day.rsi)} · OBV ${n(day.obv)} · حجم ${n(day.volume_ratio,2)}x</div>
      </div>
      <h3>🔎 لماذا ظهرت؟</h3>
      <p>${esc((d.why||[]).join(' • ')||'لا توجد إشارة حاسمة بعد')}</p>
      <p class="note">OBV = حجم تراكمي، وCVD Proxy هنا مبني من تدفق Taker Buy/Sell على شموع 1m وليس دفتر محافظ. التمويل من Futures إن توفر؛ والرادار الأساسي Spot. هذه مؤشرات احتمالية وليست ضمانًا لحركة السعر.</p>`;
  }catch(e){
    $('detail').innerHTML='<div class="empty red">تعذر جلب التفاصيل: '+esc(e.message)+'</div>';
  }
}

/* ---------- BIND ---------- */
function bindCards(){
  document.querySelectorAll('[data-symbol]').forEach(x=>x.onclick=()=>detail(x.dataset.symbol));
}

$('scan').onclick=scan;
$('af').onclick=af;
$('bt').onclick=bt;
$('close').onclick=()=>$('modal').classList.add('hidden');
$('modal').onclick=e=>{if(e.target.id==='modal')$('modal').classList.add('hidden')};
document.querySelectorAll('.mode').forEach(x=>x.onclick=()=>{
  document.querySelectorAll('.mode').forEach(y=>y.classList.remove('active'));
  x.classList.add('active');
  ACTIVE=x.dataset.mode;
  renderMode();
});

scan(); ws(); setInterval(ws,5000); setInterval(scan,180000);
