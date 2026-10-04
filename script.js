const API_BASE = "http://127.0.0.1:5000";

const youtubeUrl = document.getElementById("youtubeUrl");
const clearButton = document.getElementById("clearButton");
const generateButton = document.getElementById("generateButton");
const themeButton = document.getElementById("themeButton");
const inputError = document.getElementById("inputError");

const videoSection = document.getElementById("videoSection");
const videoThumbnail = document.getElementById("videoThumbnail");
const videoTitle = document.getElementById("videoTitle");
const videoStatus = document.getElementById("videoStatus");
const newVideoButton = document.getElementById("newVideoButton");

const resultsSection = document.getElementById("resultsSection");
const resultLabel = document.getElementById("resultLabel");
const resultTitle = document.getElementById("resultTitle");
const resultContent = document.getElementById("resultContent");
const resultClose = document.getElementById("resultClose");

const aiLoading = document.getElementById("aiLoading");
const loadingTitle = document.getElementById("loadingTitle");
const loadingText = document.getElementById("loadingText");

const askBox = document.getElementById("askBox");
const askInput = document.getElementById("askInput");
const askButton = document.getElementById("askButton");
const askAnswer = document.getElementById("askAnswer");

const examContainer = document.getElementById("examContainer");

const historyButton = document.getElementById("historyButton");
const historyDrawer = document.getElementById("historyDrawer");
const historyClose = document.getElementById("historyClose");
const drawerOverlay = document.getElementById("drawerOverlay");
const historyList = document.getElementById("historyList");
const clearHistoryButton = document.getElementById("clearHistoryButton");

const toast = document.getElementById("toast");

let currentVideo = null;
let isGenerating = false;
let activeAIFeature = null;
let isAskingAI = false;


/* =========================
   TOAST
========================= */

function showToast(message) {
    if (!toast) return;

    toast.textContent = message;
    toast.classList.add("show");

    setTimeout(() => {
        toast.classList.remove("show");
    }, 2500);
}


/* =========================
   THEME
========================= */

function loadTheme() {
    const savedTheme = localStorage.getItem("vidora-theme");

    if (savedTheme === "light") {
        document.body.classList.add("light-mode");

        if (themeButton) {
            themeButton.textContent = "☀️";
        }
    } else {
        document.body.classList.remove("light-mode");

        if (themeButton) {
            themeButton.textContent = "🌙";
        }
    }
}

if (themeButton) {
    themeButton.addEventListener("click", () => {
        document.body.classList.toggle("light-mode");

        const isLight =
            document.body.classList.contains("light-mode");

        localStorage.setItem(
            "vidora-theme",
            isLight ? "light" : "dark"
        );

        themeButton.textContent =
            isLight ? "☀️" : "🌙";

        showToast(
            isLight
                ? "Light mode enabled."
                : "Dark mode enabled."
        );
    });
}

loadTheme();


/* =========================
   URL INPUT
========================= */

if (youtubeUrl) {
    youtubeUrl.addEventListener("input", () => {
        if (clearButton) {
            clearButton.style.display =
                youtubeUrl.value.trim()
                    ? "block"
                    : "none";
        }

        if (inputError) {
            inputError.textContent = "";
        }
    });
}

if (clearButton) {
    clearButton.addEventListener("click", () => {
        youtubeUrl.value = "";

        clearButton.style.display = "none";

        if (inputError) {
            inputError.textContent = "";
        }

        youtubeUrl.focus();
    });
}


/* =========================
   NORMALIZE YOUTUBE URL
========================= */

function normalizeYouTubeUrl(url) {
    let value = String(url || "").trim();

    if (!value) {
        return "";
    }

    if (!/^https?:\/\//i.test(value)) {
        value = "https://" + value;
    }

    return value;
}


/* =========================
   YOUTUBE HOST CHECK
========================= */

function isValidYouTubeHost(hostname) {
    const host = hostname
        .toLowerCase()
        .replace(/^www\./, "");

    const validHosts = [
        "youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
        "youtube-nocookie.com"
    ];

    return validHosts.includes(host);
}


/* =========================
   YOUTUBE URL VALIDATION
========================= */

function isValidYouTubeUrl(url) {
    try {
        const normalized = normalizeYouTubeUrl(url);
        const parsed = new URL(normalized);

        return isValidYouTubeHost(parsed.hostname);
    } catch {
        return false;
    }
}


