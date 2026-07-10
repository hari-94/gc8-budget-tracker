"""Small shared helpers: Mountain Time formatting and device/browser detection."""
import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta

# America/Denver: MST = UTC-7, MDT = UTC-6. We use zoneinfo when available.
try:
    from zoneinfo import ZoneInfo
    MT = ZoneInfo("America/Denver")
except Exception:  # pragma: no cover
    MT = timezone(timedelta(hours=-7))  # fallback: MST


def to_mt(ts) -> datetime | None:
    """Parse a UTC timestamp (str or datetime) and return it in Mountain Time."""
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        return None
    dt = pd.to_datetime(ts, utc=True)
    if dt is pd.NaT:
        return None
    return dt.tz_convert(MT).to_pydatetime()


def fmt_mt(ts, fmt="%b %d, %Y %I:%M %p") -> str:
    """Format a UTC timestamp in Mountain Time, e.g. 'Jul 10, 2026 02:44 PM MT'."""
    dt = to_mt(ts)
    if dt is None:
        return ""
    return dt.strftime(fmt) + " MT"


def get_device() -> str:
    """Best-effort device/browser string. Cached in session after first read."""
    if "device" in st.session_state:
        return st.session_state["device"]
    ua = ""
    try:
        # Available on newer Streamlit; guarded because it may not exist.
        ua = st.context.headers.get("User-Agent", "")
    except Exception:
        ua = ""
    st.session_state["device"] = _summarize_ua(ua)
    return st.session_state["device"]


def _summarize_ua(ua: str) -> str:
    if not ua:
        return "Unknown device"
    ua_l = ua.lower()
    # OS / device
    if "iphone" in ua_l:
        device = "iPhone"
    elif "ipad" in ua_l:
        device = "iPad"
    elif "android" in ua_l:
        device = "Android"
    elif "windows" in ua_l:
        device = "Windows"
    elif "mac os" in ua_l or "macintosh" in ua_l:
        device = "Mac"
    elif "linux" in ua_l:
        device = "Linux"
    else:
        device = "Device"
    # Browser
    if "edg/" in ua_l:
        browser = "Edge"
    elif "chrome" in ua_l and "safari" in ua_l:
        browser = "Chrome"
    elif "firefox" in ua_l:
        browser = "Firefox"
    elif "safari" in ua_l:
        browser = "Safari"
    else:
        browser = ""
    return f"{device} · {browser}".rstrip(" ·")
