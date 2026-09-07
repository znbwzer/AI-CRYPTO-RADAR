from binance.client import Client
import pandas as pd
from indicators import indicators
from scoring import score_market
from database import save_signal


client=Client()


def symbols():

    info=client.get_exchange_info()

    result=[]

    for s in info["symbols"]:

        if (
        s["quoteAsset"]=="USDT"
        and s["status"]=="TRADING"
        ):

            result.append(
            s["symbol"]
            )

    return result




def scan():

    results=[]


    for coin in symbols():


        try:

            candles=client.get_klines(
            symbol=coin,
            interval="5m",
            limit=250
            )


            df=pd.DataFrame(
            candles
            )


            df["close"]=df[4].astype(float)
            df["volume"]=df[5].astype(float)



            data=indicators(df)


            score,reasons=score_market(data)



            if score>=70:


                price=float(df["close"].iloc[-1])


                save_signal(
                coin,
                score,
                price,
                ",".join(reasons)
                )


                results.append(
                {
                "coin":coin,
                "score":score,
                "price":price
                }
                )


        except Exception:

            pass



    return results
