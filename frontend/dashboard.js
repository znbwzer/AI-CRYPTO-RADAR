const radarTable =
    document.getElementById("radarTable");

const top5 =
    document.getElementById("top5");

const radarStatus =
    document.getElementById("radarStatus");

const scanInfo =
    document.getElementById("scanInfo");

const binanceStatus =
    document.getElementById("binanceStatus");


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


function formatVolume(volume) {

    if (volume >= 1000000000) {

        return "$" +
            (volume / 1000000000)
            .toFixed(2) +
            "B";

    }

    if (volume >= 1000000) {

        return "$" +
            (volume / 1000000)
            .toFixed(2) +
            "M";

    }

    if (volume >= 1000) {

        return "$" +
            (volume / 1000)
            .toFixed(2) +
            "K";

    }

    return "$" +
        volume.toFixed(2);
}


function scoreClass(score) {

    if (score >= 85)
        return "up";

    if (score >= 75)
        return "up";

    if (score >= 65)
        return "";

    return "down";
}


function renderTop5(coins) {

    if (!coins || coins.length === 0) {

        top5.innerHTML =
            "لا توجد فرص قوية حاليًا";

        return;
    }


    top5.innerHTML = "";


    coins.forEach(
        (coin, index) => {

            const card =
                document.createElement("div");

            card.style.padding = "14px";

            card.style.marginBottom = "10px";

            card.style.borderRadius = "12px";

            card.style.background =
                "#0d131b";

            card.style.border =
                "1px solid #26313e";


            card.innerHTML = `

                <div style="
                    display:flex;
                    justify-content:space-between;
                    align-items:center;
                    gap:10px;
                ">

                    <strong>
                        ${index + 1}.
                        ${coin.symbol}
                    </strong>

                    <strong class="${scoreClass(
                        coin.confidence
                    )}">
                        ${coin.confidence}/100
                    </strong>

                </div>

                <div style="
                    margin-top:8px;
                    font-size:14px;
                ">

                    ${coin.signal}

                </div>

                <div style="
                    margin-top:8px;
                    font-size:12px;
                    color:#8f9aaa;
                ">

                    RSI ${coin.rsi}
                    &nbsp; | &nbsp;

                    Volume x${coin.volume_ratio}
                    &nbsp; | &nbsp;

                    Momentum ${coin.momentum_5m}%

                </div>
            `;


            top5.appendChild(card);

        }
    );
}


function renderRadar(coins) {

    radarTable.innerHTML = "";


    coins.forEach(
        (coin, index) => {

            const row =
                document.createElement("tr");


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


            row.innerHTML = `

                <td>
                    ${index + 1}
                </td>

                <td class="symbol">
                    ${coin.symbol}
                </td>

                <td>
                    ${coin.signal}
                </td>

                <td class="${scoreClass(
                    coin.confidence
                )}">

                    <strong>
                        ${coin.confidence}
                    </strong>

                </td>

                <td>
                    ${coin.rsi}
                </td>

                <td class="volume">

                    x${coin.volume_ratio}

                </td>

                <td class="${changeClass}">

                    ${sign}${change.toFixed(2)}%

                </td>

            `;


            radarTable.appendChild(row);

        }
    );
}


async function runRadar() {

    try {

        radarStatus.innerHTML =
            "⏳ جاري فحص السوق وتحليل العملات...";


        const response =
            await fetch(
                "/api/radar",
                {
                    cache: "no-store"
                }
            );


        const data =
            await response.json();


        if (data.status !== "ok") {

            throw new Error(
                data.error ||
                "Radar error"
            );

        }


        binanceStatus.innerHTML =
            "🟢 Binance: Connected";


        radarStatus.innerHTML =

            "🟢 الرادار يعمل بنجاح" +
            "<br>" +
            "تم تحليل " +
            data.analyzed +
            " من " +
            data.scanned +
            " عملة";


        scanInfo.innerText =
            data.analyzed +
            " عملة";


        renderTop5(
            data.top5
        );


        renderRadar(
            data.coins
        );


    } catch (error) {

        binanceStatus.innerHTML =
            "🔴 Binance: Error";


        radarStatus.innerHTML =
            "🔴 خطأ: " +
            error.message;


        radarTable.innerHTML = `

            <tr>

                <td colspan="7">

                    🔴 تعذر تشغيل الرادار

                </td>

            </tr>

        `;

    }

}


async function checkBinance() {

    try {

        const response =
            await fetch(
                "/api/binance-test"
            );


        const data =
            await response.json();


        if (data.status === "ok") {

            binanceStatus.innerHTML =
                "🟢 Binance: Connected";

        } else {

            binanceStatus.innerHTML =
                "🔴 Binance: Error";

        }

    } catch {

        binanceStatus.innerHTML =
            "🔴 Binance: Offline";

    }

}


async function start() {

    await checkBinance();

    await runRadar();

}


start();


/*
   تحديث الرادار كل دقيقة
*/

setInterval(
    runRadar,
    60000
);


/*
   فحص الاتصال كل دقيقتين
*/

setInterval(
    checkBinance,
    120000
);
