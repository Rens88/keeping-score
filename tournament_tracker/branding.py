from __future__ import annotations

import base64
from html import escape
import json
import mimetypes
from pathlib import Path
import random
from textwrap import dedent

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
        dedent(
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
                --uc-disabled-bg: #eee4da;
                --uc-disabled-text: #867261;
                --uc-success: #15803d;
                --uc-success-bg: #ecfdf3;
                --uc-info: #2563eb;
                --uc-info-bg: #eff6ff;
                --uc-danger: #dc2626;
                --uc-danger-bg: #fef2f2;
                --uc-neutral: #94a3b8;
                --uc-neutral-bg: #f8fafc;
                --uc-hover-bg: #ead8c5;
                --uc-hover-text: #2f241b;
                --uc-panel-header-bg: #e6d2bf;
                --uc-panel-header-open-bg: #dcc4ac;
                --uc-table-bg: #ffffff;
                --uc-table-header-bg: #f1f5f9;
                --uc-table-header-focus: #e2e8f0;
                --uc-table-text: #171717;
                --uc-table-text-muted: #475569;
                --uc-table-group-header: #171717;
                --uc-shadow: 0 12px 28px rgba(23, 23, 23, 0.08);
                --uc-shadow-soft: 0 6px 18px rgba(23, 23, 23, 0.05);

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

            @media (prefers-color-scheme: dark) {
                :root,
                html,
                body,
                [data-testid="stAppViewContainer"] {
                    color-scheme: dark;
                }

                :root {
                    --uc-surface: #15110f;
                    --uc-surface-strong: #1d1815;
                    --uc-surface-muted: #27201b;
                    --uc-border: #5d4737;
                    --uc-border-strong: #a47653;
                    --uc-text: #f8f4ef;
                    --uc-text-soft: #f2e6da;
                    --uc-muted: #e0cdbb;
                    --uc-disabled-bg: #332a24;
                    --uc-disabled-text: #bca48f;
                    --uc-success: #4ade80;
                    --uc-success-bg: #13291b;
                    --uc-info: #60a5fa;
                    --uc-info-bg: #11243b;
                    --uc-danger: #f87171;
                    --uc-danger-bg: #32171a;
                    --uc-neutral: #cbd5e1;
                    --uc-neutral-bg: #1d2733;
                    --uc-hover-bg: #362922;
                    --uc-hover-text: #f8f4ef;
                    --uc-panel-header-bg: #2d231d;
                    --uc-panel-header-open-bg: #372a22;
                    --uc-table-bg: #1d1815;
                    --uc-table-header-bg: #2b241f;
                    --uc-table-header-focus: #382e27;
                    --uc-table-text: #f8f4ef;
                    --uc-table-text-muted: #d7c3b0;
                    --uc-table-group-header: #fff7ef;
                    --uc-shadow: 0 14px 32px rgba(0, 0, 0, 0.34);
                    --uc-shadow-soft: 0 8px 24px rgba(0, 0, 0, 0.24);
                }
            }

            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(251, 146, 60, 0.18), transparent 28%),
                    radial-gradient(circle at top right, rgba(251, 191, 36, 0.1), transparent 24%),
                    linear-gradient(180deg, #fffdf9 0%, #fff6ec 48%, #fffaf5 100%);
                color: var(--uc-text) !important;
            }

            @media (prefers-color-scheme: dark) {
                .stApp {
                    background:
                        radial-gradient(circle at top left, rgba(251, 146, 60, 0.14), transparent 24%),
                        radial-gradient(circle at top right, rgba(234, 88, 12, 0.12), transparent 22%),
                        linear-gradient(180deg, #0f0c0a 0%, #15110f 48%, #1a1511 100%);
                }
            }

            [data-testid="stAppViewContainer"] {
                background: transparent;
            }

            [data-testid="stHeader"] {
                background: rgba(255, 249, 242, 0.92) !important;
                backdrop-filter: blur(12px);
                border-bottom: 1px solid rgba(139, 115, 85, 0.18);
            }

            @media (prefers-color-scheme: dark) {
                [data-testid="stHeader"] {
                    background: rgba(17, 13, 11, 0.94) !important;
                    border-bottom-color: rgba(164, 118, 83, 0.22);
                }
            }

            [data-testid="stToolbar"],
            [data-testid="stToolbar"] * {
                color: var(--uc-text) !important;
            }

            /* Streamlit keeps a fixed top header. Add enough top offset so
               custom banners never render underneath it. */
            [data-testid="stAppViewContainer"] .main .block-container {
                padding-top: 4.2rem;
                padding-bottom: 1.9rem;
                padding-left: 1.1rem;
                padding-right: 1.1rem;
                max-width: 1120px;
            }

            @media (max-width: 900px) {
                [data-testid="stAppViewContainer"] .main .block-container {
                    padding-top: 4.65rem;
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
            [data-testid="stAppViewContainer"] .main p,
            [data-testid="stAppViewContainer"] .main li,
            [data-testid="stAppViewContainer"] .main small,
            [data-testid="stAppViewContainer"] .main [data-testid="stMarkdownContainer"] p,
            [data-testid="stAppViewContainer"] .main [data-testid="stMarkdownContainer"] li,
            [data-testid="stAppViewContainer"] .main [data-testid="stMarkdownContainer"] strong,
            [data-testid="stAppViewContainer"] .main [data-testid="stMarkdownContainer"] span {
                color: var(--uc-text-soft) !important;
                -webkit-text-fill-color: var(--uc-text-soft) !important;
                opacity: 1 !important;
            }

            [data-testid="stAppViewContainer"] .main label,
            [data-testid="stAppViewContainer"] .main [data-testid="stWidgetLabel"],
            [data-testid="stAppViewContainer"] .main [data-testid="stWidgetLabel"] *,
            [data-testid="stAppViewContainer"] .main [data-testid="stWidgetLabel"] label,
            [data-testid="stAppViewContainer"] .main [data-testid="stWidgetLabel"] p,
            [data-testid="stAppViewContainer"] .main [data-testid="stWidgetLabel"] span {
                color: var(--uc-text) !important;
                -webkit-text-fill-color: var(--uc-text) !important;
                opacity: 1 !important;
                font-weight: 700 !important;
                line-height: 1.35 !important;
            }

            [data-testid="stAppViewContainer"] .main [data-testid="stWidgetLabel"] p {
                font-size: 1rem !important;
            }

            [data-testid="stAppViewContainer"] .main [data-testid="stCaptionContainer"],
            [data-testid="stAppViewContainer"] .main [data-testid="stCaptionContainer"] *,
            [data-testid="stAppViewContainer"] .main [data-testid="InputInstructions"],
            [data-testid="stAppViewContainer"] .main [data-testid="InputInstructions"] * {
                color: var(--uc-text-soft) !important;
                -webkit-text-fill-color: var(--uc-text-soft) !important;
                opacity: 1 !important;
                font-weight: 600 !important;
                line-height: 1.5 !important;
            }

            [data-testid="stAppViewContainer"] .main .stMarkdown code,
            [data-testid="stAppViewContainer"] .main .stCode code {
                color: var(--uc-orange-ink) !important;
                -webkit-text-fill-color: var(--uc-orange-ink) !important;
            }

            form,
            div[data-testid="stForm"] {
                background: var(--uc-surface-strong);
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
            [data-testid="stAppViewContainer"] .main div[data-baseweb="base-input"] > div,
            [data-testid="stSelectbox"] [data-baseweb="select"] > div,
            [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
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
            [data-testid="stAppViewContainer"] .main div[data-baseweb="base-input"] > div:focus-within,
            [data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within,
            [data-testid="stMultiSelect"] [data-baseweb="select"] > div:focus-within {
                border-color: var(--uc-orange) !important;
                box-shadow: 0 0 0 3px rgba(234, 88, 12, 0.18) !important;
            }

            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] > div:has(input:disabled),
            [data-testid="stAppViewContainer"] .main div[data-baseweb="textarea"] > div:has(textarea:disabled),
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] > div[aria-disabled="true"] {
                background: var(--uc-disabled-bg) !important;
                border-color: var(--uc-border) !important;
            }

            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] input,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] input:disabled,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] input,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="textarea"] textarea,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] *,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] button,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="input"] svg,
            [data-testid="stAppViewContainer"] .main div[data-baseweb="select"] svg,
            [data-testid="stSelectbox"] [data-baseweb="select"] *,
            [data-testid="stMultiSelect"] [data-baseweb="select"] * {
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
                background: var(--uc-surface-strong) !important;
                border: 1px solid var(--uc-border) !important;
                box-shadow: var(--uc-shadow-soft);
            }

            div[role="option"],
            li[role="option"] {
                color: var(--uc-text) !important;
                background: var(--uc-surface-strong) !important;
            }

            div[role="option"][aria-selected="true"],
            li[role="option"][aria-selected="true"] {
                color: var(--uc-text) !important;
                background: var(--uc-surface-muted) !important;
            }

            div[role="option"]:hover,
            li[role="option"]:hover {
                background: rgba(234, 88, 12, 0.14) !important;
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

            [data-testid="stCheckbox"] [data-testid="stWidgetLabel"],
            [data-testid="stCheckbox"] [data-testid="stWidgetLabel"] *,
            [data-testid="stToggle"] [data-testid="stWidgetLabel"],
            [data-testid="stToggle"] [data-testid="stWidgetLabel"] * {
                color: var(--uc-text-soft) !important;
                -webkit-text-fill-color: var(--uc-text-soft) !important;
                opacity: 1 !important;
                font-weight: 700 !important;
            }

            [data-testid="stAppViewContainer"] .main [data-testid="stToggle"] {
                background: var(--uc-surface-strong);
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
                background: var(--uc-surface-strong) !important;
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
                background: var(--uc-hover-bg) !important;
                color: var(--uc-hover-text) !important;
                border-color: var(--uc-orange) !important;
                transform: translateY(-1px);
            }

            .stButton > button:focus,
            .stDownloadButton > button:focus,
            .stFormSubmitButton > button:focus,
            .stButton > button:focus-visible,
            .stDownloadButton > button:focus-visible,
            .stFormSubmitButton > button:focus-visible {
                background: var(--uc-surface-strong) !important;
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
                background: var(--uc-disabled-bg) !important;
                color: var(--uc-disabled-text) !important;
                border-color: var(--uc-border) !important;
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
                background: rgba(255, 243, 232, 0.92);
                border: 1px solid rgba(139, 115, 85, 0.2);
                border-radius: 16px;
                padding: 0.35rem;
                box-shadow: var(--uc-shadow-soft);
            }

            [data-baseweb="tab-list"] button[role="tab"] {
                color: var(--uc-orange-dark) !important;
                background: #f1dfcc !important;
                border: 1px solid rgba(139, 115, 85, 0.28) !important;
                border-radius: 10px !important;
                border-bottom: 0 !important;
                opacity: 1 !important;
                padding: 0.55rem 0.9rem !important;
                font-weight: 800 !important;
            }

            [data-baseweb="tab-list"] button[role="tab"]:hover {
                color: var(--uc-orange-dark) !important;
                background: #ead4be !important;
            }

            [data-baseweb="tab-list"] button[role="tab"][aria-selected="true"] {
                color: var(--uc-orange-ink) !important;
                background: var(--uc-white) !important;
                font-weight: 800 !important;
                box-shadow: var(--uc-shadow-soft);
                border: 1px solid rgba(234, 88, 12, 0.22) !important;
            }

            div[data-testid="stMetric"] {
                background: linear-gradient(180deg, var(--uc-surface-strong) 0%, var(--uc-surface-muted) 100%);
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
                background: linear-gradient(180deg, var(--uc-surface-strong) 0%, var(--uc-surface-muted) 100%) !important;
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

            [data-testid="stExpander"] {
                border-radius: 16px;
                overflow: hidden;
            }

            [data-testid="stExpander"] details {
                background: var(--uc-surface-strong) !important;
                border: 1px solid rgba(139, 115, 85, 0.18) !important;
                border-radius: 16px !important;
                box-shadow: var(--uc-shadow-soft);
            }

            [data-testid="stExpander"] summary {
                background: var(--uc-panel-header-bg) !important;
                color: var(--uc-text) !important;
                border-radius: 16px !important;
            }

            [data-testid="stExpander"] summary:hover {
                background: var(--uc-hover-bg) !important;
                color: var(--uc-hover-text) !important;
            }

            [data-testid="stExpander"] details[open] > summary {
                background: var(--uc-panel-header-open-bg) !important;
                color: var(--uc-text) !important;
                border-bottom-left-radius: 0 !important;
                border-bottom-right-radius: 0 !important;
                border-bottom: 1px solid rgba(139, 115, 85, 0.18) !important;
            }

            [data-testid="stExpander"] summary *,
            [data-testid="stExpander"] summary:hover *,
            [data-testid="stExpander"] details[open] > summary * {
                color: inherit !important;
                -webkit-text-fill-color: inherit !important;
            }

            [data-testid="stExpanderDetails"] {
                background: var(--uc-surface-strong) !important;
                color: var(--uc-text) !important;
            }

            [data-testid="stExpanderDetails"] * {
                color: inherit;
            }

            [data-testid="stFileUploader"] {
                background: var(--uc-surface-strong);
                border: 1px solid rgba(139, 115, 85, 0.16);
                padding: 0.5rem;
                box-shadow: var(--uc-shadow-soft);
            }

            [data-testid="stFileUploaderDropzone"] {
                background: linear-gradient(180deg, var(--uc-surface-strong) 0%, var(--uc-surface-muted) 100%) !important;
                border: 2px dashed #f59e0b !important;
                border-radius: 16px !important;
            }

            [data-testid="stFileUploaderDropzone"] * {
                color: var(--uc-text) !important;
                -webkit-text-fill-color: var(--uc-text) !important;
            }

            [data-testid="stFileUploaderDropzone"] button,
            [data-testid="stFileUploaderDropzone"] button:hover,
            [data-testid="stFileUploaderDropzone"] button:focus,
            [data-testid="stFileUploaderDropzone"] button:focus-visible {
                background: var(--uc-hover-bg) !important;
                color: var(--uc-hover-text) !important;
                border: 1px solid var(--uc-border-strong) !important;
                box-shadow: none !important;
            }

            [data-testid="stFileUploaderDropzone"] button *,
            [data-testid="stFileUploaderDropzone"] button:hover *,
            [data-testid="stFileUploaderDropzone"] button:focus *,
            [data-testid="stFileUploaderDropzone"] button:focus-visible * {
                color: inherit !important;
                -webkit-text-fill-color: inherit !important;
            }

            [data-testid="stFileUploaderDropzoneInstructions"],
            [data-testid="stFileUploaderDropzoneInstructions"] * {
                color: var(--uc-text-soft) !important;
                -webkit-text-fill-color: var(--uc-text-soft) !important;
                opacity: 1 !important;
                font-weight: 600 !important;
            }

            [data-testid="stDataFrame"] {
                background: var(--uc-table-bg);
                border: 1px solid rgba(139, 115, 85, 0.18);
                border-radius: 16px;
                overflow: hidden;
                box-shadow: var(--uc-shadow-soft);
                --gdg-font-family: "Source Sans Pro", sans-serif;
                --gdg-editor-font-size: 0.96rem;
                --gdg-rounding-radius: 8px;
                --gdg-bg-cell: var(--uc-table-bg);
                --gdg-bg-header: var(--uc-table-header-bg);
                --gdg-bg-header-has-focus: var(--uc-table-header-focus);
                --gdg-border-color: var(--uc-border);
                --gdg-text-dark: var(--uc-table-text);
                --gdg-text-medium: var(--uc-table-text-muted);
                --gdg-text-light: var(--uc-muted);
                --gdg-text-group-header: var(--uc-table-group-header);
                --gdg-accent-color: var(--uc-orange);
                --gdg-accent-fg: var(--uc-white);
                --gdg-accent-light: var(--uc-orange-soft);
                --gdg-bg-bubble: var(--uc-surface-muted);
                --gdg-link-color: var(--uc-orange-dark);
            }

            [data-testid="stCode"] pre,
            code {
                color: var(--uc-text) !important;
                background: var(--uc-surface-muted) !important;
            }

            .uc-hero {
                display: grid;
                grid-template-columns: 6rem minmax(0, 1fr);
                gap: 0.8rem;
                align-items: center;
                margin-bottom: 0.95rem;
            }

            .uc-hero-logo-wrap {
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--uc-surface-strong);
                border: 1px solid rgba(139, 115, 85, 0.18);
                border-radius: 18px;
                padding: 0.45rem;
                box-shadow: var(--uc-shadow-soft);
            }

            .uc-hero-logo {
                width: 100%;
                max-width: 5rem;
                height: auto;
                display: block;
            }

            .uc-header-shell {
                background: linear-gradient(180deg, var(--uc-surface-strong) 0%, var(--uc-surface-muted) 100%);
                border: 1px solid rgba(139, 115, 85, 0.18);
                border-left: 8px solid var(--uc-orange);
                border-radius: 18px;
                box-shadow: var(--uc-shadow-soft);
                padding: 0.85rem 0.95rem;
                margin: 0;
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
                background: linear-gradient(180deg, var(--uc-surface-strong) 0%, var(--uc-surface-muted) 100%);
                border: 1px solid rgba(139, 115, 85, 0.18);
                border-left: 8px solid var(--uc-orange);
                border-radius: 18px;
                box-shadow: var(--uc-shadow-soft);
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

            .uc-field-label-block {
                margin: 0.15rem 0 0.3rem 0;
            }

            .uc-field-label {
                color: var(--uc-text) !important;
                font-size: 1rem;
                font-weight: 800;
                line-height: 1.35;
                letter-spacing: 0.01em;
            }

            .uc-field-helper {
                margin-top: 0.14rem;
                color: var(--uc-text-soft) !important;
                font-size: 0.92rem;
                font-weight: 600;
                line-height: 1.45;
            }

            .uc-decoration-wrap {
                margin-top: 1.2rem;
                padding-top: 0.6rem;
                border-top: 1px solid rgba(0, 0, 0, 0.12);
            }

            .uc-decoration-media {
                border-radius: 12px;
                overflow: hidden;
                background: var(--uc-surface-strong);
                box-shadow: var(--uc-shadow-soft);
            }

            .uc-bottom-media {
                width: 100%;
                max-height: 32rem;
                object-fit: cover;
                display: block;
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
                    font-size: 1.08rem;
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

                .uc-bottom-media {
                    max-height: 24rem;
                }

            }

            @media (max-width: 560px) {
                .uc-hero {
                    grid-template-columns: 4.6rem minmax(0, 1fr);
                    gap: 0.65rem;
                    align-items: stretch;
                }

                .uc-hero-logo {
                    max-width: 3.9rem;
                }

                .uc-bottom-media {
                    max-height: 20rem;
                }

                form,
                div[data-testid="stForm"],
                .uc-page-intro,
                .uc-header-shell,
                .uc-hero-logo-wrap {
                    padding-left: 0.85rem;
                    padding-right: 0.85rem;
                }
            }
        </style>
        """
        ).strip(),
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


def render_html_block(markup: str) -> None:
    cleaned = dedent(markup).strip()
    html_renderer = getattr(st, "html", None)
    if callable(html_renderer):
        html_renderer(cleaned)
        return
    st.markdown(cleaned, unsafe_allow_html=True)


def render_cangeroes_header() -> None:
    apply_cangeroes_theme()

    render_html_block(
        f"""
<div class="uc-hero">
    <div class="uc-hero-logo-wrap">
        <img class="uc-hero-logo" src="{escape(CANGEROES_LOGO_URL)}" alt="Utrecht Cangeroes logo">
    </div>
    <div class="uc-header-shell">
        <div class="uc-kicker">Teamweekend 2026 / 2027</div>
        <div class="uc-title">Net geen Kampioen</div>
        <div class="uc-subtitle">Maar we hebben wel de #1 verslagen</div>
    </div>
</div>
        """
    )


def render_page_intro(title: str, description: str | None = None, eyebrow: str | None = None) -> None:
    eyebrow_html = f'<div class="uc-page-eyebrow">{escape(eyebrow)}</div>' if eyebrow else ""
    description_html = f'<div class="uc-page-copy">{escape(description)}</div>' if description else ""
    render_html_block(
        f"""
<div class="uc-page-intro">
    {eyebrow_html}
    <div class="uc-page-heading">{escape(title)}</div>
    {description_html}
</div>
        """,
    )


def render_form_field_label(label: str, helper: str | None = None) -> None:
    helper_html = f'<div class="uc-field-helper">{escape(helper)}</div>' if helper else ""
    render_html_block(
        f"""
<div class="uc-field-label-block">
    <div class="uc-field-label">{escape(label)}</div>
    {helper_html}
</div>
        """,
    )


def _image_data_url(image_bytes: bytes, suffix: str) -> str:
    mime_type = mimetypes.guess_type(f"file{suffix}")[0] or "image/jpeg"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _render_autoplay_video(video_bytes: bytes) -> str:
    encoded = base64.b64encode(video_bytes).decode("ascii")
    return (
        f"""
        <video class="uc-bottom-media" autoplay muted loop playsinline controls>
            <source src="data:video/mp4;base64,{encoded}" type="video/mp4">
            Your browser does not support the video tag.
        </video>
        """
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
    render_html_block(
        f"""
<div class="uc-release-footer">
    <div class="uc-release-left">{escape(nickname)}</div>
    <div class="uc-release-center">{escape(version)}</div>
    <div class="uc-release-right">{escape(date)}</div>
</div>
        """
    )


def render_bottom_decoration() -> None:
    media_paths = _list_decoration_media()
    chosen: Path | None = random.choice(media_paths) if media_paths else None

    media_markup = ""
    if chosen is None:
        media_markup = (
            f'<img class="uc-bottom-media" src="{escape(CANGEROES_FALLBACK_HERO_URL)}" '
            'alt="Weekend decoration">'
        )
    else:
        suffix = chosen.suffix.lower()
        if suffix in _VIDEO_EXTENSIONS:
            media_markup = _render_autoplay_video(chosen.read_bytes())
        else:
            media_markup = (
                f'<img class="uc-bottom-media" src="{_image_data_url(chosen.read_bytes(), suffix)}" '
                'alt="Weekend decoration">'
            )

    render_html_block(
        f"""
<div class="uc-decoration-wrap">
    <div class="uc-decoration-media">
        {media_markup}
    </div>
</div>
        """
    )

    _render_release_footer()
