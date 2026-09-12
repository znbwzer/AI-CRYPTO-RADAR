const top5 = document.getElementById('top5');
const radar = document.getElementById('radar');
const connection = document.getElementById('connection');
const scanInfo = document.getElementById('scanInfo');
const filter = document.getElementById('stageFilter');
const refreshBtn = document.getElementById('refreshBtn');
let allResults = [];

function n(v,d=2){return Number(v||0).toLocaleString('en-US',{maximumFractionDigits:d})}
function money(v){if(v>=1e9)return '$'+n(v/1e9,2)+'B';if(v>=1e6)return '$'+n(v/1e6,2)+'M';if(v>=1e3)return '$'+n(v/1e3,1)+'K';return '$'+n(v,0)}
function bar(label,value){return `<div class="bar">${label} <b>${n(value,0)}</b><div class="track"><div class="fill" style="width:${Math.max(0,Math.min(100,value))}%"></div></div></div>`}
function card(x){
  const stageClass=x.stage==='TRIGGER'?'good':x.stage==='READY'?'warn':x.stage==='EXPANSION'?'bad':'good';
  const flags=[];
  if(x.flags?.compression)flags.push('🟢 COMPRESSION');
  if(x.flags?.dryup)flags.push('🟢 DRY-UP');
  if(x.flags?.buy_pressure)flags.push('🟢 BUY PRESSURE');
  if(x.flags?.cvd)flags.push('🟢 CVD');
  if(x.flags?.absorption_proxy)flags.push('🟢 ABSORPTION');
  if(x.flags?.breakout)flags.push('🟢 BREAKOUT');
  return `<article class="card">
    <div class="top"><div class="sym">${x.symbol}</div><div class="stage ${stageClass}">${x.stage_ar}</div></div>
    <div class="score">${n(x.early_score,1)}<small style="font-size:12px;color:#8197a2"> / 100 Early Score</small></div>
    <div class="bars">
      ${bar('Accumulation',x.accumulation)}
      ${bar('Smart Money',x.smart_money)}
      ${bar('Volume Pressure',x.volume_pressure)}
      ${bar('Liquidity',x.liquidity)}
      ${bar('Breakout Ready',x.breakout_ready)}
      ${bar('Risk Safety',x.risk_safety)}
    </div>
    <div class="meta">
      <div>السعر<br><b>${n(x.price,8)}</b></div>
      <div>24h<br><b class="${x.change24h>=0?'good':'bad'}">${n(x.change24h,2)}%</b></div>
      <div>المقاومة<br><b>${n(x.resistance,8)}</b></div>
      <div>المسافة<br><b>${n(x.distance_to_resistance,2)}%</b></div>
      <div>CVD<br><b>${n(x.cvd_score,0)}</b></div>
      <div>Depth<br><b>${n(x.depth_score,0)}</b></div>
      <div>1h / 4h<br><b>${n(x.tf_1h,0)} / ${n(x.tf_4h,0)}</b></div>
      <div>24h Volume<br><b>${money(x.quoteVolume24h)}</b></div>
    </div>
    <div class="flags">${flags.map(f=>`<span class="flag">${f}</span>`).join('')}</div>
    <div class="why">${(x.why||[]).join(' • ')}</div>
  </article>`;
}
function render(){
  const filtered=filter.value==='ALL'?allResults:allResults.filter(x=>x.stage===filter.value);
  top5.innerHTML=allResults.slice(0,5).map(card).join('')||'<div class="card">لا توجد نتائج بعد.</div>';
  radar.innerHTML=filtered.map(card).join('')||'<div class="card">لا توجد نتائج بهذه المرحلة.</div>';
}
async function load(){
  refreshBtn.disabled=true; refreshBtn.textContent='جاري الفحص...';
  try{
    const r=await fetch('/api/radar',{cache:'no-store'});
    const d=await r.json();
    if(d.status!=='ok')throw new Error(d.error||'Radar error');
    allResults=d.results||[];
    connection.textContent='🟢 Binance متصل';
    scanInfo.textContent=`فحص ${d.scanned_universe} عملة • تحليل عميق ${d.structure_candidates} • ${d.scan_seconds}s • آخر تحديث ${new Date(d.updated_at).toLocaleTimeString()}`;
    render();
  }catch(e){
    connection.textContent='🔴 خطأ في الرادار';
    scanInfo.textContent=e.message;
  }finally{refreshBtn.disabled=false;refreshBtn.textContent='تحديث الآن'}
}
filter.addEventListener('change',render);refreshBtn.addEventListener('click',load);load();setInterval(load,90000);
