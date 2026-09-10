// =====================================================
// AI CRYPTO RADAR
// DASHBOARD V1.1
// =====================================================


const marketTable =
    document.getElementById("marketTable");

const coinCount =
    document.getElementById("coinCount");

const testResult =
    document.getElementById("testResult");

const binanceStatus =
    document.getElementById("binanceStatus");


// =====================================================
// FORMAT PRICE
// =====================================================

function formatPrice(price) {

    if (price >= 1000) {

        return price.toLocaleString(
            "en-US",
            {
                maximumFractionDigits: 2
            }
        );

    }

    if (price >= 1) {

        return price.toLocaleString(
            "en-US",
            {
                maximumFractionDigits: 4
            }
        );

    }

    return price.toLocaleString(
        "en-US",
        {
            maximumFractionDigits: 8
        }
    );
}


// =====================================================
// FORMAT VOLUME
// =====================================================

function formatVolume(volume) {

    if (volume >= 1000000000) {

        return (
            "$" +
            (volume / 1000000000).toFixed(2) +
            "B"
        );

    }

    if (volume >= 1000000) {

        return (
            "$" +
            (volume / 1000000).toFixed(2) +
            "M"
        );

    }

    if (volume >= 1000) {

        return (
            "$" +
            (volume / 1000).toFixed(2) +
            "K"
        );

    }

    return "$" + volume.toFixed(2);
}


// =====================================================
// BINANCE TEST
// =====================================================

async function testBinance() {

    try {

        testResult.innerHTML =
            "⏳ جاري الاتصال بـ Binance...";

        const response =
            await fetch("/api/binance-test");

        const data =
            await response.json();


        if (data.status === "ok") {

            binanceStatus.innerHTML =
                "🟢 Binance: Connected";

            testResult.innerHTML =

                "🟢 <strong>Binance API متصل بنجاح</strong>" +

                "<br>" +

                "Ping: " +
                data.ping_ms +
                " ms";

        } else {

            binanceStatus.innerHTML =
                "🔴 Binance: Error";

            testResult.innerHTML =
                "🔴 فشل الاتصال بـ Binance";

        }


    } catch (error) {

        binanceStatus.innerHTML =
            "🔴 Binance: Offline";

        testResult.innerHTML =
            "🔴 خطأ في الاتصال: " +
            error.message;

    }

}


// =====================================================
// LOAD MARKET
// =====================================================

async function loadMarket() {

    try {

        const response =
            await fetch("/api/market");

        const data =
            await response.json();


        if (data.status !== "ok") {

            marketTable.innerHTML =

                `<tr>
                    <td colspan="5">
                        🔴 خطأ في بيانات Binance
                    </td>
                </tr>`;

            return;

        }


        coinCount.innerText =
            data.count + " زوج USDT";


        marketTable.innerHTML = "";


        data.coins.forEach(
            (coin, index) => {

                const change =
                    coin.change_24h;

                const changeClass =
                    change >= 0
                        ? "up"
                        : "down";

                const sign =
                    change >= 0
                        ? "+"
                        : "";


                const row =
                    document.createElement("tr");


                row.innerHTML = `

                    <td>
                        ${index + 1}
                    </td>

                    <td class="symbol">
                        ${coin.symbol}
                    </td>

                    <td class="price">
                        $${formatPrice(coin.price)}
                    </td>

                    <td class="${changeClass}">
                        ${sign}${change.toFixed(2)}%
                    </td>

                    <td class="volume">
                        ${formatVolume(
                            coin.quote_volume
                        )}
                    </td>

                `;


                marketTable.appendChild(row);

            }
        );


    } catch (error) {

        marketTable.innerHTML =

            `<tr>
                <td colspan="5">
                    🔴 تعذر تحميل السوق
                </td>
            </tr>`;

    }

}


// =====================================================
// START
// =====================================================

async function startRadar() {

    await testBinance();

    await loadMarket();

}


// =====================================================
// INITIAL
// =====================================================

startRadar();


// =====================================================
// REFRESH
// =====================================================

// كل 30 ثانية فقط في هذه المرحلة

setInterval(
    loadMarket,
    30000
);


// اختبار Binance كل دقيقتين

setInterval(
    testBinance,
    120000
);