/* =========================
   EXTRACT VIDEO ID
========================= */

function extractVideoId(url) {
    try {
        const normalized = normalizeYouTubeUrl(url);
        const parsed = new URL(normalized);

        const hostname = parsed.hostname
            .toLowerCase()
            .replace(/^www\./, "");

        if (!isValidYouTubeHost(hostname)) {
            return null;
        }

        /*
         * Any YouTube URL containing ?v=VIDEO_ID
         */
        const queryVideoId =
            parsed.searchParams.get("v");

        if (queryVideoId) {
            return cleanVideoId(queryVideoId);
        }

        /*
         * youtu.be/VIDEO_ID
         */
        if (hostname === "youtu.be") {
            const parts = parsed.pathname
                .split("/")
                .filter(Boolean);

            return cleanVideoId(parts[0]);
        }

        /*
         * /shorts/VIDEO_ID
         * /embed/VIDEO_ID
         * /live/VIDEO_ID
         */
        const parts = parsed.pathname
            .split("/")
            .filter(Boolean);

        if (parts.length >= 2) {
            const type = parts[0].toLowerCase();

            if (
                type === "shorts" ||
                type === "embed" ||
                type === "live"
            ) {
                return cleanVideoId(parts[1]);
            }
        }

        return null;
    } catch {
        return null;
    }
}


/* =========================
   CLEAN VIDEO ID
========================= */

function cleanVideoId(value) {
    if (!value) return null;

    const id = String(value).trim();

    if (!/^[A-Za-z0-9_-]{11}$/.test(id)) {
        return null;
    }

    return id;
}


/* =========================
   LOADING BUTTON
========================= */

function setGenerateLoading(isLoading) {
    if (!generateButton) return;

    generateButton.disabled = isLoading;

    if (isLoading) {
        generateButton.innerHTML = `
            <span class="generate-icon">⏳</span>
            <span class="generate-text">Processing...</span>
        `;
    } else {
        generateButton.innerHTML = `
            <span class="generate-icon">✦</span>
            <span class="generate-text">Generate</span>
        `;
    }
}


/* =========================
   GENERATE STAGE
========================= */

function setGenerateStage(stage) {
    if (!videoStatus) return;

    const stages = {
        connecting: {
            title: "🔗 Connecting to YouTube...",
            text: "Connecting to the YouTube video."
        },

        transcript: {
            title: "📝 Fetching video transcript...",
            text: "Finding the best available captions."
        },

        understanding: {
            title: "🧠 Vidora AI is understanding the video...",
            text: "Preparing the video content for learning."
        },

        preparing: {
            title: "✨ Preparing your learning material...",
            text: "Almost ready."
        },

        ready: {
            title: "Video ready",
            text: "Choose how you want to learn."
        }
    };

    const current = stages[stage];

    if (!current) return;

    videoStatus.textContent =
        current.title;
}


/* =========================
   AI LOADING STAGE
========================= */

function setAILoading(message) {
    if (!aiLoading) return;

    aiLoading.classList.remove("hidden");

    if (loadingTitle) {
        loadingTitle.textContent =
            "🧠 Vidora AI is understanding the video...";
    }

    if (loadingText) {
        loadingText.textContent =
            message ||
            "Preparing your learning material...";
    }
}


/* =========================
   FETCH VIDEO INFO
========================= */

async function fetchVideoInfo(videoId) {
    try {
        const response = await fetch(
            `${API_BASE}/api/video-info`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    video_id: videoId
                })
            }
        );

        const data = await safeJSON(response);

        if (response.ok && data.success) {
            return data;
        }

        return {
            success: true,
            title: "YouTube Video",
            thumbnail:
                `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`
        };
    } catch (error) {
        console.warn(
            "Video info could not be loaded:",
            error
        );

        return {
            success: true,
            title: "YouTube Video",
            thumbnail:
                `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`
        };
    }
}


/* =========================
   SAFE JSON RESPONSE
========================= */

async function safeJSON(response) {
    try {
        return await response.json();
    } catch {
        return {
            success: false,
            error:
                `Server returned an invalid response (${response.status}).`
        };
    }
}


/* =========================
   GENERATE VIDEO
========================= */

if (generateButton) {
    generateButton.addEventListener(
        "click",
        generateVideo
    );
}

