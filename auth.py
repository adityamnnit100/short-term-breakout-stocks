"""Authentication helpers for the Streamlit dashboard."""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
from getpass import getpass
from pathlib import Path
from typing import Dict, List, Optional


HASH_ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 260_000
DB_PATH = os.environ.get(
    "ALPHASCANNER_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "breakout_history.db"),
)
WORKSPACE_FIELDS = {
    "watchlist": [],
    "trade_journal": [],
    "portfolio_positions": [],
    "portfolios": [],
    "notes": [],
}
USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]{3,32}$")


def _connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def hash_password(password: str, iterations: int = DEFAULT_ITERATIONS) -> str:
    """Return a salted PBKDF2-SHA256 password hash suitable for secrets config."""
    salt = secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    encoded_digest = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"{HASH_ALGORITHM}${iterations}${salt}${encoded_digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored PBKDF2 hash."""
    try:
        algorithm, iterations, salt, encoded_digest = stored_hash.split("$", 3)
        if algorithm != HASH_ALGORITHM:
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        )
        candidate_digest = base64.urlsafe_b64encode(candidate).decode("ascii")
        return hmac.compare_digest(candidate_digest, encoded_digest)
    except (TypeError, ValueError, OverflowError):
        return False


def normalize_username(username: str) -> str:
    return username.strip().lower()


def validate_username(username: str) -> str:
    username = normalize_username(username)
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("Username must be 3-32 characters using letters, numbers, dot, dash, or underscore.")
    return username


