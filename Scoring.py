def score_market(data):

    score=0

    reasons=[]


    if data["volume_ratio"]>3:

        score+=30
        reasons.append(
        "🐋 Volume Explosion"
        )


    if data["ema"]:

        score+=20
        reasons.append(
        "📈 Trend Positive"
        )


    if 45<data["rsi"]<70:

        score+=20
        reasons.append(
        "✅ RSI Healthy"
        )


    if data["change"]>2:

        score+=20
        reasons.append(
        "🚀 Momentum"
        )


    if score>80:

        reasons.append(
        "🔥 Strong Signal"
        )


    return score,reasons