async function generateVideo() {
    if (isGenerating) {
        return;
    }

    const rawUrl =
        youtubeUrl
            ? youtubeUrl.value.trim()
            : "";

    if (inputError) {
        inputError.textContent = "";
    }

    if (!rawUrl) {
        if (inputError) {
            inputError.textContent =
                "Please paste a YouTube video link.";
        }

        youtubeUrl.focus();
        return;
    }

    const url = normalizeYouTubeUrl(rawUrl);

    if (!isValidYouTubeUrl(url)) {
        if (inputError) {
            inputError.textContent =
                "Please enter a valid YouTube URL.";
        }

        showToast("Invalid YouTube URL.");
        return;
    }

    const videoId =
        extractVideoId(url);

    if (!videoId) {
        if (inputError) {
            inputError.textContent =
                "This YouTube link does not contain a valid video.";
        }

        showToast("Invalid YouTube video.");
        return;
    }

    isGenerating = true;

    /*
     * IMPORTANT:
     * Clear old context BEFORE starting a new generation.
     */
    currentVideo = null;

    setGenerateLoading(true);

    if (videoSection) {
        videoSection.classList.add("hidden");
    }

    resetResults();

    setGenerateStage("connecting");

    try {
        /*
         * Stage 1:
         * YouTube connection.
         */
        await delay(250);

        setGenerateStage("transcript");

        /*
         * Transcript and video info are requested
         * at the same time to reduce waiting time.
         */
        const transcriptPromise =
            fetch(
                `${API_BASE}/api/transcript`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        url: url
                    })
                }
            );

        const videoInfoPromise =
            fetchVideoInfo(videoId);

        const [
            transcriptResponse,
            videoInfo
        ] = await Promise.all([
            transcriptPromise,
            videoInfoPromise
        ]);

        const transcriptData =
            await safeJSON(transcriptResponse);

        if (
            !transcriptResponse.ok ||
            !transcriptData.success
        ) {
            throw new Error(
                transcriptData.error ||
                "This video could not be processed. Please try another YouTube video."
            );
        }

        if (
            !transcriptData.transcript ||
            !String(
                transcriptData.transcript
            ).trim()
        ) {
            throw new Error(
                "No usable transcript was found for this video. Please try a video with captions."
            );
        }

        /*
         * Stage 3
         */
        setGenerateStage("understanding");

        await delay(350);

        /*
         * Stage 4
         */
        setGenerateStage("preparing");

        await delay(350);

        const thumbnail =
            videoInfo.thumbnail ||
            `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;

        currentVideo = {
            url: url,
            videoId: videoId,
            title:
                videoInfo.title ||
                "YouTube Video",
            thumbnail: thumbnail,
            transcript:
                transcriptData.transcript,
            segments:
                transcriptData.segments || [],
            language:
                transcriptData.language || "",
            languageCode:
                transcriptData.language_code || "",
            captionType:
                transcriptData.caption_type || "",
            createdAt:
                new Date().toISOString()
        };

        /*
         * Show video.
         */
        videoThumbnail.src =
            currentVideo.thumbnail;

        videoThumbnail.onerror = () => {
            videoThumbnail.src =
                `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;
        };

        videoTitle.textContent =
            currentVideo.title;

        setGenerateStage("ready");

        videoStatus.textContent =
            "Transcript ready. Choose how you want to learn.";

        videoSection.classList.remove("hidden");

        resetResults();

        saveToHistory(currentVideo);

        showToast(
            "Video ready! Choose a learning mode."
        );

        videoSection.scrollIntoView({
            behavior: "smooth",
            block: "center"
        });

    } catch (error) {
        console.error(
            "Generate error:",
            error
        );

        currentVideo = null;

        const message =
            error && error.message
                ? error.message
                : "Something went wrong while processing this video.";

        if (inputError) {
            inputError.textContent = message;
        }

        showToast(
            "Could not process this video."
        );

    } finally {
        isGenerating = false;
        setGenerateLoading(false);
    }
}


/* =========================
   FEATURE TITLES
========================= */

const featureNames = {
    notes: {
        label: "FULL NOTES",
        title: "Complete Video Notes"
    },

    summary: {
        label: "SUMMARY",
        title: "Video Summary"
    },

    explain: {
        label: "DETAILED EXPLANATION",
        title: "Understand the Video"
    },

    keypoints: {
        label: "KEY POINTS",
        title: "Important Points"
    },

    exam: {
        label: "EXAM & MCQ MODE",
        title: "Exam Preparation"
    }
};


