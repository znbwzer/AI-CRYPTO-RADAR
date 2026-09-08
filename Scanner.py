import requests
import pandas as pd
import time

from indicators import calculate_indicators
from scoring import calculate_score


BINANCE_API = "https://api.binance.com"


session = requests.Session()


def get_usdt_symbols():

    url = (
        f"{BINANCE_API}/api/v3/exchangeInfo"
    )

    response = session.get(
        url,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    symbols = []

    for item in data["symbols"]:

        if (
            item.get("quoteAsset") == "USDT"
            and item.get("status") == "TRADING"
            and item.get("isSpotTradingAllowed", False)
        ):

            symbols.append(
                item["symbol"]
            )

    return symbols


def get_24h_tickers():

    url = (
        f"{BINANCE_API}/api/v3/ticker/24hr"
    )

    response = session.get(
        url,
        timeout=20
    )

    response.raise_for_status()

    return response.json()


def get_top_symbols(max_symbols=100):

    symbols = set(
        get_usdt_symbols()
    )

    tickers = get_24h_tickers()

    filtered = []

    for ticker in tickers:

        symbol = ticker.get("symbol")

        if symbol in symbols:

            try:

                quote_volume = float(
                    ticker.get(
                        "quoteVolume",
                        0
                    )
                )

                filtered.append(
                    (
                        symbol,
                        quote_volume
                    )
                )

            except (ValueError, TypeError):

                continue


    filtered.sort(
        key=lambda x: x[1],
        reverse=True
    )


    return [
        item[0]
        for item in filtered[:max_symbols]
    ]


def get_klines(symbol):

    url = (
        f"{BINANCE_API}/api/v3/klines"
    )

    params = {
        "symbol": symbol,
        "interval": "5m",
        "limit": 250
    }


    response = session.get(
        url,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    candles = response.json()


    df = pd.DataFrame(
        candles,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore"
        ]
    )


    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )


    df.dropna(
        inplace=True
    )

    return df


def scan_market(max_symbols=100):

    results = []

    symbols = get_top_symbols(
        max_symbols=max_symbols
    )


    for index, symbol in enumerate(symbols):

        try:

            df = get_klines(symbol)

            data = calculate_indicators(df)

            if data is None:
                continue


            result = calculate_score(data)


            if result["score"] >= 50:

                results.append({
                    "symbol": symbol,

                    "score":
                    result["score"],

                    "signal":
                    result["signal"],

                    "price":
                    data["price"],

                    "rsi":
                    round(data["rsi"], 2),

                    "volume_ratio":
                    round(
                        data["volume_ratio"],
                        2
                    ),

                    "momentum":
                    round(
                        data["momentum"],
                        2
                    ),

                    "reasons":
                    result["reasons"]
                })


        except Exception as error:

            print(
                f"Scanner error {symbol}: {error}"
            )


    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )


    return results
