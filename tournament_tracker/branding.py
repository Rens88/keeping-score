from __future__ import annotations

import base64
from html import escape
import json
from pathlib import Path
import random

import streamlit as st

CANGEROES_LOGO_URL = (
    "https://utrechtcangeroes.nl/wp-content/uploads/2025/05/"
    "logo_transparent-e1758371378168-100x0-c-default.webp"
)
CANGEROES_FALLBACK_HERO_URL = (
    "https://utrechtcangeroes.nl/wp-content/uploads/2025/08/"
    "IMG_9618-e1756283097966.jpg"
)


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_VIDEO_EXTENSIONS = {".mp4"}


def apply_cangeroes_theme() -> None:
    st.markdown(
        """
        <style>
            :root {
                --uc-orange: #ea580c;
                --uc-orange-dark: #c2410c;
                --uc-orange-soft: #fff3e8;
                --uc-orange-softer: #ffedd5;
                --uc-black: #111111;
                --uc-charcoal: #2f2f2f;
                --uc-white: #ffffff;
                --uc-surface: #fffdfa;
                --uc-border: #d6d3d1;
                --uc-muted: #4b5563;

                /* Backward-compatible aliases for existing class rules. */
                --uc-red: var(--uc-orange);
                --uc-red-dark: var(--uc-orange-dark);
                --uc-yellow: var(--uc-orange-softer);
                --uc-ivory: var(--uc-surface);
            }

            .stApp {
                background: linear-gradient(180deg, #ffffff 0%, #fff9f2 100%);
                color: var(--uc-black) !important;
            }

            /* Streamlit keeps a fixed top header. Add enough top offset so
               custom banners never render underneath it. */
            [data-testid="stAppViewContainer"] .main .block-container {
                padding-top: 4.6rem;
                padding-bottom: 1.6rem;
                padding-left: 1.1rem;
                padding-right: 1.1rem;
            }

            @media (max-width: 900px) {
                [data-testid="stAppViewContainer"] .main .block-container {
                    padding-top: 5.1rem;
                    padding-left: 0.85rem;
                    padding-right: 0.85rem;
                }
            }

            h1, h2, h3 {
                color: var(--uc-black);
                text-transform: uppercase;
                letter-spacing: 0.02em;
                font-weight: 900;
            }

            /* Main-area text contrast lock. */
            [data-testid="stAppViewContainer"] .main label,
            [data-testid="stAppViewContainer"] .main p,
            [data-testid="stAppViewContainer"] .main li,
            [data-testid="stAppViewContainer"] .main small,
            [data-testid="stAppViewContainer"] .main [data-testid="InputInstructions"],
            [data-testid="stAppViewContainer"] .main [data-testid="stWidgetLabel"],
            [data-testid="stAppViewContainer"] .main [data-testid="stWidgetLabel"] *,
            [data-testid="stAppViewContainer"] .main [data-testid="stCaptionContainer"] *,
            [data-testid="stAppViewContainer"] .main .stMarkdown * {
                color: var(--uc-black) !important;
                -webkit-text-fill-color: var(--uc-black) !important;
                opacity: 1 !important;
            }

            /* Inputs/selects/textareas always readable in both Streamlit modes. */
            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] > div,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] > div,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="textarea"] > div,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="base-input"] > div {
                background-color: var(--uc-white) !important;
                color: var(--uc-black) !important;
                border: 1px solid var(--uc-border) !important;
                box-shadow: none !important;
            }

            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] > div:focus-within,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] > div:focus-within,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="textarea"] > div:focus-within,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="base-input"] > div:focus-within {
                border-color: var(--uc-orange) !important;
                box-shadow: 0 0 0 2px rgba(234, 88, 12, 0.2) !important;
            }

            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] input,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] input,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="textarea"] textarea,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] *,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] button,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] svg,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] svg {
                color: var(--uc-black) !important;
                -webkit-text-fill-color: var(--uc-black) !important;
                opacity: 1 !important;
            }

            [data-testid="stAppViewContainer"] .main ::placeholder {
                color: var(--uc-muted) !important;
                opacity: 1 !important;
            }

            /* Dropdown menu portal colors. */
            div[role="listbox"],
            ul[role="listbox"] {
                background: var(--uc-white) !important;
                border: 1px solid var(--uc-border) !important;
            }

            div[role="option"],
            li[role="option"] {
                color: var(--uc-black) !important;
                background: var(--uc-white) !important;
            }

            div[role="option"][aria-selected="true"],
            li[role="option"][aria-selected="true"] {
                color: var(--uc-black) !important;
                background: var(--uc-orange-soft) !important;
            }

            /* Checkbox/radio controls with explicit readable contrast. */
            [data-testid="stAppViewContainer"] .main div[data-baseweb="checkbox"] > label > div:first-child,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="radio"] > div:first-child {
                background: var(--uc-white) !important;
                border-color: var(--uc-border) !important;
            }

            [data-testid="stAppViewContainer"] .main div[data-baseweb="checkbox"] svg,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="radio"] svg {
                color: var(--uc-orange-dark) !important;
                fill: var(--uc-orange-dark) !important;
            }

            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, #121212 0%, #1d1d1d 100%);
                border-right: 3px solid var(--uc-orange);
            }

            [data-testid="stSidebar"] * {
                color: #f7f7f7 !important;
            }

            [data-testid="stSidebar"] h2,
            [data-testid="stSidebar"] h3 {
                color: #ffd3b3 !important;
            }

            .stButton > button,
            .stDownloadButton > button,
            .stFormSubmitButton > button {
                background: var(--uc-white) !important;
                color: var(--uc-black) !important;
                border: 1px solid var(--uc-charcoal) !important;
                border-radius: 10px;
                font-weight: 700;
                box-shadow: none !important;
            }

            .stButton > button:hover,
            .stDownloadButton > button:hover,
            .stFormSubmitButton > button:hover {
                background: var(--uc-orange-soft) !important;
                color: var(--uc-black) !important;
                border-color: var(--uc-orange) !important;
            }

            .stButton > button:focus,
            .stDownloadButton > button:focus,
            .stFormSubmitButton > button:focus,
            .stButton > button:focus-visible,
            .stDownloadButton > button:focus-visible,
            .stFormSubmitButton > button:focus-visible {
                background: var(--uc-white) !important;
                color: var(--uc-black) !important;
                border-color: var(--uc-orange) !important;
                box-shadow: 0 0 0 2px rgba(234, 88, 12, 0.25) !important;
            }

            .stButton > button:disabled,
            .stDownloadButton > button:disabled,
            .stFormSubmitButton > button:disabled {
                background: #f3f4f6 !important;
                color: #6b7280 !important;
                border-color: #d1d5db !important;
            }

            .stButton > button span,
            .stDownloadButton > button span,
            .stFormSubmitButton > button span,
            .stButton > button:hover span,
            .stDownloadButton > button:hover span,
            .stFormSubmitButton > button:hover span,
            .stButton > button:disabled span,
            .stDownloadButton > button:disabled span,
            .stFormSubmitButton > button:disabled span {
                color: inherit !important;
            }

            /* Tabs contrast fix (unselected tabs were fading into background). */
            [data-baseweb="tab-list"] button[role="tab"] {
                color: var(--uc-muted) !important;
                border-bottom: 3px solid transparent !important;
                opacity: 1 !important;
            }

            [data-baseweb="tab-list"] button[role="tab"][aria-selected="true"] {
                color: var(--uc-orange-dark) !important;
                border-bottom-color: var(--uc-orange) !important;
                font-weight: 800 !important;
            }

            div[data-testid="stMetric"] {
                background: var(--uc-white);
                border-left: 4px solid var(--uc-orange);
                border-radius: 10px;
                padding: 0.5rem 0.75rem;
            }

            [data-testid="stAppViewContainer"] .main div[data-testid="stMetric"] label,
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetric"] p,
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetricValue"],
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetricDelta"],
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetricLabel"],
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetric"] span,
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetric"] div {
                color: var(--uc-black) !important;
                -webkit-text-fill-color: var(--uc-black) !important;
                opacity: 1 !important;
            }

            [data-testid="stAppViewContainer"] .main div[data-testid="stMetricLabel"] > div,
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetricValue"] > div,
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetricDelta"] > div {
                color: var(--uc-black) !important;
                -webkit-text-fill-color: var(--uc-black) !important;
            }

            /* Status/information messages: readable regardless of base theme. */
            [data-testid="stAlert"] {
                background: var(--uc-orange-soft) !important;
                border: 1px solid #fdba74 !important;
                border-left: 6px solid var(--uc-orange) !important;
                border-radius: 12px !important;
            }

            [data-testid="stAlert"] * {
                color: var(--uc-black) !important;
                -webkit-text-fill-color: var(--uc-black) !important;
                opacity: 1 !important;
            }

            [data-testid="stCode"] pre,
            code {
                color: var(--uc-black) !important;
                background: #fff7ed !important;
            }

            .uc-header-shell {
                background: var(--uc-white);
                border: 2px solid rgba(17,17,17,0.08);
                border-left: 8px solid var(--uc-orange);
                border-radius: 14px;
                padding: 0.6rem 0.8rem;
                margin-top: 0.2rem;
                margin-bottom: 0.8rem;
            }

            .uc-kicker {
                font-size: 0.82rem;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                color: #5a5a5a;
                font-weight: 700;
                margin-bottom: 0.2rem;
            }

            .uc-title {
                font-size: 1.55rem;
                line-height: 1.1;
                color: var(--uc-orange-dark);
                font-weight: 900;
                letter-spacing: 0.02em;
                text-transform: uppercase;
            }

            .uc-subtitle {
                margin-top: 0.35rem;
                color: #2b2b2b;
                font-weight: 600;
                font-size: 0.96rem;
            }

            .uc-decoration-wrap {
                margin-top: 1.2rem;
                padding-top: 0.6rem;
                border-top: 1px solid rgba(0, 0, 0, 0.12);
            }

            .uc-decoration-media {
                border-radius: 12px;
                overflow: hidden;
            }

            .uc-release-footer {
                margin-top: 0.55rem;
                padding-top: 0.45rem;
                border-top: 1px solid rgba(0, 0, 0, 0.1);
                display: grid;
                grid-template-columns: 1fr auto 1fr;
                align-items: center;
                column-gap: 0.5rem;
                font-size: 0.78rem;
                letter-spacing: 0.03em;
                color: var(--uc-muted);
            }

            .uc-release-left {
                text-align: left;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .uc-release-center {
                text-align: center;
                font-weight: 700;
                white-space: nowrap;
            }

            .uc-release-right {
                text-align: right;
                white-space: nowrap;
            }

            @media (max-width: 900px) {
                h1 {
                    font-size: 2rem;
                }

                h2 {
                    font-size: 1.35rem;
                }

                .uc-title {
                    font-size: 1.2rem;
                }

                .uc-subtitle {
                    font-size: 0.86rem;
                }

                .uc-release-footer {
                    font-size: 0.72rem;
                }

            }

            @media (max-width: 560px) {
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _media_folder_candidates() -> list[Path]:
    root = _project_root()
    return [
        root / "assets" / "deocration",
        root / "assets" / "decoration",
    ]


def _list_decoration_media() -> list[Path]:
    files: list[Path] = []
    for folder in _media_folder_candidates():
        if not folder.exists() or not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix in _IMAGE_EXTENSIONS or suffix in _VIDEO_EXTENSIONS:
                files.append(path)
    return files


def render_cangeroes_header() -> None:
    apply_cangeroes_theme()

    left, right = st.columns([1, 3])
    with left:
        st.image(CANGEROES_LOGO_URL, width=170)
    with right:
        st.markdown(
            """
            <div class="uc-header-shell">
                <div class="uc-kicker">Teamweekend 2026 / 2027</div>
                <div class="uc-title">Net geen Kampioen</div>
                <div class="uc-subtitle">Maar we hebben wel de #1 verslagen</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_autoplay_video(video_bytes: bytes) -> None:
    encoded = base64.b64encode(video_bytes).decode("ascii")
    st.markdown(
        f"""
        <video autoplay muted loop playsinline controls style="width:100%; border-radius:12px; display:block;">
            <source src="data:video/mp4;base64,{encoded}" type="video/mp4">
            Your browser does not support the video tag.
        </video>
        """,
        unsafe_allow_html=True,
    )


def _load_release_info() -> tuple[str, str, str]:
    release_path = _project_root() / "release_info.json"
    nickname = "No nickname"
    version = "v0.0.0"
    date = "-"

    try:
        raw = json.loads(release_path.read_text(encoding="utf-8"))
    except Exception:
        return nickname, version, date

    if not isinstance(raw, dict):
        return nickname, version, date

    nickname = str(raw.get("nickname") or nickname)
    version = str(raw.get("version") or version)
    date = str(raw.get("date") or date)
    return nickname, version, date


def _render_release_footer() -> None:
    nickname, version, date = _load_release_info()
    st.markdown(
        f"""
        <div class="uc-release-footer">
            <div class="uc-release-left">{escape(nickname)}</div>
            <div class="uc-release-center">{escape(version)}</div>
            <div class="uc-release-right">{escape(date)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_bottom_decoration() -> None:
    media_paths = _list_decoration_media()
    chosen: Path | None = random.choice(media_paths) if media_paths else None

    st.markdown(
        """
        <div class="uc-decoration-wrap">
            <div class="uc-decoration-media"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if chosen is None:
        st.image(CANGEROES_FALLBACK_HERO_URL, width="stretch")
    else:
        suffix = chosen.suffix.lower()
        if suffix in _VIDEO_EXTENSIONS:
            _render_autoplay_video(chosen.read_bytes())
        else:
            st.image(str(chosen), width="stretch")

    _render_release_footer()