/* =========================
   FEATURE BUTTONS
========================= */

document
    .querySelectorAll(".feature-card")
    .forEach(button => {

        button.addEventListener(
            "click",
            () => {

                const feature =
                    button.dataset.feature;

                if (!currentVideo) {
                    showToast(
                        "Generate a YouTube video first."
                    );
                    return;
                }

                if (activeAIFeature) {
                    showToast(
                        "Vidora is already processing another request."
                    );
                    return;
                }

                if (feature === "ask") {
                    openAskMode();
                    return;
                }

                runAIFeature(feature);
            }
        );
    });


/* =========================
   AI FEATURE
========================= */

async function runAIFeature(feature) {
    if (!currentVideo) {
        showToast(
            "Generate a video first."
        );
        return;
    }

    const info =
        featureNames[feature];

    if (!info) {
        showToast(
            "This learning mode is unavailable."
        );
        return;
    }

    if (activeAIFeature) {
        showToast(
            "Please wait for the current result."
        );
        return;
    }

    /*
     * Save the video ID so that if the user
     * generates another video during processing,
     * the old answer will not overwrite the new video.
     */
    const requestVideoId =
        currentVideo.videoId;

    activeAIFeature = feature;

    resultsSection.classList.remove("hidden");

    resultLabel.textContent =
        info.label;

    resultTitle.textContent =
        info.title;

    resultContent.innerHTML = "";

    examContainer.classList.add("hidden");

    askBox.classList.add("hidden");

    setAILoading(
        "Preparing your learning material..."
    );

    resultsSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });

    try {
        const response =
            await fetch(
                `${API_BASE}/api/ai-feature`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify({
                        feature: feature,
                        transcript:
                            currentVideo.transcript
                    })
                }
            );

        const data =
            await safeJSON(response);

        if (
            !response.ok ||
            !data.success
        ) {
            throw new Error(
                data.error ||
                "Vidora AI could not generate this result. Please try again."
            );
        }

        /*
         * Do not display an old request's
         * answer inside a newly generated video.
         */
        if (
            !currentVideo ||
            currentVideo.videoId !== requestVideoId
        ) {
            return;
        }

        aiLoading.classList.add("hidden");

        resultContent.innerHTML =
            formatAIText(
                data.answer
            );

    } catch (error) {
        console.error(
            `${feature} error:`,
            error
        );

        aiLoading.classList.add("hidden");

        resultContent.innerHTML = `
            <div class="ai-error">
                <strong>Could not generate this result.</strong>
                <p>${escapeHTML(
                    error.message ||
                    "Please try again."
                )}</p>
            </div>
        `;

    } finally {
        activeAIFeature = null;
    }
}


/* =========================
   ASK AI
========================= */

function openAskMode() {
    if (!currentVideo) {
        showToast(
            "Generate a video first."
        );
        return;
    }

    resultsSection.classList.remove("hidden");

    resultLabel.textContent =
        "ASK AI";

    resultTitle.textContent =
        "Ask Anything About This Video";

    resultContent.innerHTML = "";

    examContainer.classList.add("hidden");

    askBox.classList.remove("hidden");

    aiLoading.classList.add("hidden");

    askInput.focus();

    resultsSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}


if (askButton) {
    askButton.addEventListener(
        "click",
        askAI
    );
}

if (askInput) {
    askInput.addEventListener(
        "keydown",
        event => {
            if (event.key === "Enter") {
                event.preventDefault();
                askAI();
            }
        }
    );
}


async function askAI() {
    if (!currentVideo) {
        showToast(
            "Generate a video first."
        );
        return;
    }

    if (isAskingAI) {
        return;
    }

    const question =
        askInput.value.trim();

    if (!question) {
        showToast(
            "Type your question first."
        );

        askInput.focus();
        return;
    }

    const requestVideoId =
        currentVideo.videoId;

    isAskingAI = true;

    askButton.disabled = true;

    askAnswer.innerHTML = `
        <div class="ask-loading">
            🧠 Vidora AI is understanding your question...
        </div>
    `;

    try {
        const response =
            await fetch(
                `${API_BASE}/api/ask`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify({
                        question:
                            question,
                        transcript:
                            currentVideo.transcript
                    })
                }
            );

        const data =
            await safeJSON(response);

        if (
            !response.ok ||
            !data.success
        ) {
            throw new Error(
                data.error ||
                "Vidora AI could not answer this question."
            );
        }

        /*
         * Prevent old video's answer from
         * appearing after New Generate.
         */
        if (
            !currentVideo ||
            currentVideo.videoId !== requestVideoId
        ) {
            return;
        }

        askAnswer.innerHTML =
            formatAIText(
                data.answer
            );

        askInput.value = "";

    } catch (error) {
        console.error(
            "Ask AI error:",
            error
        );

        askAnswer.innerHTML = `
            <div class="ai-error">
                <strong>Could not answer.</strong>
                <p>${escapeHTML(
                    error.message ||
                    "Please try again."
                )}</p>
            </div>
        `;

    } finally {
        isAskingAI = false;

        askButton.disabled = false;
    }
}


