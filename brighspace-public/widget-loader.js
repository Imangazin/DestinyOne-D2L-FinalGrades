async function loadFinalGradesWidget(options) {
    const widgetUrl = options.widgetUrl || options.widgetPath || "widget.html";
    const targetId = options.targetId || "destinyone-final-grades";
    const toolUrl = options.toolUrl || "";
    const target = document.getElementById(targetId);

    try {
        const response = await fetch(widgetUrl);
        if (!response.ok) {
            throw new Error("Could not load widget HTML: " + response.status);
        }

        const html = await response.text();
        target.innerHTML = html;
        createProceedButton(target, targetId, toolUrl);
    } catch (error) {
        target.textContent = "Unable to load the Destiny One final grades widget.";
        console.error(error);
    }
}

function createProceedButton(widgetRoot, targetId, toolUrl) {
    const container = widgetRoot.querySelector("#proceed-button-container");
    const button = document.createElement("button");

    button.id = "proceed-button";
    button.type = "button";
    button.textContent = "Proceed";

    Object.assign(button.style, {
        display: "block",
        margin: "0 auto",
        border: "0",
        borderRadius: "0.3rem",
        minWidth: "250px",
        minHeight: "42px",
        padding: "0 30px",
        color: "#202122",
        background: "#e3e9f1",
        fontFamily: 'Lato, "Lucida Sans Unicode", "Lucida Grande", sans-serif',
        fontSize: "14px",
        fontWeight: "700",
        letterSpacing: "0.2px",
        lineHeight: "0.9rem",
        cursor: "pointer",
    });

    button.addEventListener("click", function () {
        const normalizedToolUrl = normalizeHtmlUrl(toolUrl);
        const target = document.getElementById(targetId);

        if (!normalizedToolUrl) {
            alert("The LTI tool link has not been configured yet.");
            return;
        }

        target.innerHTML = "";
        target.appendChild(createToolFrame(normalizedToolUrl));
    });

    container.appendChild(button);
}

function createToolFrame(toolUrl) {
    const frame = document.createElement("iframe");

    frame.src = toolUrl;
    frame.title = "Destiny One grade submission tool";

    Object.assign(frame.style, {
        width: "100%",
        minHeight: "520px",
        border: "0",
    });

    return frame;
}

function normalizeHtmlUrl(url) {
    return url.replaceAll("&amp;", "&");
}
