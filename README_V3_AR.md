# AI CRYPTO RADAR V3

## الجديد
- Historical Backtest Engine بدون look-ahead.
- اختبار 5m / 15m / 1h، افتراضي 15m.
- TP/SL وأفق زمني وعتبة إشارة قابلة للتعديل عبر API.
- Volume Profile حقيقي للبيانات الحالية من آخر صفقات Binance aggTrades، مقسم إلى 24 مستوى سعري.
- POC / HVN / LVN + Bid/Ask notional داخل مستويات السعر.
- Fallback تاريخي من Kline volume: يتم توزيع حجم كل شمعة على مستويات السعر التي لامستها. هذا ليس Tick-level exact؛ لأن Kline لا يعطي سعر كل صفقة تاريخية.
- واجهة تعرض Whale Hunter, Smart Money, Early Explosion, Liquidity, Volume Profile, CVD/Taker, Accumulation, AI Confidence وTop 5.
- زر Backtest داخل كل بطاقة.

## Endpoints
- `/api/health`
- `/api/binance-test`
- `/api/radar`
- `/api/debug`
- `/api/status`
- `/api/volume-profile/BTCUSDT`
- `/api/backtest?symbol=BTCUSDT&days=30&interval=15m&target=0.02&stop=0.015&horizon=16&threshold=70`

## منهجية Backtest
الإشارة في كل نقطة زمنية تستخدم فقط الشموع السابقة لنقطة الدخول. بعد ذلك يتم فحص الشموع المستقبلية لمعرفة أيهما حدث أولاً: الهدف أو الوقف. إذا لمس نفس البار الهدف والوقف معًا، يتم احتسابه بشكل محافظ كخسارة ملتبسة.

## ملاحظة
V3 لا يتداول ولا يضع أوامر شراء/بيع. النتائج احتمالية وليست ضمانًا للصعود.