/* =========================
   NEW GENERATE
========================= */

if (newVideoButton) {
    newVideoButton.addEventListener(
        "click",
        resetForNewVideo
    );
}

function resetForNewVideo() {
    /*
     * Completely invalidate old video context.
     */
    currentVideo = null;

    activeAIFeature = null;

    isAskingAI = false;

    if (youtubeUrl) {
        youtubeUrl.value = "";
    }

    if (clearButton) {
        clearButton.style.display = "none";
    }

    if (inputError) {
        inputError.textContent = "";
    }

    if (videoSection) {
        videoSection.classList.add("hidden");
    }

    resetResults();

    if (youtubeUrl) {
        youtubeUrl.focus();
    }

    window.scrollTo({
        top: 0,
        behavior: "smooth"
    });

    showToast(
        "Ready for a new video."
    );
}


/* =========================
   RESET RESULTS
========================= */

function resetResults() {
    if (resultsSection) {
        resultsSection.classList.add("hidden");
    }

    if (resultContent) {
        resultContent.innerHTML = "";
    }

    if (askAnswer) {
        askAnswer.innerHTML = "";
    }

    if (askInput) {
        askInput.value = "";
    }

    if (askBox) {
        askBox.classList.add("hidden");
    }

    if (examContainer) {
        examContainer.classList.add("hidden");
    }

    if (aiLoading) {
        aiLoading.classList.add("hidden");
    }

    activeAIFeature = null;
}


/* =========================
   CLOSE RESULT
========================= */

if (resultClose) {
    resultClose.addEventListener(
        "click",
        () => {
            resultsSection.classList.add("hidden");
        }
    );
}


/* =========================
   HISTORY
========================= */

function saveToHistory(video) {
    let history = [];

    try {
        history =
            JSON.parse(
                localStorage.getItem(
                    "vidora-history"
                ) || "[]"
            );
    } catch {
        history = [];
    }

    history = history.filter(
        item =>
            item.videoId !==
            video.videoId
    );

    history.unshift({
        url: video.url,
        videoId: video.videoId,
        title: video.title,
        thumbnail: video.thumbnail,
        transcript: video.transcript,
        segments: video.segments,
        language: video.language,
        languageCode: video.languageCode,
        captionType: video.captionType,
        createdAt: video.createdAt
    });

    history =
        history.slice(0, 8);

    try {
        localStorage.setItem(
            "vidora-history",
            JSON.stringify(history)
        );
    } catch (error) {
        console.warn(
            "History could not be saved.",
            error
        );
    }

    renderHistory();
}


function getHistory() {
    try {
        return JSON.parse(
            localStorage.getItem(
                "vidora-history"
            ) || "[]"
        );
    } catch {
        return [];
    }
}


function renderHistory() {
    if (!historyList) return;

    const history =
        getHistory();

    if (!history.length) {
        historyList.innerHTML = `
            <div class="empty-history">
                <div class="empty-history-icon">🕘</div>
                <h3>No videos yet</h3>
                <p>Your generated videos will appear here.</p>
            </div>
        `;

        return;
    }

    historyList.innerHTML = "";

    history.forEach(
        (video, index) => {

            const item =
                document.createElement(
                    "button"
                );

            item.type = "button";

            item.className =
                "history-item";

            item.innerHTML = `
                <img
                    src="${escapeAttribute(
                        video.thumbnail
                    )}"
                    alt=""
                    loading="lazy"
                >

                <div class="history-item-info">
                    <strong>
                        ${escapeHTML(
                            video.title
                        )}
                    </strong>

                    <span>
                        ${formatDate(
                            video.createdAt
                        )}
                    </span>
                </div>

                <span class="history-arrow">
                    →
                </span>
            `;

            item.addEventListener(
                "click",
                () => loadHistoryVideo(index)
            );

            historyList.appendChild(item);
        }
    );
}


