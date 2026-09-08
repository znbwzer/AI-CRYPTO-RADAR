def calculate_score(data):

    score = 0
    reasons = []


    # =========================
    # 🐋 Volume / Whale Activity
    # =========================

    if data["volume_ratio"] >= 4:

        score += 30

        reasons.append(
            "🐋 Very Strong Volume Activity"
        )

    elif data["volume_ratio"] >= 2.5:

        score += 22

        reasons.append(
            "🐋 Strong Volume Increase"
        )

    elif data["volume_ratio"] >= 1.5:

        score += 10

        reasons.append(
            "📊 Volume Increasing"
        )


    # =========================
    # 📈 Trend
    # =========================

    if data["above_ema200"]:

        score += 20

        reasons.append(
            "📈 Price Above EMA200"
        )


    # =========================
    # RSI
    # =========================

    if 45 <= data["rsi"] <= 68:

        score += 15

        reasons.append(
            "✅ Healthy RSI Zone"
        )

    elif 40 <= data["rsi"] <= 75:

        score += 8

        reasons.append(
            "📊 RSI Acceptable"
        )


    # =========================
    # 🚀 Momentum
    # =========================

    if 2 <= data["momentum"] <= 8:

        score += 20

        reasons.append(
            "🚀 Early Momentum Detected"
        )

    elif 1 <= data["momentum"] < 2:

        score += 10

        reasons.append(
            "📈 Momentum Starting"
        )


    # =========================
    # 💰 Accumulation
    # =========================

    if (
        abs(data["price_change_20"]) < 5
        and data["volume_ratio"] >= 2
    ):

        score += 15

        reasons.append(
            "💰 Possible Smart Money Accumulation"
        )


    # =========================
    # Limit
    # =========================

    score = min(score, 100)


    # =========================
    # Signal Type
    # =========================

    if score >= 85:

        signal = "🔥 STRONG OPPORTUNITY"

    elif score >= 70:

        signal = "🚀 HIGH POTENTIAL"

    elif score >= 50:

        signal = "👀 WATCHLIST"

    else:

        signal = "⚪ NO SIGNAL"


    return {
        "score": score,
        "signal": signal,
        "reasons": reasons
    }
