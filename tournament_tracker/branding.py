from __future__ import annotations

from pathlib import Path
import random
from typing import Optional

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
            }

            @media (max-width: 900px) {
                [data-testid="stAppViewContainer"] .main .block-container {
                    padding-top: 5.1rem;
                }
            }

            h1, h2, h3 {
                color: var(--uc-red);
                text-transform: uppercase;
                letter-spacing: 0.02em;
                font-weight: 900;
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
            .stDownloadButton > button {
                background: linear-gradient(180deg, var(--uc-red) 0%, var(--uc-red-dark) 100%);
                color: #ffffff;
                border: 1px solid #8f0f13;
                border-radius: 10px;
                font-weight: 700;
                box-shadow: 0 3px 8px rgba(0,0,0,0.2);
            }

            .stButton > button:hover,
            .stDownloadButton > button:hover {
                border-color: var(--uc-yellow);
                color: var(--uc-yellow);
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


def _list_header_media_files() -> list[Path]:
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


def _pick_random_header_media() -> Optional[Path]:
    files = _list_header_media_files()
    if not files:
        return None
    return random.choice(files)


def render_cangeroes_header() -> None:
    apply_cangeroes_theme()

    left, right = st.columns([1, 3])
    with left:
        st.image(CANGEROES_LOGO_URL, width=170)
    with right:
        st.markdown(
            """
            <div class="uc-header-shell">
                <div class="uc-kicker">Weekend Tournament</div>
                <div class="uc-title">Utrecht Cangeroes Style Tracker</div>
                <div class="uc-subtitle">Basketballen met plezier voor iedereen in Utrecht</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    media_path = _pick_random_header_media()
    if media_path is None:
        st.image(CANGEROES_FALLBACK_HERO_URL, use_container_width=True)
        st.caption("Tip: place images/mp4 in `assets/deocration` for random rotating header media.")
        return

    suffix = media_path.suffix.lower()
    if suffix in _VIDEO_EXTENSIONS:
        st.video(media_path.read_bytes())
    else:
        st.image(str(media_path), use_container_width=True)
