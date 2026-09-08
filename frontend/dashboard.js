async function fetchJSON(url) {

    const response =
    await fetch(url);

    if (!response.ok) {

        throw new Error(
            "API Error"
        );

    }

    return await response.json();

}



async function loadStatus() {

    try {

        const data =
        await fetchJSON(
            "/api/status"
        );


        const statusElement =
        document.getElementById(
            "status"
        );


        const scannerElement =
        document.getElementById(
            "scannerStatus"
        );


        document.getElementById(
            "lastScan"
        ).textContent =
        data.last_scan || "--";


        document.getElementById(
            "coinsFound"
        ).textContent =
        data.coins_found || 0;


        if (data.last_error) {

            statusElement.textContent =
            "⚠️ Scanner Error";

            statusElement.className =
            "status error";

        }

        else if (data.running) {

            statusElement.textContent =
            "🟢 LIVE";

            statusElement.className =
            "status online";

        }

        else {

            statusElement.textContent =
            "🟡 Starting";

            statusElement.className =
            "status loading";

        }


        scannerElement.textContent =
        data.running
        ? "🟢 Running"
        : "🟡 Starting";


    }

    catch (error) {

        console.error(error);

    }

}



function getScoreClass(score) {

    if (score >= 85) {

        return "high-score";

    }

    if (score >= 70) {

        return "medium-score";

    }

    return "";

}



async function loadResults() {

    try {

        const data =
        await fetchJSON(
            "/api/results"
        );


        const table =
        document.getElementById(
            "results"
        );


        const loading =
        document.getElementById(
            "loading"
        );


        table.innerHTML = "";


        if (!data.length) {

            loading.style.display =
            "block";

            return;

        }


        loading.style.display =
        "none";


        data.forEach(
            (coin, index) => {

                const row =
                document.createElement(
                    "tr"
                );


                row.innerHTML = `

                    <td>${index + 1}</td>

                    <td>
                        <strong>
                        ${coin.symbol}
                        </strong>
                    </td>

                    <td
                    class="score ${getScoreClass(
                        coin.score
                    )}">

                        ${coin.score}/100

                    </td>

                    <td>
                        ${coin.signal}
                    </td>

                    <td>
                        ${Number(
                            coin.price
                        ).toPrecision(7)}
                    </td>

                    <td>
                        ${coin.rsi}
                    </td>

                    <td>
                        ${coin.volume_ratio}x
                    </td>

                    <td
                    class="reasons">

                        ${coin.reasons.join(
                            "<br>"
                        )}

                    </td>

                `;


                table.appendChild(
                    row
                );

            }
        );


    }

    catch (error) {

        console.error(error);

    }

}



async function loadHistory() {

    try {

        const data =
        await fetchJSON(
            "/api/signals"
        );


        const container =
        document.getElementById(
            "history"
        );


        if (!data.length) {

            container.innerHTML =
            "<p>No signals yet.</p>";

            return;

        }


        container.innerHTML =
        "";


        data.slice(0, 20)
        .forEach(signal => {

            const item =
            document.createElement(
                "div"
            );


            item.className =
            "history-item";


            item.innerHTML = `

                <strong>
                    ${signal.symbol}
                </strong>

                — Score:
                ${signal.score}/100

                <br>

                Price:
                ${signal.price}

                <br>

                ${signal.reasons}

            `;


            container.appendChild(
                item
            );

        });


    }

    catch (error) {

        console.error(error);

    }

}



async function loadData() {

    await loadStatus();

    await loadResults();

    await loadHistory();

}



loadData();


setInterval(
    loadData,
    10000
);
