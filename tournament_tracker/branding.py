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
                --uc-orange-dark: #9a3412;
                --uc-orange-soft: #fff3e8;
                --uc-orange-softer: #ffedd5;
                --uc-orange-ink: #7c2d12;
                --uc-black: #171717;
                --uc-charcoal: #292524;
                --uc-white: #ffffff;
                --uc-surface: #fff9f2;
                --uc-surface-strong: #ffffff;
                --uc-surface-muted: #fff6ee;
                --uc-border: #d3c4b5;
                --uc-border-strong: #8b7355;
                --uc-text: #171717;
                --uc-text-soft: #3f3227;
                --uc-muted: #625447;
                --uc-shadow: 0 16px 32px rgba(23, 23, 23, 0.08);
                --uc-shadow-soft: 0 8px 22px rgba(23, 23, 23, 0.05);

                /* Backward-compatible aliases for existing class rules. */
                --uc-red: var(--uc-orange);
                --uc-red-dark: var(--uc-orange-dark);
                --uc-yellow: var(--uc-orange-softer);
                --uc-ivory: var(--uc-surface);
            }

            :root,
            html,
            body,
            [data-testid="stAppViewContainer"] {
                color-scheme: light;
            }

            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(251, 146, 60, 0.18), transparent 28%),
                    radial-gradient(circle at top right, rgba(251, 191, 36, 0.1), transparent 24%),
                    linear-gradient(180deg, #fffdf9 0%, #fff6ec 48%, #fffaf5 100%);
                color: var(--uc-text) !important;
            }

            [data-testid="stAppViewContainer"] {
                background: transparent;
            }

            [data-testid="stHeader"] {
                background: rgba(255, 249, 242, 0.9) !important;
                backdrop-filter: blur(12px);
                border-bottom: 1px solid rgba(139, 115, 85, 0.18);
            }

            [data-testid="stToolbar"],
            [data-testid="stToolbar"] * {
                color: var(--uc-text) !important;
            }

            /* Streamlit keeps a fixed top header. Add enough top offset so
               custom banners never render underneath it. */
            [data-testid="stAppViewContainer"] .main .block-container {
                padding-top: 4.6rem;
                padding-bottom: 1.9rem;
                padding-left: 1.1rem;
                padding-right: 1.1rem;
                max-width: 1120px;
            }

            @media (max-width: 900px) {
                [data-testid="stAppViewContainer"] .main .block-container {
                    padding-top: 5.1rem;
                    padding-left: 0.85rem;
                    padding-right: 0.85rem;
                }
            }

            h1,
            h2,
            h3 {
                color: var(--uc-text) !important;
                text-transform: uppercase;
                letter-spacing: 0.025em;
                font-weight: 900;
                line-height: 1.08;
            }

            h1 {
                font-size: 2.35rem;
                margin-bottom: 0.4rem;
            }

            h2 {
                font-size: 1.5rem;
                margin-bottom: 0.3rem;
            }

            h3 {
                font-size: 1.18rem;
                margin-bottom: 0.2rem;
            }

            [data-testid="stDivider"] {
                margin: 1.15rem 0 !important;
            }

            hr {
                border-color: rgba(139, 115, 85, 0.24) !important;
            }

            [data-testid="stAppViewContainer"] .main a,
            [data-testid="stAppViewContainer"] .main a * {
                color: var(--uc-orange-dark) !important;
            }

            /* Main-area text contrast lock. */
            [data-testid="stAppViewContainer"] .main label,
            [data-testid="stAppViewContainer"] .main p,
            [data-testid="stAppViewContainer"] .main li,
            [data-testid="stAppViewContainer"] .main small,
            [data-testid="stAppViewContainer"] .main [data-testid="InputInstructions"],
            [data-testid="stAppViewContainer"] .main [data-testid="stWidgetLabel"],
            [data-testid="stAppViewContainer"] .main [data-testid="stWidgetLabel"] *,
            [data-testid="stAppViewContainer"] .main [data-testid="stMarkdownContainer"] p,
            [data-testid="stAppViewContainer"] .main [data-testid="stMarkdownContainer"] li,
            [data-testid="stAppViewContainer"] .main [data-testid="stMarkdownContainer"] strong,
            [data-testid="stAppViewContainer"] .main [data-testid="stMarkdownContainer"] span {
                color: var(--uc-text-soft) !important;
                -webkit-text-fill-color: var(--uc-text-soft) !important;
                opacity: 1 !important;
            }

            [data-testid="stAppViewContainer"] .main [data-testid="stCaptionContainer"],
            [data-testid="stAppViewContainer"] .main [data-testid="stCaptionContainer"] *,
            [data-testid="stAppViewContainer"] .main [data-testid="InputInstructions"],
            [data-testid="stAppViewContainer"] .main [data-testid="InputInstructions"] * {
                color: var(--uc-muted) !important;
                -webkit-text-fill-color: var(--uc-muted) !important;
                opacity: 1 !important;
                font-weight: 500 !important;
            }

            [data-testid="stAppViewContainer"] .main .stMarkdown code,
            [data-testid="stAppViewContainer"] .main .stCode code {
                color: var(--uc-orange-ink) !important;
                -webkit-text-fill-color: var(--uc-orange-ink) !important;
            }

            form,
            div[data-testid="stForm"] {
                background: rgba(255, 255, 255, 0.95);
                border: 1px solid rgba(139, 115, 85, 0.18);
                border-left: 6px solid var(--uc-orange);
                border-radius: 18px;
                padding: 1rem 1rem 0.45rem;
                box-shadow: var(--uc-shadow-soft);
            }

            [data-testid="stAppViewContainer"] .main div[data-testid="stAlert"],
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetric"],
            [data-testid="stAppViewContainer"] .main div[data-testid="stDataFrame"],
            [data-testid="stAppViewContainer"] .main div[data-testid="stFileUploader"],
            [data-testid="stAppViewContainer"] .main div[data-testid="stContainer"] {
                border-radius: 16px;
            }

            /* Inputs/selects/textareas always readable in both Streamlit modes. */
            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] > div,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] > div,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="textarea"] > div,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="base-input"] > div {
                background-color: var(--uc-surface-strong) !important;
                color: var(--uc-text) !important;
                border: 1px solid var(--uc-border) !important;
                border-radius: 12px !important;
                min-height: 2.85rem;
                box-shadow: 0 2px 10px rgba(23, 23, 23, 0.02) !important;
            }

            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] > div:focus-within,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] > div:focus-within,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="textarea"] > div:focus-within,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="base-input"] > div:focus-within {
                border-color: var(--uc-orange) !important;
                box-shadow: 0 0 0 3px rgba(234, 88, 12, 0.18) !important;
            }

            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] > div:has(input:disabled),
            [data-testid="stAppViewContainer"] .main div[data-baseweb="textarea"] > div:has(textarea:disabled),
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] > div[aria-disabled="true"] {
                background: #f3ede6 !important;
                border-color: #cdbba8 !important;
            }

            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] input,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] input:disabled,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] input,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="textarea"] textarea,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] *,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] button,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] svg,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] svg {
                color: var(--uc-text) !important;
                -webkit-text-fill-color: var(--uc-text) !important;
                opacity: 1 !important;
            }

            [data-testid="stAppViewContainer"] .main ::placeholder {
                color: var(--uc-muted) !important;
                opacity: 1 !important;
            }

            [data-testid="stAppViewContainer"] .main div[data-baseweb="tag"] {
                background: var(--uc-orange-soft) !important;
                border: 1px solid #fdba74 !important;
            }

            [data-testid="stAppViewContainer"] .main div[data-baseweb="tag"] * {
                color: var(--uc-orange-ink) !important;
                -webkit-text-fill-color: var(--uc-orange-ink) !important;
            }

            /* Dropdown menu portal colors. */
            div[role="listbox"],
            ul[role="listbox"] {
                background: var(--uc-white) !important;
                border: 1px solid var(--uc-border) !important;
                box-shadow: var(--uc-shadow-soft);
            }

            div[role="option"],
            li[role="option"] {
                color: var(--uc-text) !important;
                background: var(--uc-white) !important;
            }

            div[role="option"][aria-selected="true"],
            li[role="option"][aria-selected="true"] {
                color: var(--uc-text) !important;
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

            [data-testid="stAppViewContainer"] .main [data-testid="stToggle"] {
                background: rgba(255, 255, 255, 0.88);
                border: 1px solid rgba(139, 115, 85, 0.16);
                border-radius: 14px;
                padding: 0.25rem 0.8rem;
                box-shadow: var(--uc-shadow-soft);
            }

            [data-testid="stAppViewContainer"] .main [data-testid="stToggle"] * {
                color: var(--uc-text) !important;
                -webkit-text-fill-color: var(--uc-text) !important;
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

            [data-testid="stSidebar"] .stButton > button,
            [data-testid="stSidebar"] .stDownloadButton > button,
            [data-testid="stSidebar"] .stFormSubmitButton > button {
                background: rgba(255, 255, 255, 0.08) !important;
                color: #f8fafc !important;
                border: 1px solid rgba(255, 255, 255, 0.16) !important;
            }

            [data-testid="stSidebar"] .stButton > button:hover,
            [data-testid="stSidebar"] .stDownloadButton > button:hover,
            [data-testid="stSidebar"] .stFormSubmitButton > button:hover {
                background: rgba(255, 211, 179, 0.14) !important;
                border-color: #ffb98a !important;
            }

            [data-testid="stSidebar"] .stButton > button span,
            [data-testid="stSidebar"] .stDownloadButton > button span,
            [data-testid="stSidebar"] .stFormSubmitButton > button span {
                color: inherit !important;
            }

            .stButton,
            .stDownloadButton,
            .stFormSubmitButton {
                overflow: visible !important;
            }

            .stButton > button,
            .stDownloadButton > button,
            .stFormSubmitButton > button {
                background: var(--uc-white) !important;
                color: var(--uc-text) !important;
                border: 1px solid var(--uc-border-strong) !important;
                border-radius: 12px;
                min-height: 2.85rem;
                padding: 0.55rem 1rem;
                font-weight: 800;
                box-shadow: var(--uc-shadow-soft);
            }

            .stButton > button:hover,
            .stDownloadButton > button:hover,
            .stFormSubmitButton > button:hover {
                background: var(--uc-orange-soft) !important;
                color: var(--uc-text) !important;
                border-color: var(--uc-orange) !important;
                transform: translateY(-1px);
            }

            .stButton > button:focus,
            .stDownloadButton > button:focus,
            .stFormSubmitButton > button:focus,
            .stButton > button:focus-visible,
            .stDownloadButton > button:focus-visible,
            .stFormSubmitButton > button:focus-visible {
                background: var(--uc-white) !important;
                color: var(--uc-text) !important;
                border-color: var(--uc-orange) !important;
                box-shadow: 0 0 0 3px rgba(234, 88, 12, 0.18) !important;
            }

            .stButton > button[kind="primary"],
            .stDownloadButton > button[kind="primary"],
            .stFormSubmitButton > button[kind="primary"] {
                background: linear-gradient(180deg, #f97316 0%, #ea580c 100%) !important;
                color: var(--uc-white) !important;
                border-color: #9a3412 !important;
            }

            .stButton > button[kind="primary"]:hover,
            .stDownloadButton > button[kind="primary"]:hover,
            .stFormSubmitButton > button[kind="primary"]:hover,
            .stButton > button[kind="primary"]:focus,
            .stDownloadButton > button[kind="primary"]:focus,
            .stFormSubmitButton > button[kind="primary"]:focus,
            .stButton > button[kind="primary"]:focus-visible,
            .stDownloadButton > button[kind="primary"]:focus-visible,
            .stFormSubmitButton > button[kind="primary"]:focus-visible {
                background: linear-gradient(180deg, #fb923c 0%, #ea580c 100%) !important;
                color: var(--uc-white) !important;
                border-color: #7c2d12 !important;
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
            .stFormSubmitButton > button:disabled span,
            .stButton > button[kind="primary"] span,
            .stDownloadButton > button[kind="primary"] span,
            .stFormSubmitButton > button[kind="primary"] span {
                color: inherit !important;
            }

            /* Tabs contrast fix (unselected tabs were fading into background). */
            [data-baseweb="tab-list"] {
                gap: 0.4rem;
                background: rgba(255, 243, 232, 0.8);
                border: 1px solid rgba(139, 115, 85, 0.14);
                border-radius: 16px;
                padding: 0.35rem;
                box-shadow: var(--uc-shadow-soft);
            }

            [data-baseweb="tab-list"] button[role="tab"] {
                color: var(--uc-muted) !important;
                background: transparent !important;
                border-radius: 10px !important;
                border-bottom: 0 !important;
                opacity: 1 !important;
                padding: 0.55rem 0.9rem !important;
                font-weight: 700 !important;
            }

            [data-baseweb="tab-list"] button[role="tab"][aria-selected="true"] {
                color: var(--uc-orange-ink) !important;
                background: var(--uc-white) !important;
                font-weight: 800 !important;
                box-shadow: var(--uc-shadow-soft);
            }

            div[data-testid="stMetric"] {
                background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(255, 246, 238, 0.96) 100%);
                border: 1px solid rgba(139, 115, 85, 0.16);
                border-left: 6px solid var(--uc-orange);
                border-radius: 16px;
                padding: 0.75rem 0.9rem;
                box-shadow: var(--uc-shadow-soft);
            }

            [data-testid="stAppViewContainer"] .main div[data-testid="stMetric"] label,
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetric"] p,
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetricValue"],
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetricDelta"],
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetricLabel"],
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetric"] span,
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetric"] div {
                color: var(--uc-text) !important;
                -webkit-text-fill-color: var(--uc-text) !important;
                opacity: 1 !important;
            }

            [data-testid="stAppViewContainer"] .main div[data-testid="stMetricLabel"] > div,
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetricValue"] > div,
            [data-testid="stAppViewContainer"] .main div[data-testid="stMetricDelta"] > div {
                color: var(--uc-text) !important;
                -webkit-text-fill-color: var(--uc-text) !important;
            }

            [data-testid="stAppViewContainer"] .main div[data-testid="stMetricLabel"] {
                font-weight: 700 !important;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            [data-testid="stAppViewContainer"] .main div[data-testid="stMetricValue"] {
                font-weight: 900 !important;
            }

            /* Status/information messages: readable regardless of base theme. */
            [data-testid="stAlert"] {
                background: linear-gradient(180deg, rgba(255, 249, 242, 0.98) 0%, rgba(255, 239, 220, 0.98) 100%) !important;
                border: 1px solid #fdba74 !important;
                border-left: 6px solid var(--uc-orange) !important;
                border-radius: 14px !important;
                box-shadow: var(--uc-shadow-soft);
            }

            [data-testid="stAlert"] * {
                color: var(--uc-text) !important;
                -webkit-text-fill-color: var(--uc-text) !important;
                opacity: 1 !important;
            }

            [data-testid="stFileUploader"] {
                background: rgba(255, 255, 255, 0.9);
                border: 1px solid rgba(139, 115, 85, 0.16);
                padding: 0.5rem;
                box-shadow: var(--uc-shadow-soft);
            }

            [data-testid="stFileUploaderDropzone"] {
                background: linear-gradient(180deg, #fffdfa 0%, #fff5ea 100%) !important;
                border: 2px dashed #f59e0b !important;
                border-radius: 16px !important;
            }

            [data-testid="stFileUploaderDropzone"] * {
                color: var(--uc-text) !important;
                -webkit-text-fill-color: var(--uc-text) !important;
            }

            [data-testid="stDataFrame"] {
                background: var(--uc-white);
                border: 1px solid rgba(139, 115, 85, 0.18);
                border-radius: 16px;
                overflow: hidden;
                box-shadow: var(--uc-shadow-soft);
                --gdg-font-family: "Source Sans Pro", sans-serif;
                --gdg-editor-font-size: 0.96rem;
                --gdg-rounding-radius: 8px;
                --gdg-bg-cell: var(--uc-white);
                --gdg-bg-header: #1f2937;
                --gdg-bg-header-has-focus: #111827;
                --gdg-border-color: #d3c4b5;
                --gdg-text-dark: #111111;
                --gdg-text-medium: #374151;
                --gdg-text-light: #6b7280;
                --gdg-text-group-header: #f9fafb;
                --gdg-accent-color: var(--uc-orange);
                --gdg-accent-fg: var(--uc-white);
                --gdg-accent-light: #ffedd5;
                --gdg-bg-bubble: #fff3e8;
                --gdg-link-color: var(--uc-orange-dark);
            }

            [data-testid="stCode"] pre,
            code {
                color: var(--uc-text) !important;
                background: #fff7ed !important;
            }

            .uc-header-shell {
                background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(255, 244, 233, 0.98) 100%);
                border: 1px solid rgba(17, 17, 17, 0.08);
                border-left: 8px solid var(--uc-orange);
                border-radius: 18px;
                box-shadow: var(--uc-shadow);
                padding: 0.85rem 0.95rem;
                margin-top: 0.2rem;
                margin-bottom: 1rem;
            }

            .uc-kicker {
                font-size: 0.82rem;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                color: var(--uc-muted);
                font-weight: 700;
                margin-bottom: 0.2rem;
            }

            .uc-title {
                font-size: 1.55rem;
                line-height: 1.1;
                color: var(--uc-orange-dark) !important;
                font-weight: 900;
                letter-spacing: 0.02em;
                text-transform: uppercase;
            }

            .uc-subtitle {
                margin-top: 0.35rem;
                color: var(--uc-text-soft) !important;
                font-weight: 600;
                font-size: 0.96rem;
            }

            .uc-page-intro {
                background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(255, 244, 233, 0.98) 100%);
                border: 1px solid rgba(139, 115, 85, 0.18);
                border-left: 8px solid var(--uc-orange);
                border-radius: 18px;
                box-shadow: var(--uc-shadow);
                padding: 0.95rem 1rem;
                margin: 0 0 1rem 0;
            }

            .uc-page-eyebrow {
                font-size: 0.78rem;
                letter-spacing: 0.1em;
                text-transform: uppercase;
                font-weight: 800;
                color: var(--uc-muted) !important;
                margin-bottom: 0.3rem;
            }

            .uc-page-heading {
                margin: 0;
                font-size: 2.05rem;
                line-height: 1.02;
                color: var(--uc-text) !important;
                font-weight: 900;
                letter-spacing: 0.02em;
                text-transform: uppercase;
            }

            .uc-page-copy {
                margin-top: 0.45rem;
                color: var(--uc-text-soft) !important;
                font-size: 1rem;
                font-weight: 600;
                max-width: 58rem;
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

                .uc-page-heading {
                    font-size: 1.6rem;
                }

                .uc-page-copy {
                    font-size: 0.94rem;
                }

                .uc-release-footer {
                    font-size: 0.72rem;
                }

            }

            @media (max-width: 560px) {
                form,
                div[data-testid="stForm"],
                .uc-page-intro,
                .uc-header-shell {
                    padding-left: 0.85rem;
                    padding-right: 0.85rem;
                }
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


def render_page_intro(title: str, description: str | None = None, eyebrow: str | None = None) -> None:
    eyebrow_html = f'<div class="uc-page-eyebrow">{escape(eyebrow)}</div>' if eyebrow else ""
    description_html = f'<div class="uc-page-copy">{escape(description)}</div>' if description else ""
    st.markdown(
        f"""
        <section class="uc-page-intro">
            {eyebrow_html}
            <h1 class="uc-page-heading">{escape(title)}</h1>
            {description_html}
        </section>
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