function loadHistoryVideo(index) {
    const history =
        getHistory();

    const video =
        history[index];

    if (!video) return;

    currentVideo = {
        ...video
    };

    youtubeUrl.value =
        video.url;

    clearButton.style.display =
        "block";

    videoThumbnail.src =
        video.thumbnail;

    videoTitle.textContent =
        video.title;

    videoStatus.textContent =
        "Loaded from history. Ready to learn.";

    videoSection.classList.remove(
        "hidden"
    );

    resetResults();

    closeHistory();

    showToast(
        "Video loaded from history."
    );

    videoSection.scrollIntoView({
        behavior: "smooth",
        block: "center"
    });
}


function formatDate(dateString) {
    if (!dateString) {
        return "";
    }

    const date =
        new Date(dateString);

    if (
        Number.isNaN(
            date.getTime()
        )
    ) {
        return "";
    }

    return date.toLocaleString(
        "en-IN",
        {
            day: "numeric",
            month: "short",
            year: "numeric",
            hour: "numeric",
            minute: "2-digit"
        }
    );
}


if (clearHistoryButton) {
    clearHistoryButton.addEventListener(
        "click",
        () => {

            localStorage.removeItem(
                "vidora-history"
            );

            renderHistory();

            showToast(
                "History cleared."
            );
        }
    );
}


/* =========================
   HISTORY DRAWER
========================= */

function openHistory() {
    if (!historyDrawer) return;

    historyDrawer.classList.add(
        "open"
    );

    drawerOverlay.classList.add(
        "show"
    );

    historyDrawer.setAttribute(
        "aria-hidden",
        "false"
    );
}


function closeHistory() {
    if (!historyDrawer) return;

    historyDrawer.classList.remove(
        "open"
    );

    drawerOverlay.classList.remove(
        "show"
    );

    historyDrawer.setAttribute(
        "aria-hidden",
        "true"
    );
}


if (historyButton) {
    historyButton.addEventListener(
        "click",
        openHistory
    );
}

if (historyClose) {
    historyClose.addEventListener(
        "click",
        closeHistory
    );
}

if (drawerOverlay) {
    drawerOverlay.addEventListener(
        "click",
        closeHistory
    );
}

renderHistory();


/* =========================
   SAFE TEXT FORMATTING
========================= */

function escapeHTML(text) {
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}


function escapeAttribute(text) {
    return escapeHTML(text);
}


function formatAIText(text) {
    if (!text) {
        return "<p>No result returned.</p>";
    }

    let safe =
        escapeHTML(text);

    /*
     * Headings
     */
    safe = safe.replace(
        /^### (.+)$/gm,
        "<h4>$1</h4>"
    );

    safe = safe.replace(
        /^## (.+)$/gm,
        "<h3>$1</h3>"
    );

    safe = safe.replace(
        /^# (.+)$/gm,
        "<h2>$1</h2>"
    );

    /*
     * Bold
     */
    safe = safe.replace(
        /\*\*(.+?)\*\*/g,
        "<strong>$1</strong>"
    );

    /*
     * Bullet points
     */
    safe = safe.replace(
        /^\s*[-*]\s+(.+)$/gm,
        "• $1"
    );

    /*
     * Numbered lists
     */
    safe = safe.replace(
        /^\s*(\d+)\.\s+(.+)$/gm,
        "<strong>$1.</strong> $2"
    );

    /*
     * Paragraph breaks
     */
    safe = safe.replace(
        /\n{2,}/g,
        "<br><br>"
    );

    /*
     * Single line breaks
     */
    safe = safe.replace(
        /\n/g,
        "<br>"
    );

    return safe;
}


/* =========================
   DELAY HELPER
========================= */

function delay(ms) {
    return new Promise(
        resolve =>
            setTimeout(
                resolve,
                ms
            )
    );
}


/* =========================
   KEYBOARD SHORTCUT
========================= */

if (youtubeUrl) {
    youtubeUrl.addEventListener(
        "keydown",
        event => {

            if (event.key === "Enter") {
                event.preventDefault();
                generateVideo();
            }

        }
    );
}
