import base64
import calendar
import datetime
import hashlib
import hmac
import json
import math
import os
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import extra_streamlit_components as stx

# Page Configuration
st.set_page_config(
    page_title="Attendance & Interactive Calendar Tracker",
    layout="wide",
    initial_sidebar_state="collapsed",
)

VISITOR_LOG_FILE = "student_visitors_log.csv"
STUDENT_DB_FILE = "saved_students_compact.json"
ADMIN_GLOBAL_EXTRAS_FILE = "admin_global_extras.json"
TIMETABLE_IMG_PATH = "timetable.jpg"

# SECURITY CLEANUP: Immediately delete any old shared server session file if it exists
if os.path.exists(".remembered_session.json"):
    try:
        os.remove(".remembered_session.json")
    except Exception:
        pass


# --- SECURITY & HELPER FUNCTIONS ---
def hash_password(password: str) -> str:
    return hashlib.sha256(password.strip().encode("utf-8")).hexdigest()


def get_admin_email() -> str:
    try:
        if "ADMIN_EMAIL" in st.secrets:
            return str(st.secrets["ADMIN_EMAIL"]).strip().lower()
    except Exception:
        pass
    return "honraokanishka@gmail.co"


def get_admin_password_hash() -> str:
    """
    Reads ADMIN_PASSWORD_PLAIN from Streamlit Secrets if configured;
    otherwise uses the irreversible SHA-256 hash so the plain-text password
    is NEVER exposed in GitHub source code.
    """
    try:
        if "ADMIN_PASSWORD_PLAIN" in st.secrets:
            return hash_password(str(st.secrets["ADMIN_PASSWORD_PLAIN"]))
        if "ADMIN_PASSWORD_HASH" in st.secrets:
            return str(st.secrets["ADMIN_PASSWORD_HASH"]).strip().lower()
    except Exception:
        pass
    # Irreversible SHA-256 hash of your admin password (no plain-text password in code!)
    return "341e4d0758c9b07c8671ab4fc1be9e3121a9f199c7424e4c924136461586f861"


def get_cookie_secret_salt() -> str:
    try:
        if "COOKIE_SECRET_SALT" in st.secrets:
            return str(st.secrets["COOKIE_SECRET_SALT"])
    except Exception:
        pass
    return "DBIT_SECURE_SALT_2026_KMH"


ADMIN_EMAIL = get_admin_email()
ADMIN_PASSWORD_HASH = get_admin_password_hash()
COOKIE_SECRET_SALT = get_cookie_secret_salt()


def verify_admin_password(input_pw: str) -> bool:
    if not input_pw:
        return False
    return hmac.compare_digest(hash_password(input_pw), ADMIN_PASSWORD_HASH)


