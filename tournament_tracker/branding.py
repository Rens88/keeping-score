from __future__ import annotations

import base64
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
                --uc-red: #d71f26;
                --uc-red-dark: #b3171d;
                --uc-yellow: #f6d138;
                --uc-black: #111111;
                --uc-ivory: #f8f5ef;
            }

            .stApp {
                background:
                    linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(248,245,239,1) 100%);
                color: var(--uc-black);
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
                color: var(--uc-red);
                text-transform: uppercase;
                letter-spacing: 0.02em;
                font-weight: 900;
            }

            /* Main-area body and form labels: lock readable contrast regardless
               of Streamlit light/dark mode setting. */
            [data-testid="stAppViewContainer"] .main label,
            [data-testid="stAppViewContainer"] .main p,
            [data-testid="stAppViewContainer"] .main li,
            [data-testid="stAppViewContainer"] .main small,
            [data-testid="stAppViewContainer"] .main [data-testid="InputInstructions"] {
                color: #1c1c1c !important;
            }

            /* Inputs/selects/textareas rendered with an always-readable surface. */
            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] > div,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] > div,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="textarea"] > div {
                background-color: #ffffff !important;
                color: #111111 !important;
                border: 1px solid #c7c7c7 !important;
                box-shadow: none !important;
            }

            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] input,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] input,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="textarea"] textarea,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] * {
                color: #111111 !important;
                -webkit-text-fill-color: #111111 !important;
            }

            [data-testid="stAppViewContainer"] .main ::placeholder {
                color: #6d6d6d !important;
                opacity: 1 !important;
            }

            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, #141414 0%, #1e1e1e 100%);
                border-right: 3px solid var(--uc-red);
            }

            [data-testid="stSidebar"] * {
                color: #f6f6f6;
            }

            [data-testid="stSidebar"] h2,
            [data-testid="stSidebar"] h3 {
                color: var(--uc-yellow);
            }

            .stButton > button,
            .stDownloadButton > button,
            .stFormSubmitButton > button {
                background: linear-gradient(180deg, var(--uc-red) 0%, var(--uc-red-dark) 100%);
                color: #ffffff !important;
                border: 1px solid #8f0f13;
                border-radius: 10px;
                font-weight: 700;
                box-shadow: 0 3px 8px rgba(0,0,0,0.2);
            }

            .stButton > button:hover,
            .stDownloadButton > button:hover,
            .stFormSubmitButton > button:hover {
                border-color: var(--uc-yellow);
                color: var(--uc-yellow) !important;
            }

            .stButton > button span,
            .stDownloadButton > button span,
            .stFormSubmitButton > button span {
                color: #ffffff !important;
            }

            .stButton > button:hover span,
            .stDownloadButton > button:hover span,
            .stFormSubmitButton > button:hover span {
                color: var(--uc-yellow) !important;
            }

            div[data-testid="stMetric"] {
                background: #ffffff;
                border-left: 4px solid var(--uc-red);
                border-radius: 10px;
                padding: 0.5rem 0.75rem;
            }

            .uc-header-shell {
                background: #ffffff;
                border: 2px solid rgba(17,17,17,0.08);
                border-left: 8px solid var(--uc-red);
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
                color: var(--uc-red);
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
                border-top: 1px solid rgba(0, 0, 0, 0.08);
            }

            .uc-decoration-media {
                border-radius: 12px;
                overflow: hidden;
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
        return

    suffix = chosen.suffix.lower()
    if suffix in _VIDEO_EXTENSIONS:
        _render_autoplay_video(chosen.read_bytes())
    else:
        st.image(str(chosen), width="stretch")
