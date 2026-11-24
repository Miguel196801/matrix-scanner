import importlib
import regia_tracker
import pattern_engine
# Ricarica sempre pattern_engine da disco per evitare cache stantie dei moduli in Streamlit
pattern_engine = importlib.reload(pattern_engine)
# MATRIX DVMS V6.1.3 Desktop - Terminale Trader Professionale
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import math
import warnings
import json
import os
import re
import hashlib
import hmac
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')
st.set_page_config(page_title="MATRIX DVMS V6.1.3 PRO", layout="wide", page_icon="🛡️")

# ==============================================================================
# AUTENTICAZIONE & SCHERMATA DI LOGIN (STILE EV ROADBOOK ITALIA — MOBILE-FIRST)
# ==============================================================================
UTENTI_AUTH_FILE = "utenti_auth.json"
UTENTE_PREDEFINITO_AUTH = "Fabio"
PASSWORD_INIZIALE_AUTH = "matrix2026"

# Mappa completa dei profili Multi-Utente (file, saluto e capitale versato predefinito)
PROFILI_UTENTE_MATRIX = {
    "fabio": {
        "nome": "Fabio",
        "portafoglio": "portafoglio.json",
        "impostazioni": "impostazioni.json",
        "segnali_attivi": "segnali_attivi.json",
        "regia_tracker": "regia_tracker.json",
        "skip_regia": "skip_regia.json",
        "registro_vendite": "registro_vendite.json",
        "registro_acquisti": "registro_acquisti.json",
        "minusvalenze": "minusvalenze.json",
        "saluto": "👋 Ciao Fabio, buon trading!",
        "capitale_versato_default": 29.10,
        "usa_portafoglio_iniziale": True,
    },
    "lisi": {
        "nome": "Lisi",
        "portafoglio": "portafoglio_lisi.json",
        "impostazioni": "impostazioni_lisi.json",
        "segnali_attivi": "segnali_attivi_lisi.json",
        "regia_tracker": "regia_tracker_lisi.json",
        "skip_regia": "skip_regia_lisi.json",
        "registro_vendite": "registro_vendite_lisi.json",
        "registro_acquisti": "registro_acquisti_lisi.json",
        "minusvalenze": "minusvalenze_lisi.json",
        "saluto": "👋 Benvenuta Lisi nel tuo MATRIX PRO!",
        "capitale_versato_default": 310.00,
        "usa_portafoglio_iniziale": False,
    },
    "alessia": {
        "nome": "Alessia",
        "portafoglio": "portafoglio_alessia.json",
        "impostazioni": "impostazioni_alessia.json",
        "segnali_attivi": "segnali_attivi_alessia.json",
        "regia_tracker": "regia_tracker_alessia.json",
        "skip_regia": "skip_regia_alessia.json",
        "registro_vendite": "registro_vendite_alessia.json",
        "registro_acquisti": "registro_acquisti_alessia.json",
        "minusvalenze": "minusvalenze_alessia.json",
        "saluto": "👋 Ciao Alessia, benvenuta nel tuo MATRIX PRO!",
        "capitale_versato_default": 0.00,
        "usa_portafoglio_iniziale": False,
    },
}

def _get_profilo_utente_corrente():
    """Restituisce il profilo attivo in base a st.session_state['utente_corrente'] (case-insensitive)."""
    u_raw = str(
        st.session_state.get("utente_corrente")
        or st.session_state.get("utente_autenticato")
        or UTENTE_PREDEFINITO_AUTH
    ).strip()
    u_key = u_raw.lower()
    if u_key in PROFILI_UTENTE_MATRIX:
        return dict(PROFILI_UTENTE_MATRIX[u_key], chiave=u_key)
    # Fallback dinamico per eventuali altri utenti aggiunti in st.secrets["users"]
    safe_key = re.sub(r"[^a-z0-9_]", "_", u_key) or "ospite"
    return {
        "chiave": safe_key,
        "nome": u_raw or "Utente",
        "portafoglio": f"portafoglio_{safe_key}.json",
        "impostazioni": f"impostazioni_{safe_key}.json",
        "segnali_attivi": f"segnali_attivi_{safe_key}.json",
        "regia_tracker": f"regia_tracker_{safe_key}.json",
        "skip_regia": f"skip_regia_{safe_key}.json",
        "registro_vendite": f"registro_vendite_{safe_key}.json",
        "registro_acquisti": f"registro_acquisti_{safe_key}.json",
        "minusvalenze": f"minusvalenze_{safe_key}.json",
        "saluto": f"👋 Benvenuto {u_raw or 'Utente'} nel tuo MATRIX PRO!",
        "capitale_versato_default": 0.00,
        "usa_portafoglio_iniziale": False,
    }

def _reset_sessione_utente():
    """Pulisce tutti i dati di sessione dipendenti dall'utente al Login, Cambio Utente o Logout."""
    chiavi_reset = [
        "portafoglio", "tickers_input", "_pending_tickers_input", "sb_quick_ticker",
        "sb_ticker_radio", "port_selected_chart", "sel_chart_port_side",
        "txt_analisi_singola_tk", "df_fortezza", "df_cavalli", "df_monitor",
        "df_palantir", "scansione_completata", "analisi_risultati", "dashboard_stats",
        "last_update", "pyramiding_alerts", "take_profit_alerts",
        "zona_interesse_alerts", "piano_ribilanciamento", "risultato_simulazione",
        "risultato_podc", "piano_allocazione", "breakout_tickers",
        "liquidita_totale_alloc", "pattern_alerts", "pattern_singola_attivo",
        "_msg_reload_disk", "_gh_last_msg", "_utente_sessione_caricato",
    ]
    for k in chiavi_reset:
        st.session_state.pop(k, None)
    # Rimuove anche tutti i flag di pull GitHub così il nuovo utente ricarica i propri file da zero
    for k in [k for k in list(st.session_state.keys()) if str(k).startswith("_gh_pulled_")]:
        st.session_state.pop(k, None)

def _hash_password_sha256(password_chiaro):
    """Restituisce l'hash SHA-256 esadecimale della password."""
    return hashlib.sha256(str(password_chiaro).encode("utf-8")).hexdigest()

def _normalizza_hash_auth(valore):
    """Accetta sia un hash SHA-256 (64 char hex) sia una password testuale da st.secrets."""
    s = str(valore or "").strip()
    if len(s) == 64 and all(c in "0123456789abcdefABCDEF" for c in s):
        return s.lower()
    return _hash_password_sha256(s)

def _get_auth_file_path():
    """Percorso locale assoluto di utenti_auth.json (mai sincronizzato su GitHub)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), UTENTI_AUTH_FILE)

def _salva_utenti_auth_locale(mappa_raw):
    """Salva su disco locale il file utenti_auth.json con gli hash SHA-256."""
    fp = _get_auth_file_path()
    try:
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(mappa_raw, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False

def _assicura_file_utenti_auth():
    """Carica utenti_auth.json locale; se manca lo crea al primo avvio con Fabio, Lisi e Alessia."""
    fp = _get_auth_file_path()
    dati = {}
    if os.path.exists(fp):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                caricato = json.load(f)
            if isinstance(caricato, dict) and caricato:
                dati = caricato
        except Exception:
            dati = {}
    aggiornato = False
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    h_def = _hash_password_sha256(PASSWORD_INIZIALE_AUTH)
    for prof in PROFILI_UTENTE_MATRIX.values():
        nome_u = prof["nome"]
        if not any(str(k).strip().lower() == nome_u.lower() for k in dati.keys()):
            dati[nome_u] = {
                "username": nome_u,
                "password_hash": h_def,
                "aggiornato_il": now_str,
            }
            aggiornato = True
    if aggiornato or not os.path.exists(fp):
        _salva_utenti_auth_locale(dati)
    return dati

def _carica_mappa_credenziali():
    """
    Restituisce una mappa case-insensitive:
    {utente_lower: {"username": str, "hashes": [sha256, ...], "locale": bool}}
    combinando utenti_auth.json locale ed eventuale st.secrets['users'] (Streamlit Cloud).
    """
    mappa = {}
    dati_loc = _assicura_file_utenti_auth()
    for k, v in dati_loc.items():
        if isinstance(v, dict):
            uname = str(v.get("username") or k).strip()
            phash = str(v.get("password_hash") or v.get("hash") or "").strip().lower()
        else:
            uname = str(k).strip()
            phash = _normalizza_hash_auth(v)
        if uname and phash:
            mappa[uname.lower()] = {"username": uname, "hashes": [phash], "locale": True}

    # Supporto opzionale Streamlit Cloud via st.secrets["users"]
    try:
        if "users" in st.secrets:
            sec_users = st.secrets["users"]
            for k in sec_users:
                uname = str(k).strip()
                phash = _normalizza_hash_auth(sec_users[k])
                if not uname or not phash:
                    continue
                kl = uname.lower()
                if kl in mappa:
                    if phash not in mappa[kl]["hashes"]:
                        mappa[kl]["hashes"].append(phash)
                else:
                    mappa[kl] = {"username": uname, "hashes": [phash], "locale": False}
    except Exception:
        pass
    return mappa

def _verifica_credenziali_matrix(username, password):
    """Verifica utente (case-insensitive) e password tramite confronto hash SHA-256 sicuro."""
    u_clean = str(username or "").strip().lower()
    if not u_clean or not password:
        return False, ""
    mappa = _carica_mappa_credenziali()
    info = mappa.get(u_clean)
    if not info:
        return False, ""
    h_in = _hash_password_sha256(password)
    for h_ok in info.get("hashes", []):
        if hmac.compare_digest(h_in, str(h_ok).lower()):
            return True, info["username"]
    return False, ""

def _cambia_password_utente_locale(username, vecchia_pwd, nuova_pwd):
    """Aggiorna la password (hash SHA-256) in utenti_auth.json locale dopo verifica della vecchia."""
    ok_old, nome_canonico = _verifica_credenziali_matrix(username, vecchia_pwd)
    if not ok_old:
        return False, "La password attuale non è corretta."
    if len(str(nuova_pwd or "")) < 4:
        return False, "La nuova password deve contenere almeno 4 caratteri."
    dati_loc = _assicura_file_utenti_auth()
    chiave_esistente = next((k for k in dati_loc.keys() if str(k).strip().lower() == nome_canonico.lower()), nome_canonico)
    dati_loc[chiave_esistente] = {
        "username": nome_canonico,
        "password_hash": _hash_password_sha256(nuova_pwd),
        "aggiornato_il": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if _salva_utenti_auth_locale(dati_loc):
        return True, "Password aggiornata e salvata in utenti_auth.json."
    return False, "Impossibile scrivere utenti_auth.json (ambiente in sola lettura)."

def richiedi_login_matrix():
    """
    Blocca l'accesso all'intera app finché st.session_state['autenticato'] non è True.
    Mostra esclusivamente la schermata di login mobile-first stile EV Roadbook Italia.
    """
    if "autenticato" not in st.session_state:
        st.session_state["autenticato"] = False
    if st.session_state["autenticato"]:
        return

    # Assicura che utenti_auth.json venga inizializzato già al primo avvio
    _assicura_file_utenti_auth()

    st.markdown(
        """
        <style>
        html, body, [data-testid="stAppViewContainer"], .stApp, .main {
            background-color: #0F172A !important;
            color: #F8FAFC !important;
        }
        section[data-testid="stSidebar"],
        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapsedControl"] {
            display: none !important;
        }
        header[data-testid="stHeader"] {
            background: transparent !important;
        }
        [data-testid="stMainBlockContainer"],
        .main .block-container {
            padding-top: 7vh !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            padding-bottom: 2rem !important;
            max-width: 1280px !important;
            margin: 0 auto !important;
        }
        .matrix-login-header-card {
            background-color: #1E293B;
            border: 1px solid #334155;
            border-left: 5px solid #10B981;
            border-radius: 12px;
            padding: 1.30rem 1.45rem;
            margin: 0 auto 0.95rem auto;
            max-width: 480px;
            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
        }
        div[data-testid="stForm"] {
            background-color: #1E293B !important;
            border: 1px solid #334155 !important;
            border-left: 5px solid #10B981 !important;
            border-radius: 12px !important;
            padding: 1.55rem 1.45rem 1.35rem 1.45rem !important;
            max-width: 480px !important;
            margin: 0 auto !important;
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.50) !important;
        }
        div[data-testid="stForm"] label,
        div[data-testid="stForm"] label p {
            color: #F8FAFC !important;
            font-weight: 600 !important;
            font-size: 0.92rem !important;
        }
        div[data-testid="stForm"] input {
            background-color: #0F172A !important;
            color: #F8FAFC !important;
            border: 1px solid #334155 !important;
            border-radius: 8px !important;
        }
        div[data-testid="stForm"] input:focus {
            border-color: #10B981 !important;
            box-shadow: 0 0 0 1px #10B981 !important;
        }
        div[data-testid="stFormSubmitButton"] button {
            background-color: #10B981 !important;
            border: 1px solid #10B981 !important;
            color: #FFFFFF !important;
            font-weight: 700 !important;
            font-size: 1rem !important;
            min-height: 46px !important;
            border-radius: 8px !important;
            margin-top: 0.45rem !important;
            transition: background-color 0.15s ease !important;
        }
        div[data-testid="stFormSubmitButton"] button:hover {
            background-color: #059669 !important;
            border-color: #059669 !important;
        }
        @media (max-width: 768px) {
            [data-testid="stMainBlockContainer"],
            .main .block-container {
                padding-top: 4vh !important;
                padding-left: 0.75rem !important;
                padding-right: 0.75rem !important;
            }
            .matrix-login-header-card {
                padding: 1.15rem 1.15rem;
            }
            div[data-testid="stForm"] {
                padding: 1.25rem 1.15rem 1.15rem 1.15rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Colonna centrale centrata e ristretta stile EV Roadbook Italia (responsive su desktop e mobile)
    _, col_login, _ = st.columns([1.2, 1.5, 1.2])
    with col_login:
        # Card di intestazione scura con bordo sinistro verde smeraldo sopra al form di login
        st.markdown(
            """
            <div class="matrix-login-header-card">
                <div style="font-size:1.55rem; font-weight:800; color:#F8FAFC; letter-spacing:-0.01em; line-height:1.2;">
                    📈 MATRIX PRO
                </div>
                <div style="font-size:0.96rem; font-weight:700; color:#10B981; margin-top:4px;">
                    by Fabio Tod
                </div>
                <div style="font-size:0.84rem; color:#CBD5E1; margin-top:6px;">
                    Accesso riservato • Terminale Quantitativo &amp; Portafoglio
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("matrix_login_form", clear_on_submit=False):
            utente_in = st.text_input("👤 Utente", placeholder="Nome utente...", key="matrix_login_user")
            pwd_in = st.text_input("🔑 Password", type="password", placeholder="Password...", key="matrix_login_pwd")
            accedi_btn = st.form_submit_button("🔑 Accedi", type="primary", use_container_width=True)

            if accedi_btn:
                ok_auth, nome_valido = _verifica_credenziali_matrix(utente_in, pwd_in)
                if ok_auth:
                    _reset_sessione_utente()
                    st.session_state["autenticato"] = True
                    st.session_state["utente_corrente"] = nome_valido
                    st.session_state["utente_autenticato"] = nome_valido
                    st.rerun()
                else:
                    st.error("❌ Utente o password non validi. Riprova.")

        st.markdown(
            "<div style='text-align:center; color:#94A3B8; font-size:0.76rem; margin-top:0.85rem;'>"
            "🔒 Accesso protetto con crittografia SHA-256</div>",
            unsafe_allow_html=True,
        )
    st.stop()

def render_box_account_sidebar():
    """Mostra nella sidebar l'utente autenticato, il cambio password locale e il tasto Esci."""
    st.sidebar.markdown("---")
    utente_corrente = st.session_state.get("utente_corrente") or st.session_state.get("utente_autenticato") or UTENTE_PREDEFINITO_AUTH
    st.sidebar.markdown(
        f"<div style='background:#0B0E11; border:1px solid #2A2E39; border-left:3px solid #10B981; "
        f"border-radius:6px; padding:0.55rem 0.75rem; margin-bottom:0.5rem; font-size:0.84rem; color:#F8FAFC;'>"
        f"👤 Connesso come <b>{utente_corrente}</b></div>",
        unsafe_allow_html=True,
    )
    with st.sidebar.expander("🔐 Cambia Password", expanded=False):
        with st.form("matrix_change_pwd_form", clear_on_submit=True):
            pwd_att = st.text_input("Password attuale", type="password", key="chg_pwd_old")
            pwd_new = st.text_input("Nuova password", type="password", key="chg_pwd_new")
            pwd_cnf = st.text_input("Conferma nuova password", type="password", key="chg_pwd_cnf")
            salva_pwd_btn = st.form_submit_button("💾 Aggiorna Password", use_container_width=True)
            if salva_pwd_btn:
                if pwd_new != pwd_cnf:
                    st.error("❌ Le nuove password non coincidono.")
                else:
                    ok_c, msg_c = _cambia_password_utente_locale(utente_corrente, pwd_att, pwd_new)
                    if ok_c:
                        st.success(f"✅ {msg_c}")
                    else:
                        st.error(f"❌ {msg_c}")
    if st.sidebar.button("🚪 Esci", use_container_width=True, key="btn_logout_matrix"):
        st.session_state["autenticato"] = False
        st.session_state.pop("utente_corrente", None)
        st.session_state.pop("utente_autenticato", None)
        _reset_sessione_utente()
        st.rerun()

# Esegue subito il controllo di accesso prima di caricare portafoglio, dati o sidebar
richiedi_login_matrix()

# Carica il profilo dinamico dell'utente autenticato e aggiorna i riferimenti per regia_tracker
PROFILO_ATTIVO = _get_profilo_utente_corrente()
if st.session_state.get("_utente_sessione_caricato") != PROFILO_ATTIVO["chiave"]:
    _reset_sessione_utente()
    st.session_state["_utente_sessione_caricato"] = PROFILO_ATTIVO["chiave"]
st.session_state["_regia_tracker_file"] = PROFILO_ATTIVO["regia_tracker"]
st.session_state["_skip_regia_file"] = PROFILO_ATTIVO["skip_regia"]
st.session_state["_impostazioni_file"] = PROFILO_ATTIVO["impostazioni"]

# ==============================================================================
# CSS STILE TERMINALE TRADER PROFESSIONALE (TRADINGVIEW DARK)
# ==============================================================================
st.markdown("""
<style>
@import url('https://googleapis.com');

:root {
    --tv-bg: #0B0E11;
    --tv-surface: #131722;
    --tv-surface-hover: #1E222D;
    --tv-border: #2A2E39;
    --tv-text: #D1D4DC;
    --tv-text-muted: #787B86;
    --tv-green: #089981;
    --tv-green-bg: rgba(8, 153, 129, 0.14);
    --tv-red: #F23645;
    --tv-red-bg: rgba(242, 54, 69, 0.14);
    --tv-blue: #2962FF;
    --tv-amber: #F59E0B;
}

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background-color: var(--tv-bg);
    color: var(--tv-text);
}

.main .block-container {
    padding-top: 1.1rem;
    padding-bottom: 2rem;
    max-width: 1520px;
    font-size: 13px !important;
}

section[data-testid="stSidebar"] {
    background-color: var(--tv-surface) !important;
    border-right: 1px solid var(--tv-border);
}

div[data-testid="stMetric"] {
    background-color: var(--tv-surface);
    border: 1px solid var(--tv-border);
    padding: 12px 16px;
    border-radius: 6px;
}
div[data-testid="stMetricLabel"] {
    color: var(--tv-text-muted) !important;
    font-size: 0.76rem !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
div[data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-variant-numeric: tabular-nums;
    font-size: 1.32rem !important;
    font-weight: 700 !important;
    color: #FFFFFF !important;
}

.stButton > button {
    width: 100%;
    padding: 0.6rem 1rem;
    font-size: 0.92rem;
    font-weight: 600;
    border-radius: 6px;
    border: 1px solid var(--tv-border);
    transition: all 0.15s ease;
}
.stButton > button[kind="primary"] {
    background-color: var(--tv-blue) !important;
    border-color: var(--tv-blue) !important;
    color: #FFFFFF !important;
}
.stButton > button[kind="primary"]:hover {
    background-color: #1E53E5 !important;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 20px;
    background-color: transparent !important;
    padding: 0 0 4px 0;
    border-radius: 0;
    border: none;
    border-bottom: 1px solid var(--tv-border);
    flex-wrap: wrap;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 0;
    padding: 8px 4px;
    font-weight: 600;
    font-size: 0.92rem;
    color: var(--tv-text-muted);
    background-color: transparent !important;
}
.stTabs [aria-selected="true"] {
    background-color: transparent !important;
    color: #FFFFFF !important;
    border-bottom: 2px solid var(--tv-blue) !important;
}

footer { visibility: hidden; }
div[data-baseweb="slider"] div[role="slider"] { background-color: #2962FF !important; border-color: #2962FF !important; }
div[data-baseweb="slider"] > div > div > div:first-child { background-color: #2962FF !important; }
.header-box {
    background-color: var(--tv-surface);
    border: 1px solid var(--tv-border);
    border-left: 4px solid var(--tv-blue);
    color: #FFFFFF;
    padding: 1rem 1.5rem;
    border-radius: 8px;
    text-align: left;
    margin-bottom: 1.2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 1rem;
}
.header-box h1 { color: #FFFFFF; margin: 0; font-size: 1.5rem !important; font-weight: 700; letter-spacing: -0.02em; }
.header-box p { font-size: 0.88rem !important; margin: 0.2rem 0 0 0; color: var(--tv-text-muted); }

.signal-box {
    background-color: var(--tv-surface);
    border: 1px solid var(--tv-border);
    padding: 1rem 1.2rem;
    border-radius: 6px;
    margin-bottom: 0.6rem;
    font-size: 13px !important;
}
.signal-green { background: linear-gradient(135deg, #065f46 0%, #047857 100%); border-left: 5px solid #10b981; color: #ecfdf5; }
.signal-yellow { background: linear-gradient(135deg, #78350f 0%, #92400e 100%); border-left: 5px solid #f59e0b; color: #fef3c7; }
.signal-red { background: linear-gradient(135deg, #7f1d1d 0%, #991b1b 100%); border-left: 5px solid #ef4444; color: #fee2e2; }
.signal-blue { background: linear-gradient(135deg, #1e3a8a 0%, #1d4ed8 100%); border-left: 5px solid #3b82f6; color: #dbeafe; }
.signal-fabio {
    background-color: var(--tv-surface);
    border: 1px solid var(--tv-green);
    border-left: 5px solid var(--tv-green);
    color: #D1FAE5;
    box-shadow: 0 4px 18px rgba(8, 153, 129, 0.18);
    font-size: 14px !important;
}
.signal-fabio h3 { font-size: 1.25rem !important; margin-bottom: 0.4rem !important; color: #FFFFFF; }
.signal-fabio p { font-size: 0.98rem !important; }

.dataframe { background-color: var(--tv-surface) !important; color: var(--tv-text) !important; border-radius: 6px; overflow: hidden; font-size: 13px !important; font-family: 'JetBrains Mono', monospace !important; }
.dataframe th { background-color: var(--tv-surface-hover) !important; color: #FFFFFF !important; font-size: 13px !important; font-weight: 700; }

.signal-history-box { background-color: var(--tv-surface); border-radius: 6px; padding: 0.85rem 1rem; margin: 0.8rem 0; border: 1px solid var(--tv-border); }
.signal-history-title { color: #FFFFFF; font-size: 1rem; font-weight: 700; margin-bottom: 0.4rem; }

.semaforo-box { background-color: var(--tv-surface); border: 1px solid var(--tv-border); padding: 1.1rem 1.5rem; border-radius: 8px; margin-bottom: 1.2rem; text-align: center; }
.semaforo-verde { background: linear-gradient(135deg, #065f46 0%, #047857 100%); border-left: 6px solid #10b981; }
.semaforo-giallo { background: linear-gradient(135deg, #78350f 0%, #92400e 100%); border-left: 6px solid #f59e0b; }
.semaforo-rosso { background: linear-gradient(135deg, #7f1d1d 0%, #991b1b 100%); border-left: 6px solid #ef4444; }

.target-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; vertical-align: middle; cursor: help; transition: all 0.2s ease; }
.target-dot-achieved { background-color: var(--tv-green); box-shadow: 0 0 6px var(--tv-green); }
.target-dot-pending { background-color: #363A45; }
.target-dot:hover { transform: scale(1.25); }
.target-tooltip { font-size: 0.75rem; color: var(--tv-text-muted); margin-left: 6px; }
.by-fabio-badge { background-color: var(--tv-green-bg); color: var(--tv-green); border: 1px solid var(--tv-green); padding: 3px 10px; border-radius: 4px; font-size: 0.78rem; font-weight: 700; margin-left: 8px; display: inline-block; }
.breakout-card { background-color: var(--tv-surface); border: 1px solid var(--tv-border); border-left: 4px solid var(--tv-amber); padding: 0.9rem 1.1rem; border-radius: 6px; margin-bottom: 0.5rem; }

section[data-testid="stSidebar"] div[role="radiogroup"] {
    background-color: #0B0E11;
    border: 1px solid #2A2E39;
    border-radius: 6px;
    padding: 4px;
    max-height: 210px;
    overflow-y: auto;
    gap: 2px;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label {
    padding: 5px 10px !important;
    border-radius: 4px;
    margin: 0 !important;
    width: 100%;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
    background-color: #1E222D !important;
    color: #FFFFFF !important;
    font-weight: 700;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child {
    display: none !important;
}

div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] button {
    padding: 0.35rem 0.1rem !important;
    font-size: 0.70rem !important;
    line-height: 1.15 !important;
}

    .modebar { opacity: 1 !important; visibility: visible !important; top: 4px !important; right: 8px !important; background: rgba(19, 23, 34, 0.9) !important; border: 1px solid #2A2E39; border-radius: 4px; padding: 2px; }
    .modebar-btn path { fill: #D1D4DC !important; }
    .modebar-btn:hover path { fill: #2962FF !important; }
    

    /* RESPONSIVE MOBILE & TABLET (STEP 1) */
    @media (max-width: 768px) {
        .main .block-container {
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
            padding-top: 0.5rem !important;
        }
        [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap: 0.4rem !important;
        }
        [data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
            min-width: 100% !important;
        }
        .stButton > button {
            min-height: 44px !important;
            font-size: 0.95rem !important;
            width: 100% !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            overflow-x: auto !important;
            flex-wrap: nowrap !important;
            -webkit-overflow-scrolling: touch;
            gap: 4px !important;
        }
        .stTabs [data-baseweb="tab"] {
            white-space: nowrap !important;
            padding: 8px 12px !important;
            font-size: 0.85rem !important;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.25rem !important;
        }
        .js-plotly-plot {
            max-width: 100% !important;
        }
    }
    
</style>


""", unsafe_allow_html=True)

# ==============================================================================
# GESTIONE FILE & LOG PROPOSTE (DINAMICI PER UTENTE AUTENTICATO)
# ==============================================================================
PORTAFOGLIO_FILE = PROFILO_ATTIVO["portafoglio"]
WATCHLIST_FILE = "watchlist.json"
PAPER_TRADING_FILE = "paper_trading.json"
SEGNALI_STORICI_FILE = "segnali_storici.json"
REGISTRO_VENDITE_FILE = PROFILO_ATTIVO["registro_vendite"]
REGISTRO_ACQUISTI_FILE = PROFILO_ATTIVO["registro_acquisti"]
MINUSVALENZE_FILE = PROFILO_ATTIVO["minusvalenze"]
IMPOSTAZIONI_FILE = PROFILO_ATTIVO["impostazioni"]
SEGNALI_ATTIVI_FILE = PROFILO_ATTIVO["segnali_attivi"]
REGIA_TRACKER_FILE = PROFILO_ATTIVO["regia_tracker"]
SALUTO_UTENTE_CORRENTE = PROFILO_ATTIVO["saluto"]
CAPITALE_VERSATO_DEFAULT = float(PROFILO_ATTIVO["capitale_versato_default"])
USA_PORTAFOGLIO_INIZIALE = bool(PROFILO_ATTIVO.get("usa_portafoglio_iniziale", False))
LOG_PROPOSTE_FILE = "log_proposte.json"

def _is_file_sincronizzabile_github(fname):
    """Consente il sync GitHub per i file operativi multi-utente, bloccando SEMPRE file auth/segreti."""
    fn = str(fname or "").strip()
    fl = fn.lower()
    if not fn or not fl.endswith(".json"):
        return False
    if fl == UTENTI_AUTH_FILE.lower() or "auth" in fl or "secret" in fl:
        return False
    prefissi_ammessi = (
        "portafoglio",
        "impostazioni",
        "segnali_attivi",
        "regia_tracker",
        "registro_vendite",
        "registro_acquisti",
        "minusvalenze",
    )
    if fn == "insider_promossi.json":
        return True
    for pref in prefissi_ammessi:
        if fl == f"{pref}.json" or fl.startswith(f"{pref}_"):
            return True
    return False

def _sync_github_file(file_path, content_str, mode="push"):
    try:
        fname = os.path.basename(file_path)
        if not _is_file_sincronizzabile_github(fname):
            return None
        token = str(st.secrets.get("GITHUB_TOKEN", "")).strip()
        repo = "Miguel196801/matrix-scanner"
        if not token or not repo:
            return None
        import base64, requests
        url = f"https://api.github.com/repos/{repo}/contents/{fname}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Matrix-DVMS-Sync"
        }
        sha = None
        remote_text = None
        r_get = requests.get(url, headers=headers, timeout=8)
        if r_get.status_code == 200:
            res_data = r_get.json()
            sha = res_data.get("sha")
            if mode == "pull" and "content" in res_data:
                remote_text = base64.b64decode(res_data["content"]).decode("utf-8")

        if mode == "pull":
            return remote_text

        payload = {
            "message": f"Sync auto {fname}",
            "content": base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
        }
        if sha:
            payload["sha"] = sha
        r_put = requests.put(url, json=payload, headers=headers, timeout=10)
        if r_put.status_code in (200, 201):
            try:
                st.session_state["_gh_last_msg"] = ("ok", f"☁️ Sincronizzato su GitHub: {fname} (Repo: {repo})")
            except Exception:
                pass
        else:
            try:
                pass
            except Exception:
                pass
    except Exception as _e_gh:
        try:
            pass
        except Exception:
            pass
    return None

# Espone la funzione di sincronizzazione GitHub anche al modulo regia_tracker
st.session_state["_sync_github_file_fn"] = _sync_github_file

def registra_acquisto_storico(ticker, tipo, qta, prezzo_eur, nota="Acquisto"):
    try:
        storico = carica_json(REGISTRO_ACQUISTI_FILE, default=[])
        if not isinstance(storico, list):
            storico = []
        storico.insert(0, {
            "Data": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Ticker": str(ticker).upper(),
            "Operazione": nota,
            "Tipo": str(tipo),
            "Quantita": round(float(qta), 4),
            "Prezzo_EUR": round(float(prezzo_eur), 4),
            "Totale_EUR": round(float(qta) * float(prezzo_eur), 2)
        })
        salva_json(REGISTRO_ACQUISTI_FILE, storico)
    except Exception:
        pass

def formatta_fase_weinstein_pro(val_fase):
    s = str(val_fase).upper()
    if "2" in s:
        return "<span style='color:#4ade80; font-weight:800;'>🟢 FASE 2 — Rialzo (Ideale)</span>"
    elif "1" in s:
        return "<span style='color:#fb923c; font-weight:800;'>🟠 FASE 1 — Accumulo (Attesa Breakout)</span>"
    elif "3" in s:
        return "<span style='color:#fb923c; font-weight:800;'>🟠 FASE 3 — Distribuzione (Tattico)</span>"
    elif "4" in s:
        return "<span style='color:#f87171; font-weight:800;'>🔴 FASE 4 — Ribasso (Evitare)</span>"
    return str(val_fase)

@st.cache_data(ttl=900, show_spinner=False)
def get_live_eurusd():
    try:
        _fx = yf.Ticker("EURUSD=X").history(period="1d")
        if not _fx.empty:
            _val = float(_fx["Close"].dropna().iloc[-1])
            if 0.80 < _val < 1.50:
                return round(_val, 4)
    except Exception:
        pass
    return 1.12

def _costruisci_mappa_metriche_scan():
    """
    Costruisce una mappa {TICKER: {Fase, S_Score, RSI, Giorni_Utili}} unendo i dati
    dell'ultima scansione (dashboard_stats['metriche_scan']) e i DataFrame di sessione
    (df_fortezza, df_cavalli, df_monitor, df_palantir, zona_interesse_alerts).
    """
    mappa = {}
    try:
        ds = st.session_state.get("dashboard_stats")
        if isinstance(ds, dict) and isinstance(ds.get("metriche_scan"), dict):
            for tk_k, val_d in ds["metriche_scan"].items():
                if isinstance(val_d, dict):
                    mappa[str(tk_k).strip().upper()] = dict(val_d)
        for chiave_df in ("df_fortezza", "df_cavalli", "df_monitor", "df_palantir"):
            df_s = st.session_state.get(chiave_df)
            if isinstance(df_s, pd.DataFrame) and not df_s.empty and "Ticker" in df_s.columns:
                for _, row in df_s.iterrows():
                    tk_u = str(row.get("Ticker", "")).strip().upper()
                    if not tk_u:
                        continue
                    voce = mappa.setdefault(tk_u, {})
                    if "S-Score" in df_s.columns and pd.notna(row.get("S-Score")) and voce.get("S_Score") is None:
                        voce["S_Score"] = float(row.get("S-Score"))
                    if "Fase" in df_s.columns and pd.notna(row.get("Fase")) and not voce.get("Fase"):
                        voce["Fase"] = str(row.get("Fase"))
                    if "RSI" in df_s.columns and pd.notna(row.get("RSI")) and voce.get("RSI") is None:
                        voce["RSI"] = float(row.get("RSI"))
        for z in (st.session_state.get("zona_interesse_alerts") or []):
            if isinstance(z, dict):
                tk_u = str(z.get("ticker", "")).strip().upper()
                if tk_u and z.get("s_score") is not None:
                    mappa.setdefault(tk_u, {}).setdefault("S_Score", float(z.get("s_score")))
    except Exception:
        pass
    return mappa

def _estrai_info_posizione_vendibile(ptk, po, df_map):
    """
    Estrae in modo coerente Fase, S-Score, RSI, stato PAC e giorni agli utili
    incrociando le chiavi reali di portafoglio.json ('Tipo', 'Stato_PAC', 'Earnings')
    con le metriche fresche dello scanner (df_map).
    """
    m_scan = df_map.get(ptk, {}) if isinstance(df_map, dict) else {}
    fase = str(m_scan.get("Fase") or po.get("Fase") or po.get("fase") or "").upper()
    sc = float(m_scan.get("S_Score") if m_scan.get("S_Score") is not None else (po.get("S_Score", po.get("Score", 0)) or 0))
    rsi = float(m_scan.get("RSI") if m_scan.get("RSI") is not None else (po.get("RSI", 50) or 50))
    # Riconoscimento reale PAC dalle chiavi di portafoglio.json ('Tipo' + 'Stato_PAC')
    tipo_p = str(po.get("Tipo", "Spot")).strip().upper()
    stato_pac_str = str(po.get("Stato_PAC", "")).upper()
    pac_attivo = (tipo_p == "PAC" and "SOSPESO" not in stato_pac_str) or (
        bool(po.get("PAC_Attivo", False)) and not bool(po.get("PAC_Sospeso", False))
    )
    # Giorni mancanti agli utili: da scanner oppure parsati dal testo 'Earnings' di portafoglio.json
    ut = m_scan.get("Giorni_Utili")
    if ut is None:
        if po.get("Giorni_Utili") is not None:
            ut = int(po.get("Giorni_Utili"))
        else:
            m_gg = re.search(r"tra\s+(\d+)\s*gg", str(po.get("Earnings", "")), re.IGNORECASE)
            ut = int(m_gg.group(1)) if m_gg else 999
    else:
        ut = int(ut)
    return fase, sc, rsi, pac_attivo, ut

def calcola_regia_acquisti(ign_l, fabio_l, std_l, tp_l, port_l, df_map, cassa_b, liq_ex, escl_s, cat_s, taglia, manual_l=None):
    port_m = {str(p.get("Ticker", "")).strip().upper(): p for p in port_l}
    raw = []
    for m_idx, m_tk in enumerate(manual_l or []):
        tk_m = str(m_tk).strip().upper()
        # Deduplicazione corretta controllando il ticker x[0] nella tupla
        if tk_m and not any(x[0] == tk_m for x in raw):
            raw.append((tk_m, f"PRIORITÀ MANUALE #{m_idx+1}", -100 + m_idx))
    for lst, nome, rk in [(ign_l, "IGNITION", 0), (fabio_l, "BY FABIO", 1), (std_l, "BY Standard", 2)]:
        for item in (lst or []):
            tk = str(item.get("Ticker", item.get("ticker", item)) if isinstance(item, dict) else item).strip().upper()
            if tk and not any(x[0] == tk for x in raw):
                raw.append((tk, nome, rk))
    approvati, scartati = [], []
    _skip_set = regia_tracker.get_ticker_saltati_5gg() if ('regia_tracker' in globals() and hasattr(regia_tracker, 'get_ticker_saltati_5gg')) else set()
    for tk, tipo, rk in raw:
        if tk in _skip_set:
            scartati.append(f"⏭️ **{tk}** ({tipo}): archiviato per 5 gg (non eseguito nel reale)")
            continue
        is_manual = rk < 0
        info = df_map.get(tk, {}) if isinstance(df_map, dict) else {}
        _m_pro = regia_tracker._fetch_metriche_pro(tk, get_live_eurusd()) if ('regia_tracker' in globals() and hasattr(regia_tracker, '_fetch_metriche_pro')) else None
        pot = float(_m_pro['pot_reale']) if _m_pro else float(info.get("Upside_%", info.get("Potenziale_%", info.get("Target1_%", 15.0))) or 15.0)
        fase = str(info.get("Fase", info.get("Fase_Weinstein", "2"))).upper()
        sc = float(info.get("S_Score", info.get("Score", 80)) or 80)
        if not is_manual and pot < 10.0:
            scartati.append(f"⛔ **{tk}** ({tipo}): potenziale **+{pot:.1f}%** (< 10% minimo)")
            continue
        if tk in port_m:
            pnl_p = float(port_m[tk].get("PnL_%", 0.0) or 0.0)
            if not is_manual and pnl_p > 5.0:
                scartati.append(f"⚠️ **{tk}** ({tipo}): già in gain **+{pnl_p:.1f}%** (anti-inseguimento)")
                continue
            nota = f"Mediazione in loss ({pnl_p:+.1f}%)" if pnl_p < 0 else f"Incremento (+{pnl_p:.1f}%)"
        else:
            nota = "Nuovo ingresso"
        approvati.append((rk, 0 if "2" in fase else 1, -pot, -sc, tk, tipo, pot, sc, nota))
    # Ordinamento corretto per priorità tipo, Fase 2, potenziale e S-Score
    approvati.sort(key=lambda x: (x[0], x[1], x[2], x[3]))

    pool, tp_set = [], set()
    for tpi in (tp_l or []):
        ttk = str(tpi.get("ticker", tpi.get("Ticker", "")) if isinstance(tpi, dict) else tpi).strip().upper()
        if ttk and ttk in port_m:
            tp_set.add(ttk)
            va = float(port_m[ttk].get("Valore_Attuale", 0.0) or 0.0)
            pnl = float(port_m[ttk].get("PnL_EUR", 0.0) or 0.0)
            net = round(va - max(0.0, pnl * 0.26), 2)
            if net > 0:
                # Priorita 1 per Take Profit (dopo Eventi/Trimestrali imminenti che hanno Priorita 0)
                pool.append((1, ttk, net, f"🎯 Vendi **{ttk}** (Take Profit attivo) -> netto **€ {net:,.2f}**"))
    for ptk, po in port_m.items():
        if ptk in tp_set or ptk in escl_s or ptk in cat_s:
            continue
        va = float(po.get("Valore_Attuale", 0.0) or 0.0)
        pnl = float(po.get("PnL_EUR", 0.0) or 0.0)
        if va <= 0:
            continue
        net = round(va - max(0.0, pnl * 0.26), 2)
        fase, sc, rsi, pac, ut = _estrai_info_posizione_vendibile(ptk, po, df_map)
        # Protegge i titoli vincenti in Fase 2 (o S-Score >= 85) non ipercomprati e lontani dagli utili
        if pnl > 0 and ("2" in fase or sc >= 85) and rsi < 75 and ut > 7:
            continue
        if ptk == "NKE" or ut <= 7:
            pr, lbl = 0, "⚠️ Trimestrale / Investor Day imminente"
        elif ptk == "TTD" or "4" in fase or rsi >= 70:
            pr, lbl = 2, "Fase 4 / RSI>70"
        elif pnl > 0 and not pac:
            pr, lbl = 3, "Gain Spot non in Fase 2"
        elif pnl <= 0 and not pac:
            pr, lbl = 4, "Sfoltimento 0 tasse"
        else:
            continue
        pool.append((pr, ptk, net, f"🔄 Vendi **{ptk}** ({lbl}) -> netto **€ {net:,.2f}**"))
    # Ordinamento corretto per priorità vendita (x[0]), importo netto (x[2]) e ticker (x[1])
    pool.sort(key=lambda x: (x[0], x[2], x[1]))

    rem_c, rem_e, out = float(cassa_b), float(liq_ex), []
    for idx, (_, _, _, _, tk, tipo, pot, sc, nota) in enumerate(approvati, 1):
        cop, fonti = float(taglia), []
        if rem_c > 0 and cop > 0:
            u = min(cop, rem_c); fonti.append(f"💳 Cassa Broker **€ {u:,.2f}**"); rem_c = round(rem_c - u, 2); cop = round(cop - u, 2)
        if rem_e > 0 and cop > 0:
            u = min(cop, rem_e); fonti.append(f"💵 Liq. Aggiuntiva **€ {u:,.2f}**"); rem_e = round(rem_e - u, 2); cop = round(cop - u, 2)
        while cop > 0 and pool:
            _, vtk, vnet, vdesc = pool.pop(0)
            fonti.append(vdesc)
            if vnet > cop:
                rem_c = round(rem_c + (vnet - cop), 2); cop = 0.0
            else:
                cop = round(cop - vnet, 2)
        out.append((idx, tk, tipo, pot, sc, nota, fonti, cop))
    return out, scartati

def carica_json(file_path, default=None):
    # Risolve il percorso locale assoluto rispetto alla cartella di scanner.py
    _abs_fp = file_path if os.path.isabs(file_path) else os.path.join(os.path.dirname(os.path.abspath(__file__)), file_path)
    _esiste_locale = os.path.exists(_abs_fp) or os.path.exists(file_path)
    _is_locale_pc = (os.name == "nt")
    # In locale su Windows, se il file esiste su disco NON scarica mai da GitHub (evita sovrascritture con copie vecchie).
    # Lo scaricamento da GitHub resta attivo solo su Streamlit Cloud / Mobile (Linux) oppure se il file locale manca.
    _deve_pull_gh = (not _is_locale_pc) or (not _esiste_locale)

    _k_pull = f"_gh_pulled_{os.path.basename(file_path)}"
    if _deve_pull_gh and _k_pull not in st.session_state and "_sync_github_file" in globals():
        st.session_state[_k_pull] = True
        _rem_txt = _sync_github_file(file_path, "", mode="pull")
        if _rem_txt:
            try:
                with open(_abs_fp, "w", encoding="utf-8") as _fw:
                    _fw.write(_rem_txt)
            except Exception:
                pass
    elif _k_pull not in st.session_state:
        st.session_state[_k_pull] = True

    _target_fp = _abs_fp if os.path.exists(_abs_fp) else file_path
    if os.path.exists(_target_fp):
        try:
            with open(_target_fp, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return list() if default is None else default
    return list() if default is None else default

def salva_json(file_path, data):
    _abs_fp = file_path if os.path.isabs(file_path) else os.path.join(os.path.dirname(os.path.abspath(__file__)), file_path)
    with open(_abs_fp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    try:
        _sync_github_file(file_path, json.dumps(data, indent=4, ensure_ascii=False), mode='push')
    except Exception:
        pass

def ricarica_portafoglio_da_disco(push_github=True):
    """Rilegge il file portafoglio dell'utente attivo dal disco locale, aggiorna la sessione e sincronizza su GitHub."""
    _fp_disk = os.path.join(os.path.dirname(os.path.abspath(__file__)), PORTAFOGLIO_FILE)
    if not os.path.exists(_fp_disk):
        return False, f"File {PORTAFOGLIO_FILE} non trovato su disco."
    try:
        with open(_fp_disk, "r", encoding="utf-8") as _f_disk:
            _dati_disk = json.load(_f_disk)
        if not isinstance(_dati_disk, list):
            return False, f"Formato {PORTAFOGLIO_FILE} non valido (attesa una lista)."
        st.session_state["portafoglio"] = _dati_disk
        if push_github and "_sync_github_file" in globals():
            _sync_github_file(PORTAFOGLIO_FILE, json.dumps(_dati_disk, indent=4, ensure_ascii=False), mode="push")
            return True, f"Ricaricati {len(_dati_disk)} titoli da {PORTAFOGLIO_FILE} locale e sincronizzati su GitHub."
        return True, f"Ricaricati {len(_dati_disk)} titoli da {PORTAFOGLIO_FILE} locale."
    except Exception as _e_disk:
        return False, f"Errore lettura {PORTAFOGLIO_FILE}: {_e_disk}"

def _get_segnali_attivi_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), SEGNALI_ATTIVI_FILE)

def _carica_segnali_attivi():
    """Carica la bacheca persistente dei segnali attivi dell'utente loggato (con pull GitHub su Cloud)."""
    dati = carica_json(SEGNALI_ATTIVI_FILE, default={"aperti": [], "chiusi": []})
    if isinstance(dati, dict):
        dati.setdefault("aperti", [])
        dati.setdefault("chiusi", [])
        return dati
    return {"aperti": [], "chiusi": []}

def _salva_segnali_attivi(dati):
    """Salva la bacheca segnali attivi dell'utente loggato mantenendo max 10 chiusi (con sync GitHub)."""
    if not isinstance(dati, dict):
        dati = {"aperti": [], "chiusi": []}
    dati["aperti"] = list(dati.get("aperti") or [])
    dati["chiusi"] = list(dati.get("chiusi") or [])[:10]
    salva_json(SEGNALI_ATTIVI_FILE, dati)

def _calcola_livello_rischio_segnale(stop_pct, s_score=None):
    """Restituisce il livello di rischio visivo con peperoncini in base allo stop e all'S-Score."""
    sp = abs(float(stop_pct or 10.0))
    sc = int(s_score) if s_score is not None else 65
    if sp <= 7.0 and sc >= 75:
        return "🌶️ Basso-Medio"
    if sp <= 12.5 and sc >= 60:
        return "🌶️🌶️ Medio"
    return "🌶️🌶️🌶️ Medio-Alto"

def _valuta_cluster_insider_bacheca(ticker, df, info, sec_ins, s_score, fase, currency="USD"):
    """
    Valuta un candidato per la FONTE B ('🏛️ CLUSTER INSIDER SEC') della Bacheca Segnali Attivi:
    richiede acquisti ufficiali SEC Form 4 negli ultimi 12 giorni, almeno 2 dirigenti acquirenti
    e controvalore complessivo >= $1.000.000.
    """
    try:
        if not isinstance(sec_ins, dict) or df is None or len(df) < 20:
            return None
        dettagli = sec_ins.get("dettagli") or []
        if not dettagli:
            return None
        dt_12g = (datetime.now() - timedelta(days=12)).strftime("%Y-%m-%d")
        dir_12g = set()
        n_acq_12g = 0
        val_12g = 0.0
        ult_12g = ""
        for row in dettagli:
            d_tx = str(row.get("Data", "")).strip()[:10]
            if not d_tx or d_tx < dt_12g:
                continue
            n_acq_12g += 1
            nome = str(row.get("Insider", "Dirigente")).strip()
            if nome:
                dir_12g.add(nome)
            imp_raw = str(row.get("Importo $", "0")).replace("$", "").replace(",", "").strip()
            try:
                val_12g += float(imp_raw)
            except Exception:
                pass
            if not ult_12g or d_tx > ult_12g:
                ult_12g = d_tx

        # Criteri rigorosi Fonte B: ultimi 12gg, >= 2 dirigenti distinti, >= $1.000.000
        if len(dir_12g) < 2 or val_12g < 1000000.0:
            return None

        prezzo = float(df["Close"].iloc[-1])
        if prezzo <= 0:
            return None
        # Stop di riferimento sul minimo recente (~ -12%)
        min_15 = float(df["Low"].tail(15).min())
        if prezzo * 0.84 <= min_15 <= prezzo * 0.92:
            stop_loss = round(min_15, 2)
        else:
            stop_loss = round(prezzo * 0.88, 2)
        stop_pct = round(((stop_loss - prezzo) / prezzo) * 100.0, 1)

        # Target sul Fair Value analisti oppure resistenza chiave a 52 settimane
        fv = float((info or {}).get("targetMeanPrice") or 0.0)
        res_52w = float(df["High"].max())
        if fv >= prezzo * 1.12:
            target = round(fv, 2)
            target_lbl = "Fair Value analisti"
        else:
            target = round(max(res_52w, prezzo * 1.25), 2)
            target_lbl = "resistenza chiave 52w"
        target_pct = round(((target - prezzo) / prezzo) * 100.0, 1)

        simb = "$" if str(currency).upper() == "USD" else "€"
        # Formatta la data dell'ultimo acquisto SEC Form 4 in formato italiano GG/MM/AAAA
        _ult_raw = (ult_12g or str(sec_ins.get("ultimo_acquisto") or "")).strip()[:10]
        try:
            ult_it = datetime.strptime(_ult_raw, "%Y-%m-%d").strftime("%d/%m/%Y") if _ult_raw else ""
        except Exception:
            ult_it = _ult_raw
        _ult_tag_b = f" — ultimo: {ult_it}" if ult_it else ""
        nomi_preview = ", ".join(sorted(list(dir_12g))[:3])
        motivo = (
            f"🏛️ Insider SEC ({n_acq_12g} acq / ${val_12g:,.0f}{_ult_tag_b}) da {len(dir_12g)} dirigenti "
            f"({nomi_preview}). Target su {target_lbl} ({target_pct:+.1f}%), S-Score: {int(s_score or 0)}/100."
        )
        return {
            "ticker": str(ticker).strip().upper(),
            "fonte": f"🏛️ CLUSTER INSIDER SEC{_ult_tag_b}",
            "fonte_code": "INSIDER_SEC",
            "sec_ultimo_acquisto": ult_it,
            "prezzo_segnale": round(prezzo, 2),
            "prezzo_attuale": round(prezzo, 2),
            "trigger_y": round(prezzo, 2),
            "stop_loss": stop_loss,
            "target": target,
            "orizzonte": "3-9 Mesi (Accumulo Insider)",
            "rischio": _calcola_livello_rischio_segnale(stop_pct, s_score),
            "fase_attuale": str(fase or "N/D"),
            "motivazione": motivo,
            "simbolo": simb,
            "_val_12g": val_12g,
            "_dir_12g": len(dir_12g),
            "_s_score": int(s_score or 0),
        }
    except Exception:
        return None

def _aggiorna_bacheca_segnali_attivi(pattern_alerts, cluster_candidati, scan_price_map):
    """
    Aggiorna tutti i segnali APERTI (chiusura automatica su Target, Stop o Fase 4 per Fonte A)
    e aggiunge i nuovi segnali ufficiali Fonte A (BREAKOUT MATRIX) e Fonte B (max 1 CLUSTER INSIDER SEC).
    """
    dati = _carica_segnali_attivi()
    aperti = dati.get("aperti") or []
    chiusi = dati.get("chiusi") or []
    oggi_str = datetime.now().strftime("%Y-%m-%d")

    nuovi_aperti = []
    # 1) Aggiornamento e verifica chiusura automatica sui segnali già APERTI
    for sig in aperti:
        if not isinstance(sig, dict):
            continue
        tk = str(sig.get("ticker", "")).strip().upper()
        if not tk:
            continue
        info_live = (scan_price_map or {}).get(tk)
        prezzo_att = None
        fase_att = sig.get("fase_attuale", "N/D")
        if isinstance(info_live, dict) and info_live.get("prezzo"):
            prezzo_att = float(info_live["prezzo"])
            fase_att = info_live.get("fase") or fase_att
        else:
            # Recupero diretto da yfinance se il titolo non era nella scansione corrente
            try:
                df_tmp = yf.Ticker(tk).history(period="1y", interval="1d")
                if df_tmp is not None and not df_tmp.empty:
                    df_tmp = df_tmp.dropna(subset=["Close"])
                    if not df_tmp.empty:
                        prezzo_att = float(df_tmp["Close"].iloc[-1])
                        if len(df_tmp) >= 200:
                            fase_att = rileva_fase_weinstein(df_tmp)
            except Exception:
                pass

        if prezzo_att is not None and prezzo_att > 0:
            sig["prezzo_attuale"] = round(prezzo_att, 2)
        sig["fase_attuale"] = str(fase_att or "N/D")

        p_sig = float(sig.get("prezzo_segnale") or 0.0)
        p_now = float(sig.get("prezzo_attuale") or p_sig)
        stop_l = float(sig.get("stop_loss") or 0.0)
        target_p = float(sig.get("target") or 0.0)
        rend_pct = round(((p_now - p_sig) / p_sig) * 100.0, 2) if p_sig > 0 else 0.0
        sig["rendimento_pct"] = rend_pct

        nuovo_stato = "APERTO"
        if target_p > 0 and p_now >= target_p:
            nuovo_stato = "CHIUSO_TARGET"
        elif stop_l > 0 and p_now <= stop_l:
            nuovo_stato = "CHIUSO_STOP"
        elif sig.get("fonte_code") == "BREAKOUT" and "FASE 4" in str(sig.get("fase_attuale", "")).upper():
            # Chiusura per deterioramento trend (Fase 4) applicata solo ai segnali tecnici Fonte A
            nuovo_stato = "CHIUSO_TREND"

        if nuovo_stato != "APERTO":
            sig["stato"] = nuovo_stato
            sig["data_chiusura"] = oggi_str
            chiusi.insert(0, sig)
        else:
            sig["stato"] = "APERTO"
            nuovi_aperti.append(sig)

    chiavi_aperte = {(str(s.get("ticker", "")).upper(), str(s.get("fonte_code", ""))) for s in nuovi_aperti}

    # 2) FONTE A — Tutti i segnali BUY ufficiali generati da pattern_engine.py
    if isinstance(pattern_alerts, dict):
        for cat_a in ("buy_nuovo", "buy_incremento", "buy_mediazione"):
            for al in (pattern_alerts.get(cat_a) or []):
                if not isinstance(al, dict):
                    continue
                tk_a = str(al.get("ticker", "")).strip().upper()
                if not tk_a or (tk_a, "BREAKOUT") in chiavi_aperte:
                    continue
                p_sig_a = float(al.get("prezzo") or al.get("trigger_y") or 0.0)
                if p_sig_a <= 0:
                    continue
                fig_nome = str(al.get("figura", "Breakout"))
                orizz_a = "2-4 Mesi" if fig_nome in ("Cup & Handle", "Flat Base", "Doppio Minimo (W)") else "3-8 Settimane"
                simb_a = "$" if str(al.get("currency", "USD")).upper() == "USD" else "€"
                fase_a = (scan_price_map.get(tk_a) or {}).get("fase", "FASE 2")
                motivo_a = (
                    f"{al.get('badge', 'BUY')} — {fig_nome} (Confidenza {al.get('confidenza', 0)}%, "
                    f"R/R 1:{float(al.get('rr', 0) or 0):.2f}). {al.get('motivo', '')}"
                )
                nuovi_aperti.insert(0, {
                    "id": f"{tk_a}_BREAKOUT_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "ticker": tk_a,
                    "fonte": "🎯 BREAKOUT MATRIX",
                    "fonte_code": "BREAKOUT",
                    "stato": "APERTO",
                    "data_segnale": oggi_str,
                    "prezzo_segnale": round(p_sig_a, 2),
                    "prezzo_attuale": round(p_sig_a, 2),
                    "trigger_y": round(float(al.get("trigger_y") or p_sig_a), 2),
                    "stop_loss": round(float(al.get("stop_price") or p_sig_a * 0.92), 2),
                    "target": round(float(al.get("target_price") or p_sig_a * 1.18), 2),
                    "orizzonte": orizz_a,
                    "rischio": _calcola_livello_rischio_segnale(al.get("stop_pct", -8.0), al.get("s_score")),
                    "fase_attuale": str(fase_a),
                    "motivazione": motivo_a,
                    "simbolo": simb_a,
                    "data_chiusura": "",
                    "rendimento_pct": 0.0,
                })
                chiavi_aperte.add((tk_a, "BREAKOUT"))

    # 3) FONTE B — Max 1 titolo top fresco "🏛️ CLUSTER INSIDER SEC" per scansione
    if cluster_candidati:
        cand_ordinati = sorted(
            [c for c in cluster_candidati if isinstance(c, dict) and (c.get("ticker"), "INSIDER_SEC") not in chiavi_aperte],
            key=lambda x: (float(x.get("_val_12g", 0.0)), int(x.get("_dir_12g", 0)), int(x.get("_s_score", 0))),
            reverse=True,
        )
        if cand_ordinati:
            top_b = dict(cand_ordinati[0])
            tk_b = top_b["ticker"]
            nuovi_aperti.insert(0, {
                "id": f"{tk_b}_INSIDER_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "ticker": tk_b,
                "fonte": top_b.get("fonte", "🏛️ CLUSTER INSIDER SEC"),
                "fonte_code": "INSIDER_SEC",
                "sec_ultimo_acquisto": top_b.get("sec_ultimo_acquisto", ""),
                "stato": "APERTO",
                "data_segnale": oggi_str,
                "prezzo_segnale": top_b["prezzo_segnale"],
                "prezzo_attuale": top_b["prezzo_attuale"],
                "trigger_y": top_b["trigger_y"],
                "stop_loss": top_b["stop_loss"],
                "target": top_b["target"],
                "orizzonte": top_b["orizzonte"],
                "rischio": top_b["rischio"],
                "fase_attuale": top_b["fase_attuale"],
                "motivazione": top_b["motivazione"],
                "simbolo": top_b.get("simbolo", "$"),
                "data_chiusura": "",
                "rendimento_pct": 0.0,
            })

    dati["aperti"] = nuovi_aperti
    dati["chiusi"] = chiusi[:10]
    _salva_segnali_attivi(dati)
    return dati

def render_bacheca_segnali_attivi(eurusd_rate=1.12):
    """Renderizza la Bacheca Segnali Attivi completa e immediata nel Riepilogo Operativo."""
    st.subheader("📋 Bacheca Segnali Attivi (Operazioni in Corso fino a chiusura)")
    dati = _carica_segnali_attivi()
    aperti = dati.get("aperti") or []
    chiusi = dati.get("chiusi") or []

    if not aperti:
        st.info(
            "Nessun segnale attivo in bacheca al momento. Avvia **🚀 AVVIA SCANSIONE** per registrare "
            "automaticamente eventuali segnali **🎯 BREAKOUT MATRIX** o **🏛️ CLUSTER INSIDER SEC**."
        )
    else:
        st.caption(
            f"Operazioni aperte monitorate automaticamente fino a Target, Stop Loss o cambio trend: **{len(aperti)}** "
            "(Fonti: **🎯 BREAKOUT MATRIX** e **🏛️ CLUSTER INSIDER SEC**)."
        )
        for idx_s, sig in enumerate(aperti):
            sig_id = str(sig.get("id") or f"{sig.get('ticker')}_{idx_s}")
            tk = str(sig.get("ticker", ""))
            fonte = str(sig.get("fonte", "🎯 BREAKOUT MATRIX"))
            is_insider_b = (sig.get("fonte_code") == "INSIDER_SEC")
            b_col = "#A855F7" if is_insider_b else "#10B981"
            badge_bg = "rgba(168,85,247,0.20)" if is_insider_b else "rgba(16,185,129,0.20)"
            badge_txt = "#E9D5FF" if is_insider_b else "#6EE7B7"

            simb = sig.get("simbolo", "$")
            p_sig = float(sig.get("prezzo_segnale") or 0.0)
            p_att = float(sig.get("prezzo_attuale") or p_sig)
            var_pct = ((p_att - p_sig) / p_sig) * 100.0 if p_sig > 0 else 0.0
            var_col = "#4ADE80" if var_pct >= 0 else "#F87171"

            # Semaforo immediato "Ancora Comprabile" vs "Già Corso / Solo Gestione"
            if var_pct <= 3.5:
                sem_html = (
                    "<span style='background:rgba(16,185,129,0.18); color:#4ADE80; border:1px solid rgba(16,185,129,0.55); "
                    "padding:3px 9px; border-radius:5px; font-size:0.78rem; font-weight:800;'>"
                    "🟢 ANCORA COMPRABILE (entro +3.5% dal segnale)</span>"
                )
            else:
                sem_html = (
                    f"<span style='background:rgba(245,158,11,0.18); color:#FBBF24; border:1px solid rgba(245,158,11,0.55); "
                    f"padding:3px 9px; border-radius:5px; font-size:0.78rem; font-weight:800;'>"
                    f"🟡 GIÀ CORSO ({var_pct:+.1f}% dal segnale) — NON INSEGUIRE, SOLO GESTIONE</span>"
                )

            stop_v = float(sig.get("stop_loss") or 0.0)
            target_v = float(sig.get("target") or 0.0)
            trig_v = float(sig.get("trigger_y") or p_sig)
            stop_pct_d = ((stop_v - p_sig) / p_sig) * 100.0 if p_sig > 0 else 0.0
            tgt_pct_d = ((target_v - p_sig) / p_sig) * 100.0 if p_sig > 0 else 0.0
            trig_html = f"<span>⚡ <b>Trigger Y:</b> {simb}{trig_v:.2f}</span>" if not is_insider_b else ""

            c_card, c_act = st.columns([6.2, 1.0])
            with c_card:
                st.markdown(
                    f"""
                    <div style="background:#131722; border:1px solid #2A2E39; border-left:4px solid {b_col};
                                border-radius:8px; padding:0.80rem 1.0rem; margin-bottom:0.55rem;">
                        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:0.40rem;">
                            <div>
                                <span style="background:{badge_bg}; color:{badge_txt}; border:1px solid {b_col};
                                             font-size:0.72rem; font-weight:800; padding:2px 8px; border-radius:4px;">{fonte}</span>
                                <span style="font-size:1.12rem; font-weight:800; color:#FFFFFF; margin-left:8px;">{tk}</span>
                                <span style="color:#94A3B8; font-size:0.80rem; margin-left:8px;">📅 Segnale: <b>{sig.get('data_segnale', '-')}</b></span>
                            </div>
                            <div>{sem_html}</div>
                        </div>
                        <div style="display:flex; flex-wrap:wrap; gap:14px; font-family:'JetBrains Mono', monospace;
                                    font-size:0.83rem; color:#E2E8F0; margin-bottom:0.35rem;">
                            <span>📌 <b>Prezzo Segnale:</b> {simb}{p_sig:.2f}</span>
                            <span>💹 <b>Attuale:</b> {simb}{p_att:.2f} <b style="color:{var_col};">({var_pct:+.1f}%)</b></span>
                            {trig_html}
                            <span style="color:#F87171;">🛑 <b>Stop:</b> {simb}{stop_v:.2f} ({stop_pct_d:+.1f}%)</span>
                            <span style="color:#4ADE80;">🎯 <b>Target:</b> {simb}{target_v:.2f} ({tgt_pct_d:+.1f}%)</span>
                        </div>
                        <div style="display:flex; flex-wrap:wrap; gap:14px; font-size:0.80rem; color:#CBD5E1; margin-bottom:0.30rem;">
                            <span>⏳ <b>Orizzonte:</b> {sig.get('orizzonte', '-')}</span>
                            <span>⚖️ <b>Rischio:</b> {sig.get('rischio', '🌶️🌶️ Medio')}</span>
                            <span>🏛️ <b>Fase:</b> {sig.get('fase_attuale', 'N/D')}</span>
                        </div>
                        <div style="font-size:0.81rem; color:#94A3B8; border-top:1px solid #1E222D; padding-top:0.35rem;">
                            📝 <b style="color:#E2E8F0;">Motivazione:</b> {sig.get('motivazione', '')}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with c_act:
                st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
                if st.button("❌ Archivia", key=f"btn_arch_sig_{sig_id}_{idx_s}", use_container_width=True):
                    sig_arch = dict(sig)
                    sig_arch["stato"] = "ARCHIVIATO"
                    sig_arch["data_chiusura"] = datetime.now().strftime("%Y-%m-%d")
                    sig_arch["rendimento_pct"] = round(var_pct, 2)
                    dati["aperti"] = [x for k_x, x in enumerate(aperti) if k_x != idx_s]
                    dati["chiusi"] = ([sig_arch] + chiusi)[:10]
                    _salva_segnali_attivi(dati)
                    st.rerun()

    # Storico richiudibile degli ultimi 10 segnali chiusi / archiviati
    with st.expander(f"📜 Storico Ultimi Segnali Chiusi / Archiviati ({len(chiusi)}/10)", expanded=False):
        if chiusi:
            mappa_esiti = {
                "CHIUSO_TARGET": "✅ TARGET RAGGIUNTO",
                "CHIUSO_STOP": "🛑 STOP LOSS",
                "CHIUSO_TREND": "📉 TREND FASE 4",
                "ARCHIVIATO": "🗂️ ARCHIVIATO",
            }
            righe_ch = []
            for ch in chiusi[:10]:
                sb = ch.get("simbolo", "$")
                righe_ch.append({
                    "Chiusura": ch.get("data_chiusura", "-"),
                    "Fonte": ch.get("fonte", "-"),
                    "Ticker": ch.get("ticker", "-"),
                    "Esito": mappa_esiti.get(ch.get("stato", ""), ch.get("stato", "-")),
                    "Data Segnale": ch.get("data_segnale", "-"),
                    "Ingresso": f"{sb}{float(ch.get('prezzo_segnale') or 0):.2f}",
                    "Chiusura $": f"{sb}{float(ch.get('prezzo_attuale') or 0):.2f}",
                    "Rendimento %": f"{float(ch.get('rendimento_pct') or 0):+.2f}%",
                })
            st.dataframe(pd.DataFrame(righe_ch), use_container_width=True, hide_index=True)
        else:
            st.caption("Nessun segnale chiuso o archiviato finora.")

def render_simulatore_mediazione_portafoglio(portafoglio):
    """
    Renderizza nella scheda Portafoglio il box richiudibile ad alto contrasto
    '🧮 Simulatore Mediazione & Gain Portafoglio' con calcolo su azioni intere,
    confronto rimbalzo necessario al pareggio e tabella rapida riduzione perdita (-15%, -10%, -5%).
    """
    with st.expander("🧮 Simulatore Mediazione & Gain Portafoglio", expanded=False):
        pos_valide = []
        for p in (portafoglio or []):
            tk = str(p.get("Ticker", "")).strip().upper()
            qta = float(p.get("Quantita", 0) or 0)
            pmc = float(p.get("Prezzo_Medio", 0) or 0)
            p_att = float(p.get("Prezzo_Attuale_EUR") or 0)
            if not tk or qta <= 0 or pmc <= 0:
                continue
            has_live = p_att > 0
            if not has_live:
                p_att = pmc
            val_car = qta * pmc
            val_att = qta * p_att
            pnl_eur = val_att - val_car
            pnl_pct = ((p_att / pmc) - 1.0) * 100.0 if pmc > 0 else 0.0
            pos_valide.append({
                "ticker": tk,
                "tipo": str(p.get("Tipo", "Spot")),
                "qta": qta,
                "pmc": pmc,
                "p_att": p_att,
                "has_live": has_live,
                "val_car": val_car,
                "val_att": val_att,
                "pnl_eur": pnl_eur,
                "pnl_pct": pnl_pct,
            })

        if not pos_valide:
            st.info("Nessuna posizione valida in portafoglio per la simulazione.")
            return

        # 1) Panoramica rapida GAIN / LOSS in due colonnine compatte
        gain_list = sorted([x for x in pos_valide if x["pnl_pct"] >= 0], key=lambda x: x["pnl_pct"], reverse=True)
        loss_list = sorted([x for x in pos_valide if x["pnl_pct"] < 0], key=lambda x: x["pnl_pct"])

        cg_col, cl_col = st.columns(2)
        with cg_col:
            righe_g = ""
            if gain_list:
                for g in gain_list:
                    righe_g += (
                        f"<div style='display:flex; justify-content:space-between; padding:3px 0; border-bottom:1px solid #1E293B; "
                        f"font-family:\"JetBrains Mono\", monospace; font-size:0.83rem; color:#F8FAFC;'>"
                        f"<span><b>{g['ticker']}</b> <span style='color:#94A3B8; font-size:0.75rem;'>({g['tipo']})</span></span>"
                        f"<span style='color:#4ADE80; font-weight:700;'>{g['pnl_pct']:+.1f}% &nbsp;|&nbsp; € {g['pnl_eur']:+,.2f}</span>"
                        f"</div>"
                    )
            else:
                righe_g = "<div style='color:#E2E8F0; font-size:0.82rem;'>Nessun titolo attualmente in gain.</div>"
            st.markdown(
                f"<div style='background:#131722; border:1px solid #334155; border-left:4px solid #10B981; border-radius:8px; padding:0.70rem 0.90rem;'>"
                f"<div style='font-weight:800; color:#F8FAFC; font-size:0.90rem; margin-bottom:0.40rem;'>🟢 Titoli in GAIN ({len(gain_list)})</div>"
                f"{righe_g}</div>",
                unsafe_allow_html=True,
            )
        with cl_col:
            righe_l = ""
            if loss_list:
                for l in loss_list:
                    righe_l += (
                        f"<div style='display:flex; justify-content:space-between; padding:3px 0; border-bottom:1px solid #1E293B; "
                        f"font-family:\"JetBrains Mono\", monospace; font-size:0.83rem; color:#F8FAFC;'>"
                        f"<span><b>{l['ticker']}</b> <span style='color:#94A3B8; font-size:0.75rem;'>({l['tipo']})</span></span>"
                        f"<span style='color:#F87171; font-weight:700;'>{l['pnl_pct']:+.1f}% &nbsp;|&nbsp; € {l['pnl_eur']:+,.2f}</span>"
                        f"</div>"
                    )
            else:
                righe_l = "<div style='color:#E2E8F0; font-size:0.82rem;'>Nessun titolo attualmente in perdita.</div>"
            st.markdown(
                f"<div style='background:#131722; border:1px solid #334155; border-left:4px solid #EF4444; border-radius:8px; padding:0.70rem 0.90rem;'>"
                f"<div style='font-weight:800; color:#F8FAFC; font-size:0.90rem; margin-bottom:0.40rem;'>🔴 Titoli in LOSS ({len(loss_list)})</div>"
                f"{righe_l}</div>",
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

        # Ordina per perdita % più profonda così di default viene preselezionato il titolo con il loss maggiore
        ordinati_sel = sorted(pos_valide, key=lambda x: x["pnl_pct"])
        etichette_sel = [
            f"{x['ticker']} ({x['pnl_pct']:+.1f}% | Att. €{x['p_att']:.2f} | PMC €{x['pmc']:.2f})"
            for x in ordinati_sel
        ]
        c_sel_tk, c_sel_imp = st.columns([1.4, 1.0])
        with c_sel_tk:
            scelta_lbl = st.selectbox(
                "📌 Seleziona titolo da simulare (default: perdita % maggiore):",
                etichette_sel,
                index=0,
                key="sim_med_select_ticker",
            )
        with c_sel_imp:
            imp_sim = st.number_input(
                "💶 Importo indicativo da investire (€):",
                min_value=1.0,
                max_value=500000.0,
                value=300.0,
                step=50.0,
                key="sim_med_importo_eur",
            )

        idx_scelto = etichette_sel.index(scelta_lbl)
        pos_sel = ordinati_sel[idx_scelto]
        tk_s = pos_sel["ticker"]
        q_old = pos_sel["qta"]
        pmc_old = pos_sel["pmc"]
        p_att = pos_sel["p_att"]
        cap_old = pos_sel["val_car"]
        pnl_old = pos_sel["pnl_pct"]

        if not pos_sel["has_live"]:
            st.caption("ℹ️ Quotazione live non ancora caricata per questo titolo: clicca **🔄 Aggiorna Prezzi** per usare il prezzo di mercato reale.")

        # 2) Calcolo con AZIONI INTERE (arrotondate all'intero più vicino, minimo 1 azione)
        az_intere = max(1, int(round(float(imp_sim) / p_att))) if p_att > 0 else 1
        costo_esatto = az_intere * p_att

        # Opzioni +/- 1 azione (in particolare quando l'arrotondamento supera leggermente il budget)
        opz_alt = []
        if az_intere > 1:
            az_m = az_intere - 1
            opz_alt.append(f"<b>{az_m} azioni</b> = € {az_m * p_att:,.2f}" + (" (entro budget)" if costo_esatto > imp_sim else ""))
        az_p = az_intere + 1
        opz_alt.append(f"<b>{az_p} azioni</b> = € {az_p * p_att:,.2f}")
        nota_budget = " (leggermente sopra budget)" if costo_esatto > imp_sim else " (entro budget)"

        q_new = q_old + az_intere
        cap_new = cap_old + costo_esatto
        pmc_new = cap_new / q_new if q_new > 0 else pmc_old
        pnl_new = ((p_att / pmc_new) - 1.0) * 100.0 if pmc_new > 0 else 0.0

        # Rimbalzo necessario per tornare esattamente a 0,00% (pareggio)
        if pnl_old < 0:
            rimb_prima = ((pmc_old / p_att) - 1.0) * 100.0 if p_att > 0 else 0.0
            rimb_dopo = ((pmc_new / p_att) - 1.0) * 100.0 if p_att > 0 else 0.0
            stato_riga = (
                f"📉 <b>Perdita %:</b> da <b style='color:#F87171;'>{pnl_old:+.2f}%</b> a <b style='color:#F8FAFC;'>{pnl_new:+.2f}%</b> "
                f"&nbsp;|&nbsp; 🚀 <b>Rimbalzo per pareggio (0,00%):</b> da <b>+{rimb_prima:.2f}%</b> a <b style='color:#4ADE80;'>+{rimb_dopo:.2f}%</b> "
                f"(risparmi <b>{max(0.0, rimb_prima - rimb_dopo):.2f} punti %</b>)"
            )
            bordo_ris = "#38BDF8"
        else:
            cuscinetto_new = ((p_att / pmc_new) - 1.0) * 100.0 if pmc_new > 0 else 0.0
            stato_riga = (
                f"📈 <b>Gain % aggiornato:</b> da <b style='color:#4ADE80;'>{pnl_old:+.2f}%</b> a <b style='color:#F8FAFC;'>{pnl_new:+.2f}%</b> "
                f"&nbsp;|&nbsp; 🛡️ <b>Nuovo livello di pareggio (PMC):</b> <b style='color:#F8FAFC;'>€ {pmc_new:.2f}</b> "
                f"(margine cuscinetto: <b>{cuscinetto_new:+.2f}%</b>)"
            )
            bordo_ris = "#10B981"

        st.markdown(
            f"""
            <div style="background:#131722; border:1px solid #334155; border-left:4px solid {bordo_ris};
                        border-radius:8px; padding:0.85rem 1.05rem; margin-top:0.35rem; margin-bottom:0.70rem;">
                <div style="font-size:0.96rem; font-weight:800; color:#F8FAFC; margin-bottom:0.40rem;">
                    🧾 Simulazione su {tk_s} @ € {p_att:.2f} — <span style="color:#4ADE80;">{az_intere} azioni intere = € {costo_esatto:,.2f}</span>
                    <span style="font-size:0.80rem; font-weight:600; color:#E2E8F0;">{nota_budget}</span>
                </div>
                <div style="font-size:0.80rem; color:#E2E8F0; margin-bottom:0.45rem;">
                    🔁 Alternative ±1 azione: {' &nbsp;|&nbsp; '.join(opz_alt)}
                </div>
                <div style="display:flex; flex-wrap:wrap; gap:18px; font-family:'JetBrains Mono', monospace;
                            font-size:0.85rem; color:#F8FAFC; margin-bottom:0.45rem; padding:0.45rem 0.65rem;
                            background:#0B0E11; border:1px solid #1E293B; border-radius:6px;">
                    <span>🎯 <b>Nuovo PMC:</b> € {pmc_new:.2f} <span style="color:#E2E8F0;">(prima € {pmc_old:.2f})</span></span>
                    <span>📦 <b>Azioni Totali:</b> {q_new:.4f} <span style="color:#E2E8F0;">(prima {q_old:.4f})</span></span>
                    <span>💶 <b>Capitale Investito:</b> € {cap_new:,.2f} <span style="color:#E2E8F0;">(prima € {cap_old:,.2f})</span></span>
                </div>
                <div style="font-size:0.85rem; color:#F8FAFC; line-height:1.5;">
                    {stato_riga}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 3) Tabella rapida "Quanto serve per ridurre la perdita" (SOLO per titoli in LOSS)
        if pnl_old < 0 and p_att > 0:
            st.markdown(f"**📊 Quanto serve per ridurre la perdita di `{tk_s}` (Azioni Intere @ € {p_att:.2f}):**")
            righe_ob = []
            for target_loss_pct in (15.0, 10.0, 5.0):
                L = target_loss_pct / 100.0
                if pnl_old >= -target_loss_pct:
                    righe_ob.append({
                        "Obiettivo Perdita": f"-{int(target_loss_pct)}%",
                        "Azioni Intere da Comprare": 0,
                        "Costo Stimato (€)": "€ 0,00",
                        "Nuovo PMC (€)": f"€ {pmc_old:.2f}",
                        "Perdita Risultante": f"{pnl_old:+.2f}% (✅ già raggiunto)",
                        "Rimbalzo per Pareggio": f"+{((pmc_old / p_att) - 1.0) * 100.0:.2f}%",
                    })
                else:
                    pmc_target = p_att / (1.0 - L)
                    denom = pmc_target - p_att
                    n_esatto = (q_old * (pmc_old - pmc_target)) / denom if denom > 0 else 0.0
                    n_int = max(1, int(math.ceil(n_esatto)))
                    costo_ob = n_int * p_att
                    pmc_ris = (cap_old + costo_ob) / (q_old + n_int)
                    pnl_ris = ((p_att / pmc_ris) - 1.0) * 100.0
                    rimb_ris = ((pmc_ris / p_att) - 1.0) * 100.0
                    righe_ob.append({
                        "Obiettivo Perdita": f"-{int(target_loss_pct)}%",
                        "Azioni Intere da Comprare": n_int,
                        "Costo Stimato (€)": f"€ {costo_ob:,.2f}",
                        "Nuovo PMC (€)": f"€ {pmc_ris:.2f}",
                        "Perdita Risultante": f"{pnl_ris:+.2f}%",
                        "Rimbalzo per Pareggio": f"+{rimb_ris:.2f}%",
                    })
            st.dataframe(pd.DataFrame(righe_ob), use_container_width=True, hide_index=True)

def _get_impostazioni_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), IMPOSTAZIONI_FILE)

def _parse_ora_agg(val):
    if not val:
        return None
    try:
        return datetime.strptime(str(val).strip(), "%d/%m/%Y %H:%M")
    except Exception:
        return None

def _scegli_ora_piu_recente(*candidati):
    best_dt = None
    best_str = None
    fallback_str = None
    for c in candidati:
        if not c:
            continue
        s = str(c).strip()
        if not s or s == "-":
            continue
        if fallback_str is None:
            fallback_str = s
        dt = _parse_ora_agg(s)
        if dt is not None and (best_dt is None or dt > best_dt):
            best_dt = dt
            best_str = s
    return best_str or fallback_str

def leggi_ultimo_agg_prezzi():
    imp = {}
    fp_imp = _get_impostazioni_path()
    if os.path.exists(fp_imp):
        try:
            with open(fp_imp, 'r', encoding='utf-8') as f_imp:
                data_imp = json.load(f_imp)
            if isinstance(data_imp, dict):
                imp = data_imp
        except Exception:
            imp = {}
    ora_best = _scegli_ora_piu_recente(
        imp.get("ultimo_agg_prezzi"),
        imp.get("_saved_last_price_update"),
        st.session_state.get("_last_price_update")
    )
    if not ora_best:
        fp_port = os.path.join(os.path.dirname(os.path.abspath(__file__)), PORTAFOGLIO_FILE)
        if os.path.exists(fp_port):
            try:
                ora_best = datetime.fromtimestamp(os.path.getmtime(fp_port)).strftime("%d/%m/%Y %H:%M")
            except Exception:
                ora_best = "-"
        else:
            ora_best = "-"
    if ora_best and ora_best != "-":
        st.session_state["_last_price_update"] = ora_best
    return ora_best

def salva_ultimo_agg_prezzi(ora_str=None):
    nuova_ora = str(ora_str).strip() if ora_str else datetime.now().strftime("%d/%m/%Y %H:%M")
    fp_imp = _get_impostazioni_path()
    imp = {}
    if os.path.exists(fp_imp):
        try:
            with open(fp_imp, 'r', encoding='utf-8') as f_imp:
                data_imp = json.load(f_imp)
            if isinstance(data_imp, dict):
                imp = data_imp
        except Exception:
            imp = {}
    ora_finale = _scegli_ora_piu_recente(
        nuova_ora,
        imp.get("ultimo_agg_prezzi"),
        imp.get("_saved_last_price_update"),
        st.session_state.get("_last_price_update")
    ) or nuova_ora
    imp["ultimo_agg_prezzi"] = ora_finale
    imp.pop("_saved_last_price_update", None)
    try:
        with open(fp_imp, 'w', encoding='utf-8') as f_imp:
            json.dump(imp, f_imp, indent=4, ensure_ascii=False)
        try:
            _sync_github_file(IMPOSTAZIONI_FILE, json.dumps(imp, indent=4, ensure_ascii=False), mode='push')
        except Exception:
            pass
    except Exception:
        pass
    st.session_state["_last_price_update"] = ora_finale
    return ora_finale

def registra_proposta(modulo, azione, ticker, dettaglio, stato="N/D"):
    try:
        log = carica_json(LOG_PROPOSTE_FILE)
        log.append({
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'modulo': modulo,
            'azione': azione,
            'ticker': ticker,
            'dettaglio': dettaglio,
            'stato_mercato': stato
        })
        if len(log) > 500:
            log = log[-500:]
        salva_json(LOG_PROPOSTE_FILE, log)
    except Exception as e:
        print(f"Errore log proposta: {e}")

def calcola_semaforo_mercato():
    try:
        spy = yf.Ticker('SPY').history(period='1mo')
        if spy.empty or len(spy) < 10:
            return {'stato': 'giallo', 'spy_prezzo': None, 'spy_sma10': None, 'vix': None, 'messaggio': 'Dati SPY insufficienti'}
        spy['SMA10'] = spy['Close'].rolling(10).mean()
        spy_prezzo = float(spy['Close'].iloc[-1])
        spy_sma10 = float(spy['SMA10'].iloc[-1])
        vix_valore = None
        try:
            vix = yf.Ticker('^VIX').history(period='1d')
            if not vix.empty:
                vix_valore = float(vix['Close'].iloc[-1])
        except:
            pass
        if vix_valore is not None:
            if spy_prezzo > spy_sma10 and vix_valore < 18.5:
                stato, messaggio = 'verde', '🟢 MERCATO RIALZISTA - Strategia Aggressiva'
            elif spy_prezzo < spy_sma10 or vix_valore > 30:
                stato, messaggio = 'rosso', '🔴 MERCATO RIBASSISTA - Strategia Difensiva'
            else:
                stato, messaggio = 'giallo', '🟡 MERCATO LATERALE - Strategia Selettiva'
        else:
            if spy_prezzo > spy_sma10:
                stato, messaggio = 'verde', '🟢 SPY RIALZISTA (VIX N/D)'
            elif spy_prezzo < spy_sma10:
                stato, messaggio = 'rosso', '🔴 SPY RIBASSISTA (VIX N/D)'
            else:
                stato, messaggio = 'giallo', '🟡 SPY LATERALE (VIX N/D)'
        return {
            'stato': stato,
            'spy_prezzo': round(spy_prezzo, 2),
            'spy_sma10': round(spy_sma10, 2),
            'vix': round(vix_valore, 2) if vix_valore else None,
            'messaggio': messaggio
        }
    except Exception as e:
        return {'stato': 'giallo', 'spy_prezzo': None, 'spy_sma10': None, 'vix': None, 'messaggio': f'Errore: {str(e)}'}
# ==============================================================================
# MODULO 2: SIMULATORE DI ACQUISTO INTELLIGENTE
# ==============================================================================
def simula_acquisto(titolo, importo, portafoglio, eurusd_rate, esclusioni_list=None, catalizzatori_input=""):
    scenari = {'vendita_gain': list(), 'vendita_loss': list(), 'hold_catalizzatore': list(), 'nuova_liquidita': True}
    if esclusioni_list is None:
        esclusioni_list = list()
    catalizzatori = dict()
    if catalizzatori_input:
        for item in catalizzatori_input.split(';'):
            item = item.strip()
            if ':' in item:
                ticker, resto = item.split(':', 1)
                ticker = ticker.strip().upper()
                match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', resto)
                if match:
                    giorno, mese, anno = match.groups()
                    if len(anno) == 2:
                        anno = '20' + anno
                    try:
                        data_cat = datetime(int(anno), int(mese), int(giorno))
                        catalizzatori[ticker] = {'descrizione': resto.split('-')[0].strip() if '-' in resto else resto.strip(), 'data': data_cat}
                    except:
                        pass
    oggi = datetime.now()
    try:
        ticker_obj = yf.Ticker(titolo)
        info = ticker_obj.info
        hist = ticker_obj.history(period='1y')
        if hist.empty:
            return {'errore': f'Impossibile recuperare dati per {titolo}'}
        currency = info.get('currency', 'USD')
        prezzo_raw = hist['Close'].dropna().iloc[-1]
        prezzo_eur = prezzo_raw / eurusd_rate if currency == 'USD' else prezzo_raw
        quantita_acquistabile = importo / prezzo_eur
        for pos in portafoglio:
            ticker_pos = pos['Ticker']
            if ticker_pos in esclusioni_list:
                continue
            try:
                ticker_obj_pos = yf.Ticker(ticker_pos)
                hist_pos = ticker_obj_pos.history(period='1y')
                info_pos = ticker_obj_pos.info
                if hist_pos.empty:
                    continue
                currency_pos = info_pos.get('currency', 'USD')
                prezzo_raw_pos = hist_pos['Close'].iloc[-1]
                prezzo_eur_pos = prezzo_raw_pos / eurusd_rate if currency_pos == 'USD' else prezzo_raw_pos
                prezzo_medio = pos['Prezzo_Medio']
                pnl_pct = ((prezzo_eur_pos / prezzo_medio) - 1) * 100 if prezzo_medio > 0 else 0
                trend_30gg = 0
                if len(hist_pos) >= 30:
                    trend_30gg = ((hist_pos['Close'].iloc[-1] / hist_pos['Close'].iloc[-30]) - 1) * 100
                s_score = calcola_s_score(info_pos)
                fase = rileva_fase_weinstein(hist_pos)
                kill_switch = ("FASE 4" in fase or s_score < 50)
                has_catalizzatore = False
                if ticker_pos in catalizzatori:
                    if catalizzatori[ticker_pos]['data'] >= oggi:
                        has_catalizzatore = True
                if has_catalizzatore:
                    scenari['hold_catalizzatore'].append({'ticker': ticker_pos, 'messaggio': f"⚠️ {ticker_pos} ha un catalizzatore imminente. Non vendere nonostante la perdita."})
                elif pnl_pct > 0 and trend_30gg > 0:
                    scenari['vendita_gain'].append({'ticker': ticker_pos, 'pnl_pct': round(pnl_pct, 2), 'trend_30gg': round(trend_30gg, 2), 'quantita': pos['Quantita'], 'valore': round(prezzo_eur_pos * pos['Quantita'], 2), 'messaggio': f'⚠️ NON VENDERE: {ticker_pos} è in gain (+{pnl_pct:.1f}%) con trend positivo (+{trend_30gg:.1f}% in 30gg). Ha impiegato mesi per caricarsi ed è ora pronto a ripartire.'})
                elif pnl_pct < 0 or kill_switch:
                    supporto = hist_pos['Low'].tail(20).min()
                    distanza_supporto = ((prezzo_eur_pos - supporto) / supporto) * 100 if supporto > 0 else 0
                    scenari['vendita_loss'].append({'ticker': ticker_pos, 'pnl_pct': round(pnl_pct, 2), 'kill_switch': kill_switch, 'distanza_supporto': round(distanza_supporto, 2), 'quantita': pos['Quantita'], 'valore': round(prezzo_eur_pos * pos['Quantita'], 2), 'messaggio': f'✅ CONSIDERA VENDITA: {ticker_pos} è in loss ({pnl_pct:.1f}%) {"con Kill Switch attivo" if kill_switch else ""}. Ottimizzazione fiscale possibile.'})
            except:
                continue
        if scenari['vendita_loss']:
            scenari['nuova_liquidita'] = False
        return {'titolo': titolo, 'prezzo_eur': round(prezzo_eur, 2), 'quantita_acquistabile': round(quantita_acquistabile, 6), 'importo': importo, 'scenari': scenari}
    except Exception as e:
        return {'errore': str(e)}

# ==============================================================================
# MODULO 3: MOTORE DI RIBILANCIAMENTO MENSILE
# ==============================================================================
def parse_catalizzatori(testo):
    catalizzatori = dict()
    if not testo:
        return catalizzatori
    for item in testo.split(';'):
        item = item.strip()
        if ':' in item:
            ticker, resto = item.split(':', 1)
            ticker = ticker.strip().upper()
            match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', resto)
            if match:
                giorno, mese, anno = match.groups()
                if len(anno) == 2:
                    anno = '20' + anno
                try:
                    data_cat = datetime(int(anno), int(mese), int(giorno))
                    catalizzatori[ticker] = {'descrizione': resto.split('-')[0].strip() if '-' in resto else resto.strip(), 'data': data_cat}
                except:
                    pass
    return catalizzatori

def calcola_score_ribilanciamento(ticker, df, info, insider_data=None):
    score = 0
    fase = rileva_fase_weinstein(df)
    if "FASE 2" in fase:
        score += 30
    elif "FASE 1" in fase:
        score += 20
    elif "FASE 3" in fase:
        score += 10
    elif "CORREZIONE" in fase:
        score += 25
    else:
        score += 0
    s_score = calcola_s_score(info)
    score += (s_score / 100) * 25
    if len(df) >= 30:
        trend_30gg = ((df['Close'].iloc[-1] / df['Close'].iloc[-30]) - 1) * 100
        if trend_30gg > 10:
            score += 20
        elif trend_30gg > 5:
            score += 15
        elif trend_30gg > 0:
            score += 10
        elif trend_30gg > -5:
            score += 5
        else:
            score += 10
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi_val = float((100 - (100 / (1 + rs))).iloc[-1]) if not rs.empty else 50
    if 40 <= rsi_val <= 60:
        score += 15
    elif 30 <= rsi_val < 40:
        score += 12
    elif 60 < rsi_val <= 70:
        score += 10
    else:
        score += 5
    if insider_data:
        if insider_data.get('has_buy'):
            score += 10
        elif insider_data.get('has_sell'):
            score += 0
        else:
            score += 5
    else:
        score += 5
    return min(100, max(0, round(score, 1)))
def genera_piano_ribilanciamento(portafoglio, watchlist_tickers, semaforo, catalizzatori, esclusioni, eurusd_rate):
    oggi = datetime.now()
    vendite, monitor, acquisti = list(), list(), list()
    for pos in portafoglio:
        ticker = pos['Ticker']
        if ticker in esclusioni:
            continue
        try:
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period='1y')
            info = ticker_obj.info
            if df.empty:
                continue
            score = calcola_score_ribilanciamento(ticker, df, info, {'has_buy': False, 'has_sell': False})
            fase = rileva_fase_weinstein(df)
            has_catalizzatore = False
            cat_desc = ""
            if ticker in catalizzatori:
                cat = catalizzatori[ticker]
                if cat['data'] >= oggi:
                    has_catalizzatore = True
                    cat_desc = cat['descrizione']
            pnl_pct = round(((pos.get('Prezzo_Attuale_EUR', 0) / pos.get('Prezzo_Medio', 1)) - 1) * 100 if pos.get('Prezzo_Medio', 0) > 0 else 0, 2)
            if has_catalizzatore:
                monitor.append({'ticker': ticker, 'score': score, 'fase': fase, 'messaggio': f"⚠️ HOLD FORZATO: Ha un catalizzatore imminente ({cat_desc}). Non vendere nonostante il punteggio."})
            elif "FASE 3" in fase:
                vendite.append({'ticker': ticker, 'score': score, 'fase': fase, 'pnl_pct': pnl_pct, 'messaggio': "⚠️ Fase di distribuzione in atto. Valuta vendita parziale o totale per proteggere i guadagni."})
            elif "FASE 4" in fase:
                s_score_check = calcola_s_score(info)
                if s_score_check >= 60:
                    monitor.append({'ticker': ticker, 'score': score, 'fase': fase, 'pnl_pct': pnl_pct, 'messaggio': f"⚠️ FASE 4 ma S-Score alto ({s_score_check}). Possibile falsa Fase 4 (accumulazione). Monitorare, non vendere."})
                else:
                    vendite.append({'ticker': ticker, 'score': score, 'fase': fase, 'pnl_pct': pnl_pct, 'messaggio': "🔴 FASE 4 (Declino Strutturale): Vendita consigliata per proteggere il capitale."})
            elif score < 40:
                vendite.append({'ticker': ticker, 'score': score, 'fase': fase, 'pnl_pct': pnl_pct, 'messaggio': "Score basso e trend debole. Ottimizzazione fiscale consigliata."})
            elif "FASE 1" in fase and score >= 40:
                monitor.append({'ticker': ticker, 'score': score, 'fase': fase, 'messaggio': "🟢 Pronti al Rimbalzo: Titolo in fase di accumulo, pronto a ripartire quando il mercato gira."})
            elif "CORREZIONE" in fase:
                monitor.append({'ticker': ticker, 'score': score, 'fase': fase, 'messaggio': "🟡 Correzione in Trend: Pullback sano in Fase 2. Monitorare per ingresso."})
            else:
                monitor.append({'ticker': ticker, 'score': score, 'fase': fase, 'messaggio': "Monitorare l'evoluzione del trend."})
        except:
            continue

    BIG_TECH_GROWTH_LIST = "GOOGL, AMZN, PLTR, META, MSFT, AAPL, TSLA, AVGO, CRM, ADBE, NOW, PANW, FTNT, CRDO, SMCI, ARMR, MRVL, QCOM, MU, INTU"
    watchlist_tickers = [t.strip().upper() for t in BIG_TECH_GROWTH_LIST.split(",")]
    for ticker in watchlist_tickers:
        if any(p['Ticker'] == ticker for p in portafoglio) or ticker in esclusioni:
            continue
        try:
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period='1y')
            info = ticker_obj.info
            if df.empty:
                continue
            score = calcola_score_ribilanciamento(ticker, df, info, {'has_buy': False, 'has_sell': False})
            fase = rileva_fase_weinstein(df)
            prezzo_eur = round((df['Close'].iloc[-1] / eurusd_rate) if info.get('currency', 'USD') == 'USD' else df['Close'].iloc[-1], 2)
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_val = float((100 - (100 / (1 + rs))).iloc[-1]) if not rs.empty else 50
            sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
            prezzo_attuale = df['Close'].dropna().iloc[-1]
            distanza_sma200_pct = abs(prezzo_attuale - sma200) / sma200 * 100 if sma200 > 0 else 999
            s_score = calcola_s_score(info)
            is_extreme_oversold = (s_score >= 85 and rsi_val < 30)
            if score > 75 or is_extreme_oversold:
                if semaforo['stato'] == 'rosso':
                    msg = "⚠️ Titolo pronto all'acquisto, ma acquisti sospesi per mercato ribassista. Ricontrolla tra 7 giorni."
                    if is_extreme_oversold:
                        msg = "⚠️ Rimbalzo Tecnico Estremo: Titolo ipervenduto con fondamentali solidi. Alto rischio/alto rendimento. Valuta ingresso con position sizing ridotto. (Acquisti sospesi per mercato ribassista)."
                else:
                    msg = "✅ Setup valido e mercato favorevole."
                    if is_extreme_oversold:
                        msg = "⚠️ Rimbalzo Tecnico Estremo: Titolo ipervenduto con fondamentali solidi. Alto rischio/alto rendimento. Valuta ingresso con position sizing ridotto."
                acquisti.append({'ticker': ticker, 'score': score, 'fase': fase, 'prezzo_eur': prezzo_eur, 'stato_mercato': 'sospeso' if semaforo['stato'] == 'rosso' else 'attivo', 'messaggio': msg, 's_score': s_score, 'rsi': rsi_val, 'distanza_sma': distanza_sma200_pct})
        except:
            continue

    acquisti_sorted = sorted(acquisti, key=lambda x: (-x.get('s_score', 0), x.get('rsi', 50), x.get('distanza_sma', 100)))
    for idx, item in enumerate(acquisti_sorted):
        rank = idx + 1
        if rank == 1:
            badge = "🥇 PRIORITÀ 1"
        elif rank == 2:
            badge = "🥈 PRIORITÀ 2"
        elif rank == 3:
            badge = "🥉 PRIORITÀ 3"
        else:
            badge = f"🎯 PRIORITÀ {rank}"
        upside_msg = " | Upside stimato: Alto" if item.get('s_score', 0) >= 85 and item.get('rsi', 50) < 30 else ""
        item['badge'] = f"{badge}{upside_msg}"

    return {'vendite': sorted(vendite, key=lambda x: x['score']), 'monitor': sorted(monitor, key=lambda x: x['score'], reverse=True), 'acquisti': acquisti_sorted, 'semaforo': semaforo['stato']}

def registra_acquisto(ticker, qta_acquistata, prezzo_acquisto, data_acquisto=None):
    try:
        if data_acquisto is None:
            data_acquisto = datetime.now().strftime("%Y-%m-%d")
        importo_totale = prezzo_acquisto * qta_acquistata
        registro = carica_json(REGISTRO_ACQUISTI_FILE)
        id_op = max([v.get('id', 0) for v in registro], default=0) + 1
        registro.append({'id': id_op, 'Data': data_acquisto, 'Ticker': ticker.strip().upper(), 'Qta_Acquistata': round(qta_acquistata, 6), 'Prezzo_Acquisto': round(prezzo_acquisto, 4), 'Importo_Totale': round(importo_totale, 2)})
        salva_json(REGISTRO_ACQUISTI_FILE, registro)
        return {'id': id_op, 'importo_totale': round(importo_totale, 2)}
    except Exception as e:
        print(f"Errore registrazione acquisto: {e}")
        return None
def genera_piano_allocazione(portafoglio, liquidita_totale, eurusd_rate, watchlist_tickers=None, registro_acquisti=None):
    if watchlist_tickers is None:
        watchlist_tickers = list()
    if registro_acquisti is None:
        registro_acquisti = carica_json(REGISTRO_ACQUISTI_FILE)
    oggi = datetime.now()
    ticker_acquistati_recenti = set()
    for v in registro_acquisti:
        try:
            data_acquisto = datetime.strptime(v.get('Data', ''), "%Y-%m-%d")
            giorni_fa = (oggi - data_acquisto).days
            if giorni_fa <= 5:
                ticker_acquistati_recenti.add(v.get('Ticker', '').strip().upper())
        except:
            pass
    watchlist_filtrata = [t for t in watchlist_tickers if t not in ticker_acquistati_recenti]
    by_fabio_tickers, pac_ottimali, watchlist_breakout, nuove_entrate = list(), list(), list(), list()

    for pos in portafoglio:
        ticker = pos['Ticker']
        try:
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period='1y')
            info = ticker_obj.info
            if df.empty:
                continue
            s_score = calcola_s_score(info)
            fase = rileva_fase_weinstein(df)
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_oggi = float((100 - (100 / (1 + rs))).iloc[-1]) if not rs.empty else 50
            prezzo_raw = df['Close'].iloc[-1]
            currency = info.get('currency', 'USD')
            prezzo = prezzo_raw / eurusd_rate if currency == 'USD' else prezzo_raw
            trigger_by_fabio, motivo_by_fabio = verifica_by_fabio(df, 50, ticker_obj)
            if trigger_by_fabio:
                by_fabio_tickers.append({'ticker': ticker, 's_score': s_score, 'fase': fase, 'rsi': rsi_oggi, 'prezzo': prezzo, 'motivo': motivo_by_fabio, 'tipo': 'pyramiding'})
                continue
            if pos.get('Tipo') == 'PAC' and fase in ["FASE 2 (Avanzamento)", "CORREZIONE in Trend (Pullback Fase 2)"]:
                pac_ottimali.append({'ticker': ticker, 's_score': s_score, 'fase': fase, 'rsi': rsi_oggi, 'prezzo': prezzo, 'tipo': 'pac_extra'})
                continue
        except:
            continue

    ticker_in_portafoglio = {p['Ticker'] for p in portafoglio}
    for ticker in watchlist_filtrata:
        if ticker in ticker_in_portafoglio:
            continue
        try:
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period='1y')
            info = ticker_obj.info
            if df.empty:
                continue
            s_score = calcola_s_score(info)
            fase = rileva_fase_weinstein(df)
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_oggi = float((100 - (100 / (1 + rs))).iloc[-1]) if not rs.empty else 50
            prezzo_raw = df['Close'].iloc[-1]
            currency = info.get('currency', 'USD')
            prezzo = prezzo_raw / eurusd_rate if currency == 'USD' else prezzo_raw
            sma50 = df['Close'].rolling(window=50).mean().iloc[-1]
            vol_medio = df['Volume'].rolling(window=20).mean().iloc[-1]
            vol_oggi = df['Volume'].iloc[-1]
            trigger_by_fabio, motivo_by_fabio = verifica_by_fabio(df, 50, ticker_obj)
            if trigger_by_fabio:
                nuove_entrate.append({'ticker': ticker, 's_score': s_score, 'fase': fase, 'rsi': rsi_oggi, 'prezzo': prezzo, 'motivo': motivo_by_fabio, 'tipo': 'nuova_entrata'})
                continue
            if s_score >= 65 and prezzo < sma50 * 0.95 and 30 <= rsi_oggi <= 50 and vol_oggi > vol_medio * 1.2:
                if ticker not in [t['ticker'] for t in watchlist_breakout]:
                    watchlist_breakout.append({'ticker': ticker, 's_score': s_score, 'fase': fase, 'rsi': rsi_oggi, 'prezzo': prezzo, 'tipo': 'breakout'})
        except:
            continue

    capitale_residuo = liquidita_totale
    allocazioni = list()
    all_by_fabio = by_fabio_tickers + nuove_entrate
    if all_by_fabio:
        importo_per_ticker = (capitale_residuo * 0.45) / len(all_by_fabio)
        for t in all_by_fabio:
            azioni = round(importo_per_ticker / t['prezzo'], 4) if t['prezzo'] > 0 else 0
            nuovo_medio_display = ""
            if t['tipo'] == 'pyramiding':
                pos_attuale = next((p for p in portafoglio if p['Ticker'] == t['ticker']), None)
                if pos_attuale:
                    qta_attuale = pos_attuale.get('Quantita', 0)
                    prezzo_medio_attuale = pos_attuale.get('Prezzo_Medio', 0)
                    if qta_attuale > 0 and azioni > 0:
                        nuovo_medio = ((qta_attuale * prezzo_medio_attuale) + (azioni * t['prezzo'])) / (qta_attuale + azioni)
                        nuovo_medio_display = f" | Nuovo medio: €{nuovo_medio:.2f} (da €{prezzo_medio_attuale:.2f})"
            motivazione = f"🔁 AGGIUNGI {azioni} azioni di {t['ticker']} (Pyramiding) - Totale: €{importo_per_ticker:.0f} - {t.get('motivo', '')}{nuovo_medio_display}" if t['tipo'] == 'pyramiding' else f"🆕 ACQUISTA {azioni} azioni di {t['ticker']} (Nuova Entrata BY FABIO) - Totale: €{importo_per_ticker:.0f} - {t.get('motivo', '')}"
            allocazioni.append({'ticker': t['ticker'], 'importo': round(importo_per_ticker, 2), 'azioni': azioni, 'motivazione': motivazione, 'priorita': 1, 'tipo': t['tipo'], 'prezzo': t['prezzo']})
        capitale_residuo -= importo_per_ticker * len(all_by_fabio)

    if pac_ottimali and capitale_residuo > 0:
        importo_per_ticker = (capitale_residuo * 0.30) / len(pac_ottimali)
        for t in pac_ottimali:
            azioni = round(importo_per_ticker / t['prezzo'], 4) if t['prezzo'] > 0 else 0
            nuovo_medio_display = ""
            pos_attuale = next((p for p in portafoglio if p['Ticker'] == t['ticker']), None)
            if pos_attuale:
                qta_attuale = pos_attuale.get('Quantita', 0)
                prezzo_medio_attuale = pos_attuale.get('Prezzo_Medio', 0)
                if qta_attuale > 0 and azioni > 0:
                    nuovo_medio = ((qta_attuale * prezzo_medio_attuale) + (azioni * t['prezzo'])) / (qta_attuale + azioni)
                    nuovo_medio_display = f" | Nuovo medio: €{nuovo_medio:.2f} (da €{prezzo_medio_attuale:.2f})"
            allocazioni.append({'ticker': t['ticker'], 'importo': round(importo_per_ticker, 2), 'azioni': azioni, 'motivazione': f"📈 ACQUISTO EXTRA {azioni} azioni su {t['ticker']} (Non è il PAC settimanale) - Totale: €{importo_per_ticker:.0f} - {t['fase']} | S-Score {t['s_score']}{nuovo_medio_display}", 'priorita': 2, 'tipo': t['tipo'], 'prezzo': t['prezzo']})
        capitale_residuo -= importo_per_ticker * len(pac_ottimali)

    if watchlist_breakout and capitale_residuo > 0:
        importo_per_ticker = (capitale_residuo * 0.20) / len(watchlist_breakout)
        for t in watchlist_breakout:
            azioni = round(importo_per_ticker / t['prezzo'], 4) if t['prezzo'] > 0 else 0
            allocazioni.append({'ticker': t['ticker'], 'importo': round(importo_per_ticker, 2), 'azioni': azioni, 'motivazione': f"⚡ ACQUISTA {azioni} azioni di {t['ticker']} (Breakout Imminente) - Totale: €{importo_per_ticker:.0f} - S-Score {t['s_score']} | RSI {t['rsi']:.0f}", 'priorita': 3, 'tipo': t['tipo'], 'prezzo': t['prezzo']})
        capitale_residuo -= importo_per_ticker * len(watchlist_breakout)

    allocazioni.sort(key=lambda x: (x['priorita'], -x['importo']))
    contatore_proposte = 0
    for alloc in allocazioni:
        if alloc['importo'] >= 50 and contatore_proposte < 3:
            alloc['proposto'] = True
            contatore_proposte += 1
        else:
            alloc['proposto'] = False

    return {'allocazioni': allocazioni, 'liquidita_residua': round(capitale_residuo, 2), 'by_fabio_count': len(by_fabio_tickers), 'nuove_entrate_count': len(nuove_entrate), 'pac_ottimali_count': len(pac_ottimali), 'watchlist_breakout_count': len(watchlist_breakout), 'proposte_count': contatore_proposte}
# ==============================================================================
# SISTEMA SEGNALI STORICI
# ==============================================================================
def registra_segnale(ticker, tipo_segnale, prezzo_usd, data_segnale=None):
    try:
        segnali = carica_json(SEGNALI_STORICI_FILE)
        if data_segnale is None:
            data_segnale = datetime.now().strftime("%Y-%m-%d")
        ticker_norm = ticker.strip().upper()
        for segnale in segnali:
            if segnale.get('Ticker', '').strip().upper() == ticker_norm and segnale.get('Data') == data_segnale:
                return
        segnali.append({'Ticker': ticker_norm, 'Tipo': tipo_segnale, 'Data': data_segnale, 'Prezzo': round(prezzo_usd, 2)})
        salva_json(SEGNALI_STORICI_FILE, segnali)
    except:
        pass

def get_ultimo_segnale(ticker):
    try:
        segnali = carica_json(SEGNALI_STORICI_FILE)
        if not segnali:
            return None
        ticker_norm = ticker.strip().upper()
        segnali_ticker = [s for s in segnali if s.get('Ticker', '').strip().upper() == ticker_norm]
        if not segnali_ticker:
            return None
        segnali_ticker.sort(key=lambda x: x.get('Data', ''), reverse=True)
        return segnali_ticker[0]
    except:
        return None

def calcola_performance_segnale(segnale, prezzo_attuale):
    if segnale is None:
        return None, None, None
    try:
        prezzo_segnale = segnale.get('Prezzo', 0)
        if prezzo_segnale is None or prezzo_segnale == 0:
            return None, None, None
        data_segnale = datetime.strptime(segnale.get('Data', ''), "%Y-%m-%d")
        giorni_trascorsi = (datetime.now() - data_segnale).days
        variazione_pct = ((prezzo_attuale - prezzo_segnale) / prezzo_segnale) * 100
        return variazione_pct, giorni_trascorsi, prezzo_segnale
    except:
        return None, None, None

def formatta_data_europea(data_iso):
    try:
        return datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        return data_iso

def format_ultimo_segnale_display(ticker, prezzo_attuale_usd):
    try:
        if prezzo_attuale_usd is None or prezzo_attuale_usd == 0:
            return "N/D"
        ultimo_segnale = get_ultimo_segnale(ticker)
        if not ultimo_segnale:
            return "N/D"
        prezzo_segnale = ultimo_segnale.get('Prezzo', 0)
        if prezzo_segnale is None or prezzo_segnale == 0:
            return "N/D"
        var_pct = ((prezzo_attuale_usd - prezzo_segnale) / prezzo_segnale) * 100
        data_fmt = formatta_data_europea(ultimo_segnale.get('Data', ''))
        tipo = ultimo_segnale.get('Tipo', 'N/D')
        segno = "+" if var_pct > 0 else ""
        if tipo == 'BY':
            return f"🟢 BY: {data_fmt} ({segno}{var_pct:.1f}%)" if var_pct >= 0 else f"🔴 BY: {data_fmt} ({segno}{var_pct:.1f}%)"
        elif tipo == 'BY_FABIO':
            return f"🟢 BY FABIO: {data_fmt} ({segno}{var_pct:.1f}%)" if var_pct >= 0 else f"🔴 BY FABIO: {data_fmt} ({segno}{var_pct:.1f}%)"
        else:
            return f"🟢 SELL: {data_fmt} ({segno}{var_pct:.1f}%)" if var_pct <= 0 else f"🟠 SELL: {data_fmt} ({segno}{var_pct:.1f}%)"
    except:
        return "N/D"

# ==============================================================================
# SISTEMA REGISTRO VENDITE & FISCALITÀ
# ==============================================================================
ALIQUOTA_TASSE = 0.26
ANNI_COMPENSAZIONE = 4

def registra_vendita(ticker, qta_venduta, prezzo_medio, prezzo_vendita, data_vendita=None):
    try:
        if data_vendita is None:
            data_vendita = datetime.now().strftime("%Y-%m-%d")
        pnl_lordo = ((prezzo_vendita - prezzo_medio) * qta_venduta) - 1.0  # Comm. 1 EUR Trade Republic
        pnl_pct = ((prezzo_vendita / prezzo_medio) - 1) * 100 if prezzo_medio > 0 else 0
        minusvalenze = carica_json(MINUSVALENZE_FILE)
        tasse, minusvalenze_usate, tipo_operazione = 0.0, 0.0, ""
        if pnl_lordo > 0:
            tipo_operazione = "plusvalenza"
            residuo = pnl_lordo
            for mv in sorted(minusvalenze, key=lambda x: x.get('Scadenza', '9999-12-31')):
                if mv.get('Scadenza', '') >= data_vendita and mv.get('Importo', 0) > 0:
                    usa = min(mv['Importo'], residuo)
                    minusvalenze_usate += usa
                    residuo -= usa
                    mv['Importo'] -= usa
                    if residuo <= 0:
                        break
            tasse = residuo * ALIQUOTA_TASSE
            pnl_netto = pnl_lordo - tasse
        else:
            tipo_operazione = "minusvalenza"
            pnl_netto = pnl_lordo
            scadenza = (datetime.strptime(data_vendita, "%Y-%m-%d") + timedelta(days=365*ANNI_COMPENSAZIONE)).strftime("%Y-%m-%d")
            minusvalenze.append({'Data': data_vendita, 'Scadenza': scadenza, 'Importo': abs(pnl_lordo), 'Ticker': ticker.strip().upper()})
        minusvalenze = [m for m in minusvalenze if m.get('Importo', 0) > 0]
        salva_json(MINUSVALENZE_FILE, minusvalenze)
        registro = carica_json(REGISTRO_VENDITE_FILE)
        id_op = max([v.get('id', 0) for v in registro], default=0) + 1
        registro.append({'id': id_op, 'Data': data_vendita, 'Ticker': ticker.strip().upper(), 'Qta_Venduta': round(qta_venduta, 6), 'Prezzo_Medio': round(prezzo_medio, 4), 'Prezzo_Vendita': round(prezzo_vendita, 4), 'PnL_Lordo': round(pnl_lordo, 2), 'PnL_Pct': round(pnl_pct, 2), 'Minusvalenze_Usate': round(minusvalenze_usate, 2), 'Tasse': round(tasse, 2), 'PnL_Netto': round(pnl_netto, 2), 'Tipo': tipo_operazione})
        salva_json(REGISTRO_VENDITE_FILE, registro)
        return {'id': id_op, 'pnl_lordo': pnl_lordo, 'pnl_pct': pnl_pct, 'tasse': tasse, 'pnl_netto': pnl_netto, 'minusvalenze_usate': minusvalenze_usate, 'tipo': tipo_operazione}
    except Exception as e:
        print(f"Errore registrazione vendita: {e}")
        return None

def calcola_riepilogo_fiscale(anno=None):
    registro = carica_json(REGISTRO_VENDITE_FILE)
    if anno:
        registro = [v for v in registro if v.get('Data', '').startswith(str(anno))]
    gain_totale = sum(v.get('PnL_Lordo', 0) for v in registro if v.get('PnL_Lordo', 0) > 0)
    loss_totale = sum(v.get('PnL_Lordo', 0) for v in registro if v.get('PnL_Lordo', 0) < 0)
    tasse_totali = sum(v.get('Tasse', 0) for v in registro)
    netto_reale = gain_totale + loss_totale - tasse_totali
    minusvalenze = carica_json(MINUSVALENZE_FILE)
    oggi = datetime.now().strftime("%Y-%m-%d")
    pool_disponibile = sum(m.get('Importo', 0) for m in minusvalenze if m.get('Scadenza', '') >= oggi)
    return {'gain_totale': round(gain_totale, 2), 'loss_totale': round(loss_totale, 2), 'tasse_totali': round(tasse_totali, 2), 'netto_reale': round(netto_reale, 2), 'pool_minusvalenze': round(pool_disponibile, 2), 'num_operazioni': len(registro)}

def calcola_liquidita_totale():
    registro = carica_json(REGISTRO_VENDITE_FILE, default=[])
    reg_acq = carica_json(REGISTRO_ACQUISTI_FILE, default=[])
    chiave_u = PROFILO_ATTIVO.get("chiave", "fabio")

    # Per Fabio mantiene il calcolo storico esatto (rettifica Trade Republic + movimenti)
    if chiave_u == "fabio":
        liquidita_totale = CAPITALE_VERSATO_DEFAULT  # Rettifica allineamento saldo reale Trade Republic
        for v in registro:
            qta = v.get('Qta_Venduta', 0)
            prezzo_vendita = v.get('Prezzo_Vendita', 0)
            tasse = v.get('Tasse', 0)
            comm_tr = 1.0 if str(v.get('Data', ''))[:10] >= '2026-11-15' else 0.0
            incasso = (prezzo_vendita * qta) - tasse - comm_tr
            liquidita_totale += incasso
        for a in reg_acq:
            dt_a = str(a.get('Data', ''))[:10]
            if dt_a >= '2026-11-15':
                spesa = float(a.get('Totale_EUR') or a.get('Importo_Totale') or (float(a.get('Quantita', 0)) * float(a.get('Prezzo_EUR', 0))))
                liquidita_totale -= spesa
        return round(liquidita_totale, 2)

    # Per Lisi, Alessia e altri profili: usa il capitale versato del profilo (o da impostazioni_<utente>.json)
    imp_u = carica_json(IMPOSTAZIONI_FILE, default={})
    if isinstance(imp_u, dict) and imp_u.get("capitale_versato") is not None:
        base_versata = float(imp_u.get("capitale_versato") or 0.0)
    else:
        base_versata = CAPITALE_VERSATO_DEFAULT

    incassi_vendite = 0.0
    for v in registro:
        qta = v.get('Qta_Venduta', 0)
        prezzo_vendita = v.get('Prezzo_Vendita', 0)
        tasse = v.get('Tasse', 0)
        comm_tr = 1.0 if str(v.get('Data', ''))[:10] >= '2026-11-15' else 0.0
        incassi_vendite += (prezzo_vendita * qta) - tasse - comm_tr

    spese_reg_acq = 0.0
    ha_mov_acq = False
    for a in reg_acq:
        dt_a = str(a.get('Data', ''))[:10]
        if dt_a >= '2026-11-15':
            ha_mov_acq = True
            spese_reg_acq += float(a.get('Totale_EUR') or a.get('Importo_Totale') or (float(a.get('Quantita', 0)) * float(a.get('Prezzo_EUR', 0))))

    if ha_mov_acq:
        # Se esiste uno storico acquisti dedicato all'utente, usa eventuale liquidita_totale da impostazioni
        base_liq = float(imp_u.get("liquidita_totale")) if (isinstance(imp_u, dict) and imp_u.get("liquidita_totale") is not None) else base_versata
        return round(base_liq + incassi_vendite - spese_reg_acq, 2)

    # Senza registro acquisti locale (es. Streamlit Cloud / sincronizzazione Multi-Utente):
    # sottrae dal capitale versato il valore di carico delle posizioni attualmente in portafoglio
    port_u = st.session_state.get("portafoglio") or []
    cap_inv_u = sum(
        float(p.get("Valore_Carico") or (float(p.get("Quantita", 0) or 0) * float(p.get("Prezzo_Medio", 0) or 0)))
        for p in port_u
    )
    if base_versata == 0.0 and cap_inv_u == 0.0:
        return round(incassi_vendite, 2)
    return round(base_versata - cap_inv_u + incassi_vendite, 2)

def elimina_operazione_vendita(id_op):
    try:
        registro = carica_json(REGISTRO_VENDITE_FILE)
        registro = [v for v in registro if v.get('id') != id_op]
        salva_json(REGISTRO_VENDITE_FILE, registro)
        return True
    except:
        return False

def reset_registro_vendite():
    try:
        salva_json(REGISTRO_VENDITE_FILE, list())
        salva_json(MINUSVALENZE_FILE, list())
        return True
    except:
        return False
# ==============================================================================
# FUNZIONI DI RICOSTRUZIONE SEGNALI RETROATTIVI
# ==============================================================================
def prepara_dataframe_per_segnali(df, sma_short=50, sma_long=200):
    df = df.copy()
    df['SMA_Short'] = df['Close'].rolling(window=sma_short).mean()
    df['SMA_Long'] = df['Close'].rolling(window=sma_long).mean()
    df['Vol_Media_20'] = df['Volume'].rolling(window=20).mean()
    return df

def trova_segnali_by(df, sma_short=50, sma_long=200):
    by_signals = list()
    for i in range(sma_long, len(df)):
        try:
            prezzo = df['Close'].iloc[i]
            sma50 = df['SMA_Short'].iloc[i]
            vol = df['Volume'].iloc[i]
            vol_medio = df['Vol_Media_20'].iloc[i]
            open_price = df['Open'].iloc[i]
            distanza_sma50 = abs(prezzo - sma50) / sma50
            if distanza_sma50 <= 0.02 and vol > vol_medio and prezzo > open_price:
                by_signals.append({'Data': df.index[i].strftime("%Y-%m-%d"), 'Prezzo': round(prezzo, 2), 'Idx': i})
        except:
            continue
    return by_signals

def trova_segnali_sell(df, sma_short=50, sma_long=200):
    sell_signals = list()
    for i in range(sma_long, len(df)):
        try:
            prezzo = df['Close'].iloc[i]
            prezzo_prev = df['Close'].iloc[i-1]
            sma200 = df['SMA_Long'].iloc[i]
            sma200_prev = df['SMA_Long'].iloc[i-1]
            vol = df['Volume'].iloc[i]
            vol_medio = df['Vol_Media_20'].iloc[i]
            if prezzo < sma200 and prezzo_prev >= sma200_prev and vol > vol_medio:
                sell_signals.append({'Data': df.index[i].strftime("%Y-%m-%d"), 'Prezzo': round(prezzo, 2), 'Idx': i})
        except:
            continue
    return sell_signals

def ricostruisci_segnali_retroattivi(ticker, anni_indietro=1):
    try:
        ticker_obj = yf.Ticker(ticker)
        df = ticker_obj.history(period=f"{anni_indietro}y")
        if df.empty or len(df) < 250:
            return 0
        df = prepara_dataframe_per_segnali(df, sma_short=50, sma_long=200)
        by_signals = trova_segnali_by(df, sma_short=50, sma_long=200)
        sell_signals = trova_segnali_sell(df, sma_short=50, sma_long=200)
        segnali = carica_json(SEGNALI_STORICI_FILE)
        ticker_norm = ticker.strip().upper()
        segnali_aggiunti = 0
        for sig in by_signals:
            if not any(s.get('Ticker', '').strip().upper() == ticker_norm and s.get('Data') == sig['Data'] and s.get('Tipo') == 'BY' for s in segnali):
                segnali.append({'Ticker': ticker_norm, 'Tipo': 'BY', 'Data': sig['Data'], 'Prezzo': sig['Prezzo']})
                segnali_aggiunti += 1
        for sig in sell_signals:
            if not any(s.get('Ticker', '').strip().upper() == ticker_norm and s.get('Data') == sig['Data'] and s.get('Tipo') == 'SELL' for s in segnali):
                if not any(s.get('Ticker', '').strip().upper() == ticker_norm and s.get('Data') == sig['Data'] and s.get('Tipo') == 'BY' for s in segnali):
                    segnali.append({'Ticker': ticker_norm, 'Tipo': 'SELL', 'Data': sig['Data'], 'Prezzo': sig['Prezzo']})
                    segnali_aggiunti += 1
        if segnali_aggiunti > 0:
            salva_json(SEGNALI_STORICI_FILE, segnali)
        return segnali_aggiunti
    except Exception as e:
        print(f"Errore ricostruzione {ticker}: {e}")
        return 0

# ==============================================================================
# PORTAFOGLIO INIZIALE & SESSION STATE
# ==============================================================================
PORTAFOGLIO_INIZIALE = [
    {"Ticker": "TTWO", "Tipo": "Spot", "Quantita": 3.547945, "Prezzo_Medio": 187.55},
    {"Ticker": "SOFI", "Tipo": "PAC", "Quantita": 53.607426, "Prezzo_Medio": 14.31, "PAC_Settimanale": 15.0},
    {"Ticker": "VRT", "Tipo": "PAC", "Quantita": 0.335985, "Prezzo_Medio": 178.58, "PAC_Settimanale": 30.0},
    {"Ticker": "CRWD", "Tipo": "PAC", "Quantita": 0.092269, "Prezzo_Medio": 216.76, "PAC_Settimanale": 10.0},
] if USA_PORTAFOGLIO_INIZIALE else []
BIG_TECH_GROWTH_LIST = "GOOGL, AMZN, PLTR, META, MSFT, AAPL, TSLA, AVGO, CRM, ADBE, NOW, PANW, FTNT, CRDO, SMCI, ARMR, MRVL, QCOM, MU, INTU"

for key in ['df_fortezza', 'df_cavalli', 'df_monitor', 'df_palantir', 'scansione_completata', 'analisi_risultati', 'grafico_ticker', 'grafico_prezzo_medio', 'spy_data', 'dashboard_stats', 'portafoglio', 'last_update', 'pyramiding_alerts', 'take_profit_alerts', 'zona_interesse_alerts', 'semaforo_mercato', 'piano_ribilanciamento', 'risultato_simulazione', 'risultato_podc', 'piano_allocazione', 'breakout_tickers', 'liquidita_totale_alloc', 'pattern_alerts', 'pattern_singola_attivo']:
    if key not in st.session_state:
        st.session_state[key] = None if key not in ['pyramiding_alerts', 'take_profit_alerts', 'zona_interesse_alerts', 'breakout_tickers'] else list()

if st.session_state.portafoglio is None:
    _pf_caricato = carica_json(PORTAFOGLIO_FILE, default=None)
    if isinstance(_pf_caricato, list) and (len(_pf_caricato) > 0 or not USA_PORTAFOGLIO_INIZIALE):
        st.session_state.portafoglio = _pf_caricato
    else:
        st.session_state.portafoglio = list(PORTAFOGLIO_INIZIALE)
        _fp_pf_abs = os.path.join(os.path.dirname(os.path.abspath(__file__)), PORTAFOGLIO_FILE)
        if not os.path.exists(_fp_pf_abs):
            salva_json(PORTAFOGLIO_FILE, st.session_state.portafoglio)

# ==============================================================================
# FUNZIONI CORE
# ==============================================================================
def calcola_s_score(info, ticker=None):
    score = 50
    cr = info.get('currentRatio', 1.0) or 1.0
    if cr > 2.0: score += 15
    elif cr > 1.5: score += 10
    elif cr < 1.0: score -= 15
    de = info.get('debtToEquity', 50.0) or 50.0
    if de < 30: score += 15
    elif de < 50: score += 10
    elif de > 100: score -= 15
    pm = info.get('profitMargins', 0.0) or 0.0
    if pm > 0.15: score += 10
    elif pm > 0.05: score += 5
    rg = info.get('revenueGrowth', 0.0) or 0.0
    if rg > 0.10: score += 10
    elif rg > 0: score += 5
    return max(0, min(100, score))

def rileva_fase_weinstein(df):
    if len(df) < 200:
        return "Dati insufficienti"
    prezzo = df['Close'].iloc[-1]
    sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
    sma200_prev = df['Close'].rolling(window=200).mean().iloc[-20]
    sma50 = df['Close'].rolling(window=50).mean().iloc[-1]
    slope_sma200 = (sma200 - sma200_prev) / sma200_prev if sma200_prev > 0 else 0
    if prezzo < sma200 and slope_sma200 < -0.01:
        distanza_sma200 = abs(prezzo - sma200) / sma200
        if prezzo > sma50 and distanza_sma200 < 0.03:
            return "FASE 1 (Accumulazione/Basing)"
        return "FASE 4 (Declino Strutturale)"
    if prezzo < sma50 and prezzo > sma200 and slope_sma200 > 0.005:
        return "CORREZIONE in Trend (Pullback Fase 2)"
    if prezzo > sma200 * 1.2 and slope_sma200 > 0.02:
        return "FASE 3 (Distribuzione)"
    if prezzo > sma200 and slope_sma200 > 0.005:
        return "FASE 2 (Avanzamento)"
    return "FASE 1 (Accumulazione/Basing)"
def rileva_figura_z(df):
    if len(df) < 55:
        return False, "Dati insufficienti"
    sma50 = df['Close'].rolling(window=50).mean()
    for i in range(1, 6):
        idx_shakeout = -(i + 1)
        idx_close = -i
        if abs(idx_shakeout) >= len(df) or abs(idx_close) >= len(df):
            continue
        low_val = df['Low'].iloc[idx_shakeout]
        sma50_shake = sma50.iloc[idx_shakeout]
        close_val = df['Close'].iloc[idx_close]
        sma50_close = sma50.iloc[idx_close]
        if low_val < sma50_shake and close_val > sma50_close:
            return True, f"Figura Z confermata ({i} giorni fa)"
    return False, "Nessuna Figura Z"

def controlla_earnings(ticker_obj):
    try:
        earnings_dates = ticker_obj.earnings_dates
        if earnings_dates is None or earnings_dates.empty:
            return None, "⚪ N/D", False
        oggi = datetime.now()
        prossima_data = None
        for data in earnings_dates.index:
            data_naive = data.tz_localize(None) if hasattr(data, 'tz_localize') else data
            if data_naive > oggi:
                prossima_data = data_naive
                break
        if prossima_data is None:
            return None, "⚪ N/D", False
        giorni_mancanti = (prossima_data - oggi).days
        if giorni_mancanti <= 7:
            return giorni_mancanti, f"🔴 UTILI tra {giorni_mancanti}gg", True
        elif giorni_mancanti <= 14:
            return giorni_mancanti, f"🟡 Utili tra {giorni_mancanti}gg", False
        else:
            return giorni_mancanti, f"⚪ Utili tra {giorni_mancanti}gg", False
    except:
        return None, "⚪ N/D", False

def get_prezzi_corretti(ticker_obj, eurusd_rate):
    info = ticker_obj.info
    currency = info.get('currency', 'USD')
    history = ticker_obj.history(period='1d')
    if history.empty:
        return None, None, currency
    prezzo_raw = history['Close'].dropna().iloc[-1]
    if currency == 'USD':
        return round(prezzo_raw / eurusd_rate, 2), round(prezzo_raw, 2), currency
    else:
        return round(prezzo_raw, 2), round(prezzo_raw * eurusd_rate, 2), currency

def calcola_variazione_giornaliera(ticker_obj):
    try:
        hist = ticker_obj.history(period="2d")
        if len(hist) < 2:
            return None, None
        _c = hist['Close'].dropna()
        if len(_c) < 2: return None, None
        variazione_pct = ((_c.iloc[-1] - _c.iloc[-2]) / _c.iloc[-2]) * 100
        return round(variazione_pct, 2), round(hist['Close'].iloc[-1] - hist['Close'].iloc[-2], 2)
    except:
        return None, None

def rileva_gap_storico(df, soglia_minima_pct=3.0):
    try:
        if len(df) < 30:
            return None
        prezzo_attuale = df['Close'].dropna().iloc[-1]
        max_gap_sotto, max_gap_size = None, 0
        df_scan = df.copy()
        df_scan['Prev_Close'] = df_scan['Close'].shift(1)
        for idx in range(1, len(df_scan)):
            prev_close = df_scan.iloc[idx-1]['Close']
            open_price = df_scan.iloc[idx]['Open']
            if open_price < prev_close:
                gap_pct = ((prev_close - open_price) / prev_close) * 100
                if open_price < prezzo_attuale and gap_pct >= soglia_minima_pct:
                    post_gap_lows = df_scan.iloc[idx:]['Low']
                    if post_gap_lows.min() >= open_price * 0.95:
                        if gap_pct > max_gap_size:
                            max_gap_size = gap_pct
                            max_gap_sotto = open_price
        return round(max_gap_sotto, 2) if max_gap_sotto else None
    except:
        return None

def verifica_trigger_by_fortezza(df, sma_short, ticker_obj=None):
    if len(df) < sma_short + 5:
        return False, "Dati insufficienti", False
    prezzo = df['Close'].iloc[-1]
    sma50 = df['Close'].rolling(window=sma_short).mean().iloc[-1]
    vol_medio = df['Volume'].rolling(window=20).mean().iloc[-1]
    vol_oggi = df['Volume'].iloc[-1]
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi_oggi = float((100 - (100 / (1 + (gain/loss)))).iloc[-1]) if not (gain/loss).empty else 50
    fase = rileva_fase_weinstein(df)
    if "FASE 4" in fase:
        return False, f"❌ Bloccato: {fase}", False
    if rsi_oggi > 70:
        return False, f"❌ Bloccato: RSI ipercomprato ({rsi_oggi:.0f})", False
    distanza_sma50 = abs(prezzo - sma50) / sma50 * 100
    prezzo_vicino_sma50 = distanza_sma50 <= 3.0 or prezzo > sma50
    volume_ok = vol_oggi > vol_medio
    rsi_ok = rsi_oggi < 70
    candela_verde = df['Close'].iloc[-1] > df['Open'].iloc[-1]
    earnings_giorni, earnings_msg, earnings_bloccato = controlla_earnings(ticker_obj) if ticker_obj else (None, "N/D", False)
    if earnings_bloccato:
        return False, earnings_msg, True
    if rsi_oggi < 30 and fase in ["FASE 1 (Accumulazione/Basing)", "FASE 2 (Avanzamento)"] and vol_oggi > vol_medio * 1.5:
        return True, f"✅ Oversold bounce: RSI {rsi_oggi:.0f}, {fase}, Vol {vol_oggi/vol_medio:.2f}x", False
    if prezzo_vicino_sma50 and volume_ok and rsi_ok and candela_verde:
        return True, f"Pullback SMA50 completato (Vol: {vol_oggi/vol_medio:.2f}x, RSI: {rsi_oggi:.0f})", False
    else:
        motivi = list()
        if not prezzo_vicino_sma50:
            motivi.append(f"Prezzo fuori SMA50 ({distanza_sma50:.1f}%)")
        if not volume_ok:
            motivi.append(f"Volume bassi ({vol_oggi/vol_medio:.2f}x)")
        if not rsi_ok:
            motivi.append(f"RSI ipercomprato ({rsi_oggi:.0f})")
        if not candela_verde:
            motivi.append("Candela rossa")
        return False, "; ".join(motivi), False
PANIER_INSIDER_MID_LARGE = [
    "MTDR", "TTMI", "BSX", "SHAK", "DUOL", "GME", "AN", "FANG", "PR", "CHRD",
    "SM", "OVV", "APA", "DVN", "OXY", "SLB", "HAL", "BKR", "CTRA", "EQT",
    "AR", "RRC", "SWN", "CNX", "CRK", "DINO", "MPC", "VLO", "PSX", "TRGP",
    "OKE", "WMB", "KMI", "ET", "EPD", "MPLX", "ENB", "TRP", "PAA", "WES",
    "HIMS", "OSCR", "ALGN", "DXCM", "PODD", "ISRG", "EW", "ZBH", "SYK", "MDT",
    "BAX", "BDX", "HOLX", "RMD", "ICUI", "GMED", "NVST", "XRAY", "INSP", "SWAV",
    "CAVA", "WING", "CMG", "TXRH", "DRI", "EAT", "CAKE", "PLAY", "BROS", "CELH",
    "MNST", "ELF", "ULTA", "LULU", "ONON", "DECK", "CROX", "SKX", "BIRK", "GPS",
    "ANF", "AEO", "URBN", "FIVE", "OLLI", "DG", "DLTR", "TGT", "WMT", "COST"
]

def render_scheda_titolo_pro(r, eurusd_rate=1.12):
    tk = r['ticker']
    info_y = {}
    df_1y = None
    try:
        t_obj = yf.Ticker(tk)
        info_y = t_obj.info if isinstance(t_obj.info, dict) else {}
        df_1y = t_obj.history(period="1y", interval="1d").dropna(subset=['Close', 'Low', 'High'])
    except Exception:
        pass

    nome_az = info_y.get('longName') or info_y.get('shortName') or tk
    settore = info_y.get('sector', '')
    industria = info_y.get('industry', '')
    sub_sett = f"<div style='color:#9CA3AF;font-size:0.85rem;margin-top:-10px;margin-bottom:8px;'>{settore}{' • ' + industria if industria else ''}</div>" if settore else ""

    vpoc_val, whale_b = calcola_livello_balene(df_1y) if ('calcola_livello_balene' in globals() and df_1y is not None) else (None, "")
    _, stag_txt = calcola_stagionalita_10y(tk) if 'calcola_stagionalita_10y' in globals() else (None, "N/D")

    st.markdown(f"## {nome_az} ({tk}) {whale_b} — {r['segnale']}")
    if sub_sett:
        st.markdown(sub_sett, unsafe_allow_html=True)

    b_ins = get_badge_insider_attivo(tk, 60) if 'get_badge_insider_attivo' in globals() else ""
    if b_ins:
        st.info(f"**Segnale Insider Attivo:** {b_ins}")

    # Acquisti reali sul mercato aperto (Form 4 codice "P") letti direttamente dalla SEC EDGAR API
    if 'get_sec_insider_buys_90gg' in globals():
        try:
            _sec_scheda = get_sec_insider_buys_90gg(tk)
            if isinstance(_sec_scheda, dict) and _sec_scheda.get("buys", 0) > 0:
                _val_s = float(_sec_scheda.get("valore_usd", 0) or 0)
                _ult_s = _sec_scheda.get("ultimo_acquisto") or "N/D"
                st.success(
                    f"🕵️ **SEC Form 4 (90gg):** {_sec_scheda['buys']} acquisti reali sul mercato aperto "
                    f"({_sec_scheda['num_insider']} insider) | Totale stimato: **${_val_s:,.0f}** | Ultimo: **{_ult_s}**"
                )
                _det_sec = _sec_scheda.get("dettagli") or []
                if _det_sec:
                    with st.expander(f"📋 Dettaglio Acquisti Insider SEC Form 4 — {tk} ({len(_det_sec)} op.)", expanded=False):
                        st.dataframe(pd.DataFrame(_det_sec), use_container_width=True, hide_index=True)
            else:
                st.caption("🕵️ SEC Form 4 (90gg): nessun acquisto sul mercato aperto (codice P) rilevato.")
        except Exception:
            pass

    p_usd = float(r.get('prezzo_usd') or 0)
    p_eur = float(r.get('prezzo_eur') or 0)
    var_pct = float(r.get('var_oggi_pct') if r.get('var_oggi_pct') is not None else (r.get('var_pct') or 0))
    col_v = "#089981" if var_pct >= 0 else "#F23645"
    day_low = float(info_y.get('dayLow') or (df_1y['Low'].iloc[-1] if df_1y is not None and not df_1y.empty else p_usd))
    day_high = float(info_y.get('dayHigh') or (df_1y['High'].iloc[-1] if df_1y is not None and not df_1y.empty else p_usd))
    low_52 = float(info_y.get('fiftyTwoWeekLow') or (df_1y['Low'].min() if df_1y is not None and not df_1y.empty else 0))
    high_52 = float(info_y.get('fiftyTwoWeekHigh') or (df_1y['High'].max() if df_1y is not None and not df_1y.empty else 0))

    # Pre-Market / Post-Market da Yahoo
    ext_html = ""
    pre_p = info_y.get('preMarketPrice')
    post_p = info_y.get('postMarketPrice')
    if pre_p and p_usd > 0:
        pre_chg = ((float(pre_p) - p_usd) / p_usd) * 100
        c_ext = "#089981" if pre_chg >= 0 else "#F23645"
        ext_html = f" &nbsp;|&nbsp; <span style='font-size:0.9rem;color:#D1D4DC;'>🌅 Pre-Market: <b>${float(pre_p):.2f}</b> <span style='color:{c_ext};'>({pre_chg:+.2f}%)</span></span>"
    elif post_p and p_usd > 0:
        post_chg = ((float(post_p) - p_usd) / p_usd) * 100
        c_ext = "#089981" if post_chg >= 0 else "#F23645"
        ext_html = f" &nbsp;|&nbsp; <span style='font-size:0.9rem;color:#D1D4DC;'>🌙 After-Hours: <b>${float(post_p):.2f}</b> <span style='color:{c_ext};'>({post_chg:+.2f}%)</span></span>"

    st.markdown(
        f"<div style='background:#131722;border:1px solid #2A2E39;border-radius:8px;padding:10px 14px;margin-bottom:10px;'>"
        f"<span style='font-size:1.35rem;font-weight:700;color:#FFFFFF;'>${p_usd:.2f}</span> "
        f"<span style='font-size:1.05rem;color:#9CA3AF;'>(€ {p_eur:.2f})</span> &nbsp;|&nbsp; "
        f"<span style='font-size:1.05rem;font-weight:600;color:{col_v};'>Oggi: {var_pct:+.2f}%</span> &nbsp;|&nbsp; <span style='font-size:0.9rem;color:#D1D4DC;'>Day Range: <b>${day_low:.2f} - ${day_high:.2f}</b></span>"
        f"{ext_html} &nbsp;|&nbsp; "
        f"<span style='font-size:0.9rem;color:#D1D4DC;'>Range 52w: <b>${low_52:.2f} - ${high_52:.2f}</b></span>"
        f"</div>",
        unsafe_allow_html=True
    )

    _v50 = float(df_1y['Close'].rolling(50).mean().iloc[-1]) if (df_1y is not None and len(df_1y) >= 50) else 0.0
    _v200 = float(df_1y['Close'].rolling(200).mean().iloc[-1]) if (df_1y is not None and len(df_1y) >= 200) else 0.0

    vol_oggi = float(df_1y['Volume'].iloc[-1]) if (df_1y is not None and not df_1y.empty) else 0
    vol_med = float(df_1y['Volume'].rolling(20).mean().iloc[-1]) if (df_1y is not None and len(df_1y) >= 20) else 0
    vol_str = f"{vol_oggi/1e6:.2f}M / {vol_med/1e6:.2f}M" if vol_med > 0 else f"{r.get('vol_ratio', 0):.2f}x"

    c1, c2, c3, c4 = st.columns(4)
    _fw_raw = str(r.get("fase", "N/D")).upper()
    _fw_lbl = "🟢 FASE 2" if "2" in _fw_raw else ("🟠 FASE 1" if "1" in _fw_raw else ("🟠 FASE 3" if "3" in _fw_raw else ("🔴 FASE 4" if "4" in _fw_raw else _fw_raw)))
    _fw_desc = "Rialzo (Ideale)" if "2" in _fw_raw else ("Accumulo (Attesa Breakout)" if "1" in _fw_raw else ("Distribuzione (Tattico)" if "3" in _fw_raw else ("Ribasso (Evitare)" if "4" in _fw_raw else "")))
    _fw_col = "normal" if "2" in _fw_raw else ("inverse" if "4" in _fw_raw else "off")
    c1.metric("🏛️ Fase Weinstein", _fw_lbl, _fw_desc, delta_color=_fw_col)
    _sma50_lbl = f"${_v50:.2f}" if _v50 > 0 else "N/D (<50g)"
    _sma200_lbl = f"SMA200: ${_v200:.2f}" if _v200 > 0 else "SMA200: N/D (<200g)"
    c2.metric("📈 SMA 50 / SMA 200", _sma50_lbl, _sma200_lbl)
    _rsi_val_scheda = r.get('rsi')
    _rsi_lbl_scheda = f"RSI (14): {float(_rsi_val_scheda):.1f}" if (_rsi_val_scheda is not None and pd.notna(_rsi_val_scheda) and not (r.get('is_ipo_recente') and int(r.get('n_sedute') or 0) < 15)) else "RSI (14): N/D"
    c3.metric("🐋 VPOC Balene", f"${vpoc_val:.2f}" if vpoc_val else "N/D", _rsi_lbl_scheda)
    c4.metric("📊 Volumi (Oggi/Med)", vol_str, f"Figura Z: {'SÌ ✅' if r.get('figura_z') else 'No'}")

    mcap = float(info_y.get('marketCap') or 0)
    mcap_str = f"${mcap/1e9:.2f}B" if mcap >= 1e9 else (f"${mcap/1e6:.0f}M" if mcap > 0 else "N/D")
    pe_val = info_y.get('trailingPE') or info_y.get('forwardPE')
    beta_val = info_y.get('beta')
    sub_mcap = f"P/E: {float(pe_val):.2f}" if pe_val else "P/E: N/D"
    if beta_val:
        sub_mcap += f" | Beta: {float(beta_val):.2f}"

    tgt_1y = float(info_y.get('targetMeanPrice') or 0)
    upside_1y = ((tgt_1y - p_usd) / p_usd * 100) if (tgt_1y > 0 and p_usd > 0) else 0
    tgt_str = f"${tgt_1y:.2f} ({upside_1y:+.1f}%)" if tgt_1y > 0 else "N/D"

    f1, f2, f3, f4 = st.columns(4)
    f1.metric("⚡ S-Score Matrix", f"{r.get('s_score', 0)}/100")
    f2.metric("🏢 Market Cap", mcap_str, sub_mcap)
    f3.metric("🎯 Target Analisti 1y", tgt_str)
    f4.metric("📅 Stagionalità 60gg", stag_txt or "N/D", str(r.get('earnings_str', '')))

    if p_usd > 0:
        atr_val = float((df_1y['High'] - df_1y['Low']).tail(14).mean()) if (df_1y is not None and len(df_1y) >= 14) else (p_usd * 0.04)
        sl_usd = max(0.01, p_usd - (2.0 * atr_val))
        rischio_usd = max(0.01, p_usd - sl_usd)
        t1_usd = p_usd + (1.5 * rischio_usd)
        t2_usd = p_usd + (2.5 * rischio_usd)
        t3_usd = tgt_1y if tgt_1y > t2_usd else (p_usd + (3.5 * rischio_usd))
        rr_ratio = (t2_usd - p_usd) / rischio_usd
        sl_pct = ((sl_usd - p_usd) / p_usd) * 100
        t1_pct = ((t1_usd - p_usd) / p_usd) * 100
        t2_pct = ((t2_usd - p_usd) / p_usd) * 100
        t3_pct = ((t3_usd - p_usd) / p_usd) * 100

        st.markdown(
            f"<div style='background:linear-gradient(90deg, rgba(124,58,237,0.16) 0%, rgba(19,23,34,0.95) 100%);"
            f"border:1px solid rgba(124,58,237,0.5);border-radius:8px;padding:10px 14px;margin-top:8px;margin-bottom:8px;'>"
            f"<div style='font-size:0.82rem;font-weight:700;color:#C4B5FD;margin-bottom:4px;'>🎯 TARGET OPERATIVI & RAPPORTO RISCHIO/RENDIMENTO (ATR 14gg)</div>"
            f"<span style='color:#F23645;font-weight:600;'>🛑 Stop Loss: ${sl_usd:.2f} ({sl_pct:+.1f}%)</span> &nbsp;|&nbsp; "
            f"<span style='color:#089981;font-weight:600;'>T1: ${t1_usd:.2f} ({t1_pct:+.1f}%)</span> &nbsp;|&nbsp; "
            f"<span style='color:#089981;font-weight:600;'>T2: ${t2_usd:.2f} ({t2_pct:+.1f}%)</span> &nbsp;|&nbsp; "
            f"<span style='color:#38BDF8;font-weight:600;'>T3: ${t3_usd:.2f} ({t3_pct:+.1f}%)</span> &nbsp;|&nbsp; "
            f"<span style='color:#FBBF24;font-weight:700;'>⚖️ R/R: 1 : {rr_ratio:.1f}</span>"
            f"</div>",
            unsafe_allow_html=True
        )

def get_badge_insider_attivo(ticker, giorni_validita=60):
    try:
        prom = carica_json('insider_promossi.json') if 'carica_json' in globals() else {}
        if not isinstance(prom, dict):
            return ""
        tk_u = ticker.strip().upper()
        if tk_u not in prom:
            return ""
        info_p = prom[tk_u]
        if isinstance(info_p, dict):
            dt_str = info_p.get('data_acquisto') or info_p.get('data_promozione', '')
            det = info_p.get('dettagli', '')
        else:
            dt_str = str(info_p)
            det = ""
        dt_p = pd.to_datetime(dt_str, errors='coerce')
        if pd.isna(dt_p):
            return "🕵️ INSIDER"
        gg_passati = max(0, (pd.Timestamp.now() - dt_p).days)
        if gg_passati <= giorni_validita:
            rim = giorni_validita - gg_passati
            return f"🕵️ INSIDER ({gg_passati}gg fa, -{rim}gg){' | ' + det if det else ''}"
    except Exception:
        pass
    return ""

def get_giorni_insider_rimanenti(ticker, giorni_validita=60):
    try:
        prom = carica_json('insider_promossi.json') if 'carica_json' in globals() else {}
        if not isinstance(prom, dict):
            return "-"
        tk_u = ticker.strip().upper()
        if tk_u not in prom:
            return "-"
        info_p = prom[tk_u]
        dt_str = info_p.get('data_acquisto') or info_p.get('data_promozione', '') if isinstance(info_p, dict) else str(info_p)
        dt_p = pd.to_datetime(dt_str, errors='coerce')
        if pd.isna(dt_p):
            return "🕵️ 60gg"
        gg_passati = max(0, (pd.Timestamp.now() - dt_p).days)
        if gg_passati <= giorni_validita:
            return f"🕵️ {giorni_validita - gg_passati}gg"
    except Exception:
        pass
    return "-"

def uniforma_tabella_scanner(df_in):
    if df_in is None or not isinstance(df_in, pd.DataFrame) or df_in.empty or 'Ticker' not in df_in.columns:
        return df_in
    df_out = df_in.copy()
    if 'PEG' in df_out.columns or 'Rev Growth' in df_out.columns:
        df_out['Insider (60gg)'] = df_out['Ticker'].apply(lambda t: get_giorni_insider_rimanenti(str(t)) if 'get_giorni_insider_rimanenti' in globals() else '-')
        return df_out
    if 'Stato' not in df_out.columns:
        if 'Stato BY' in df_out.columns:
            df_out = df_out.rename(columns={'Stato BY': 'Stato'})
        elif 'Segnale' in df_out.columns:
            df_out = df_out.rename(columns={'Segnale': 'Stato'})
        else:
            df_out['Stato'] = '🟡 HOLD'
    if 'Motivo / Segnale' not in df_out.columns:
        for alt_m in ['Motivo BY', 'Motivo Hold', 'Motivo', 'Dettagli']:
            if alt_m in df_out.columns:
                df_out = df_out.rename(columns={alt_m: 'Motivo / Segnale'})
                break
    df_out['Insider (60gg)'] = df_out['Ticker'].apply(lambda t: get_giorni_insider_rimanenti(str(t)) if 'get_giorni_insider_rimanenti' in globals() else '-')
    col_std = ['Ticker', 'Prezzo EUR', 'S-Score', 'Fase', 'Stato', 'Motivo / Segnale', 'Earnings', 'Insider (60gg)']
    col_finali = [c for c in col_std if c in df_out.columns] + [c for c in df_out.columns if c not in col_std]
    return df_out[col_finali]

# Header conforme alle regole SEC EDGAR (richiesto User-Agent descrittivo + contatto)
SEC_EDGAR_HEADERS = {
    "User-Agent": "MatrixScannerPro/1.0 (contatto@matrixscanner.local)",
    "Accept-Encoding": "gzip, deflate",
}

@st.cache_data(ttl=3600, show_spinner=False)
def get_sec_ticker_cik_map():
    """Scarica e memorizza in cache la mappa ufficiale Ticker -> CIK (10 cifre) dalla SEC."""
    import requests
    mappa = {}
    try:
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=SEC_EDGAR_HEADERS,
            timeout=12,
        )
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict):
                for entry in data.values():
                    tk_sec = str(entry.get("ticker", "")).strip().upper()
                    cik_raw = entry.get("cik_str")
                    if tk_sec and cik_raw is not None:
                        cik_10 = str(cik_raw).strip().zfill(10)
                        mappa[tk_sec] = cik_10
                        if "-" in tk_sec:
                            mappa[tk_sec.replace("-", ".")] = cik_10
                        if "." in tk_sec:
                            mappa[tk_sec.replace(".", "-")] = cik_10
    except Exception:
        pass
    return mappa

@st.cache_data(ttl=1800, show_spinner=False)
def get_sec_insider_buys_90gg(ticker, max_docs=14):
    """
    Interroga direttamente la SEC EDGAR API (Form 4 XML) per rilevare gli acquisti reali
    sul mercato aperto (transactionCode == 'P') negli ultimi 90 giorni.
    """
    import time
    import requests
    import xml.etree.ElementTree as ET

    tk_up = str(ticker or "").strip().upper()
    vuoto = {
        "fonte": "SEC Form 4",
        "ticker": tk_up,
        "cik": "",
        "buys": 0,
        "num_insider": 0,
        "nomi_insider": [],
        "valore_usd": 0.0,
        "ultimo_acquisto": "",
        "dettagli": [],
        "form4_analizzati": 0,
    }
    if not tk_up:
        return vuoto

    try:
        cik_map = get_sec_ticker_cik_map()
        cik_10 = cik_map.get(tk_up) or cik_map.get(tk_up.replace(".", "-")) or cik_map.get(tk_up.replace("-", "."))
        if not cik_10:
            return vuoto
        cik_num = str(int(cik_10))

        # Scarica l'elenco depositi ufficiali SEC per il CIK
        sub_url = f"https://data.sec.gov/submissions/CIK{cik_10}.json"
        r_sub = requests.get(sub_url, headers=SEC_EDGAR_HEADERS, timeout=8)
        if r_sub.status_code != 200:
            return vuoto
        recent = (r_sub.json().get("filings") or {}).get("recent") or {}
        forms = recent.get("form") or []
        filing_dates = recent.get("filingDate") or []
        accessions = recent.get("accessionNumber") or []
        primary_docs = recent.get("primaryDocument") or []

        cutoff_dt = datetime.now() - timedelta(days=90)
        cutoff_str = cutoff_dt.strftime("%Y-%m-%d")
        cutoff_tx_str = (datetime.now() - timedelta(days=95)).strftime("%Y-%m-%d")

        # Filtra i Form 4 depositati negli ultimi 90 giorni (fino a max_docs documenti per velocità)
        candidati_f4 = []
        n_rec = min(len(forms), len(filing_dates), len(accessions), len(primary_docs))
        for i in range(n_rec):
            if str(forms[i]).strip().upper() == "4" and str(filing_dates[i]) >= cutoff_str:
                candidati_f4.append((str(filing_dates[i]), str(accessions[i]), str(primary_docs[i])))
                if len(candidati_f4) >= int(max_docs):
                    break

        if not candidati_f4:
            vuoto["cik"] = cik_10
            return vuoto

        buys_count = 0
        valore_tot = 0.0
        insider_names = set()
        ultimo_acq = ""
        dettagli = []
        analizzati = 0

        for idx_doc, (f_date, acc_num, prim_doc) in enumerate(candidati_f4):
            if idx_doc > 0:
                # Rispetta il rate limit ufficiale SEC (max 10 req/sec)
                time.sleep(0.11)
            acc_nodash = acc_num.replace("-", "").strip()
            # Rimuove l'eventuale prefisso XSLT (es. xslF345X06/form4.xml -> form4.xml) per scaricare l'XML grezzo
            raw_doc = prim_doc.split("/")[-1].strip()
            if not raw_doc or not raw_doc.lower().endswith(".xml"):
                continue
            xml_url = f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_nodash}/{raw_doc}"
            try:
                r_xml = requests.get(xml_url, headers=SEC_EDGAR_HEADERS, timeout=6)
                if r_xml.status_code != 200 or not r_xml.content:
                    continue
                root = ET.fromstring(r_xml.content)
                analizzati += 1
            except Exception:
                continue

            # Estrae nome e ruolo dell'insider dichiarante
            nome_ins = (root.findtext(".//reportingOwner/reportingOwnerId/rptOwnerName") or "Insider").strip()
            ruolo_txt = (root.findtext(".//reportingOwner/reportingOwnerRelationship/officerTitle") or "").strip()
            if not ruolo_txt:
                ruoli_flag = []
                if (root.findtext(".//reportingOwner/reportingOwnerRelationship/isOfficer") or "").strip().lower() in ("1", "true"):
                    ruoli_flag.append("Officer")
                if (root.findtext(".//reportingOwner/reportingOwnerRelationship/isDirector") or "").strip().lower() in ("1", "true"):
                    ruoli_flag.append("Director")
                if (root.findtext(".//reportingOwner/reportingOwnerRelationship/isTenPercentOwner") or "").strip().lower() in ("1", "true"):
                    ruoli_flag.append("10% Owner")
                ruolo_txt = " / ".join(ruoli_flag) if ruoli_flag else "Dirigente"

            # Analizza tutte le transazioni non-derivative cercando gli acquisti reali sul mercato aperto (code == 'P')
            for tx in root.findall(".//nonDerivativeTable/nonDerivativeTransaction"):
                tx_code = (tx.findtext(".//transactionCoding/transactionCode") or "").strip().upper()
                if tx_code != "P":
                    continue
                tx_date = (tx.findtext(".//transactionDate/value") or f_date).strip()[:10]
                if tx_date and tx_date < cutoff_tx_str:
                    continue
                try:
                    shares = float((tx.findtext(".//transactionAmounts/transactionShares/value") or "0").strip())
                except Exception:
                    shares = 0.0
                if shares <= 0:
                    continue
                try:
                    price_str = (tx.findtext(".//transactionAmounts/transactionPricePerShare/value") or "0").strip()
                    price = float(price_str) if price_str else 0.0
                except Exception:
                    price = 0.0
                imp_usd = shares * price if price > 0 else 0.0

                buys_count += 1
                valore_tot += imp_usd
                insider_names.add(nome_ins)
                if tx_date and (not ultimo_acq or tx_date > ultimo_acq):
                    ultimo_acq = tx_date
                dettagli.append({
                    "Data": tx_date or f_date,
                    "Insider": nome_ins[:32],
                    "Ruolo": ruolo_txt[:28],
                    "Azioni": f"{shares:,.0f}" if shares >= 10 else f"{shares:,.2f}",
                    "Prezzo $": f"${price:,.2f}" if price > 0 else "N/D",
                    "Importo $": f"${imp_usd:,.0f}" if imp_usd > 0 else "N/D",
                })

        dettagli.sort(key=lambda x: x.get("Data", ""), reverse=True)
        return {
            "fonte": "SEC Form 4",
            "ticker": tk_up,
            "cik": cik_10,
            "buys": buys_count,
            "num_insider": len(insider_names),
            "nomi_insider": sorted(list(insider_names)),
            "valore_usd": round(valore_tot, 2),
            "ultimo_acquisto": ultimo_acq,
            "dettagli": dettagli,
            "form4_analizzati": analizzati,
        }
    except Exception:
        return vuoto

def analizza_insider_e_minimi(ticker):
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period="1y", interval="1d")
        if df.empty:
            return None
        df = df.dropna(subset=['Close', 'Low', 'Volume']).copy()
        if len(df) < 60:
            return None
        prezzo = float(df['Close'].iloc[-1])
        low_52w = float(df['Low'].min())
        dist_min_pct = ((prezzo - low_52w) / low_52w) * 100 if low_52w > 0 else 0.0

        vol_oggi = float(df['Volume'].iloc[-1])
        vol_med = float(df['Volume'].rolling(20).mean().iloc[-1])
        vol_ratio = vol_oggi / vol_med if vol_med > 0 else 0

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi_s = (100 - (100 / (1 + (gain / loss.replace(0, np.nan))))).fillna(50)
        rsi_now = float(rsi_s.iloc[-1])
        div_rialzista = (float(df['Low'].tail(10).min()) <= float(df['Low'].tail(30).min()) * 1.02) and (float(rsi_s.tail(10).min()) > float(rsi_s.tail(30).min()) + 2)

        insider_buys = 0
        insider_val = 0.0
        insider_names = set()
        min_days_ago = 999
        last_buy_dt = None
        sec_dettagli = []
        fonte_insider = "SEC Form 4"

        # 1) Fonte ufficiale principale: SEC EDGAR Form 4 (transactionCode == 'P')
        try:
            sec_res = get_sec_insider_buys_90gg(ticker)
            if isinstance(sec_res, dict) and sec_res.get("buys", 0) > 0:
                insider_buys = int(sec_res.get("buys", 0))
                insider_val = float(sec_res.get("valore_usd", 0.0) or 0.0)
                insider_names = set(sec_res.get("nomi_insider") or [])
                sec_dettagli = sec_res.get("dettagli") or []
                fonte_insider = "SEC Form 4"
                _ult_sec = sec_res.get("ultimo_acquisto") or ""
                if _ult_sec:
                    dt_sec = pd.to_datetime(_ult_sec, errors='coerce')
                    if pd.notna(dt_sec):
                        last_buy_dt = dt_sec.tz_localize(None) if dt_sec.tzinfo is not None else dt_sec
                        min_days_ago = max(0, (pd.Timestamp.now() - last_buy_dt).days)
        except Exception:
            pass

        # 2) Fallback Yahoo Finance se la SEC non riporta acquisti (es. titoli esteri/ADR senza CIK)
        if insider_buys == 0:
            try:
                itx = tk.insider_transactions
                if itx is not None and not itx.empty:
                    cutoff = pd.Timestamp.now() - pd.Timedelta(days=95)
                    for _, row in itx.iterrows():
                        dt_val = pd.to_datetime(row.get('Start Date', row.name), errors='coerce')
                        if pd.notna(dt_val):
                            if dt_val.tzinfo is not None:
                                dt_val = dt_val.tz_localize(None)
                            if dt_val < cutoff:
                                continue
                        txt = str(row.get('Transaction', '') or row.get('Text', '')).lower()
                        shares = float(row.get('Shares', 0) or 0)
                        val = float(row.get('Value', 0) or 0)
                        if ('purchase' in txt or 'buy' in txt) and 'sale' not in txt and shares > 0:
                            insider_buys += 1
                            insider_val += val
                            nome_yf = str(row.get('Insider', 'Dirigente'))
                            insider_names.add(nome_yf)
                            fonte_insider = "Yahoo Finance"
                            if pd.notna(dt_val):
                                gg = max(0, (pd.Timestamp.now() - dt_val).days)
                                if gg < min_days_ago:
                                    min_days_ago = gg
                                    last_buy_dt = dt_val
                            sec_dettagli.append({
                                "Data": dt_val.strftime("%Y-%m-%d") if pd.notna(dt_val) else "N/D",
                                "Insider": nome_yf[:32],
                                "Ruolo": str(row.get('Position', 'Dirigente'))[:28],
                                "Azioni": f"{shares:,.0f}" if shares >= 10 else f"{shares:,.2f}",
                                "Prezzo $": "N/D",
                                "Importo $": f"${val:,.0f}" if val > 0 else "N/D",
                            })
            except Exception:
                pass

        info = tk.info if isinstance(tk.info, dict) else {}
        target_mean = float(info.get('targetMeanPrice') or 0)
        sconto_fv = ((target_mean - prezzo) / target_mean * 100) if target_mean > prezzo else 0.0
        s_score = calcola_s_score(info) if 'calcola_s_score' in globals() else 60

        score_opp = 0
        if len(insider_names) >= 3: score_opp += 35
        elif len(insider_names) == 2: score_opp += 25
        elif insider_buys >= 1: score_opp += 15
        if s_score >= 75: score_opp += 20
        elif s_score >= 60: score_opp += 10
        if 25 <= rsi_now <= 58: score_opp += 20
        elif rsi_now > 70: score_opp -= 35
        if div_rialzista: score_opp += 15
        if dist_min_pct <= 20: score_opp += 15
        if sconto_fv >= 15: score_opp += 15
        elif sconto_fv >= 5: score_opp += 8
        if min_days_ago <= 15: score_opp += 15
        elif min_days_ago <= 30: score_opp += 8

        ultimo_acq_str = (f"🔥 {min_days_ago}gg fa" if min_days_ago <= 15 else f"{min_days_ago}gg fa") if min_days_ago < 999 else "-"
        var_da_acq_str = "-"
        if last_buy_dt is not None:
            try:
                df_no_tz = df.copy()
                if df_no_tz.index.tz is not None:
                    df_no_tz.index = df_no_tz.index.tz_localize(None)
                df_sub_acq = df_no_tz[df_no_tz.index >= last_buy_dt]
                if not df_sub_acq.empty:
                    p_acq_ins = float(df_sub_acq['Close'].iloc[0])
                    if p_acq_ins > 0:
                        var_ins = ((prezzo - p_acq_ins) / p_acq_ins) * 100
                        var_da_acq_str = f"{var_ins:+.1f}%"
                        if -15.0 <= var_ins <= 3.0:
                            score_opp += 12
                        elif var_ins > 20.0:
                            score_opp -= 15
            except Exception:
                pass

        return {
            'Ticker': ticker,
            'Azienda': str(info.get('shortName', ticker))[:22],
            'Prezzo $': f"${prezzo:.2f}",
            'Insider (90gg)': f"{insider_buys} acq ({len(insider_names)} dir.)" if insider_buys > 0 else "0",
            'Fonte': fonte_insider,
            'Ultimo Acq.': ultimo_acq_str,
            'Dal Acq. Ins.': var_da_acq_str,
            'Valore Insider $': f"${insider_val:,.0f}",
            'Sconto FV %': f"{sconto_fv:.1f}%",
            'Dist. Min 52w %': f"+{dist_min_pct:.1f}%",
            'RSI': round(rsi_now, 1),
            'Divergenza': "SI" if div_rialzista else "No",
            'S-Score': s_score,
            'Score': score_opp,
            '_buys': insider_buys,
            '_var_ins': var_ins if 'var_ins' in locals() else 0.0,
            '_last_buy_str': last_buy_dt.strftime('%Y-%m-%d') if last_buy_dt is not None else '',
            '_sec_dettagli': sec_dettagli,
        }
    except Exception:
        return None

def calcola_stagionalita_10y(ticker):
    try:
        df10 = yf.Ticker(ticker).history(period="10y", interval="1mo")
        if df10.empty or len(df10) < 24:
            return None, None
        df10 = df10.copy()
        df10['Ret'] = df10['Close'].pct_change() * 100
        df10['Mese'] = df10.index.month
        mesi_nomi = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
        stats_mesi = []
        for m in range(1, 13):
            sub = df10[df10['Mese'] == m]['Ret'].dropna()
            if len(sub) > 0:
                med = float(sub.mean())
                win_rate = float((sub > 0).sum() / len(sub) * 100)
                stats_mesi.append({'Mese_Num': m, 'Mese': mesi_nomi[m-1], 'Rendimento_Medio': round(med, 2), 'Win_Rate': round(win_rate, 0), 'Anni': len(sub)})
        df_stag = pd.DataFrame(stats_mesi)
        m_curr = datetime.now().month
        m_next = 1 if m_curr == 12 else m_curr + 1
        r1 = df_stag[df_stag['Mese_Num'] == m_curr]['Rendimento_Medio'].values
        r2 = df_stag[df_stag['Mese_Num'] == m_next]['Rendimento_Medio'].values
        w1 = df_stag[df_stag['Mese_Num'] == m_curr]['Win_Rate'].values
        v1 = float(r1[0]) if len(r1) else 0.0
        v2 = float(r2[0]) if len(r2) else 0.0
        res_60g = round(v1 + v2, 2)
        wr_curr = int(w1[0]) if len(w1) else 0
        return df_stag, f"{res_60g:+.1f}% (WinRate mese: {wr_curr}%)"
    except Exception:
        return None, None

IGNITION_UNIVERSE = [
    "NVDA", "AMD", "PLTR", "SMCI", "AVGO", "META", "MSFT", "GOOGL", "AAPL", "TSLA",
    "CRWD", "PANW", "VRT", "SOFI", "RKLB", "IONQ", "ASTS", "NKE", "CRDO", "NU",
    "MCD", "DIS", "SBUX", "PEP", "INTC", "ANET", "MTDR", "TTMI", "BSX", "SHAK",
    "DUOL", "FANG", "OXY", "SLB", "HIMS", "DXCM", "PODD", "ISRG", "SYK", "MDT",
    "CAVA", "CMG", "TXRH", "DRI", "LULU", "ONON", "DECK", "CROX", "WMT", "COST",
    "COIN", "HOOD", "RBLX", "U", "DASH", "ABNB", "NET", "SNOW", "DDOG", "ZS",
    "OKTA", "MDB", "ESTC", "CELH", "MNST", "ELF", "ULTA", "GAP", "ANF", "AEO",
    "URBN", "FIVE", "OLLI", "DG", "DLTR", "TGT", "NBIS", "SOUN", "BBAI", "ZETA"
]

def verifica_ignition_start(df, ticker, s_score_precalc=None):
    if df is None or len(df) < 60:
        return False, ""
    prezzo = float(df['Close'].iloc[-1])
    prezzo_ieri = float(df['Close'].iloc[-2])
    open_oggi = float(df['Open'].iloc[-1])
    if prezzo <= open_oggi:
        return False, ""

    sma20_s = df['Close'].rolling(window=20).mean()
    std20_s = df['Close'].rolling(window=20).std()
    sma20 = float(sma20_s.iloc[-1])
    sma20_ieri = float(sma20_s.iloc[-2])
    bb_width = ((sma20_s + 2 * std20_s) - (sma20_s - 2 * std20_s)) / sma20_s.replace(0, np.nan)
    bw_now = float(bb_width.iloc[-1]) if pd.notna(bb_width.iloc[-1]) else 1.0
    bw_min60 = float(bb_width.tail(60).min()) if pd.notna(bb_width.tail(60).min()) else 1.0
    is_squeeze = bw_now <= bw_min60 * 1.35

    vol_oggi = float(df['Volume'].iloc[-1])
    vol_medio = float(df['Volume'].rolling(window=20).mean().iloc[-1])
    vol_ratio = vol_oggi / vol_medio if vol_medio > 0 else 0

    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rsi_s = (100 - (100 / (1 + (gain / loss.replace(0, np.nan))))).fillna(50)
    rsi_now = float(rsi_s.iloc[-1])
    rsi_prev = float(rsi_s.iloc[-4])

    vpoc, whale = calcola_livello_balene(df) if 'calcola_livello_balene' in globals() else (None, "")
    sopra_vpoc = (prezzo >= vpoc * 0.99) if vpoc else True
    riconquista_sma20 = (prezzo > sma20 and prezzo_ieri <= sma20_ieri * 1.01)

    if s_score_precalc is not None:
        s_score_ign = int(round(float(s_score_precalc)))
    else:
        info_ign = yf.Ticker(ticker).info if 'yf' in globals() else {}
        s_score_ign = calcola_s_score(info_ign) if 'calcola_s_score' in globals() and isinstance(info_ign, dict) else 65
    if s_score_ign < 60:
        return False, ""
    if (riconquista_sma20 or is_squeeze) and prezzo > sma20 and sopra_vpoc and vol_ratio >= 1.35 and (45 <= rsi_now <= 63) and (rsi_now > rsi_prev):
        tag_sq = "Squeeze + " if is_squeeze else ""
        _ins_ign = " | 🕵️ INSIDER" if ('get_giorni_insider_rimanenti' in globals() and get_giorni_insider_rimanenti(ticker) != "-") else ""
        return True, f"{tag_sq}Riconquista SMA20 | S-Score {s_score_ign} | Vol {vol_ratio:.1f}x | RSI {rsi_now:.0f} {whale}{_ins_ign}".strip()
    return False, ""

def verifica_by_fabio(df, sma_short, ticker_obj=None):
    if len(df) < sma_short + 5:
        return False, "Dati insufficienti"
    prezzo = df['Close'].iloc[-1]
    sma50 = df['Close'].rolling(window=sma_short).mean().iloc[-1]
    sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
    sma200_prev = df['Close'].rolling(window=200).mean().iloc[-20]
    vol_medio = df['Volume'].rolling(window=20).mean().iloc[-1]
    vol_oggi = df['Volume'].iloc[-1]
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi_oggi = float((100 - (100 / (1 + rs))).iloc[-1]) if not rs.empty else 50
    slope_sma200 = (sma200 - sma200_prev) / sma200_prev if sma200_prev > 0 else 0
    if ticker_obj:
        info = ticker_obj.info
        s_score = calcola_s_score(info)
    else:
        return False, "S-Score non disponibile"
    if s_score < 70:
        return False, f"S-Score {s_score} < 70 (non Fortezza)"
    if prezzo > sma50 and vol_oggi > vol_medio * 1.3 and 40 <= rsi_oggi <= 65:
        prezzo_ieri = df['Close'].iloc[-2]
        sma50_ieri = df['Close'].rolling(window=sma_short).mean().iloc[-2]
        if prezzo_ieri < sma50_ieri:
            return True, f"✅ BREAKOUT Fortezza: S-Score {s_score}, Vol {vol_oggi/vol_medio:.2f}x, RSI {rsi_oggi:.0f}"
    distanza_sma200 = (prezzo - sma200) / sma200 * 100
    if 0 <= distanza_sma200 <= 3.0 and slope_sma200 > 0 and 40 <= rsi_oggi <= 60:
        return True, f"✅ PULLBACK Fortezza: S-Score {s_score}, Distanza SMA200 {distanza_sma200:.1f}%, RSI {rsi_oggi:.0f}"
    return False, f"S-Score {s_score} OK ma condizioni geometriche non soddisfatte"

def trova_breakout_imminenti(portafoglio, eurusd_rate):
    breakout_tickers = list()
    for pos in portafoglio:
        ticker = pos['Ticker']
        try:
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period='1y')
            info = ticker_obj.info
            if df.empty or len(df) < 50:
                continue
            s_score = calcola_s_score(info)
            if s_score < 65:
                continue
            prezzo = df['Close'].iloc[-1]
            sma50 = df['Close'].rolling(window=50).mean().iloc[-1]
            distanza_sma50 = (sma50 - prezzo) / sma50 * 100
            if distanza_sma50 > 5.0 or prezzo > sma50:
                continue
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_oggi = float((100 - (100 / (1 + rs))).iloc[-1]) if not rs.empty else 50
            rsi_5gg_fa = float((100 - (100 / (1 + rs))).iloc[-6]) if len(rs) >= 6 else rsi_oggi
            if not (rsi_oggi > rsi_5gg_fa and 30 <= rsi_oggi <= 50):
                continue
            vol_medio = df['Volume'].rolling(window=20).mean().iloc[-1]
            vol_oggi = df['Volume'].iloc[-1]
            if vol_oggi <= vol_medio * 1.2:
                continue
            breakout_tickers.append({'ticker': ticker, 's_score': s_score, 'prezzo': round(prezzo / eurusd_rate if info.get('currency', 'USD') == 'USD' else prezzo, 2), 'sma50': round(sma50 / eurusd_rate if info.get('currency', 'USD') == 'USD' else sma50, 2), 'distanza_sma50': round(distanza_sma50, 1), 'rsi': round(rsi_oggi, 1), 'rsi_5gg_fa': round(rsi_5gg_fa, 1), 'volume_ratio': round(vol_oggi / vol_medio, 2)})
        except:
            continue
    return breakout_tickers

def render_barra_intervalli_yahoo(ticker_symbol, key_prefix, default_tf="3M"):
    tf_list = [("5D", "5d"), ("1M", "1mo"), ("3M", "3mo"), ("6M", "6mo"), ("YTD", "ytd"), ("1Y", "1y"), ("2Y", "2y")]
    state_key = f"tf_sel_{key_prefix}_{ticker_symbol}"
    if state_key not in st.session_state:
        st.session_state[state_key] = default_tf

    try:
        hist_2y = yf.Ticker(ticker_symbol).history(period="2y")['Close'].dropna()
    except Exception:
        hist_2y = pd.Series(dtype=float)

    cols_tf = st.columns(len(tf_list))
    oggi_ts = pd.Timestamp.now(tz=hist_2y.index.tz) if (not hist_2y.empty and hist_2y.index.tz is not None) else pd.Timestamp.now()

    for idx_t, (label_tf, _) in enumerate(tf_list):
        pct_str = ""
        if len(hist_2y) >= 2:
            last_p = float(hist_2y.iloc[-1])
            sub_s = hist_2y
            if label_tf == "5D":
                sub_s = hist_2y.tail(6)
            elif label_tf == "1M":
                sub_s = hist_2y[hist_2y.index >= (oggi_ts - pd.Timedelta(days=30))]
            elif label_tf == "3M":
                sub_s = hist_2y[hist_2y.index >= (oggi_ts - pd.Timedelta(days=90))]
            elif label_tf == "6M":
                sub_s = hist_2y[hist_2y.index >= (oggi_ts - pd.Timedelta(days=182))]
            elif label_tf == "YTD":
                sub_s = hist_2y[hist_2y.index.year == oggi_ts.year]
            elif label_tf == "1Y":
                sub_s = hist_2y[hist_2y.index >= (oggi_ts - pd.Timedelta(days=365))]
            first_p = float(next(iter(sub_s), 0.0))
            if len(sub_s) >= 2 and first_p > 0:
                pct_val = ((last_p / first_p) - 1) * 100
                pct_str = f"\n{pct_val:+.1f}%"

        is_active = (st.session_state[state_key] == label_tf)
        btn_label = f"{label_tf}{pct_str}"
        with cols_tf[idx_t]:
            if st.button(btn_label, key=f"btn_{key_prefix}_{ticker_symbol}_{label_tf}", type="primary" if is_active else "secondary", use_container_width=True):
                st.session_state[state_key] = label_tf
                st.rerun()

    return st.session_state[state_key]

def calcola_livello_balene(df):
    if df is None or len(df) < 30:
        return None, ""
    sub = df.tail(60).copy()
    prezzo_att = float(sub['Close'].iloc[-1])
    bins = np.linspace(float(sub['Low'].min()), float(sub['High'].max()), 25)
    if len(bins) < 2 or bins[-1] <= bins[0]:
        return None, ""
    sub['bin'] = pd.cut(sub['Close'], bins=bins, include_lowest=True)
    vol_by_bin = sub.groupby('bin', observed=False)['Volume'].sum()
    if vol_by_bin.empty:
        return None, ""
    vpoc = round(float(vol_by_bin.idxmax().mid), 2)
    sma50 = float(df['Close'].rolling(window=min(50, len(df))).mean().iloc[-1])
    sma200 = float(df['Close'].rolling(window=min(200, len(df))).mean().iloc[-1])
    if sma50 > sma200 and prezzo_att >= min(sma200, vpoc) * 0.98:
        badge = "🐋🐋"
    elif prezzo_att >= vpoc * 0.97:
        badge = "🐋"
    else:
        badge = ""
    return vpoc, badge

def applica_controlli_grafico(fig, chart_id):
    # Rimossi i pulsanti di zoom manuali sopra il grafico per lasciare spazio pulito su mobile:
    # navigazione fluida con pan a un dito, pinch-to-zoom e doppio tap per ripristinare la vista iniziale.
    if fig is not None:
        fig.update_layout(dragmode="pan")
        fig.update_yaxes(fixedrange=False, row=1, col=1)
    return fig

def genera_grafico_baleine(ticker, period, sma_short, sma_long, prezzo_medio_eur=None, timeframe='1d', interval='1d', eurusd_rate=1.12, height=860, pattern_info=None):
    df = yf.Ticker(ticker).history(period=period, interval=interval)
    if df.empty:
        return None
    df = df.dropna(subset=['Open', 'High', 'Low', 'Close']).copy()
    if len(df) < 2:
        return None

    # Eventuale ricampionamento settimanale o mensile se i dati di origine sono giornalieri
    if timeframe == '1wk' and interval == '1d':
        df = df.resample('W').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
    elif timeframe == '1mo' and interval == '1d':
        try:
            df = df.resample('ME').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        except Exception:
            df = df.resample('M').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
    if len(df) < 2:
        return None

    # Calcola le medie mobili reali solo quando lo storico ha abbastanza candele (evita linee fittizie sulle IPO recenti)
    has_sma20 = len(df) >= 20
    has_sma_short = len(df) >= sma_short
    has_sma_long = len(df) >= sma_long
    window_v = min(20, len(df))
    df['SMA_20'] = df['Close'].rolling(window=20).mean() if has_sma20 else np.nan
    std_20 = df['Close'].rolling(window=20).std() if has_sma20 else np.nan
    df['BB_Upper'] = df['SMA_20'] + (2 * std_20) if has_sma20 else np.nan
    df['BB_Lower'] = df['SMA_20'] - (2 * std_20) if has_sma20 else np.nan
    df['SMA_Short'] = df['Close'].rolling(window=sma_short).mean() if has_sma_short else np.nan
    df['SMA_Long'] = df['Close'].rolling(window=sma_long).mean() if has_sma_long else np.nan
    df['Vol_Media_20'] = df['Volume'].rolling(window=window_v).mean()

    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df['RSI'] = (100 - (100 / (1 + rs))).fillna(50)

    recent_df = df.tail(60)
    supporto = float(recent_df['Low'].min())
    resistenza = float(recent_df['High'].max())
    gap_level = rileva_gap_storico(df, soglia_minima_pct=3.0)

    prezzo_attuale = float(df['Close'].iloc[-1])
    prezzo_prec = float(df['Close'].iloc[-2]) if len(df) >= 2 else prezzo_attuale
    var_pct_oggi = ((prezzo_attuale - prezzo_prec) / prezzo_prec) * 100 if prezzo_prec > 0 else 0.0
    colore_titolo = "#10B981" if var_pct_oggi >= 0 else "#EF4444"

    # Polarità seduta stile StockCharts (Close vs Chiusura precedente) per candele Hollow e volumi coerenti
    prev_close = df['Close'].shift(1).fillna(df['Open'])
    is_up = df['Close'] >= prev_close

    vpoc_level, whale_badge = calcola_livello_balene(df)
    rsi_now = float(df['RSI'].iloc[-1]) if 'RSI' in df.columns and pd.notna(df['RSI'].iloc[-1]) else 50.0
    rsi_col = "#10B981" if rsi_now <= 30 else ("#EF4444" if rsi_now >= 70 else "#CE93D8")
    titolo_main = f"<b>{ticker}</b> {whale_badge}  ${prezzo_attuale:.2f}  <span style='color:{colore_titolo};'>({var_pct_oggi:+.2f}%)</span>  |  <span style='color:{rsi_col};'>RSI: {rsi_now:.1f}</span>  [{timeframe.upper()}]"
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.70, 0.15, 0.15], subplot_titles=("", "Volume", f"RSI (14): {rsi_now:.1f}"))

    # Intestazione compatta stile TradingView in alto a sinistra dentro il grafico (evita sovrapposizioni con la legenda)
    fig.add_annotation(
        text=titolo_main,
        xref="x domain",
        yref="y domain",
        x=0.005,
        y=0.99,
        xanchor="left",
        yanchor="top",
        showarrow=False,
        bgcolor="rgba(11, 14, 17, 0.72)",
        borderpad=3,
        font=dict(size=11, color="#D1D4DC"),
        row=1,
        col=1,
    )

    if has_sma20:
        fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='rgba(0, 188, 212, 0.35)', width=1, dash='dot'), name='BB Sup'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], fill='tonexty', fillcolor='rgba(0, 188, 212, 0.05)', line=dict(color='rgba(0, 188, 212, 0.35)', width=1, dash='dot'), name='BB Inf'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], line=dict(color='#00BCD4', width=1.3), name='SMA 20'), row=1, col=1)

    # Candele Hollow stile StockCharts: colore su Close vs Chiusura prec., riempimento (vuota/piena) su Close vs Open
    # Sedute positive (Close >= Chiusura prec.): Verde vuota se Close >= Open, Verde piena se Close < Open (es. Gap Up)
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df['Open'].where(is_up),
            high=df['High'].where(is_up),
            low=df['Low'].where(is_up),
            close=df['Close'].where(is_up),
            name='Prezzo',
            legendgroup='prezzo',
            showlegend=True,
            increasing_line_color="#10B981",
            increasing_fillcolor="#0B0E11",
            increasing_line_width=1.3,
            decreasing_line_color="#10B981",
            decreasing_fillcolor="#10B981",
            decreasing_line_width=1.1,
            whiskerwidth=0.4,
        ),
        row=1,
        col=1,
    )
    # Sedute negative (Close < Chiusura prec.): Rossa vuota se Close >= Open (es. Gap Down con rimbalzo), Rossa piena se Close < Open
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df['Open'].where(~is_up),
            high=df['High'].where(~is_up),
            low=df['Low'].where(~is_up),
            close=df['Close'].where(~is_up),
            name='Prezzo',
            legendgroup='prezzo',
            showlegend=False,
            increasing_line_color="#EF4444",
            increasing_fillcolor="#0B0E11",
            increasing_line_width=1.3,
            decreasing_line_color="#EF4444",
            decreasing_fillcolor="#EF4444",
            decreasing_line_width=1.1,
            whiskerwidth=0.4,
        ),
        row=1,
        col=1,
    )
    if has_sma_short:
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_Short'], line=dict(color='#F59E0B', width=1.5), name=f'SMA {sma_short}'), row=1, col=1)
    if has_sma_long:
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_Long'], line=dict(color='#2962FF', width=1.7), name=f'SMA {sma_long}'), row=1, col=1)

    if prezzo_medio_eur is not None:
        prezzo_medio_usd = prezzo_medio_eur * eurusd_rate
        fig.add_hline(y=prezzo_medio_usd, line_dash="dot", line_color="#10B981", line_width=1.8, annotation_text=f" PMC: ${prezzo_medio_usd:.2f} (€{prezzo_medio_eur:.2f}) ", annotation_position="top left", annotation_bgcolor="rgba(11, 14, 17, 0.85)", annotation_font=dict(color="#10B981", size=11), row=1, col=1)

    if vpoc_level:
        fig.add_hline(y=vpoc_level, line_dash="dashdot", line_color="#E040FB", line_width=1.4, annotation_text=f" 🐋 VPOC: ${vpoc_level:.2f} ", annotation_position="bottom right", annotation_bgcolor="rgba(11, 14, 17, 0.85)", annotation_font=dict(color="#E040FB", size=10), row=1, col=1)
    fig.add_hline(y=supporto, line_dash="dash", line_color="#10B981", line_width=1.2, annotation_text=f" Sup: {supporto:.2f} ", annotation_position="bottom left", annotation_bgcolor="rgba(11, 14, 17, 0.85)", annotation_font=dict(color="#10B981", size=10), row=1, col=1)
    fig.add_hline(y=resistenza, line_dash="dash", line_color="#EF4444", line_width=1.2, annotation_text=f" Res: {resistenza:.2f} ", annotation_position="top left", annotation_bgcolor="rgba(11, 14, 17, 0.85)", annotation_font=dict(color="#EF4444", size=10), row=1, col=1)
    if gap_level:
        fig.add_hline(y=gap_level, line_dash="dot", line_color="#F59E0B", line_width=1.5, annotation_text=f" Gap: {gap_level:.2f} ", annotation_position="top left", annotation_bgcolor="rgba(11, 14, 17, 0.85)", annotation_font=dict(color="#F59E0B", size=10), row=1, col=1)

    by_x, by_y, sell_x, sell_y = list(), list(), list(), list()
    if len(df) >= 60:
        for i in range(max(sma_short, 20), len(df)):
            sma_s_val, sma_l_val, sma_l_prev = df['SMA_Short'].iloc[i], df['SMA_Long'].iloc[i], df['SMA_Long'].iloc[i - 1]
            vol_val, vol_m_val = df['Volume'].iloc[i], df['Vol_Media_20'].iloc[i]
            if pd.notna(sma_s_val) and sma_s_val > 0 and pd.notna(vol_m_val):
                if abs(df['Close'].iloc[i] - sma_s_val) / sma_s_val <= 0.02 and vol_val > vol_m_val and df['Close'].iloc[i] > df['Open'].iloc[i]:
                    by_x.append(df.index[i]); by_y.append(df['Low'].iloc[i] * 0.985)
            if pd.notna(sma_l_val) and pd.notna(sma_l_prev) and pd.notna(vol_m_val):
                if df['Close'].iloc[i] < sma_l_val and df['Close'].iloc[i - 1] >= sma_l_prev and vol_val > vol_m_val:
                    sell_x.append(df.index[i]); sell_y.append(df['High'].iloc[i] * 1.015)

    if by_x:
        fig.add_trace(go.Scatter(x=by_x, y=by_y, mode='markers', marker=dict(symbol='triangle-up', size=13, color='#10B981', line=dict(width=1.2, color='#FFFFFF')), name=f'▲ BY ({len(by_x)})'), row=1, col=1)
    if sell_x:
        fig.add_trace(go.Scatter(x=sell_x, y=sell_y, mode='markers', marker=dict(symbol='triangle-down', size=13, color='#EF4444', line=dict(width=1.2, color='#FFFFFF')), name=f'▼ SELL ({len(sell_x)})'), row=1, col=1)

    vol_colors = ['rgba(16, 185, 129, 0.65)' if up else 'rgba(239, 68, 68, 0.65)' for up in is_up]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=vol_colors, name='Volume'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#9C27B0', width=1.5), name='RSI 14'), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#EF4444", line_width=1, row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#10B981", line_width=1, row=3, col=1)

    # Layout compatto stile TradingView ottimizzato anche per schermo mobile
    fig.update_layout(
        height=height,
        dragmode="pan",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        paper_bgcolor='#131722',
        plot_bgcolor='#0B0E11',
        font=dict(family='Inter, sans-serif', color='#D1D4DC', size=11),
        margin=dict(l=8, r=42, t=28, b=20),
        hovermode='x unified',
        legend=dict(font=dict(size=10), orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0, bgcolor='rgba(19, 23, 34, 0.75)'),
        modebar=dict(bgcolor='rgba(19, 23, 34, 0.92)', color='#D1D4DC', activecolor='#2962FF'),
    )

    # Applica la rimozione dei buchi dei weekend solo sul timeframe Daily (mai su Weekly/Monthly)
    is_weekly = (interval == '1wk' or timeframe == '1wk')
    is_monthly = (interval == '1mo' or timeframe == '1mo')
    is_daily = (interval == '1d' and not is_weekly and not is_monthly)
    if is_daily:
        fig.update_xaxes(gridcolor='#1E222D', zerolinecolor='#2A2E39', rangebreaks=[dict(bounds=["sat", "mon"])], fixedrange=False)
    else:
        fig.update_xaxes(gridcolor='#1E222D', zerolinecolor='#2A2E39', fixedrange=False)
    fig.update_yaxes(gridcolor='#1E222D', zerolinecolor='#2A2E39', side='right', fixedrange=False)

    # Finestra visibile iniziale intelligente per timeframe (mantenendo tutto lo storico scorribile)
    end_dt = df.index[-1]
    if is_monthly:
        sub_df = df.tail(48)
        left_pad = pd.Timedelta(days=15)
        right_pad = pd.Timedelta(days=45)
    elif is_weekly:
        sub_df = df.tail(52)
        left_pad = pd.Timedelta(days=4)
        right_pad = pd.Timedelta(days=14)
    elif timeframe == '1d':
        sub_df = df.tail(95)
        left_pad = pd.Timedelta(days=1)
        right_pad = pd.Timedelta(days=4)
    elif timeframe in ["5D", "1M", "3M", "6M", "YTD", "1Y", "1A", "2Y"]:
        if timeframe == "5D":
            sub_df = df.tail(6)
        elif timeframe == "2Y":
            sub_df = df
        elif timeframe == "YTD":
            start_ytd = pd.Timestamp(year=end_dt.year, month=1, day=1, tz=end_dt.tz)
            sub_df = df[df.index >= start_ytd]
        else:
            days_map = {"1M": 30, "3M": 90, "6M": 182, "1Y": 365, "1A": 365}
            sub_df = df[df.index >= (end_dt - pd.Timedelta(days=days_map.get(timeframe, 182)))]
        if len(sub_df) < 2:
            sub_df = df.tail(min(95, len(df)))
        left_pad = pd.Timedelta(days=1)
        right_pad = pd.Timedelta(days=4)
    else:
        # Intraday (15m / 1h): mostra le ultime 95 candele
        sub_df = df.tail(95)
        left_pad = pd.Timedelta(minutes=15)
        right_pad = pd.Timedelta(hours=2)

    if len(sub_df) >= 2:
        x_start = sub_df.index[0] - left_pad
        x_end = end_dt + right_pad

        # Calcolo range asse Y iniziale sul min/max visibile (+ livelli attivi pattern_engine) con margine 5%
        vis_low = float(sub_df['Low'].min())
        vis_high = float(sub_df['High'].max())
        _pat_for_range = pattern_info
        if _pat_for_range is None:
            _pat_for_range = (st.session_state.get("pattern_alerts") or {}).get("per_ticker", {}).get(str(ticker).upper())
        if isinstance(_pat_for_range, dict):
            for _k_lvl in ("trigger_y", "target_price", "stop_price"):
                _v_lvl = _pat_for_range.get(_k_lvl)
                if _v_lvl is not None:
                    try:
                        _fv = float(_v_lvl)
                        if _fv > 0:
                            vis_low = min(vis_low, _fv)
                            vis_high = max(vis_high, _fv)
                    except Exception:
                        pass

        span_y = max(vis_high - vis_low, vis_high * 0.02, 1e-6)
        y_min = max(0.0, vis_low - span_y * 0.05)
        y_max = vis_high + span_y * 0.05

        fig.update_xaxes(range=[x_start, x_end], row=1, col=1)
        fig.update_xaxes(range=[x_start, x_end], row=2, col=1)
        fig.update_xaxes(range=[x_start, x_end], row=3, col=1)
        fig.update_yaxes(range=[y_min, y_max], fixedrange=False, row=1, col=1)

    return fig

def valuta_stato_pac(info, df_storico):
    try:
        s_score = calcola_s_score(info)
        fase = rileva_fase_weinstein(df_storico)
        rev_growth = info.get('revenueGrowth', 0.0) or 0.0
        if "FASE 4" in fase or s_score < 50 or rev_growth < 0:
            return "🔴 PAC SOSPESO"
        return "🟢 PAC ATTIVO"
    except:
        return "⚪ N/D"

def aggiorna_quotazioni_portafoglio(portafoglio, eurusd_rate):
    risultati = list()
    for pos in portafoglio:
        ticker = pos['Ticker']
        try:
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info
            hist = ticker_obj.history(period="1y")
            if hist.empty:
                risultati.append({**pos, "Prezzo_Attuale_EUR": None, "Prezzo_Attuale_USD": None, "PnL_EUR": None, "PnL_%": None, "Trend": "N/D", "Earnings": "N/D", "Variazione_Pct": None, "Stato_PAC": "N/D", "Ultimo_Segnale": "N/D"})
                continue
            currency = info.get('currency', 'USD')
            prezzo_raw = hist['Close'].dropna().iloc[-1]
            prezzo_eur = prezzo_raw / eurusd_rate if currency == 'USD' else prezzo_raw
            prezzo_usd = prezzo_raw if currency == 'USD' else prezzo_raw * eurusd_rate
            var_pct, var_abs = calcola_variazione_giornaliera(ticker_obj)
            prezzo_medio = pos['Prezzo_Medio']
            quantita = pos['Quantita']
            valore_attuale = prezzo_eur * quantita
            valore_carico = prezzo_medio * quantita
            pnl_eur = valore_attuale - valore_carico
            pnl_pct = ((prezzo_eur / prezzo_medio) - 1) * 100 if prezzo_medio > 0 else 0
            trend = "🟢 Forte +" if pnl_pct > 5 else ("🟢 +" if pnl_pct > 0 else ("🟡 -" if pnl_pct > -5 else "🔴 Forte -"))
            earnings_giorni, earnings_msg, _ = controlla_earnings(ticker_obj)
            stato_pac = valuta_stato_pac(info, hist) if pos.get('Tipo') == 'PAC' else "N/A"
            ultimo_segnale_display = format_ultimo_segnale_display(ticker, prezzo_usd)
            risultati.append({**pos, "Prezzo_Attuale_EUR": round(prezzo_eur, 2), "Prezzo_Attuale_USD": round(prezzo_usd, 2), "Valore_Attuale": round(valore_attuale, 2), "PnL_EUR": round(pnl_eur, 2), "PnL_%": round(pnl_pct, 2), "Trend": trend, "Earnings": earnings_msg, "Variazione_Pct": var_pct, "Stato_PAC": stato_pac, "Ultimo_Segnale": ultimo_segnale_display})
        except Exception:
            risultati.append({**pos, "Prezzo_Attuale_EUR": None, "Prezzo_Attuale_USD": None, "PnL_EUR": None, "PnL_%": None, "Trend": "Errore", "Earnings": "N/D", "Variazione_Pct": None, "Stato_PAC": "Errore", "Ultimo_Segnale": "N/D"})
    salva_ultimo_agg_prezzi()
    return risultati

def calcola_target(ticker_obj, prezzo_medio, prezzo_attuale):
    try:
        hist = ticker_obj.history(period='1y')
        if hist.empty:
            return None
        rendimenti = hist['Close'].pct_change().dropna()
        volatilita = rendimenti.std() * math.sqrt(252) if len(rendimenti) > 0 else 0.15
        high_52w = hist['High'].max()
        picchi = list()
        window = 20
        for i in range(window, len(hist) - window):
            if hist['High'].iloc[i] == hist['High'].iloc[i-window:i+window+1].max():
                picchi.append(hist['High'].iloc[i])
        picchi = sorted(list(set(picchi)), reverse=True)
        resistenze_sopra = [p for p in picchi if p > prezzo_medio * 1.05]
        if len(resistenze_sopra) >= 3:
            t1, t2, t3 = resistenze_sopra[-1], resistenze_sopra[len(resistenze_sopra)//2], resistenze_sopra[0]
        elif len(resistenze_sopra) == 2:
            t1, t2, t3 = resistenze_sopra[-1], resistenze_sopra[0], high_52w
        elif len(resistenze_sopra) == 1:
            t1, t2, t3 = resistenze_sopra[0], high_52w, high_52w * 1.15
        else:
            t1 = prezzo_medio * (1 + volatilita * 1.5)
            t2 = prezzo_medio * (1 + volatilita * 3)
            t3 = prezzo_medio * (1 + volatilita * 5)
        t1 = max(t1, prezzo_medio * 1.08)
        t2 = max(t2, t1 * 1.15, prezzo_medio * 1.20)
        t3 = max(t3, t2 * 1.20, prezzo_medio * 1.35, high_52w)
        sl = min(hist['Low'].tail(20).min(), prezzo_medio * 0.92)
        def calc_progress(current, entry, target):
            try:
                if not current or not entry or not target:
                    return 0.0
                if target <= entry:
                    return 100.0
                progress = ((current - entry) / (target - entry)) * 100
                if math.isnan(progress) or math.isinf(progress):
                    return 0.0
                return max(0.0, min(100.0, round(progress, 1)))
            except:
                return 0.0
        prog1 = calc_progress(prezzo_attuale, prezzo_medio, t1)
        prog2 = calc_progress(prezzo_attuale, prezzo_medio, t2)
        prog3 = calc_progress(prezzo_attuale, prezzo_medio, t3)
        upside1 = round(((t1 / prezzo_attuale) - 1) * 100, 1) if prezzo_attuale and prezzo_attuale > 0 else 0
        upside2 = round(((t2 / prezzo_attuale) - 1) * 100, 1) if prezzo_attuale and prezzo_attuale > 0 else 0
        upside3 = round(((t3 / prezzo_attuale) - 1) * 100, 1) if prezzo_attuale and prezzo_attuale > 0 else 0
        sl_down = round(((sl / prezzo_attuale) - 1) * 100, 1) if prezzo_attuale and prezzo_attuale > 0 else 0
        return {'t1': round(t1, 2), 'prog1': prog1, 'upside1': upside1, 't2': round(t2, 2), 'prog2': prog2, 'upside2': upside2, 't3': round(t3, 2), 'prog3': prog3, 'upside3': upside3, 'sl': round(sl, 2), 'sl_down': sl_down}
    except:
        return None
# ==============================================================================
# PODC CON LOG COMPLETO
# ==============================================================================
def avvia_podc(portafoglio, eurusd_rate, catalizzatori_input, stato_mercato="N/D"):
    catalizzatori = dict()
    if catalizzatori_input:
        for item in catalizzatori_input.split(';'):
            item = item.strip()
            if ':' in item:
                ticker, resto = item.split(':', 1)
                catalizzatori[ticker.strip().upper()] = resto.strip()
    registro_vendite = carica_json(REGISTRO_VENDITE_FILE)
    oggi = datetime.now()
    ticker_venduti_recenti = set()
    for v in registro_vendite:
        try:
            data_str = v.get('Data', '')
            data_vendita = None
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    data_vendita = datetime.strptime(data_str, fmt)
                    break
                except:
                    continue
            if data_vendita is None:
                continue
            giorni_fa = (oggi - data_vendita).days
            if giorni_fa <= 5:
                ticker_venduti_recenti.add(v.get('Ticker', '').strip().upper())
        except Exception as e:
            print(f"Errore controllo 5 giorni: {e}")

    registra_proposta("PODC", "PODC_AVVIATO", "SISTEMA", f"PODC avviato. Titoli in portafoglio: {len(portafoglio)}. Stato mercato: {stato_mercato}", stato_mercato)

    gain_suggestions, loss_candidates, gain_analyzed, loss_rejected = list(), list(), list(), list()
    total_capital_freed = 0.0
    for pos in portafoglio:
        ticker = pos['Ticker']
        try:
            prezzo_attuale = pos.get('Prezzo_Attuale_EUR')
            if not prezzo_attuale:
                continue
            prezzo_medio = pos['Prezzo_Medio']
            qty = pos['Quantita']
            pnl_pct = ((prezzo_attuale / prezzo_medio) - 1) * 100
            ticker_obj = yf.Ticker(ticker)
            hist = ticker_obj.history(period='1y')
            info = ticker_obj.info
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = float((100 - (100 / (1 + rs))).iloc[-1]) if not rs.empty else 50
            s_score = calcola_s_score(info)
            fase = rileva_fase_weinstein(hist)
            targets = calcola_target(ticker_obj, prezzo_medio, prezzo_attuale)
            upside1 = targets['upside1'] if targets else 100
            has_catalyst = ticker in catalizzatori
            pos_data = {'ticker': ticker, 'prezzo_attuale': prezzo_attuale, 'prezzo_medio': prezzo_medio, 'qty': qty, 'pnl_pct': pnl_pct, 'rsi': rsi, 's_score': s_score, 'fase': fase, 'upside1': upside1, 'valore_totale': prezzo_attuale * qty, 'has_catalyst': has_catalyst}

            if pnl_pct >= 0:
                if ticker in ticker_venduti_recenti:
                    gain_analyzed.append({'ticker': ticker, 'pnl_pct': pnl_pct, 'reason': f"Gain +{pnl_pct:.1f}% - ✅ Vendita già registrata negli ultimi 5 giorni. Non riproporre."})
                    continue
                if pnl_pct >= 5.0 and (upside1 < 10.0 or rsi > 70):
                    capital_freed = pos_data['valore_totale'] * 0.5
                    total_capital_freed += capital_freed
                    gain_suggestions.append({**pos_data, 'capital_freed': capital_freed})
                    gain_analyzed.append({'ticker': ticker, 'pnl_pct': pnl_pct, 'reason': f"Gain +{pnl_pct:.1f}%, Upside {upside1:.1f}%, RSI {rsi:.1f} -> Consiglio: Vendi parzialmente (50%)"})
                else:
                    reason = f"Gain +{pnl_pct:.1f}% (sotto soglia minima del 5%)" if pnl_pct < 5.0 else f"Gain +{pnl_pct:.1f}%, Upside {upside1:.1f}%, RSI {rsi:.1f} -> Consiglio: Mantieni"
                    gain_analyzed.append({'ticker': ticker, 'pnl_pct': pnl_pct, 'reason': reason})
            if pnl_pct < 0:
                if has_catalyst:
                    loss_rejected.append({'ticker': ticker, 'pnl_pct': pnl_pct, 'reason': f"Catalizzatore imminente, posizione protetta"})
                elif pnl_pct < -5.0:
                    if fase == "FASE 4 (Declino Strutturale)" or s_score < 65:
                        loss_rejected.append({'ticker': ticker, 'pnl_pct': pnl_pct, 'reason': f"Fase 4 o S-Score < 65"})
                    elif s_score >= 70 and fase in ["FASE 1 (Accumulazione/Basing)", "FASE 2 (Avanzamento)", "CORREZIONE in Trend (Pullback Fase 2)"] and rsi < 40:
                        loss_candidates.append(pos_data)
                    else:
                        loss_rejected.append({'ticker': ticker, 'pnl_pct': pnl_pct, 'reason': f"Non soddisfa criteri Fortezza (RSI >= 40 o Fase non ottimale)"})
                else:
                    loss_rejected.append({'ticker': ticker, 'pnl_pct': pnl_pct, 'reason': f"Loss {pnl_pct:.1f}% (sotto soglia minima del 5%)"})
        except Exception as e:
            loss_rejected.append({'ticker': ticker, 'pnl_pct': 0, 'reason': f"Errore analisi: {str(e)}"})

    suggestions = list()
    for cand_a in gain_suggestions:
        for cand_b in loss_candidates:
            capital = cand_a['capital_freed']
            if capital < 50:
                continue
            new_qty = cand_b['qty'] + (capital / cand_b['prezzo_attuale'])
            new_avg = ((cand_b['qty'] * cand_b['prezzo_medio']) + capital) / new_qty
            new_pnl_pct = ((cand_b['prezzo_attuale'] / new_avg) - 1) * 100
            improvement = new_pnl_pct - cand_b['pnl_pct']
            if improvement >= 2.0 or (cand_b['pnl_pct'] < -10 and new_pnl_pct > -5):
                sug = {'sell_ticker': cand_a['ticker'], 'sell_pct': 50, 'capital_freed': capital, 'buy_ticker': cand_b['ticker'], 'old_avg': cand_b['prezzo_medio'], 'new_avg': new_avg, 'old_pnl': cand_b['pnl_pct'], 'new_pnl': new_pnl_pct}
                suggestions.append(sug)
                registra_proposta("PODC", "VENDITA_PARZIALE", sug['sell_ticker'], f"Vendi {sug['sell_pct']}% per mediare {sug['buy_ticker']}. Capitale liberato: €{sug['capital_freed']:.2f}", stato_mercato)
                registra_proposta("PODC", "ACQUISTO_MEDIA", sug['buy_ticker'], f"Nuovo medio: €{sug['new_avg']:.2f} (da €{sug['old_avg']:.2f}). PnL: {sug['old_pnl']:.1f}% → {sug['new_pnl']:.1f}%", stato_mercato)

    if not suggestions:
        registra_proposta("PODC", "NESSUNA_PROPOSTA", "SISTEMA", f"Nessuna proposta valida. Gain analizzati: {len(gain_analyzed)}, Loss candidati: {len(loss_candidates)}", stato_mercato)
    else:
        registra_proposta("PODC", "PROPOSTE_GENERATE", "SISTEMA", f"Generate {len(suggestions)} proposte. Capitale liberato: €{total_capital_freed:.2f}", stato_mercato)

    return {'suggestions': suggestions, 'gain_analyzed': gain_analyzed, 'loss_rejected': loss_rejected, 'loss_candidates': loss_candidates, 'total_capital_freed': total_capital_freed}

# ==============================================================================
# INTERFACCIA PRINCIPALE - TOP BAR TERMINALE
# ==============================================================================
semaforo_header = calcola_semaforo_mercato()
if semaforo_header['stato'] == 'verde':
    sem_color, sem_icon, sem_msg = "#089981", "🟢", "MERCATO RIALZISTA"
elif semaforo_header['stato'] == 'rosso':
    sem_color, sem_icon, sem_msg = "#F23645", "🔴", "MERCATO RIBASSISTA"
else:
    sem_color, sem_icon, sem_msg = "#F59E0B", "🟡", "MERCATO LATERALE"

if semaforo_header['spy_prezzo'] is None or semaforo_header['vix'] is None:
    sem_display = "🟡 DATI MERCATO N/D"
else:
    sem_display = f"{sem_icon} {sem_msg}  |  SPY: ${semaforo_header['spy_prezzo']}  |  VIX: {semaforo_header['vix']}"

_agg_prezzi_display = leggi_ultimo_agg_prezzi()
st.markdown(f'''
<div class="header-box" style="padding: 0.65rem 1.2rem; margin-bottom: 0.75rem;">
    <div style="display:flex; align-items:center; gap:10px;">
        <span style="font-size:1.3rem; font-weight:800; color:#FFFFFF; letter-spacing:-0.02em;">MATRIX DVMS</span>
        <span style="background-color:#1E222D; color:#94A3B8; border:1px solid #2A2E39; padding:2px 7px; border-radius:4px; font-size:0.75rem; font-weight:700;">V6.1.3 PRO</span><span style="margin-left:14px; color:#e2e8f0; font-size:0.95rem; font-weight:600;">{SALUTO_UTENTE_CORRENTE}</span><span style="margin-left:14px; color:#94a3b8; font-size:0.78rem; background:rgba(15,23,42,0.65); padding:3px 9px; border-radius:6px; border:1px solid rgba(148,163,184,0.2);">🕒 Agg. Prezzi: {_agg_prezzi_display}</span>
    </div>
    <div style="background-color:#0B0E11; border:1px solid #2A2E39; padding:6px 14px; border-radius:6px; font-family:'JetBrains Mono', monospace; font-size:0.85rem; font-weight:700; color: {sem_color};">
        {sem_display}
    </div>
</div>
''', unsafe_allow_html=True)
if 'regia_tracker' in globals() and hasattr(regia_tracker, 'render_barra_indici_usa'):
    regia_tracker.render_barra_indici_usa()

_fp_impostazioni = _get_impostazioni_path()
_imp_caricate = carica_json(IMPOSTAZIONI_FILE, default={})
if isinstance(_imp_caricate, dict) and _imp_caricate:
    impostazioni = _imp_caricate
else:
    impostazioni = {"lista_ticker_default": "ADBE, RKLB, SOUN, IONQ, ASTS, PLTR, ZETA, NKE, AMD, CRWD, NU, NVDA, TSLA, MCD, DIS, SBUX, PEP, INTC, SOFI, NBIS, VRT, ANET", "catalizzatori": "", "esclusioni": ""}

avvia_scansione_btn = st.sidebar.button("🚀 AVVIA SCANSIONE", type="primary", use_container_width=True, key="btn_avvia_scansione_top")
st.sidebar.markdown("---")
st.sidebar.markdown("**💼 Selezione Rapida Portafoglio**")
_sb_list = list(dict.fromkeys([p['Ticker'] for p in (st.session_state.portafoglio or list()) if p.get('Ticker')])) or ["Portafoglio vuoto"]
if "sb_quick_ticker" not in st.session_state or st.session_state["sb_quick_ticker"] not in _sb_list:
    st.session_state["sb_quick_ticker"] = next(iter(_sb_list))
if "sb_ticker_radio" not in st.session_state or st.session_state["sb_ticker_radio"] not in _sb_list:
    st.session_state["sb_ticker_radio"] = st.session_state["sb_quick_ticker"]

def _on_sb_ticker_change():
    val = st.session_state.get("sb_ticker_radio")
    if val and val != "Portafoglio vuoto":
        st.session_state["sb_quick_ticker"] = val
        st.session_state["port_selected_chart"] = val
        st.session_state["sel_chart_port_side"] = val
        st.session_state["txt_analisi_singola_tk"] = val

_sb_sel = st.sidebar.radio("Selezione Rapida", _sb_list, label_visibility="collapsed", key="sb_ticker_radio", on_change=_on_sb_ticker_change)
st.sidebar.markdown("---")
st.sidebar.subheader("📌 Titoli da Acquistare (Priorità)")
titoli_priorita_input = st.sidebar.text_input("In ordine di priorità (es. PLTR, RKLB):", value="", key="titoli_priorita_input")
st.sidebar.subheader("💵 Liquidità Aggiuntiva")
liq_aggiuntiva_sim = st.sidebar.number_input("Disponibilità extra (€):", min_value=0.0, value=0.0, step=50.0, key="liq_aggiuntiva_sim")
st.sidebar.subheader("📅 Catalizzatori Eventi")
catalizzatori_input = st.sidebar.text_area("Formato: TICKER: Desc - GG/MM/AA", value=impostazioni.get("catalizzatori", ""), height=75)
st.sidebar.subheader("🚫 Esclusioni Ribilanciamento")
esclusioni_input = st.sidebar.text_area("Titoli da escludere (virgola):", value=impostazioni.get("esclusioni", ""), height=65)

with st.sidebar.expander("⚙️ Impostazioni Avanzate & Watchlist", expanded=False):
    # Applica eventuale aggiornamento Watchlist arrivato dalla stellina in regia_tracker prima di creare il widget
    if "_pending_tickers_input" in st.session_state:
        st.session_state["tickers_input"] = st.session_state.pop("_pending_tickers_input")
    if "tickers_input" not in st.session_state:
        st.session_state["tickers_input"] = impostazioni.get("lista_ticker_default", "")
    tickers_input = st.text_area("Watchlist Scanner (virgola):", height=95, key="tickers_input")
    period = st.selectbox("Periodo:", ["3mo", "6mo", "1y", "2y"], index=2)
    sma_short = st.slider("SMA Breve:", 10, 100, 50)
    sma_long = st.slider("SMA Lunga:", 50, 200, 200)
    eurusd_rate = st.number_input("EUR/USD:", min_value=0.8, max_value=1.5, value=get_live_eurusd(), step=0.001, format="%.4f")
    ignore_fase_4 = st.checkbox("Blocca Fase 4", True)
    if st.button("🔍 Verifica Segnali Storici", key="btn_dbg_storici"):
        segnali = carica_json(SEGNALI_STORICI_FILE)
        st.info(f"Totale segnali: {len(segnali)}")
    if st.button("🔄 Ricostruisci Segnali (1 anno)", key="btn_dbg_ricostr"):
        tks_ric = list(set([t.strip().upper() for t in tickers_input.split(",") if t.strip()] + [t.strip().upper() for t in BIG_TECH_GROWTH_LIST.split(",")]))
        pb = st.progress(0)
        tot = sum(ricostruisci_segnali_retroattivi(tk, 1) for i, tk in enumerate(tks_ric) if not pb.progress((i + 1) / len(tks_ric)))
        pb.empty()
        st.success(f"✅ Aggiunti {tot} segnali storici.")
        st.rerun()

# Box Account nella sidebar: utente connesso, cambio password e tasto Esci
render_box_account_sidebar()

tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
if avvia_scansione_btn:
    impostazioni["lista_ticker_default"] = tickers_input
    impostazioni["catalizzatori"] = catalizzatori_input
    impostazioni["esclusioni"] = esclusioni_input
    with open(_fp_impostazioni, 'w', encoding='utf-8') as f:
        json.dump(impostazioni, f, indent=4, ensure_ascii=False)
        try:
            _sync_github_file(IMPOSTAZIONI_FILE, json.dumps(impostazioni, indent=4, ensure_ascii=False), mode='push')
        except Exception:
            pass
    progress_bar = st.progress(0)
    if st.session_state.spy_data is None:
        try:
            st.session_state.spy_data = yf.Ticker("SPY").history(period=period)
        except:
            st.session_state.spy_data = None
    stats = {'by_count': 0, 'hold_count': 0, 'sell_count': 0, 'by_tickers': list(), 'hold_tickers': list(), 'sell_tickers': list(), 'earnings_warnings': list(), 'error_tickers': list(), 'by_fabio_tickers': list(), 'smci_tickers': list(), 'ignition_oggi': list(), 'metriche_scan': dict()}
    pyramiding_alerts, take_profit_alerts, zona_interesse_alerts, extended_hours_alerts = list(), list(), list(), list()
    lista_fortezza, lista_cavalli, lista_monitor, lista_palantir = list(), list(), list(), list()
    # Inizializza il contenitore degli alert del motore figure grafiche secondo il regime SPY
    _spy_regime_scan = (semaforo_header.get('stato') if isinstance(semaforo_header, dict) else 'verde') or 'verde'
    pattern_alerts_scan = pattern_engine.crea_contenitore_pattern_alerts(spy_regime=_spy_regime_scan)
    sorvegliati_candidati_scan = list()
    cluster_insider_bacheca_scan = list()
    scan_price_map_bacheca = dict()
    watchlist_only_set = {str(t).strip().upper() for t in tickers if str(t).strip()}
    portafoglio_attuale = st.session_state.portafoglio or carica_json(PORTAFOGLIO_FILE) or PORTAFOGLIO_INIZIALE
    ticker_in_portafoglio = {p['Ticker']: p for p in portafoglio_attuale}
    tickers = list(set(tickers + list(ticker_in_portafoglio.keys())))
    tickers.sort()
    st.info(f"🔄 Scansione avviata per {len(tickers)} titoli.")
    for i, ticker in enumerate(tickers):
        progress_bar.progress((i + 1) / len(tickers))
        try:
            ticker_obj = yf.Ticker(ticker)
            periodo_analisi = '1y' if period in ['3mo', '6mo'] else period
            df = ticker_obj.history(period=periodo_analisi)
            info = ticker_obj.info
            if df.empty or len(df) < max(sma_long, 50):
                continue
            prezzo_eur, prezzo_usd, currency = get_prezzi_corretti(ticker_obj, eurusd_rate)
            if prezzo_eur is None:
                continue
            df['SMA_Short'] = df['Close'].rolling(window=sma_short).mean()
            df['SMA_Long'] = df['Close'].rolling(window=sma_long).mean()
            df['Vol_Media_20'] = df['Volume'].rolling(window=20).mean()
            vol_ratio = df.iloc[-1]['Volume'] / df.iloc[-1]['Vol_Media_20'] if df.iloc[-1]['Vol_Media_20'] > 0 else 0
            s_score = calcola_s_score(info)
            fase = rileva_fase_weinstein(df)
            figura_z, _ = rileva_figura_z(df)
            trigger_by, motivo_by, earnings_bloccato = verifica_trigger_by_fortezza(df, sma_short, ticker_obj)
            earnings_giorni, earnings_msg, earnings_bloccato2 = controlla_earnings(ticker_obj)
            if earnings_bloccato2:
                stats['earnings_warnings'].append(f"{ticker} ({earnings_msg})")
            trigger_by_fabio, motivo_by_fabio = verifica_by_fabio(df, sma_short, ticker_obj)
            if trigger_by_fabio:
                stats.setdefault('by_fabio_tickers', list()).append(ticker)
                registra_proposta("SCANSIONE", "BY_FABIO", ticker, f"Segnale BY FABIO rilevato - {motivo_by_fabio}", stato="N/D")
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_oggi = float((100 - (100 / (1 + (gain/loss)))).iloc[-1]) if not (gain/loss).empty else 50
            revenue_growth = info.get('revenueGrowth', 0.0) or 0.0
            peg_ratio = info.get('pegRatio', 0.0) or 0.0
            sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
            sma50 = df['Close'].rolling(window=50).mean().iloc[-1]
            prezzo_attuale = df['Close'].dropna().iloc[-1]
            distanza_sma200_pct = abs(prezzo_attuale - sma200) / sma200 * 100 if sma200 > 0 else 999
            if s_score >= 75 and "FASE 1" in fase and prezzo_attuale < sma50 and 35 <= rsi_oggi <= 50:
                stats.setdefault('smci_tickers', list()).append(ticker)
                registra_proposta("SCANSIONE", "TIPOLOGIA_SMCI", ticker, f"Pattern SMCI: S-Score {s_score}, FASE 1, RSI {rsi_oggi:.0f}", stato="N/D")
            is_palantir = (s_score >= 75 and revenue_growth >= 0.20 and (peg_ratio > 0 and peg_ratio < 1.5) and rsi_oggi < 45 and distanza_sma200_pct <= 5.0)
            if is_palantir:
                lista_palantir.append({'Ticker': ticker, 'Prezzo EUR': prezzo_eur, 'S-Score': s_score, 'RSI': round(rsi_oggi, 1), 'PEG': round(peg_ratio, 2) if peg_ratio > 0 else 'N/D', 'Rev Growth': f"{revenue_growth*100:.1f}%", 'Distanza SMA200': f"{distanza_sma200_pct:.1f}%"})
            pm_var = info.get('preMarketChangePercent') or 0
            am_var = info.get('postMarketChangePercent') or 0
            variazione_extra = am_var if am_var != 0 else pm_var
            if abs(variazione_extra) >= 5.0:
                tipo_sessione = "After-Hours" if am_var != 0 else "Pre-Market"
                colore = "🟢" if variazione_extra > 0 else "🔴"
                extended_hours_alerts.append({'ticker': ticker, 'variazione': round(variazione_extra, 2), 'sessione': tipo_sessione, 'colore': colore, 'prezzo_eur': prezzo_eur})
            if ticker in ticker_in_portafoglio:
                if rsi_oggi >= 75:
                    pos = ticker_in_portafoglio[ticker]
                    gain_pct = ((prezzo_eur / pos['Prezzo_Medio']) - 1) * 100 if pos['Prezzo_Medio'] > 0 else 0
                    take_profit_alerts.append({'ticker': ticker, 'rsi': round(rsi_oggi, 1), 'prezzo_attuale_eur': prezzo_eur, 'gain_pct': round(gain_pct, 1), 'tipo': pos.get('Tipo', 'Spot')})
                    registra_proposta("SCANSIONE", "TAKE_PROFIT", ticker, f"RSI {rsi_oggi:.0f}, Gain +{gain_pct:.1f}%", stato="N/D")
            if ticker in ticker_in_portafoglio or s_score >= 60:
                if s_score >= 60 and distanza_sma200_pct <= 5.0:
                    zona_interesse_alerts.append({'ticker': ticker, 'prezzo_attuale_eur': prezzo_eur, 'sma200_eur': round(sma200 / eurusd_rate if currency == 'USD' else sma200, 2), 'distanza_pct': round(distanza_sma200_pct, 1), 's_score': s_score})
                    registra_proposta("SCANSIONE", "ZONA_INTERESSE", ticker, f"S-Score {s_score}, Distanza SMA200 {distanza_sma200_pct:.1f}%", stato="N/D")
            # Salva le metriche tecniche fresche del titolo per Regia Acquisti e Simulatore
            stats['metriche_scan'][ticker] = {
                'Fase': fase,
                'S_Score': s_score,
                'RSI': round(rsi_oggi, 1) if pd.notna(rsi_oggi) else 50.0,
                'Giorni_Utili': earnings_giorni,
            }
            # Attiva segnale IGNITION (Inizio Salita) sui titoli idonei (S-Score >= 60 e non in Fase 4)
            if s_score >= 60 and "FASE 4" not in fase:
                try:
                    _ok_ign_s, _mot_ign_s = verifica_ignition_start(df, ticker, s_score_precalc=s_score)
                    if _ok_ign_s:
                        _pos_ign = ticker_in_portafoglio.get(ticker, {})
                        stats['ignition_oggi'].append({
                            'ticker': ticker,
                            'Ticker': ticker,
                            'motivo': _mot_ign_s,
                            's_score': s_score,
                            'fase': fase,
                            'prezzo_eur': prezzo_eur,
                            'quote': float(_pos_ign.get('Quantita', 0) or 0),
                            'pmc_eur': float(_pos_ign.get('Prezzo_Medio', 0) or 0),
                        })
                        registra_proposta("SCANSIONE", "IGNITION", ticker, _mot_ign_s, stato="N/D")
                except Exception:
                    pass
            # Rilevamento figure grafiche ad alta probabilità (Watchlist e Portafoglio)
            try:
                _in_port_pat = ticker in ticker_in_portafoglio
                _pnl_pat = None
                if _in_port_pat:
                    _pos_pat = ticker_in_portafoglio[ticker]
                    _pmc_pat = float(_pos_pat.get('Prezzo_Medio', 0) or 0)
                    if _pmc_pat > 0 and prezzo_eur is not None:
                        _pnl_pat = ((float(prezzo_eur) / _pmc_pat) - 1.0) * 100.0
                    elif _pos_pat.get('PnL_%') is not None:
                        _pnl_pat = float(_pos_pat.get('PnL_%'))
                _pat_res = pattern_engine.analizza_pattern_titolo(
                    ticker=ticker,
                    df=df,
                    in_portafoglio=_in_port_pat,
                    pnl_pct=_pnl_pat,
                    eurusd_rate=eurusd_rate,
                    currency=currency,
                    earnings_giorni=earnings_giorni,
                    spy_regime=_spy_regime_scan,
                    s_score=s_score,
                )
                pattern_engine.registra_alert_in_contenitore(pattern_alerts_scan, _pat_res)
            except Exception:
                pass
            # Valutazione "Sorvegliati Speciali — Luce Arancione" e candidati "Cluster Insider SEC" (Fonte B)
            try:
                _tk_up_sc = str(ticker).strip().upper()
                scan_price_map_bacheca[_tk_up_sc] = {"prezzo": float(df["Close"].iloc[-1]), "fase": fase, "currency": currency}
                if _tk_up_sc in watchlist_only_set:
                    _sec_ins_scan = get_sec_insider_buys_90gg(ticker, max_docs=12) if 'get_sec_insider_buys_90gg' in globals() else None
                    _sv_item = pattern_engine.valuta_sorvegliato_speciale(
                        ticker=ticker,
                        df=df,
                        s_score=s_score,
                        fase_weinstein=fase,
                        currency=currency,
                        eurusd_rate=eurusd_rate,
                        spy_regime=_spy_regime_scan,
                        sec_insider=_sec_ins_scan,
                    )
                    if _sv_item:
                        sorvegliati_candidati_scan.append(_sv_item)
                    _cl_item = _valuta_cluster_insider_bacheca(ticker, df, info, _sec_ins_scan, s_score, fase, currency=currency)
                    if _cl_item:
                        cluster_insider_bacheca_scan.append(_cl_item)
            except Exception:
                pass
            oggi_str = datetime.now().strftime("%Y-%m-%d")
            idx_oggi = len(df) - 1
            trigger_by_tecnico_oggi = False
            trigger_sell_tecnico_oggi = False
            if idx_oggi >= sma_long:
                prezzo_oggi = df['Close'].iloc[idx_oggi]
                sma50_oggi = df['SMA_Short'].iloc[idx_oggi]
                vol_oggi = df['Volume'].iloc[idx_oggi]
                vol_medio_oggi = df['Vol_Media_20'].iloc[idx_oggi]
                open_oggi = df['Open'].iloc[idx_oggi]
                distanza = abs(prezzo_oggi - sma50_oggi) / sma50_oggi
                delta_rsi = df['Close'].diff()
                gain_rsi = (delta_rsi.where(delta_rsi > 0, 0)).rolling(window=14).mean()
                loss_rsi = (-delta_rsi.where(delta_rsi < 0, 0)).rolling(window=14).mean()
                rs_rsi = gain_rsi / loss_rsi
                rsi_oggi_scan = float((100 - (100 / (1 + rs_rsi))).iloc[idx_oggi]) if not rs_rsi.empty else 50
                if distanza <= 0.02 and vol_oggi > vol_medio_oggi and prezzo_oggi > open_oggi and rsi_oggi_scan <= 70:
                    trigger_by_tecnico_oggi = True
                prezzo_ieri = df['Close'].iloc[idx_oggi-1]
                sma200_oggi = df['SMA_Long'].iloc[idx_oggi]
                sma200_ieri = df['SMA_Long'].iloc[idx_oggi-1]
                if prezzo_oggi < sma200_oggi and prezzo_ieri >= sma200_ieri and vol_oggi > vol_medio_oggi:
                    trigger_sell_tecnico_oggi = True
            if trigger_by_tecnico_oggi:
                registra_segnale(ticker, 'BY', prezzo_usd, oggi_str)
            elif trigger_sell_tecnico_oggi:
                registra_segnale(ticker, 'SELL', prezzo_usd, oggi_str)
            if ignore_fase_4 and "FASE 4" in fase:
                stats['sell_count'] += 1
                stats['sell_tickers'].append(ticker)
                continue
            # Filtri allineati al testo semplice restituito da rileva_fase_weinstein(df)
            is_cp_valido = (40 <= s_score <= 60 and ("FASE 1" in fase or "FASE 2" in fase) and vol_ratio >= 1.60 and figura_z)
            is_fortezza_valida = (s_score >= 60 and "FASE 2" in fase)
            is_fortezza_accumulo = (s_score >= 60 and "FASE 1" in fase and vol_ratio >= 1.60 and figura_z)
            is_watchlist = (s_score >= 40 and ("FASE 1" in fase or "FASE 2" in fase or "CORREZIONE" in fase) and not is_cp_valido and not is_fortezza_valida)
            if ticker in ticker_in_portafoglio and (trigger_by or trigger_by_fabio):
                pos = ticker_in_portafoglio[ticker]
                azioni = math.floor(100.0 / prezzo_eur)
                if azioni > 0:
                    pyramiding_alerts.append({'ticker': ticker, 'tipo': pos.get('Tipo', 'Spot'), 'prezzo_attuale': prezzo_eur, 'pyramiding': {'azioni': azioni, 'capitale': round(azioni * prezzo_eur, 2), 'stop_loss': round(prezzo_eur * 0.88, 2), 'target': round(prezzo_eur * 1.50, 2)}})
                    registra_proposta("SCANSIONE", "PYRAMIDING", ticker, f"Pyramiding: {azioni} azioni, Capitale ~{round(azioni * prezzo_eur, 2)}€", stato="N/D")
            if is_cp_valido:
                registra_segnale(ticker, 'BY', prezzo_usd, oggi_str)
                lista_cavalli.append({'Ticker': ticker, 'Prezzo EUR': prezzo_eur, 'S-Score': s_score, 'Fase': fase, 'Vol Ratio': round(vol_ratio, 2), 'Figura Z': 'SI', 'Stato BY': "🟢 BY", 'Earnings': earnings_msg})
                stats['by_count'] += 1
                stats['by_tickers'].append(ticker)
            elif is_fortezza_valida or is_fortezza_accumulo:
                if trigger_by_fabio:
                    registra_segnale(ticker, 'BY_FABIO', prezzo_usd, oggi_str)
                    stato_by_display, motivo_display = "🟢 BY FABIO", motivo_by_fabio
                elif trigger_by or is_fortezza_accumulo:
                    registra_segnale(ticker, 'BY', prezzo_usd, oggi_str)
                    stato_by_display, motivo_display = "🟢 BY", motivo_by
                else:
                    stato_by_display, motivo_display = "🟡 HOLD", motivo_by
                lista_fortezza.append({'Ticker': ticker, 'Prezzo EUR': prezzo_eur, 'S-Score': s_score, 'Fase': fase, 'Stato BY': stato_by_display, 'Motivo BY': motivo_display, 'Earnings': earnings_msg})
                if trigger_by or trigger_by_fabio or is_fortezza_accumulo:
                    stats['by_count'] += 1
                    stats['by_tickers'].append(ticker)
                else:
                    stats['hold_count'] += 1
                    stats['hold_tickers'].append(ticker)
            elif is_watchlist:
                motivi_hold = list()
                if vol_ratio < 1.60:
                    motivi_hold.append("Volumi bassi")
                if not figura_z:
                    motivi_hold.append("No Figura Z")
                lista_monitor.append({'Ticker': ticker, 'Prezzo EUR': prezzo_eur, 'S-Score': s_score, 'Fase': fase, 'Motivo Hold': "; ".join(motivi_hold), 'Earnings': earnings_msg})
                stats['hold_count'] += 1
                stats['hold_tickers'].append(ticker)
        except Exception as e:
            error_msg = str(e)[:100]
            stats.setdefault('error_tickers', list()).append(f"{ticker}: {error_msg}")

    registra_proposta("SCANSIONE", "RIEPILOGO_SCANSIONE", "SISTEMA", f"BY: {stats['by_count']}, HOLD: {stats['hold_count']}, SELL: {stats['sell_count']}, BY_FABIO: {len(stats.get('by_fabio_tickers', list()))}, SMCI: {len(stats.get('smci_tickers', list()))}", stato="N/D")
    progress_bar.empty()
    st.session_state.dashboard_stats = stats
    try:
        if st.session_state.get('portafoglio'):
            st.session_state.portafoglio = aggiorna_quotazioni_portafoglio(st.session_state.portafoglio, eurusd_rate)
        salva_ultimo_agg_prezzi()
    except Exception:
        pass
    st.session_state.pyramiding_alerts = pyramiding_alerts
    st.session_state.take_profit_alerts = take_profit_alerts
    st.session_state.zona_interesse_alerts = zona_interesse_alerts
    st.session_state.extended_hours_alerts = extended_hours_alerts
    # Salva i risultati ordinati del motore figure grafiche in session_state per non rallentare la navigazione
    st.session_state.pattern_alerts = pattern_engine.ordina_contenitore_pattern_alerts(pattern_alerts_scan)
    # Esclude dai Sorvegliati Speciali tutti i titoli già promossi a BUY verde
    _buy_esclusi_sorv = set(stats.get('by_tickers', []) or []) | set(stats.get('by_fabio_tickers', []) or [])
    for _ig_s in (stats.get('ignition_oggi') or []):
        if isinstance(_ig_s, dict) and _ig_s.get('ticker'):
            _buy_esclusi_sorv.add(str(_ig_s.get('ticker')).upper())
    for _cat_b in ('buy_nuovo', 'buy_incremento', 'buy_mediazione'):
        for _al_b in (st.session_state.pattern_alerts.get(_cat_b) or []):
            if isinstance(_al_b, dict) and _al_b.get('ticker'):
                _buy_esclusi_sorv.add(str(_al_b.get('ticker')).upper())
    st.session_state.pattern_alerts["sorvegliati_speciali"] = pattern_engine.ordina_sorvegliati_speciali(
        sorvegliati_candidati_scan,
        buy_tickers_set=_buy_esclusi_sorv,
        max_items=8,
        max_grafici=3,
    )
    # Aggiorna la Bacheca Segnali Attivi (Fonte A Breakout Matrix + Fonte B max 1 Cluster Insider SEC + chiusure auto)
    try:
        _aggiorna_bacheca_segnali_attivi(
            st.session_state.pattern_alerts,
            cluster_insider_bacheca_scan,
            scan_price_map_bacheca,
        )
    except Exception:
        pass
    st.session_state.df_palantir = pd.DataFrame(lista_palantir) if lista_palantir else None
    if lista_fortezza or lista_cavalli or lista_monitor or lista_palantir:
        st.session_state.df_fortezza = pd.DataFrame(lista_fortezza) if lista_fortezza else None
        st.session_state.df_cavalli = pd.DataFrame(lista_cavalli) if lista_cavalli else None
        st.session_state.df_monitor = pd.DataFrame(lista_monitor) if lista_monitor else None
    st.session_state.scansione_completata = True
    st.rerun()

# ==============================================================================
# FASCIA 5 KPI FISSI SEMPRE IN ALTO (SOPRA LE TAB)
# ==============================================================================
_port_top = st.session_state.portafoglio or list()
_val_pos = sum(p.get('Valore_Attuale', 0) or (p.get('Prezzo_Attuale_EUR', 0) * p.get('Quantita', 0)) for p in _port_top if p.get('Prezzo_Attuale_EUR') is not None)
_cap_inv = sum(p.get('Prezzo_Medio', 0) * p.get('Quantita', 0) for p in _port_top)
_liq_net = calcola_liquidita_totale()
_pat_tot = _liq_net + (_val_pos if _val_pos > 0 else _cap_inv)
_pnl_pos = (_val_pos - _cap_inv) if _val_pos > 0 else 0.0
_pnl_pos_pct = ((_val_pos / _cap_inv) - 1) * 100 if (_val_pos > 0 and _cap_inv > 0) else 0.0
_pnl_tot_pct = ((_pat_tot / _cap_inv) - 1) * 100 if _cap_inv > 0 else 0.0

_p_file = 'privacy_saldi.json'
if 'nascondi_saldi' not in st.session_state:
    try:
        with open(_p_file, 'r') as _f: st.session_state.nascondi_saldi = json.load(_f).get('nascondi', False)
    except Exception: st.session_state.nascondi_saldi = False
_ce1, _ce2 = st.columns([6.5, 1])
with _ce2:
    if st.button('👁️ Mostra' if st.session_state.nascondi_saldi else '🙈 Nascondi', key='btn_eye_saldi', use_container_width=True):
        st.session_state.nascondi_saldi = not st.session_state.nascondi_saldi
        try:
            with open(_p_file, 'w') as _f: json.dump({'nascondi': st.session_state.nascondi_saldi}, _f)
        except Exception: pass
        st.rerun()
_tk1, _tk2, _tk3, _tk4, _tk5 = st.columns(5)
if st.session_state.nascondi_saldi:
    _tk1.metric('VALORE POSIZIONI', '€ •••••')
    _tk2.metric('CAPITALE INVESTITO', '€ •••••')
    _tk3.metric('P&L POSIZIONI', '€ •••••', '••••%')
    _tk4.metric('LIQUIDITÀ NETTA', '€ •••••')
    _tk5.metric('PATRIMONIO TOTALE', '€ •••••', '••••%')
else:
    _tk1.metric("VALORE POSIZIONI", f"€ {_val_pos:,.2f}" if _val_pos > 0 else "Aggiorna...")
    _tk2.metric("CAPITALE INVESTITO", f"€ {_cap_inv:,.2f}")
    _tk3.metric("P&L POSIZIONI", f"€ {_pnl_pos:+,.2f}", f"{_pnl_pos_pct:+.2f}%")
    _tk4.metric("LIQUIDITA NETTA", f"€ {_liq_net:,.2f}")
    _tk5.metric("PATRIMONIO TOTALE", f"€ {_pat_tot:,.2f}", f"{_pnl_tot_pct:+.2f}%")
st.markdown("<div style='margin-bottom: 0.6rem;'></div>", unsafe_allow_html=True)

# ==============================================================================
# TAB PRINCIPALI (7 SCHEDE CON RIEPILOGO OPERATIVO IN PRIMA PAGINA)
# ==============================================================================
tab_riepilogo, tab_portafoglio, tab_console, tab_confronto, tab_scanner, tab_analisi, tab_registro, tab_paper, tab_insider, tab_check_regole = st.tabs(["Riepilogo",
    "Portafoglio",
    "Console Operativa",
    "Confronto BY",
    "Scanner Dashboard",
    "Analisi Singola",
    "Registro Acquisti & Vendite",
    "Portfolio AI", "🕵️ Insider & Stagionalità", "🩺 Check Regole"])

with tab_riepilogo:
    st.subheader("🎯 Riepilogo Operativo — Cose da Fare & Valutare Oggi")
    st.caption("Cruscotto rapido delle priorità operative estratte da Scansione, Portafoglio e Ottimizzazione.")

    col_r_btn1, col_r_btn2 = st.columns(2)
    with col_r_btn1:
        if st.button("🔄 Aggiorna Quotazioni Portafoglio", type="secondary", key="riep_upd_port"):
            with st.spinner("🔄 Aggiornamento quotazioni in corso..."):
                st.session_state.portafoglio = aggiorna_quotazioni_portafoglio(st.session_state.portafoglio, eurusd_rate)
                st.session_state.last_update = datetime.now().strftime("%H:%M:%S")
                salva_ultimo_agg_prezzi()
            st.rerun()
    with col_r_btn2:
        st.info("💡 Per aggiornare segnali BY / BY FABIO e alert tecnici, usa **🔴 AVVIA SCANSIONE** nella barra a sinistra.")

    st.markdown("---")
    stats_riep = st.session_state.dashboard_stats
    port_riep = st.session_state.portafoglio or list()

    # KPI Riepilogo Rapido
    by_fabio_list = stats_riep.get('by_fabio_tickers', list()) if stats_riep else list()
    by_std_list = [t for t in (stats_riep.get('by_tickers', list()) if stats_riep else list()) if t not in by_fabio_list]
    tp_list = st.session_state.get('take_profit_alerts', list()) or list()
    pyr_list = st.session_state.get('pyramiding_alerts', list()) or list()
    zona_list = st.session_state.get('zona_interesse_alerts', list()) or list()

    ign_list = (st.session_state.get('dashboard_stats') or {}).get('ignition_oggi', [])
    ign_tickers_str = ', '.join([x['ticker'] for x in ign_list]) if ign_list else 'Nessuno oggi'
    c_buy1, c_buy2, c_buy3 = st.columns(3)
    with c_buy1:
        st.metric('🚀 IGNITION (Inizio Salita)', len(ign_list), ign_tickers_str)
        with st.expander('ℹ️ Spiegazione & Dettagli IGNITION', expanded=bool(ign_list)):
            st.caption('Intercetta l\'inizio del rialzo: Squeeze Bollinger o riconquista SMA 20 + sopra VPOC Balene + S-Score >= 60 + Squeeze Bollinger o riconquista SMA 20 + sopra VPOC Balene + Volumi >= 1.35x + RSI 45-63 in salita.')
            if ign_list:
                for x in sorted(ign_list, key=lambda x: float(x.get('investito_eur') or x.get('capitale_investito') or (float(x.get('quote') or x.get('quantita') or x.get('qta') or 0) * float(x.get('pmc_eur') or x.get('pmc') or x.get('prezzo_medio') or x.get('prezzo_carico') or 0))), reverse=True):
                    st.markdown(f"- **{x['ticker']}**: {x['motivo']}")
            else:
                st.info('Nessun titolo attiva tutti i 4 filtri di accensione oggi.')
    with c_buy2:
        st.metric("🟢 Ingressi BY FABIO", len(by_fabio_list), ", ".join(by_fabio_list) if by_fabio_list else "Nessuno")
        with st.expander("ℹ️ Spiegazione BY FABIO"):
            if by_fabio_list:
                st.markdown(f"**Titoli attivi:** `{', '.join(by_fabio_list)}`\n\nSetup matematico ad alta probabilità: ritracciamento su **SMA 50**, volumi superiori alla media e punteggio fondamentale elevato.")
            else:
                st.caption("Nessun titolo soddisfa oggi tutti i filtri severi BY FABIO.")
    with c_buy3:
        st.metric("🔵 Ingressi BY Standard", len(by_std_list), ", ".join(by_std_list[:4]) if by_std_list else "Nessuno")
        with st.expander("ℹ️ Spiegazione BY"):
            if by_std_list:
                st.markdown(f"**Titoli attivi:** `{', '.join(by_std_list)}`\n\nSegnale tecnico di rimbalzo su SMA 50 confermato con volumi.")
            else:
                st.caption("Nessun segnale BY tecnico standard attivo al momento.")

    c_gest1, c_gest2 = st.columns(2)
    with c_gest1:
        st.metric("🎯 Take Profit / Pyramiding", f"{len(tp_list)} TP / {len(pyr_list)} PYR")
        with st.expander("ℹ️ Vedi titoli TP / PYR"):
            if tp_list:
                for _tp in tp_list:
                    st.markdown(f"🔴 **Take Profit — {_tp.get('ticker')}**: RSI a **{_tp.get('rsi')}** (ipercomprato) con gain **+{_tp.get('gain_pct')}%**. Valuta una presa di profitto parziale.")
            if pyr_list:
                for _py in pyr_list:
                    st.markdown(f"🔵 **Pyramiding — {_py.get('ticker')}**: trend forte, puoi aggiungere **{_py.get('pyramiding', {}).get('azioni')} az.** (~€{_py.get('pyramiding', {}).get('capitale')}).")
            if not tp_list and not pyr_list:
                st.caption("Nessun titolo in zona Take Profit o Pyramiding.")
    with c_gest2:
        st.metric("🟡 Zona SMA 200", len(zona_list), "Supporti chiave")
        with st.expander("ℹ️ Vedi titoli su SMA 200"):
            if zona_list:
                for _z in zona_list:
                    st.markdown(f"🟡 **{_z.get('ticker')}**: distanza **{_z.get('distanza_pct')}%** dalla SMA 200.")

    st.markdown("---")
    # Sezione 4 alert distinti del motore figure grafiche ad alta probabilità
    pattern_engine.render_sezione_pattern_riepilogo(st, st.session_state.get("pattern_alerts"))

    st.markdown("---")
    # Bacheca Segnali Attivi persistente (Fonte A Breakout Matrix + Fonte B Cluster Insider SEC)
    render_bacheca_segnali_attivi(eurusd_rate)

    st.markdown("---")
    if st.session_state.get('extended_hours_alerts'):
        st.subheader('⚡ ALERT MOVIMENTI ANOMALI (Fuori Orario > ±5%)')
        col_ex1, col_ex2 = st.columns(2)
        for idx_ex, al_ex in enumerate(st.session_state.extended_hours_alerts):
            bx_c = 'signal-green' if al_ex['variazione'] > 0 else 'signal-red'
            htm_ex = f'<div class="signal-box {bx_c}"><h4 style="margin:0">{al_ex["colore"]} {al_ex["ticker"]} - ({al_ex["sessione"]})</h4><p style="margin:0.5rem 0">Variazione: <strong>{al_ex["variazione"]:+.2f}%</strong> | Prezzo: €{al_ex["prezzo_eur"]:.2f}</p></div>'
            if idx_ex % 2 == 0:
                col_ex1.markdown(htm_ex, unsafe_allow_html=True)
            else:
                col_ex2.markdown(htm_ex, unsafe_allow_html=True)
        st.markdown('---')
    st.subheader("🎯 Regia Acquisti Prioritizzata & Fonti di Finanziamento")
    _taglia_ok = float(st.session_state.get("sim_importo_box", 200.0) or 200.0)
    # Costruisce la mappa reale di Fase/S-Score/RSI/Earnings dai dati dell'ultima scansione
    _df_m = _costruisci_mappa_metriche_scan()
    _cassa_ok = float(_liq_net) if "_liq_net" in locals() else float(st.session_state.get("liquidita", 0.0) or 0.0)
    _extra_ok = float(st.session_state.get("liq_aggiuntiva_sim", 0.0) or 0.0)
    _escl_ok = {x.strip().upper() for x in re.split(r"[,;\s\n]+", str(esclusioni_input if "esclusioni_input" in locals() else "")) if x.strip()}
    _cat_ok = {x.split(":")[0].strip().upper() for x in str(catalizzatori_input if "catalizzatori_input" in locals() else "").splitlines() if ":" in x}
    _port_ok = portafoglio_attuale if "portafoglio_attuale" in locals() else st.session_state.get("portafoglio", [])
    _piano_ok, _scart_ok = calcola_regia_acquisti(ign_list if "ign_list" in locals() else [], by_fabio_list if "by_fabio_list" in locals() else [], by_std_list if "by_std_list" in locals() else [], tp_list if "tp_list" in locals() else [], _port_ok, _df_m, _cassa_ok, _extra_ok, _escl_ok, _cat_ok, _taglia_ok, manual_l=[x.strip().upper() for x in re.split(r"[,;\s\n]+", str(st.session_state.get("titoli_priorita_input", ""))) if x.strip()])
    if _piano_ok:
        st.caption(f"Taglia per singolo ordine: **€ {_taglia_ok:,.2f}** | Allocazione automatica per priorità e potenziale:")
        for _rk_i, _tk_i, _tp_i, _pt_i, _sc_i, _nt_i, _fn_i, _cp_i in _piano_ok:
            _med = "🥇" if _rk_i == 1 else ("🥈" if _rk_i == 2 else ("🥉" if _rk_i == 3 else f"#{_rk_i}"))
            _c1, _c2 = st.columns([1.1, 1.9])
            with _c1:
                _m_card = regia_tracker._fetch_metriche_pro(_tk_i, eurusd_rate) if ('regia_tracker' in globals() and hasattr(regia_tracker, '_fetch_metriche_pro')) else None
                _pt_show = _m_card['pot_reale'] if _m_card else _pt_i
                _sl_txt_v = f"\n- **🛑 Stop Loss:** € {_m_card['sl_eur']:.2f} ({_m_card['sl_pct']:+.1f}%) | **🎯 T1:** € {_m_card['t1_eur']:.2f} (+{_m_card['t1_pct']:.1f}%) | **T2:** € {_m_card['t2_eur']:.2f} (+{_m_card['t2_pct']:.1f}%)" if _m_card else ""
                st.markdown(f"### {_med} {_tk_i} ({_tp_i})\n- **Stato:** {_nt_i}\n- **Potenziale:** {_pt_show:+.1f}% | **Score:** {_sc_i:.0f}{_sl_txt_v}")
                if 'regia_tracker' in globals() and hasattr(regia_tracker, 'render_stella_watchlist'):
                    regia_tracker.render_stella_watchlist(_tk_i, f'regia_{_rk_i}')
            with _c2:
                if _cp_i <= 0:
                    st.success(f"✅ **Finanziato (€ {_taglia_ok:,.2f}):**\n" + "\n".join([f"- {x}" for x in _fn_i]))
                else:
                    _parz = " + ".join(_fn_i) if _fn_i else "Nessuna risorsa residua"
                    st.warning(f"⚠️ **Risorse insufficienti:** disponibile ({_parz}). **Mancano € {_cp_i:,.2f}** di liquidità extra: lascia passare o aggiungi € {_cp_i:,.2f} nella sidebar.")
    else:
        st.info("Nessun segnale BUY supera oggi i filtri di qualità (potenziale ≥ +10% e regola mediazione).")
    if _scart_ok:
        with st.expander("🚫 Segnali BUY scartati dai filtri di qualità"):
            for _sm in _scart_ok:
                st.markdown(f"- {_sm}")
                st.caption("Area di supporto istituzionale di lungo periodo: attendi conferma rialzista prima di entrare.")
            else:
                st.caption("Nessun titolo della watchlist vicino alla SMA 200.")

    import importlib; importlib.reload(regia_tracker)
    regia_tracker.render_tracker_regia(_piano_ok, _port_ok, eurusd_rate, _taglia_ok)
    st.markdown("---")
    col_op1, col_op2 = st.columns(2)

    with col_op1:
        st.markdown("#### 1. 🟢 Nuovi Ingressi & Rafforzamenti da Valutare")
        if by_fabio_list:
            st.markdown(f"""
            <div class="signal-box signal-fabio">
                <h4 style="margin:0; color:#FFFFFF;">⭐ PRIORITÀ 1 — Segnali BY FABIO ({len(by_fabio_list)})</h4>
                <p style="margin:0.4rem 0 0 0; font-size:1.1rem; font-weight:bold; color:#089981;">{', '.join(by_fabio_list)}</p>
                <small>Setup matematico ad alta probabilità. Vai nella tab <strong>⚖️ Confronto BY / FABIO</strong> per confrontare i grafici.</small>
            </div>
            """, unsafe_allow_html=True)
        if by_std_list:
            st.markdown(f"""
            <div class="signal-box signal-green">
                <strong>✅ Segnali BY Tecnici ({len(by_std_list)}):</strong> {', '.join(by_std_list)}<br>
                <small>Pullback su SMA 50 confermato con volumi sopra la media.</small>
            </div>
            """, unsafe_allow_html=True)
        if pyr_list:
            for p_al in pyr_list:
                st.markdown(f"""
                <div class="signal-box signal-blue">
                    <strong>🔁 Pyramiding su {p_al['ticker']}:</strong> Aggiungi {p_al['pyramiding']['azioni']} azioni (~€{p_al['pyramiding']['capitale']}) | Stop: €{p_al['pyramiding']['stop_loss']}
                </div>
                """, unsafe_allow_html=True)
        if zona_list:
            tickers_z = ", ".join([f"{z['ticker']} ({z['distanza_pct']}%)" for z in zona_list])
            st.markdown(f"""
            <div class="signal-box signal-yellow">
                <strong>🟡 Vicini a SMA 200 (Zona Acquisto):</strong> {tickers_z}
            </div>
            """, unsafe_allow_html=True)
        if not (by_fabio_list or by_std_list or pyr_list or zona_list):
            st.info("Nessun segnale di ingresso attivo. Avvia una scansione per aggiornare.")

    with col_op2:
        st.markdown("#### 2. 🛡️ Gestione Portafoglio, Prese di Profitto & Allerte")
        if tp_list:
            for tp in tp_list:
                st.markdown(f"""
                <div class="signal-box signal-red">
                    <strong>🎯 Valuta Take Profit su {tp['ticker']}:</strong> RSI a {tp['rsi']} (Ipercomprato) | Gain attuale: <strong>+{tp['gain_pct']}%</strong>
                </div>
                """, unsafe_allow_html=True)

        # Controllo Earnings e PAC sospesi dal portafoglio
        alert_port_trovati = False
        for pos in port_riep:
            earn_txt = pos.get('Earnings', '')
            stato_p = pos.get('Stato_PAC', '')
            if '🔴' in earn_txt or '🟡' in earn_txt:
                alert_port_trovati = True
                st.markdown(f"""
                <div class="signal-box signal-yellow">
                    <strong>📅 Trimestrale in arrivo — {pos['Ticker']}:</strong> {earn_txt} (Valuta protezione posizione)
                </div>
                """, unsafe_allow_html=True)
            if 'SOSPESO' in stato_p:
                alert_port_trovati = True
                st.markdown(f"""
                <div class="signal-box signal-red">
                    <strong>⛔ {pos['Ticker']} — {stato_p}:</strong> Deterioramento trend o fondamentali. Controlla nella tab Portafoglio.
                </div>
                """, unsafe_allow_html=True)

        if stats_riep and stats_riep.get('sell_tickers'):
            st.markdown(f"""
            <div class="signal-box signal-red">
                <strong>🔴 Titoli in Fase 4 / Da Evitare:</strong> {', '.join(stats_riep['sell_tickers'])}
            </div>
            """, unsafe_allow_html=True)
            alert_port_trovati = True

        if st.session_state.get('risultato_podc') and st.session_state['risultato_podc'].get('suggestions'):
            for sug in st.session_state['risultato_podc']['suggestions']:
                alert_port_trovati = True
                st.markdown(f"""
                <div class="signal-box signal-green">
                    <strong>🛡️ Proposta PODC attiva:</strong> Vendi {sug['sell_pct']}% di {sug['sell_ticker']} (€{sug['capital_freed']:.2f}) → Media {sug['buy_ticker']}
                </div>
                """, unsafe_allow_html=True)

        if not tp_list and not alert_port_trovati:
            st.success("✅ Nessuna criticità o allerta urgente sulle posizioni in portafoglio.")

with tab_confronto:
    st.subheader("⚖️ Confronto Rapido Grafici — Segnali BY & BY FABIO")
    st.caption("Affianca a colpo d'occhio i titoli con segnale attivo (o selezionali manualmente) con tutti i segnali ▲ BY e ▼ SELL sul grafico.")

    stats_conf = st.session_state.dashboard_stats
    lista_fabio_conf = stats_conf.get('by_fabio_tickers', list()) if stats_conf else list()
    lista_by_conf = stats_conf.get('by_tickers', list()) if stats_conf else list()
    tutti_segnali_conf = list(dict.fromkeys(lista_fabio_conf + lista_by_conf))

    col_cf1, col_cf2, col_cf3 = st.columns([2, 2, 1])
    with col_cf1:
        filtro_gruppo = st.radio(
            "Gruppo da confrontare:",
            ["🟢 Solo BY FABIO", "🔵 Tutti i BY (FABIO + Standard)", "🎯 Selezione Manuale"],
            horizontal=True
        )
    with col_cf2:
        tf_conf_map = {
            "6 Mesi (Daily)": ("6mo", "1d", "1d"),
            "1 Anno (Daily)": ("1y", "1d", "1d"),
            "2 Anni (Weekly)": ("2y", "1d", "1wk")
        }
        tf_conf_scelta = st.selectbox("Orizzonte Grafici:", list(tf_conf_map.keys()), index=1)
    with col_cf3:
        num_colonne_conf = st.selectbox("Colonne:", [2, 1], index=0)

    if filtro_gruppo == "🟢 Solo BY FABIO":
        tickers_da_mostrare = lista_fabio_conf
    elif filtro_gruppo == "🔵 Tutti i BY (FABIO + Standard)":
        tickers_da_mostrare = tutti_segnali_conf
    else:
        opzioni_manuali = sorted(list(set(tickers + tutti_segnali_conf)))
        default_manuali = tutti_segnali_conf[:4] if tutti_segnali_conf else opzioni_manuali[:2]
        tickers_da_mostrare = st.multiselect("Scegli i titoli da affiancare:", opzioni_manuali, default=default_manuali)

    if not tickers_da_mostrare:
        st.info("📭 Nessun titolo trovato in questo gruppo. Avvia una scansione dalla sidebar oppure scegli **🎯 Selezione Manuale** per confrontare qualsiasi ticker.")
    else:
        st.markdown(f"**Visualizzazione di {len(tickers_da_mostrare)} titoli:** {', '.join(tickers_da_mostrare)}")
        st.markdown("---")
        p_conf, int_conf, tf_conf = tf_conf_map[tf_conf_scelta]
        port_lookup = {p['Ticker']: p['Prezzo_Medio'] for p in (st.session_state.portafoglio or list())}

        zoom_ticker = st.session_state.get("conf_fullscreen_ticker")
        if zoom_ticker and zoom_ticker in tickers_da_mostrare:
            if st.button(f"⬅️ Torna alla vista affiancata (chiudi zoom su {zoom_ticker})", type="primary", key="btn_exit_zoom_conf"):
                st.session_state.conf_fullscreen_ticker = None
                st.rerun()
            tickers_render = [zoom_ticker]
            cols_effettive = 1
            altezza_g = 720
        else:
            tickers_render = tickers_da_mostrare
            cols_effettive = num_colonne_conf
            altezza_g = 520

        for idx_c in range(0, len(tickers_render), cols_effettive):
            cols_grid = st.columns(cols_effettive)
            for j in range(cols_effettive):
                if idx_c + j < len(tickers_render):
                    t_curr = tickers_render[idx_c + j]
                    with cols_grid[j]:
                        if not zoom_ticker:
                            if st.button(f"🔍 Espandi {t_curr} a tutto schermo", key=f"btn_zoom_{t_curr}_{idx_c}_{j}", use_container_width=True):
                                st.session_state.conf_fullscreen_ticker = t_curr
                                st.rerun()
                        badge_tipo = '<span class="by-fabio-badge">🟢 BY FABIO</span>' if t_curr in lista_fabio_conf else '<span style="background-color:rgba(41,98,255,0.18);color:#60A5FA;border:1px solid #2962FF;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:700;margin-left:8px;">🔵 BY</span>'
                        try:
                            t_obj_c = yf.Ticker(t_curr)
                            h_c = t_obj_c.history(period="1y")
                            inf_c = t_obj_c.info
                            if not h_c.empty:
                                p_eur_c, p_usd_c, _ = get_prezzi_corretti(t_obj_c, eurusd_rate)
                                sc_c = calcola_s_score(inf_c)
                                fase_c = rileva_fase_weinstein(h_c)
                                d_c = h_c['Close'].diff()
                                g_c = (d_c.where(d_c > 0, 0)).rolling(window=14).mean()
                                l_c = (-d_c.where(d_c < 0, 0)).rolling(window=14).mean()
                                rsi_c = float((100 - (100 / (1 + (g_c / l_c)))).iloc[-1]) if not (g_c / l_c).empty else 50
                                st.markdown(f"""
                                <div style="background-color:#131722; border:1px solid #2A2E39; border-radius:8px 8px 0 0; padding:0.75rem 1rem; margin-bottom:-0.5rem;">
                                    <div style="display:flex; justify-content:space-between; align-items:center;">
                                        <span style="font-size:1.25rem; font-weight:700; color:#FFFFFF;">{t_curr} {badge_tipo}</span>
                                        <span style="font-family:'JetBrains Mono', monospace; font-size:1.1rem; font-weight:700; color:#FFFFFF;">€{p_eur_c:.2f} <span style="color:#787B86; font-size:0.85rem;">(${p_usd_c:.2f})</span></span>
                                    </div>
                                    <div style="font-size:0.82rem; color:#94A3B8; margin-top:0.35rem;">
                                        S-Score: <strong style="color:#FFFFFF;">{sc_c}</strong> &nbsp;|&nbsp; RSI: <strong style="color:#FFFFFF;">{rsi_c:.1f}</strong> &nbsp;|&nbsp; {fase_c}
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                        except:
                            st.markdown(f"#### {t_curr}")

                        tf_c_sel = st.session_state.get(f"tf_sel_conf_{t_curr}", "3M")
                        # Carica sempre 2 anni di storico scorribile mantenendo la finestra iniziale sul timeframe scelto
                        per_c = "2y"
                        fig_c = genera_grafico_baleine(
                            t_curr, per_c, sma_short, sma_long,
                            prezzo_medio_eur=port_lookup.get(t_curr),
                            timeframe=tf_c_sel, interval="1d",
                            eurusd_rate=eurusd_rate, height=altezza_g
                        )
                        if fig_c:
                            fig_c = applica_controlli_grafico(fig_c, 1)
                            st.plotly_chart(fig_c, use_container_width=True, config={"scrollZoom": True, "displaylogo": False, "responsive": True}, key=f"chart_conf_{t_curr}_{idx_c}_{j}")
                            render_barra_intervalli_yahoo(t_curr, "conf", default_tf="3M")
                        else:
                            st.warning(f"Dati grafico non disponibili per {t_curr}")

st.session_state.pop("_gh_last_msg", None)
if False:
    _st_t, _st_m = st.session_state["_gh_last_msg"]
    if _st_t == "ok":
        st.success(_st_m)
    else:
        st.error(_st_m)

with tab_portafoglio:
    st.session_state["_grafico_uid_cnt"] = 0
    with st.expander("➕ Aggiungi / Modifica Titoli in Portafoglio", expanded=(len(st.session_state.portafoglio or []) == 0)):
        col_add1, col_add2, col_add3, col_add4 = st.columns(4)
        with col_add1:
            new_ticker = st.text_input("Ticker (es. META, GOOGL, MU)", key="inp_new_tk_port").upper()
        with col_add2:
            new_tipo = st.selectbox("Tipo", ["Spot", "PAC"], key="sel_new_tp_port")
        with col_add3:
            new_qta = st.number_input("Quantità", min_value=0.0001, step=0.0001, format="%.6f", key="num_new_qta_port")
        with col_add4:
            new_medio = st.number_input("Prezzo Medio €", min_value=0.01, step=0.01, key="num_new_pmc_port")
        if st.button("✅ Conferma Acquisto in Portafoglio", type="primary", key="btn_add_port_direct"):
            _tk_clean = str(new_ticker).strip().upper()
            if _tk_clean and float(new_qta) > 0 and float(new_medio) > 0:
                _trovato_m = False
                # Fonde sempre sul ticker esistente (anche se PAC vs Spot) per evitare schede duplicate
                for _item_m in st.session_state.portafoglio:
                    if str(_item_m.get("Ticker", "")).strip().upper() == _tk_clean:
                        _q_old = float(_item_m.get("Quantita", 0) or 0)
                        _pmc_old = float(_item_m.get("Prezzo_Medio", 0) or 0)
                        _q_new = round(_q_old + float(new_qta), 6)
                        _pmc_new = round(((_q_old * _pmc_old) + (float(new_qta) * float(new_medio))) / _q_new, 4)
                        _item_m["Quantita"] = _q_new
                        _item_m["Prezzo_Medio"] = _pmc_new
                        _item_m["Valore_Carico"] = round(_q_new * _pmc_new, 2)
                        _pe_es = float(_item_m.get("Prezzo_Attuale_EUR") or 0)
                        if _pe_es > 0:
                            _item_m["Valore_Attuale"] = round(_q_new * _pe_es, 2)
                            _item_m["PnL_EUR"] = round(_item_m["Valore_Attuale"] - _item_m["Valore_Carico"], 2)
                            _item_m["PnL_%"] = round(((_item_m["Valore_Attuale"] / _item_m["Valore_Carico"]) - 1) * 100, 2) if _item_m["Valore_Carico"] > 0 else 0.0
                        _trovato_m = True
                        salva_ultimo_agg_prezzi()
                        salva_json(PORTAFOGLIO_FILE, st.session_state.portafoglio)
                        registra_acquisto_storico(_tk_clean, str(_item_m.get("Tipo", new_tipo)), float(new_qta), float(new_medio), nota="Mediazione PMC")
                        break
                if not _trovato_m:
                    _q_n = round(float(new_qta), 6)
                    _pm_n = round(float(new_medio), 4)
                    st.session_state.portafoglio.append({
                        "Ticker": _tk_clean,
                        "Tipo": str(new_tipo),
                        "Quantita": _q_n,
                        "Prezzo_Medio": _pm_n,
                        "Valore_Carico": round(_q_n * _pm_n, 2),
                        "Prezzo_Attuale_EUR": _pm_n,
                        "Valore_Attuale": round(_q_n * _pm_n, 2),
                        "PnL_EUR": 0.0,
                        "PnL_%": 0.0,
                        "Data_Acquisto": datetime.now().strftime("%Y-%m-%d")
                    })
                    salva_ultimo_agg_prezzi()
                    salva_json(PORTAFOGLIO_FILE, st.session_state.portafoglio)
                    registra_acquisto_storico(_tk_clean, str(new_tipo), _q_n, _pm_n, nota="Nuovo Acquisto")
                st.rerun()

    _msg_rld_port = st.session_state.pop("_msg_reload_disk", None)
    if _msg_rld_port:
        st.success(f"✅ {_msg_rld_port}")

    for _p_chk in st.session_state.portafoglio:
        _q_c = float(_p_chk.get('Quantita', 0) or 0)
        _pmc_c = float(_p_chk.get('Prezzo_Medio', 0) or 0)
        _pe_c = float(_p_chk.get('Prezzo_Attuale_EUR', 0) or 0)
        if _q_c > 0 and _pmc_c > 0:
            _p_chk['Valore_Carico'] = round(_q_c * _pmc_c, 2)
            if _pe_c > 0:
                _p_chk['Valore_Attuale'] = round(_q_c * _pe_c, 2)
                _p_chk['PnL_EUR'] = round(_p_chk['Valore_Attuale'] - _p_chk['Valore_Carico'], 2)
                _p_chk['PnL_%'] = round(((_p_chk['Valore_Attuale'] / _p_chk['Valore_Carico']) - 1) * 100, 2)
    portafoglio = sorted(st.session_state.portafoglio, key=lambda x: float(x.get('Valore_Carico') or (float(x.get('Quantita', 0) or 0) * float(x.get('Prezzo_Medio', 0) or 0))), reverse=True)
    # Simulatore Mediazione & Gain Portafoglio subito sotto l'expander Aggiungi / Modifica Titoli
    if portafoglio:
        render_simulatore_mediazione_portafoglio(portafoglio)
    if not portafoglio or len(portafoglio) == 0:
        st.warning("⚠️ Portafoglio vuoto. Aggiungi titoli usando l'expander sopra o carica il file portafoglio.json")
        if st.button("📂 Ricarica portafoglio.json da disco", key="btn_reload_port_disk_empty"):
            _ok_r, _msg_r = ricarica_portafoglio_da_disco(push_github=True)
            if _ok_r:
                st.session_state["_msg_reload_disk"] = _msg_r
                st.rerun()
            else:
                st.error(_msg_r)
    else:
        has_live_data = any(p.get('Prezzo_Attuale_EUR') is not None for p in portafoglio)
        if not has_live_data:
            st.info("👆 Clicca **🔄 Aggiorna Quotazioni** per caricare i dati di mercato")
            if st.button("📂 Ricarica portafoglio.json da disco", key="btn_reload_port_disk_nolive"):
                _ok_r, _msg_r = ricarica_portafoglio_da_disco(push_github=True)
                if _ok_r:
                    st.session_state["_msg_reload_disk"] = _msg_r
                    st.rerun()
                else:
                    st.error(_msg_r)
        else:
            _tickers_p = list(dict.fromkeys([p['Ticker'] for p in portafoglio if p.get('Ticker')]))
            if 'port_selected_chart' not in st.session_state or st.session_state.port_selected_chart not in _tickers_p:
                _init_tk_port = st.session_state.get("sb_quick_ticker")
                st.session_state.port_selected_chart = _init_tk_port if _init_tk_port in _tickers_p else next(iter(_tickers_p))
            if 'sel_chart_port_side' not in st.session_state or st.session_state['sel_chart_port_side'] not in _tickers_p:
                st.session_state['sel_chart_port_side'] = st.session_state.port_selected_chart

            def _on_port_chart_change():
                val_p = st.session_state.get("sel_chart_port_side")
                if val_p:
                    st.session_state["port_selected_chart"] = val_p
                    st.session_state["sb_quick_ticker"] = val_p
                    st.session_state["sb_ticker_radio"] = val_p
                    st.session_state["txt_analisi_singola_tk"] = val_p

            col_port_left, col_port_right = st.columns((0.65, 1.6)) if st.session_state.get('port_big_chart', False) else st.columns((1.25, 1))
            with col_port_right:
                _g_c1, _g_c2 = st.columns([2.2, 1])
                with _g_c1:
                    st.markdown("#### 📈 Grafico Live Posizione")
                with _g_c2:
                    _is_big = st.session_state.get("port_big_chart", False)
                    if st.button("🗗 Riduci" if _is_big else "⛶ Ingrandisci", key="btn_toggle_big_port", use_container_width=True):
                        st.session_state.port_big_chart = not _is_big
                        st.rerun()
                st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
                sel_t = st.selectbox("Seleziona titolo:", _tickers_p, label_visibility="collapsed", key="sel_chart_port_side", on_change=_on_port_chart_change)
                st.session_state.port_selected_chart = sel_t
                pmc_sel = next((p['Prezzo_Medio'] for p in portafoglio if p['Ticker'] == sel_t), None)
                tf_port_sel = st.session_state.get(f"tf_sel_port_{sel_t}", "3M")
                # Carica sempre 2 anni di storico scorribile mantenendo la finestra iniziale sul timeframe scelto
                per_port = "2y"
                _pat_live = (st.session_state.get("pattern_alerts") or {}).get("per_ticker", {}).get(str(sel_t).upper())
                fig_side = genera_grafico_baleine(sel_t, per_port, sma_short, sma_long, prezzo_medio_eur=pmc_sel, timeframe=tf_port_sel, interval="1d", eurusd_rate=eurusd_rate, height=780 if st.session_state.get('port_big_chart', False) else 580, pattern_info=_pat_live)
                if fig_side:
                    # Se il titolo ha un pattern attivo rilevato in scansione, traccia Trigger Y, Target e Stop
                    if _pat_live:
                        fig_side = pattern_engine.aggiungi_livelli_pattern_al_grafico(fig_side, _pat_live)
                        _sym_live = "$" if str(_pat_live.get("currency", "USD")).upper() == "USD" else "€"
                        st.caption(
                            f"**{_pat_live.get('badge')}** — {_pat_live.get('figura')} ({_pat_live.get('confidenza')}%) | "
                            f"⚡ Y: `{_sym_live}{_pat_live.get('trigger_y'):.2f}` | 🎯 Target: `{_pat_live.get('target_pct'):+.1f}%` (`{_sym_live}{_pat_live.get('target_price'):.2f}`) | "
                            f"🛑 Stop: `{_sym_live}{_pat_live.get('stop_price'):.2f}` | R/R `1:{_pat_live.get('rr'):.2f}`"
                        )
                    fig_side = applica_controlli_grafico(fig_side, 2)
                    st.plotly_chart(fig_side, use_container_width=True, config={"scrollZoom": True, "displaylogo": False, "responsive": True}, key=f"port_side_live_chart_{sel_t}")
                    render_barra_intervalli_yahoo(sel_t, "port", default_tf="3M")
            with col_port_left:
                _hdr_c1, _hdr_c2, _hdr_c3 = st.columns((1.25, 0.95, 1.15))
                with _hdr_c1:
                    st.markdown("#### 💼 Posizioni in Portafoglio")
                with _hdr_c2:
                    if st.button("🔄 Aggiorna Prezzi", type="primary", key="btn_upd_fast_top", use_container_width=True):
                        with st.spinner("Aggiornamento..."):
                            st.session_state.portafoglio = aggiorna_quotazioni_portafoglio(st.session_state.portafoglio, eurusd_rate)
                            st.session_state.last_update = datetime.now().strftime("%H:%M:%S")
                            salva_ultimo_agg_prezzi()
                        st.rerun()
                with _hdr_c3:
                    if st.button("📂 Ricarica portafoglio.json da disco", key="btn_reload_port_disk", use_container_width=True):
                        _ok_r, _msg_r = ricarica_portafoglio_da_disco(push_github=True)
                        if _ok_r:
                            st.session_state["_msg_reload_disk"] = _msg_r
                            st.rerun()
                        else:
                            st.error(_msg_r)
                for idx_pos, pos in enumerate(portafoglio):
                    if idx_pos % 2 == 0:
                        grid_cols = st.columns(2)
                    with grid_cols[idx_pos % 2]:
                        ticker = pos['Ticker']
                        prezzo_eur = pos.get('Prezzo_Attuale_EUR')
                        var_pct = pos.get('Variazione_Pct')
                        pnl_pct = pos.get('PnL_%', 0) or 0
                        stato_pac = pos.get('Stato_PAC', 'N/A')
                        ultimo_segnale = pos.get('Ultimo_Segnale', 'N/D')
                        trend = pos.get('Trend', 'N/D')
                        earnings = pos.get('Earnings', 'N/D')
                        prezzo_medio = pos.get('Prezzo_Medio', 0)
                        quantita = pos.get('Quantita', 0)
                        pnl_eur = pos.get('PnL_EUR', 0) or 0
                        if prezzo_medio > 0 and prezzo_eur:
                            var_acquisto = ((prezzo_eur / prezzo_medio) - 1) * 100
                        else:
                            var_acquisto = 0
                        if var_pct is not None:
                            var_color = "#089981" if var_pct > 0 else "#F23645"
                            var_symbol = "▲" if var_pct > 0 else "▼" if var_pct < 0 else "●"
                            var_display = f"{var_symbol} {var_pct:+.2f}%"
                        else:
                            var_color, var_symbol, var_display = "#787B86", "●", "N/D"
                        if var_acquisto > 0:
                            acqu_color, acqu_symbol = "#089981", "▲"
                        elif var_acquisto < 0:
                            acqu_color, acqu_symbol = "#F23645", "▼"
                        else:
                            acqu_color, acqu_symbol = "#787B86", "●"
                        if pnl_pct > 0:
                            border_color = "#089981"
                        elif pnl_pct < 0:
                            border_color = "#F23645"
                        else:
                            border_color = "#2A2E39"
                        prezzo_display = f"{prezzo_eur:.2f}" if prezzo_eur is not None else "N/D"
                        if pnl_eur > 0:
                            pnl_netto = pnl_eur * 0.74
                            netto_label = f"+€ {pnl_netto:.2f} netto"
                        elif pnl_eur < 0:
                            pnl_netto = pnl_eur
                            netto_label = f"-€ {abs(pnl_netto):.2f} netto"
                        else:
                            pnl_netto, netto_label = 0, "€ 0.00 netto"
                        ticker_obj = yf.Ticker(ticker)
                        targets = calcola_target(ticker_obj, prezzo_medio, prezzo_eur)
                        if targets:
                            target_raggiunti = sum(1 for p in [targets['prog1'], targets['prog2'], targets['prog3']] if p >= 100.0)
                            if target_raggiunti == 0:
                                dots_html = '<span class="target-dot target-dot-pending" title="Nessun target raggiunto"></span><span class="target-dot target-dot-pending" title="Nessun target raggiunto"></span><span class="target-dot target-dot-pending" title="Nessun target raggiunto"></span>'
                            elif target_raggiunti == 1:
                                dots_html = '<span class="target-dot target-dot-achieved" title="Target 1 raggiunto"></span><span class="target-dot target-dot-pending" title="Target 2 non raggiunto"></span><span class="target-dot target-dot-pending" title="Target 3 non raggiunto"></span>'
                            elif target_raggiunti == 2:
                                dots_html = '<span class="target-dot target-dot-achieved" title="Target 1 raggiunto"></span><span class="target-dot target-dot-achieved" title="Target 2 raggiunto"></span><span class="target-dot target-dot-pending" title="Target 3 non raggiunto"></span>'
                            else:
                                dots_html = '<span class="target-dot target-dot-achieved" title="Target 1 raggiunto"></span><span class="target-dot target-dot-achieved" title="Target 2 raggiunto"></span><span class="target-dot target-dot-achieved" title="Target 3 raggiunto"></span>'
                            dots_display = f'{dots_html} <span class="target-tooltip">{target_raggiunti}/3 Target</span>'
                        else:
                            dots_display = '<span class="target-tooltip">N/D</span>'
                        trigger_by_fabio, motivo_by_fabio = verifica_by_fabio(ticker_obj.history(period='1y'), 50, ticker_obj) if not ticker_obj.history(period='1y').empty else (False, "")
                        by_fabio_indicator = '<span class="by-fabio-badge" title="Ingresso matematicamente validato: Fortezza + Grafico">🟢 BY FABIO</span>' if trigger_by_fabio else ''
                        pill_bg = "#089981" if (var_pct is not None and not math.isnan(var_pct) and var_pct > 0) else ("#F23645" if (var_pct is not None and not math.isnan(var_pct) and var_pct < 0) else "#363A45")
                        pill_txt = f"{var_symbol} {var_pct:+.2f}%" if (var_pct is not None and not math.isnan(var_pct)) else "N/D"
                        st.markdown(f"""<div style="background-color:#131722;border:1px solid #2A2E39;border-radius:8px;padding:0.85rem 1rem;margin-bottom:0.45rem;border-left:4px solid {border_color};"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.2rem;"><div><span style="font-size:1.35rem;color:#FFFFFF;font-weight:700;">{ticker}</span>{by_fabio_indicator}</div><span style="background-color:{pill_bg};color:#FFFFFF;font-family:'JetBrains Mono',monospace;font-size:0.82rem;font-weight:700;padding:3px 9px;border-radius:5px;">{pill_txt}</span></div><div style="font-size:0.78rem;color:#787B86;margin-bottom:0.55rem;border-bottom:1px solid #1E222D;padding-bottom:0.4rem;">{stato_pac} &nbsp;•&nbsp; PMC €{prezzo_medio:.2f}<br><span style='color:#D1D4DC;font-weight:600;'>In carico: {quantita:.4f} az. &nbsp;•&nbsp; Valore €{(pos.get('Valore_Attuale') or (prezzo_medio * quantita)):.2f}</span></div><div style="display:flex;justify-content:space-between;font-size:0.84rem;margin-bottom:0.22rem;"><span style="color:#787B86;">Prezzo Attuale</span><span style="font-family:'JetBrains Mono',monospace;color:#FFFFFF;font-weight:700;font-size:0.96rem;">€ {prezzo_display}</span></div><div style="display:flex;justify-content:space-between;font-size:0.84rem;margin-bottom:0.22rem;"><span style="color:#787B86;">P&L Totale</span><span style="font-family:'JetBrains Mono',monospace;color:{acqu_color};font-weight:600;">{acqu_symbol} {var_acquisto:+.1f}% | {netto_label}</span></div><div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:0.22rem;"><span style="color:#787B86;">Ultimo Segnale</span><span style="color:#D1D4DC;">{ultimo_segnale}</span></div><div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:0.4rem;"><span style="color:#787B86;">Trend</span><span style="color:#D1D4DC;">{trend}</span></div><div style="display:flex;justify-content:space-between;align-items:center;border-top:1px solid #1E222D;padding-top:0.4rem;font-size:0.78rem;"><span style="color:#787B86;">Target</span><div>{dots_display}</div></div></div>""", unsafe_allow_html=True)
                        with st.expander(f"🎯 Target e Stop Loss - {ticker}"):
                            if targets:
                                st.markdown(f"""
                                <div style="background-color: #131722; padding: 1rem; border-radius: 6px; border: 1px solid #2A2E39;">
                                    <h4 style="margin-top:0; color: #F59E0B;">🎯 TARGET DI PREZZO (Basati su resistenze grafiche):</h4>
                                    <p style="margin: 0.2rem 0;">• <strong>Target 1:</strong> € {targets['t1']} (Upside: +{targets['upside1']}% | Progresso: {targets['prog1']}%)</p>
                                    <p style="margin: 0.2rem 0;">• <strong>Target 2:</strong> € {targets['t2']} (Upside: +{targets['upside2']}% | Progresso: {targets['prog2']}%)</p>
                                    <p style="margin: 0.2rem 0;">• <strong>Target 3:</strong> € {targets['t3']} (Upside: +{targets['upside3']}% | Progresso: {targets['prog3']}%)</p>
                                    <hr style="border-color: #2A2E39; margin: 0.5rem 0;">
                                    <h4 style="margin-top:0; color: #F23645;">🛡️ STOP LOSS DINAMICO: € {targets['sl']} ({targets['sl_down']}% dal prezzo attuale)</h4>
                                    <ul style="font-size: 0.9rem; color: #D1D4DC; margin-bottom: 0;">
                                        <li>⚠️ Quando raggiungi Target 1 → sposta stop a € {prezzo_medio:.2f} (break-even)</li>
                                        <li>⚠️ Quando raggiungi Target 2 → sposta stop a € {targets['t1']}</li>
                                        <li>⚠️ Quando raggiungi Target 3 → sposta stop a € {targets['t2']}</li>
                                    </ul>
                                </div>
                                """, unsafe_allow_html=True)
                            else:
                                st.info("Dati insufficienti per calcolare i target.")

                        with st.expander(f"📋 Dettagli e Operazioni - {ticker}"):
                            st.markdown(f"<div style='background:#0B0E11;border:1px solid #2A2E39;border-radius:6px;padding:8px 10px;font-size:0.82rem;margin-bottom:6px;'><div style='display:flex;justify-content:space-between;'><span>Quantità: <b>{quantita:.4f}</b></span><span>Prezzo: <b>€ {prezzo_display}</b></span></div><div style='display:flex;justify-content:space-between;margin-top:4px;'><span>P&L: <b style='color:{acqu_color};'>{netto_label}</b></span><span>Var: <b style='color:{acqu_color};'>{var_acquisto:+.1f}%</b></span></div></div>", unsafe_allow_html=True)
                            st.caption(f"📅 Prossimi Utili: {earnings}")
                            st.markdown("---")
                            st.markdown("**➕ Aggiungi Quote**")
                            col_a1, col_a2 = st.columns(2)
                            with col_a1:
                                nuova_qta = st.number_input("Nuova Qta", min_value=0.0001, step=0.0001, key=f"qta_{ticker}_{idx_pos}")
                            with col_a2:
                                nuovo_prezzo_acq = st.number_input("Prezzo Acquisto €", min_value=0.01, step=0.01, key=f"prezzo_acq_{ticker}_{idx_pos}")
                            if st.button("✅ Conferma Aggiunta", key=f"add_{ticker}_{idx_pos}", use_container_width=True):
                                    if nuova_qta > 0 and nuovo_prezzo_acq > 0:
                                        vecchio_medio = pos['Prezzo_Medio']
                                        nuovo_medio = ((quantita * vecchio_medio) + (nuova_qta * nuovo_prezzo_acq)) / (quantita + nuova_qta)
                                        pos['Quantita'] = round(quantita + nuova_qta, 6)
                                        pos['Prezzo_Medio'] = round(nuovo_medio, 4)
                                        salva_json(PORTAFOGLIO_FILE, portafoglio)
                                        st.session_state.portafoglio = portafoglio
                                        registra_acquisto_storico(ticker, pos.get('Tipo', 'Spot'), nuova_qta, nuovo_prezzo_acq, nota="Aggiunta Quote")
                                        st.success(f"✅ Aggiunte {nuova_qta} quote di {ticker}. Nuovo medio: €{nuovo_medio:.4f}")
                                        st.rerun()
                            st.markdown("---")
                            st.markdown("**➖ Vendi Quote**")
                            modalita_vendita = st.radio(f"Modalità vendita {ticker}", ["📊 Percentuale (%)", "🔢 Quantità specifica"], horizontal=True, key=f"modalita_{ticker}_{idx_pos}")
                            qta_da_vendere = 0
                            if modalita_vendita == "📊 Percentuale (%)":
                                pct_vendita = st.slider("Percentuale da vendere", min_value=1.0, max_value=100.0, value=100.0, step=1.0, key=f"pct_{ticker}_{idx_pos}")
                                qta_da_vendere = quantita * (pct_vendita / 100.0)
                                st.info(f"📊 Venderai {pct_vendita:.0f}% = {qta_da_vendere:.6f} quote")
                            else:
                                qta_da_vendere = st.number_input(f"Quantità da vendere (max {quantita:.6f})", min_value=0.0001, max_value=quantita, step=0.0001, value=min(quantita, 1.0), key=f"qta_vend_{ticker}_{idx_pos}")
                            prezzo_vendita = st.number_input("Prezzo di vendita €", min_value=0.01, step=0.01, value=float(prezzo_eur) if prezzo_eur else 0.01, key=f"prezzo_vend_{ticker}_{idx_pos}")
                            if qta_da_vendere > 0 and prezzo_vendita > 0 and prezzo_medio > 0:
                                pnl_lordo_prev = ((prezzo_vendita - prezzo_medio) * qta_da_vendere) - 1.0
                                pnl_pct_prev = ((prezzo_vendita / prezzo_medio) - 1) * 100
                                minusvalenze_disp = carica_json(MINUSVALENZE_FILE)
                                oggi_str = datetime.now().strftime("%Y-%m-%d")
                                tasse_sim = 0
                                if pnl_lordo_prev > 0:
                                    residuo = pnl_lordo_prev
                                    for mv in sorted(minusvalenze_disp, key=lambda x: x.get('Scadenza', '9999-12-31')):
                                        if mv.get('Scadenza', '') >= oggi_str and mv.get('Importo', 0) > 0:
                                            usa = min(mv['Importo'], residuo)
                                            residuo -= usa
                                            if residuo <= 0:
                                                break
                                    tasse_sim = residuo * ALIQUOTA_TASSE
                                pnl_netto_prev = pnl_lordo_prev - tasse_sim
                                st.markdown(f"""
                                <div style="background-color: #131722; padding: 1rem; border-radius: 6px; margin: 1rem 0; border: 1px solid #2A2E39;">
                                    <div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">
                                        <div><div style="color: #787B86; font-size: 0.85rem;">P&L Lordo</div><div style="font-family: 'JetBrains Mono', monospace; color: {'#089981' if pnl_lordo_prev > 0 else '#F23645'}; font-size: 1.2rem; font-weight: 700;">€ {pnl_lordo_prev:+.2f} ({pnl_pct_prev:+.1f}%)</div></div>
                                        <div><div style="color: #787B86; font-size: 0.85rem;">Tasse stimate (26%)</div><div style="font-family: 'JetBrains Mono', monospace; color: #F23645; font-size: 1.2rem; font-weight: 700;">€ -{tasse_sim:.2f}</div></div>
                                        <div><div style="color: #787B86; font-size: 0.85rem;">Netto reale</div><div style="font-family: 'JetBrains Mono', monospace; color: {'#089981' if pnl_netto_prev > 0 else '#F23645'}; font-size: 1.2rem; font-weight: 700;">€ {pnl_netto_prev:+.2f}</div></div>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                                if st.button(f"🔴 Conferma Vendita {ticker}", key=f"vend_{ticker}_{idx_pos}", type="primary"):
                                    if qta_da_vendere <= quantita:
                                        risultato = registra_vendita(ticker, qta_da_vendere, prezzo_medio, prezzo_vendita)
                                        if risultato and 'regia_tracker' in globals() and hasattr(regia_tracker, 'salta_ticker_5gg'):
                                            regia_tracker.salta_ticker_5gg(ticker)
                                        if risultato:
                                            pos['Quantita'] = round(quantita - qta_da_vendere, 6)
                                            if pos['Quantita'] <= 0:
                                                portafoglio = [p for p in portafoglio if p['Ticker'] != ticker]
                                            st.session_state.portafoglio = portafoglio
                                            salva_json(PORTAFOGLIO_FILE, portafoglio)
                                            st.success(f"✅ Vendute {qta_da_vendere:.6f} quote di {ticker}. P&L Netto: €{risultato['pnl_netto']:+.2f}")
                                            st.rerun()
                            st.markdown("---")
                            if st.button(f"🗑️ Rimuovi {ticker} dal Portafoglio", key=f"remove_{ticker}_{idx_pos}"):
                                portafoglio = [p for p in portafoglio if p['Ticker'] != ticker]
                                st.session_state.portafoglio = portafoglio
                                salva_json(PORTAFOGLIO_FILE, portafoglio)
                                st.success(f"✅ {ticker} rimosso dal portafoglio")
                                st.rerun()

            st.markdown("---")

with tab_console:
    portafoglio = st.session_state.portafoglio or list()
    if not portafoglio:
        st.warning('⚠️ Portafoglio vuoto.')
    else:
        st.markdown("#### 🛠️ Strumenti Operativi & Gestione Capitale")
        _m2, _m3, _m4 = st.columns(3)
        with _m2:
            st.markdown('<div style="background-color:#131722;border:1px solid #2A2E39;border-top:3px solid #089981;border-radius:6px;padding:0.75rem;margin-bottom:0.4rem;"><div style="font-weight:700;color:#FFFFFF;font-size:0.92rem;">🛡️ Ottimizzazione PODC</div><div style="color:#787B86;font-size:0.76rem;margin-top:2px;">Libera gain e media loss</div></div>', unsafe_allow_html=True)
            if st.button("Avvia Protocollo PODC", type="primary", key="btn_podc_card"):
                with st.spinner("Analisi PODC..."):
                    semaforo_podc = calcola_semaforo_mercato()
                    st.session_state.risultato_podc = avvia_podc(portafoglio, eurusd_rate, catalizzatori_input, semaforo_podc['stato'])
        with _m3:
            st.markdown('<div style="background-color:#131722;border:1px solid #2A2E39;border-top:3px solid #F59E0B;border-radius:6px;padding:0.75rem;margin-bottom:0.4rem;"><div style="font-weight:700;color:#FFFFFF;font-size:0.92rem;">📊 Rotazione Mensile</div><div style="color:#787B86;font-size:0.76rem;margin-top:2px;">Vendite, hold e nuovi setup</div></div>', unsafe_allow_html=True)
            if st.button("Genera Piano Rotazione", type="secondary", key="btn_rib_card"):
                with st.spinner("Analisi rotazione..."):
                    semaforo = calcola_semaforo_mercato()
                    catalizzatori = parse_catalizzatori(catalizzatori_input)
                    esclusioni_list = [t.strip().upper() for t in esclusioni_input.split(",") if t.strip()]
                    st.session_state.piano_ribilanciamento = genera_piano_ribilanciamento(portafoglio, tickers, semaforo, catalizzatori, esclusioni_list, eurusd_rate)
        with _m4:
            st.markdown('<div style="background-color:#131722;border:1px solid #2A2E39;border-top:3px solid #8B5CF6;border-radius:6px;padding:0.75rem;margin-bottom:0.4rem;"><div style="font-weight:700;color:#FFFFFF;font-size:0.92rem;">💰 Allocazione Dinamica</div><div style="color:#787B86;font-size:0.76rem;margin-top:2px;">Ripartisci liquidità disponibile</div></div>', unsafe_allow_html=True)
            if st.button("Genera Allocazione", type="secondary", key="btn_all_card"):
                with st.spinner("Calcolo allocazione..."):
                    liquidita_reale = calcola_liquidita_totale()
                    liquidita_totale_alloc = liquidita_reale + 500
                    st.session_state.piano_allocazione = genera_piano_allocazione(portafoglio, liquidita_totale_alloc, eurusd_rate, tickers)
                    st.session_state.liquidita_totale_alloc = liquidita_totale_alloc

        if st.session_state.get('risultato_podc'):
            res = st.session_state.risultato_podc
            if st.button("✖️ Nascondi Analisi PODC"):
                st.session_state.risultato_podc = None
                st.rerun()
            st.markdown("---")
            st.markdown("#### 🛡️ PROTOCOLLO DI OTTIMIZZAZIONE (PODC)")
            if not res['suggestions'] and not res['gain_analyzed']:
                st.info("✅ Nessuna ottimizzazione necessaria al momento. Il portafoglio è bilanciato.")
            else:
                _visti_sell, _visti_buy = set(), set()
                for sug in res['suggestions']:
                    if sug.get('sell_ticker') in _visti_sell or sug.get('buy_ticker') in _visti_buy:
                        continue
                    _visti_sell.add(sug.get('sell_ticker'))
                    _visti_buy.add(sug.get('buy_ticker'))
                    st.markdown(f"""
                    <div style="background-color: #131722; padding: 1rem; border-radius: 8px; border: 1px solid #2A2E39; border-left: 4px solid #089981; margin-bottom: 1rem;">
                        <p style="margin: 0.2rem 0;"><strong>1. LIBERA CAPITALE:</strong> Vendi {sug['sell_pct']}% di <span style="color: #089981;">{sug['sell_ticker']}</span> → Libera circa <strong>€{sug['capital_freed']:.2f}</strong>.</p>
                        <p style="margin: 0.2rem 0;"><strong>2. MEDIA STRATEGICA:</strong> Usa €{sug['capital_freed']:.2f} per comprare <span style="color: #2962FF;">{sug['buy_ticker']}</span>.</p>
                        <p style="margin: 0.2rem 0;"><strong>3. RISULTATO:</strong> Il prezzo medio di {sug['buy_ticker']} scende da €{sug['old_avg']:.2f} a <strong>€{sug['new_avg']:.2f}</strong>. Il tuo PnL passa da {sug['old_pnl']:.1f}% a <strong style="color: #089981;">{sug['new_pnl']:.1f}%</strong>.</p>
                    </div>
                    """, unsafe_allow_html=True)
            st.markdown("---")
            st.markdown("#### 📊 RIEPILOGO ANALISI PODC:")
            st.markdown(f"**✅ Titoli in Gain analizzati:** {len(res['gain_analyzed'])}")
            for g in res['gain_analyzed']:
                st.markdown(f"- **{g['ticker']}**: {g['reason']}")
            st.markdown(f"<br>**❌ Titoli in Loss NON candidati alla media:** {len(res['loss_rejected'])}", unsafe_allow_html=True)
            for r_item in res['loss_rejected']:
                st.markdown(f"- **{r_item['ticker']}**: {r_item['reason']}")
            st.markdown(f"<br>**🎯 Candidati validi per media:** {len(res['loss_candidates'])}", unsafe_allow_html=True)
            for c in res['loss_candidates']:
                hypothetical_new_avg = ((c['qty'] * c['prezzo_medio']) + res['total_capital_freed']) / (c['qty'] + (res['total_capital_freed'] / c['prezzo_attuale'])) if res['total_capital_freed'] > 0 else c['prezzo_medio']
                st.markdown(f"- **{c['ticker']}**: S-Score {c['s_score']}, Fase {c['fase']}, RSI {c['rsi']:.1f}, Prezzo medio attuale €{c['prezzo_medio']:.2f}, Nuovo prezzo medio ipotetico €{hypothetical_new_avg:.2f}")
            liquidita_reale = calcola_liquidita_totale()
            capitale_proposto = res['total_capital_freed']
            totale_disponibile = liquidita_reale + capitale_proposto
            st.markdown("---")
            st.markdown("#### 💰 DISPONIBILITÀ CAPITALE")
            col_liq1, col_liq2, col_liq3 = st.columns(3)
            with col_liq1:
                st.metric("💵 Liquidità reale in cassa", f"€ {liquidita_reale:,.2f}", help="Soldi già incassati dalle vendite passate (netto tasse)")
            with col_liq2:
                st.metric("🎯 Capitale liberabile proposto", f"€ {capitale_proposto:,.2f}", help="Soldi che il PODC suggerisce di liberare ora")
            with col_liq3:
                st.metric("🏦 TOTALE DISPONIBILE", f"€ {totale_disponibile:,.2f}", help="Liquidità reale + Capitale liberabile = Totale per nuovi acquisti")

        st.markdown("---")
        if st.session_state.get('piano_ribilanciamento'):
            if st.button("✖️ Nascondi Piano"):
                st.session_state.piano_ribilanciamento = None
                st.rerun()
            piano = st.session_state.piano_ribilanciamento
            st.markdown("---")
            st.markdown(f"**Stato Mercato:** {piano['semaforo'].upper()}")
            st.markdown("---")
            if piano['vendite']:
                st.subheader("🔴 Da Vendere / Valutare Vendita")
                for item in piano['vendite']:
                    st.markdown(f"""
                    <div class="signal-box signal-red">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div><strong>{item['ticker']}</strong> - Score: {item['score']}/100<br><small>Fase: {item['fase']} | P&L: {item['pnl_pct']:+.1f}%</small><br><small style="color: #fca5a5;">{item.get('messaggio', '')}</small></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("✅ Nessun titolo da vendere")
            if piano['monitor']:
                st.subheader("🟡 Da Monitorare / Accumulo")
                for item in piano['monitor']:
                    st.markdown(f"""
                    <div class="signal-box signal-yellow">
                        <strong>{item['ticker']}</strong> - Score: {item['score']}/100<br><small>Fase: {item['fase']}</small><br><small style="color: #fcd34d;">{item.get('messaggio', '')}</small>
                    </div>
                    """, unsafe_allow_html=True)
            if piano['acquisti']:
                st.subheader("🟢 Da Comprare (Score > 75 o Override Ipervenduto)")
                for item in piano['acquisti']:
                    box_class = "signal-yellow" if item['stato_mercato'] == 'sospeso' else "signal-green"
                    badge = item.get('badge', '')
                    st.markdown(f"""
                    <div class="signal-box {box_class}">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div><strong>{badge} {item['ticker']}</strong> - Score: {item['score']}/100<br><small>Fase: {item['fase']} | Prezzo: €{item['prezzo_eur']:.2f}</small><br><small style="color: #fcd34d;">{item.get('messaggio', '')}</small></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            st.markdown("---")
            st.subheader("💡 AZIONE CONSIGLIATA DAL SISTEMA")
            consigli = list()
            if piano['vendite']:
                tickers_vendita = ", ".join([v['ticker'] for v in piano['vendite'][:3]])
                consigli.append(f"1. **Ottimizza:** Valuta la vendita di {tickers_vendita} per liberare liquidità e generare minusvalenze fiscali compensabili.")
            accumuli = [m['ticker'] for m in piano['monitor'] if "Rimbalzo" in m.get('messaggio', '')]
            if accumuli:
                consigli.append(f"2. **Tieni d'occhio:** {', '.join(accumuli)} sono in fase di accumulo e pronti a ripartire. Non vendere.")
            if piano['semaforo'] == 'rosso':
                consigli.append("3. **Mercato:** Il mercato è in fase difensiva. Gli acquisti di nuovi titoli sono sospesi. Ricontrolla tra 7 giorni o quando il VIX scende sotto 25.")
            elif piano['acquisti']:
                attivi = [a['ticker'] for a in piano['acquisti'] if a['stato_mercato'] == 'attivo']
                if attivi:
                    consigli.append(f"3. **Nuove Entrate:** {', '.join(attivi)} mostrano setup validi. Valuta l'ingresso con nuova liquidità.")
            if not consigli:
                consigli.append("Mantieni la rotta. Il portafoglio è ben bilanciato rispetto alle condizioni attuali di mercato.")
            for c in consigli:
                st.info(c)
        st.markdown("---")
        if st.session_state.get('piano_allocazione'):
            piano = st.session_state.piano_allocazione
            liquidita_totale_alloc = st.session_state.get('liquidita_totale_alloc', 0)
            st.markdown(f"**Liquidità Totale Disponibile:** € {liquidita_totale_alloc:,.2f}")
            st.markdown(f"**BY FABIO attivi (portafoglio):** {piano['by_fabio_count']} | **Nuove Entrate BY FABIO:** {piano.get('nuove_entrate_count', 0)} | **PAC ottimali:** {piano['pac_ottimali_count']} | **Breakout imminenti:** {piano['watchlist_breakout_count']} | **Proposte attive:** {piano.get('proposte_count', 0)}")
            if piano['allocazioni']:
                df_alloc = pd.DataFrame(piano['allocazioni'])
                priorita_map = {1: '🥇 PRIORITÀ 1 - BY FABIO', 2: '🥈 PRIORITÀ 2 - PAC EXTRA', 3: '🥉 PRIORITÀ 3 - BREAKOUT'}
                df_alloc['Priorità'] = df_alloc['priorita'].map(priorita_map)
                tipo_map = {'nuova_entrata': '🟢 BY FABIO (Nuova Entrata)', 'pyramiding': '🟢 BY FABIO (Pyramiding)', 'pac_extra': '📈 PAC Extra', 'breakout': '⚡ Breakout'}
                df_alloc['Tipo'] = df_alloc['tipo'].map(tipo_map).fillna(df_alloc['tipo'])
                df_alloc['Proposto'] = df_alloc['proposto'].apply(lambda x: '✅ SÌ' if x else '⚠️ NO')
                df_display = df_alloc[['ticker', 'importo', 'azioni', 'motivazione', 'Priorità', 'Tipo', 'Proposto']].copy()
                df_display.columns = ['Ticker', 'Importo (€)', 'Azioni stimate', 'Motivazione', 'Priorità', 'Tipo', 'Proposto']
                st.dataframe(df_display, use_container_width=True, height=600)
                st.markdown("""
                <div style="background-color: #131722; padding: 1rem; border-radius: 8px; margin-top: 1rem; border: 1px solid #2A2E39; font-size: 13px;">
                    <h4 style="margin-top: 0; color: #F59E0B;">📋 LEGENDA PRIORITÀ:</h4>
                    <p style="margin: 0.3rem 0;"><strong>🥇 PRIORITÀ 1 - BY FABIO (45% capitale):</strong> Segnale d'élite. S-Score ≥ 70 + geometria perfetta (Breakout su SMA50 con volume > 1.3x OPPURE Pullback su SMA200 con distanza 0-3% e RSI 40-60).</p>
                    <p style="margin: 0.3rem 0;"><strong>🥈 PRIORITÀ 2 - PAC EXTRA (30% capitale):</strong> Rinforzo strategico su PAC esistenti in Fase 2 o Correzione sana. Non è il PAC settimanale automatico.</p>
                    <p style="margin: 0.3rem 0;"><strong>🥉 PRIORITÀ 3 - BREAKOUT (20% capitale):</strong> Titolo sotto SMA50 di oltre 5%, RSI in risalita (30-50), volume > 1.2x. Si prepara a rompere al rialzo.</p>
                    <p style="margin: 0.3rem 0; color: #FBBF24;"><strong>⚠️ NOTA:</strong> Solo i primi 3 titoli con importo ≥ €50 sono contrassegnati come "Proposto ✅ SÌ". Gli altri sono candidati ma non prioritari.</p>
                </div>
                """, unsafe_allow_html=True)
            st.metric("💵 Liquidità Residua", f"€ {piano['liquidita_residua']:,.2f}")
            if st.button("✖️ Nascondi Piano di Allocazione"):
                st.session_state.piano_allocazione = None
                st.session_state.liquidita_totale_alloc = None
                st.rerun()

        st.markdown("---")

        with st.expander("⚙️ Modifica Portafoglio (Aggiungi/Rimuovi Titoli)"):
            col_add1, col_add2, col_add3, col_add4 = st.columns([2, 1, 1, 1])
            with col_add1:
                new_ticker = st.text_input("Ticker (es. AAPL)").upper()
            with col_add2:
                new_tipo = st.selectbox("Tipo", ["Spot", "PAC"])
            with col_add3:
                new_qta = st.number_input("Quantità", min_value=0.0001, step=0.0001)
            with col_add4:
                new_medio = st.number_input("Prezzo Medio €", min_value=0.01, step=0.01)
            if st.button("➕ Aggiungi al Portafoglio"):
                _tk_clean = str(new_ticker).strip().upper()
                if _tk_clean and float(new_qta) > 0 and float(new_medio) > 0:
                    _trovato_m = False
                    # Fonde sempre sul ticker esistente (anche se PAC vs Spot) per evitare schede duplicate
                    for _item_m in st.session_state.portafoglio:
                        if str(_item_m.get("Ticker", "")).strip().upper() == _tk_clean:
                            _q_old = float(_item_m.get("Quantita", 0) or 0)
                            _pmc_old = float(_item_m.get("Prezzo_Medio", 0) or 0)
                            _q_new = round(_q_old + float(new_qta), 6)
                            _pmc_new = round(((_q_old * _pmc_old) + (float(new_qta) * float(new_medio))) / _q_new, 4)
                            _item_m["Quantita"] = _q_new
                            _item_m["Prezzo_Medio"] = _pmc_new
                            _item_m["Valore_Carico"] = round(_q_new * _pmc_new, 2)
                            _pe_es = float(_item_m.get("Prezzo_Attuale_EUR") or 0)
                            if _pe_es > 0:
                                _item_m["Valore_Attuale"] = round(_q_new * _pe_es, 2)
                                _item_m["PnL_EUR"] = round(_item_m["Valore_Attuale"] - _item_m["Valore_Carico"], 2)
                                _item_m["PnL_%"] = round(((_item_m["Valore_Attuale"] / _item_m["Valore_Carico"]) - 1) * 100, 2) if _item_m["Valore_Carico"] > 0 else 0.0
                            _trovato_m = True
                            salva_ultimo_agg_prezzi(); salva_json(PORTAFOGLIO_FILE, st.session_state.portafoglio)
                            registra_acquisto_storico(_tk_clean, str(_item_m.get("Tipo", new_tipo)), float(new_qta), float(new_medio), nota="Mediazione PMC"); st.success(f"✅ {_tk_clean} mediato! Totale: {_q_new:.4f} az. | Nuovo PMC: € {_pmc_new:.2f}")
                            break
                    if not _trovato_m:
                        _q_n = round(float(new_qta), 6)
                        _pm_n = round(float(new_medio), 4)
                        st.session_state.portafoglio.append({
                            "Ticker": _tk_clean,
                            "Tipo": str(new_tipo),
                            "Quantita": _q_n,
                            "Prezzo_Medio": _pm_n,
                            "Valore_Carico": round(_q_n * _pm_n, 2),
                            "Prezzo_Attuale_EUR": _pm_n,
                            "Valore_Attuale": round(_q_n * _pm_n, 2),
                            "PnL_EUR": 0.0,
                            "PnL_%": 0.0,
                            "Data_Acquisto": datetime.now().strftime("%Y-%m-%d")
                        })
                        salva_ultimo_agg_prezzi(); salva_json(PORTAFOGLIO_FILE, st.session_state.portafoglio)
                        registra_acquisto_storico(_tk_clean, str(new_tipo), _q_n, _pm_n, nota="Nuovo Acquisto"); st.success(f"✅ {_tk_clean} aggiunto al portafoglio ({_q_n:.4f} az. @ € {_pm_n:.2f})!")
            st.markdown("---")
            st.write("Rimuovi un titolo:")
            port_att = st.session_state.portafoglio or carica_json(PORTAFOGLIO_FILE) or PORTAFOGLIO_INIZIALE
            if port_att:
                ticker_da_rimuovere = st.selectbox("Seleziona Ticker da rimuovere", [p['Ticker'] for p in port_att])
                if st.button("🗑️ Rimuovi"):
                    port_att = [p for p in port_att if p['Ticker'] != ticker_da_rimuovere]
                    st.session_state.portafoglio = port_att
                    salva_json(PORTAFOGLIO_FILE, port_att)
                    st.success(f"{ticker_da_rimuovere} rimosso!")
                    st.rerun()
        st.markdown("---")


with tab_scanner:
    if st.session_state.get('semaforo_mercato') is None:
        st.session_state.semaforo_mercato = calcola_semaforo_mercato()
    semaforo = st.session_state.semaforo_mercato
    if semaforo['stato'] == 'verde':
        st.markdown(f'<div class="semaforo-box semaforo-verde"><h2 style="margin:0; color:white;">{semaforo["messaggio"]}</h2><p style="margin:0.5rem 0 0 0; color:#d1fae5;">SPY: ${semaforo["spy_prezzo"]} | SMA10: ${semaforo["spy_sma10"]} | VIX: {semaforo["vix"]}</p></div>', unsafe_allow_html=True)
    elif semaforo['stato'] == 'rosso':
        st.markdown(f'<div class="semaforo-box semaforo-rosso"><h2 style="margin:0; color:white;">{semaforo["messaggio"]}</h2><p style="margin:0.5rem 0 0 0; color:#fee2e2;">SPY: ${semaforo["spy_prezzo"]} | SMA10: ${semaforo["spy_sma10"]} | VIX: {semaforo["vix"]}</p></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="semaforo-box semaforo-giallo"><h2 style="margin:0; color:white;">{semaforo["messaggio"]}</h2><p style="margin:0.5rem 0 0 0; color:#fef3c7;">SPY: ${semaforo["spy_prezzo"]} | SMA10: ${semaforo["spy_sma10"]} | VIX: {semaforo["vix"]}</p></div>', unsafe_allow_html=True)
    st.markdown("---")
    if st.button("🔄 Aggiorna Semaforo"):
        st.session_state.semaforo_mercato = calcola_semaforo_mercato()
        st.rerun()
    st.markdown("---")
    if st.session_state.dashboard_stats:
        stats = st.session_state.dashboard_stats
        col_d1, col_d2, col_d3 = st.columns(3)
        col_d1.metric("🟢 Segnali BY", stats['by_count'], ", ".join(stats['by_tickers']) if stats['by_tickers'] else "Nessuno")
        col_d2.metric("🟡 In Accumulo", stats['hold_count'], ", ".join(stats['hold_tickers']) if stats['hold_tickers'] else "Nessuno")
        col_d3.metric("🔴 Segnali SELL", stats['sell_count'], ", ".join(stats['sell_tickers']) if stats['sell_tickers'] else "Nessuno")
        if stats['earnings_warnings']:
            st.warning(f"⚠️ **Attenzione Utili**: {', '.join(stats['earnings_warnings'])}")
        if stats.get('by_fabio_tickers'):
            st.markdown("---")
            st.subheader("🚨 SEGNALI BY FABIO RILEVATI (Ingresso Matematico)")
            st.markdown(f"""
            <div class="signal-box signal-fabio">
                <h3 style="margin: 0;">🟢 {len(stats['by_fabio_tickers'])} Titoli con segnale BY FABIO</h3>
                <p style="margin: 0.8rem 0 0 0; font-size: 1.3rem; font-weight: bold;"><strong>{', '.join(stats['by_fabio_tickers'])}</strong></p>
                <p style="margin: 0.5rem 0 0 0; font-size: 1.05rem; opacity: 0.9;">✅ Ingresso matematicamente validato: Fortezza (S-Score ≥ 70) + Grafico (Breakout/Pullback)</p>
                <p style="margin: 0.3rem 0 0 0; font-size: 0.95rem; color: #F59E0B;">🎯 Priorità 1 - Allocazione 45% del capitale disponibile</p>
            </div>
            """, unsafe_allow_html=True)
        if stats.get('error_tickers'):
            st.markdown("---")
            st.subheader("❌ Titoli con Errori di Scansione")
            for err in stats['error_tickers']:
                st.warning(f"⚠️ {err}")
        if stats.get('smci_tickers'):
            st.markdown("---")
            st.subheader("🎯 TITOLI TIPOLOGIA 'SMCI' RILEVATI (Pattern Accumulo Fortezza)")
            st.markdown(f"""
            <div class="signal-box signal-blue">
                <h3 style="margin: 0; color: #dbeafe;">🧬 {len(stats['smci_tickers'])} Titoli con geometria SMCI</h3>
                <p style="margin: 0.5rem 0 0 0; font-size: 1.1rem; font-weight: bold; color: #dbeafe;">{', '.join(stats['smci_tickers'])}</p>
                <p style="margin: 0.3rem 0 0 0; font-size: 0.9rem; opacity: 0.9;">S-Score ≥ 75 | FASE 1 | Prezzo &lt; SMA50 | RSI 35-50. Valutazione manuale del Capitano.</p>
            </div>
            """, unsafe_allow_html=True)
        if st.session_state.get('extended_hours_alerts'):
            st.markdown("---")
            st.subheader("⚡ ALERT MOVIMENTI ANOMALI (Fuori Orario)")
            col_a1, col_a2 = st.columns(2)
            for idx, alert in enumerate(st.session_state.extended_hours_alerts):
                box_class = "signal-green" if alert['variazione'] > 0 else "signal-red"
                html_block = f"""<div class="signal-box {box_class}"><h4 style="margin:0">{alert['colore']} {alert['ticker']} - {alert['sessione']}</h4><p style="margin:0.5rem 0">Variazione: <strong>{alert['variazione']:+.2f}%</strong> | Prezzo: €{alert['prezzo_eur']:.2f}</p></div>"""
                if idx % 2 == 0:
                    col_a1.markdown(html_block, unsafe_allow_html=True)
                else:
                    col_a2.markdown(html_block, unsafe_allow_html=True)
        if st.session_state.pyramiding_alerts:
            st.markdown("---")
            st.subheader("🟢 Opportunità Pyramiding")
            for alert in st.session_state.pyramiding_alerts:
                pyr = alert['pyramiding']
                st.markdown(f"""<div class="signal-box signal-green"><h4 style="margin:0">{alert['ticker']} ({alert['tipo']})</h4><p style="margin:0.5rem 0">💶 Capitale: ~{pyr['capitale']}€ | 📊 Azioni: {pyr['azioni']} | 🛑 Stop: {pyr['stop_loss']}€ | 🎯 Target: {pyr['target']}€</p></div>""", unsafe_allow_html=True)
        if st.session_state.get('zona_interesse_alerts'):
            st.markdown("---")
            st.subheader("🟡 Zona di Interesse (Supporto SMA 200)")
            for alert in st.session_state.zona_interesse_alerts:
                st.markdown(f"""<div class="signal-box signal-yellow"><h4 style="margin:0">🟡 {alert['ticker']} (S-Score: {alert['s_score']})</h4><p style="margin:0.5rem 0">💶 Prezzo: {alert['prezzo_attuale_eur']}€ | 🛡️ SMA 200: {alert['sma200_eur']}€ (Distanza: {alert['distanza_pct']}%)</p></div>""", unsafe_allow_html=True)
        if st.session_state.get('take_profit_alerts'):
            st.markdown("---")
            st.subheader("🎯 Allerta Take Profit")
            for alert in st.session_state.take_profit_alerts:
                st.markdown(f"""<div class="signal-box signal-red"><h4 style="margin:0">🔴 {alert['ticker']} ({alert['tipo']}) - RSI: {alert['rsi']}</h4><p style="margin:0.5rem 0">💶 Prezzo: {alert['prezzo_attuale_eur']}€ | 📈 Gain: <span style="color:#089981;font-weight:bold">+{alert['gain_pct']}%</span></p></div>""", unsafe_allow_html=True)
        st.markdown("---")
        st.subheader("⚠️ Watchlist Breakout Imminente")
        st.markdown("### 🚀 Radar IGNITION — Inizio Salita (80 Titoli)")
        _c_ig1, _c_ig2 = st.columns([2.5, 1])
        with _c_ig1:
            st.caption("Scansiona i migliori 80 titoli USA + Watchlist alla ricerca di Squeeze Bollinger, riconquista SMA 20, supporto VPOC Balene e volumi >= 1.35x.")
        with _c_ig2:
            _avvia_ig = st.button("🚀 Scansiona Radar IGNITION", type="primary", key="btn_run_ignition_80", use_container_width=True)
        if _avvia_ig:
            _lista_ig = sorted(list(set(IGNITION_UNIVERSE if 'IGNITION_UNIVERSE' in globals() else []) | set([x.strip().upper() for x in st.session_state.get('tickers_input', '').split(',') if x.strip()])))
            _trovati_ig = []
            _pre_ig = []
            _pb_ig = st.progress(0, text="Scansione Radar IGNITION in corso...")
            for _idx_i, _tk_i in enumerate(_lista_ig):
                _pb_ig.progress((_idx_i + 1) / max(1, len(_lista_ig)), text=f"Analisi IGNITION: {_tk_i} ({_idx_i+1}/{len(_lista_ig)})")
                try:
                    _df_i = yf.Ticker(_tk_i).history(period="6mo", interval="1d").dropna(subset=["Close", "Volume"])
                    if len(_df_i) >= 25:
                        _c = _df_i["Close"]
                        _v = _df_i["Volume"]
                        _p_now = float(_c.iloc[-1])
                        _p_prev = float(_c.iloc[-2])
                        _sma20 = _c.rolling(20).mean()
                        _std20 = _c.rolling(20).std()
                        _s20_now = float(_sma20.iloc[-1])
                        _s20_prev = float(_sma20.iloc[-2])
                        _bb_w = ((_sma20 + 2 * _std20) - (_sma20 - 2 * _std20)) / _sma20
                        _squeeze = float(_bb_w.iloc[-1]) <= float(_bb_w.tail(60).quantile(0.30))
                        _vol_r = float(_v.iloc[-1]) / max(1.0, float(_v.tail(21).iloc[:-1].mean()))
                        _delta = _c.diff()
                        _gain = _delta.clip(lower=0).rolling(14).mean()
                        _loss = (-_delta.clip(upper=0)).rolling(14).mean()
                        _rs = _gain / _loss.replace(0, np.nan)
                        _rsi_i = float((100 - (100 / (1 + _rs))).iloc[-1])
                        _riconq = (_p_now > _s20_now) and (_p_prev <= _s20_prev * 1.01) and (_p_now > _p_prev)
                        _vp_i, _wh_i = calcola_livello_balene(_df_i) if "calcola_livello_balene" in globals() else (None, "")
                        _ins_i = " | 🕵️ INSIDER" if ("get_giorni_insider_rimanenti" in globals() and get_giorni_insider_rimanenti(_tk_i) != "-") else ""
                        _dist_s20 = ((_p_now - _s20_now) / _s20_now) * 100
                        if (_riconq or (_squeeze and _p_now > _s20_now and _p_now > _p_prev)) and _vol_r >= 1.20 and 40 <= _rsi_i <= 68:
                            _tag_sq = "🔥 Squeeze + " if _squeeze else ""
                            _det_i = f"{_tag_sq}Riconquista SMA20 (${_s20_now:.2f}) | Vol {_vol_r:.2f}x | RSI {_rsi_i:.0f} {_wh_i}{_ins_i}".strip()
                            _trovati_ig.append({"Ticker": _tk_i, "Prezzo $": f"${_p_now:.2f}", "Stato": "🚀 IGNITION ATTIVO", "Dettagli & Conferme": _det_i})
                        elif (-2.5 <= _dist_s20 <= 2.5) and 42 <= _rsi_i <= 62 and (_squeeze or _vol_r >= 1.05):
                            _sc_pre = (20 if _squeeze else 0) + (_vol_r * 10) + (5 if _ins_i else 0)
                            _tag_sq2 = "🔥 Squeeze | " if _squeeze else ""
                            _det_p = f"{_tag_sq2}Dist. SMA20: {_dist_s20:+.1f}% (${_s20_now:.2f}) | Vol {_vol_r:.2f}x | RSI {_rsi_i:.0f} {_wh_i}{_ins_i}".strip()
                            _pre_ig.append((_sc_pre, {"Ticker": _tk_i, "Prezzo $": f"${_p_now:.2f}", "Stato": "⏳ PRE-IGNITION", "Dettagli & Conferme": _det_p}))
                except Exception:
                    pass
            _pb_ig.empty()
            _pre_ig.sort(key=lambda x: x[0], reverse=True)
            st.session_state["risultati_radar_ignition_80"] = _trovati_ig + [x[1] for x in _pre_ig[:6]]
        if "risultati_radar_ignition_80" in st.session_state:
            _res_ig = st.session_state["risultati_radar_ignition_80"]
            if _res_ig:
                st.success(f"🔥 Trovati **{len(_res_ig)}** titoli in fase di partenza (IGNITION):")
                st.dataframe(pd.DataFrame(_res_ig), use_container_width=True, hide_index=True)
            else:
                st.info("Nessun titolo in partenza IGNITION rilevato in questo momento sugli 80 titoli.")

        port_scan_ref = st.session_state.portafoglio or list()
        breakout_tickers = trova_breakout_imminenti(port_scan_ref, eurusd_rate)
        if breakout_tickers:
            st.info(f"🎯 Trovati {len(breakout_tickers)} titoli con breakout imminente")
            for bt in breakout_tickers:
                st.markdown(f"""
                <div class="breakout-card">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div><strong style="font-size: 1.2rem;">🟡 {bt['ticker']}</strong><span style="margin-left: 10px; color: #F59E0B;">Breakout Imminente</span></div>
                        <div style="text-align: right;">
                            <div style="font-size: 0.9rem; color: #FEF3C7;">Prezzo: €{bt['prezzo']:.2f} | SMA50: €{bt['sma50']:.2f}</div>
                            <div style="font-size: 0.9rem; color: #FEF3C7;">Distanza: -{bt['distanza_sma50']}% | RSI: {bt['rsi']:.0f} (↑ da {bt['rsi_5gg_fa']:.0f}) | Vol: {bt['volume_ratio']:.2f}x</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Nessun titolo con breakout imminente al momento.")
        if st.session_state.scansione_completata:
            st.markdown("---")
            tab_f, tab_c, tab_m, tab_p = st.tabs(["🏰 Fortezza Reale", "🎪 Arena Cavalli Pazzi", "👁️ Da Monitorare (HOLD)", "🤖 Setup Palantir"])
            with tab_f:
                st.subheader("Asset Strutturali (S-Score > 60, Fase 2)")
                if st.session_state.df_fortezza is not None:
                    st.dataframe(uniforma_tabella_scanner(st.session_state.df_fortezza), use_container_width=True, height=400)
                else:
                    st.info("Nessun titolo in Fortezza.")
            with tab_c:
                st.subheader("Arena Speculativa (S-Score 40-60, Vol > +60%, Fase 1/2, Figura Z)")
                if st.session_state.df_cavalli is not None:
                    st.dataframe(uniforma_tabella_scanner(st.session_state.df_cavalli), use_container_width=True, height=400)
                else:
                    st.info("Nessun titolo ha superato i 3 filtri rigidi.")
            with tab_m:
                st.subheader("👁️ Watchlist Permanente - Titoli da Monitorare")
                if st.session_state.df_monitor is not None:
                    st.dataframe(uniforma_tabella_scanner(st.session_state.df_monitor), use_container_width=True, height=400)
                else:
                    st.info("La watchlist è vuota.")
            with tab_p:
                st.subheader("🤖 Setup Palantir (Growth Esplosiva + Sconto Irrazionale)")
                st.markdown("*Filtri: S-Score ≥ 75, Revenue Growth ≥ 20%, PEG < 1.5, RSI < 45, Distanza SMA 200 ≤ 5%*")
                if st.session_state.df_palantir is not None and not st.session_state.df_palantir.empty:
                    st.dataframe(uniforma_tabella_scanner(st.session_state.df_palantir), use_container_width=True, height=400)
                else:
                    st.info("Nessun titolo soddisfa attualmente i rigorosi criteri del Setup Palantir. Avvia una scansione.")
    else:
        st.info("👆 Apri la barra laterale sinistra (freccia `>` in alto a sinistra) e clicca **🔴 AVVIA SCANSIONE** per caricare tutti i segnali e le tabelle.")

with tab_analisi:
    st.subheader("🔍 Analisi Singola & Grafico")
    col_in1, col_in2 = st.columns([2, 1])
    with col_in1:
        st.markdown("**📊 Indici USA (Solo Grafico & Trend):**")
        ic1, ic2, ic3, ic4 = st.columns(4)
        if ic1.button("📈 S&P 500 (SPY)", use_container_width=True, key="btn_idx_spy"):
            st.session_state["txt_analisi_singola_tk"] = "SPY"
        if ic2.button("💻 Nasdaq 100 (QQQ)", use_container_width=True, key="btn_idx_qqq"):
            st.session_state["txt_analisi_singola_tk"] = "QQQ"
        if ic3.button("🏭 Dow Jones (DIA)", use_container_width=True, key="btn_idx_dia"):
            st.session_state["txt_analisi_singola_tk"] = "DIA"
        if ic4.button("🚀 Russell 2000 (IWM)", use_container_width=True, key="btn_idx_iwm"):
            st.session_state["txt_analisi_singola_tk"] = "IWM"
        if "txt_analisi_singola_tk" not in st.session_state:
            _def_an_tk = st.session_state.get("sb_quick_ticker", "SOFI")
            st.session_state["txt_analisi_singola_tk"] = _def_an_tk if _def_an_tk != "Portafoglio vuoto" else "SOFI"
        ticker_input = st.text_input("Inserisci Ticker:", key="txt_analisi_singola_tk")
        if ticker_input.strip():
            c_wl_1, c_wl_2 = st.columns(2)
            with c_wl_1:
                if 'regia_tracker' in globals() and hasattr(regia_tracker, 'render_stella_watchlist'):
                    regia_tracker.render_stella_watchlist(ticker_input.strip().upper(), 'singola_top')
            with c_wl_2:
                if st.button("🩺 Check 3 Regole", key="btn_check_singola_3reg", use_container_width=True):
                    st.session_state["_run_check_singola"] = ticker_input.strip().upper()
            if st.session_state.get("_run_check_singola") == ticker_input.strip().upper():
                if 'regia_tracker' in globals() and hasattr(regia_tracker, 'render_check_3_regole'):
                    import importlib; importlib.reload(regia_tracker); regia_tracker.render_check_3_regole([ticker_input.strip().upper()], eurusd_rate, rileva_fase_fn=rileva_fase_weinstein)
                if st.button("✖️ Chiudi Check", key="btn_chiudi_check_singola"):
                    st.session_state.pop("_run_check_singola", None)
                    st.rerun()
    with col_in2:
        st.write("")
        st.write("")
        if st.button("🔎 Analizza", type="primary", use_container_width=True):
            ticker_s = ticker_input.strip().upper()
            try:
                ticker_obj = yf.Ticker(ticker_s)
                df = ticker_obj.history(period="1y")
                if df is not None and not df.empty:
                    df = df.dropna(subset=['Open', 'High', 'Low', 'Close']).copy()
                info = ticker_obj.info if isinstance(ticker_obj.info, dict) else {}
                # In Analisi Singola consentiamo anche titoli neo-quotati (IPO recenti) con almeno 2 candele
                if df is None or df.empty or len(df) < 2:
                    st.error("Dati insufficienti (meno di 2 candele disponibili)")
                else:
                    n_sedute = int(len(df))
                    is_ipo_recente = n_sedute < 60
                    prezzo_eur, prezzo_usd, currency = get_prezzi_corretti(ticker_obj, eurusd_rate)
                    # Fallback sul Close dell'ultima candela se history(period='1d') risultasse vuoto
                    if prezzo_usd is None or prezzo_eur is None:
                        _p_raw = float(df['Close'].iloc[-1])
                        if str(currency).upper() == 'USD':
                            prezzo_usd = round(_p_raw, 2)
                            prezzo_eur = round(_p_raw / eurusd_rate, 2) if eurusd_rate > 0 else round(_p_raw, 2)
                        else:
                            prezzo_eur = round(_p_raw, 2)
                            prezzo_usd = round(_p_raw * eurusd_rate, 2)
                    var_pct, var_abs = calcola_variazione_giornaliera(ticker_obj)
                    if var_pct is None and n_sedute >= 2:
                        _c_last = float(df['Close'].iloc[-1])
                        _c_prev = float(df['Close'].iloc[-2])
                        if _c_prev > 0:
                            var_pct = round(((_c_last - _c_prev) / _c_prev) * 100.0, 2)
                            var_abs = round(_c_last - _c_prev, 2)
                    vol_oggi = float(df['Volume'].iloc[-1]) if 'Volume' in df.columns else 0.0
                    _win_vol = min(20, n_sedute)
                    _vm_raw = df['Volume'].rolling(window=_win_vol).mean().iloc[-1] if 'Volume' in df.columns else 0.0
                    vol_medio = round(float(_vm_raw), 0) if pd.notna(_vm_raw) else 0.0
                    vol_ratio = (vol_oggi / vol_medio) if vol_medio > 0 else 0.0
                    s_score = calcola_s_score(info, ticker_s)
                    earnings_giorni, earnings_msg, _ = controlla_earnings(ticker_obj)
                    supporto = round(float(df.tail(min(60, n_sedute))['Low'].min()), 2)
                    resistenza = round(float(df.tail(min(60, n_sedute))['High'].max()), 2)
                    delta_rsi = df['Close'].diff()
                    gain_rsi = (delta_rsi.where(delta_rsi > 0, 0)).rolling(window=14).mean()
                    loss_rsi = (-delta_rsi.where(delta_rsi < 0, 0)).rolling(window=14).mean()
                    rs_rsi = gain_rsi / loss_rsi.replace(0, np.nan)
                    _rsi_last = (100 - (100 / (1 + rs_rsi))).iloc[-1] if n_sedute >= 15 and not rs_rsi.empty else np.nan
                    rsi_oggi = float(_rsi_last) if pd.notna(_rsi_last) else 50.0
                    post_price = info.get('postMarketPrice')
                    post_change = info.get('postMarketChangePercent')
                    pre_price = info.get('preMarketPrice')
                    pre_change = info.get('preMarketChangePercent')
                    if post_price and post_change:
                        market_msg = f"🌙 After-Hours: ${post_price:.2f} ({post_change:+.2f}%)"
                    elif pre_price and pre_change:
                        market_msg = f"🌅 Pre-Market: ${pre_price:.2f} ({pre_change:+.2f}%)"
                    else:
                        market_msg = "🌞 Regular Market (o N/D fuori orario)"
                    hist_intraday = ticker_obj.history(period='5d', interval='1d')
                    if not hist_intraday.empty:
                        last_day = hist_intraday.iloc[-1]
                        min_oggi, max_oggi = round(float(last_day['Low']), 2), round(float(last_day['High']), 2)
                    else:
                        min_oggi, max_oggi = round(float(df['Low'].iloc[-1]), 2), round(float(df['High'].iloc[-1]), 2)

                    if is_ipo_recente:
                        # Modalità IPO recente (2..59 sedute): niente segnali automatici né medie mobili lunghe
                        fase = f"🆕 IPO Recente ({n_sedute} sedute)"
                        figura_z = False
                        trigger_by = False
                        trigger_by_fabio = False
                        motivo_by = f"Titolo neo-quotato ({n_sedute} sedute): medie mobili lunghe e filtri statistici attivi da 60 candele."
                        motivo_by_fabio = ""
                        _s50_tmp = df['Close'].rolling(window=50).mean().iloc[-1] if n_sedute >= 50 else np.nan
                        sma50_usd = round(float(_s50_tmp), 2) if pd.notna(_s50_tmp) else 0.0
                        sma200_usd = 0.0
                        pre_golden_cross = False
                        pre_death_cross = False
                        segnale = f"🆕 IPO Recente ({n_sedute} sedute)"
                        st.session_state.pattern_singola_attivo = None
                        # Apre subito il grafico a candele per la consultazione della neo-quotata
                        port_att_ipo = st.session_state.portafoglio or carica_json(PORTAFOGLIO_FILE) or list()
                        st.session_state.grafico_ticker = ticker_s
                        st.session_state.grafico_prezzo_medio = next((p['Prezzo_Medio'] for p in port_att_ipo if p['Ticker'] == ticker_s), None)
                    else:
                        df['SMA_Short'] = df['Close'].rolling(window=50).mean()
                        df['SMA_Long'] = df['Close'].rolling(window=200).mean()
                        df['Vol_Media_20'] = df['Volume'].rolling(window=20).mean()
                        fase = rileva_fase_weinstein(df)
                        figura_z, _ = rileva_figura_z(df)
                        trigger_by, motivo_by, _ = verifica_trigger_by_fortezza(df, 50, ticker_obj)
                        trigger_by_fabio, motivo_by_fabio = verifica_by_fabio(df, 50, ticker_obj)
                        _s50_raw = df['Close'].rolling(window=50).mean().iloc[-1]
                        _s200_raw = df['Close'].rolling(window=200).mean().iloc[-1] if n_sedute >= 200 else np.nan
                        sma50_usd = round(float(_s50_raw), 2) if pd.notna(_s50_raw) else 0.0
                        sma200_usd = round(float(_s200_raw), 2) if pd.notna(_s200_raw) else 0.0
                        distanza_medie_pct = abs(sma50_usd - sma200_usd) / sma200_usd * 100 if sma200_usd != 0 else 999.0
                        pre_golden_cross = sma200_usd > 0 and distanza_medie_pct < 3.0 and sma50_usd < sma200_usd
                        pre_death_cross = sma200_usd > 0 and distanza_medie_pct < 3.0 and sma50_usd > sma200_usd
                        if trigger_by_fabio:
                            segnale = "🟢 BY FABIO - Ingresso Matematico"
                        elif trigger_by:
                            segnale = "🟢 BY - Acquista"
                        elif "FASE 4" in fase or s_score < 40:
                            segnale = "🔴 SELL - Evita"
                        elif s_score >= 60 and "FASE 2" in fase:
                            segnale = "🟡 HOLD - Monitora"
                        else:
                            segnale = "🟡 HOLD - In attesa"
                        # Calcola anche l'eventuale pattern attivo per il titolo analizzato in Analisi Singola
                        try:
                            _port_an = st.session_state.portafoglio or list()
                            _pos_an = next((p for p in _port_an if str(p.get('Ticker', '')).upper() == ticker_s), None)
                            _pnl_an = None
                            if _pos_an is not None:
                                _pmc_an = float(_pos_an.get('Prezzo_Medio', 0) or 0)
                                if _pmc_an > 0 and prezzo_eur is not None:
                                    _pnl_an = ((float(prezzo_eur) / _pmc_an) - 1.0) * 100.0
                            _spy_reg_an = (semaforo_header.get('stato') if isinstance(semaforo_header, dict) else 'verde') or 'verde'
                            _pat_an_list = pattern_engine.analizza_pattern_titolo(
                                ticker=ticker_s,
                                df=df,
                                in_portafoglio=_pos_an is not None,
                                pnl_pct=_pnl_an,
                                eurusd_rate=eurusd_rate,
                                currency=currency,
                                earnings_giorni=earnings_giorni,
                                spy_regime=_spy_reg_an,
                                s_score=s_score,
                            )
                            if _pat_an_list:
                                _pat_best_an = next((x for x in _pat_an_list if x.get('lato') == 'SELL'), _pat_an_list[0])
                                st.session_state.pattern_singola_attivo = _pat_best_an
                            else:
                                st.session_state.pattern_singola_attivo = None
                        except Exception:
                            st.session_state.pattern_singola_attivo = None

                    st.session_state.analisi_risultati = {
                        'ticker': ticker_s, 'segnale': segnale, 'prezzo_eur': prezzo_eur, 'prezzo_usd': prezzo_usd,
                        's_score': s_score, 'fase': fase, 'vol_ratio': vol_ratio, 'figura_z': figura_z,
                        'earnings_msg': earnings_msg, 'motivo_by': motivo_by_fabio if trigger_by_fabio else motivo_by,
                        'var_pct': var_pct, 'var_abs': var_abs, 'sma50_usd': sma50_usd, 'sma200_usd': sma200_usd,
                        'vol_oggi': vol_oggi, 'vol_medio': vol_medio, 'supporto': supporto, 'resistenza': resistenza,
                        'market_msg': market_msg, 'pre_golden_cross': pre_golden_cross, 'pre_death_cross': pre_death_cross,
                        'min_oggi': min_oggi, 'max_oggi': max_oggi, 'rsi': rsi_oggi, 'trigger_by_fabio': trigger_by_fabio,
                        'is_ipo_recente': is_ipo_recente, 'n_sedute': n_sedute
                    }
            except Exception as e:
                st.error(f"Errore: {e}")

    if st.session_state.analisi_risultati:
        r = st.session_state.analisi_risultati
        if r.get('is_ipo_recente'):
            _n_sed_ipo = int(r.get('n_sedute') or 0)
            st.warning(f"⚠️ Titolo neo-quotato (IPO recente — {_n_sed_ipo} sedute): medie mobili lunghe e filtri statistici saranno attivi al raggiungimento di 60 candele")
        render_scheda_titolo_pro(r, eurusd_rate)
        _b_ins_an = get_badge_insider_attivo(r['ticker'])
        if False:
            st.info(f"**Promosso da Insider Tracker:** {_b_ins_an}")
        if False:
            st.markdown(f"**Prezzo:** € {r['prezzo_eur']:.2f} (${r['prezzo_usd']:.2f}) | **S-Score:** {r['s_score']}/100 | **RSI:** {r['rsi']:.1f}")
            col5, col6, col7, col8 = st.columns(4)
            col5.metric("📊 Fase Weinstein", r['fase'].split(' ')[0] + " " + r['fase'].split(' ')[1] if len(r['fase'].split(' ')) > 1 else r['fase'])
            col6.metric("📈 SMA 50", f"$ {r['sma50_usd']:.2f}")
            col7.metric("📉 SMA 200", f"$ {r['sma200_usd']:.2f}")
            col8.metric("📊 Vol Ratio", f"{r['vol_ratio']:.2f}x")

            if r.get('var_pct') is not None:
                var_color = "#089981" if r['var_pct'] > 0 else "#F23645"
                st.markdown(f"**Variazione oggi:** <span style='color:{var_color};font-weight:bold'>{r['var_pct']:+.2f}% ({r['var_abs']:+.2f}€)</span> &nbsp;|&nbsp; **Min/Max Oggi:** ${r['min_oggi']} / ${r['max_oggi']}", unsafe_allow_html=True)
            st.markdown(f"**{r['market_msg']}** &nbsp;|&nbsp; **Figura Z:** {'✅ Sì' if r['figura_z'] else '❌ No'} &nbsp;|&nbsp; **Utili:** {r['earnings_msg']} &nbsp;|&nbsp; **Sup/Res:** ${r['supporto']:.2f} / ${r['resistenza']:.2f}")
            if r.get('pre_golden_cross'):
                st.success("🚀 **Pre-Golden Cross**: La SMA 50 sta per incrociare la SMA 200 dal basso!")
            elif r.get('pre_death_cross'):
                st.warning("⚠️ **Pre-Death Cross**: La SMA 50 sta per incrociare la SMA 200 dall'alto. Attenzione!")

            ticker_obj_analisi = yf.Ticker(r['ticker'])
            targets_analisi = calcola_target(ticker_obj_analisi, r['prezzo_eur'], r['prezzo_usd'])
            if targets_analisi:
                rischio_pct = round(((targets_analisi['sl'] / r['prezzo_usd']) - 1) * 100, 1)
                rapporto_rr = round(targets_analisi['upside1'] / abs(rischio_pct), 1) if rischio_pct != 0 else 1.5
                st.markdown(f"""
                <div style="background-color: #131722; padding: 1rem; border-radius: 8px; margin: 1rem 0; border: 1px solid #2A2E39;">
                <h4 style="margin-top:0; color: #F59E0B;">🎯 TARGET DI PREZZO (Basati su resistenze grafiche):</h4>
                <p style="margin: 0.2rem 0;">• <strong>Target 1:</strong> ${targets_analisi['t1']} (+{targets_analisi['upside1']}%) &nbsp;|&nbsp; <strong>Target 2:</strong> ${targets_analisi['t2']} (+{targets_analisi['upside2']}%) &nbsp;|&nbsp; <strong>Target 3:</strong> ${targets_analisi['t3']} (+{targets_analisi['upside3']}%)</p>
                <hr style="border-color: #2A2E39; margin: 0.5rem 0;">
                <p style="margin: 0.2rem 0;"><strong>⚖️ RAPPORTO RISCHIO/RENDIMENTO:</strong> Rischio <span style="color: #F23645;">{rischio_pct}%</span> vs Rendimento <span style="color: #089981;">+{targets_analisi['upside1']}%</span> → <strong>Rapporto 1:{rapporto_rr} ✅</strong></p>
            </div>
            """, unsafe_allow_html=True)
        if r.get('is_ipo_recente'):
            # Per le IPO recenti l'avviso esplicativo è già mostrato in testa alla scheda
            pass
        elif r.get('trigger_by_fabio'):
            st.success(f"**🟢 BY FABIO**: {r['motivo_by']}")
        elif "BY" in r['segnale']:
            st.success(f"**Motivo**: {r['motivo_by']}")
        elif "HOLD" in r['segnale']:
            st.warning(f"**Motivo**: {r['motivo_by']}")
        else:
            st.error("**Motivo**: Titolo in Fase 4 o S-Score troppo basso")
        st.markdown("---")
        st.subheader("💰 Simulatore di Acquisto Intelligente")
        col_sim1, col_sim2 = st.columns([2, 1])
        with col_sim1:
            sim_ticker = st.text_input("Titolo da acquistare:", value=r['ticker'])
        with col_sim2:
            if "sim_importo_box" not in st.session_state:
                st.session_state["sim_importo_box"] = 200
            sim_importo = st.number_input("Importo (€):", min_value=100, max_value=100000, step=100, key="sim_importo_box")
        try:
            _cassa_broker = float(_liq_net) if "_liq_net" in locals() else float(st.session_state.get("liquidita", 0.0) or 0.0)
            _escl_raw = str(esclusioni_input) if "esclusioni_input" in locals() else str(impostazioni.get("esclusioni", "") if "impostazioni" in locals() else "")
            _escl_set = {x.strip().upper() for x in re.split(r"[,;\s\n]+", _escl_raw) if x.strip()}
            _cat_raw = str(catalizzatori_input) if "catalizzatori_input" in locals() else ""
            _cat_set = {x.split(":")[0].strip().upper() for x in _cat_raw.splitlines() if ":" in x}
            _port_src = portafoglio_attuale if "portafoglio_attuale" in locals() else st.session_state.get("portafoglio", [])
            _df_m_sim = _costruisci_mappa_metriche_scan()
            _vendibili = []
            _tot_vend_netto = 0.0
            for _p_s in _port_src:
                _tk_s = str(_p_s.get("Ticker", "")).strip().upper()
                _va_s = float(_p_s.get("Valore_Attuale", 0.0) or 0.0)
                _pnl_s = float(_p_s.get("PnL_EUR", 0.0) or 0.0)
                if not _tk_s or _tk_s in _escl_set or _tk_s in _cat_set or _va_s <= 0:
                    continue
                _tassa_s = max(0.0, _pnl_s * 0.26)
                _netto_s = round(_va_s - _tassa_s, 2)
                _fase_s, _score_s, _rsi_s, _pac_s, _ut_gg = _estrai_info_posizione_vendibile(_tk_s, _p_s, _df_m_sim)
                if _pnl_s > 0 and ("2" in _fase_s or _score_s >= 85) and _rsi_s < 75 and _ut_gg > 7:
                    continue
                if _tk_s == "NKE" or _ut_gg <= 7:
                    _prio = 0
                    _tag_s = "Trimestrale / Investor Day imminente"
                elif _tk_s == "TTD" or "4" in _fase_s or _rsi_s >= 70:
                    _prio = 1
                    _tag_s = "Fase 4 / RSI>70"
                elif _pnl_s > 0 and not _pac_s:
                    _prio = 2
                    _tag_s = "Gain Spot non in Fase 2"
                elif _pnl_s <= 0 and not _pac_s:
                    _prio = 3
                    _tag_s = "Sfoltimento 0 tasse"
                else:
                    continue
                _pnl_netto_sim = round((_pnl_s - _tassa_s - 1.0) if "_pnl_s" in locals() else (_netto_s - _va_s), 2)
                _motivo_s = f"{_tag_s} | P&L Netto: €{_pnl_netto_sim:+.2f} | netto €{max(0.0, _netto_s - 1.0):.2f}" + (f" (-€{_tassa_s:.2f} tasse -€1 comm.)" if _tassa_s > 0 else " (0 tasse, -€1 comm.)")
                _vendibili.append((_prio, _va_s, _tk_s, _netto_s, _motivo_s))
                _tot_vend_netto += _netto_s
            _vendibili.sort(key=lambda x: (x[0], x[1]))
            _liq_extra = float(st.session_state.get("liq_aggiuntiva_sim", 0.0) or 0.0)
            _cassa_tot = round(_cassa_broker + _liq_extra, 2)
            _tot_disponibile = round(_cassa_tot + _tot_vend_netto, 2)
            _imp_req = float(sim_importo) if "sim_importo" in locals() else 200.0
            _tk_req = str(sim_ticker).upper().strip() if "sim_ticker" in locals() else "TITOLO"
            _mancante = round(max(0.0, _imp_req - _tot_disponibile), 2)
            _c_r1, _c_r2, _c_r3 = st.columns(3)
            _c_r1.metric("💳 Cassa Broker + Extra", f"€ {_cassa_tot:,.2f}", f"Broker €{_cassa_broker:.2f} + Extra €{_liq_extra:.2f}")
            _c_r2.metric("🔄 Vendibili (Netto Tasse)", f"€ {_tot_vend_netto:,.2f}", f"{len(_vendibili)} titoli sbloccati")
            _c_r3.metric("🎯 Copertura Totale", f"€ {_tot_disponibile:,.2f}", "Pronto" if _mancante == 0 else f"Mancano € {_mancante:,.2f}", delta_color="normal" if _mancante == 0 else "inverse")
            if _mancante > 0:
                st.warning(f"⚠️ **Fabio, per acquistare {_tk_req} da € {_imp_req:,.2f} ti mancano ancora € {_mancante:,.2f}** di liquidità aggiuntiva (hai € {_cassa_broker:,.2f} sul broker + € {_liq_extra:,.2f} extra nella sidebar + € {_tot_vend_netto:,.2f} netti dai titoli non esclusi).")
            else:
                _piano_step = []
                _residuo = _imp_req
                if _cassa_broker > 0 and _residuo > 0:
                    _usa_b = min(_residuo, _cassa_broker)
                    _piano_step.append(f"1️⃣ **Cassa Broker:** € {_usa_b:,.2f}")
                    _residuo = round(max(0.0, _residuo - _usa_b), 2)
                if _liq_extra > 0 and _residuo > 0:
                    _usa_e = min(_residuo, _liq_extra)
                    _piano_step.append(f"2️⃣ **Liquidità Aggiuntiva (Sidebar):** € {_usa_e:,.2f}")
                    _residuo = round(max(0.0, _residuo - _usa_e), 2)
                for _pr, _va_o, _v_tk, _v_net, _v_mot in _vendibili:
                    if _residuo <= 0:
                        break
                    _piano_step.append(f"🔄 **Vendi {_v_tk}** ({_v_mot}) -> incasso netto **€ {_v_net:,.2f}**")
                    _residuo = round(max(0.0, _residuo - _v_net), 2)
                st.success(f"✅ **Acquisto {_tk_req} (€ {_imp_req:,.2f}) coperto!** Piano consigliato:\n\n" + "\n".join([f"- {s}" for s in _piano_step]))
        except Exception as _e_sim:
            st.caption(f"⚠️ Simulatore non disponibile al momento: {_e_sim}")
        if st.button("🔍 Analizza Finanziamento", type="secondary", use_container_width=True):
            portafoglio_attuale = st.session_state.portafoglio or carica_json(PORTAFOGLIO_FILE) or PORTAFOGLIO_INIZIALE
            esclusioni_list = [t.strip().upper() for t in esclusioni_input.split(",") if t.strip()]
            st.session_state.risultato_simulazione = simula_acquisto(sim_ticker.upper(), sim_importo, portafoglio_attuale, eurusd_rate, esclusioni_list, catalizzatori_input)
        if st.session_state.get('risultato_simulazione'):
            if st.button("✖️ Nascondi Analisi"):
                st.session_state.risultato_simulazione = None
                st.rerun()
            risultato = st.session_state.risultato_simulazione
            if 'errore' in risultato:
                st.error(risultato['errore'])
            else:
                st.markdown(f"**Titolo:** {risultato['titolo']} | **Prezzo:** €{risultato['prezzo_eur']:.2f} | **Quantità acquistabile:** {risultato['quantita_acquistabile']:.6f}")
                st.markdown("---")
                scenari = risultato['scenari']
                if scenari['hold_catalizzatore']:
                    st.markdown("### ⚠️ Titoli da NON Vendere (Catalizzatori Imminenti)")
                    for item in scenari['hold_catalizzatore']:
                        st.warning(item['messaggio'])
                if scenari['vendita_gain']:
                    st.markdown("### ⚠️ Scenario 1: Vendita Titoli in Gain")
                    for item in scenari['vendita_gain']:
                        st.warning(item['messaggio'])
                if scenari['vendita_loss']:
                    st.markdown("### ✅ Scenario 2: Vendita Titoli in Loss/Kill Switch")
                    for item in scenari['vendita_loss']:
                        st.success(item['messaggio'])
                if scenari['nuova_liquidita']:
                    st.markdown("### 🎯 Scenario 3: Nuova Liquidità")
                    st.success("**OPZIONE MIGLIORE.** Preservi il portafoglio esistente e mantieni i titoli in gain pronti a ripartire.")
                st.markdown("---")
                st.markdown("### 🏁 CONSIGLIO FINALE DEL SISTEMA")
                if scenari['nuova_liquidita'] and not scenari['vendita_loss'] and not scenari['hold_catalizzatore']:
                    st.success(f"🎯 **Visti gli scenari, consigliamo l'acquisto di {risultato['titolo']} con NUOVA LIQUIDITÀ di {risultato['importo']}€.** I titoli in gain sono in fase di ripresa e non vanno toccati. Procedi con l'acquisto.")
                elif scenari['vendita_loss'] or scenari['hold_catalizzatore']:
                    loss_tickers = ", ".join([v['ticker'] for v in scenari['vendita_loss'][:2]])
                    hold_tickers = ", ".join([v['ticker'] for v in scenari['hold_catalizzatore'][:2]])
                    msg_parts = list()
                    if hold_tickers:
                        msg_parts.append(f"**NON VENDERE** {hold_tickers} (catalizzatore imminente).")
                    if loss_tickers:
                        msg_parts.append(f"Valuta prima di vendere {loss_tickers} per ottimizzazione fiscale.")
                    st.warning(f"⚠️ {' '.join(msg_parts)} Se decidi di non vendere, procedi pure con la nuova liquidità.")
                else:
                    st.info("Valuta attentamente le opzioni sopra prima di procedere.")

        st.markdown("---")
        st.markdown('<div class="signal-history-box"><div class="signal-history-title">📊 STORICO SEGNALI MATRIX</div></div>', unsafe_allow_html=True)
        ultimo_segnale_check = get_ultimo_segnale(r['ticker'])
        if not ultimo_segnale_check and not r.get('is_ipo_recente'):
            with st.spinner(f"🔄 Ricostruzione segnali storici per {r['ticker']}..."):
                try:
                    segnali_aggiunti = ricostruisci_segnali_retroattivi(r['ticker'], anni_indietro=1)
                    if segnali_aggiunti > 0:
                        st.success(f"✅ Trovati {segnali_aggiunti} segnali storici per {r['ticker']}")
                        st.rerun()
                    else:
                        st.info(f"ℹ️ Nessun segnale storico trovato per {r['ticker']} negli ultimi 12 mesi")
                except Exception as e:
                    st.error(f"❌ Errore ricostruzione: {e}")
        ultimo_segnale = get_ultimo_segnale(r['ticker'])
        if ultimo_segnale:
            var_pct_segnale, giorni_trascorsi, prezzo_segnale = calcola_performance_segnale(ultimo_segnale, r['prezzo_usd'])
            if var_pct_segnale is not None:
                if ultimo_segnale['Tipo'] == 'BY':
                    colore_var, testo_successo = ("#089981", "✅ Segnale vincente") if var_pct_segnale >= 0 else ("#F23645", "❌ Segnale perdente")
                elif ultimo_segnale['Tipo'] == 'BY_FABIO':
                    colore_var, testo_successo = ("#089981", "✅ Segnale BY FABIO vincente") if var_pct_segnale >= 0 else ("#F23645", "❌ Segnale BY FABIO perdente")
                else:
                    colore_var, testo_successo = ("#089981", "✅ Ha evitato perdita") if var_pct_segnale <= 0 else ("#F59E0B", "⚠️ Opportunità mancata")
                data_fmt = formatta_data_europea(ultimo_segnale.get('Data', ''))
                segno = "+" if var_pct_segnale > 0 else ""
                st.markdown(f"""
                <div style="background-color: #131722; border: 1px solid #2A2E39; border-left: 4px solid {colore_var}; padding: 1rem; border-radius: 6px; margin: 1rem 0;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>Ultimo segnale:</strong> {'🟢 BY FABIO' if ultimo_segnale['Tipo'] == 'BY_FABIO' else ('🟢 BY' if ultimo_segnale['Tipo'] == 'BY' else '🔴 SELL/EVITA')}<br>
                            <strong>Data:</strong> {data_fmt} ({giorni_trascorsi} giorni fa)<br>
                            <strong>Prezzo al segnale:</strong> ${prezzo_segnale:.2f}
                        </div>
                        <div style="text-align: right;">
                            <div style="font-family: 'JetBrains Mono', monospace; font-size: 1.5rem; font-weight: bold; color: {colore_var};">{segno}{var_pct_segnale:.1f}%</div>
                            <div style="font-size: 0.85rem; color: {colore_var};">{testo_successo}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.info("Nessun segnale precedente disponibile per il calcolo.")
        else:
            st.info("Nessun segnale precedente registrato per questo titolo.")

        if st.button(f"📊 Mostra Grafico {r['ticker']}", type="secondary", use_container_width=True):
            st.session_state.grafico_ticker = r['ticker']
            port_att = st.session_state.portafoglio or carica_json(PORTAFOGLIO_FILE) or list()
            st.session_state.grafico_prezzo_medio = next((p['Prezzo_Medio'] for p in port_att if p['Ticker'] == r['ticker']), None)
        if st.session_state.get('grafico_ticker'):
            st.markdown("---")
            st.subheader(f"📊 {st.session_state.grafico_ticker}")
            timeframe_options = {
                "1GG (1 giorno, 15min)": {"period": "5d", "interval": "15m", "tf": "15m"},
                "5GG (5 giorni, 1h)": {"period": "1mo", "interval": "1h", "tf": "1h"},
                "1M (1 mese)": {"period": "2y", "interval": "1d", "tf": "1M"},
                "3M (3 mesi)": {"period": "2y", "interval": "1d", "tf": "3M"},
                "6M (6 mesi)": {"period": "2y", "interval": "1d", "tf": "6M"},
                "1A (1 anno)": {"period": "2y", "interval": "1d", "tf": "1A"},
                "Da Inizio Anno": {"period": "2y", "interval": "1d", "tf": "YTD"},
                "1d (Daily)": {"period": "2y", "interval": "1d", "tf": "1d"},
                "1wk (Weekly)": {"period": "5y", "interval": "1wk", "tf": "1wk"},
                "1mo (Monthly)": {"period": "max", "interval": "1mo", "tf": "1mo"},
            }
            tf_choice = st.selectbox("Timeframe:", list(timeframe_options.keys()), index=7)
            tf_config = timeframe_options[tf_choice]
            # Recupera eventuale pattern attivo prima di generare il grafico così il range Y include Trigger Y, Target e Stop
            _tk_g_up = str(st.session_state.grafico_ticker).upper()
            _pat_an = (st.session_state.get("pattern_alerts") or {}).get("per_ticker", {}).get(_tk_g_up)
            if not _pat_an:
                _pat_s = st.session_state.get("pattern_singola_attivo")
                if isinstance(_pat_s, dict) and str(_pat_s.get("ticker", "")).upper() == _tk_g_up:
                    _pat_an = _pat_s
            fig = genera_grafico_baleine(st.session_state.grafico_ticker, tf_config['period'], 50, 200, prezzo_medio_eur=st.session_state.grafico_prezzo_medio, timeframe=tf_config['tf'], interval=tf_config['interval'], eurusd_rate=eurusd_rate, height=860, pattern_info=_pat_an)
            if fig:
                # Se il titolo ha un pattern attivo (da scansione o da Analisi Singola), traccia Trigger Y, Target e Stop
                if _pat_an:
                    fig = pattern_engine.aggiungi_livelli_pattern_al_grafico(fig, _pat_an)
                    _sym_an = "$" if str(_pat_an.get("currency", "USD")).upper() == "USD" else "€"
                    st.caption(
                        f"**{_pat_an.get('badge')}** — {_pat_an.get('figura')} ({_pat_an.get('confidenza')}%) | "
                        f"⚡ Y: `{_sym_an}{_pat_an.get('trigger_y'):.2f}` | 🎯 Target: `{_pat_an.get('target_pct'):+.1f}%` (`{_sym_an}{_pat_an.get('target_price'):.2f}`) | "
                        f"🛑 Stop: `{_sym_an}{_pat_an.get('stop_price'):.2f}` | R/R `1:{_pat_an.get('rr'):.2f}`"
                    )
                fig = applica_controlli_grafico(fig, 3)
                st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True, "displaylogo": False, "responsive": True})
            else:
                st.error("Impossibile generare il grafico")
            if st.button("✖️ Chiudi grafico", use_container_width=True):
                st.session_state.grafico_ticker = None
                st.session_state.grafico_prezzo_medio = None
                st.rerun()
with tab_registro:
    st.markdown("### 📒 Registro Acquisti & Mediazioni")
    if os.path.exists("registro_acquisti.json"):
        with open("registro_acquisti.json", "r", encoding="utf-8") as _fa:
            _dati_acq = json.load(_fa)
        if _dati_acq:
            st.dataframe(pd.DataFrame(_dati_acq), use_container_width=True, hide_index=True)
        else:
            st.info("Nessun acquisto registrato finora.")
    else:
        st.info("Il registro acquisti si creerà automaticamente al primo nuovo acquisto o mediazione.")

    st.subheader("📋 Registro Vendite & Fiscalità")
    anni_disponibili = ["Tutti"] + [str(y) for y in range(2024, 2028)]
    anno_corrente = str(datetime.now().year)
    index_default = anni_disponibili.index(anno_corrente) if anno_corrente in anni_disponibili else 0
    anno_filter = st.selectbox("📅 Filtra per anno:", anni_disponibili, index=index_default)
    anno_val = None if anno_filter == "Tutti" else int(anno_filter)
    liquidita_totale = calcola_liquidita_totale()
    riepilogo = calcola_riepilogo_fiscale(None)
    col_liq1, col_liq2, col_liq3, col_liq4 = st.columns(4)
    with col_liq1:
        st.metric("💰 Liquidità Netta da Vendite", f"€ {liquidita_totale:,.2f}", help="Somma incassi netti (prezzo × qta - tasse) da tutte le vendite")
    with col_liq2:
        st.metric("📈 P&L Realizzato Netto", f"€ {riepilogo['netto_reale']:+,.2f}", help="Utile netto dopo tasse e compensazione minusvalenze")
    with col_liq3:
        st.metric("🏛️ Tasse Pagate Totali", f"€ {riepilogo['tasse_totali']:,.2f}", help="Totale tasse 26% pagate su plusvalenze")
    with col_liq4:
        st.metric("📊 Pool Minusvalenze", f"€ {riepilogo['pool_minusvalenze']:,.2f}", help="Minusvalenze disponibili per compensazione futura")
    st.markdown("---")
    riepilogo = calcola_riepilogo_fiscale(anno_val)
    col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
    with col_f1:
        st.metric("💰 Gain Totale", f"€ {riepilogo['gain_totale']:+.2f}")
    with col_f2:
        st.metric("📉 Loss Totale", f"€ {riepilogo['loss_totale']:+.2f}")
    with col_f3:
        st.metric("🏛️ Tasse (26%)", f"€ {riepilogo['tasse_totali']:.2f}")
    with col_f4:
        st.metric("✅ Netto Reale", f"€ {riepilogo['netto_reale']:+.2f}")
    with col_f5:
        st.metric("📊 Pool Minusvalenze", f"€ {riepilogo['pool_minusvalenze']:.2f}")
    st.caption(f"📊 {riepilogo['num_operazioni']} operazioni registrate" + (f" nel {anno_filter}" if anno_val else ""))
    st.markdown("---")
    registro = carica_json(REGISTRO_VENDITE_FILE)
    if anno_val:
        registro = [v for v in registro if v.get('Data', '').startswith(str(anno_val))]
    col_act1, col_act2, col_act3 = st.columns(3)
    with col_act1:
        st.markdown("**🗑️ Cancella Operazione (Testing)**")
        if registro:
            id_da_cancellare = st.selectbox("Seleziona ID", [v['id'] for v in registro])
            if st.button("Elimina operazione"):
                if elimina_operazione_vendita(id_da_cancellare):
                    st.success(f"✅ Operazione #{id_da_cancellare} eliminata")
                    st.rerun()
                else:
                    st.info("📭 Nessuna operazione registrata.")
    with col_act2:
        st.markdown("**📥 Esporta CSV**")
        csv_data = None
        if registro:
            import csv
            from io import StringIO
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(['ID', 'Data', 'Ticker', 'Qta Venduta', 'Prezzo Medio', 'Prezzo Vendita', 'P&L Lordo', 'P&L %', 'Minusvalenze Usate', 'Tasse', 'P&L Netto', 'Tipo'])
            for v in registro:
                writer.writerow([v.get('id', ''), v.get('Data', ''), v.get('Ticker', ''), v.get('Qta_Venduta', ''), v.get('Prezzo_Medio', ''), v.get('Prezzo_Vendita', ''), v.get('PnL_Lordo', ''), v.get('PnL_Pct', ''), v.get('Minusvalenze_Usate', ''), v.get('Tasse', ''), v.get('PnL_Netto', ''), v.get('Tipo', '')])
            csv_data = output.getvalue()
        if csv_data:
            st.download_button(label="⬇️ Scarica CSV", data=csv_data, file_name=f"registro_vendite_{anno_filter}.csv", mime="text/csv")
        else:
            st.info("Nessun dato da esportare")
    with col_act3:
        st.markdown("**⚠️ Reset Completo**")
        if st.button("🗑️ Reset Registro", type="primary"):
            if reset_registro_vendite():
                st.success("✅ Registro e minusvalenze resettati")
                st.rerun()
    st.markdown("---")
    if registro:
        df_registro = pd.DataFrame(registro)
        df_display = df_registro[['id', 'Data', 'Ticker', 'Qta_Venduta', 'Prezzo_Medio', 'Prezzo_Vendita', 'PnL_Lordo', 'PnL_Pct', 'Minusvalenze_Usate', 'Tasse', 'PnL_Netto', 'Tipo']].copy()
        df_display.columns = ['ID', 'Data', 'Ticker', 'Qta', 'P.Medio', 'P.Vendita', 'P&L Lordo', 'P&L %', 'MV Usate', 'Tasse', 'P&L Netto', 'Tipo']
        def color_pnl(val):
            try:
                v = float(val)
                return 'color: #089981; font-weight: bold' if v > 0 else ('color: #F23645; font-weight: bold' if v < 0 else '')
            except:
                return ''
        st.dataframe(df_display.style.map(color_pnl, subset=['P&L Lordo', 'P&L Netto']), use_container_width=True, height=400)
    else:
        st.info(f"📭 Nessuna vendita registrata" + (f" nel {anno_filter}." if anno_val else "."))
    st.markdown("---")
    st.subheader("📊 Pool Minusvalenze Disponibili")
    minusvalenze = carica_json(MINUSVALENZE_FILE)
    oggi_str = datetime.now().strftime("%Y-%m-%d")
    minusvalenze_attive = [m for m in minusvalenze if m.get('Scadenza', '') >= oggi_str]
    if minusvalenze_attive:
        df_mv = pd.DataFrame(minusvalenze_attive)
        df_mv.columns = ['Data Origine', 'Scadenza', 'Importo', 'Ticker']
        st.dataframe(df_mv, use_container_width=True, height=200)
    else:
        st.info("Nessuna minusvalenza disponibile nel pool.")

with tab_paper:
    st.subheader("🤖 Portfolio Sperimentale AI (Paper Trading)")
    st.markdown("Gestione virtuale basata sul **Setup Palantir**: S-Score ≥ 75, Growth ≥ 20%, PEG < 1.5, RSI < 45, Distanza SMA 200 ≤ 5%.")
    paper_port = carica_json(PAPER_TRADING_FILE)
    col_btn1, col_btn2 = st.columns([3, 1])
    with col_btn1:
        if st.button("🤖 Scansione AI: Cerca su Watchlist + Big Tech (fino a 3 setup)", type="primary"):
            tickers_personali = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
            tickers_big_tech = [t.strip().upper() for t in BIG_TECH_GROWTH_LIST.split(",") if t.strip()]
            tutti_tickers = list(set(tickers_personali + tickers_big_tech))
            progress_bar = st.progress(0)
            candidati_palantir = list()
            for i, ticker in enumerate(tutti_tickers):
                progress_bar.progress((i + 1) / len(tutti_tickers))
                try:
                    ticker_obj = yf.Ticker(ticker)
                    df = ticker_obj.history(period=period)
                    info = ticker_obj.info
                    if df.empty or len(df) < 200:
                        continue
                    prezzo_eur, prezzo_usd, currency = get_prezzi_corretti(ticker_obj, eurusd_rate)
                    if prezzo_eur is None:
                        continue
                    s_score = calcola_s_score(info)
                    fase = rileva_fase_weinstein(df)
                    delta = df['Close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    rsi_oggi = float((100 - (100 / (1 + (gain/loss)))).iloc[-1]) if not (gain/loss).empty else 50
                    revenue_growth = info.get('revenueGrowth', 0.0) or 0.0
                    peg_ratio = info.get('pegRatio', 0.0) or 0.0
                    sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
                    prezzo_attuale = df['Close'].dropna().iloc[-1]
                    distanza_sma200_pct = abs(prezzo_attuale - sma200) / sma200 * 100 if sma200 > 0 else 999
                    is_palantir = (s_score >= 75 and revenue_growth >= 0.20 and (peg_ratio > 0 and peg_ratio < 1.5) and rsi_oggi < 45 and distanza_sma200_pct <= 5.0)
                    if is_palantir:
                        candidati_palantir.append({'Ticker': ticker, 'Prezzo EUR': prezzo_eur, 'S-Score': s_score, 'RSI': round(rsi_oggi, 1), 'PEG': round(peg_ratio, 2) if peg_ratio > 0 else 'N/D', 'Rev Growth': f"{revenue_growth*100:.1f}%", 'Distanza SMA200': f"{distanza_sma200_pct:.1f}%"})
                except:
                    pass
            progress_bar.empty()
            if not candidati_palantir:
                st.warning("⚠️ Nessun Setup Palantir trovato nella scansione estesa.")
            else:
                candidati_palantir.sort(key=lambda x: x['S-Score'], reverse=True)
                top_3 = candidati_palantir[:3]
                attivi_tickers = [p['Ticker'] for p in paper_port if p.get('Stato') == 'Attivo']
                nuovi_trade = list()
                for c in top_3:
                    if c['Ticker'] not in attivi_tickers:
                        entry_price = c['Prezzo EUR']
                        nuovi_trade.append({"Ticker": c['Ticker'], "Entry": round(entry_price, 2), "Stop_Loss": round(entry_price * 0.92, 2), "Target": round(entry_price * 1.20, 2), "Data_Ingresso": datetime.now().strftime("%Y-%m-%d"), "Stato": "Attivo"})
                if nuovi_trade:
                    paper_port.extend(nuovi_trade)
                    salva_json(PAPER_TRADING_FILE, paper_port)
                    st.success(f"✅ Aggiunti {len(nuovi_trade)} titoli al Paper Trading: {', '.join([t['Ticker'] for t in nuovi_trade])}")
                    st.info(f"📊 Scansionati {len(tutti_tickers)} titoli (Watchlist + Big Tech). Trovati {len(candidati_palantir)} setup Palantir.")
                    st.rerun()
                else:
                    st.info("ℹ️ Tutti i titoli Palantir rilevati sono già in portafoglio come 'Attivi'.")
    st.markdown("---")
    if paper_port:
        df_paper = pd.DataFrame(paper_port)
        pnl_virtuali, ultimo_segnale_col, stats_pnl_list = list(), list(), list()
        aggiornato_json = False

        for idx, row in df_paper.iterrows():
            ticker = str(row.get('Ticker', '')).strip().upper()
            stato_cur = str(row.get('Stato', 'Attivo'))
            entry_eur = float(row.get('Entry', 0) or 0)
            sl_eur = float(row.get('Stop_Loss', 0) or 0)
            tg_eur = float(row.get('Target', 0) or 0)
            dt_ing = str(row.get('Data_Ingresso', ''))[:10]

            if stato_cur == 'Attivo' and ticker and entry_eur > 0:
                try:
                    hist_1y = yf.Ticker(ticker).history(period='1y', interval='1d')
                    if not hist_1y.empty:
                        current_price_usd = float(hist_1y['Close'].dropna().iloc[-1])
                        current_price_eur = current_price_usd / eurusd_rate

                        sub_h = hist_1y[hist_1y.index.strftime('%Y-%m-%d') >= dt_ing] if dt_ing else hist_1y.tail(1)
                        min_low_eur = float(sub_h['Low'].min()) / eurusd_rate if not sub_h.empty else current_price_eur
                        max_high_eur = float(sub_h['High'].max()) / eurusd_rate if not sub_h.empty else current_price_eur

                        if sl_eur > 0 and min_low_eur <= sl_eur:
                            pnl_sl = ((sl_eur - entry_eur) / entry_eur) * 100
                            df_paper.at[idx, 'Stato'] = 'Chiuso (SL)'
                            pnl_virtuali.append(f"{pnl_sl:+.1f}%")
                            ultimo_segnale_col.append(f"🛑 Stop €{sl_eur:.2f}")
                            stats_pnl_list.append(pnl_sl)
                            paper_port[idx]['Stato'] = 'Chiuso (SL)'
                            paper_port[idx]['Prezzo_Uscita'] = sl_eur
                            aggiornato_json = True
                        elif tg_eur > 0 and max_high_eur >= tg_eur:
                            pnl_tp = ((tg_eur - entry_eur) / entry_eur) * 100
                            df_paper.at[idx, 'Stato'] = 'Chiuso (TP)'
                            pnl_virtuali.append(f"{pnl_tp:+.1f}%")
                            ultimo_segnale_col.append(f"🎯 Target €{tg_eur:.2f}")
                            stats_pnl_list.append(pnl_tp)
                            paper_port[idx]['Stato'] = 'Chiuso (TP)'
                            paper_port[idx]['Prezzo_Uscita'] = tg_eur
                            aggiornato_json = True
                        else:
                            pnl_pct = ((current_price_eur - entry_eur) / entry_eur) * 100
                            pnl_virtuali.append(f"{pnl_pct:+.1f}%")
                            stats_pnl_list.append(pnl_pct)
                            sig_txt = format_ultimo_segnale_display(ticker, current_price_usd)
                            m_dt = re.search(r'(\d{2})/(\d{2})/(\d{4})', str(sig_txt))
                            if m_dt and dt_ing and f"{m_dt.group(3)}-{m_dt.group(2)}-{m_dt.group(1)}" < dt_ing:
                                sig_txt = "In corso"
                            ultimo_segnale_col.append(sig_txt)
                    else:
                        pnl_virtuali.append("N/D")
                        ultimo_segnale_col.append("N/D")
                except Exception:
                    pnl_virtuali.append("N/D")
                    ultimo_segnale_col.append("N/D")
            else:
                exit_eur = float(row.get('Prezzo_Uscita') or sl_eur or entry_eur)
                pnl_ch = ((exit_eur - entry_eur) / entry_eur) * 100 if entry_eur > 0 else 0.0
                pnl_virtuali.append(f"{pnl_ch:+.1f}%")
                stats_pnl_list.append(pnl_ch)
                if stato_cur == 'Chiuso':
                    df_paper.at[idx, 'Stato'] = 'Chiuso (SL)'
                ultimo_segnale_col.append(f"Chiuso @ €{exit_eur:.2f}")

        if aggiornato_json:
            salva_json(PAPER_TRADING_FILE, paper_port)

        df_paper['P&L Virtuale'] = pnl_virtuali
        df_paper['Ultimo Segnale'] = ultimo_segnale_col

        stats_pnl_list = [x for x in stats_pnl_list if x is not None and not math.isnan(float(x))]
        if stats_pnl_list:
            win_count = sum(1 for x in stats_pnl_list if x > 0)
            win_rate = (win_count / len(stats_pnl_list)) * 100
            avg_ret = sum(stats_pnl_list) / len(stats_pnl_list)
            tot_ret = sum(stats_pnl_list)
            _taglia_sp = float(st.session_state.get("sim_importo_box", 200.0) or 200.0)
            _pnl_lordo_eur = sum((_taglia_sp * (x / 100.0)) for x in stats_pnl_list)
            _tasse_sp = sum(max(0.0, (_taglia_sp * (x / 100.0)) * 0.26) for x in stats_pnl_list)
            _gain_netto_eur = round(_pnl_lordo_eur - _tasse_sp, 2)
            cs1, cs2, cs3, cs4, cs5 = st.columns(5)
            cs1.metric("🎯 Win Rate Strategia", f"{win_rate:.0f}%", f"{win_count} vincenti su {len(stats_pnl_list)}")
            cs2.metric("📊 Rendimento Medio", f"{avg_ret:+.2f}%", "Per singolo trade")
            cs3.metric("📈 P&L Cumulato", f"{tot_ret:+.1f}%", "Somma segnali")
            cs4.metric("💶 Gain Netto (26%)", f"€ {_gain_netto_eur:+,.2f}", f"Su taglia €{_taglia_sp:.0f} (-€{_tasse_sp:.2f} tasse)")
            cs5.metric("📁 Posizioni Tracciate", f"{len(stats_pnl_list)}", f"{sum(1 for s in df_paper['Stato'] if s == 'Attivo')} attive")

        st.dataframe(df_paper[['Ticker', 'Entry', 'Stop_Loss', 'Target', 'Data_Ingresso', 'Stato', 'P&L Virtuale', 'Ultimo Segnale']], use_container_width=True, hide_index=True, height=340)
        st.markdown("---")
        st.subheader("🔒 Gestione Posizioni")
        ticker_attivi = [p['Ticker'] for p in paper_port if p.get('Stato') == 'Attivo']
        if ticker_attivi:
            ticker_da_chiudere = st.selectbox("Seleziona Ticker da chiudere", ticker_attivi)
            if st.button("Chiudi Posizione (Passa a Chiuso)"):
                for p in paper_port:
                    if p['Ticker'] == ticker_da_chiudere and p.get('Stato') == 'Attivo':
                        p['Stato'] = 'Chiuso'
                        p['Data_Uscita'] = datetime.now().strftime("%Y-%m-%d")
                        try:
                            _p_close_usd = float(yf.Ticker(ticker_da_chiudere).history(period='1d')['Close'].iloc[-1])
                            p['Prezzo_Uscita'] = round(_p_close_usd / eurusd_rate, 2)
                        except Exception:
                            pass
                salva_json(PAPER_TRADING_FILE, paper_port)
                st.success(f"Posizione {ticker_da_chiudere} chiusa e archiviata.")
                st.rerun()
        else:
            st.info("Nessuna posizione attiva da chiudere.")
    else:
        st.info("📭 Il portfolio sperimentale è vuoto. Usa il pulsante 'Scansione AI' per iniziare a tracciare i setup.")

def _leggi_tutti_ticker_wl():
    _tks = []
    _base = os.path.dirname(os.path.abspath(__file__))
    _fp_imp = os.path.join(_base, IMPOSTAZIONI_FILE)
    if os.path.exists(_fp_imp):
        try:
            with open(_fp_imp, 'r', encoding='utf-8') as _f:
                _d = json.load(_f)
            if isinstance(_d, dict):
                for _k in ['tickers', 'lista_ticker_default', 'watchlist']:
                    _raw = _d.get(_k, '')
                    _items = _raw if isinstance(_raw, list) else str(_raw).replace('\n', ',').split(',')
                    for _el in _items:
                        _tc = str(_el.get('Ticker', _el) if isinstance(_el, dict) else _el).strip().upper()
                        if 1 <= len(_tc) <= 5 and _tc.isalpha() and _tc not in _tks:
                            _tks.append(_tc)
        except Exception:
            pass
    _fp_wl = os.path.join(_base, 'watchlist.json')
    if os.path.exists(_fp_wl):
        try:
            with open(_fp_wl, 'r', encoding='utf-8') as _f:
                _w = json.load(_f)
            if isinstance(_w, list):
                for _el in _w:
                    _tc = str(_el.get('Ticker', _el) if isinstance(_el, dict) else _el).strip().upper()
                    if 1 <= len(_tc) <= 5 and _tc.isalpha() and _tc not in _tks:
                        _tks.append(_tc)
        except Exception:
            pass
    return _tks

with tab_check_regole:
    st.subheader('🩺 Check-Up 3 Regole (IGNITION • BY FABIO • BY Standard)')
    st.caption('Lascia in bianco e clicca Controlla Tutta la Watchlist per filtrare tutti i 71 titoli, oppure inserisci ticker specifici.')
    chk_in = st.text_input('Ticker specifici (opzionale, es. MU, GOOGL, META):', value='', key='txt_check_multi_regole')
    f_col1, f_col2, f_col3 = st.columns([1.6, 1.3, 1.8])
    with f_col1:
        filtro_fase = st.selectbox('📊 Filtro Fase Weinstein', ['Tutte le Fasi', '✅ Solo Fase 2 (Rialzo)', '🧱 Solo Fase 1 (Accumulo)'], key='sel_fase_multi')
    with f_col2:
        st.write('')
        solo_pre_ign = st.checkbox('⏳ Solo PRE-IGNITION', value=False, key='chk_pre_ign_multi')
    with f_col3:
        min_score = st.slider('🎯 S-Score Minimo (0 = Tutti)', 0, 100, 0, 5, key='sld_min_score_multi')
    c_chk1, c_chk2, c_chk3 = st.columns([1.2, 1.8, 1.0])
    with c_chk1:
        if st.button('🔍 Avvia Check Ticker', key='btn_avvia_check_multi', type='primary', use_container_width=True):
            t_man = [t.strip().upper() for t in chk_in.replace('\n', ',').split(',') if t.strip()]
            st.session_state['_multi_check_list'] = t_man if t_man else _leggi_tutti_ticker_wl()
    with c_chk2:
        if st.button('📋 Controlla Tutta la Watchlist (~71)', key='btn_avvia_check_wl_all', use_container_width=True):
            st.session_state['_multi_check_list'] = _leggi_tutti_ticker_wl()
    with c_chk3:
        if st.session_state.get('_multi_check_list'):
            if st.button('✖️ Chiudi Check', key='btn_chiudi_check_multi', use_container_width=True):
                st.session_state.pop('_multi_check_list', None)
                st.rerun()
    if st.session_state.get('_multi_check_list'):
        if 'regia_tracker' in globals() and hasattr(regia_tracker, 'render_check_3_regole'):
            import importlib; importlib.reload(regia_tracker); regia_tracker.render_check_3_regole(st.session_state['_multi_check_list'], eurusd_rate, solo_fase2=filtro_fase, min_score=min_score, solo_pre_ign=solo_pre_ign, rileva_fase_fn=rileva_fase_weinstein)
with tab_insider:
    st.markdown("### 🕵️ Insider Tracker (SEC Form 4) & Stagionalità 10 Anni")
    st.caption("Individua acquisti reali dei dirigenti (Cluster Buying) su titoli sottovalutati vicini ai minimi con stagionalità favorevole.")

    col_ins1, col_ins2, col_ins3, col_ins4 = st.columns([1.3, 1, 1, 1])
    with col_ins1:
        solo_con_insider = st.checkbox("Solo con Acquisti Insider (90gg)", value=True)
    with col_ins2:
        min_s_score_ins = st.slider("S-Score minimo", 0, 90, 55, step=5)
    with col_ins3:
        max_dist_min = st.slider("Max dist. minimi 52w (%)", 5, 60, 30)
    with col_ins4:
        avvia_ins = st.button("🔍 Scansiona Insider & Minimi", type="primary", use_container_width=True)

    if avvia_ins:
        # Usa sempre la Watchlist reale dello Scanner e legge 'Ticker' (maiuscolo) dal portafoglio
        _wl_raw_ins = st.session_state.get('tickers_input') or (tickers_input if 'tickers_input' in locals() else '') or impostazioni.get('lista_ticker_default', '')
        wl_attuale = [t.strip().upper() for t in str(_wl_raw_ins).replace('\n', ',').split(',') if t.strip()]
        _port_data = st.session_state.get('portafoglio') or (carica_json(PORTAFOGLIO_FILE) if 'carica_json' in globals() else [])
        _port_tks = [str(p.get('Ticker') or p.get('ticker') or '').strip().upper() for p in _port_data if isinstance(p, dict) and (p.get('Ticker') or p.get('ticker'))] if isinstance(_port_data, list) else []
        lista_tot = sorted(list(set(wl_attuale) | set(_port_tks) | set(PANIER_INSIDER_MID_LARGE)))
        risultati_ins = []
        prog_bar = st.progress(0, text="Analisi transazioni Insider e minimi in corso...")
        for idx_i, tk_i in enumerate(lista_tot):
            prog_bar.progress((idx_i + 1) / len(lista_tot), text=f"Scansione {tk_i} ({idx_i+1}/{len(lista_tot)})...")
            res_i = analizza_insider_e_minimi(tk_i)
            if res_i:
                if solo_con_insider and res_i['_buys'] == 0:
                    continue
                if res_i['S-Score'] < min_s_score_ins:
                    continue
                _promossi_file = 'insider_promossi.json'
                _promossi = (carica_json(_promossi_file) or {}) if 'carica_json' in globals() else {}
                if not isinstance(_promossi, dict): _promossi = {}
                _t_code = res_i['Ticker']
                _l_buy = res_i.get('_last_buy_str', '')
                # Se già promosso per questo stesso acquisto insider, nascondilo finché non c'è un nuovo acquisto
                _prev_b = _promossi[_t_code].get('data_acquisto', '') if isinstance(_promossi.get(_t_code), dict) else str(_promossi.get(_t_code, ''))
                if _t_code in _promossi and _prev_b >= _l_buy and _l_buy != '':
                    continue
                # Se è salito troppo (> +18% da acquisto insider o RSI > 68) ma è buona azienda (S-Score >= 65) -> sposta in Watchlist
                if (res_i.get('_var_ins', 0) > 18.0 or res_i['RSI'] > 68) and res_i['S-Score'] >= 65:
                    if _l_buy:
                        _promossi[_t_code] = {
                            'data_acquisto': _l_buy,
                            'data_promozione': datetime.now().strftime('%Y-%m-%d'),
                            'dettagli': f"{res_i.get('Insider (90gg)', '')} | {res_i.get('Valore Insider $', '')}"
                        }
                        if 'salva_json' in globals(): salva_json(_promossi_file, _promossi)
                    _imp = (carica_json(IMPOSTAZIONI_FILE) or {}) if 'carica_json' in globals() else {}
                    if not isinstance(_imp, dict): _imp = {}
                    _wl_str = _imp.get('lista_ticker_default', '')
                    _wl_list = [x.strip().upper() for x in _wl_str.split(',') if x.strip()]
                    if _t_code not in _wl_list:
                        _wl_list.append(_t_code)
                        _imp['lista_ticker_default'] = ', '.join(_wl_list)
                        if 'salva_json' in globals(): salva_json(IMPOSTAZIONI_FILE, _imp)
                    st.session_state.setdefault('insider_promossi_oggi', []).append(_t_code)
                    continue
                if float(str(res_i['Dist. Min 52w %']).replace('+','').replace('%','').replace('nan','0')) <= max_dist_min or res_i['_buys'] >= 2:
                    _, stag_txt = calcola_stagionalita_10y(tk_i)
                    res_i['Stagionalità 60gg'] = stag_txt or "N/D"
                    if stag_txt and stag_txt.startswith('+'):
                        res_i['Score'] += 10
                    risultati_ins.append(res_i)
        prog_bar.empty()
        risultati_ins.sort(key=lambda x: (x['Score'], x['S-Score']), reverse=True)
        for idx_r, item_r in enumerate(risultati_ins):
            medal = "🥇 #1 TOP" if idx_r == 0 else ("🥈 #2" if idx_r == 1 else ("🥉 #3" if idx_r == 2 else f"#{idx_r+1}"))
            item_r['Scelta'] = medal
        st.session_state.insider_results = risultati_ins
        if st.session_state.get('insider_promossi_oggi'): st.info(f"📲 **Promossi in Watchlist MATRIX** (già saliti troppo, in attesa di pullback): {', '.join(st.session_state['insider_promossi_oggi'])}")

    ins_res = st.session_state.get('insider_results', [])
    if ins_res:
        df_ins_view = pd.DataFrame(ins_res).drop(columns=['_buys', '_var_ins', '_last_buy_str', '_sec_dettagli'], errors='ignore')
        if 'Scelta' in df_ins_view.columns:
            cols_order = ['Scelta'] + [c for c in df_ins_view.columns if c != 'Scelta']
            df_ins_view = df_ins_view[cols_order]
        st.dataframe(df_ins_view, use_container_width=True, hide_index=True)
    elif avvia_ins:
        st.info("Nessun titolo trovato con i filtri attuali. Prova ad allargare la distanza dai minimi o deseleziona il filtro solo Insider.")

    st.markdown("---")
    st.markdown("#### 📅 Analisi Dettagliata Stagionalità & Grafico Singolo")
    default_tk_ins = ins_res[0]['Ticker'] if ins_res else "TTMI"
    c_sel1, c_sel2 = st.columns([1.5, 3])
    with c_sel1:
        tk_stag = st.text_input("Ticker da analizzare (es. TTMI, MTDR, BSX):", value=default_tk_ins).strip().upper()
    if tk_stag:
        df_stag_chart, stag_summary = calcola_stagionalita_10y(tk_stag)
        det_singolo = analizza_insider_e_minimi(tk_stag)
        _sec_tab_det = []
        if det_singolo:
            m1, m2, m3, m4 = st.columns(4)
            _delta_ins = det_singolo.get('Valore Insider $', '$0') if det_singolo.get('_buys', 0) > 0 else det_singolo.get('Fonte', 'SEC Form 4')
            m1.metric("Insider Buys (90gg)", det_singolo['Insider (90gg)'], _delta_ins)
            m2.metric("Sconto Fair Value", str(det_singolo["Sconto FV %"]))
            m3.metric("Distanza Min 52w", str(det_singolo["Dist. Min 52w %"]))
            m4.metric("Stagionalità 60gg", stag_summary or "N/D")
            _sec_tab_det = det_singolo.get('_sec_dettagli') or []
        else:
            # Anche su titoli con meno di 60 candele interroga comunque i Form 4 ufficiali SEC
            _sec_fb = get_sec_insider_buys_90gg(tk_stag)
            if isinstance(_sec_fb, dict) and _sec_fb.get("buys", 0) > 0:
                st.metric("Insider Buys (90gg — SEC Form 4)", f"{_sec_fb['buys']} acq ({_sec_fb['num_insider']} dir.)", f"${_sec_fb['valore_usd']:,.0f}")
                _sec_tab_det = _sec_fb.get("dettagli") or []
        if _sec_tab_det:
            st.markdown(f"**🕵️ Dettaglio Acquisti Insider Ufficiali (SEC Form 4 / 90gg) — {tk_stag}:**")
            st.dataframe(pd.DataFrame(_sec_tab_det), use_container_width=True, hide_index=True)
        else:
            st.caption(f"🕵️ SEC Form 4 (90gg): nessun acquisto sul mercato aperto (codice P) rilevato per {tk_stag}.")
        if df_stag_chart is not None and not df_stag_chart.empty:
            colors_s = ['#089981' if v >= 0 else '#F23645' for v in df_stag_chart['Rendimento_Medio']]
            fig_s = go.Figure(go.Bar(
                x=df_stag_chart['Mese'],
                y=df_stag_chart['Rendimento_Medio'],
                marker_color=colors_s,
                text=[f"{v:+.1f}%<br>({int(w)}% pos)" for v, w in zip(df_stag_chart['Rendimento_Medio'], df_stag_chart['Win_Rate'])],
                textposition='outside'
            ))
            fig_s.update_layout(
                title=f"Stagionalità Media Mensile 10 Anni — {tk_stag}",
                height=380,
                template="plotly_dark",
                paper_bgcolor='#131722',
                plot_bgcolor='#0B0E11',
                margin=dict(l=15, r=15, t=45, b=20),
                yaxis_title="Rendimento Medio %"
            )
            st.plotly_chart(fig_s, use_container_width=True, config={'displayModeBar': False})