def create_browser_auth_token(email: str, pw_hash: str) -> str:
    """Creates a signed token tied to a specific email and password hash for the user's browser cookie."""
    msg = f"{email.strip().lower()}:{pw_hash}".encode("utf-8")
    sig = hmac.new(COOKIE_SECRET_SALT.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"{email.strip().lower()}|{sig}"


def verify_browser_auth_token(token_str: str, all_db: dict):
    """Verifies a browser cookie token against the student database. Returns email if valid, else None."""
    if not token_str or "|" not in str(token_str):
        return None
    try:
        email, sig = str(token_str).split("|", 1)
        email = email.strip().lower()
        if email not in all_db:
            return None
        pw_hash = all_db[email].get("password_hash", "")
        if not pw_hash:
            return None
        expected_token = create_browser_auth_token(email, pw_hash)
        if hmac.compare_digest(str(token_str), expected_token):
            return email
    except Exception:
        return None
    return None


def get_ist_now():
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    return utc_now + datetime.timedelta(hours=5, minutes=30)


def get_time_greeting():
    hour = get_ist_now().hour
    if 5 <= hour < 12:
        return "Good Morning"
    elif 12 <= hour < 17:
        return "Good Afternoon"
    else:
        return "Good Evening"


def load_all_students_db():
    if os.path.exists(STUDENT_DB_FILE):
        try:
            with open(STUDENT_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def load_admin_global_extras():
    if os.path.exists(ADMIN_GLOBAL_EXTRAS_FILE):
        try:
            with open(ADMIN_GLOBAL_EXTRAS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_admin_global_extras(extras_dict):
    try:
        with open(ADMIN_GLOBAL_EXTRAS_FILE, "w", encoding="utf-8") as f:
            json.dump(extras_dict, f)
    except Exception:
        pass


def save_student_compact(
    email,
    name,
    branch,
    batch,
    semesters_dict,
    daily_logs=None,
    daily_slot_ticks=None,
    slot7_extra_map=None,
    password_hash=None,
    guide_completed=None,
    target_attendance_pct=None,
):
    db = load_all_students_db()
    key = email.strip().lower()
    existing_rec = db.get(key, {})

    compact_sems = {}
    for sem, df in semesters_dict.items():
        sem_data = {}
        for _, row in df.iterrows():
            unatt_val = int(row["Unattended"]) if "Unattended" in row else 0
            extra_val = int(row["Extra Lectures Attended"]) if "Extra Lectures Attended" in row else 0
            sem_data[row["Course Code"]] = [
                int(row["Importance (1-3)"]),
                unatt_val,
                extra_val,
            ]
        compact_sems[sem] = sem_data

    final_logs = existing_rec.get("daily_logs", {}) if daily_logs is None else daily_logs
    final_ticks = existing_rec.get("daily_slot_ticks", {}) if daily_slot_ticks is None else daily_slot_ticks
    final_slot7 = existing_rec.get("slot7_extra_map", {}) if slot7_extra_map is None else slot7_extra_map
    final_pw = existing_rec.get("password_hash", "") if password_hash is None else password_hash
    final_guide = existing_rec.get("guide_completed", False) if guide_completed is None else guide_completed
    final_target = existing_rec.get("target_attendance_pct", 75) if target_attendance_pct is None else target_attendance_pct

    db[key] = {
        "email": key,
        "name": name.strip(),
        "branch": branch,
        "batch": batch,
        "password_hash": final_pw,
        "guide_completed": final_guide,
        "target_attendance_pct": int(final_target),
        "storage_mode": "unattended_v6",
        "last_updated": get_ist_now().strftime("%Y-%m-%d %H:%M:%S IST"),
        "data": compact_sems,
        "daily_logs": final_logs,
        "daily_slot_ticks": final_ticks,
        "slot7_extra_map": final_slot7,
    }
    with open(STUDENT_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f)


def update_student_visit(email, name, branch, batch):
    ist_time = get_ist_now().strftime("%Y-%m-%d %H:%M:%S IST")
    if os.path.exists(VISITOR_LOG_FILE):
        log_df = pd.read_csv(VISITOR_LOG_FILE)
        if "Batch" not in log_df.columns:
            log_df["Batch"] = "Batch A"
        if "Email" in log_df.columns and email.lower() in log_df["Email"].str.lower().values:
            log_df.loc[
                log_df["Email"].str.lower() == email.lower(),
                ["Student Name", "Branch", "Batch", "Last Login Time"],
            ] = [name.strip(), branch, batch, ist_time]
        else:
            new_row = pd.DataFrame([{
                "Email": email.strip().lower(),
                "Student Name": name.strip(),
                "Branch": branch,
                "Batch": batch,
                "Last Login Time": ist_time,
            }])
            log_df = pd.concat([log_df, new_row], ignore_index=True)
    else:
        log_df = pd.DataFrame([{
            "Email": email.strip().lower(),
            "Student Name": name.strip(),
            "Branch": branch,
            "Batch": batch,
            "Last Login Time": ist_time,
        }])
    log_df.to_csv(VISITOR_LOG_FILE, index=False)


# --- INITIALIZE PER-BROWSER COOKIE MANAGER (ISOLATED PER DEVICE/PHONE) ---
cookie_manager = stx.CookieManager(key="secure_student_cookie_mgr")

# SECURITY FIX: Never allow ?email= or ?token= in the URL bar so shared links NEVER leak accounts
if "email" in st.query_params or "token" in st.query_params or "logged_out" in st.query_params:
    st.query_params.clear()


# --- CONTEXTUAL STEP GUIDE ---
def apply_guide_blur_css():
    st.markdown(
        """
        <style>
        [data-testid="stVerticalBlock"] > div:has(> div.stMarkdown > div > .blur-target-block) {
            filter: blur(8px) brightness(0.38);
            pointer-events: none !important;
            user-select: none !important;
            transition: all 0.25s ease;
        }
        [data-testid="stSidebar"] {
            filter: blur(8px) brightness(0.38);
            pointer-events: none !important;
            user-select: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_side_guide_card(step_num, total_steps, title, message, state_key, arrow_dir="left", finish_tour=False):
    arrow_symbol = "&#8592; Linked Section" if arrow_dir == "left" else "&#8593; Linked Section Above"
    st.markdown(
        f"""
        <div id="active-guide-anchor" class="guide-callout-box blinking-guide-window">
            <div class="guide-step-pill">STEP {step_num} OF {total_steps} (ACTION REQUIRED)</div>
            <div style="color:#60a5fa; font-weight:800; font-size:14px; margin-bottom:6px;">
                {arrow_symbol}
            </div>
            <div class="guide-box-title">{title}</div>
            <div class="guide-box-desc">{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Got it", key=f"got_it_{state_key}_{step_num}", type="primary", width="stretch"):
        st.session_state[state_key] += 1
        if finish_tour and st.session_state.get("student_logged_in", False):
            st.session_state.guide_completed = True
            save_student_compact(
                st.session_state.student_email,
                st.session_state.student_name,
                st.session_state.student_branch,
                st.session_state.get("student_batch", "Batch A"),
                st.session_state.saved_semesters,
                st.session_state.daily_logs,
                st.session_state.daily_slot_ticks,
                st.session_state.slot7_extra_map,
                guide_completed=True,
                target_attendance_pct=st.session_state.get("target_attendance_pct", 75),
            )
        st.rerun()

    components.html(
        """
        <script>
        (function() {
            function scrollToGuide() {
                try {
                    const parentDoc = window.parent.document;
                    const guideEl = parentDoc.getElementById('active-guide-anchor');
                    if (guideEl) {
                        guideEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                } catch (e) {}
            }
            setTimeout(scrollToGuide, 120);
            setTimeout(scrollToGuide, 450);
        })();
        </script>
        """,
        height=0,
    )


# --- GLOBAL & MOBILE-RESPONSIVE CSS ---
st.markdown(
    """
    <style>
    @keyframes blinker {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.25; transform: scale(0.97); }
    }
    @keyframes guidePulse {
        0%, 100% {
            box-shadow: 0 0 12px rgba(59, 130, 246, 0.7), 0 0 28px rgba(37, 99, 235, 0.5);
            border-color: #60a5fa;
            transform: scale(1);
        }
        50% {
            box-shadow: 0 0 26px rgba(59, 130, 246, 1), 0 0 48px rgba(96, 165, 250, 0.95);
            border-color: #ffffff;
            transform: scale(1.015);
        }
    }
    @keyframes blueBtnBlink {
        0%, 100% {
            background-color: #2563eb !important;
            box-shadow: 0 0 10px rgba(37, 99, 235, 0.8);
            border: 2px solid #93c5fd !important;
        }
        50% {
            background-color: #1d4ed8 !important;
            box-shadow: 0 0 24px rgba(96, 165, 250, 1);
            border: 2px solid #ffffff !important;
        }
    }

    button[kind="primary"] {
        background-color: #2563eb !important;
        color: #ffffff !important;
        font-weight: 800 !important;
        font-size: 15px !important;
        border-radius: 8px !important;
        animation: blueBtnBlink 1.1s infinite ease-in-out !important;
    }
    button[kind="primary"]:hover {
        background-color: #1e40af !important;
        color: #ffffff !important;
    }

    .missed-lectures-banner {
        background: linear-gradient(90deg, #0f172a, #1e3a8a, #0f172a);
        color: #ffffff;
        padding: 14px 20px;
        border: 2px solid #38bdf8;
        border-radius: 8px;
        font-size: 20px;
        font-weight: 900;
        letter-spacing: 1px;
        text-transform: uppercase;
        text-align: center;
        margin-top: 10px;
        margin-bottom: 12px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    }

    .blinking-guide-window {
        animation: guidePulse 1.15s infinite ease-in-out;
    }
    .blinking-batch-badge {
        background-color: #dc2626;
        color: #ffffff;
        padding: 3px 7px;
        border-radius: 5px;
        font-weight: 800;
        font-size: 11px;
        border: 1px solid #fecaca;
        animation: blinker 1s linear infinite;
        display: inline-block;
        margin-top: 4px;
    }
    .guide-callout-box {
        background: linear-gradient(135deg, #0f172a, #1e3a8a);
        color: #f8fafc;
        border: 3px solid #3b82f6;
        border-radius: 12px;
        padding: 18px 20px;
        position: relative;
        font-family: 'Segoe UI', sans-serif;
        margin-top: 8px;
        margin-bottom: 12px;
        z-index: 99999;
    }
    .guide-step-pill {
        background: #2563eb;
        color: #ffffff;
        font-weight: 800;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 11px;
        letter-spacing: 0.5px;
        display: inline-block;
        margin-bottom: 8px;
        border: 1px solid #93c5fd;
    }
    .guide-box-title {
        font-size: 17px;
        font-weight: 700;
        color: #e0f2fe;
        margin-bottom: 6px;
    }
    .guide-box-desc {
        font-size: 13.5px;
        color: #e2e8f0;
        line-height: 1.45;
        margin-bottom: 8px;
    }
    .cal-legend {
        display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px;
        padding: 10px; background: rgba(30, 41, 59, 0.7); border: 1px solid #475569; border-radius: 8px;
    }
    .legend-item { display: flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600; }
    .dot-red { width: 13px; height: 13px; background: #ef4444; border-radius: 3px; display: inline-block; }
    .dot-green { width: 13px; height: 13px; background: #22c55e; border-radius: 3px; display: inline-block; }
    .dot-yellow { width: 13px; height: 13px; background: #eab308; border-radius: 3px; display: inline-block; }
    .dot-blue { width: 13px; height: 13px; background: #3b82f6; border-radius: 3px; display: inline-block; }

    .cal-hdr-cell {
        text-align: center;
        font-weight: 800;
        font-size: 12.5px;
        color: #f8fafc;
        background-color: #1e293b;
        border: 1.5px solid #64748b;
        padding: 7px 2px;
        margin-bottom: 2px;
    }
    .cal-cell {
        border-radius: 0px;
        padding: 6px 2px;
        text-align: center;
        font-weight: 700;
        font-size: 12.5px;
        min-height: 52px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        border: 1.5px solid #64748b;
        box-sizing: border-box;
    }
    .cal-red { background-color: #ef4444; color: #ffffff; border: 1.5px solid #991b1b; }
    .cal-green { background-color: #22c55e; color: #ffffff; border: 1.5px solid #166534; }
    .cal-yellow { background-color: #eab308; color: #111827; border: 1.5px solid #854d0e; }
    .cal-blue { background-color: #3b82f6; color: #ffffff; border: 1.5px solid #1e40af; }
    .cal-empty {
        background-color: rgba(15, 23, 42, 0.35);
        min-height: 52px;
        border: 1.5px solid #334155;
        box-sizing: border-box;
    }
    .cal-sub { font-size: 9px; font-weight: 800; margin-top: 2px; line-height: 1.05; word-break: break-word; }

    .tt-scroll-wrapper {
        width: 100%;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        border-radius: 8px;
        margin-top: 8px;
    }
    .vertical-tt-table {
        width: 100%;
        min-width: 680px;
        border-collapse: collapse;
        font-family: 'Segoe UI', sans-serif;
    }
    .vertical-tt-table th {
        background-color: #1e293b;
        color: #f8fafc;
        font-size: 15px;
        font-weight: 800;
        padding: 12px 10px;
        border: 2px solid #475569;
        text-align: center;
    }
    .vertical-tt-table td {
        padding: 14px 10px;
        border: 2px solid #475569;
        text-align: center;
        vertical-align: middle;
        font-size: 13.5px;
        line-height: 1.4;
        min-height: 68px;
    }
    .tt-slot-col {
        background-color: #0f172a;
        color: #e2e8f0;
        font-weight: 800;
        font-size: 13px;
        width: 14%;
    }
    .tt-cell-green {
        background-color: rgba(34, 197, 94, 0.28);
        color: #bbf7d0;
        font-weight: 700;
    }
    .tt-cell-yellow {
        background-color: rgba(234, 179, 8, 0.32);
        color: #fef08a;
        font-weight: 700;
    }
    .tt-cell-red {
        background-color: #ef4444;
        color: #ffffff;
        font-weight: 800;
        letter-spacing: 0.5px;
    }
    .tt-cell-blue {
        background-color: rgba(59, 130, 246, 0.22);
        color: #bfdbfe;
        font-weight: 600;
    }
    .creator-footer {
        text-align: center;
        margin-top: 40px;
        padding: 18px;
        border-top: 2px solid #334155;
        color: #e2e8f0;
        font-size: 17px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }

    /* --- MOBILE SCREEN OPTIMIZATIONS (ANDROID & IOS) --- */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
            padding-top: 1.2rem !important;
        }
        h1 { font-size: 1.55rem !important; }
        h2, h3 { font-size: 1.2rem !important; }
        .missed-lectures-banner {
            font-size: 15px !important;
            padding: 10px 12px !important;
        }
        [data-testid="stHorizontalBlock"]:has(.cal-cell),
        [data-testid="stHorizontalBlock"]:has(.cal-empty),
        [data-testid="stHorizontalBlock"]:has(.cal-hdr-cell) {
            display: grid !important;
            grid-template-columns: repeat(7, minmax(0, 1fr)) !important;
            gap: 2px !important;
            width: 100% !important;
        }
        [data-testid="stHorizontalBlock"]:has(.cal-cell) > div,
        [data-testid="stHorizontalBlock"]:has(.cal-empty) > div,
        [data-testid="stHorizontalBlock"]:has(.cal-hdr-cell) > div {
            width: 100% !important;
            min-width: 0 !important;
            flex: unset !important;
        }
        .cal-hdr-cell {
            font-size: 10px !important;
            padding: 4px 1px !important;
        }
        .cal-cell, .cal-empty {
            min-height: 44px !important;
            font-size: 11px !important;
            padding: 3px 1px !important;
        }
        .cal-sub {
            font-size: 7.5px !important;
        }
        [data-testid="stHorizontalBlock"]:has(.cal-cell) button {
            padding: 2px 2px !important;
            font-size: 9.5px !important;
            min-height: 24px !important;
            height: 24px !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- TIMETABLE DATA ---
TIME_SLOTS = [
    "1 (9:00 - 10:00)",
    "2 (10:00 - 11:00)",
    "Short Break (11:00 - 11:15)",
    "3 (11:15 - 12:15)",
    "4 (12:15 - 13:15)",
    "Lunch Break (13:15 - 14:00)",
    "5 (14:00 - 15:00)",
    "6 (15:00 - 16:00)",
    "7 (16:00 - 17:00)",
]

EVEN_WEEK_TIMETABLE_GRID = {
    "MON": ["AP", "Lab EC (A) / Lab AP (B) / FEM-I Tut (C)", "SHORT BREAK", "FEM-I", "EG", "LUNCH BREAK", "Lab CP (A) / Lab EG (B) / Lab BE&DE (C)", "Lab CP (A) / Lab EG (B) / Lab BE&DE (C)", "Remedial Lecture"],
    "TUE": ["EC", "EG", "SHORT BREAK", "BE&DE", "FEM-I", "LUNCH BREAK", "Lab AP (A) / FEM-I Tut (B) / Lab EC (C)", "UHV", "FE Mentoring Slot"],
    "WED": ["FEM-I Tut (A) / Lab EC (B) / Lab AP (C)", "AP", "SHORT BREAK", "CP", "CP", "LUNCH BREAK", "Workshop-I [WS-I] (A) / Workshop-I [WS-I] (B) / Workshop-I [WS-I] (C)", "Workshop-I [WS-I] (A) / Workshop-I [WS-I] (B) / Workshop-I [WS-I] (C)", "Extra Lecture Slot 1"],
    "THR": ["Lab EG (A) / Lab BE&DE (B) / Lab CP (C)", "Lab EG (A) / Lab BE&DE (B) / Lab CP (C)", "SHORT BREAK", "Lab BE&DE (A) / Lab CP (B) / Lab EG (C)", "Lab BE&DE (A) / Lab CP (B) / Lab EG (C)", "LUNCH BREAK", "BE&DE", "FEM-I", "Extra Lecture Slot 2"],
    "FRI": ["BE&DE", "FEM-I", "SHORT BREAK", "EG", "BE&DE", "LUNCH BREAK", "EC", "UHV", "Extra Lecture Slot 3"],
}

ODD_WEEK_TIMETABLE_GRID = {
    "MON": ["AP", "Lab EC (A) / Lab AP (B) / FEM-I Tut (C)", "SHORT BREAK", "FEM-I", "EG", "LUNCH BREAK", "Lab CP (A) / Lab EG (B) / Lab BE&DE (C)", "Lab CP (A) / Lab EG (B) / Lab BE&DE (C)", "Remedial Lecture"],
    "TUE": ["EC", "BE&DE", "SHORT BREAK", "FEM-I", "AP", "LUNCH BREAK", "Lab AP (A) / FEM-I Tut (B) / Lab EC (C)", "UHV", "FE Mentoring Slot"],
    "WED": ["FEM-I Tut (A) / Lab EC (B) / Lab AP (C)", "EC", "SHORT BREAK", "CP", "CP", "LUNCH BREAK", "Workshop-I [WS-I] (A) / Workshop-I [WS-I] (B) / Workshop-I [WS-I] (C)", "Workshop-I [WS-I] (A) / Workshop-I [WS-I] (B) / Workshop-I [WS-I] (C)", "Extra Lecture Slot 1"],
    "THR": ["Lab EG (A) / Lab BE&DE (B) / Lab CP (C)", "Lab EG (A) / Lab BE&DE (B) / Lab CP (C)", "SHORT BREAK", "Lab BE&DE (A) / Lab CP (B) / Lab EG (C)", "Lab BE&DE (A) / Lab CP (B) / Lab EG (C)", "LUNCH BREAK", "FEM-I", "BE&DE", "Extra Lecture Slot 2"],
    "FRI": ["EC", "BE&DE", "SHORT BREAK", "EG", "BE&DE", "LUNCH BREAK", "FEM-I", "AP", "UHV"],
}

EVEN_WEEK_RANGES = [
    (datetime.date(2026, 9, 21), datetime.date(2026, 9, 25)),
    (datetime.date(2026, 10, 5), datetime.date(2026, 10, 9)),
    (datetime.date(2026, 10, 26), datetime.date(2026, 10, 30)),
    (datetime.date(2026, 11, 9), datetime.date(2026, 11, 13)),
    (datetime.date(2026, 11, 23), datetime.date(2026, 11, 27)),
]

ODD_WEEK_RANGES = [
    (datetime.date(2026, 9, 7), datetime.date(2026, 9, 11)),
    (datetime.date(2026, 9, 28), datetime.date(2026, 10, 2)),
    (datetime.date(2026, 10, 12), datetime.date(2026, 10, 16)),
    (datetime.date(2026, 11, 1), datetime.date(2026, 11, 6)),
    (datetime.date(2026, 11, 16), datetime.date(2026, 11, 20)),
    (datetime.date(2026, 11, 30), datetime.date(2026, 12, 4)),
]


def get_week_type(d: datetime.date):
    for start, end in EVEN_WEEK_RANGES:
        if start <= d <= end:
            return "Even Week"
    for start, end in ODD_WEEK_RANGES:
        if start <= d <= end:
            return "Odd Week"
    return "Even Week" if d.isocalendar()[1] % 2 == 0 else "Odd Week"


def extract_batch_specific_entry(raw_entry: str, batch_letter: str):
    if "/" in raw_entry and ("(A)" in raw_entry or "(B)" in raw_entry or "(C)" in raw_entry):
        parts = [p.strip() for p in raw_entry.split("/")]
        for part in parts:
            if f"({batch_letter})" in part:
                return part, True
    return raw_entry, False


def match_subject_short_form(entry_text: str, subject_stats_dict: dict):
    clean_up = entry_text.strip().upper()
    if not clean_up:
        return None
    if "WORKSHOP" in clean_up or "WS-I" in clean_up:
        return "WS-I" if "WS-I" in subject_stats_dict else None
    for sf_code, info in subject_stats_dict.items():
        if info["code"].upper() in clean_up:
            return sf_code
    for sf_code in sorted(subject_stats_dict.keys(), key=len, reverse=True):
        if sf_code.upper() in clean_up:
            return sf_code
    return None


SEM1_OFFICIAL_MILESTONES = [
    {"Sr. No.": 1, "Academic Activity / Particulars": "Working days for all FE Engineering Programs", "Scheduled Dates": "07th September to 23rd December 2026"},
    {"Sr. No.": 2, "Academic Activity / Particulars": "FE Orientation", "Scheduled Dates": "12th September 2026"},
    {"Sr. No.": 3, "Academic Activity / Particulars": "Mid-Term Break (Ganesh Festival)", "Scheduled Dates": "14th September to 18th September 2026"},
    {"Sr. No.": 4, "Academic Activity / Particulars": "Mid Semester Examination FE (SEM-I)", "Scheduled Dates": "19th October to 24th October 2026"},
    {"Sr. No.": 5, "Academic Activity / Particulars": "Diwali Break", "Scheduled Dates": "07th November to 10th November 2026"},
    {"Sr. No.": 6, "Academic Activity / Particulars": "Oral/Practical Examination", "Scheduled Dates": "07th December to 12th December 2026"},
    {"Sr. No.": 7, "Academic Activity / Particulars": "End Semester Examination FE (SEM-I)", "Scheduled Dates": "14th December to 23rd December 2026"},
    {"Sr. No.": 8, "Academic Activity / Particulars": "Open House", "Scheduled Dates": "31st December 2026"},
    {"Sr. No.": 9, "Academic Activity / Particulars": "Results Declaration", "Scheduled Dates": "11th January 2027"},
    {"Sr. No.": 10, "Academic Activity / Particulars": "Supplementary Examination FE (SEM-I)", "Scheduled Dates": "01st February to 05th February 2027"},
    {"Sr. No.": 11, "Academic Activity / Particulars": "Commencement of New Term", "Scheduled Dates": "04th January 2027"},
]

SEM1_HOLIDAY_DATES = [
    {"Date": "2026-09-14", "Holiday Name": "Ganeshotsav Break", "Term": "Semester I (FE)"},
    {"Date": "2026-09-15", "Holiday Name": "Ganeshotsav Break", "Term": "Semester I (FE)"},
    {"Date": "2026-09-16", "Holiday Name": "Ganeshotsav Break", "Term": "Semester I (FE)"},
    {"Date": "2026-09-17", "Holiday Name": "Ganeshotsav Break", "Term": "Semester I (FE)"},
    {"Date": "2026-09-18", "Holiday Name": "Ganeshotsav Break", "Term": "Semester I (FE)"},
    {"Date": "2026-10-02", "Holiday Name": "Gandhi Jayanti", "Term": "Semester I (FE)"},
    {"Date": "2026-10-20", "Holiday Name": "Dussehra", "Term": "Semester I (FE)"},
    {"Date": "2026-11-07", "Holiday Name": "Diwali Break", "Term": "Semester I (FE)"},
    {"Date": "2026-11-08", "Holiday Name": "Diwali Break", "Term": "Semester I (FE)"},
    {"Date": "2026-11-09", "Holiday Name": "Diwali Break", "Term": "Semester I (FE)"},
    {"Date": "2026-11-10", "Holiday Name": "Diwali Break", "Term": "Semester I (FE)"},
    {"Date": "2026-11-24", "Holiday Name": "Guru Nanak Jayanti", "Term": "Semester I (FE)"},
]

YEARLY_HOLIDAYS = [
    {"Date": "2026-08-15", "Holiday Name": "Independence Day", "Term": "Odd Semester"},
    {"Date": "2026-10-02", "Holiday Name": "Gandhi Jayanti", "Term": "Odd Semester"},
    {"Date": "2026-10-20", "Holiday Name": "Dussehra", "Term": "Odd Semester"},
    {"Date": "2026-11-09", "Holiday Name": "Diwali", "Term": "Odd Semester"},
    {"Date": "2027-01-26", "Holiday Name": "Republic Day", "Term": "Even Semester"},
    {"Date": "2027-03-22", "Holiday Name": "Holi", "Term": "Even Semester"},
    {"Date": "2027-05-01", "Holiday Name": "Maharashtra Din", "Term": "Even Semester"},
]

SEMESTER_DATA = {
    "Semester I": [
        {"Course Category": "Compulsory", "Course Code": "25FE1BSC01", "Short Form": "FEM-I", "Course Name": "Fundamentals of Engineering Mathematics I", "Credits": 4, "Importance (1-3)": 3, "Total Lectures": 45, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25FE1BSC02", "Short Form": "AP", "Course Name": "Applied Physics", "Credits": 3, "Importance (1-3)": 3, "Total Lectures": 35, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25FE1BSC03", "Short Form": "EC", "Course Name": "Engineering Chemistry", "Credits": 3, "Importance (1-3)": 3, "Total Lectures": 35, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25FE1ESC01", "Short Form": "EG", "Course Name": "Engineering Graphics", "Credits": 3, "Importance (1-3)": 2, "Total Lectures": 30, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25FE1ESC02", "Short Form": "BE&DE", "Course Name": "Basic Electrical and Digital Electronics", "Credits": 3, "Importance (1-3)": 2, "Total Lectures": 35, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25FE1VSEC01", "Short Form": "WS-I", "Course Name": "Workshop - 1", "Credits": 2, "Importance (1-3)": 2, "Total Lectures": 20, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25FE1VSEC02", "Short Form": "CP", "Course Name": "Problem Solving using C programming", "Credits": 2, "Importance (1-3)": 3, "Total Lectures": 30, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25FE1VEC01", "Short Form": "UHV", "Course Name": "Universal Human Values", "Credits": 2, "Importance (1-3)": 1, "Total Lectures": 20, "Unattended": 0, "Extra Lectures Attended": 0},
    ],
    "Semester II": [
        {"Course Category": "Compulsory", "Course Code": "25FE2BSC01", "Short Form": "FEM-II", "Course Name": "Fundamentals of Engineering Mathematics II", "Credits": 4, "Importance (1-3)": 3, "Total Lectures": 45, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25FE2BSC02", "Short Form": "AP-II", "Course Name": "Applied Physics II", "Credits": 3, "Importance (1-3)": 2, "Total Lectures": 30, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25FE2BSC03", "Short Form": "AC-II", "Course Name": "Applied Chemistry II", "Credits": 3, "Importance (1-3)": 2, "Total Lectures": 30, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25FE2ESC01", "Short Form": "EM", "Course Name": "Engineering Mechanics", "Credits": 4, "Importance (1-3)": 3, "Total Lectures": 40, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25FE2VSEC01", "Short Form": "WS-II", "Course Name": "Workshop - 2", "Credits": 2, "Importance (1-3)": 2, "Total Lectures": 20, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25FE2VSEC02", "Short Form": "PY", "Course Name": "Python Programming", "Credits": 2, "Importance (1-3)": 3, "Total Lectures": 30, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25FE2AEC01", "Short Form": "PCE", "Course Name": "Professional Communication & Ethics", "Credits": 2, "Importance (1-3)": 1, "Total Lectures": 25, "Unattended": 0, "Extra Lectures Attended": 0},
    ],
    "Semester III": [
        {"Course Category": "Compulsory", "Course Code": "25SE3BSC01", "Short Form": "EM-III", "Course Name": "Engineering Mathematics III", "Credits": 4, "Importance (1-3)": 3, "Total Lectures": 40, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25SE3PCC01", "Short Form": "DSA", "Course Name": "Data Structures and Algorithms", "Credits": 4, "Importance (1-3)": 3, "Total Lectures": 40, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25SE3PCC02", "Short Form": "DBMS", "Course Name": "Database Management Systems", "Credits": 3, "Importance (1-3)": 3, "Total Lectures": 35, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25SE3PCC03", "Short Form": "COA", "Course Name": "Computer Organization & Architecture", "Credits": 3, "Importance (1-3)": 2, "Total Lectures": 35, "Unattended": 0, "Extra Lectures Attended": 0},
    ],
    "Semester IV": [
        {"Course Category": "Compulsory", "Course Code": "25SE4BSC01", "Short Form": "EM-IV", "Course Name": "Engineering Mathematics IV", "Credits": 4, "Importance (1-3)": 3, "Total Lectures": 40, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25SE4PCC01", "Short Form": "AOA", "Course Name": "Analysis of Algorithms", "Credits": 4, "Importance (1-3)": 3, "Total Lectures": 40, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25SE4PCC02", "Short Form": "OS", "Course Name": "Operating Systems", "Credits": 3, "Importance (1-3)": 3, "Total Lectures": 35, "Unattended": 0, "Extra Lectures Attended": 0},
    ],
    "Semester V": [
        {"Course Category": "Compulsory", "Course Code": "25TE5PCC01", "Short Form": "TCS", "Course Name": "Theory of Computer Science", "Credits": 4, "Importance (1-3)": 3, "Total Lectures": 40, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25TE5PCC02", "Short Form": "SE", "Course Name": "Software Engineering", "Credits": 3, "Importance (1-3)": 2, "Total Lectures": 35, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25TE5PCC03", "Short Form": "CN", "Course Name": "Computer Networks", "Credits": 4, "Importance (1-3)": 3, "Total Lectures": 40, "Unattended": 0, "Extra Lectures Attended": 0},
    ],
    "Semester VI": [
        {"Course Category": "Compulsory", "Course Code": "25TE6PCC01", "Short Form": "SPCC", "Course Name": "System Programming & Compiler Construction", "Credits": 4, "Importance (1-3)": 3, "Total Lectures": 40, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25TE6PCC02", "Short Form": "CSS", "Course Name": "Cryptography & System Security", "Credits": 3, "Importance (1-3)": 3, "Total Lectures": 35, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25TE6PCC04", "Short Form": "AI", "Course Name": "Artificial Intelligence", "Credits": 4, "Importance (1-3)": 3, "Total Lectures": 40, "Unattended": 0, "Extra Lectures Attended": 0},
    ],
    "Semester VII": [
        {"Course Category": "Compulsory", "Course Code": "25BE7PCC01", "Short Form": "ML", "Course Name": "Machine Learning", "Credits": 4, "Importance (1-3)": 3, "Total Lectures": 40, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25BE7PCC02", "Short Form": "BDA", "Course Name": "Big Data Analytics", "Credits": 4, "Importance (1-3)": 3, "Total Lectures": 40, "Unattended": 0, "Extra Lectures Attended": 0},
    ],
    "Semester VIII": [
        {"Course Category": "Compulsory", "Course Code": "25BE8PCC01", "Short Form": "DC", "Course Name": "Distributed Computing / Cloud Computing", "Credits": 4, "Importance (1-3)": 3, "Total Lectures": 40, "Unattended": 0, "Extra Lectures Attended": 0},
        {"Course Category": "Compulsory", "Course Code": "25BE8PRJ01", "Short Form": "MP-II", "Course Name": "Major Project - II", "Credits": 6, "Importance (1-3)": 3, "Total Lectures": 30, "Unattended": 0, "Extra Lectures Attended": 0},
    ],
}

BRANCH_OPTIONS = [
    "Basic Sciences and Humanities (FE)",
    "Electronics and Telecommunication Engineering",
    "Computer Engineering",
    "Information Technology",
    "Mechanical Engineering",
]

BATCH_OPTIONS = ["Batch A", "Batch B", "Batch C"]


def hydrate_semesters_for_user(user_obj):
    saved_student_data = user_obj.get("data", {})
    sem_dict_out = {}
    for sem, courses in SEMESTER_DATA.items():
        temp_df = pd.DataFrame(courses)
        if sem in saved_student_data:
            sem_dict = saved_student_data[sem]
            for idx, row in temp_df.iterrows():
                code = row["Course Code"]
                tot_lec = int(row["Total Lectures"])
                if code in sem_dict:
                    vals = sem_dict[code]
                    temp_df.loc[idx, "Importance (1-3)"] = vals[0]
                    temp_df.loc[idx, "Unattended"] = min(tot_lec, max(0, int(vals[1])))
                    base_extra = vals[2] if len(vals) > 2 else 0
                    temp_df.loc[idx, "Extra Lectures Attended"] = max(0, int(base_extra))
        temp_df.index = range(1, len(temp_df) + 1)
        sem_dict_out[sem] = temp_df
    return sem_dict_out


# --- PER-DEVICE BROWSER COOKIE AUTO-LOGIN (100% ISOLATED PER USER PHONE/PC) ---
if "student_logged_in" not in st.session_state:
    st.session_state.student_logged_in = False

if not st.session_state.get("student_logged_in", False) and not st.session_state.get("manual_logout", False):
    browser_cookie_token = cookie_manager.get(cookie="att_device_auth_token")
    if browser_cookie_token:
        all_db = load_all_students_db()
        verified_email = verify_browser_auth_token(browser_cookie_token, all_db)
        if verified_email:
            user_record = all_db[verified_email]
            st.session_state.student_logged_in = True
            st.session_state.student_email = verified_email
            st.session_state.student_name = user_record.get("name", "Student")
            st.session_state.student_branch = user_record.get("branch", BRANCH_OPTIONS[0])
            st.session_state.student_batch = user_record.get("batch", BATCH_OPTIONS[0])
            st.session_state.guide_completed = True
            st.session_state.target_attendance_pct = int(user_record.get("target_attendance_pct", 75))
            st.session_state.dashboard_guide_step = 99

if "dashboard_guide_step" not in st.session_state:
    st.session_state.dashboard_guide_step = 99 if st.session_state.get("guide_completed", False) else 1

if st.session_state.get("student_logged_in", False) and "saved_semesters" not in st.session_state:
    email_key = st.session_state.student_email.strip().lower()
    all_db = load_all_students_db()
    user_obj = all_db.get(email_key, {})
    st.session_state.student_batch = user_obj.get("batch", BATCH_OPTIONS[0])
    st.session_state.guide_completed = user_obj.get("guide_completed", True)
    st.session_state.target_attendance_pct = int(user_obj.get("target_attendance_pct", 75))
    st.session_state.daily_logs = user_obj.get("daily_logs", {})
    st.session_state.daily_slot_ticks = user_obj.get("daily_slot_ticks", {})
    st.session_state.slot7_extra_map = user_obj.get("slot7_extra_map", {})
    st.session_state.saved_semesters = hydrate_semesters_for_user(user_obj)

# --- LOGIN SCREEN ---
if not st.session_state.get("student_logged_in", False):
    st.title("Attendance, Timetable & Calendar Tracker")
    st.subheader("Secure Student Login & Registration")
    st.caption("Your login is saved privately inside your own phone/laptop browser cookie—sharing the website link in groups will never share your account.")

    with st.form("student_login_form"):
        input_email = st.text_input("Enter Your Gmail Address (must end with @gmail.com):")
        input_password = st.text_input("Enter Your Password (new users: choose a password to lock your account):", type="password")
        input_name = st.text_input("Enter Your Real Full Name (Required for first-time registration):")
        input_branch = st.selectbox("Select Your Branch:", BRANCH_OPTIONS)
        input_batch = st.selectbox("Select Your College Batch:", BATCH_OPTIONS)
        remember_me = st.checkbox("Remember Me on this device only", value=True)
        submit_btn = st.form_submit_button("Login / Register & Enter Dashboard", width="stretch")

        if submit_btn:
            clean_email = input_email.strip().lower()
            clean_name = input_name.strip()
            clean_pw = input_password.strip()

            if not clean_email.endswith("@gmail.com"):
                st.error("Invalid email domain. Please use a valid Gmail address ending with '@gmail.com'.")
            elif not clean_pw:
                st.error("Please enter a password.")
            else:
                if clean_email == ADMIN_EMAIL and not verify_admin_password(clean_pw):
                    st.error("Invalid password for Admin Gmail account.")
                    st.stop()

                all_db = load_all_students_db()
                pw_hashed = hash_password(clean_pw)
                is_existing_user = clean_email in all_db

                if is_existing_user:
                    user_obj = all_db[clean_email]
                    stored_hash = user_obj.get("password_hash", "")
                    if stored_hash and stored_hash != pw_hashed and clean_email != ADMIN_EMAIL:
                        st.error("Incorrect password for this Gmail account.")
                        st.stop()
                    final_name = clean_name if clean_name else user_obj.get("name", "Kanishka Maya Honrao" if clean_email == ADMIN_EMAIL else "Student")
                    final_branch = user_obj.get("branch", input_branch)
                    final_batch = user_obj.get("batch", input_batch)
                    guide_done = True
                    st.session_state.dashboard_guide_step = 99
                else:
                    if not clean_name and clean_email != ADMIN_EMAIL:
                        st.error("First-time registration requires your Real Full Name.")
                        st.stop()
                    user_obj = {}
                    final_name = clean_name if clean_name else "Kanishka Maya Honrao"
                    final_branch = input_branch
                    final_batch = input_batch
                    guide_done = False
                    st.session_state.dashboard_guide_step = 1

                st.session_state.manual_logout = False
                st.session_state.student_email = clean_email
                st.session_state.student_name = final_name
                st.session_state.student_branch = final_branch
                st.session_state.student_batch = final_batch
                st.session_state.guide_completed = guide_done
                st.session_state.target_attendance_pct = int(user_obj.get("target_attendance_pct", 75))
                st.session_state.student_logged_in = True

                st.session_state.daily_logs = user_obj.get("daily_logs", {})
                st.session_state.daily_slot_ticks = user_obj.get("daily_slot_ticks", {})
                st.session_state.slot7_extra_map = user_obj.get("slot7_extra_map", {})
                st.session_state.saved_semesters = hydrate_semesters_for_user(user_obj)

                save_student_compact(
                    clean_email,
                    final_name,
                    final_branch,
                    final_batch,
                    st.session_state.saved_semesters,
                    st.session_state.daily_logs,
                    st.session_state.daily_slot_ticks,
                    st.session_state.slot7_extra_map,
                    password_hash=pw_hashed,
                    guide_completed=guide_done,
                    target_attendance_pct=st.session_state.target_attendance_pct,
                )
                update_student_visit(clean_email, final_name, final_branch, final_batch)

                if remember_me:
                    signed_token = create_browser_auth_token(clean_email, pw_hashed)
                    cookie_manager.set(
                        "att_device_auth_token",
                        signed_token,
                        expires_at=datetime.datetime.now() + datetime.timedelta(days=60),
                    )
                else:
                    try:
                        cookie_manager.delete("att_device_auth_token")
                    except Exception:
                        pass

                st.rerun()

    st.markdown(
        '<div class="creator-footer">Designed and Created by Kanishka Maya Honrao</div>',
        unsafe_allow_html=True,
    )
    st.stop()

if "slot7_extra_map" not in st.session_state:
    st.session_state.slot7_extra_map = {}

# --- MAIN DASHBOARD ---
active_step = st.session_state.dashboard_guide_step
guide_is_active = (not st.session_state.get("guide_completed", True)) and (active_step in [1, 2, 3, 4])
if guide_is_active:
    apply_guide_blur_css()

greeting = get_time_greeting()
st.title(f"{greeting}, {st.session_state.student_name}")
st.caption(f"**Branch:** {st.session_state.student_branch} | **Batch:** {st.session_state.get('student_batch', 'Batch A')} | **Verified Gmail:** {st.session_state.student_email}")

# Quick Mobile Bar for Batch, Semester & Logout
with st.expander("Quick Profile, Batch, Semester & Logout Controls (Mobile Friendly)", expanded=False):
    mob_c1, mob_c2, mob_c3 = st.columns(3)
    with mob_c1:
        current_batch_idx = BATCH_OPTIONS.index(st.session_state.get("student_batch", BATCH_OPTIONS[0])) if st.session_state.get("student_batch") in BATCH_OPTIONS else 0
        quick_batch = st.selectbox("Your Batch:", BATCH_OPTIONS, index=current_batch_idx, key="mob_batch_sel", disabled=guide_is_active)
        if quick_batch != st.session_state.get("student_batch"):
            st.session_state.student_batch = quick_batch
            save_student_compact(
                st.session_state.student_email,
                st.session_state.student_name,
                st.session_state.student_branch,
                st.session_state.student_batch,
                st.session_state.saved_semesters,
                st.session_state.daily_logs,
                st.session_state.daily_slot_ticks,
                st.session_state.slot7_extra_map,
            )
            st.rerun()
    with mob_c2:
        selected_semester = st.selectbox(
            "Choose Semester (1 to 8):",
            list(SEMESTER_DATA.keys()),
            index=0,
            key="mob_sem_sel",
            disabled=guide_is_active,
        )
    with mob_c3:
        st.write("")
        if st.button("Logout of This Device", key="mob_logout_btn", width="stretch", disabled=guide_is_active):
            try:
                cookie_manager.delete("att_device_auth_token")
            except Exception:
                pass
            st.session_state.manual_logout = True
            st.session_state.student_logged_in = False
            st.session_state.pop("saved_semesters", None)
            st.rerun()

# --- TOP BAR: DESIRED ATTENDANCE PERCENTAGE ---
st.markdown("### Custom Target Attendance Percentage")
t_col1, t_col2, t_col3 = st.columns([1.6, 1.4, 1])

with t_col1:
    preset_choice = st.radio(
        "Quick Select Desired Attendance %:",
        ["75% (Minimum)", "80%", "85%", "90%", "Custom %"],
        horizontal=True,
        index=0,
        disabled=guide_is_active,
    )

with t_col2:
    preset_map = {"75% (Minimum)": 75, "80%": 80, "85%": 85, "90%": 90}
    default_num_val = preset_map.get(preset_choice, st.session_state.get("target_attendance_pct", 75))
    target_att_pct = st.number_input(
        "Type Desired Attendance % (Min 75%):",
        min_value=75,
        max_value=100,
        value=int(default_num_val),
        step=1,
        disabled=guide_is_active,
    )
    if target_att_pct != st.session_state.get("target_attendance_pct", 75):
        st.session_state.target_attendance_pct = int(target_att_pct)
        save_student_compact(
            st.session_state.student_email,
            st.session_state.student_name,
            st.session_state.student_branch,
            st.session_state.get("student_batch", "Batch A"),
            st.session_state.saved_semesters,
            st.session_state.daily_logs,
            st.session_state.daily_slot_ticks,
            st.session_state.slot7_extra_map,
            target_attendance_pct=int(target_att_pct),
        )

with t_col3:
    st.write("")
    if st.button("Replay Feature Guide", disabled=guide_is_active, width="stretch"):
        st.session_state.guide_completed = False
        st.session_state.dashboard_guide_step = 1
        st.rerun()

# --- SIDEBAR CONTROLS ---
st.sidebar.header("Student Profile")
st.sidebar.write(f"**Name:** {st.session_state.student_name}")
st.sidebar.write(f"**Email:** {st.session_state.student_email}")
st.sidebar.write(f"**Branch:** {st.session_state.student_branch}")
st.sidebar.write(f"**Batch:** {st.session_state.get('student_batch', 'Batch A')}")

# --- ADMIN POWER PANEL (EXCLUSIVELY FOR KANISHKA VIA HASH/SECRETS VERIFICATION) ---
is_kanishka = st.session_state.student_email.strip().lower() == ADMIN_EMAIL
if is_kanishka:
    st.sidebar.markdown("---")
    st.sidebar.header("Admin Power Panel")
    admin_auth = st.sidebar.text_input("Enter Admin Password:", type="password", key="sidebar_admin_pwd")
    if verify_admin_password(admin_auth):
        st.sidebar.success("Admin Power Unlocked (Linked to your Gmail)")
        global_extras_current = load_admin_global_extras()
        st.sidebar.write("**Broadcast Extra Lectures (Visible to Everyone Else Other Than You):**")
        target_sem_for_admin = st.sidebar.selectbox("Select Semester:", list(SEMESTER_DATA.keys()), key="admin_sem_pick")
        admin_course_options = {f"{c['Short Form']} - {c['Course Name']} ({c['Course Code']})": c["Course Code"] for c in SEMESTER_DATA[target_sem_for_admin]}
        chosen_course_label = st.sidebar.selectbox("Select Subject:", list(admin_course_options.keys()), key="admin_subj_pick")
        chosen_course_code = admin_course_options[chosen_course_label]
        current_pushed_val = int(global_extras_current.get(chosen_course_code, 0))
        extra_count_to_push = st.sidebar.number_input(
            "Extra Lectures for All Other Students:",
            min_value=0,
            value=current_pushed_val,
            step=1,
            key="admin_extra_num",
        )

        if st.sidebar.button("Broadcast Extra Lectures to Other Students", width="stretch"):
            global_extras_current[chosen_course_code] = int(extra_count_to_push)
            save_admin_global_extras(global_extras_current)
            st.sidebar.success(f"Broadcasted {extra_count_to_push} extra lecture(s) for {chosen_course_code} to all other students!")

        if global_extras_current:
            st.sidebar.caption("Active Global Extra Lectures (Applied to other students):")
            st.sidebar.json(global_extras_current)

        with st.sidebar.expander("View Student Visitor Log (Admin Only)", expanded=False):
            if os.path.exists(VISITOR_LOG_FILE):
                log_df = pd.read_csv(VISITOR_LOG_FILE)
                log_df.index = range(1, len(log_df) + 1)
                st.dataframe(log_df, width="stretch")
            else:
                st.write("No students have logged in yet.")
    elif admin_auth:
        st.sidebar.error("Incorrect Admin Password.")

if st.sidebar.button("Switch Student / Logout", disabled=guide_is_active):
    try:
        cookie_manager.delete("att_device_auth_token")
    except Exception:
        pass
    st.session_state.manual_logout = True
    st.session_state.student_logged_in = False
    st.session_state.pop("saved_semesters", None)
    st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button(f"Reset {selected_semester} Missed Lectures to 0", disabled=guide_is_active):
    reset_df = pd.DataFrame(SEMESTER_DATA[selected_semester])
    reset_df.index = range(1, len(reset_df) + 1)
    st.session_state.saved_semesters[selected_semester] = reset_df
    st.session_state.daily_logs = {}
    st.session_state.daily_slot_ticks = {}
    st.session_state.slot7_extra_map = {}
    save_student_compact(
        st.session_state.student_email,
        st.session_state.student_name,
        st.session_state.student_branch,
        st.session_state.get("student_batch", "Batch A"),
        st.session_state.saved_semesters,
        st.session_state.daily_logs,
        st.session_state.daily_slot_ticks,
        st.session_state.slot7_extra_map,
    )
    st.rerun()

odd_semesters = ["Semester I", "Semester III", "Semester V", "Semester VII"]
if selected_semester == "Semester I":
    sem_start_date = datetime.date(2026, 9, 7)
    sem_end_date = datetime.date(2026, 12, 23)
    st.sidebar.info("**FE Sem I Official Window:**\n07 Sep 2026 to 23 Dec 2026")
elif selected_semester in odd_semesters:
    sem_start_date = st.sidebar.date_input("Semester Start Date:", value=datetime.date(2026, 7, 15), disabled=guide_is_active)
    sem_end_date = st.sidebar.date_input("Semester End Date:", value=datetime.date(2026, 11, 30), disabled=guide_is_active)
else:
    sem_start_date = st.sidebar.date_input("Semester Start Date:", value=datetime.date(2027, 1, 4), disabled=guide_is_active)
    sem_end_date = st.sidebar.date_input("Semester End Date:", value=datetime.date(2027, 5, 15), disabled=guide_is_active)

target_credits = st.sidebar.number_input(
    f"Target Credits ({selected_semester}):",
    min_value=1,
    max_value=200,
    value=22,
    step=1,
    disabled=guide_is_active,
)


# --- HELPER TO COMPUTE DERIVED COLUMNS ---
def compute_attendance_metrics(base_df, target_pct_val: int, current_user_email: str):
    t_ratio = target_pct_val / 100.0
    is_admin_user = current_user_email.strip().lower() == ADMIN_EMAIL
    global_extras = load_admin_global_extras()

    df = base_df.copy()
    df["Credits"] = pd.to_numeric(df["Credits"], errors="coerce").fillna(3).astype(int)
    df["Importance (1-3)"] = pd.to_numeric(df["Importance (1-3)"], errors="coerce").fillna(2).astype(int)
    df["Total Lectures"] = pd.to_numeric(df["Total Lectures"], errors="coerce").fillna(1).replace(0, 1).astype(int)
    if "Unattended" not in df.columns:
        df["Unattended"] = 0
    df["Unattended"] = pd.to_numeric(df["Unattended"], errors="coerce").fillna(0).clip(lower=0).astype(int)
    df["Unattended"] = df[["Unattended", "Total Lectures"]].min(axis=1)

    if "Extra Lectures Attended" not in df.columns:
        df["Extra Lectures Attended"] = 0
    df["Extra Lectures Attended"] = pd.to_numeric(df["Extra Lectures Attended"], errors="coerce").fillna(0).clip(lower=0).astype(int)

    if not is_admin_user:
        df["Admin Broadcast Extra"] = df["Course Code"].apply(lambda c: int(global_extras.get(c, 0)))
    else:
        df["Admin Broadcast Extra"] = 0

    df["Total Extra Lectures"] = df["Extra Lectures Attended"] + df["Admin Broadcast Extra"]
    df["Regular Attended"] = (df["Total Lectures"] - df["Unattended"]).clip(lower=0)
    df["Effective Attended"] = (df["Regular Attended"] + df["Total Extra Lectures"]).clip(upper=df["Total Lectures"])
    df["Effective Unattended"] = (df["Total Lectures"] - df["Effective Attended"]).clip(lower=0)

    df["Unattended / Total"] = df["Unattended"].astype(str) + " / " + df["Total Lectures"].astype(str)
    df["Current Attendance %"] = ((df["Effective Attended"] / df["Total Lectures"]) * 100).round(2)

    df["Required for Target"] = df["Total Lectures"].apply(lambda tot: math.ceil(t_ratio * tot))
    df["Classes Needed for Target"] = (df["Required for Target"] - df["Effective Attended"]).clip(lower=0)
    df["Max Allowed Bunks"] = df["Total Lectures"] - df["Required for Target"]
    df["Safe Bunks Left"] = (df["Max Allowed Bunks"] - df["Effective Unattended"]).clip(lower=0)
    df["Status"] = df["Current Attendance %"].apply(
        lambda x: f"Safe (>={target_att_pct}%)" if x >= target_att_pct else f"Shortage (<{target_att_pct}%)"
    )
    return df


# --- SECTION 1: INTERACTIVE SUBJECT TABLE ---
sec1_wrapper = st.container()
with sec1_wrapper:
    if guide_is_active and active_step in [2, 3, 4]:
        st.markdown('<div class="blur-target-block"></div>', unsafe_allow_html=True)

    st.subheader(f"1. {selected_semester} Subjects & Unattended Lectures Input")
    st.markdown(
        '<div class="missed-lectures-banner">ENTER HOW MANY LECTURES YOU HAVE MISSED</div>',
        unsafe_allow_html=True,
    )
    st.caption("Tap or double-click **Unattended** (missed lectures, default 0), **Extra Lectures Attended**, or **Importance (1-3)** to update. Synced with Section 3 Calendar Ticks and Section 4.")

    if guide_is_active and active_step == 1:
        s1_col_main, s1_col_guide = st.columns([2.2, 1])
    else:
        s1_col_main = st.container()
        s1_col_guide = None

    with s1_col_main:
        current_sem_df = st.session_state.saved_semesters[selected_semester]
        sec1_disabled_cols = (
            list(current_sem_df.columns)
            if guide_is_active
            else ["Course Category", "Course Code", "Short Form", "Course Name", "Credits", "Total Lectures"]
        )
        edited_sec1 = st.data_editor(
            current_sem_df,
            num_rows="fixed",
            disabled=sec1_disabled_cols,
            column_config={
                "Unattended": st.column_config.NumberColumn("Unattended Lectures (Missed)", min_value=0, default=0, step=1),
                "Extra Lectures Attended": st.column_config.NumberColumn("Extra Lectures Attended", min_value=0, default=0, step=1),
            },
            width="stretch",
            key=f"sec1_editor_{selected_semester}",
        )

        if not guide_is_active and not edited_sec1.equals(current_sem_df):
            st.session_state.saved_semesters[selected_semester] = edited_sec1.copy()
            save_student_compact(
                st.session_state.student_email,
                st.session_state.student_name,
                st.session_state.student_branch,
                st.session_state.get("student_batch", "Batch A"),
                st.session_state.saved_semesters,
                st.session_state.daily_logs,
                st.session_state.daily_slot_ticks,
                st.session_state.slot7_extra_map,
            )
            st.rerun()

    if s1_col_guide is not None:
        with s1_col_guide:
            render_side_guide_card(
                1,
                4,
                "Step 1: Enter How Many Lectures You Have Missed",
                "This arrow points to Section 1. Enter any lectures you have missed in 'Unattended' and any 'Extra Lectures Attended'. Click the blinking blue 'Got it' button below to proceed.",
                "dashboard_guide_step",
                arrow_dir="left",
            )

df = compute_attendance_metrics(
    st.session_state.saved_semesters[selected_semester],
    target_att_pct,
    st.session_state.student_email,
)

if not is_kanishka and int(df["Admin Broadcast Extra"].sum()) > 0:
    st.info(f"Admin Broadcast Active: {int(df['Admin Broadcast Extra'].sum())} extra college-wide lecture(s) have been automatically included in your attendance calculation.")

subject_stats_by_short = {}
for _, r in df.iterrows():
    sf = r["Short Form"]
    subject_stats_by_short[sf] = {
        "code": r["Course Code"],
        "name": r["Course Name"],
        "unattended": int(r["Unattended"]),
        "regular_attended": int(r["Regular Attended"]),
        "extra": int(r["Total Extra Lectures"]),
        "effective": int(r["Effective Attended"]),
        "total": int(r["Total Lectures"]),
        "pct": float(r["Current Attendance %"]),
        "req_target": int(r["Required for Target"]),
        "needed": int(r["Classes Needed for Target"]),
        "bunks": int(r["Safe Bunks Left"]),
    }

# --- SECTION 2: DASHBOARD METRICS ---
sec2_wrapper = st.container()
with sec2_wrapper:
    if guide_is_active:
        st.markdown('<div class="blur-target-block"></div>', unsafe_allow_html=True)

    st.markdown("---")
    st.subheader(f"2. {selected_semester} {target_att_pct}% Target Summary")

    overall_att = (df["Effective Attended"].sum() / df["Total Lectures"].sum()) * 100
    total_unattended = int(df["Unattended"].sum())
    total_safe_bunks = int(df["Safe Bunks Left"].sum())
    total_classes_needed = int(df["Classes Needed for Target"].sum())

    mcol1, mcol2, mcol3, mcol