def init_auth_db() -> None:
    conn = _connect_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_users (
            username      TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            is_admin      INTEGER NOT NULL DEFAULT 0,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_workspace (
            username                 TEXT PRIMARY KEY,
            watchlist_json           TEXT NOT NULL DEFAULT '[]',
            trade_journal_json       TEXT NOT NULL DEFAULT '[]',
            portfolio_positions_json TEXT NOT NULL DEFAULT '[]',
            portfolios_json          TEXT NOT NULL DEFAULT '[]',
            notes_json               TEXT NOT NULL DEFAULT '[]',
            updated_at               DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(user_workspace)").fetchall()
    }
    if "portfolios_json" not in columns:
        conn.execute("ALTER TABLE user_workspace ADD COLUMN portfolios_json TEXT NOT NULL DEFAULT '[]'")
    if "notes_json" not in columns:
        conn.execute("ALTER TABLE user_workspace ADD COLUMN notes_json TEXT NOT NULL DEFAULT '[]'")
    conn.commit()
    conn.close()


def _get_secret_auth_config() -> dict:
    secret_paths = [
        Path.cwd() / ".streamlit" / "secrets.toml",
        Path.home() / ".streamlit" / "secrets.toml",
    ]
    if not any(path.exists() for path in secret_paths):
        return {}

    import streamlit as st
    try:
        return dict(st.secrets.get("auth", {}))
    except Exception:
        return {}


def signup_enabled() -> bool:
    value = os.environ.get("ALPHASCANNER_ALLOW_SIGNUP")
    if value is not None:
        return value.strip().lower() not in {"0", "false", "no", "off"}

    auth_config = _get_secret_auth_config()
    value = auth_config.get("allow_signup", True)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def get_signup_code() -> str:
    env_code = os.environ.get("ALPHASCANNER_SIGNUP_CODE", "").strip()
    if env_code:
        return env_code
    auth_config = _get_secret_auth_config()
    return str(auth_config.get("signup_code", "")).strip()


def load_config_users() -> Dict[str, str]:
    """Load username -> password_hash from Streamlit secrets and environment."""
    users: Dict[str, str] = {}

    auth_config = _get_secret_auth_config()
    configured_users = auth_config.get("users", {})
    if hasattr(configured_users, "items"):
        users.update({normalize_username(str(username)): str(password_hash) for username, password_hash in configured_users.items()})

    single_username = auth_config.get("username")
    single_password_hash = auth_config.get("password_hash")
    if single_username and single_password_hash:
        users[normalize_username(str(single_username))] = str(single_password_hash)

    env_username = os.environ.get("ALPHASCANNER_AUTH_USERNAME")
    env_password_hash = os.environ.get("ALPHASCANNER_AUTH_PASSWORD_HASH")
    if env_username and env_password_hash:
        users[normalize_username(env_username)] = env_password_hash

    return users


def load_db_users() -> Dict[str, str]:
    init_auth_db()
    conn = _connect_db()
    rows = conn.execute("SELECT username, password_hash FROM auth_users").fetchall()
    conn.close()
    return {username: password_hash for username, password_hash in rows}


def load_users() -> Dict[str, str]:
    """Load username -> password_hash from config and the local user database."""
    users = load_config_users()
    users.update(load_db_users())
    return users


def is_admin_user(username: str) -> bool:
    username = normalize_username(username)
    if username in load_config_users():
        return True

    init_auth_db()
    conn = _connect_db()
    row = conn.execute("SELECT is_admin FROM auth_users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return bool(row and row[0])


def is_current_user_admin() -> bool:
    import streamlit as st

    return bool(st.session_state.get("auth_is_admin"))


def list_accounts() -> List[dict]:
    config_users = load_config_users()
    accounts = [
        {"username": username, "is_admin": True, "source": "config"}
        for username in sorted(config_users)
    ]

    init_auth_db()
    conn = _connect_db()
    rows = conn.execute("SELECT username, is_admin FROM auth_users ORDER BY username").fetchall()
    conn.close()
    accounts.extend(
        {"username": username, "is_admin": bool(is_admin), "source": "database"}
        for username, is_admin in rows
    )
    return accounts


def create_user(username: str, password: str, is_admin: bool = False) -> None:
    username = validate_username(username)
    if username in load_config_users():
        raise ValueError("That username is managed in secrets/environment config.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    init_auth_db()
    conn = _connect_db()
    try:
        conn.execute(
            """
            INSERT INTO auth_users (username, password_hash, is_admin)
            VALUES (?, ?, ?)
            """,
            (username, hash_password(password), int(is_admin)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError("That username already exists.")
    finally:
        conn.close()


def create_signup_user(username: str, password: str, invite_code: str = "") -> None:
    if not signup_enabled():
        raise ValueError("Public sign-up is disabled.")

    required_code = get_signup_code()
    if required_code and not hmac.compare_digest(invite_code.strip(), required_code):
        raise ValueError("Invite code is incorrect.")

    create_user(username, password, is_admin=not bool(load_users()))


def update_user_password(username: str, password: str) -> None:
    username = normalize_username(username)
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    init_auth_db()
    conn = _connect_db()
    cur = conn.execute(
        "UPDATE auth_users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE username = ?",
        (hash_password(password), username),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise ValueError("Only database users can be updated here.")


def delete_user(username: str) -> None:
    username = normalize_username(username)
    init_auth_db()
    conn = _connect_db()
    conn.execute("DELETE FROM auth_users WHERE username = ?", (username,))
    conn.execute("DELETE FROM user_workspace WHERE username = ?", (username,))
    conn.commit()
    conn.close()


def load_user_workspace(username: str) -> dict:
    username = normalize_username(username)
    init_auth_db()
    conn = _connect_db()
    row = conn.execute(
        """
        SELECT watchlist_json, trade_journal_json, portfolio_positions_json, portfolios_json, notes_json
        FROM user_workspace
        WHERE username = ?
        """,
        (username,),
    ).fetchone()
    conn.close()

    if not row:
        return {field: list(default_value) for field, default_value in WORKSPACE_FIELDS.items()}

    values = {}
    for field, raw_value in zip(WORKSPACE_FIELDS, row):
        try:
            loaded = json.loads(raw_value)
            values[field] = loaded if isinstance(loaded, list) else []
        except (TypeError, json.JSONDecodeError):
            values[field] = []
    return values


def load_workspace_into_session(username: str) -> None:
    import streamlit as st

    for field, value in load_user_workspace(username).items():
        st.session_state[field] = value


def save_user_workspace(username: str, workspace: dict) -> None:
    username = normalize_username(username)
    init_auth_db()
    payload = {
        field: json.dumps(workspace.get(field, []), ensure_ascii=False)
        for field in WORKSPACE_FIELDS
    }
    conn = _connect_db()
    conn.execute(
        """
        INSERT INTO user_workspace (
            username,
            watchlist_json,
            trade_journal_json,
            portfolio_positions_json,
            portfolios_json,
            notes_json,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(username) DO UPDATE SET
            watchlist_json = excluded.watchlist_json,
            trade_journal_json = excluded.trade_journal_json,
            portfolio_positions_json = excluded.portfolio_positions_json,
            portfolios_json = excluded.portfolios_json,
            notes_json = excluded.notes_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            username,
            payload["watchlist"],
            payload["trade_journal"],
            payload["portfolio_positions"],
            payload["portfolios"],
            payload["notes"],
        ),
    )
    conn.commit()
    conn.close()


def save_current_user_workspace() -> None:
    import streamlit as st

    username = get_current_user()
    if not username:
        return
    save_user_workspace(
        username,
        {field: st.session_state.get(field, []) for field in WORKSPACE_FIELDS},
    )


def get_current_user() -> Optional[str]:
    import streamlit as st

    if st.session_state.get("authenticated"):
        return st.session_state.get("auth_user")
    return None


def logout() -> None:
    import streamlit as st

    st.session_state.clear()
    st.rerun()


def render_logout_control() -> None:
    import streamlit as st

    current_user = get_current_user()
    if not current_user:
        return

    with st.sidebar:
        st.caption(f"Signed in as `{current_user}`")
        if st.button("Logout", use_container_width=True, key="auth_logout"):
            logout()


def require_login() -> None:
    """Render the login screen and stop execution until the user is authenticated."""
    import streamlit as st

    current_user = get_current_user()
    if current_user:
        st.session_state.auth_is_admin = is_admin_user(current_user)
        if st.session_state.get("workspace_loaded_for") != current_user:
            load_workspace_into_session(current_user)
            st.session_state.workspace_loaded_for = current_user
        return

    users = load_users()

    st.session_state.setdefault("authenticated", False)

    if not users and not signup_enabled():
        _, setup_col, _ = st.columns([1, 1.1, 1])
        with setup_col:
            st.error("No login users are configured yet.")
            st.info(
                "Create a password hash with `python -m alphascanner_ui.auth`, then add it to "
                "`.streamlit/secrets.toml` or set `ALPHASCANNER_AUTH_USERNAME` and "
                "`ALPHASCANNER_AUTH_PASSWORD_HASH` in your environment."
            )
        st.stop()

    st.markdown(
        """
        <style>
            div[data-testid="stHorizontalBlock"]:has(.auth-anchor) {
                align-items: center;
            }
            .auth-hero {
                background: linear-gradient(180deg, rgba(13,26,46,0.94) 0%, rgba(11,23,40,0.98) 100%);
                border: 1px solid rgba(0,229,255,0.18);
                border-radius: 12px;
                padding: 22px 24px;
                margin: 7vh auto 18px;
                box-shadow: 0 14px 36px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.04);
            }
            .auth-kicker {
                color: #22d3ee;
                font-family: 'JetBrains Mono', monospace;
                font-size: 0.72rem;
                font-weight: 700;
                letter-spacing: 0.14rem;
                text-transform: uppercase;
                border-left: 3px solid #22d3ee;
                padding-left: 10px;
                margin-bottom: 18px;
            }
            .auth-title {
                color: #e8f0fe;
                font-size: 1.75rem;
                font-weight: 800;
                letter-spacing: 0;
                margin-bottom: 8px;
            }
            .auth-subtitle {
                color: #cbd5e1;
                font-size: 0.92rem;
                line-height: 1.5;
            }
            .auth-help {
                color: #cbd5e1;
                font-size: 0.82rem;
                margin: 8px 0 12px;
            }
            @media (max-width: 900px) {
                .auth-hero { margin-top: 2vh; }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _, auth_col, _ = st.columns([1, 0.78, 1])
    with auth_col:
        st.markdown(
            """
            <span class="auth-anchor"></span>
            <div class="auth-hero">
                <div class="auth-kicker">Private Workspace</div>
                <div class="auth-title">AlphaScanner PRO</div>
                <div class="auth-subtitle">Sign in to access scanner signals, watchlists, portfolio analysis, journal, and risk tools.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if signup_enabled():
            login_tab, signup_tab = st.tabs(["Login", "Sign Up"])
        else:
            login_tab = st.container()
            signup_tab = None

        with login_tab:
            with st.form("login_form"):
                username = st.text_input("Username", autocomplete="username")
                password = st.text_input("Password", type="password", autocomplete="current-password")
                submitted = st.form_submit_button("Login", use_container_width=True)

            if submitted:
                clean_username = normalize_username(username)
                stored_hash = users.get(clean_username)
                if stored_hash and verify_password(password, stored_hash):
                    st.session_state.authenticated = True
                    st.session_state.auth_user = clean_username
                    st.session_state.auth_is_admin = is_admin_user(clean_username)
                    st.session_state.pop("auth_error", None)
                    load_workspace_into_session(clean_username)
                    st.session_state.workspace_loaded_for = clean_username
                    st.rerun()

                st.session_state.auth_error = "Invalid username or password."

            if st.session_state.get("auth_error"):
                st.error(st.session_state.auth_error)

        if signup_tab is not None:
            with signup_tab:
                st.markdown(
                    '<div class="auth-help">Create your own account. If an invite code is enabled, ask the site owner for it.</div>',
                    unsafe_allow_html=True,
                )
                with st.form("signup_form"):
                    signup_username = st.text_input("Choose username", autocomplete="username", key="signup_username")
                    signup_password = st.text_input("Choose password", type="password", autocomplete="new-password", key="signup_password")
                    signup_confirm = st.text_input("Confirm password", type="password", autocomplete="new-password", key="signup_confirm")
                    invite_code = ""
                    if get_signup_code():
                        invite_code = st.text_input("Invite code", type="password", key="signup_invite")
                    signup_submitted = st.form_submit_button("Create Account", use_container_width=True)

                if signup_submitted:
                    if signup_password != signup_confirm:
                        st.error("Passwords do not match.")
                    else:
                        try:
                            create_signup_user(signup_username, signup_password, invite_code)
                            clean_username = normalize_username(signup_username)
                            st.session_state.authenticated = True
                            st.session_state.auth_user = clean_username
                            st.session_state.auth_is_admin = is_admin_user(clean_username)
                            load_workspace_into_session(clean_username)
                            st.session_state.workspace_loaded_for = clean_username
                            st.success("Account created.")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))

    st.stop()


def render_user_management() -> None:
    """Render account controls for the current user and admins."""
    import pandas as pd
    import streamlit as st

    current_user = get_current_user()
    if not current_user:
        return

    st.divider()
    st.markdown("### My Account")
    if current_user in load_config_users():
        st.info("Your owner/admin account is managed from secrets or environment variables.")
    else:
        with st.form("auth_change_own_password"):
            current_password = st.text_input("Current password", type="password", key="auth_current_password")
            new_password = st.text_input("New password", type="password", key="auth_own_new_password")
            submitted = st.form_submit_button("Change My Password", use_container_width=True)
        if submitted:
            stored_hash = load_users().get(current_user)
            if not stored_hash or not verify_password(current_password, stored_hash):
                st.error("Current password is incorrect.")
            else:
                try:
                    update_user_password(current_user, new_password)
                    st.success("Password updated.")
                except ValueError as exc:
                    st.error(str(exc))

    if not is_current_user_admin():
        return

    st.divider()
    st.markdown("### Account Access")
    st.caption("Create one account per person. Share the site URL, then give each person only their own username and password.")

    accounts = list_accounts()
    if accounts:
        st.dataframe(
            pd.DataFrame(accounts),
            use_container_width=True,
            hide_index=True,
            column_config={
                "username": "Username",
                "is_admin": "Admin",
                "source": "Source",
            },
        )

    with st.expander("Add User", expanded=False):
        with st.form("auth_create_user"):
            new_username = st.text_input("Username", key="auth_new_username")
            new_password = st.text_input("Temporary password", type="password", key="auth_new_password")
            new_is_admin = st.checkbox("Admin access", key="auth_new_is_admin")
            submitted = st.form_submit_button("Create User", use_container_width=True)
        if submitted:
            try:
                create_user(new_username, new_password, new_is_admin)
                st.success(f"Created account for {normalize_username(new_username)}.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    db_usernames = [account["username"] for account in accounts if account["source"] == "database"]
    if db_usernames:
        with st.expander("Manage Database User", expanded=False):
            selected_user = st.selectbox("User", db_usernames, key="auth_manage_user")
            reset_password = st.text_input("New password", type="password", key="auth_reset_password")
            reset_col, delete_col = st.columns(2)
            with reset_col:
                if st.button("Reset Password", use_container_width=True):
                    try:
                        update_user_password(selected_user, reset_password)
                        st.success(f"Password updated for {selected_user}.")
                    except ValueError as exc:
                        st.error(str(exc))
            with delete_col:
                delete_disabled = selected_user == get_current_user()
                if st.button("Delete User", use_container_width=True, disabled=delete_disabled):
                    delete_user(selected_user)
                    st.success(f"Deleted {selected_user}.")
                    st.rerun()


def _main() -> None:
    password = sys.argv[1] if len(sys.argv) > 1 else getpass("Password to hash: ")
    print(hash_password(password))


if __name__ == "__main__":
    _main()
