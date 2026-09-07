import ta


def indicators(df):

    close=df["close"]
    volume=df["volume"]


    ema=ta.trend.EMAIndicator(
        close,
        200
    ).ema_indicator()


    rsi=ta.momentum.RSIIndicator(
        close,
        14
    ).rsi()



    avg_volume=volume[:-1].mean()


    return {

    "volume_ratio":
    volume.iloc[-1]/avg_volume,


    "ema":
    close.iloc[-1] > ema.iloc[-1],


    "rsi":
    float(rsi.iloc[-1]),


    "change":
    (
    close.iloc[-1] /
    close.iloc[-10]-1
    )*100

    }
