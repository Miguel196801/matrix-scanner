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
from datetime import date, datetime, timedelta, timezone

def _get_tz_italia():
    """Restituisce il fuso orario italiano (ZoneInfo Europe/Rome) con fallback UTC+1."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Rome")
    except Exception:
        return timezone(timedelta(hours=1))

def _now_italia():
    """Restituisce data e ora correnti nel fuso orario italiano (anche su Streamlit Cloud UTC)."""
    return datetime.now(_get_tz_italia())

# ==============================================================================
# CALENDARIO AUTOMATICO CHIUSURE & ORARI RIDOTTI BORSA USA (NYSE / NASDAQ)
# ==============================================================================
def _calcola_pasqua_gregoriana(anno):
    """Calcola la data della Domenica di Pasqua gregoriana (algoritmo di Butcher/Meeus)."""
    a = anno % 19
    b = anno // 100
    c = anno % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese = (h + l - 7 * m + 114) // 31
    giorno = ((h + l - 7 * m + 114) % 31) + 1
    return date(anno, mese, giorno)

def _nth_weekday_of_month(anno, mese, weekday, n):
    """Restituisce l'n-esimo giorno della settimana (0=Lun .. 6=Dom) nel mese indicato."""
    primo = date(anno, mese, 1)
    offset = (weekday - primo.weekday()) % 7
    return primo + timedelta(days=offset + (n - 1) * 7)

def _last_weekday_of_month(anno, mese, weekday):
    """Restituisce l'ultimo giorno della settimana (0=Lun .. 6=Dom) nel mese indicato."""
    ultimo = date(anno + 1, 1, 1) - timedelta(days=1) if mese == 12 else date(anno, mese + 1, 1) - timedelta(days=1)
    offset = (ultimo.weekday() - weekday) % 7
    return ultimo - timedelta(days=offset)

def _osservanza_nyse(data_festa, permetti_anno_precedente=True):
    """
    Applica la regola di compensazione (observed) NYSE/Nasdaq:
    - Sabato -> Venerdì precedente (eccetto il 1° Gennaio che per regola NYSE non chiude il 31 Dic).
    - Domenica -> Lunedì successivo.
    """
    wd = data_festa.weekday()
    if wd == 5:
        if not permetti_anno_precedente and data_festa.month == 1 and data_festa.day == 1:
            return None
        return data_festa - timedelta(days=1)
    if wd == 6:
        return data_festa + timedelta(days=1)
    return data_festa

def _get_calendario_nyse_anno(anno):
    """
    Calcola automaticamente per l'anno indicato:
    - chiusure: dict {date: nome_festivita} di tutte le chiusure feriali NYSE / Nasdaq
      (Capodanno, MLK Day, Presidents' Day, Venerdì Santo, Memorial Day, Juneteenth,
      Independence Day, Labor Day, Thanksgiving Day, Natale + giorni compensativi observed).
    - orari_ridotti: dict {date: nome_evento} delle sedute con chiusura anticipata alle 19:00 italiane
      (Black Friday, Vigilia Independence Day 3 Lug feriale, Vigilia Natale 24 Dic feriale).
    """
    chiusure = {}
    orari_ridotti = {}

    # 1) Capodanno (New Year's Day — 1 Gennaio; se sabato non chiude il 31 Dic precedente)
    nyd_obs = _osservanza_nyse(date(anno, 1, 1), permetti_anno_precedente=False)
    if nyd_obs is not None and nyd_obs.year == anno:
        suff = " (osservato)" if nyd_obs != date(anno, 1, 1) else ""
        chiusure[nyd_obs] = f"Capodanno / New Year's Day{suff}"

    # 2) Martin Luther King Jr. Day (3° lunedì di Gennaio)
    chiusure[_nth_weekday_of_month(anno, 1, 0, 3)] = "Martin Luther King Jr. Day"

    # 3) Presidents' Day (3° lunedì di Febbraio)
    chiusure[_nth_weekday_of_month(anno, 2, 0, 3)] = "Presidents' Day"

    # 4) Venerdì Santo / Good Friday (Pasqua - 2 giorni)
    good_friday = _calcola_pasqua_gregoriana(anno) - timedelta(days=2)
    chiusure[good_friday] = "Venerdì Santo / Good Friday"

    # 5) Memorial Day (ultimo lunedì di Maggio)
    chiusure[_last_weekday_of_month(anno, 5, 0)] = "Memorial Day"

    # 6) Juneteenth National Independence Day (19 Giugno, con osservanza Ven/Lun)
    j19_obs = _osservanza_nyse(date(anno, 6, 19))
    if j19_obs is not None:
        suff = " (osservato)" if j19_obs != date(anno, 6, 19) else ""
        chiusure[j19_obs] = f"Juneteenth National Independence Day{suff}"

    # 7) Independence Day (4 Luglio, con osservanza Ven/Lun)
    ind_obs = _osservanza_nyse(date(anno, 7, 4))
    if ind_obs is not None:
        suff = " (osservato)" if ind_obs != date(anno, 7, 4) else ""
        chiusure[ind_obs] = f"Independence Day{suff}"

    # 8) Labor Day (1° lunedì di Settembre)
    chiusure[_nth_weekday_of_month(anno, 9, 0, 1)] = "Labor Day"

    # 9) Thanksgiving Day (4° giovedì di Novembre)
    thanksgiving = _nth_weekday_of_month(anno, 11, 3, 4)
    chiusure[thanksgiving] = "Thanksgiving Day"

    # 10) Natale / Christmas Day (25 Dicembre, con osservanza Ven/Lun)
    xmas_obs = _osservanza_nyse(date(anno, 12, 25))
    if xmas_obs is not None:
        suff = " (osservato)" if xmas_obs != date(anno, 12, 25) else ""
        chiusure[xmas_obs] = f"Natale / Christmas Day{suff}"

    # --- CHIUSURE ANTICIPATE ALLE 19:00 ITALIANE (13:00 ET) ---
    # A) Black Friday (venerdì successivo al Thanksgiving)
    black_friday = thanksgiving + timedelta(days=1)
    if black_friday.weekday() < 5 and black_friday not in chiusure:
        orari_ridotti[black_friday] = "Black Friday"

    # B) Vigilia Independence Day (3 Luglio feriale, se non già chiuso per observed 4 Luglio)
    vig_luglio = date(anno, 7, 3)
    if vig_luglio.weekday() < 5 and vig_luglio not in chiusure:
        orari_ridotti[vig_luglio] = "Vigilia Independence Day"

    # C) Vigilia di Natale (24 Dicembre feriale, se non già chiuso per observed 25 Dicembre)
    vig_natale = date(anno, 12, 24)
    if vig_natale.weekday() < 5 and vig_natale not in chiusure:
        orari_ridotti[vig_natale] = "Vigilia di Natale"

    return chiusure, orari_ridotti

def _analizza_stato_borsa_usa_oggi_domani(data_rif=None):
    """
    Verifica con fuso orario italiano (ZoneInfo Europe/Rome) eventuali festività
    o chiusure anticipate (19:00 italiane) di NYSE / Nasdaq per OGGI e DOMANI.
    Restituisce una lista di avvisi pronti per il rendering banner.
    """
    oggi = data_rif or _now_italia().date()
    domani = oggi + timedelta(days=1)
    chiusure, orari_ridotti = _get_calendario_nyse_anno(oggi.year)
    if domani.year != oggi.year:
        ch_next, rid_next = _get_calendario_nyse_anno(domani.year)
        chiusure.update(ch_next)
        orari_ridotti.update(rid_next)

    avvisi = []
    if oggi.weekday() < 5 and oggi in chiusure:
        avvisi.append({
            "tipo": "chiusa_oggi",
            "testo": f"🇺🇸 BORSA USA CHIUSA OGGI ({chiusure[oggi]}) — Nessuna contrattazione fino alla prossima apertura.",
        })
    elif oggi.weekday() < 5 and oggi in orari_ridotti:
        avvisi.append({
            "tipo": "ridotto_oggi",
            "testo": f"⏰ ORARIO RIDOTTO BORSA USA: Oggi Wall Street chiude in anticipo alle 19:00 italiane ({orari_ridotti[oggi]}).",
        })

    if domani.weekday() < 5 and domani in chiusure:
        avvisi.append({
            "tipo": "chiusa_domani",
            "testo": f"📅 AVVISO: DOMANI BORSA USA CHIUSA ({chiusure[domani]}) — Wall Street resterà chiusa.",
        })
    elif domani.weekday() < 5 and domani in orari_ridotti:
        avvisi.append({
            "tipo": "ridotto_domani",
            "testo": f"⏰ ORARIO RIDOTTO BORSA USA: Domani Wall Street chiude in anticipo alle 19:00 italiane ({orari_ridotti[domani]}).",
        })
    return avvisi

def render_banner_calendario_borsa_usa():
    """Mostra eventuali banner ad alto contrasto su chiusure feriali o orari ridotti NYSE / Nasdaq."""
    avvisi = _analizza_stato_borsa_usa_oggi_domani()
    if not avvisi:
        return
    stili = {
        "chiusa_oggi": ("#2B1418", "#EF4444", "#FEE2E2"),
        "chiusa_domani": ("#2A1F0D", "#F59E0B", "#FEF3C7"),
        "ridotto_oggi": ("#0F2436", "#38BDF8", "#E0F2FE"),
        "ridotto_domani": ("#0F2436", "#38BDF8", "#E0F2FE"),
    }
    blocchi = []
    for av in avvisi:
        bg, brd, fg = stili.get(av["tipo"], ("#1E293B", "#64748B", "#F8FAFC"))
        blocchi.append(
            f"<div style='background:{bg}; border:1px solid {brd}; border-left:5px solid {brd}; "
            f"border-radius:10px; padding:0.65rem 1.05rem; margin-bottom:0.55rem; "
            f"color:{fg}; font-size:0.92rem; font-weight:700; line-height:1.35;'>"
            f"{av['testo']}</div>"
        )
    st.markdown("".join(blocchi), unsafe_allow_html=True)

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
        "capitale_versato_default": 0.00,
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
        "vista_attiva", "home_cascata_eseguita", "home_salute_portafoglio",
        "risultati_radar_ignition_80", "insider_results",
        "insider_promossi_oggi", "ai_palantir_candidati",
        "home_anteprima_punto_attiva", "_home_hash_caricato",
        "home_snapshot_decisionale", "home_tabella_salute_aperta",
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

def _get_data_giornaliera_auth_italia():
    """Restituisce la data odierna nel fuso orario italiano (YYYY-MM-DD) per la firma giornaliera del token."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Rome")).strftime("%Y-%m-%d")
    except Exception:
        from datetime import timezone
        return datetime.now(timezone(timedelta(hours=1))).strftime("%Y-%m-%d")

def _genera_firma_token_auth(username_lower, hashes_utente, data_str):
    """Genera una firma SHA-256 giornaliera legata all'utente e agli hash delle sue credenziali."""
    segreto_extra = ""
    try:
        segreto_extra = str(st.secrets.get("GITHUB_TOKEN", "") or st.secrets.get("AUTH_SECRET", ""))[:16]
    except Exception:
        segreto_extra = ""
    base_hashes = "|".join(sorted([str(h).lower() for h in (hashes_utente or [])]))
    payload = f"MATRIX_PRO_MOBILE_AUTH_V1|{username_lower}|{data_str}|{base_hashes}|{segreto_extra}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

def _genera_token_auth_url(username):
    """Crea il token firmato '<utente>:<firma_sha256_giornaliera>' da salvare in st.query_params['auth']."""
    u_key = str(username or "").strip().lower()
    if not u_key:
        return ""
    mappa = _carica_mappa_credenziali()
    info = mappa.get(u_key)
    if not info:
        return ""
    data_oggi = _get_data_giornaliera_auth_italia()
    firma = _genera_firma_token_auth(u_key, info.get("hashes", []), data_oggi)
    return f"{u_key}:{firma}"

def _verifica_token_auth_url(token_raw):
    """Verifica il token firmato letto da st.query_params['auth'] e restituisce (valido, nome_canonico)."""
    tok = str(token_raw or "").strip()
    if ":" not in tok:
        return False, ""
    u_part, sig_part = tok.split(":", 1)
    u_key = u_part.strip().lower()
    sig_clean = sig_part.strip().lower()
    if not u_key or not sig_clean:
        return False, ""
    mappa = _carica_mappa_credenziali()
    info = mappa.get(u_key)
    if not info:
        return False, ""
    data_oggi = _get_data_giornaliera_auth_italia()
    firma_attesa = _genera_firma_token_auth(u_key, info.get("hashes", []), data_oggi)
    if hmac.compare_digest(sig_clean, firma_attesa):
        return True, info["username"]
    return False, ""

def richiedi_login_matrix():
    """
    Blocca l'accesso all'intera app finché st.session_state['autenticato'] non è True.
    Supporta sessione persistente su browser mobile tramite token firmato giornaliero in st.query_params['auth'].
    """
    if "autenticato" not in st.session_state:
        st.session_state["autenticato"] = False
    if st.session_state["autenticato"]:
        return

    # Assicura che utenti_auth.json venga inizializzato già al primo avvio
    _assicura_file_utenti_auth()

    # Ripristino automatico sessione al ricaricamento del browser mobile (es. ritorno da Trade Republic)
    try:
        tok_url = st.query_params.get("auth")
        if isinstance(tok_url, list):
            tok_url = tok_url[0] if tok_url else ""
        if tok_url:
            ok_tok, nome_tok = _verifica_token_auth_url(tok_url)
            if ok_tok:
                st.session_state["autenticato"] = True
                st.session_state["utente_corrente"] = nome_tok
                st.session_state["utente_autenticato"] = nome_tok
                return
            else:
                # Token scaduto o non valido: ripulisce il parametro URL
                st.query_params.clear()
    except Exception:
        pass

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

    # Racchiude la UI di Login in uno slot svuotabile così al click su Accedi scompare subito senza residui DOM
    login_slot = st.empty()
    with login_slot.container():
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
                        # Salva il token firmato giornaliero nei parametri URL per sessione persistente su Mobile
                        try:
                            tok_nuovo = _genera_token_auth_url(nome_valido)
                            if tok_nuovo:
                                st.query_params["auth"] = tok_nuovo
                        except Exception:
                            pass
                        # Rimuove subito dal DOM la card di Login prima del rerun (evita sovrapposizioni fantasma)
                        login_slot.empty()
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
    if st.sidebar.button("🚪 Esci (Logout)", use_container_width=True, key="btn_logout_matrix"):
        st.session_state["autenticato"] = False
        st.session_state.pop("utente_corrente", None)
        st.session_state.pop("utente_autenticato", None)
        _reset_sessione_utente()
        # Svuota i parametri URL (incluso il token auth) per chiudere pulitamente la sessione
        try:
            st.query_params.clear()
        except Exception:
            pass
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


def _invia_notifica_telegram(utente, messaggio):
    """Wrapper sicuro per notifiche push Telegram separate per membro Famiglia (legge solo da st.secrets)."""
    try:
        if "regia_tracker" in globals() and hasattr(regia_tracker, "_invia_notifica_telegram"):
            return bool(regia_tracker._invia_notifica_telegram(utente, messaggio))
    except Exception:
        pass
    return False

OPZIONI_MOTIVO_ACQUISTO = [
    "DCA Binario 1 (Pullback Fase 2)",
    "DCA Binario 2 (Supporto)",
    "Breakout Matrix",
    "Radar IGNITION 80",
    "Setup Palantir AI",
    "Switch Riserva Intelligente",
    "Cluster Insider SEC",
    "Manuale / Discrezionale",
]

OPZIONI_MOTIVO_VENDITA = [
    "Presa Profitto >= +35%",
    "Target Raggiunto",
    "Stop Loss",
    "Switch Riserva Intelligente",
    "Deterioramento Strutturale (Fase 4)",
    "Manuale / Discrezionale",
]

def _rileva_motivo_segnale_ticker(ticker, lato="ACQUISTO"):
    """
    Rileva automaticamente il motivo/segnale operativo attivo per il ticker indicato
    ispezionando st.session_state (Home Page Pilota Automatico, Scanner, Radar IGNITION,
    Setup Palantir, Insider SEC, Salute Portafoglio) e la Bacheca Segnali Attivi.
    Restituisce una voce valida di OPZIONI_MOTIVO_ACQUISTO o OPZIONI_MOTIVO_VENDITA.
    """
    tk = str(ticker or "").strip().upper()
    lato_u = str(lato or "ACQUISTO").strip().upper()
    if not tk:
        return "Manuale / Discrezionale"

    snap_dec = st.session_state.get("home_snapshot_decisionale") or {}
    bacheca = st.session_state.get("bacheca_segnali_attivi")
    if not isinstance(bacheca, dict):
        try:
            bacheca = _carica_segnali_attivi()
        except Exception:
            bacheca = {"aperti": [], "chiusi": []}

    if lato_u == "VENDITA":
        # 1) Riserva Intelligente Fonte A / Fonte B (Switch o Presa Profitto >= +35%)
        riserva = snap_dec.get("riserva") or {}
        if str(riserva.get("ticker", "")).strip().upper() == tk:
            fonte_r = str(riserva.get("fonte", "")).upper()
            if "FONTE A" in fonte_r or float(riserva.get("pnl_pct") or 0.0) >= 35.0:
                if snap_dec.get("top1_cand"):
                    return "Switch Riserva Intelligente"
                return "Presa Profitto >= +35%"
            return "Switch Riserva Intelligente"

        # 2) Alert espliciti di Take Profit
        for tp in (st.session_state.get("take_profit_alerts") or []):
            tp_tk = str(tp.get("Ticker") or tp.get("ticker") or "").strip().upper() if isinstance(tp, dict) else str(tp).strip().upper()
            if tp_tk == tk:
                return "Presa Profitto >= +35%"

        # 3) Salute Portafoglio (P&L >= +35%, Stop Loss, Deterioramento Fase 4)
        salute_map = st.session_state.get("home_salute_portafoglio") or {}
        inf_sal = None
        if isinstance(salute_map, dict):
            inf_sal = salute_map.get(tk)
        elif isinstance(salute_map, list):
            for row_s in salute_map:
                if isinstance(row_s, dict) and str(row_s.get("Ticker") or row_s.get("ticker") or "").strip().upper() == tk:
                    inf_sal = row_s
                    break
        if isinstance(inf_sal, dict):
            pnl_s = float(inf_sal.get("pnl_pct") or 0.0)
            fase_s = str(inf_sal.get("fase") or "").upper()
            stato_s = str(inf_sal.get("stato") or inf_sal.get("verdetto") or inf_sal.get("azione") or "").upper()
            if pnl_s >= 35.0:
                return "Presa Profitto >= +35%"
            if "STOP" in stato_s:
                return "Stop Loss"
            if "FASE 4" in fase_s or "DETERIOR" in stato_s:
                return "Deterioramento Strutturale (Fase 4)"
            if "TARGET" in stato_s:
                return "Target Raggiunto"

        # 4) Bacheca Segnali Attivi (aperti/chiusi per target o stop)
        for gruppo in ("aperti", "chiusi"):
            for seg in (bacheca.get(gruppo) or []):
                if not isinstance(seg, dict):
                    continue
                if str(seg.get("Ticker") or seg.get("ticker") or "").strip().upper() == tk:
                    esito = str(seg.get("Esito") or seg.get("Stato") or seg.get("stato") or "").upper()
                    if "TARGET" in esito:
                        return "Target Raggiunto"
                    if "STOP" in esito:
                        return "Stop Loss"

        return "Manuale / Discrezionale"

    # --- LATO ACQUISTO / MEDIAZIONE ---
    # 1) Proposta DCA Doppio Binario della Home Page
    dca_cand = snap_dec.get("dca_cand") or {}
    if str(dca_cand.get("ticker", "")).strip().upper() == tk:
        return "DCA Binario 1 (Pullback Fase 2)" if int(dca_cand.get("binario") or 1) == 1 else "DCA Binario 2 (Supporto)"

    # 2) Top 1 Unico della Home Page (incluso eventuale Switch da Riserva Intelligente)
    top1_cand = snap_dec.get("top1_cand") or {}
    if str(top1_cand.get("ticker", "")).strip().upper() == tk:
        riserva = snap_dec.get("riserva") or {}
        liq_alloc = float(st.session_state.get("liquidita_totale_alloc") or 0.0)
        if riserva and liq_alloc < 40.0:
            return "Switch Riserva Intelligente"
        motori_txt = " ".join([str(m) for m in (top1_cand.get("motori") or [])]).upper()
        if top1_cand.get("is_breakout_matrix") or "BREAKOUT" in motori_txt or "MATRIX" in motori_txt:
            return "Breakout Matrix"
        if "IGNITION" in motori_txt:
            return "Radar IGNITION 80"
        if "PALANTIR" in motori_txt:
            return "Setup Palantir AI"
        if int(top1_cand.get("sec_buys") or 0) >= 1:
            return "Cluster Insider SEC"
        return "Breakout Matrix"

    # 3) Bacheca Segnali Attivi (segnali aperti)
    for seg in (bacheca.get("aperti") or []):
        if not isinstance(seg, dict):
            continue
        if str(seg.get("Ticker") or seg.get("ticker") or "").strip().upper() == tk:
            fonte_s = f"{seg.get('Fonte', '')} {seg.get('Pattern', '')} {seg.get('Motivo', '')}".upper()
            if "INSIDER" in fonte_s:
                return "Cluster Insider SEC"
            if "IGNITION" in fonte_s:
                return "Radar IGNITION 80"
            if "PALANTIR" in fonte_s:
                return "Setup Palantir AI"
            return "Breakout Matrix"

    # 4) Radar IGNITION 80
    for r_ig in (st.session_state.get("risultati_radar_ignition_80") or []):
        if isinstance(r_ig, dict) and str(r_ig.get("Ticker") or r_ig.get("ticker") or "").strip().upper() == tk:
            return "Radar IGNITION 80"

    # 5) Setup Palantir AI
    for r_pl in (st.session_state.get("ai_palantir_candidati") or []):
        if isinstance(r_pl, dict) and str(r_pl.get("Ticker") or r_pl.get("ticker") or "").strip().upper() == tk:
            return "Setup Palantir AI"

    # 6) Pattern / Breakout Matrix & Pyramiding
    pat_alerts = st.session_state.get("pattern_alerts") or {}
    if isinstance(pat_alerts, dict) and tk in {str(k).strip().upper() for k in pat_alerts.keys()}:
        return "Breakout Matrix"
    for pyr in (st.session_state.get("pyramiding_alerts") or []):
        pyr_tk = str(pyr.get("Ticker") or pyr.get("ticker") or "").strip().upper() if isinstance(pyr, dict) else str(pyr).strip().upper()
        if pyr_tk == tk:
            return "Breakout Matrix"

    # 7) Cluster Insider SEC
    for ins_r in (st.session_state.get("insider_results") or []):
        if isinstance(ins_r, dict) and str(ins_r.get("Ticker") or ins_r.get("ticker") or "").strip().upper() == tk:
            return "Cluster Insider SEC"

    return "Manuale / Discrezionale"

OPZIONI_TIPO_ACQUISTO_UI = [
    "Spot (Tattico / Segnale MATRIX)",
    "PAC (Accumulo Fisso)",
]

def _normalizza_tipo_operazione(val_tipo):
    """Normalizza l'etichetta UI o storica del tipo operazione in 'PAC' oppure 'Spot'."""
    s = str(val_tipo or "Spot").strip().upper()
    if s.startswith("PAC") and "SPOT" not in s:
        return "PAC"
    return "Spot"

# Soglia minima anti-briciole per il raccolto parziale 50% Fonte A (€ netti dopo tasse 26% e commissioni TR)
SOGLIA_MIN_NETTO_FONTE_A = 100.0

def _commissione_default_tr(lato="ACQUISTO", tipo_op="Spot"):
    """
    Restituisce la commissione Trade Republic predefinita in Euro:
    - Acquisto PAC: 0.00 €
    - Acquisto Spot: 1.00 €
    - Qualsiasi Vendita (inclusa vendita/chiusura PAC): 1.00 €
    """
    if str(lato or "ACQUISTO").strip().upper() == "VENDITA":
        return 1.0
    return 0.0 if _normalizza_tipo_operazione(tipo_op) == "PAC" else 1.0

def _calcola_ripartizione_pac_spot(pos):
    """
    Calcola in modo retrocompatibile (q_pac, q_spot) per una posizione in portafoglio
    garantendo che la somma corrisponda alla Quantita totale (PMC fiscale unico Trade Republic).
    """
    q_tot = round(max(0.0, float((pos or {}).get("Quantita", 0) or 0)), 6)
    if q_tot <= 0:
        return 0.0, 0.0
    has_pac = (pos or {}).get("Quantita_PAC") is not None
    has_spot = (pos or {}).get("Quantita_Spot") is not None
    if has_pac or has_spot:
        q_pac = round(max(0.0, float((pos or {}).get("Quantita_PAC", 0) or 0)), 6)
        q_spot = round(max(0.0, float((pos or {}).get("Quantita_Spot", 0) or 0)), 6)
        somma = round(q_pac + q_spot, 6)
        if abs(somma - q_tot) > 1e-4:
            if somma > 0:
                q_pac = round(min(q_pac, q_tot), 6)
                q_spot = round(max(0.0, q_tot - q_pac), 6)
            else:
                if _normalizza_tipo_operazione((pos or {}).get("Tipo", "Spot")) == "PAC":
                    return q_tot, 0.0
                return 0.0, q_tot
        return q_pac, q_spot
    if _normalizza_tipo_operazione((pos or {}).get("Tipo", "Spot")) == "PAC":
        return q_tot, 0.0
    return 0.0, q_tot

def _formatta_badge_tipo_posizione(pos, con_dettaglio=False):
    """Restituisce 'PAC + Spot', 'PAC' o 'Spot' (con dettaglio opzionale delle quote)."""
    q_pac, q_spot = _calcola_ripartizione_pac_spot(pos)
    if q_pac > 1e-6 and q_spot > 1e-6:
        return f"PAC + Spot ({q_pac:.2f} PAC + {q_spot:.2f} Spot)" if con_dettaglio else "PAC + Spot"
    if q_pac > 1e-6:
        return "PAC"
    return "Spot"

def _aggiorna_ripartizione_acquisto(pos, qta_add, tipo_acq):
    """
    Aggiorna Quantita_PAC, Quantita_Spot e Tipo della posizione dopo un acquisto/mediazione,
    preservando il PMC fiscale unificato Trade Republic.
    """
    q_pac_old, q_spot_old = _calcola_ripartizione_pac_spot(pos)
    q_add_f = round(max(0.0, float(qta_add or 0)), 6)
    tipo_n = _normalizza_tipo_operazione(tipo_acq)
    if tipo_n == "PAC":
        q_pac_new = round(q_pac_old + q_add_f, 6)
        q_spot_new = round(q_spot_old, 6)
    else:
        q_pac_new = round(q_pac_old, 6)
        q_spot_new = round(q_spot_old + q_add_f, 6)
    pos["Quantita_PAC"] = q_pac_new
    pos["Quantita_Spot"] = q_spot_new
    if q_pac_new > 1e-6 and q_spot_new > 1e-6:
        pos["Tipo"] = "PAC + Spot"
    elif q_pac_new > 1e-6:
        pos["Tipo"] = "PAC"
    else:
        pos["Tipo"] = "Spot"

def _aggiorna_ripartizione_vendita(pos, qta_vend):
    """
    Scala la quantità venduta dando priorità alle quote tattiche Spot prima delle quote PAC,
    riallineando Quantita_PAC, Quantita_Spot e Tipo della posizione residua.
    """
    q_pac_old, q_spot_old = _calcola_ripartizione_pac_spot(pos)
    q_v = round(max(0.0, float(qta_vend or 0)), 6)
    da_spot = min(q_spot_old, q_v)
    residuo = max(0.0, q_v - da_spot)
    da_pac = min(q_pac_old, residuo)
    q_spot_new = round(max(0.0, q_spot_old - da_spot), 6)
    q_pac_new = round(max(0.0, q_pac_old - da_pac), 6)
    pos["Quantita_PAC"] = q_pac_new
    pos["Quantita_Spot"] = q_spot_new
    if q_pac_new > 1e-6 and q_spot_new > 1e-6:
        pos["Tipo"] = "PAC + Spot"
    elif q_pac_new > 1e-6:
        pos["Tipo"] = "PAC"
    else:
        pos["Tipo"] = "Spot"

OPZIONI_FONTE_FONDI = [
    "💰 Liquidità sul Conto / Vendite",
    "🏦 Nuova Liquidità Versata",
    "🔀 Mista (Conto + Nuova Liquidità)",
]

MESI_ITALIANI_MAP = {
    1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
    5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
    9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre",
}

def _calcola_default_fonte_fondi(costo_totale_eur, tipo_acq="Spot", cassa_disp=None):
    """
    Determina automaticamente la Fonte Fondi consigliata all'acquisto senza complicare l'inserimento:
    - PAC oppure cassa < 1.00 € -> '🏦 Nuova Liquidità Versata'
    - cassa >= costo_totale_eur -> '💰 Liquidità sul Conto / Vendite'
    - 1.00 € <= cassa < costo_totale_eur -> '🔀 Mista (Conto + Nuova Liquidità)'
    Restituisce (fonte_default, quota_cassa, quota_nuova_liq).
    """
    costo = round(max(0.0, float(costo_totale_eur or 0.0)), 2)
    if cassa_disp is None:
        try:
            cassa_disp = max(0.0, float(calcola_liquidita_totale() or 0.0))
        except Exception:
            cassa_disp = 0.0
    cassa = round(max(0.0, float(cassa_disp or 0.0)), 2)
    if _normalizza_tipo_operazione(tipo_acq) == "PAC" or cassa < 1.0:
        return "🏦 Nuova Liquidità Versata", 0.0, costo
    if cassa >= costo:
        return "💰 Liquidità sul Conto / Vendite", costo, 0.0
    return "🔀 Mista (Conto + Nuova Liquidità)", cassa, round(max(0.0, costo - cassa), 2)

def _calcola_quote_fonte_fondi(fonte_scelta, costo_totale_eur, cassa_disp=None):
    """Calcola (quota_da_cassa, quota_nuova_liquidita) coerenti con la fonte scelta dall'utente."""
    costo = round(max(0.0, float(costo_totale_eur or 0.0)), 2)
    if cassa_disp is None:
        try:
            cassa_disp = max(0.0, float(calcola_liquidita_totale() or 0.0))
        except Exception:
            cassa_disp = 0.0
    cassa = round(max(0.0, float(cassa_disp or 0.0)), 2)
    s = str(fonte_scelta or "").upper()
    if "NUOVA" in s and "MISTA" not in s:
        return 0.0, costo
    if "MISTA" in s:
        q_c = round(min(cassa, costo), 2)
        return q_c, round(max(0.0, costo - q_c), 2)
    return costo, 0.0

def _get_tickers_cooldown_vendite(giorni=21, data_rif=None):
    """
    Legge registro_vendite*.json (già sincronizzato su GitHub) e restituisce un dizionario
    {TICKER: giorni_trascorsi} per tutti i titoli venduti negli ultimi `giorni` di calendario.
    Serve come blocco Anti Ping-Pong (21 giorni) per Top 1 BUY e DCA.
    """
    oggi = data_rif or _now_italia().date()
    reg_v = carica_json(REGISTRO_VENDITE_FILE, default=[])
    if not isinstance(reg_v, list):
        return {}
    bloccati = {}
    for v in reg_v:
        if not isinstance(v, dict):
            continue
        tk = str(v.get("Ticker") or "").strip().upper()
        dt_s = str(v.get("Data") or "").strip()[:10]
        if not tk or len(dt_s) < 10:
            continue
        try:
            dt_v = datetime.strptime(dt_s, "%Y-%m-%d").date()
            diff_gg = (oggi - dt_v).days
            if 0 <= diff_gg <= int(giorni):
                if tk not in bloccati or diff_gg < bloccati[tk]:
                    bloccati[tk] = diff_gg
        except Exception:
            continue
    return bloccati

def _calcola_bilancio_mensile_flussi():
    """
    Aggrega automaticamente mese per mese (es. 'Novembre 2026') tutti i flussi di capitale
    da registro_vendite*.json e registro_acquisti*.json:
    - Vendite nette (dopo tasse 26% e commissioni TR) + elenco ticker venduti
    - Nuova liquidità versata (totale, quota PAC, quota Spot/DCA)
    - Reinvestito da cassa/vendite
    - Commissioni TR e flusso netto di tasca propria.
    Restituisce lista ordinata per mese decrescente (più recente prima).
    """
    reg_v = carica_json(REGISTRO_VENDITE_FILE, default=[])
    reg_a = carica_json(REGISTRO_ACQUISTI_FILE, default=[])
    mesi = {}

    def _get_mese(ym):
        if ym not in mesi:
            try:
                y_i, m_i = int(ym[:4]), int(ym[5:7])
                lbl = f"{MESI_ITALIANI_MAP.get(m_i, ym)} {y_i}"
            except Exception:
                lbl = ym
            mesi[ym] = {
                "ym": ym,
                "label": lbl,
                "vendite_nette_eur": 0.0,
                "comm_vendite_eur": 0.0,
                "titoli_venduti": [],
                "dettaglio_vendite": [],
                "nuova_liq_tot_eur": 0.0,
                "nuova_liq_pac_eur": 0.0,
                "nuova_liq_spot_eur": 0.0,
                "reinvestito_cassa_eur": 0.0,
                "totale_investito_eur": 0.0,
                "comm_acquisti_eur": 0.0,
                "titoli_acquistati": [],
                "dettaglio_acquisti": [],
            }
        return mesi[ym]

    for v in (reg_v if isinstance(reg_v, list) else []):
        if not isinstance(v, dict):
            continue
        dt_s = str(v.get("Data") or "").strip()[:10]
        if len(dt_s) < 7:
            continue
        ym = dt_s[:7]
        m = _get_mese(ym)
        tk = str(v.get("Ticker") or "").strip().upper()
        qta = float(v.get("Qta_Venduta") or 0.0)
        pv = float(v.get("Prezzo_Vendita") or 0.0)
        tasse = float(v.get("Tasse") or 0.0)
        comm = 1.0 if dt_s >= "2026-11-15" else 0.0
        netto = round((pv * qta) - tasse - comm, 2)
        m["vendite_nette_eur"] = round(m["vendite_nette_eur"] + netto, 2)
        m["comm_vendite_eur"] = round(m["comm_vendite_eur"] + comm, 2)
        if tk and tk not in m["titoli_venduti"]:
            m["titoli_venduti"].append(tk)
        m["dettaglio_vendite"].append({
            "Data": dt_s,
            "Ticker": tk,
            "Incasso Netto €": netto,
            "Tasse €": round(tasse, 2),
            "Comm. TR €": comm,
            "Motivo": v.get("Motivo_Segnale") or "Manuale / Storico",
        })

    for a in (reg_a if isinstance(reg_a, list) else []):
        if not isinstance(a, dict):
            continue
        dt_s = str(a.get("Data") or "").strip()[:10]
        if len(dt_s) < 7:
            continue
        ym = dt_s[:7]
        m = _get_mese(ym)
        tk = str(a.get("Ticker") or "").strip().upper()
        tp = _normalizza_tipo_operazione(a.get("Tipo", "Spot"))
        tot = round(float(a.get("Totale_EUR") or (float(a.get("Quantita") or 0.0) * float(a.get("Prezzo_EUR") or 0.0))), 2)
        comm = float(a.get("Commissione_EUR")) if a.get("Commissione_EUR") is not None else _commissione_default_tr("ACQUISTO", tp)
        fonte = str(a.get("Fonte_Fondi") or "")
        if a.get("Quota_Da_Cassa_EUR") is not None or a.get("Quota_Nuova_Liquidita_EUR") is not None:
            q_cassa = round(float(a.get("Quota_Da_Cassa_EUR") or 0.0), 2)
            q_nuova = round(float(a.get("Quota_Nuova_Liquidita_EUR") or 0.0), 2)
        elif "NUOVA" in fonte.upper():
            q_cassa, q_nuova = 0.0, tot
        else:
            q_cassa, q_nuova = tot, 0.0
        m["nuova_liq_tot_eur"] = round(m["nuova_liq_tot_eur"] + q_nuova, 2)
        if tp == "PAC":
            m["nuova_liq_pac_eur"] = round(m["nuova_liq_pac_eur"] + q_nuova, 2)
        else:
            m["nuova_liq_spot_eur"] = round(m["nuova_liq_spot_eur"] + q_nuova, 2)
        m["reinvestito_cassa_eur"] = round(m["reinvestito_cassa_eur"] + q_cassa, 2)
        m["totale_investito_eur"] = round(m["totale_investito_eur"] + tot, 2)
        m["comm_acquisti_eur"] = round(m["comm_acquisti_eur"] + comm, 2)
        if tk and tk not in m["titoli_acquistati"]:
            m["titoli_acquistati"].append(tk)
        m["dettaglio_acquisti"].append({
            "Data": str(a.get("Data") or ""),
            "Ticker": tk,
            "Tipo": tp,
            "Totale €": tot,
            "Da Cassa €": q_cassa,
            "Nuova Liq. €": q_nuova,
            "Fonte Fondi": fonte or ("🏦 Nuova Liquidità Versata" if q_nuova > 0 and q_cassa == 0 else "💰 Liquidità sul Conto / Vendite"),
            "Motivo": a.get("Motivo_Segnale") or "Manuale / Storico",
        })

    risultati = []
    for ym in sorted(mesi.keys(), reverse=True):
        m = mesi[ym]
        m["comm_totali_eur"] = round(m["comm_vendite_eur"] + m["comm_acquisti_eur"], 2)
        m["flusso_netto_tasca_eur"] = round(m["nuova_liq_tot_eur"], 2)
        m["variazione_cassa_mese_eur"] = round(m["vendite_nette_eur"] - m["reinvestito_cassa_eur"], 2)
        risultati.append(m)
    return risultati

def registra_acquisto_storico(
    ticker,
    tipo,
    qta,
    prezzo_eur,
    nota="Acquisto",
    motivo_segnale=None,
    commissione_eur=None,
    fonte_fondi=None,
    quota_da_cassa=None,
    quota_nuova_liquidita=None,
):
    """Registra un acquisto o una mediazione nello storico acquisti (sincronizzato su GitHub) con commissioni TR e Fonte Fondi."""
    try:
        storico = carica_json(REGISTRO_ACQUISTI_FILE, default=[])
        if not isinstance(storico, list):
            storico = []
        tk_u = str(ticker).strip().upper()
        tipo_n = _normalizza_tipo_operazione(tipo)
        comm_tr = round(float(commissione_eur), 2) if commissione_eur is not None else _commissione_default_tr("ACQUISTO", tipo_n)
        tot_eur = round(float(qta) * float(prezzo_eur), 2)
        costo_eff = round(tot_eur + comm_tr, 2)
        if fonte_fondi is None:
            fonte_fin, q_cassa_def, q_nuova_def = _calcola_default_fonte_fondi(costo_eff, tipo_acq=tipo_n)
        else:
            fonte_fin = str(fonte_fondi).strip()
            q_cassa_def, q_nuova_def = _calcola_quote_fonte_fondi(fonte_fin, costo_eff)
        q_cassa_fin = round(float(quota_da_cassa), 2) if quota_da_cassa is not None else q_cassa_def
        q_nuova_fin = round(float(quota_nuova_liquidita), 2) if quota_nuova_liquidita is not None else q_nuova_def
        motivo_fin = str(motivo_segnale).strip() if motivo_segnale else _rileva_motivo_segnale_ticker(tk_u, "ACQUISTO")
        storico.insert(0, {
            "Data": _now_italia().strftime("%Y-%m-%d %H:%M"),
            "Ticker": tk_u,
            "Operazione": nota,
            "Motivo_Segnale": motivo_fin,
            "Tipo": tipo_n,
            "Quantita": round(float(qta), 4),
            "Prezzo_EUR": round(float(prezzo_eur), 4),
            "Commissione_EUR": comm_tr,
            "Totale_EUR": tot_eur,
            "Fonte_Fondi": fonte_fin,
            "Quota_Da_Cassa_EUR": q_cassa_fin,
            "Quota_Nuova_Liquidita_EUR": q_nuova_fin,
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

def _stato_pac_manuale(pos):
    """
    Gestione 100% manuale dello stato PAC (zero automatismi):
    - Se il titolo possiede quote PAC (pure o PAC+Spot): legge esclusivamente il flag manuale 'PAC_Sospeso'.
      * PAC_Sospeso == True  -> '⏸️ PAC Sospeso — Long' (quote PAC comunque protette al 100%)
      * PAC_Sospeso == False -> '🟢 PAC ATTIVO'
    - Se il titolo è solo Spot -> 'N/A'.
    """
    q_pac, _ = _calcola_ripartizione_pac_spot(pos)
    if q_pac <= 1e-6:
        return "N/A"
    return "⏸️ PAC Sospeso — Long" if bool((pos or {}).get("PAC_Sospeso", False)) else "🟢 PAC ATTIVO"

def _estrai_info_posizione_vendibile(ptk, po, df_map):
    """
    Estrae in modo coerente Fase, S-Score, RSI, protezione PAC (100% protette anche se PAC Sospeso)
    e giorni agli utili incrociando portafoglio.json con le metriche fresche dello scanner (df_map).
    """
    m_scan = df_map.get(ptk, {}) if isinstance(df_map, dict) else {}
    fase = str(m_scan.get("Fase") or po.get("Fase") or po.get("fase") or "").upper()
    sc = float(m_scan.get("S_Score") if m_scan.get("S_Score") is not None else (po.get("S_Score", po.get("Score", 0)) or 0))
    rsi = float(m_scan.get("RSI") if m_scan.get("RSI") is not None else (po.get("RSI", 50) or 50))
    # Protezione assoluta delle quote PAC (sia Attive sia Sospese — Long): è vendibile solo un'eventuale quota Spot
    q_pac_p, q_spot_p = _calcola_ripartizione_pac_spot(po)
    solo_pac_protetto = (q_pac_p > 1e-6 and q_spot_p <= 1e-6)
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
    return fase, sc, rsi, solo_pac_protetto, ut

def calcola_regia_acquisti(ign_l, fabio_l, std_l, tp_l, port_l, df_map, cassa_b, liq_ex, escl_s, cat_s, taglia, manual_l=None):
    """
    Regia Acquisti Prioritizzata allineata alle nuove regole del Pilota Automatico:
    - Cooldown Anti Ping-Pong 21 giorni sui titoli venduti di recente (da registro_vendite*.json).
    - Zero hardcode (rimossi NKE/TTD) e zero 'Sfoltimento 0 tasse' in perdita.
    - Protezione assoluta delle quote PAC (anche se PAC Sospeso — Long), Scudo Tom Nash e Insider SEC 90gg.
    - Fonti di finanziamento: solo Fonte A (gain >= +35% o >= +25% con RSI > 72 -> 50%) o Fonte B Spot (-3%..+12%).
    """
    port_m = {str(p.get("Ticker", "")).strip().upper(): p for p in port_l}
    salute_reg = st.session_state.get("home_salute_portafoglio") or {}
    raw = []
    for m_idx, m_tk in enumerate(manual_l or []):
        tk_m = str(m_tk).strip().upper()
        if tk_m and not any(x[0] == tk_m for x in raw):
            raw.append((tk_m, f"PRIORITÀ MANUALE #{m_idx+1}", -100 + m_idx))
    for lst, nome, rk in [(ign_l, "IGNITION", 0), (fabio_l, "BY FABIO", 1), (std_l, "BY Standard", 2)]:
        for item in (lst or []):
            tk = str(item.get("Ticker", item.get("ticker", item)) if isinstance(item, dict) else item).strip().upper()
            if tk and not any(x[0] == tk for x in raw):
                raw.append((tk, nome, rk))
    approvati, scartati = [], []
    _skip_set = regia_tracker.get_ticker_saltati_5gg() if ('regia_tracker' in globals() and hasattr(regia_tracker, 'get_ticker_saltati_5gg')) else set()
    _cooldown_21 = _get_tickers_cooldown_vendite(21)
    for tk, tipo, rk in raw:
        if tk in _cooldown_21:
            scartati.append(f"🚫 **{tk}** ({tipo}): venduto {_cooldown_21[tk]} gg fa — Cooldown Anti Ping-Pong (21 gg)")
            continue
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
            nota = f"Mediazione Spot ({pnl_p:+.1f}%)" if pnl_p < 0 else f"Incremento Spot (+{pnl_p:.1f}%)"
        else:
            nota = "Nuovo ingresso"
        approvati.append((rk, 0 if "2" in fase else 1, -pot, -sc, tk, tipo, pot, sc, nota))
    approvati.sort(key=lambda x: (x[0], x[1], x[2], x[3]))

    # Pool vendibile allineato al Piano B Qualitativo (zero hardcode, zero vendite in loss su aziende sane/PAC)
    pool, tp_set = [], set()
    for ptk, po in port_m.items():
        if ptk in escl_s or ptk in cat_s:
            continue
        va = float(po.get("Valore_Attuale", 0.0) or 0.0)
        vc = float(po.get("Valore_Carico") or (float(po.get("Quantita", 0) or 0) * float(po.get("Prezzo_Medio", 0) or 0)))
        pnl = va - vc
        pnl_pct = ((va / vc) - 1.0) * 100.0 if vc > 0 else float(po.get("PnL_%", 0.0) or 0.0)
        if va <= 0:
            continue
        inf_s = salute_reg.get(ptk) or {}
        fase, sc, rsi, solo_pac, _ = _estrai_info_posizione_vendibile(ptk, po, df_map)
        sec_b = int(inf_s.get("sec_buys") or 0)
        scudo_tn = bool(inf_s.get("scudo_tom_nash"))
        q_pac_p, q_spot_p = _calcola_ripartizione_pac_spot(po)
        q_tot_p = max(1e-6, float(po.get("Quantita", 0) or 0))

        # Fonte A: Raccolto Profitti parziale 50% Spot (gain >= +35% o >= +25% con RSI > 72) solo se netto >= € 100
        if pnl_pct >= 35.0 or (pnl_pct >= 25.0 and rsi > 72.0):
            if q_spot_p > 1e-6:
                frac_a = min(1.0, q_spot_p / q_tot_p) * 0.5
                v_l = va * frac_a
                g_l = max(0.0, pnl * frac_a)
                net_a = round(v_l - (g_l * 0.26) - 2.0, 2)
                if net_a >= SOGLIA_MIN_NETTO_FONTE_A:
                    tp_set.add(ptk)
                    pool.append((1, ptk, net_a, f"💰 Fonte A — Vendi 50% **{ptk}** ({pnl_pct:+.1f}%) → netto **€ {net_a:,.2f}**"))
            continue

        # Fonte B: SOLO quote Spot (protezione assoluta PAC anche se sospesi), no Scudo Tom Nash, no Insider SEC, no Fase 2 forte
        if solo_pac or q_spot_p <= 1e-6:
            continue
        if scudo_tn or sec_b > 0:
            continue
        if ("2" in fase) and sc >= 70:
            continue
        if -3.0 <= pnl_pct <= 12.0:
            frac_s = min(1.0, q_spot_p / q_tot_p)
            v_l = va * frac_s
            g_l = max(0.0, pnl * frac_s)
            net_b = round(v_l - (g_l * 0.26) - 2.0, 2)
            if net_b >= 30.0:
                nota_sp = f" (solo quota Spot {q_spot_p:.2f} az., PAC protetto)" if q_pac_p > 1e-6 else ""
                pool.append((2, ptk, net_b, f"🔄 Fonte B — Switch Spot **{ptk}** ({pnl_pct:+.1f}%{nota_sp}) → netto **€ {net_b:,.2f}**"))

    pool.sort(key=lambda x: (x[0], -x[2], x[1]))

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
    """Carica la bacheca persistente dei segnali attivi dell'utente loggato (su Cloud scarica da GitHub)."""
    dati = carica_json(SEGNALI_ATTIVI_FILE, default={"aperti": [], "chiusi": []})
    if isinstance(dati, dict):
        dati.setdefault("aperti", [])
        dati.setdefault("chiusi", [])
        return dati
    return {"aperti": [], "chiusi": []}

def _salva_segnali_attivi(dati):
    """
    Salva la bacheca segnali attivi dell'utente loggato (max 10 chiusi) su disco locale
    e sincronizza automaticamente SEGNALI_ATTIVI_FILE su GitHub tramite _sync_github_file().
    """
    if not isinstance(dati, dict):
        dati = {"aperti": [], "chiusi": []}
    dati["aperti"] = list(dati.get("aperti") or [])
    dati["chiusi"] = list(dati.get("chiusi") or [])[:10]
    salva_json(SEGNALI_ATTIVI_FILE, dati)
    try:
        st.session_state["bacheca_segnali_attivi"] = dati
    except Exception:
        pass

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
                    sig_arch["data_chiusura"] = _now_italia().strftime("%Y-%m-%d")
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
                ora_best = datetime.fromtimestamp(os.path.getmtime(fp_port), tz=_get_tz_italia()).strftime("%d/%m/%Y %H:%M")
            except Exception:
                ora_best = "-"
        else:
            ora_best = "-"
    if ora_best and ora_best != "-":
        st.session_state["_last_price_update"] = ora_best
    return ora_best

def salva_ultimo_agg_prezzi(ora_str=None):
    # Usa sempre l'ora italiana reale (ZoneInfo Europe/Rome) anche su server Streamlit Cloud in UTC
    nuova_ora = str(ora_str).strip() if ora_str else _now_italia().strftime("%d/%m/%Y %H:%M")
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
    ora_finale = nuova_ora
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

def _classifica_zona_spy_tom_nash(spy_drawdown_pct, vix_valore=None):
    """
    Classifica la fascia macro del Termometro SPY Drawdown a 52 settimane (filosofia Tom Nash):
    - 'sconto': SPY tra -8.0% e -18.0% dai massimi 52w (e VIX <= 35) -> Modalità Sconto Istituzionale.
    - 'bear': SPY oltre -18.0% dai massimi 52w oppure VIX > 35 -> Prudenza Bear Market.
    - 'normale': nessuna correzione significativa.
    """
    dd = float(spy_drawdown_pct) if spy_drawdown_pct is not None else 0.0
    vix_alto = (vix_valore is not None and float(vix_valore) > 35.0)
    if dd <= -18.0 or vix_alto:
        return "bear"
    if dd <= -8.0:
        return "sconto"
    return "normale"

def render_banner_termometro_tom_nash(semaforo_header):
    """Mostra il banner del Termometro Macro SPY Drawdown 52w quando attiva fascia Sconto o Bear Market."""
    if not isinstance(semaforo_header, dict):
        return
    zona = str(semaforo_header.get("zona_sconto_tom_nash") or "normale").lower()
    dd = semaforo_header.get("spy_drawdown_pct")
    vix_v = semaforo_header.get("vix")
    if zona == "normale" or dd is None:
        return
    dd_str = f"{float(dd):.1f}%".replace(".", ",")
    if zona == "sconto":
        st.markdown(
            f"<div style='background:#0F2436; border:1px solid #38BDF8; border-left:5px solid #38BDF8; "
            f"border-radius:10px; padding:0.75rem 1.1rem; margin-bottom:0.75rem; color:#E0F2FE; "
            f"font-size:0.93rem; line-height:1.45;'>"
            f"<b>📉 MODALITÀ SCONTO ISTITUZIONALE (SPY {dd_str} dai massimi 52 settimane):</b> "
            f"il mercato prezza i tassi/dazi mentre gli utili restano forti — vietate vendite nel panico "
            f"e sbloccato DCA mirato sui campioni fondamentali.</div>",
            unsafe_allow_html=True,
        )
    elif zona == "bear":
        vix_note = f" • VIX {float(vix_v):.1f}" if vix_v is not None else ""
        st.markdown(
            f"<div style='background:#2B1418; border:1px solid #F59E0B; border-left:5px solid #F59E0B; "
            f"border-radius:10px; padding:0.75rem 1.1rem; margin-bottom:0.75rem; color:#FEF3C7; "
            f"font-size:0.93rem; line-height:1.45;'>"
            f"<b>🛡️ PRUDENZA BEAR MARKET (SPY {dd_str} dai massimi 52 settimane{vix_note}):</b> "
            f"correzione profonda in corso — vietato svendere aziende sane nel panico, procedi solo "
            f"con piccoli accumuli DCA scaglionati e senza leva.</div>",
            unsafe_allow_html=True,
        )

def calcola_semaforo_mercato():
    try:
        spy = yf.Ticker('SPY').history(period='1y')
        if spy.empty or len(spy) < 10:
            spy = yf.Ticker('SPY').history(period='1mo')
        if spy.empty or len(spy) < 10:
            return {'stato': 'giallo', 'spy_prezzo': None, 'spy_sma10': None, 'spy_high_52w': None, 'spy_drawdown_pct': None, 'zona_sconto_tom_nash': 'normale', 'vix': None, 'messaggio': 'Dati SPY insufficienti'}
        spy['SMA10'] = spy['Close'].rolling(10).mean()
        spy_prezzo = float(spy['Close'].iloc[-1])
        spy_sma10 = float(spy['SMA10'].iloc[-1])
        # Massimo a 52 settimane e Drawdown % dai massimi storici recenti (Termometro Tom Nash)
        serie_high = spy['High'].dropna() if 'High' in spy.columns and not spy['High'].dropna().empty else spy['Close'].dropna()
        spy_high_52w = float(serie_high.max()) if not serie_high.empty else spy_prezzo
        spy_drawdown_pct = round(min(0.0, ((spy_prezzo / spy_high_52w) - 1.0) * 100.0), 2) if spy_high_52w > 0 else 0.0
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
        zona_tn = _classifica_zona_spy_tom_nash(spy_drawdown_pct, vix_valore)
        return {
            'stato': stato,
            'spy_prezzo': round(spy_prezzo, 2),
            'spy_sma10': round(spy_sma10, 2),
            'spy_high_52w': round(spy_high_52w, 2),
            'spy_drawdown_pct': spy_drawdown_pct,
            'zona_sconto_tom_nash': zona_tn,
            'vix': round(vix_valore, 2) if vix_valore else None,
            'messaggio': messaggio
        }
    except Exception as e:
        return {'stato': 'giallo', 'spy_prezzo': None, 'spy_sma10': None, 'spy_high_52w': None, 'spy_drawdown_pct': None, 'zona_sconto_tom_nash': 'normale', 'vix': None, 'messaggio': f'Errore: {str(e)}'}
# ==============================================================================
# MODULO 2: SIMULATORE DI ACQUISTO INTELLIGENTE
# ==============================================================================
def _calcola_profilo_target_simulazione(tk_target, portafoglio, eurusd_rate):
    """
    Calcola il profilo qualitativo (target_score 0-100) e il verdetto sintetico reale
    del Pilota Automatico MATRIX sul titolo simulato (3 Scudi + Motori ufficiali + Fase).
    """
    tk = str(tk_target or "").strip().upper()
    info = _get_info_cached(tk) if "_get_info_cached" in globals() else {}
    hist = _get_single_ohlc_cached(tk, period="1y") if "_get_single_ohlc_cached" in globals() else None
    metriche_scan = (st.session_state.get("dashboard_stats") or {}).get("metriche_scan") or {}
    s_sc = int((metriche_scan.get(tk) or {}).get("S_Score") or calcola_s_score(info) or 50)
    tn_tk = _valuta_fondamentali_tom_nash(info, s_score=s_sc)
    fase_tk = rileva_fase_weinstein(hist) if (hist is not None and not hist.empty and len(hist) >= 50) else "N/D"
    fase_u = str(fase_tk or "N/D").upper()

    # Controllo 3 Scudi + Cooldown 21gg
    cooldown_map = _get_tickers_cooldown_vendite(21) if "_get_tickers_cooldown_vendite" in globals() else {}
    sem_m = st.session_state.get("semaforo_mercato")
    if not isinstance(sem_m, dict) or not sem_m.get("stato"):
        sem_m = calcola_semaforo_mercato() if "calcola_semaforo_mercato" in globals() else {"stato": "giallo"}
    spy_st = str((sem_m or {}).get("stato", "giallo")).lower()
    _, qqq_st, _ = _verifica_qqq_regime_verde() if "_verifica_qqq_regime_verde" in globals() else (False, "giallo", "")
    regime_rosso = (spy_st == "rosso" or str(qqq_st).lower() == "rosso")

    # Esposizione attuale in portafoglio (Scudo 3 > 22%)
    val_tot_p = 0.0
    val_tk_p = 0.0
    for p in (portafoglio or []):
        q_p = float(p.get("Quantita", 0) or 0)
        att_p = float(p.get("Prezzo_Attuale_EUR") or p.get("Prezzo_Medio") or 0)
        v_p = q_p * att_p
        val_tot_p += v_p
        if str(p.get("Ticker", "")).strip().upper() == tk:
            val_tk_p += v_p
    peso_tk = (val_tk_p / val_tot_p * 100.0) if val_tot_p > 0 else 0.0

    # Trimestrali (Scudo 2 <= 10gg)
    gg_ut = (metriche_scan.get(tk) or {}).get("Giorni_Utili")

    # Verifica motori ufficiali MATRIX (Breakout Matrix / Radar IGNITION / Setup Palantir AI)
    pat_alerts = st.session_state.get("pattern_alerts") or {}
    buy_nuovo_list = (pat_alerts.get("buy_nuovo") or []) if isinstance(pat_alerts, dict) else []
    al_pat = next((a for a in buy_nuovo_list if isinstance(a, dict) and str(a.get("ticker", "")).strip().upper() == tk), None)
    if al_pat is None and isinstance(pat_alerts, dict):
        al_per = (pat_alerts.get("per_ticker") or {}).get(tk)
        if isinstance(al_per, dict):
            al_pat = al_per
    radar_rows = st.session_state.get("risultati_radar_ignition_80") or []
    ha_ign = any(
        isinstance(r_ig, dict)
        and str(r_ig.get("Ticker", "")).strip().upper() == tk
        and "ATTIVO" in str(r_ig.get("Stato", "")).upper()
        for r_ig in radar_rows
    )
    pal_cands = st.session_state.get("ai_palantir_candidati") or []
    ha_pal = any(isinstance(r_pl, dict) and str(r_pl.get("Ticker", "")).strip().upper() == tk for r_pl in pal_cands)

    motori = []
    base_sc = 0.0
    sotto_trigger_y = False
    esteso_trigger_y = False
    if isinstance(al_pat, dict):
        stato_tr = str(al_pat.get("stato_trigger", "")).upper()
        dist_y = float(al_pat.get("dist_y_pct", -999.0) or -999.0)
        if "PRE-BREAKOUT" in stato_tr or dist_y < 0.0:
            sotto_trigger_y = True
        elif dist_y > 3.5:
            esteso_trigger_y = True
        else:
            motori.append("Breakout")
            base_sc = max(base_sc, min(74.0, float(al_pat.get("confidenza") or 75.0) * 0.74))
    if ha_ign:
        motori.append("IGNITION")
        base_sc = max(base_sc, 58.0)
    if ha_pal:
        motori.append("Palantir AI")
        base_sc = max(base_sc, 62.0)

    # Calcolo target_score (0-100) comparabile con Hold-Score per il Delta Qualitativo Fonte B
    if motori:
        sc_tot = (
            base_sc
            + (15.0 if len(motori) >= 2 else 0.0)
            + (8.0 if s_sc >= 75 else (4.0 if s_sc >= 65 else 0.0))
            + float(tn_tk.get("bonus_multipli") or 0)
        )
        target_score = int(max(0, min(100, round(sc_tot))))
    else:
        # Score qualitativo intrinseco (coerente con scala Hold-Score 0-100) quando non c'è breakout attivo
        sc_q = min(40.0, max(0.0, (s_sc / 100.0) * 40.0))
        if "FASE 2" in fase_u:
            sc_q += 28.0
        elif "CORREZIONE" in fase_u:
            sc_q += 20.0
        elif "FASE 1" in fase_u:
            sc_q += 15.0
        elif "FASE 3" in fase_u:
            sc_q += 8.0
        if tn_tk.get("scudo_tom_nash"):
            sc_q += 12.0
        sc_q += float(tn_tk.get("bonus_multipli") or 0)
        target_score = int(max(0, min(100, round(sc_q))))

    # Frase sintetica in due parole sul verdetto reale del Pilota Automatico MATRIX
    approvato = False
    if tk in cooldown_map:
        verdetto = f"🤖 MATRIX resterebbe FERMO (Cooldown Anti Ping-Pong 21gg — venduto {cooldown_map[tk]} gg fa)."
    elif peso_tk > 22.0:
        verdetto = f"🤖 MATRIX resterebbe FERMO (Scudo Concentrazione attivo: {tk} pesa già {peso_tk:.1f}% > 22%)."
    elif gg_ut is not None and 0 <= int(gg_ut) <= 10:
        verdetto = f"🤖 MATRIX resterebbe FERMO (Trimestrale imminente tra {int(gg_ut)} giorni)."
    elif regime_rosso:
        if "FASE 4" in fase_u:
            verdetto = f"🤖 MATRIX resterebbe FERMO (Regime SPY/QQQ ROSSO e {tk} in Fase 4)."
        else:
            verdetto = f"🤖 MATRIX resterebbe FERMO (Regime SPY/QQQ ROSSO)."
    elif sotto_trigger_y:
        verdetto = "🤖 MATRIX resterebbe FERMO (Sotto Trigger Y)."
    elif esteso_trigger_y:
        verdetto = "🤖 MATRIX resterebbe FERMO (Esteso oltre +3,5% dal Trigger Y)."
    elif "FASE 4" in fase_u and not motori:
        verdetto = f"🤖 MATRIX resterebbe FERMO ({tk} in Fase 4)."
    elif motori:
        approvato = True
        mot_lbl = " + ".join(motori)
        verdetto = f"🟢 MATRIX APPROVA L'INGRESSO ({mot_lbl} confermato · Super-Score {target_score}/100)."
    else:
        verdetto = f"🤖 MATRIX resterebbe FERMO (Nessun breakout confermato · {fase_tk})."

    return {
        "ticker": tk,
        "target_score": target_score,
        "s_score": s_sc,
        "fase": fase_tk,
        "approvato_matrix": approvato,
        "verdetto_matrix": verdetto,
        "regime_rosso": regime_rosso,
    }


def _raccogli_candidati_switch_simulazione(
    portafoglio,
    salute_map,
    target_score,
    tk_target="",
    liq_libera=0.0,
    esclusioni=None,
    catalizzatori_set=None,
):
    """
    Raccoglie tutti i candidati validi per finanziare un acquisto in piena coerenza con
    _trova_riserva_liquidita_intelligente():
    - Fonte A (Raccolto Profitti): P&L >= +35% oppure (P&L >= +25% con RSI > 72) -> parziale 50% netto >= 30 €
      (o 100% solo se il 50% netto è < 30 €).
    - Fonte B (Switch Qualitativo Spot): SOLO quote Spot (mai PAC anche se sospesi), P&L -3%..+12%,
      no Fase 2 forte sopra SMA 50 con S-Score >= 70, no Scudo Tom Nash, no Insider SEC 90gg,
      anzianità >= 45gg (se nota) e Delta Qualitativo (target_score - Hold-Score) >= +20 pt, netto >= 30 €.
    Restituisce (lista_candidati_ordinata, totale_netto_eur).
    """
    tk_t = str(tk_target or "").strip().upper()
    escl_s = {str(x).strip().upper() for x in (esclusioni or []) if str(x).strip()}
    cat_s = {str(x).strip().upper() for x in (catalizzatori_set or []) if str(x).strip()}
    df_m_sim = _costruisci_mappa_metriche_scan() if "_costruisci_mappa_metriche_scan" in globals() else {}
    reg_acq_sim = carica_json(REGISTRO_ACQUISTI_FILE, default=[]) if "carica_json" in globals() else []
    candidati = []

    for pos in (portafoglio or []):
        tk = str(pos.get("Ticker", "")).strip().upper()
        if not tk or tk == tk_t or tk in escl_s or tk in cat_s:
            continue
        qta = float(pos.get("Quantita", 0) or 0)
        pmc = float(pos.get("Prezzo_Medio", 0) or 0)
        p_att = float(pos.get("Prezzo_Attuale_EUR") or 0)
        if qta <= 0 or pmc <= 0:
            continue
        val_car = qta * pmc
        val_att = (qta * p_att) if p_att > 0 else float(pos.get("Valore_Attuale", val_car) or val_car)
        if val_att <= 0:
            continue
        pnl_pct = ((val_att / val_car) - 1.0) * 100.0 if val_car > 0 else float(pos.get("PnL_%", 0) or 0)

        inf_s = dict((salute_map or {}).get(tk) or {})
        fase_ext, sc_ext, rsi_ext, solo_pac_ext, _ = _estrai_info_posizione_vendibile(tk, pos, df_m_sim)
        s_sc = int(inf_s.get("s_score") or sc_ext or 55)
        fase_s = str(inf_s.get("fase") or fase_ext or "N/D").upper()
        rsi_v = float(inf_s.get("rsi") if inf_s.get("rsi") is not None else (rsi_ext or 50.0))
        sopra_50 = inf_s.get("sopra_sma50")
        sec_b = int(inf_s.get("sec_buys") or 0)
        if "scudo_tom_nash" in inf_s:
            scudo_tn = bool(inf_s.get("scudo_tom_nash"))
        else:
            tn_loc = _valuta_fondamentali_tom_nash(_get_info_cached(tk), s_score=s_sc)
            scudo_tn = bool(tn_loc.get("scudo_tom_nash"))
            inf_s.update(tn_loc)
        inf_s.setdefault("s_score", s_sc)
        inf_s.setdefault("fase", fase_s)
        inf_s.setdefault("sec_buys", sec_b)
        hold_score = _calcola_hold_score_posizione(pos, inf_s)
        q_pac_p, q_spot_p = _calcola_ripartizione_pac_spot(pos)

        # Fonte A: Raccolto Profitti parziale 50% Spot (>= +35% oppure >= +25% con RSI > 72) — soglia anti-briciole >= € 100 netti
        if pnl_pct >= 35.0 or (pnl_pct >= 25.0 and rsi_v > 72.0):
            if q_spot_p <= 1e-6:
                continue
            frac = min(1.0, q_spot_p / qta) * 0.5
            v_lordo = val_att * frac
            gain_lordo = max(0.0, (val_att - val_car) * frac)
            tasse_26 = round(gain_lordo * 0.26, 2)
            netto_disp = round(max(0.0, v_lordo - tasse_26 - 2.0), 2)
            if netto_disp >= SOGLIA_MIN_NETTO_FONTE_A:
                delta_q = (int(target_score) - hold_score) if target_score is not None else None
                candidati.append({
                    "priorita": 1,
                    "codice_fonte": "FONTE_A",
                    "fonte": "Fonte A (Raccolto 50%)",
                    "ticker": tk,
                    "pct_vendita": 50,
                    "quantita": round(q_spot_p * 0.5, 4),
                    "pnl_pct": round(pnl_pct, 1),
                    "hold_score": hold_score,
                    "delta_qualita": delta_q,
                    "lordo_eur": round(v_lordo, 2),
                    "tasse_eur": tasse_26,
                    "netto_eur": netto_disp,
                    "motivo": f"Fonte A (Raccolto 50%, {pnl_pct:+.1f}%) | netto € {netto_disp:,.2f} (-€ {tasse_26:,.2f} tasse, -€ 2 comm. TR)",
                })
            continue

        # Fonte B: Rotazione Qualitativa — SOLO quote Spot (protezione assoluta PAC anche se sospesi)
        if solo_pac_ext or q_spot_p <= 1e-6:
            continue
        gg_det = inf_s.get("giorni_detenzione")
        if gg_det is None and "_calcola_giorni_detenzione_posizione" in globals():
            gg_det = _calcola_giorni_detenzione_posizione(pos, reg_acq_sim)
        if gg_det is None or gg_det < 45:
            continue
        if ("FASE 2" in fase_s) and (sopra_50 is not False) and s_sc >= 70:
            continue
        if sec_b > 0 or scudo_tn:
            continue
        delta_q = (int(target_score) - hold_score) if target_score is not None else 0
        if target_score is not None and delta_q < 20:
            continue
        if -3.0 <= pnl_pct <= 12.0:
            frazione_spot = min(1.0, q_spot_p / qta)
            v_lordo = val_att * frazione_spot
            gain_lordo = max(0.0, (val_att - val_car) * frazione_spot)
            tasse_26 = round(gain_lordo * 0.26, 2)
            netto_disp = round(max(0.0, v_lordo - tasse_26 - 2.0), 2)
            if netto_disp >= 30.0:
                nota_sp = f" — solo quota Spot ({q_spot_p:.2f} az.)" if q_pac_p > 1e-6 else ""
                candidati.append({
                    "priorita": 2,
                    "codice_fonte": "FONTE_B",
                    "fonte": "Fonte B (Switch Qualitativo Spot)",
                    "ticker": tk,
                    "pct_vendita": int(round(frazione_spot * 100.0)),
                    "quantita": round(q_spot_p, 4),
                    "pnl_pct": round(pnl_pct, 1),
                    "hold_score": hold_score,
                    "delta_qualita": delta_q,
                    "lordo_eur": round(v_lordo, 2),
                    "tasse_eur": tasse_26,
                    "netto_eur": netto_disp,
                    "motivo": f"Fonte B (Switch Spot {pnl_pct:+.1f}%, Hold-Score {hold_score}/100, Delta +{delta_q} pt{nota_sp}) | netto € {netto_disp:,.2f}",
                })

    candidati.sort(key=lambda x: (x["priorita"], x["hold_score"], -x["netto_eur"]))
    tot_netto = round(sum(c["netto_eur"] for c in candidati), 2)
    return candidati, tot_netto


def simula_acquisto(titolo, importo, portafoglio, eurusd_rate, esclusioni_list=None, catalizzatori_input=""):
    """
    Simulatore di Acquisto allineato allo Scudo Tom Nash, alla protezione assoluta delle quote PAC,
    al Delta Qualitativo Fonte B (>= +20 pt) di _trova_riserva_liquidita_intelligente() e al verdetto
    reale del Pilota Automatico MATRIX sul titolo simulato.
    """
    scenari = {'vendita_gain': list(), 'vendita_loss': list(), 'hold_catalizzatore': list(), 'nuova_liquidita': True}
    if esclusioni_list is None:
        esclusioni_list = list()
    escl_set = {str(x).strip().upper() for x in esclusioni_list if str(x).strip()}
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
                    except Exception:
                        pass
    oggi = datetime.now()
    cat_attivi_set = {tk_c for tk_c, d_c in catalizzatori.items() if d_c.get('data') and d_c['data'] >= oggi}
    salute_cache = st.session_state.get("home_salute_portafoglio") or {}
    try:
        tk_target = str(titolo or "").strip().upper()
        info = _get_info_cached(tk_target) if "_get_info_cached" in globals() else (yf.Ticker(tk_target).info or {})
        hist = _get_single_ohlc_cached(tk_target, period="1y") if "_get_single_ohlc_cached" in globals() else yf.Ticker(tk_target).history(period='1y')
        if hist is None or hist.empty:
            return {'errore': f'Impossibile recuperare dati per {tk_target}'}
        currency = str(info.get('currency', 'USD') or 'USD').upper()
        prezzo_raw = float(hist['Close'].dropna().iloc[-1])
        prezzo_eur = prezzo_raw / eurusd_rate if currency == 'USD' else prezzo_raw
        quantita_acquistabile = importo / prezzo_eur if prezzo_eur > 0 else 0.0

        # 1) Profilo qualitativo e verdetto reale del Pilota Automatico MATRIX sul titolo simulato
        prof_target = _calcola_profilo_target_simulazione(tk_target, portafoglio, eurusd_rate)
        target_score = prof_target["target_score"]

        # 2) Candidati Switch Qualitativi unificati (Fonte A parziale + Fonte B Spot con Delta >= +20 pt)
        candidati_ab, switch_netto_tot = _raccogli_candidati_switch_simulazione(
            portafoglio=portafoglio,
            salute_map=salute_cache,
            target_score=target_score,
            tk_target=tk_target,
            esclusioni=escl_set,
            catalizzatori_set=cat_attivi_set,
        )
        cand_ab_map = {c["ticker"]: c for c in candidati_ab}

        for pos in (portafoglio or []):
            ticker_pos = str(pos.get('Ticker', '')).strip().upper()
            if not ticker_pos or ticker_pos == tk_target or ticker_pos in escl_set:
                continue
            try:
                q_pac_p, q_spot_p = _calcola_ripartizione_pac_spot(pos)
                inf_s = salute_cache.get(ticker_pos) or {}
                info_pos = _get_info_cached(ticker_pos) if "_get_info_cached" in globals() else {}
                hist_pos = _get_single_ohlc_cached(ticker_pos, period="1y") if "_get_single_ohlc_cached" in globals() else None
                if hist_pos is None or hist_pos.empty:
                    continue
                currency_pos = str(info_pos.get('currency', 'USD') or 'USD').upper()
                prezzo_raw_pos = float(hist_pos['Close'].dropna().iloc[-1])
                prezzo_eur_pos = prezzo_raw_pos / eurusd_rate if currency_pos == 'USD' else prezzo_raw_pos
                prezzo_medio = float(pos.get('Prezzo_Medio', 0) or 0)
                pnl_pct = ((prezzo_eur_pos / prezzo_medio) - 1.0) * 100.0 if prezzo_medio > 0 else 0.0
                trend_30gg = ((float(hist_pos['Close'].iloc[-1]) / float(hist_pos['Close'].iloc[-30])) - 1.0) * 100.0 if len(hist_pos) >= 30 else 0.0
                s_score = int(inf_s.get("s_score") or calcola_s_score(info_pos) or 50)
                fase = str(inf_s.get("fase") or rileva_fase_weinstein(hist_pos) or "N/D")
                sec_buys = int(inf_s.get("sec_buys") or 0)
                tn_pos = _valuta_fondamentali_tom_nash(info_pos, s_score=s_score)
                scudo_tn = bool(tn_pos.get("scudo_tom_nash"))
                has_catalizzatore = ticker_pos in cat_attivi_set

                # Protezione assoluta delle posizioni PAC pure (attive o sospese Long)
                if q_spot_p <= 1e-6:
                    stato_pac_lbl = "PAC Sospeso Long" if bool(pos.get("PAC_Sospeso", False)) else "PAC Attivo"
                    scenari['hold_catalizzatore'].append({
                        'ticker': ticker_pos,
                        'messaggio': f"🛡️ PROTETTO ({stato_pac_lbl}): {ticker_pos} è un piano di accumulo fisso — mai toccare le quote PAC per finanziare acquisti Spot."
                    })
                    continue

                if has_catalizzatore:
                    scenari['hold_catalizzatore'].append({
                        'ticker': ticker_pos,
                        'messaggio': f"🛡️ PROTETTO (Catalizzatore): {ticker_pos} ha un catalizzatore imminente — non vendere."
                    })
                    continue

                # Candidato Fonte A o Fonte B confermato dalle regole di _trova_riserva_liquidita_intelligente()
                cand_ab = cand_ab_map.get(ticker_pos)
                if cand_ab and cand_ab["codice_fonte"] == "FONTE_A":
                    scenari['vendita_gain'].append({
                        'ticker': ticker_pos, 'pnl_pct': cand_ab["pnl_pct"], 'trend_30gg': round(trend_30gg, 2),
                        'quantita': cand_ab["quantita"], 'valore': cand_ab["netto_eur"], 'fonte': 'FONTE_A',
                        'messaggio': (
                            f"💰 FONTE A — RACCOLTO PROFITTI ({cand_ab['pct_vendita']}% Spot): {ticker_pos} ({cand_ab['pnl_pct']:+.1f}%) "
                            f"libera circa € {cand_ab['netto_eur']:,.2f} netti (già al netto di € {cand_ab['tasse_eur']:,.2f} tasse 26% e € 2 comm. TR)."
                        )
                    })
                elif cand_ab and cand_ab["codice_fonte"] == "FONTE_B":
                    nota_sp_m = f" — solo quota Spot ({q_spot_p:.2f} az., quota PAC intoccata)" if q_pac_p > 1e-6 else ""
                    scenari['vendita_loss'].append({
                        'ticker': ticker_pos, 'pnl_pct': cand_ab["pnl_pct"], 'kill_switch': ("FASE 4" in fase.upper()),
                        'distanza_supporto': 0.0, 'quantita': cand_ab["quantita"], 'valore': cand_ab["netto_eur"],
                        'hold_score': cand_ab["hold_score"], 'delta_qualita': cand_ab["delta_qualita"],
                        'messaggio': (
                            f"🔄 FONTE B — SWITCH QUALITATIVO SPOT: {ticker_pos} ({cand_ab['pnl_pct']:+.1f}%, {fase}, "
                            f"Hold-Score {cand_ab['hold_score']}/100, Delta +{cand_ab['delta_qualita']} pt vs {tk_target}){nota_sp_m} "
                            f"→ libera circa € {cand_ab['netto_eur']:,.2f} netti."
                        )
                    })
                elif scudo_tn or sec_buys > 0 or (pnl_pct < 0 and s_score >= 65):
                    motivi_p = []
                    if scudo_tn:
                        motivi_p.append(f"Scudo Tom Nash ({tn_pos.get('scudo_tom_nash_nota', '')})")
                    if sec_buys > 0:
                        motivi_p.append(f"{sec_buys} acq. Insider SEC 90gg")
                    if not motivi_p:
                        motivi_p.append(f"Azienda sana (S-Score {s_score}/100)")
                    scenari['hold_catalizzatore'].append({
                        'ticker': ticker_pos,
                        'messaggio': f"🛡️ PROTETTO ({ticker_pos}, {pnl_pct:+.1f}%): {' + '.join(motivi_p)} — non sacrificare questo titolo."
                    })
                elif pnl_pct > 0:
                    if pnl_pct >= 35.0:
                        msg_hold_g = (
                            f"🟢 MANTIENI (posizione piccola): {ticker_pos} (+{pnl_pct:.1f}%) — il 50% netto è sotto "
                            f"€ {SOGLIA_MIN_NETTO_FONTE_A:.0f} (soglia anti-briciole), lascialo correre intero protetto dal Trailing Stop."
                        )
                    else:
                        msg_hold_g = f"🟢 MANTIENI: {ticker_pos} (+{pnl_pct:.1f}%) è in salute ({fase}, S-Score {s_score}/100) — nessun Delta sufficiente per ruotarlo."
                    scenari['vendita_gain'].append({
                        'ticker': ticker_pos, 'pnl_pct': round(pnl_pct, 2), 'trend_30gg': round(trend_30gg, 2),
                        'quantita': q_spot_p, 'valore': round(prezzo_eur_pos * q_spot_p, 2), 'fonte': 'HOLD',
                        'messaggio': msg_hold_g,
                    })
            except Exception:
                continue

        if candidati_ab:
            scenari['nuova_liquidita'] = False
        return {
            'titolo': tk_target,
            'prezzo_eur': round(prezzo_eur, 2),
            'quantita_acquistabile': round(quantita_acquistabile, 6),
            'importo': importo,
            'scenari': scenari,
            'target_score': target_score,
            'verdetto_matrix': prof_target["verdetto_matrix"],
            'approvato_matrix': prof_target["approvato_matrix"],
            'candidati_fonte_ab': candidati_ab,
            'switch_netto_tot': switch_netto_tot,
        }
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

def registra_vendita(ticker, qta_venduta, prezzo_medio, prezzo_vendita, data_vendita=None, motivo_segnale=None):
    """Registra una vendita nel registro vendite e fiscalità (sincronizzato su GitHub) con Motivo_Segnale."""
    try:
        if data_vendita is None:
            data_vendita = _now_italia().strftime("%Y-%m-%d")
        tk_u = ticker.strip().upper()
        motivo_fin = str(motivo_segnale).strip() if motivo_segnale else _rileva_motivo_segnale_ticker(tk_u, "VENDITA")
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
            minusvalenze.append({'Data': data_vendita, 'Scadenza': scadenza, 'Importo': abs(pnl_lordo), 'Ticker': tk_u})
        minusvalenze = [m for m in minusvalenze if m.get('Importo', 0) > 0]
        salva_json(MINUSVALENZE_FILE, minusvalenze)
        registro = carica_json(REGISTRO_VENDITE_FILE)
        id_op = max([v.get('id', 0) for v in registro], default=0) + 1
        registro.append({'id': id_op, 'Data': data_vendita, 'Ticker': tk_u, 'Motivo_Segnale': motivo_fin, 'Qta_Venduta': round(qta_venduta, 6), 'Prezzo_Medio': round(prezzo_medio, 4), 'Prezzo_Vendita': round(prezzo_vendita, 4), 'PnL_Lordo': round(pnl_lordo, 2), 'PnL_Pct': round(pnl_pct, 2), 'Minusvalenze_Usate': round(minusvalenze_usate, 2), 'Tasse': round(tasse, 2), 'PnL_Netto': round(pnl_netto, 2), 'Tipo': tipo_operazione})
        salva_json(REGISTRO_VENDITE_FILE, registro)
        return {'id': id_op, 'pnl_lordo': pnl_lordo, 'pnl_pct': pnl_pct, 'tasse': tasse, 'pnl_netto': pnl_netto, 'minusvalenze_usate': minusvalenze_usate, 'tipo': tipo_operazione, 'motivo_segnale': motivo_fin}
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
    """
    Calcola la Liquidità Libera reale sul conto Trade Republic dell'utente attivo.
    Sottrae dalla cassa ESCLUSIVAMENTE 'Quota_Da_Cassa_EUR' degli acquisti (evitando saldi negativi
    fantasma quando un acquisto o PAC viene finanziato con '🏦 Nuova Liquidità Versata').
    Supporta l'allineamento puntuale di cassa tramite 'saldo_cassa_allineato' in impostazioni.json.
    """
    registro = carica_json(REGISTRO_VENDITE_FILE, default=[])
    reg_acq = carica_json(REGISTRO_ACQUISTI_FILE, default=[])
    imp_u = carica_json(IMPOSTAZIONI_FILE, default={})
    if not isinstance(imp_u, dict):
        imp_u = {}
    chiave_u = PROFILO_ATTIVO.get("chiave", "fabio")

    def _estrai_quota_cassa_acquisto(a):
        if a.get("Quota_Da_Cassa_EUR") is not None:
            return max(0.0, float(a.get("Quota_Da_Cassa_EUR") or 0.0))
        fonte_s = str(a.get("Fonte_Fondi") or "").upper()
        if "NUOVA" in fonte_s and "MISTA" not in fonte_s:
            return 0.0
        return max(0.0, float(a.get("Totale_EUR") or a.get("Importo_Totale") or (float(a.get("Quantita", 0)) * float(a.get("Prezzo_EUR", 0)))))

    # Modalità con saldo cassa esplicitamente allineato (es. Fabio: € 0,00 al 26/11/2026 dopo id vendita 3)
    if imp_u.get("saldo_cassa_allineato") is not None:
        saldo_base = float(imp_u.get("saldo_cassa_allineato") or 0.0)
        dt_allin = str(imp_u.get("data_allineamento_cassa") or "2026-11-26")[:10]
        last_id_v = int(imp_u.get("ultimo_id_vendita_allineato") or 0)
        liquidita_totale = saldo_base
        for v in (registro if isinstance(registro, list) else []):
            vid = int(v.get("id") or 0)
            dt_v = str(v.get("Data") or "")[:10]
            if vid > last_id_v or (last_id_v == 0 and dt_v > dt_allin):
                qta = float(v.get("Qta_Venduta") or 0.0)
                prezzo_vendita = float(v.get("Prezzo_Vendita") or 0.0)
                tasse = float(v.get("Tasse") or 0.0)
                comm_tr = 1.0
                liquidita_totale += (prezzo_vendita * qta) - tasse - comm_tr
        for a in (reg_acq if isinstance(reg_acq, list) else []):
            dt_a = str(a.get("Data") or "")[:10]
            if dt_a >= dt_allin:
                liquidita_totale -= _estrai_quota_cassa_acquisto(a)
        return round(max(0.0, liquidita_totale), 2)

    # Calcolo standard per Fabio (se non presente allineamento esplicito)
    if chiave_u == "fabio":
        liquidita_totale = CAPITALE_VERSATO_DEFAULT
        for v in (registro if isinstance(registro, list) else []):
            qta = float(v.get('Qta_Venduta', 0) or 0)
            prezzo_vendita = float(v.get('Prezzo_Vendita', 0) or 0)
            tasse = float(v.get('Tasse', 0) or 0)
            comm_tr = 1.0 if str(v.get('Data', ''))[:10] >= '2026-11-15' else 0.0
            liquidita_totale += (prezzo_vendita * qta) - tasse - comm_tr
        for a in (reg_acq if isinstance(reg_acq, list) else []):
            dt_a = str(a.get('Data', ''))[:10]
            if dt_a >= '2026-11-15':
                liquidita_totale -= _estrai_quota_cassa_acquisto(a)
        return round(max(0.0, liquidita_totale), 2)

    # Per Lisi, Alessia e altri profili: capitale versato del profilo + vendite nette - sola Quota_Da_Cassa_EUR
    if imp_u.get("capitale_versato") is not None:
        base_versata = float(imp_u.get("capitale_versato") or 0.0)
    else:
        base_versata = CAPITALE_VERSATO_DEFAULT

    incassi_vendite = 0.0
    for v in (registro if isinstance(registro, list) else []):
        qta = float(v.get('Qta_Venduta', 0) or 0)
        prezzo_vendita = float(v.get('Prezzo_Vendita', 0) or 0)
        tasse = float(v.get('Tasse', 0) or 0)
        comm_tr = 1.0 if str(v.get('Data', ''))[:10] >= '2026-11-15' else 0.0
        incassi_vendite += (prezzo_vendita * qta) - tasse - comm_tr

    spese_cassa_acq = 0.0
    ha_mov_acq = False
    for a in (reg_acq if isinstance(reg_acq, list) else []):
        dt_a = str(a.get('Data', ''))[:10]
        if dt_a >= '2026-11-15':
            ha_mov_acq = True
            spese_cassa_acq += _estrai_quota_cassa_acquisto(a)

    if ha_mov_acq:
        base_liq = float(imp_u.get("liquidita_totale")) if imp_u.get("liquidita_totale") is not None else base_versata
        return round(max(0.0, base_liq + incassi_vendite - spese_cassa_acq), 2)

    port_u = st.session_state.get("portafoglio") or []
    cap_inv_u = sum(
        float(p.get("Valore_Carico") or (float(p.get("Quantita", 0) or 0) * float(p.get("Prezzo_Medio", 0) or 0)))
        for p in port_u
    )
    if base_versata == 0.0 and cap_inv_u == 0.0:
        return round(max(0.0, incassi_vendite), 2)
    return round(max(0.0, base_versata - cap_inv_u + incassi_vendite), 2)

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

def _valuta_verdetto_coerente_scudi(r, prezzo_nat_corrente=None):
    """
    Allinea il verdetto di Analisi Singola agli Scudi della Home Page Pilota Automatico
    per eliminare ogni contraddizione:
    se esiste un pattern BUY (o segnale BY) ma lo Scudo 1 (Regime SPY/QQQ ROSSO) è attivo
    oppure il prezzo attuale è ancora sotto il Trigger Y (Pre-Breakout) o già esteso > +3.5%,
    sostituisce il verde libero con '🟡 PATTERN RILEVATO — ⏳ IN ATTESA SCUDO' indicando i motivi esatti.
    Restituisce (segnale_display, in_attesa_scudo: bool, motivo_scudo_str).
    """
    tk_u = str((r or {}).get("ticker") or "").strip().upper()
    seg_orig = str((r or {}).get("segnale") or "HOLD")
    pat = None
    pat_sing = st.session_state.get("pattern_singola_attivo")
    if isinstance(pat_sing, dict) and str(pat_sing.get("ticker", "")).strip().upper() == tk_u:
        pat = pat_sing
    else:
        pat_map = (st.session_state.get("pattern_alerts") or {}).get("per_ticker") or {}
        if isinstance(pat_map, dict) and tk_u in pat_map:
            pat = pat_map.get(tk_u)

    has_pat_buy = bool(isinstance(pat, dict) and str(pat.get("lato", "")).upper() != "SELL")
    is_seg_buy = ("BY" in seg_orig.upper()) or bool((r or {}).get("trigger_by_fabio"))
    if not (has_pat_buy or is_seg_buy):
        return seg_orig, False, ""

    motivi_blocco = []
    # Scudo 1 — Regime SPY / QQQ ROSSO
    try:
        sem_cor = st.session_state.get("semaforo_mercato")
        if not isinstance(sem_cor, dict) or not sem_cor.get("stato"):
            sem_cor = semaforo_header if ("semaforo_header" in globals() and isinstance(semaforo_header, dict)) else calcola_semaforo_mercato()
        spy_st_c = str((sem_cor or {}).get("stato", "giallo")).lower()
        _, qqq_st_c, _ = _verifica_qqq_regime_verde()
        if spy_st_c == "rosso" or str(qqq_st_c).lower() == "rosso":
            motivi_blocco.append("Regime SPY/QQQ ROSSO (Scudo 1)")
    except Exception:
        pass

    # Verifica Trigger Y del pattern (Pre-Breakout sotto Trigger Y o già esteso > +3.5%)
    if has_pat_buy:
        trig_y = float(pat.get("trigger_y") or 0.0)
        dist_y = pat.get("dist_y_pct")
        stato_tr = str(pat.get("stato_trigger", "")).upper()
        simb_p = "$" if str(pat.get("currency", "USD")).upper() == "USD" else "€"
        p_ref = float(prezzo_nat_corrente) if (prezzo_nat_corrente is not None and float(prezzo_nat_corrente) > 0) else float(pat.get("prezzo") or (r or {}).get("prezzo_usd") or 0.0)
        sotto_y = ("PRE-BREAKOUT" in stato_tr) or (dist_y is not None and float(dist_y) < 0.0) or (trig_y > 0 and p_ref > 0 and p_ref < trig_y)
        oltre_y = (dist_y is not None and float(dist_y) > 3.5) or (trig_y > 0 and p_ref > trig_y * 1.035)
        if sotto_y and trig_y > 0:
            motivi_blocco.append(f"Sotto Trigger Y {simb_p}{trig_y:.2f} (attendi rottura confermata)")
        elif oltre_y and trig_y > 0:
            motivi_blocco.append(f"Oltre +3.5% dal Trigger Y {simb_p}{trig_y:.2f} (non inseguire)")

    if motivi_blocco:
        fig_lbl = f" ({pat.get('figura')})" if (has_pat_buy and pat.get("figura")) else ""
        return f"🟡 PATTERN RILEVATO{fig_lbl} — ⏳ IN ATTESA SCUDO", True, " + ".join(motivi_blocco)
    return seg_orig, False, ""

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

    # Allinea il verdetto agli Scudi della Home Page Pilota Automatico (zero contraddizioni)
    _p_nat_live = float(df_1y["Close"].iloc[-1]) if (df_1y is not None and not df_1y.empty) else r.get("prezzo_usd")
    _seg_coerente, _in_attesa_scudo, _motivo_scudo = _valuta_verdetto_coerente_scudi(r, prezzo_nat_corrente=_p_nat_live)

    # Badge Scudo Fondamentale Tom Nash & Stato manuale PAC/Spot nell'intestazione accanto al verdetto
    _tn_scheda = _valuta_fondamentali_tom_nash(info_y, s_score=r.get("s_score", 50)) if "_valuta_fondamentali_tom_nash" in globals() else {}
    _badge_tn_hdr = ""
    if _tn_scheda.get("scudo_tom_nash"):
        _nota_tn_h = str(_tn_scheda.get("scudo_tom_nash_nota") or "")
        _badge_tn_hdr = (
            f" <span title='{_nota_tn_h}' style='display:inline-block; vertical-align:middle; margin-left:8px; "
            f"background:#0F2436; color:#38BDF8; border:1px solid #38BDF8; border-radius:999px; "
            f"padding:2px 10px; font-size:0.76rem; font-weight:700;'>🛡️ SCUDO TOM NASH</span>"
        )
    _pos_scheda = next((p for p in (st.session_state.get("portafoglio") or []) if str(p.get("Ticker", "")).strip().upper() == str(tk).upper()), None)
    _badge_pac_hdr = ""
    if _pos_scheda:
        _st_p_h = _stato_pac_manuale(_pos_scheda)
        _tp_p_h = _formatta_badge_tipo_posizione(_pos_scheda, con_dettaglio=False)
        _lbl_p_h = _st_p_h if _st_p_h != "N/A" else f"📂 {_tp_p_h}"
        _badge_pac_hdr = (
            f" <span style='display:inline-block; vertical-align:middle; margin-left:6px; "
            f"background:#1E293B; color:#E2E8F0; border:1px solid #475569; border-radius:999px; "
            f"padding:2px 9px; font-size:0.74rem; font-weight:600;'>{_lbl_p_h}</span>"
        )

    st.markdown(
        f"<h2 style='margin-bottom:6px; line-height:1.3;'>{nome_az} ({tk}) {whale_b} — {_seg_coerente}{_badge_tn_hdr}{_badge_pac_hdr}</h2>",
        unsafe_allow_html=True,
    )
    if _in_attesa_scudo and _motivo_scudo:
        st.warning(f"🛡️ **Allineamento Scudi Home Page:** {_motivo_scudo} — nessun semaforo verde operativo finché lo scudo non si libera.")
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
    """
    Rifinisce il grafico Plotly per mobile/desktop senza toccare pattern_engine.py:
    - Pan fluido a un dito, pinch-to-zoom e doppio tap per ripristinare la vista.
    - Compatta automaticamente eventuali etichette lunghe di pattern_engine (Trigger Y / Target / Stop)
      per evitare sovrapposizioni su schermi stretti da smartphone.
    """
    if fig is not None:
        fig.update_layout(dragmode="pan")
        fig.update_yaxes(fixedrange=False, row=1, col=1)
        try:
            for ann in (fig.layout.annotations or []):
                txt = str(getattr(ann, "text", "") or "")
                if "Trigger Y" in txt:
                    m_p = re.search(r"([\$€]\s*[\d,\.]+)", txt)
                    if m_p:
                        ann.text = f" ⚡ Y: {m_p.group(1)} "
                        ann.font.size = 10
                elif "Target" in txt and ("R/R" in txt or "🎯" in txt):
                    m_p = re.search(r"([\$€]\s*[\d,\.]+)", txt)
                    m_pct = re.search(r"([+\-]\d+(?:\.\d+)?%)", txt)
                    if m_p:
                        pct_s = f" ({m_pct.group(1)})" if m_pct else ""
                        ann.text = f" 🎯 T: {m_p.group(1)}{pct_s} "
                        ann.font.size = 10
                elif "Stop" in txt and "🛑" in txt:
                    m_p = re.search(r"([\$€]\s*[\d,\.]+)", txt)
                    if m_p:
                        ann.text = f" 🛑 SL: {m_p.group(1)} "
                        ann.font.size = 10
        except Exception:
            pass
    return fig

def genera_grafico_baleine(ticker, period, sma_short, sma_long, prezzo_medio_eur=None, timeframe='1d', interval='1d', eurusd_rate=1.12, height=640, pattern_info=None):
    tk_u = str(ticker or "").strip().upper()
    df = yf.Ticker(tk_u).history(period=period, interval=interval)
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

    # Recupera valuta e dati Tom Nash dalla cache _get_info_cached (zero chiamate lente extra)
    info_g = _get_info_cached(tk_u) if "_get_info_cached" in globals() else {}
    cur_g = str((info_g or {}).get("currency", "USD") or "USD").upper()
    simb_g = "€" if cur_g == "EUR" else "$"
    conv_eur_to_chart = 1.0 if cur_g == "EUR" else float(eurusd_rate or 1.12)
    s_sc_g = calcola_s_score(info_g) if "calcola_s_score" in globals() else 50
    tn_g = _valuta_fondamentali_tom_nash(info_g, s_score=s_sc_g) if "_valuta_fondamentali_tom_nash" in globals() else {}

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
    _tn_title_tag = "  <span style='color:#38BDF8; font-weight:700;'>• 🛡️ Tom Nash</span>" if tn_g.get("scudo_tom_nash") else ""
    titolo_main = f"<b>{tk_u}</b> {whale_badge} {simb_g}{prezzo_attuale:.2f} <span style='color:{colore_titolo};'>({var_pct_oggi:+.2f}%)</span> | <span style='color:{rsi_col};'>RSI {rsi_now:.1f}</span> [{timeframe.upper()}]{_tn_title_tag}"
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.70, 0.15, 0.15], subplot_titles=("", "Volume", f"RSI (14): {rsi_now:.1f}"))

    # Tracce secondarie senza voce in legenda (mantiene legenda compatta in fondo sotto al grafico)
    if has_sma20:
        fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='rgba(0, 188, 212, 0.30)', width=1, dash='dot'), name='BB Sup', showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], fill='tonexty', fillcolor='rgba(0, 188, 212, 0.05)', line=dict(color='rgba(0, 188, 212, 0.30)', width=1, dash='dot'), name='BB Inf', showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], line=dict(color='#00BCD4', width=1.2), name='SMA 20', showlegend=False), row=1, col=1)

    # Candele Hollow stile StockCharts: colore su Close vs Chiusura prec., riempimento (vuota/piena) su Close vs Open
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df['Open'].where(is_up),
            high=df['High'].where(is_up),
            low=df['Low'].where(is_up),
            close=df['Close'].where(is_up),
            name='Prezzo',
            legendgroup='prezzo',
            showlegend=False,
            increasing_line_color="#10B981",
            increasing_fillcolor="#0B0E11",
            increasing_line_width=1.4,
            decreasing_line_color="#10B981",
            decreasing_fillcolor="#10B981",
            decreasing_line_width=1.2,
            whiskerwidth=0.45,
        ),
        row=1,
        col=1,
    )
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
            increasing_line_width=1.4,
            decreasing_line_color="#EF4444",
            decreasing_fillcolor="#EF4444",
            decreasing_line_width=1.2,
            whiskerwidth=0.45,
        ),
        row=1,
        col=1,
    )
    if has_sma_short:
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_Short'], line=dict(color='#F59E0B', width=1.5), name=f'SMA {sma_short}'), row=1, col=1)
    if has_sma_long:
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_Long'], line=dict(color='#2962FF', width=1.7), name=f'SMA {sma_long}'), row=1, col=1)

    # Recupera eventuale pattern attivo per evitare sovrapposizione Res / Trigger Y
    _pat_for_range = pattern_info
    if _pat_for_range is None:
        _pat_for_range = (st.session_state.get("pattern_alerts") or {}).get("per_ticker", {}).get(tk_u)
    _trig_y_val = None
    if isinstance(_pat_for_range, dict) and _pat_for_range.get("trigger_y"):
        try:
            _trig_y_val = float(_pat_for_range["trigger_y"])
        except Exception:
            _trig_y_val = None

    # Linea PMC + simbolo ancorato sull'ultima seduta + badge pillola ad alto contrasto
    prezzo_medio_chart = None
    if prezzo_medio_eur is not None and float(prezzo_medio_eur) > 0:
        prezzo_medio_chart = float(prezzo_medio_eur) * conv_eur_to_chart
        fig.add_hline(
            y=prezzo_medio_chart,
            line_dash="dot",
            line_color="#10B981",
            line_width=1.8,
            annotation_text=f" 💼 PMC {simb_g}{prezzo_medio_chart:.2f} (€{float(prezzo_medio_eur):.2f}) ",
            annotation_position="top left",
            annotation_bgcolor="rgba(11, 24, 18, 0.90)",
            annotation_bordercolor="#10B981",
            annotation_borderwidth=1,
            annotation_font=dict(color="#4ADE80", size=10),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=[df.index[-1]],
                y=[prezzo_medio_chart],
                mode="markers",
                marker=dict(symbol="star", size=11, color="#10B981", line=dict(width=1.2, color="#FFFFFF")),
                name="💼 PMC",
                showlegend=False,
                hovertemplate=f"<b>💼 PMC Portafoglio</b><br>{simb_g}{prezzo_medio_chart:.2f} (€{float(prezzo_medio_eur):.2f})<extra></extra>",
            ),
            row=1,
            col=1,
        )

    # Marker diamanti oro/verde per ogni acquisto reale da registro_acquisti*.json (con fallback portafoglio*.json)
    acq_x, acq_y, acq_hover = [], [], []
    try:
        reg_acq_g = carica_json(REGISTRO_ACQUISTI_FILE, default=[])
        idx_naive = df.index.tz_localize(None) if getattr(df.index, "tz", None) is not None else df.index
        trovati_reg = False
        for row_a in (reg_acq_g if isinstance(reg_acq_g, list) else []):
            if not isinstance(row_a, dict) or str(row_a.get("Ticker", "")).strip().upper() != tk_u:
                continue
            dt_a_s = str(row_a.get("Data", "")).strip()[:10]
            p_a_eur = float(row_a.get("Prezzo_EUR") or 0.0)
            if len(dt_a_s) < 10 or p_a_eur <= 0:
                continue
            try:
                ts_a = pd.Timestamp(dt_a_s)
                pos_idx = int(np.argmin(np.abs((idx_naive - ts_a).total_seconds())))
                if abs((idx_naive[pos_idx] - ts_a).days) <= 10:
                    p_a_chart = round(p_a_eur * conv_eur_to_chart, 2)
                    acq_x.append(df.index[pos_idx])
                    acq_y.append(p_a_chart)
                    q_a = float(row_a.get("Quantita") or 0.0)
                    tp_a = str(row_a.get("Tipo") or "Spot")
                    mot_a = str(row_a.get("Motivo_Segnale") or "Manuale / Storico")
                    ff_a = str(row_a.get("Fonte_Fondi") or "N/D")
                    acq_hover.append(
                        f"<b>💎 Acquisto Reale ({tp_a})</b><br>"
                        f"Data: {dt_a_s}<br>"
                        f"Prezzo: {simb_g}{p_a_chart:.2f} (€{p_a_eur:.2f})<br>"
                        f"Quantità: {q_a:.4f}<br>"
                        f"Motivo: {mot_a}<br>"
                        f"Fonte: {ff_a}"
                    )
                    trovati_reg = True
            except Exception:
                continue
        # Fallback su Data_Acquisto da portafoglio.json per posizioni storiche non ancora nel registro
        if not trovati_reg:
            pos_st = next((p for p in (st.session_state.get("portafoglio") or []) if str(p.get("Ticker", "")).strip().upper() == tk_u), None)
            if pos_st:
                dt_p_s = str(pos_st.get("Data_Acquisto") or pos_st.get("data_acquisto") or "").strip()[:10]
                p_p_eur = float(pos_st.get("Prezzo_Medio") or 0.0)
                if len(dt_p_s) >= 10 and p_p_eur > 0:
                    try:
                        ts_p = pd.Timestamp(dt_p_s)
                        pos_idx = int(np.argmin(np.abs((idx_naive - ts_p).total_seconds())))
                        if abs((idx_naive[pos_idx] - ts_p).days) <= 10:
                            p_p_chart = round(p_p_eur * conv_eur_to_chart, 2)
                            acq_x.append(df.index[pos_idx])
                            acq_y.append(p_p_chart)
                            acq_hover.append(
                                f"<b>💎 Posizione Storica ({pos_st.get('Tipo', 'Spot')})</b><br>"
                                f"Data: {dt_p_s}<br>"
                                f"PMC: {simb_g}{p_p_chart:.2f} (€{p_p_eur:.2f})<br>"
                                f"Quantità: {float(pos_st.get('Quantita') or 0):.4f}"
                            )
                    except Exception:
                        pass
    except Exception:
        pass

    if acq_x:
        fig.add_trace(
            go.Scatter(
                x=acq_x,
                y=acq_y,
                mode="markers",
                marker=dict(symbol="diamond", size=12, color="#FACC15", line=dict(width=1.8, color="#10B981")),
                name=f"💎 Acquisti ({len(acq_x)})",
                text=acq_hover,
                hovertemplate="%{text}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    # Etichette compatte e alternate (evita di stampare Res se coincide entro ±1.5% con Trigger Y)
    if vpoc_level:
        fig.add_hline(y=vpoc_level, line_dash="dashdot", line_color="#E040FB", line_width=1.3, annotation_text=f" 🐋 VPOC {simb_g}{vpoc_level:.2f} ", annotation_position="bottom right", annotation_bgcolor="rgba(11, 14, 17, 0.85)", annotation_font=dict(color="#E040FB", size=10), row=1, col=1)
    fig.add_hline(y=supporto, line_dash="dash", line_color="#10B981", line_width=1.1, annotation_text=f" Sup {supporto:.2f} ", annotation_position="bottom left", annotation_bgcolor="rgba(11, 14, 17, 0.85)", annotation_font=dict(color="#10B981", size=10), row=1, col=1)
    res_vicina_y = (_trig_y_val is not None and _trig_y_val > 0 and abs(resistenza - _trig_y_val) / _trig_y_val <= 0.015)
    if not res_vicina_y:
        fig.add_hline(y=resistenza, line_dash="dash", line_color="#EF4444", line_width=1.1, annotation_text=f" Res {resistenza:.2f} ", annotation_position="top left", annotation_bgcolor="rgba(11, 14, 17, 0.85)", annotation_font=dict(color="#EF4444", size=10), row=1, col=1)
    if gap_level:
        fig.add_hline(y=gap_level, line_dash="dot", line_color="#F59E0B", line_width=1.3, annotation_text=f" Gap {gap_level:.2f} ", annotation_position="top right", annotation_bgcolor="rgba(11, 14, 17, 0.85)", annotation_font=dict(color="#F59E0B", size=10), row=1, col=1)

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
        fig.add_trace(go.Scatter(x=by_x, y=by_y, mode='markers', marker=dict(symbol='triangle-up', size=12, color='#10B981', line=dict(width=1.2, color='#FFFFFF')), name=f'▲ BY ({len(by_x)})'), row=1, col=1)
    if sell_x:
        fig.add_trace(go.Scatter(x=sell_x, y=sell_y, mode='markers', marker=dict(symbol='triangle-down', size=12, color='#EF4444', line=dict(width=1.2, color='#FFFFFF')), name=f'▼ SELL ({len(sell_x)})'), row=1, col=1)

    vol_colors = ['rgba(16, 185, 129, 0.65)' if up else 'rgba(239, 68, 68, 0.65)' for up in is_up]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=vol_colors, name='Volume', showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#9C27B0', width=1.5), name='RSI 14', showlegend=False), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#EF4444", line_width=1, row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#10B981", line_width=1, row=3, col=1)

    # Layout pulito mobile-first: titolo in testa, pulsanti 1M..Tutto separati sotto, legenda in fondo sotto RSI
    fig.update_layout(
        title=dict(text=titolo_main, x=0.01, y=0.988, xanchor="left", yanchor="top", font=dict(size=11, color="#F8FAFC")),
        height=height,
        dragmode="pan",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        paper_bgcolor='#131722',
        plot_bgcolor='#0B0E11',
        font=dict(family='Inter, sans-serif', color='#D1D4DC', size=11),
        margin=dict(l=4, r=46, t=66, b=54),
        hovermode='x unified',
        legend=dict(
            font=dict(size=10),
            orientation="h",
            yanchor="top",
            y=-0.06,
            xanchor="left",
            x=0.0,
            tracegroupgap=4,
            bgcolor='rgba(19, 23, 34, 0.0)',
        ),
    )

    # Rimozione buchi weekend solo sul Daily + selettori rapidi 1M / 3M / 6M / 1A / Tutto liberi da sovrapposizioni
    is_weekly = (interval == '1wk' or timeframe == '1wk')
    is_monthly = (interval == '1mo' or timeframe == '1mo')
    is_daily = (interval == '1d' and not is_weekly and not is_monthly)
    if is_daily:
        fig.update_xaxes(gridcolor='#1E222D', zerolinecolor='#2A2E39', rangebreaks=[dict(bounds=["sat", "mon"])], fixedrange=False)
    else:
        fig.update_xaxes(gridcolor='#1E222D', zerolinecolor='#2A2E39', fixedrange=False)
    if is_daily or is_weekly:
        fig.update_xaxes(
            rangeselector=dict(
                bgcolor="#1E293B",
                activecolor="#2962FF",
                font=dict(color="#F8FAFC", size=10),
                x=0.0,
                y=1.015,
                xanchor="left",
                yanchor="bottom",
                buttons=[
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(count=6, label="6M", step="month", stepmode="backward"),
                    dict(count=1, label="1A", step="year", stepmode="backward"),
                    dict(step="all", label="Tutto"),
                ],
            ),
            row=1,
            col=1,
        )
    fig.update_yaxes(gridcolor='#1E222D', zerolinecolor='#2A2E39', side='right', fixedrange=False)

    # Finestra visibile iniziale ottimizzata mobile: 68 sedute sul Daily (candele larghe e nitide)
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
        sub_df = df.tail(68)
        left_pad = pd.Timedelta(days=1)
        right_pad = pd.Timedelta(days=3)
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
            sub_df = df.tail(min(68, len(df)))
        left_pad = pd.Timedelta(days=1)
        right_pad = pd.Timedelta(days=3)
    else:
        sub_df = df.tail(68)
        left_pad = pd.Timedelta(minutes=15)
        right_pad = pd.Timedelta(hours=2)

    if len(sub_df) >= 2:
        x_start = sub_df.index[0] - left_pad
        x_end = end_dt + right_pad

        # Calcolo range asse Y iniziale: candele + Trigger Y + Stop Loss (Target e PMC solo se entro ±12% dal prezzo
        # per non schiacciare mai le candele creando spazio nero vuoto in alto!)
        vis_low = float(sub_df['Low'].min())
        vis_high = float(sub_df['High'].max())
        if isinstance(_pat_for_range, dict):
            for _k_lvl in ("trigger_y", "stop_price"):
                _v_lvl = _pat_for_range.get(_k_lvl)
                if _v_lvl is not None:
                    try:
                        _fv = float(_v_lvl)
                        if _fv > 0:
                            vis_low = min(vis_low, _fv)
                            vis_high = max(vis_high, _fv)
                    except Exception:
                        pass
            _v_targ = _pat_for_range.get("target_price")
            if _v_targ is not None and prezzo_attuale > 0:
                try:
                    _ft = float(_v_targ)
                    if _ft > 0 and abs(_ft - prezzo_attuale) / prezzo_attuale <= 0.12:
                        vis_high = max(vis_high, _ft)
                except Exception:
                    pass
        if prezzo_medio_chart is not None and prezzo_attuale > 0:
            if abs(prezzo_medio_chart - prezzo_attuale) / prezzo_attuale <= 0.12:
                vis_low = min(vis_low, prezzo_medio_chart)
                vis_high = max(vis_high, prezzo_medio_chart)

        span_y = max(vis_high - vis_low, vis_high * 0.02, 1e-6)
        y_min = max(0.0, vis_low - span_y * 0.06)
        y_max = vis_high + span_y * 0.06

        fig.update_xaxes(range=[x_start, x_end], row=1, col=1)
        fig.update_xaxes(range=[x_start, x_end], row=2, col=1)
        fig.update_xaxes(range=[x_start, x_end], row=3, col=1)
        fig.update_yaxes(range=[y_min, y_max], fixedrange=False, row=1, col=1)

    return fig

def valuta_stato_pac(pos_o_info, df_storico=None):
    """
    Gestione 100% manuale dello stato PAC (rimossa ogni sospensione automatica):
    se riceve il dizionario posizione restituisce '_stato_pac_manuale(pos)', altrimenti '🟢 PAC ATTIVO'.
    """
    if isinstance(pos_o_info, dict) and ("Ticker" in pos_o_info or "PAC_Sospeso" in pos_o_info or "Quantita" in pos_o_info):
        return _stato_pac_manuale(pos_o_info)
    return "🟢 PAC ATTIVO"

def aggiorna_quotazioni_portafoglio(portafoglio, eurusd_rate):
    risultati = list()
    for pos in portafoglio:
        ticker = pos['Ticker']
        # Preserva rigorosamente lo stato manuale PAC (zero sospensioni automatiche)
        stato_pac_man = _stato_pac_manuale(pos)
        try:
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info
            hist = ticker_obj.history(period="1y")
            if hist.empty:
                risultati.append({**pos, "Prezzo_Attuale_EUR": None, "Prezzo_Attuale_USD": None, "PnL_EUR": None, "PnL_%": None, "Trend": "N/D", "Earnings": "N/D", "Variazione_Pct": None, "Stato_PAC": stato_pac_man, "Ultimo_Segnale": "N/D"})
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
            ultimo_segnale_display = format_ultimo_segnale_display(ticker, prezzo_usd)
            risultati.append({**pos, "Prezzo_Attuale_EUR": round(prezzo_eur, 2), "Prezzo_Attuale_USD": round(prezzo_usd, 2), "Valore_Attuale": round(valore_attuale, 2), "PnL_EUR": round(pnl_eur, 2), "PnL_%": round(pnl_pct, 2), "Trend": trend, "Earnings": earnings_msg, "Variazione_Pct": var_pct, "Stato_PAC": stato_pac_man, "Ultimo_Segnale": ultimo_segnale_display})
        except Exception:
            risultati.append({**pos, "Prezzo_Attuale_EUR": None, "Prezzo_Attuale_USD": None, "PnL_EUR": None, "PnL_%": None, "Trend": "Errore", "Earnings": "N/D", "Variazione_Pct": None, "Stato_PAC": stato_pac_man, "Ultimo_Segnale": "N/D"})
    salva_ultimo_agg_prezzi()
    return risultati


def _aggiorna_solo_prezzi_live_portafoglio(portafoglio, eurusd_rate, salute_map=None, chiave_u="fabio"):
    """
    Aggiorna in ~1-2 secondi solo i prezzi live/intraday e la variazione giornaliera (Oggi %)
    delle posizioni in portafoglio con un unico mini-batch yf.download(period='5d', interval='1d'),
    senza rilanciare la cascata 5 fasi né perdere la cache da 20 minuti.
    Aggiorna in-place portafoglio, salute_map, cache snapshot e rilancia il check Stop Loss/Gain Spot.
    """
    if not portafoglio:
        return portafoglio, (salute_map or {}), 0
    tks = list(dict.fromkeys(
        str(p.get("Ticker", "")).strip().upper()
        for p in portafoglio
        if isinstance(p, dict) and str(p.get("Ticker", "")).strip()
    ))
    if not tks:
        return portafoglio, (salute_map or {}), 0

    rate = float(eurusd_rate or get_live_eurusd() or 1.12)
    suffissi_eur = (".MI", ".DE", ".PA", ".AS", ".F", ".MC", ".BR", ".VI", ".HE", ".LS")
    prezzi_map = {}
    try:
        raw = yf.download(
            tks if len(tks) > 1 else tks[0],
            period="5d",
            interval="1d",
            group_by="ticker" if len(tks) > 1 else "column",
            threads=True,
            progress=False,
            auto_adjust=False,
        )
        if raw is not None and not raw.empty:
            for tk in tks:
                try:
                    if len(tks) == 1:
                        sub = raw
                    elif isinstance(raw.columns, pd.MultiIndex):
                        if tk not in raw.columns.get_level_values(0):
                            continue
                        sub = raw[tk]
                    else:
                        continue
                    closes = sub["Close"].dropna()
                    if closes.empty:
                        continue
                    c_now = float(closes.iloc[-1])
                    c_prev = float(closes.iloc[-2]) if len(closes) >= 2 else c_now
                    if c_now > 0:
                        prezzi_map[tk] = (c_now, c_prev)
                except Exception:
                    continue
    except Exception:
        pass

    sal_upd = dict(salute_map or {})
    port_upd = []
    aggiornati = 0
    for pos in portafoglio:
        p_new = dict(pos)
        tk = str(p_new.get("Ticker", "")).strip().upper()
        if tk in prezzi_map:
            c_now, c_prev = prezzi_map[tk]
            # Rileva valuta senza chiamate lente di rete (cache _get_info_cached o suffisso borsa europea)
            cur = "EUR" if any(tk.endswith(s) for s in suffissi_eur) else "USD"
            try:
                inf_c = _get_info_cached(tk) if "_get_info_cached" in globals() else {}
                if isinstance(inf_c, dict) and inf_c.get("currency"):
                    cur = str(inf_c.get("currency")).strip().upper()
            except Exception:
                pass
            p_eur = round(c_now / rate, 2) if cur == "USD" else round(c_now, 2)
            p_usd = round(c_now, 2) if cur == "USD" else round(c_now * rate, 2)
            var_pct = round(((c_now / c_prev) - 1.0) * 100.0, 2) if c_prev > 0 else 0.0
            qta = float(p_new.get("Quantita", 0) or 0)
            pmc = float(p_new.get("Prezzo_Medio", 0) or 0)
            val_att = round(p_eur * qta, 2)
            val_car = round(pmc * qta, 2)
            pnl_eur = round(val_att - val_car, 2)
            pnl_pct = round(((p_eur / pmc) - 1.0) * 100.0, 2) if pmc > 0 else 0.0
            p_new["Prezzo_Attuale_EUR"] = p_eur
            p_new["Prezzo_Attuale_USD"] = p_usd
            p_new["Valore_Attuale"] = val_att
            p_new["Valore_Carico"] = val_car
            p_new["PnL_EUR"] = pnl_eur
            p_new["PnL_%"] = pnl_pct
            p_new["Variazione_Pct"] = var_pct
            p_new["Variazione_Abs"] = round(abs(c_now - c_prev), 2)
            p_new["Stato_PAC"] = _stato_pac_manuale(p_new)
            if tk in sal_upd and isinstance(sal_upd[tk], dict):
                sal_upd[tk] = dict(sal_upd[tk])
                sal_upd[tk].update({
                    "pnl_pct": pnl_pct,
                    "pnl_eur": pnl_eur,
                    "val_att": val_att,
                    "val_car": val_car,
                    "close_oggi": c_now,
                    "close_ieri": c_prev,
                    "var_pct_oggi": var_pct,
                })
            aggiornati += 1
        port_upd.append(p_new)

    if aggiornati > 0:
        ora_it_live = _now_italia().strftime("%d/%m/%Y %H:%M")
        salva_ultimo_agg_prezzi(ora_it_live)
        st.session_state["portafoglio"] = port_upd
        st.session_state["home_salute_portafoglio"] = sal_upd
        snap_d = st.session_state.get("home_snapshot_decisionale")
        if isinstance(snap_d, dict):
            snap_d = dict(snap_d)
            snap_d["calcolato_alle"] = ora_it_live
            st.session_state["home_snapshot_decisionale"] = snap_d
        # Aggiorna in-place anche lo snapshot in cache da 20 minuti così il rientro su mobile resta istantaneo e fresco
        try:
            cache_st = _get_home_snapshot_cache_store()
            u_low = str(chiave_u or "fabio").strip().lower()
            for ck, cval in list(cache_st.items()):
                if isinstance(ck, tuple) and len(ck) >= 1 and ck[0] == u_low and isinstance(cval, tuple) and len(cval) == 2 and isinstance(cval[1], dict):
                    cval[1]["portafoglio"] = port_upd
                    cval[1]["home_salute_portafoglio"] = sal_upd
                    if isinstance(cval[1].get("home_snapshot_decisionale"), dict):
                        cval[1]["home_snapshot_decisionale"]["calcolato_alle"] = ora_it_live
        except Exception:
            pass
        # Check istantaneo Stop Loss / Protezione Profitto & Gain Telegram sui nuovi prezzi live (zero API extra)
        try:
            if "regia_tracker" in globals() and hasattr(regia_tracker, "sincronizza_avvisi_protezione_spot"):
                regia_tracker.sincronizza_avvisi_protezione_spot(
                    port_upd, eurusd_rate=rate, ohlc_map=None, utente=str(chiave_u or "fabio").strip().lower()
                )
        except Exception:
            pass

    return port_upd, sal_upd, aggiornati

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
# MARKET DATA HUB CONDIVISO (@st.cache_data) & MOTORI ESTRATTI UNIFICATI
# ==============================================================================
@st.cache_data(ttl=900, show_spinner=False)
def _scarica_ohlc_batch_cached(tickers_tuple, period="1y"):
    """
    Scarica in un unico batch multi-thread lo storico OHLCV per tutti i ticker richiesti
    (condiviso tra Scansione Principale, Radar IGNITION 80, Palantir AI e Salute Portafoglio).
    """
    out = {}
    tks = [str(t).strip().upper() for t in (tickers_tuple or ()) if str(t).strip()]
    tks = sorted(list(dict.fromkeys(tks)))
    if not tks:
        return out
    try:
        raw = yf.download(
            tks if len(tks) > 1 else tks[0],
            period=period,
            interval="1d",
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=True,
        )
        if raw is None or raw.empty:
            return out
        if isinstance(raw.columns, pd.MultiIndex):
            lvl0 = set(raw.columns.get_level_values(0))
            for tk in tks:
                if tk in lvl0:
                    sub = raw[tk].dropna(subset=["Close"]).copy()
                    if not sub.empty:
                        out[tk] = sub
        else:
            sub = raw.dropna(subset=["Close"]).copy()
            if not sub.empty:
                out[tks[0]] = sub
    except Exception:
        pass
    return out

@st.cache_data(ttl=900, show_spinner=False)
def _get_single_ohlc_cached(ticker, period="1y"):
    """Fallback singolo con cache 15 min se un ticker manca nel download batch."""
    try:
        df_s = yf.Ticker(str(ticker).strip().upper()).history(period=period, interval="1d")
        if df_s is not None and not df_s.empty:
            return df_s.dropna(subset=["Close"]).copy()
    except Exception:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=1800, show_spinner=False)
def _get_info_cached(ticker):
    """Scarica e mette in cache per 30 min i fondamentali .info del ticker evitando chiamate duplicate."""
    try:
        inf = yf.Ticker(str(ticker).strip().upper()).info
        return inf if isinstance(inf, dict) else {}
    except Exception:
        return {}

def _get_ohlc_from_hub(ticker, ohlc_map=None, period="1y"):
    """Recupera lo storico OHLCV prima dal batch in RAM, poi dalla cache singola."""
    tk_u = str(ticker or "").strip().upper()
    if not tk_u:
        return pd.DataFrame()
    if isinstance(ohlc_map, dict) and tk_u in ohlc_map:
        df_m = ohlc_map[tk_u]
        if df_m is not None and not df_m.empty:
            return df_m.copy()
    return _get_single_ohlc_cached(tk_u, period=period)

def _calcola_giorni_detenzione_posizione(pos, registro_acquisti=None):
    """
    Calcola i giorni di detenzione di una posizione usando fallback sicuro:
    1) pos['Data_Acquisto'] / pos['data_acquisto'] (sempre tagliato a [:10])
    2) data più vecchia trovata per quel ticker in registro_acquisti*.json (sempre [:10])
    3) None se nessuna data disponibile (evita smobilizzi Fonte B alla cieca).
    """
    tk_u = str((pos or {}).get("Ticker", "")).strip().upper()
    date_cand = []
    for k_dt in ("Data_Acquisto", "data_acquisto"):
        raw_d = str((pos or {}).get(k_dt, "") or "").strip()[:10]
        if len(raw_d) == 10:
            try:
                date_cand.append(datetime.strptime(raw_d, "%Y-%m-%d"))
            except Exception:
                pass
    if not date_cand and tk_u and isinstance(registro_acquisti, list):
        for r in registro_acquisti:
            if not isinstance(r, dict):
                continue
            if str(r.get("Ticker", "")).strip().upper() != tk_u:
                continue
            raw_r = str(r.get("Data", "") or "").strip()[:10]
            if len(raw_r) == 10:
                try:
                    date_cand.append(datetime.strptime(raw_r, "%Y-%m-%d"))
                except Exception:
                    pass
    if not date_cand:
        return None
    dt_min = min(date_cand)
    return max(0, (datetime.now() - dt_min).days)

def _formatta_badge_sec_tabella(sec_buys, sec_val_usd=0.0, sec_ult=""):
    """Formatta in modo compatto la colonna 'Insider SEC (90gg)' della tabella Salute Portafoglio."""
    n = int(sec_buys or 0)
    if n <= 0:
        return "—"
    v = float(sec_val_usd or 0.0)
    if v >= 1_000_000:
        v_str = f"${v / 1_000_000:.2f}M"
    elif v >= 1_000:
        v_str = f"${v / 1_000:.0f}k"
    elif v > 0:
        v_str = f"${v:,.0f}"
    else:
        v_str = ""
    dt_it = ""
    raw_u = str(sec_ult or "").strip()[:10]
    if len(raw_u) == 10:
        try:
            dt_it = datetime.strptime(raw_u, "%Y-%m-%d").strftime("%d/%m")
        except Exception:
            dt_it = raw_u
    pezzi = [f"🏛️ {n} acq"]
    if v_str:
        pezzi.append(v_str)
    out = " / ".join(pezzi)
    if dt_it:
        out += f" ({dt_it})"
    return out

def _calcola_winrate_storico_60gg(df):
    """Calcola la probabilità statistica storica (WinRate %) su finestre rolling di 60 sedute."""
    try:
        if df is None or df.empty or "Close" not in df.columns:
            return None
        closes = df["Close"].dropna()
        if len(closes) >= 90:
            ret_60 = (closes.shift(-60) / closes - 1.0).dropna()
            if len(ret_60) > 0:
                return round(float((ret_60 > 0).mean() * 100.0), 1)
        elif len(closes) >= 25:
            win = max(10, len(closes) // 3)
            ret_w = (closes.shift(-win) / closes - 1.0).dropna()
            if len(ret_w) > 0:
                return round(float((ret_w > 0).mean() * 100.0), 1)
    except Exception:
        pass
    return None

def _valuta_fondamentali_tom_nash(info_dict, s_score=50):
    """
    Valuta in modo pulito e anti-dati sporchi i fondamentali secondo la filosofia Tom Nash
    usando esclusivamente info_dict già in cache (_get_info_cached, zero chiamate API extra):
    - Crescita reale: revenueGrowth >= +5% oppure earningsGrowth >= +5%.
    - Bonus Sconto Multipli (anti-Value Trap): solo se crescita reale >= +5%, 0 < forwardPE < 65
      e 0 < trailingPE < 250 -> +8 pt se sconto >= 20% (fwd <= 0.80*trail), +5 pt se >= 10%.
    - Scudo Fondamentale Anti-Panico: attivo se crescita reale >= +5% e multiplo sano in compressione
      (0 < forwardPE < 65 e forwardPE < trailingPE * 0.95) oppure crescita ricavi >= +15% con S-Score >= 65.
    """
    info = info_dict if isinstance(info_dict, dict) else {}

    def _safe_float(val):
        try:
            f = float(val)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        except Exception:
            return None

    rev_g = _safe_float(info.get("revenueGrowth"))
    earn_g = _safe_float(info.get("earningsGrowth"))
    trail_pe = _safe_float(info.get("trailingPE"))
    fwd_pe = _safe_float(info.get("forwardPE"))

    rev_g_pct = round(rev_g * 100.0, 1) if rev_g is not None else None
    earn_g_pct = round(earn_g * 100.0, 1) if earn_g is not None else None
    crescita_reale = bool((rev_g is not None and rev_g >= 0.05) or (earn_g is not None and earn_g >= 0.05))

    # Bonus Sconto Multipli (anti-Value Trap: entrambi i P/E positivi e realistici + crescita reale)
    bonus_multipli = 0
    badge_multipli = ""
    if (
        crescita_reale
        and fwd_pe is not None and 0.0 < fwd_pe < 65.0
        and trail_pe is not None and 0.0 < trail_pe < 250.0
    ):
        if fwd_pe <= trail_pe * 0.80:
            bonus_multipli = 8
        elif fwd_pe <= trail_pe * 0.90:
            bonus_multipli = 5
        if bonus_multipli > 0:
            badge_multipli = f"💎 Sconto Multipli (Fwd P/E {fwd_pe:.1f}x vs {trail_pe:.1f}x)"

    # Scudo Fondamentale Tom Nash (anti-dati sporchi su P/E negativi/estremi e micro-crescite)
    multiplo_sano_compressione = bool(
        fwd_pe is not None and 0.0 < fwd_pe < 65.0
        and (trail_pe is None or trail_pe <= 0.0 or fwd_pe < trail_pe * 0.95)
    )
    crescita_forte_sana = bool((rev_g is not None and rev_g >= 0.15) and int(s_score or 50) >= 65)
    scudo_attivo = bool(crescita_reale and (multiplo_sano_compressione or crescita_forte_sana))

    parti_nota = []
    if rev_g_pct is not None and rev_g_pct >= 5.0:
        parti_nota.append(f"Fatturato {rev_g_pct:+.0f}%")
    elif earn_g_pct is not None and earn_g_pct >= 5.0:
        parti_nota.append(f"Utili {earn_g_pct:+.0f}%")
    if fwd_pe is not None and 0.0 < fwd_pe < 65.0:
        if trail_pe is not None and 0.0 < trail_pe < 250.0 and fwd_pe < trail_pe * 0.95:
            parti_nota.append(f"Forward P/E {fwd_pe:.1f}x in calo da {trail_pe:.1f}x")
        else:
            parti_nota.append(f"Forward P/E {fwd_pe:.1f}x")
    nota_scudo = ", ".join(parti_nota) if parti_nota else f"S-Score {int(s_score or 50)}/100"

    return {
        "rev_growth_pct": rev_g_pct,
        "earn_growth_pct": earn_g_pct,
        "trailing_pe": round(trail_pe, 1) if (trail_pe is not None and trail_pe > 0) else None,
        "forward_pe": round(fwd_pe, 1) if (fwd_pe is not None and fwd_pe > 0) else None,
        "bonus_multipli": bonus_multipli,
        "badge_multipli": badge_multipli,
        "scudo_tom_nash": scudo_attivo,
        "scudo_tom_nash_nota": nota_scudo,
    }

def _valuta_salute_portafoglio_home(portafoglio, eurusd_rate, cache_salute=None, ohlc_map=None):
    """
    Valuta salute e probabilità statistica di ciascun titolo in portafoglio:
    P&L %, S-Score, acquisti SEC Form 4 90gg (chiave 'buys', importo $ e data),
    SMA 50/200, Fase Weinstein, WinRate storico a 60gg, RSI, anzianità posizione,
    ripartizione PAC/Spot e metriche fondamentali Tom Nash (zero chiamate API extra).
    """
    salute = dict(cache_salute or {})
    reg_acq_u = carica_json(REGISTRO_ACQUISTI_FILE, default=[])
    if not isinstance(reg_acq_u, list):
        reg_acq_u = []

    for pos in (portafoglio or []):
        tk = str(pos.get("Ticker", "")).strip().upper()
        if not tk:
            continue
        qta = float(pos.get("Quantita", 0) or 0)
        pmc = float(pos.get("Prezzo_Medio", 0) or 0)
        p_eur = float(pos.get("Prezzo_Attuale_EUR") or 0)
        val_car = round(qta * pmc, 2)
        val_att = round(qta * p_eur, 2) if p_eur > 0 else val_car
        pnl_eur = round(val_att - val_car, 2)
        pnl_pct = round(((p_eur / pmc) - 1.0) * 100.0, 2) if (p_eur > 0 and pmc > 0) else float(pos.get("PnL_%", 0) or 0)
        gg_det = _calcola_giorni_detenzione_posizione(pos, reg_acq_u)
        q_pac_p, q_spot_p = _calcola_ripartizione_pac_spot(pos)
        tipo_badge = _formatta_badge_tipo_posizione(pos, con_dettaglio=False)
        tipo_dettaglio = _formatta_badge_tipo_posizione(pos, con_dettaglio=True)

        # Recupera acquisti SEC Form 4 (chiave esatta 'buys', throttling gentile max_docs=8 + cache 30 min)
        sec_buys = 0
        sec_num_ins = 0
        sec_val_usd = 0.0
        sec_ult = ""
        try:
            sec_d = get_sec_insider_buys_90gg(tk, max_docs=8) if "get_sec_insider_buys_90gg" in globals() else None
            if isinstance(sec_d, dict):
                sec_buys = int(sec_d.get("buys") or 0)
                sec_num_ins = int(sec_d.get("num_insider") or 0)
                sec_val_usd = float(sec_d.get("valore_usd") or 0.0)
                sec_ult = str(sec_d.get("ultimo_acquisto") or "")
        except Exception:
            pass

        esistente = salute.get(tk)
        if isinstance(esistente, dict) and esistente.get("s_score") is not None and esistente.get("fase"):
            tn_es = _valuta_fondamentali_tom_nash(_get_info_cached(tk), s_score=esistente.get("s_score", 50))
            esistente.update({
                "pnl_pct": pnl_pct,
                "pnl_eur": pnl_eur,
                "val_car": val_car,
                "val_att": val_att,
                "tipo": tipo_badge,
                "tipo_dettaglio": tipo_dettaglio,
                "qta_pac": q_pac_p,
                "qta_spot": q_spot_p,
                "giorni_detenzione": gg_det,
                "sec_buys": sec_buys,
                "sec_num_insider": sec_num_ins,
                "sec_valore_usd": sec_val_usd,
                "sec_ultimo_acquisto": sec_ult,
                **tn_es,
            })
            salute[tk] = esistente
            continue

        s_score = 50
        fase = "N/D"
        sma50_val = None
        sma200_val = None
        sopra_sma50 = None
        sopra_sma200 = None
        winrate_60g = None
        rsi_val = 50.0
        close_oggi = None
        close_ieri = None
        tn_info = _valuta_fondamentali_tom_nash({}, s_score=50)
        try:
            df_h = _get_ohlc_from_hub(tk, ohlc_map=ohlc_map, period="1y")
            info_h = _get_info_cached(tk)
            s_score = calcola_s_score(info_h)
            tn_info = _valuta_fondamentali_tom_nash(info_h, s_score=s_score)
            if df_h is not None and not df_h.empty:
                df_h = df_h.dropna(subset=["Close"])
                closes = df_h["Close"]
                if len(closes) >= 2:
                    close_oggi = float(closes.iloc[-1])
                    close_ieri = float(closes.iloc[-2])
                elif len(closes) == 1:
                    close_oggi = float(closes.iloc[-1])
                    close_ieri = close_oggi
                if len(closes) >= 15:
                    delta_r = closes.diff()
                    g_r = delta_r.clip(lower=0).rolling(14).mean()
                    l_r = (-delta_r.clip(upper=0)).rolling(14).mean()
                    rs_r = g_r / l_r.replace(0, np.nan)
                    rsi_s = (100 - (100 / (1 + rs_r))).iloc[-1]
                    if pd.notna(rsi_s):
                        rsi_val = round(float(rsi_s), 1)
                if len(df_h) >= 50:
                    fase = rileva_fase_weinstein(df_h)
                    sma50_val = float(closes.rolling(window=50).mean().iloc[-1])
                    if pd.notna(sma50_val) and sma50_val > 0 and close_oggi is not None:
                        sopra_sma50 = bool(close_oggi >= sma50_val)
                winrate_60g = _calcola_winrate_storico_60gg(df_h)
                if len(df_h) >= 200:
                    sma200_val = float(closes.rolling(window=200).mean().iloc[-1])
                    if pd.notna(sma200_val) and sma200_val > 0 and close_oggi is not None:
                        sopra_sma200 = bool(close_oggi >= sma200_val)
        except Exception:
            pass

        salute[tk] = {
            "ticker": tk,
            "s_score": int(s_score or 50),
            "fase": str(fase or "N/D"),
            "sma50": round(sma50_val, 2) if sma50_val is not None else None,
            "sma200": round(sma200_val, 2) if sma200_val is not None else None,
            "sopra_sma50": sopra_sma50,
            "sopra_sma200": sopra_sma200,
            "rsi": rsi_val,
            "close_oggi": close_oggi,
            "close_ieri": close_ieri,
            "winrate_60g": winrate_60g,
            "pnl_pct": pnl_pct,
            "pnl_eur": pnl_eur,
            "val_car": val_car,
            "val_att": val_att,
            "tipo": tipo_badge,
            "tipo_dettaglio": tipo_dettaglio,
            "qta_pac": q_pac_p,
            "qta_spot": q_spot_p,
            "giorni_detenzione": gg_det,
            "sec_buys": sec_buys,
            "sec_num_insider": sec_num_ins,
            "sec_valore_usd": sec_val_usd,
            "sec_ultimo_acquisto": sec_ult,
            **tn_info,
        }
    return salute

def esegui_radar_ignition_80(watchlist_str="", ohlc_map=None, progress_bar=None):
    """
    Motore estratto Radar IGNITION — Inizio Salita (80 Titoli + Watchlist).
    Mantiene intatti tutti i filtri originali e salva in st.session_state['risultati_radar_ignition_80'].
    """
    wl_tks = [x.strip().upper() for x in str(watchlist_str or "").replace("\n", ",").split(",") if x.strip()]
    lista_ig = sorted(list(set(IGNITION_UNIVERSE if "IGNITION_UNIVERSE" in globals() else []) | set(wl_tks)))
    if not lista_ig:
        st.session_state["risultati_radar_ignition_80"] = []
        return [], []

    if ohlc_map is None:
        ohlc_map = _scarica_ohlc_batch_cached(tuple(lista_ig), period="1y")

    trovati_ig = []
    pre_ig = []
    attivi_meta = []
    tot_ig = max(1, len(lista_ig))
    for idx_i, tk_i in enumerate(lista_ig):
        if progress_bar is not None:
            try:
                progress_bar.progress((idx_i + 1) / tot_ig, text=f"Analisi IGNITION: {tk_i} ({idx_i+1}/{tot_ig})")
            except Exception:
                pass
        try:
            df_i = _get_ohlc_from_hub(tk_i, ohlc_map=ohlc_map, period="1y")
            if df_i is None or df_i.empty or "Close" not in df_i.columns or "Volume" not in df_i.columns:
                continue
            df_i = df_i.tail(130).dropna(subset=["Close", "Volume"])
            if len(df_i) >= 25:
                c = df_i["Close"]
                v = df_i["Volume"]
                p_now = float(c.iloc[-1])
                p_prev = float(c.iloc[-2])
                sma20 = c.rolling(20).mean()
                std20 = c.rolling(20).std()
                s20_now = float(sma20.iloc[-1])
                s20_prev = float(sma20.iloc[-2])
                bb_w = ((sma20 + 2 * std20) - (sma20 - 2 * std20)) / sma20
                squeeze = float(bb_w.iloc[-1]) <= float(bb_w.tail(60).quantile(0.30))
                vol_r = float(v.iloc[-1]) / max(1.0, float(v.tail(21).iloc[:-1].mean()))
                delta = c.diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain / loss.replace(0, np.nan)
                rsi_i = float((100 - (100 / (1 + rs))).iloc[-1])
                riconq = (p_now > s20_now) and (p_prev <= s20_prev * 1.01) and (p_now > p_prev)
                vp_i, wh_i = calcola_livello_balene(df_i) if "calcola_livello_balene" in globals() else (None, "")
                ins_i = " | 🕵️ INSIDER" if ("get_giorni_insider_rimanenti" in globals() and get_giorni_insider_rimanenti(tk_i) != "-") else ""
                dist_s20 = ((p_now - s20_now) / s20_now) * 100
                if (riconq or (squeeze and p_now > s20_now and p_now > p_prev)) and vol_r >= 1.20 and 40 <= rsi_i <= 68:
                    tag_sq = "🔥 Squeeze + " if squeeze else ""
                    det_i = f"{tag_sq}Riconquista SMA20 (${s20_now:.2f}) | Vol {vol_r:.2f}x | RSI {rsi_i:.0f} {wh_i}{ins_i}".strip()
                    row_ok = {"Ticker": tk_i, "Prezzo $": f"${p_now:.2f}", "Stato": "🚀 IGNITION ATTIVO", "Dettagli & Conferme": det_i}
                    trovati_ig.append(row_ok)
                    attivi_meta.append({
                        "ticker": tk_i,
                        "prezzo": p_now,
                        "sma20": s20_now,
                        "vol_ratio": round(vol_r, 2),
                        "rsi": round(rsi_i, 1),
                        "squeeze": bool(squeeze),
                        "dettaglio": det_i,
                    })
                elif (-2.5 <= dist_s20 <= 2.5) and 42 <= rsi_i <= 62 and (squeeze or vol_r >= 1.05):
                    sc_pre = (20 if squeeze else 0) + (vol_r * 10) + (5 if ins_i else 0)
                    tag_sq2 = "🔥 Squeeze | " if squeeze else ""
                    det_p = f"{tag_sq2}Dist. SMA20: {dist_s20:+.1f}% (${s20_now:.2f}) | Vol {vol_r:.2f}x | RSI {rsi_i:.0f} {wh_i}{ins_i}".strip()
                    pre_ig.append((sc_pre, {"Ticker": tk_i, "Prezzo $": f"${p_now:.2f}", "Stato": "⏳ PRE-IGNITION", "Dettagli & Conferme": det_p}))
        except Exception:
            pass
    pre_ig.sort(key=lambda x: x[0], reverse=True)
    risultati_finali = trovati_ig + [x[1] for x in pre_ig[:6]]
    st.session_state["risultati_radar_ignition_80"] = risultati_finali
    return risultati_finali, attivi_meta

def esegui_scansione_insider_sec(
    watchlist_str="",
    portafoglio=None,
    solo_con_insider=True,
    min_s_score=55,
    max_dist_min=30,
    include_panier_esteso=True,
    max_docs_sec=12,
    progress_bar=None,
):
    """
    Motore estratto Insider Tracker (SEC Form 4 & Stagionalità 10 Anni).
    Mantiene i filtri originali; in cascata Home usa include_panier_esteso=False + max_docs_sec=8
    per rispettare con margine il rate-limit SEC EDGAR (10 req/s) e restare veloce su Mobile.
    """
    wl_attuale = [t.strip().upper() for t in str(watchlist_str or "").replace("\n", ",").split(",") if t.strip()]
    port_data = portafoglio if isinstance(portafoglio, list) else (st.session_state.get("portafoglio") or carica_json(PORTAFOGLIO_FILE) or [])
    port_tks = [str(p.get("Ticker") or p.get("ticker") or "").strip().upper() for p in port_data if isinstance(p, dict) and (p.get("Ticker") or p.get("ticker"))]
    panier = set(PANIER_INSIDER_MID_LARGE) if (include_panier_esteso and "PANIER_INSIDER_MID_LARGE" in globals()) else set()
    lista_tot = sorted(list(set(wl_attuale) | set(port_tks) | panier))

    risultati_ins = []
    promossi_oggi = []
    tot_ins = max(1, len(lista_tot))
    for idx_i, tk_i in enumerate(lista_tot):
        if progress_bar is not None:
            try:
                progress_bar.progress((idx_i + 1) / tot_ins, text=f"Scansione Insider {tk_i} ({idx_i+1}/{tot_ins})...")
            except Exception:
                pass
        try:
            # In modalità cascata leggera interroga prima SEC con max_docs ridotto (cachato 30 min)
            if not include_panier_esteso and solo_con_insider:
                sec_q = get_sec_insider_buys_90gg(tk_i, max_docs=max_docs_sec)
                if not isinstance(sec_q, dict) or int(sec_q.get("buys") or 0) <= 0:
                    continue
            res_i = analizza_insider_e_minimi(tk_i)
            if not res_i:
                continue
            if solo_con_insider and res_i["_buys"] == 0:
                continue
            if res_i["S-Score"] < min_s_score:
                continue
            promossi_file = "insider_promossi.json"
            promossi = carica_json(promossi_file) or {}
            if not isinstance(promossi, dict):
                promossi = {}
            t_code = res_i["Ticker"]
            l_buy = res_i.get("_last_buy_str", "")
            prev_b = promossi[t_code].get("data_acquisto", "") if isinstance(promossi.get(t_code), dict) else str(promossi.get(t_code, ""))
            if t_code in promossi and prev_b >= l_buy and l_buy != "":
                continue
            # Se è salito troppo (> +18% o RSI > 68) ma buona azienda (S-Score >= 65) -> promuove in Watchlist
            if (res_i.get("_var_ins", 0) > 18.0 or res_i["RSI"] > 68) and res_i["S-Score"] >= 65:
                if include_panier_esteso:
                    if l_buy:
                        promossi[t_code] = {
                            "data_acquisto": l_buy,
                            "data_promozione": datetime.now().strftime("%Y-%m-%d"),
                            "dettagli": f"{res_i.get('Insider (90gg)', '')} | {res_i.get('Valore Insider $', '')}",
                        }
                        salva_json(promossi_file, promossi)
                    imp_loc = carica_json(IMPOSTAZIONI_FILE) or {}
                    if not isinstance(imp_loc, dict):
                        imp_loc = {}
                    wl_list = [x.strip().upper() for x in str(imp_loc.get("lista_ticker_default", "")).split(",") if x.strip()]
                    if t_code not in wl_list:
                        wl_list.append(t_code)
                        imp_loc["lista_ticker_default"] = ", ".join(wl_list)
                        salva_json(IMPOSTAZIONI_FILE, imp_loc)
                    promossi_oggi.append(t_code)
                continue
            dist_val = float(str(res_i["Dist. Min 52w %"]).replace("+", "").replace("%", "").replace("nan", "0"))
            if dist_val <= max_dist_min or res_i["_buys"] >= 2:
                _, stag_txt = calcola_stagionalita_10y(tk_i)
                res_i["Stagionalità 60gg"] = stag_txt or "N/D"
                if stag_txt and stag_txt.startswith("+"):
                    res_i["Score"] += 10
                risultati_ins.append(res_i)
        except Exception:
            pass

    risultati_ins.sort(key=lambda x: (x["Score"], x["S-Score"]), reverse=True)
    for idx_r, item_r in enumerate(risultati_ins):
        medal = "🥇 #1 TOP" if idx_r == 0 else ("🥈 #2" if idx_r == 1 else ("🥉 #3" if idx_r == 2 else f"#{idx_r+1}"))
        item_r["Scelta"] = medal
    st.session_state.insider_results = risultati_ins
    if promossi_oggi:
        st.session_state.setdefault("insider_promossi_oggi", []).extend(promossi_oggi)
    return risultati_ins, promossi_oggi

def esegui_scansione_ai_palantir(
    watchlist_str="",
    period="1y",
    eurusd_rate=1.12,
    ohlc_map=None,
    scrivi_paper=False,
    progress_bar=None,
):
    """
    Motore estratto Setup Palantir AI (Watchlist + BIG_TECH_GROWTH_LIST).
    Mantiene i filtri originali (S-Score >= 75, RevGrowth >= 20%, 0 < PEG < 1.5, RSI < 45, dist SMA200 <= 5%).
    In cascata Home gira con scrivi_paper=False (sola proposta, senza auto-scrivere in paper_trading.json).
    """
    tickers_personali = [t.strip().upper() for t in str(watchlist_str or "").replace("\n", ",").split(",") if t.strip()]
    tickers_big_tech = [t.strip().upper() for t in BIG_TECH_GROWTH_LIST.split(",") if t.strip()]
    tutti_tickers = sorted(list(set(tickers_personali + tickers_big_tech)))
    if ohlc_map is None:
        ohlc_map = _scarica_ohlc_batch_cached(tuple(tutti_tickers), period="1y")

    candidati_palantir = []
    tot_p = max(1, len(tutti_tickers))
    for i, ticker in enumerate(tutti_tickers):
        if progress_bar is not None:
            try:
                progress_bar.progress((i + 1) / tot_p)
            except Exception:
                pass
        try:
            df = _get_ohlc_from_hub(ticker, ohlc_map=ohlc_map, period="1y")
            if df is None or df.empty or len(df) < 200:
                continue
            info = _get_info_cached(ticker)
            currency = str(info.get("currency", "USD") or "USD").upper()
            prezzo_attuale = float(df["Close"].dropna().iloc[-1])
            prezzo_eur = round(prezzo_attuale / eurusd_rate if currency == "USD" else prezzo_attuale, 2)
            s_score = calcola_s_score(info)
            delta = df["Close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss.replace(0, np.nan)
            rsi_val = (100 - (100 / (1 + rs))).iloc[-1]
            rsi_oggi = float(rsi_val) if pd.notna(rsi_val) else 50.0
            revenue_growth = info.get("revenueGrowth", 0.0) or 0.0
            peg_ratio = info.get("pegRatio", 0.0) or 0.0
            sma200 = float(df["Close"].rolling(window=200).mean().iloc[-1])
            distanza_sma200_pct = abs(prezzo_attuale - sma200) / sma200 * 100 if sma200 > 0 else 999
            is_palantir = (
                s_score >= 75
                and revenue_growth >= 0.20
                and (peg_ratio > 0 and peg_ratio < 1.5)
                and rsi_oggi < 45
                and distanza_sma200_pct <= 5.0
            )
            if is_palantir:
                candidati_palantir.append({
                    "Ticker": ticker,
                    "Prezzo EUR": prezzo_eur,
                    "Prezzo Nat": round(prezzo_attuale, 2),
                    "Currency": currency,
                    "S-Score": s_score,
                    "RSI": round(rsi_oggi, 1),
                    "PEG": round(peg_ratio, 2) if peg_ratio > 0 else "N/D",
                    "Rev Growth": f"{revenue_growth*100:.1f}%",
                    "Distanza SMA200": f"{distanza_sma200_pct:.1f}%",
                    "SMA200": round(sma200, 2),
                })
        except Exception:
            pass

    candidati_palantir.sort(key=lambda x: x["S-Score"], reverse=True)
    st.session_state["ai_palantir_candidati"] = candidati_palantir
    if candidati_palantir:
        cols_df = ["Ticker", "Prezzo EUR", "S-Score", "RSI", "PEG", "Rev Growth", "Distanza SMA200"]
        st.session_state.df_palantir = pd.DataFrame([{k: c[k] for k in cols_df} for c in candidati_palantir])

    nuovi_trade = []
    if scrivi_paper and candidati_palantir:
        paper_port = carica_json(PAPER_TRADING_FILE) or []
        attivi_tickers = [p["Ticker"] for p in paper_port if p.get("Stato") == "Attivo"]
        for c in candidati_palantir[:3]:
            if c["Ticker"] not in attivi_tickers:
                entry_price = c["Prezzo EUR"]
                nuovi_trade.append({
                    "Ticker": c["Ticker"],
                    "Entry": round(entry_price, 2),
                    "Stop_Loss": round(entry_price * 0.92, 2),
                    "Target": round(entry_price * 1.20, 2),
                    "Data_Ingresso": datetime.now().strftime("%Y-%m-%d"),
                    "Stato": "Attivo",
                })
        if nuovi_trade:
            paper_port.extend(nuovi_trade)
            salva_json(PAPER_TRADING_FILE, paper_port)
    return candidati_palantir, nuovi_trade, len(tutti_tickers)

def esegui_scansione_completa_motore(
    impostazioni,
    tickers_input,
    catalizzatori_input,
    esclusioni_input,
    period,
    sma_short,
    sma_long,
    eurusd_rate,
    ignore_fase_4,
    semaforo_header,
    salva_impostazioni=True,
    progress_bar=None,
    mostra_info_avvio=True,
    ohlc_map=None,
    max_docs_sec=12,
):
    """
    Esegue la scansione completa del motore (pattern_engine.py + Insider SEC Form 4 +
    aggiornamento Bacheca Segnali Attivi) usando il Market Data Hub condiviso senza modificare
    alcun filtro e salva tutti i risultati in st.session_state.
    """
    _fp_imp = _get_impostazioni_path()
    if salva_impostazioni:
        impostazioni["lista_ticker_default"] = tickers_input
        impostazioni["catalizzatori"] = catalizzatori_input
        impostazioni["esclusioni"] = esclusioni_input
        with open(_fp_imp, 'w', encoding='utf-8') as f:
            json.dump(impostazioni, f, indent=4, ensure_ascii=False)
            try:
                _sync_github_file(IMPOSTAZIONI_FILE, json.dumps(impostazioni, indent=4, ensure_ascii=False), mode='push')
            except Exception:
                pass

    pbar_locale = progress_bar is None
    if pbar_locale:
        progress_bar = st.progress(0)

    if st.session_state.spy_data is None:
        try:
            st.session_state.spy_data = _get_single_ohlc_cached("SPY", period=period)
        except Exception:
            st.session_state.spy_data = None

    stats = {
        'by_count': 0, 'hold_count': 0, 'sell_count': 0,
        'by_tickers': list(), 'hold_tickers': list(), 'sell_tickers': list(),
        'earnings_warnings': list(), 'error_tickers': list(),
        'by_fabio_tickers': list(), 'smci_tickers': list(),
        'ignition_oggi': list(), 'metriche_scan': dict()
    }
    pyramiding_alerts, take_profit_alerts, zona_interesse_alerts, extended_hours_alerts = list(), list(), list(), list()
    lista_fortezza, lista_cavalli, lista_monitor, lista_palantir = list(), list(), list(), list()
    # Inizializza il contenitore degli alert del motore figure grafiche secondo il regime SPY
    _spy_regime_scan = (semaforo_header.get('stato') if isinstance(semaforo_header, dict) else 'verde') or 'verde'
    pattern_alerts_scan = pattern_engine.crea_contenitore_pattern_alerts(spy_regime=_spy_regime_scan)
    sorvegliati_candidati_scan = list()
    cluster_insider_bacheca_scan = list()
    scan_price_map_bacheca = dict()
    salute_portafoglio_scan = dict()

    tickers_base = [t.strip().upper() for t in str(tickers_input or "").split(",") if t.strip()]
    watchlist_only_set = {str(t).strip().upper() for t in tickers_base if str(t).strip()}
    portafoglio_attuale = st.session_state.portafoglio if isinstance(st.session_state.portafoglio, list) else (carica_json(PORTAFOGLIO_FILE) or PORTAFOGLIO_INIZIALE)
    ticker_in_portafoglio = {str(p['Ticker']).strip().upper(): p for p in portafoglio_attuale if p.get('Ticker')}
    tickers_scan = sorted(list(set(tickers_base + list(ticker_in_portafoglio.keys()))))

    periodo_analisi = '1y' if period in ['3mo', '6mo'] else period
    if ohlc_map is None and tickers_scan:
        ohlc_map = _scarica_ohlc_batch_cached(tuple(tickers_scan), period=periodo_analisi)

    if mostra_info_avvio:
        st.info(f"🔄 Scansione avviata per {len(tickers_scan)} titoli.")

    tot_tk = max(1, len(tickers_scan))
    for i, ticker in enumerate(tickers_scan):
        try:
            progress_bar.progress((i + 1) / tot_tk)
        except Exception:
            pass
        try:
            df = _get_ohlc_from_hub(ticker, ohlc_map=ohlc_map, period=periodo_analisi)
            if df is None or df.empty or len(df) < max(sma_long, 50):
                continue
            ticker_obj = yf.Ticker(ticker)
            info = _get_info_cached(ticker)
            currency = str(info.get("currency", "USD") or "USD").upper()
            prezzo_usd = float(df["Close"].dropna().iloc[-1])
            prezzo_eur = round(prezzo_usd / eurusd_rate if currency == "USD" else prezzo_usd, 2)
            if prezzo_eur is None or prezzo_eur <= 0:
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
            rs = gain / loss.replace(0, np.nan)
            rsi_val_raw = (100 - (100 / (1 + rs))).iloc[-1] if not rs.empty else 50
            rsi_oggi = float(rsi_val_raw) if pd.notna(rsi_val_raw) else 50.0
            revenue_growth = info.get('revenueGrowth', 0.0) or 0.0
            peg_ratio = info.get('pegRatio', 0.0) or 0.0
            sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
            sma50 = df['Close'].rolling(window=50).mean().iloc[-1]
            closes_clean = df['Close'].dropna()
            prezzo_attuale = float(closes_clean.iloc[-1])
            prezzo_prec_close = float(closes_clean.iloc[-2]) if len(closes_clean) >= 2 else prezzo_attuale
            distanza_sma200_pct = abs(prezzo_attuale - sma200) / sma200 * 100 if (pd.notna(sma200) and sma200 > 0) else 999

            # Salva la salute dettagliata per i titoli del portafoglio (incluso WinRate 60gg, RSI, SMA50/200)
            if ticker in ticker_in_portafoglio:
                pos_s = ticker_in_portafoglio[ticker]
                pmc_s = float(pos_s.get('Prezzo_Medio', 0) or 0)
                qta_s = float(pos_s.get('Quantita', 0) or 0)
                pnl_p_s = round(((prezzo_eur / pmc_s) - 1.0) * 100.0, 2) if pmc_s > 0 else 0.0
                val_car_s = round(qta_s * pmc_s, 2)
                val_att_s = round(qta_s * prezzo_eur, 2)
                salute_portafoglio_scan[ticker] = {
                    "ticker": ticker,
                    "s_score": int(s_score or 50),
                    "fase": str(fase or "N/D"),
                    "sma50": round(float(sma50), 2) if pd.notna(sma50) else None,
                    "sma200": round(float(sma200), 2) if pd.notna(sma200) else None,
                    "sopra_sma50": bool(prezzo_attuale >= sma50) if (pd.notna(sma50) and sma50 > 0) else None,
                    "sopra_sma200": bool(prezzo_attuale >= sma200) if (pd.notna(sma200) and sma200 > 0) else None,
                    "rsi": round(rsi_oggi, 1),
                    "close_oggi": prezzo_attuale,
                    "close_ieri": prezzo_prec_close,
                    "winrate_60g": _calcola_winrate_storico_60gg(df),
                    "pnl_pct": pnl_p_s,
                    "pnl_eur": round(val_att_s - val_car_s, 2),
                    "val_car": val_car_s,
                    "val_att": val_att_s,
                    "tipo": str(pos_s.get('Tipo', 'Spot')),
                }

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
                    _sec_ins_scan = get_sec_insider_buys_90gg(ticker, max_docs=max_docs_sec) if 'get_sec_insider_buys_90gg' in globals() else None
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
    if pbar_locale:
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
    # Completa eventuali titoli in portafoglio con storico < 200 candele nella mappa salute Home
    st.session_state["home_salute_portafoglio"] = _valuta_salute_portafoglio_home(
        st.session_state.get("portafoglio") or [],
        eurusd_rate,
        cache_salute=salute_portafoglio_scan,
        ohlc_map=ohlc_map,
    )
    st.session_state.scansione_completata = True
    st.session_state["home_cascata_eseguita"] = True

@st.cache_data(ttl=900, show_spinner=False)
def _verifica_qqq_regime_verde():
    """Verifica lo stato del Nasdaq 100 (QQQ): (verde: bool, stato_str: 'verde'|'giallo'|'rosso', nota: str)."""
    try:
        df_q = _get_single_ohlc_cached("QQQ", period="1y")
        if df_q is None or df_q.empty or len(df_q) < 200:
            return False, "giallo", "QQQ N/D"
        closes = df_q["Close"].dropna()
        if len(closes) < 200:
            return False, "giallo", "QQQ N/D"
        p_q = float(closes.iloc[-1])
        sma50_q = float(closes.rolling(50).mean().iloc[-1])
        sma200_q = float(closes.rolling(200).mean().iloc[-1])
        if p_q >= sma50_q and p_q >= sma200_q:
            return True, "verde", f"QQQ verde (${p_q:.2f} sopra SMA50/SMA200)"
        if p_q < sma200_q:
            return False, "rosso", f"QQQ sotto SMA200 (${p_q:.2f} < ${sma200_q:.2f})"
        return False, "giallo", f"QQQ in correzione sotto SMA50 (${p_q:.2f} < ${sma50_q:.2f})"
    except Exception:
        return False, "giallo", "QQQ N/D"

def _formatta_taglia_esecuzione_tr(importo_eur, prezzo_eur, nascondi_eur=False):
    """
    Formatta l'istruzione di size pronta per Trade Republic:
    - Tra 40 € e 150 €: ordine in Euro (azioni frazionate) + avviso commissione 1 € se < 50 €.
    - >= 200 €: mostra sia azioni intere arrotondate con controvalore esatto sia importo frazionato.
    """
    imp = round(float(importo_eur or 0.0), 2)
    if nascondi_eur:
        return "€ ••••", ""
    if imp < 150.01:
        nota_comm = " (nota: sotto € 50 la commissione TR di € 1 incide >2%)" if imp < 50.0 else ""
        return f"€ {imp:,.2f} (in Euro / frazionate)", nota_comm
    if imp >= 200.0 and prezzo_eur and float(prezzo_eur) > 0:
        n_int = max(1, int(round(imp / float(prezzo_eur))))
        costo_int = round(n_int * float(prezzo_eur), 2)
        return f"€ {imp:,.2f} (oppure {n_int} azioni intere ≈ € {costo_int:,.2f})", ""
    return f"€ {imp:,.2f}", ""

def _calcola_hold_score_posizione(pos, inf):
    """
    Calcola a costo zero (dai dati già in salute_map) l'Hold-Score (0-100) di un titolo in portafoglio:
    valuta solidità fondamentale (S-Score), struttura grafica (Fase Weinstein + SMA 50/200),
    Scudo Tom Nash, Insider SEC Form 4 (90gg) e Bonus Sconto Multipli.
    """
    inf_d = inf if isinstance(inf, dict) else {}
    s_sc = int(inf_d.get("s_score", 55) or 55)
    fase_s = str(inf_d.get("fase", "N/D")).upper()
    sopra_50 = inf_d.get("sopra_sma50")
    sopra_200 = inf_d.get("sopra_sma200")
    sec_b = int(inf_d.get("sec_buys") or 0)
    scudo_tn = bool(inf_d.get("scudo_tom_nash"))
    bonus_m = int(inf_d.get("bonus_multipli") or 0)

    # 1) Base S-Score (0..40 pt)
    score = min(40.0, max(0.0, (s_sc / 100.0) * 40.0))
    # 2) Struttura grafica Weinstein + medie (0..30 pt)
    if "FASE 2" in fase_s:
        if sopra_50 is True and sopra_200 is True:
            score += 30.0
        elif sopra_200 is True or sopra_50 is True:
            score += 24.0
        else:
            score += 18.0
    elif "CORREZIONE" in fase_s:
        score += 22.0 if sopra_200 is True else 15.0
    elif "FASE 1" in fase_s:
        score += 18.0 if sopra_50 is True else 12.0
    elif "FASE 3" in fase_s:
        score += 8.0
    else:
        score += 4.0 if sopra_200 is True else 0.0
    # 3) Scudi istituzionali & fondamentali (0..30 pt)
    if scudo_tn:
        score += 12.0
    if sec_b >= 2:
        score += 12.0
    elif sec_b >= 1:
        score += 8.0
    if bonus_m > 0:
        score += 6.0
    return int(max(0, min(100, round(score))))

def _get_esclusioni_switch_attive():
    """Legge i ticker esclusi dallo Switch Piano B (sidebar '🚫 Esclusioni Switch' o impostazioni.json)."""
    raw = st.session_state.get("esclusioni_switch_input")
    if raw is None:
        imp_loc = carica_json(IMPOSTAZIONI_FILE, default={})
        raw = imp_loc.get("esclusioni", "") if isinstance(imp_loc, dict) else ""
    return {x.strip().upper() for x in re.split(r"[,;\s\n]+", str(raw or "")) if x.strip()}

def _trova_riserva_liquidita_intelligente(portafoglio, salute_map, target_score=None, modalita="BUY", liq_libera=0.0, esclusioni=None):
    """
    Piano B Qualitativo — Individua la migliore 'Riserva di Liquidità Intelligente' (Fonte A o Fonte B):
    - Rispetta sempre le '🚫 Esclusioni Switch' impostate dall'utente.
    - Fonte A (Raccolto Profitti): P&L >= +35% OPPURE (P&L >= +25% con RSI > 72) -> vendita parziale 50%
      (o 100% se il 50% netto + cassa < 50 €).
    - Fonte B (Rotazione Qualitativa — SOLO quote Spot, MAI quote PAC anche se sospese!):
      * P&L tra -3.0% e +12.0%, anzianità >= 45 giorni
      * NON in Fase 2 forte (non Fase 2 sopra SMA 50 con S-Score >= 70)
      * Zero acquisti Insider SEC 90gg e zero Scudo Tom Nash attivo
      * Delta Qualitativo obbligatorio: target_score - Hold-Score >= +20 pt (BUY) o >= +15 pt (DCA)
    Calcola il ricavo netto dopo 26% di tasse sulla sola plusvalenza e 2 € commissioni TR (1 € vendita + 1 € acquisto).
    Richiede (netto + eventuale cassa) >= 50.0 €; altrimenti restituisce None ('Portafoglio Intatto').
    """
    candidati_ris = []
    mod_u = str(modalita or "BUY").strip().upper()
    delta_min = 15 if mod_u == "DCA" else 20
    cassa_agg = max(0.0, float(liq_libera or 0.0))
    escl_set = {str(x).strip().upper() for x in esclusioni} if esclusioni is not None else _get_esclusioni_switch_attive()

    for pos in (portafoglio or []):
        tk = str(pos.get("Ticker", "")).strip().upper()
        if not tk or tk in escl_set:
            continue
        inf = (salute_map or {}).get(tk) or {}
        qta = float(pos.get("Quantita", 0) or 0)
        pmc = float(pos.get("Prezzo_Medio", 0) or 0)
        p_att = float(pos.get("Prezzo_Attuale_EUR") or 0)
        if qta <= 0 or pmc <= 0:
            continue
        val_car = qta * pmc
        val_att = (qta * p_att) if p_att > 0 else float(inf.get("val_att", val_car) or val_car)
        pnl_pct = ((val_att / val_car) - 1.0) * 100.0 if val_car > 0 else 0.0
        fase_s = str(inf.get("fase", "N/D")).upper()
        s_sc = int(inf.get("s_score", 60) or 60)
        rsi_v = float(inf.get("rsi", 50.0) or 50.0)
        sopra_50 = inf.get("sopra_sma50")
        gg_det = inf.get("giorni_detenzione")
        sec_b = int(inf.get("sec_buys") or 0)
        scudo_tn = bool(inf.get("scudo_tom_nash"))
        hold_score = _calcola_hold_score_posizione(pos, inf)

        # Fonte A: Raccolto Profitti parziale 50% Spot (>= +35% oppure >= +25% con RSI > 72) — soglia anti-briciole >= € 100 netti
        if pnl_pct >= 35.0 or (pnl_pct >= 25.0 and rsi_v > 72.0):
            _, q_spot_a = _calcola_ripartizione_pac_spot(pos)
            if q_spot_a > 1e-6:
                motivo_a = f"forte profitto ({pnl_pct:+.1f}%)" if pnl_pct >= 35.0 else f"profitto esteso ({pnl_pct:+.1f}%, RSI {rsi_v:.0f})"
                frac = min(1.0, q_spot_a / qta) * 0.5
                v_lordo = val_att * frac
                gain_lordo = max(0.0, (val_att - val_car) * frac)
                tasse_26 = gain_lordo * 0.26
                netto_disp = round(v_lordo - tasse_26 - 2.0, 2)
                if netto_disp >= SOGLIA_MIN_NETTO_FONTE_A:
                    candidati_ris.append({
                        "priorita": 1,
                        "fonte": "Fonte A (Raccolto Profitti)",
                        "ticker": tk,
                        "pct_vendita": 50,
                        "pnl_pct": round(pnl_pct, 1),
                        "hold_score": hold_score,
                        "delta_qualita": (int(target_score) - hold_score) if target_score is not None else None,
                        "lordo_eur": round(v_lordo, 2),
                        "tasse_eur": round(tasse_26, 2),
                        "netto_eur": netto_disp,
                        "motivo": motivo_a,
                    })
            continue

        # Fonte B: Rotazione Qualitativa — SOLO quote Spot (protezione assoluta PAC!)
        q_pac_p, q_spot_p = _calcola_ripartizione_pac_spot(pos)
        if q_spot_p <= 1e-6:
            continue
        if gg_det is None or gg_det < 45:
            continue
        # Esclude titoli in Fase 2 forte
        if ("FASE 2" in fase_s) and (sopra_50 is True) and s_sc >= 70:
            continue
        # Esclude titoli protetti da Insider SEC (90gg) o Scudo Fondamentale Tom Nash
        if sec_b > 0 or scudo_tn:
            continue
        # Verifica Delta Qualitativo obbligatorio (+20 pt BUY, +15 pt DCA)
        delta_q = None
        if target_score is not None:
            delta_q = int(target_score) - hold_score
            if delta_q < delta_min:
                continue
        if -3.0 <= pnl_pct <= 12.0:
            frazione_spot = min(1.0, q_spot_p / qta) if qta > 0 else 1.0
            v_lordo = val_att * frazione_spot
            gain_lordo = max(0.0, (val_att - val_car) * frazione_spot)
            tasse_26 = gain_lordo * 0.26
            # Commissioni Trade Republic: 1.00 € vendita + 1.00 € nuovo acquisto Spot = 2.00 €
            netto_disp = round(v_lordo - tasse_26 - 2.0, 2)
            if (netto_disp + cassa_agg) >= 50.0 and netto_disp >= 30.0:
                pct_vend_spot = int(round(frazione_spot * 100.0))
                nota_pac_prot = f" — solo quota Spot ({q_spot_p:.2f} az.), quota PAC intoccata" if q_pac_p > 1e-6 else ""
                nota_delta = f", Hold-Score {hold_score}/100, Delta +{delta_q} pt" if delta_q is not None else f", Hold-Score {hold_score}/100"
                candidati_ris.append({
                    "priorita": 2,
                    "fonte": "Fonte B (Rotazione Qualitativa Spot)",
                    "ticker": tk,
                    "pct_vendita": pct_vend_spot,
                    "pnl_pct": round(pnl_pct, 1),
                    "hold_score": hold_score,
                    "delta_qualita": delta_q,
                    "lordo_eur": round(v_lordo, 2),
                    "tasse_eur": round(tasse_26, 2),
                    "netto_eur": netto_disp,
                    "motivo": f"fermo da {gg_det} gg ({pnl_pct:+.1f}%{nota_delta}){nota_pac_prot}",
                })

    if not candidati_ris:
        return None
    candidati_ris.sort(key=lambda x: (x["priorita"], x["hold_score"], -x["netto_eur"]))
    return candidati_ris[0]

def _valuta_titoli_priorita_home(
    priorita_str,
    portafoglio,
    salute_map,
    val_totale_port,
    eurusd_rate,
    spy_stato,
    qqq_stato,
    pattern_alerts,
    radar_rows,
    palantir_cands,
    liq_libera,
):
    """
    Valuta esplicitamente i ticker inseriti dall'utente nel campo '📌 Titoli da Acquistare (Priorità)'
    usando lo stesso motore Super-Score, i 3 Scudi Anti-Trappola, il Cooldown 21gg e il Piano A/B.
    """
    tks = [x.strip().upper() for x in str(priorita_str or "").replace("\n", ",").split(",") if x.strip()]
    if not tks:
        return []
    cooldown_map = _get_tickers_cooldown_vendite(21)
    peso_port = {}
    if val_totale_port > 0:
        for pos in (portafoglio or []):
            tk_p = str(pos.get("Ticker", "")).strip().upper()
            if tk_p:
                q_p = float(pos.get("Quantita", 0) or 0)
                att_p = float(pos.get("Prezzo_Attuale_EUR") or pos.get("Prezzo_Medio") or 0)
                peso_port[tk_p] = ((q_p * att_p) / val_totale_port) * 100.0

    buy_map = {str(a.get("ticker", "")).strip().upper(): a for a in ((pattern_alerts or {}).get("buy_nuovo") or []) if isinstance(a, dict) and a.get("ticker")}
    ig_map = {str(r.get("Ticker", "")).strip().upper(): r for r in (radar_rows or []) if isinstance(r, dict) and r.get("Ticker") and "ATTIVO" in str(r.get("Stato", "")).upper()}
    pal_map = {str(r.get("Ticker", "")).strip().upper(): r for r in (palantir_cands or []) if isinstance(r, dict) and r.get("Ticker")}
    metriche_scan = (st.session_state.get("dashboard_stats") or {}).get("metriche_scan") or {}
    regime_rosso = (str(spy_stato).lower() == "rosso" or str(qqq_stato).lower() == "rosso")

    esiti = []
    for tk in list(dict.fromkeys(tks))[:5]:
        # 1) Controllo Cooldown 21 giorni
        if tk in cooldown_map:
            gg_fa = cooldown_map[tk]
            esiti.append({
                "ticker": tk, "pronto": False, "stato": "COOLDOWN",
                "testo": f"🚫 <b>{tk}</b>: venduto {gg_fa} gg fa — bloccato dal Cooldown Anti Ping-Pong (21 gg).",
            })
            continue
        # 2) Scudo 3 Concentrazione
        if peso_port.get(tk, 0.0) > 22.0:
            esiti.append({
                "ticker": tk, "pronto": False, "stato": "CONCENTRAZIONE",
                "testo": f"🛡️ <b>{tk}</b>: già oltre il 22% del portafoglio ({peso_port[tk]:.1f}%) — Scudo Concentrazione attivo.",
            })
            continue
        # 3) Scudo 2 Trimestrali <= 10gg
        gg_ut = (metriche_scan.get(tk) or {}).get("Giorni_Utili")
        if gg_ut is not None and 0 <= int(gg_ut) <= 10:
            esiti.append({
                "ticker": tk, "pronto": False, "stato": "UTILI",
                "testo": f"⏳ <b>{tk}</b>: trimestrale tra {int(gg_ut)} giorni — attendi dopo gli utili (Scudo 2).",
            })
            continue

        info_tk = _get_info_cached(tk)
        s_sc = int((metriche_scan.get(tk) or {}).get("S_Score") or calcola_s_score(info_tk) or 50)
        tn_tk = _valuta_fondamentali_tom_nash(info_tk, s_score=s_sc)
        df_tk = _get_single_ohlc_cached(tk, period="1y")
        fase_tk = rileva_fase_weinstein(df_tk) if (df_tk is not None and len(df_tk) >= 50) else "N/D"
        p_nat = float(df_tk["Close"].dropna().iloc[-1]) if (df_tk is not None and not df_tk.empty) else 0.0
        cur_tk = str((info_tk or {}).get("currency", "USD") or "USD").upper()
        p_eur = round(p_nat / eurusd_rate if cur_tk == "USD" else p_nat, 2) if p_nat > 0 else 0.0
        simb = "$" if cur_tk == "USD" else "€"

        # 4) Scudo 1 Regime Rosso
        if regime_rosso:
            esiti.append({
                "ticker": tk, "pronto": False, "stato": "REGIME_ROSSO",
                "testo": f"🛡️ <b>{tk}</b> (S-Score {s_sc}/100, {fase_tk}): <b>attendi</b> — regime mercato SPY/QQQ ROSSO (Scudo 1 blocca nuovi breakout).",
            })
            continue

        # 5) Verifica segnale attivo nei motori (Breakout Matrix confermato / IGNITION / Palantir)
        al = buy_map.get(tk)
        motori = []
        base_sc = 0.0
        max_ent, stop_p, targ_p, rr_v = 0.0, 0.0, 0.0, 0.0
        motivo_attesa = ""
        if al:
            stato_tr = str(al.get("stato_trigger", "")).upper()
            dist_y = float(al.get("dist_y_pct", -999.0) or -999.0)
            trig_y = float(al.get("trigger_y") or 0.0)
            if "PRE-BREAKOUT" in stato_tr or dist_y < 0.0:
                motivo_attesa = f"Pre-Breakout sotto Trigger Y ({simb}{trig_y:.2f}, distanza {dist_y:+.1f}%) — attendi rottura confermata."
            elif dist_y > 3.5:
                motivo_attesa = f"già esteso oltre +3.5% dal Trigger Y ({simb}{trig_y:.2f}, +{dist_y:.1f}%) — non inseguire, attendi pullback."
            else:
                motori.append("Breakout Matrix")
                base_sc = max(base_sc, min(74.0, float(al.get("confidenza") or 75.0) * 0.74))
                max_ent = round(trig_y * 1.035, 2)
                stop_p = float(al.get("stop_price") or round(p_nat * 0.92, 2))
                targ_p = float(al.get("target_price") or round(p_nat * 1.20, 2))
                rr_v = float(al.get("rr") or 2.0)
        if tk in ig_map:
            motori.append("Radar IGNITION")
            base_sc = max(base_sc, 58.0)
        if tk in pal_map:
            motori.append("Setup Palantir AI")
            base_sc = max(base_sc, 62.0)

        if not motori:
            if not motivo_attesa:
                motivo_attesa = f"nessun breakout o segnale IGNITION/Palantir confermato oggi ({fase_tk}, S-Score {s_sc}/100) — attendi il setup."
            esiti.append({
                "ticker": tk, "pronto": False, "stato": "ATTENDI",
                "testo": f"⏳ <b>{tk}</b>: {motivo_attesa}",
            })
            continue

        # Calcolo Super-Score sintetico
        sc_tot = base_sc + (15.0 if len(motori) >= 2 else 0.0) + (8.0 if s_sc >= 75 else (4.0 if s_sc >= 65 else 0.0)) + float(tn_tk.get("bonus_multipli") or 0)
        super_sc = int(max(0, min(100, round(sc_tot))))
        if max_ent <= 0 and p_nat > 0:
            max_ent = round(p_nat * 1.035, 2)
            stop_p = round(p_nat * 0.92, 2)
            targ_p = round(p_nat * 1.22, 2)
            rr_v = 2.2

        # Piano A (cassa sufficiente) vs Piano B (Switch Qualitativo vs Portafoglio Intatto)
        if liq_libera >= 40.0:
            imp_a = round(min(liq_libera, 500.0), 2)
            piano_txt = f"<b>Piano A (Cassa):</b> acquista € {imp_a:,.2f} (max {simb}{max_ent:.2f}, Stop {simb}{stop_p:.2f}, Target {simb}{targ_p:.2f})."
        else:
            ris_p = _trova_riserva_liquidita_intelligente(portafoglio, salute_map, target_score=super_sc, modalita="BUY", liq_libera=liq_libera)
            if ris_p:
                piano_txt = (
                    f"<b>Piano B (Switch Qualitativo):</b> libera {ris_p['pct_vendita']}% di <b>{ris_p['ticker']}</b> "
                    f"(~€ {ris_p['netto_eur']:,.2f} netti, {ris_p['motivo']}) e acquista <b>{tk}</b> (max {simb}{max_ent:.2f})."
                )
            else:
                imp_sug = max(150.0, round(p_eur, 2) if p_eur >= 50 else 200.0)
                piano_txt = (
                    f"<b>Piano B (Portafoglio Intatto):</b> nessun titolo da vendere (tutti solidi o in PAC) — "
                    f"se vuoi cogliere <b>{tk}</b>, versa ~<b>€ {imp_sug:,.0f}</b> di nuova liquidità dedicata su Trade Republic."
                )
        esiti.append({
            "ticker": tk, "pronto": True, "stato": "PRONTO", "super_score": super_sc,
            "testo": f"🚀 <b>{tk} PRONTO</b> ({' + '.join(motori)} • Super-Score {super_sc}/100 • S-Score {s_sc}/100): {piano_txt}",
        })
    return esiti

def _calcola_top1_super_automatismo(
    portafoglio,
    val_totale_port,
    eurusd_rate,
    spy_stato,
    qqq_stato,
    pattern_alerts,
    radar_ignition_rows,
    palantir_candidati,
):
    """
    Motore 'TOP 1 UNICO': unisce i candidati confermati di Breakout Matrix TOP 3 (sopra Trigger Y entro +3.5%,
    MAI Pre-Breakout), Radar IGNITION 80 attivi e Setup Palantir AI, applica i 3 Scudi Anti-Trappola
    (Regime SPY/QQQ ROSSO, Trimestrali <= 10gg, Concentrazione > 22%) e calcola il Super-Score Unificato (0-100).
    Restituisce (best_candidate_dict | None, motivo_veto_str | None).
    """
    # Scudo 1 — Veto Regime: con SPY o QQQ in regime ROSSO nessun nuovo BUY breakout
    if str(spy_stato).lower() == "rosso" or str(qqq_stato).lower() == "rosso":
        return None, "Regime mercato difensivo (SPY o QQQ ROSSO): nuovi BUY breakout sospesi automaticamente."

    # Cooldown Anti Ping-Pong (21 giorni): esclude automaticamente titoli venduti di recente
    cooldown_21g = _get_tickers_cooldown_vendite(21)

    # Mappa esposizione attuale per Scudo 3 (Concentrazione > 22%)
    peso_port = {}
    if val_totale_port > 0:
        for pos in (portafoglio or []):
            tk_p = str(pos.get("Ticker", "")).strip().upper()
            if not tk_p:
                continue
            q_p = float(pos.get("Quantita", 0) or 0)
            att_p = float(pos.get("Prezzo_Attuale_EUR") or pos.get("Prezzo_Medio") or 0)
            peso_port[tk_p] = ((q_p * att_p) / val_totale_port) * 100.0

    pool = {}

    # 1) Breakout Matrix TOP 3 (SOLO sopra Trigger Y entro +3.5%, MAI Pre-Breakout)
    buy_nuovo_top3 = ((pattern_alerts or {}).get("buy_nuovo") or [])[:3]
    for al in buy_nuovo_top3:
        if not isinstance(al, dict):
            continue
        tk = str(al.get("ticker", "")).strip().upper()
        if not tk or tk in cooldown_21g:
            continue
        stato_tr = str(al.get("stato_trigger", "")).upper()
        dist_y = float(al.get("dist_y_pct", -999.0) or -999.0)
        if "PRE-BREAKOUT" in stato_tr or not (0.0 <= dist_y <= 3.5):
            continue
        trig_y = float(al.get("trigger_y") or 0.0)
        stop_p = float(al.get("stop_price") or 0.0)
        targ_p = float(al.get("target_price") or 0.0)
        rr_v = float(al.get("rr") or 0.0)
        conf_v = float(al.get("confidenza") or 75.0)
        cur_v = str(al.get("currency", "USD") or "USD").upper()
        fig_v = str(al.get("figura", "Breakout"))
        p_nat = float(al.get("prezzo") or trig_y or 0.0)
        pool[tk] = {
            "ticker": tk,
            "motori": ["Breakout Matrix"],
            "is_breakout_matrix": True,
            "base_score": min(74.0, conf_v * 0.74),
            "trigger_y": trig_y,
            "max_entry": round(trig_y * 1.035, 2),
            "stop_price": stop_p,
            "target_price": targ_p,
            "rr": rr_v,
            "currency": cur_v,
            "prezzo_nat": p_nat,
            "prezzo_eur": round(p_nat / eurusd_rate if cur_v == "USD" else p_nat, 2) if p_nat > 0 else 0.0,
            "orizzonte": "2-4 Mesi" if fig_v in ("Cup & Handle", "Flat Base", "Doppio Minimo (W)") else "3-8 Settimane",
            "figura": fig_v,
        }

    # 2) Radar IGNITION 80 (solo '🚀 IGNITION ATTIVO')
    for row_ig in (radar_ignition_rows or []):
        if not isinstance(row_ig, dict):
            continue
        if "ATTIVO" not in str(row_ig.get("Stato", "")).upper():
            continue
        tk = str(row_ig.get("Ticker", "")).strip().upper()
        if not tk:
            continue
        if tk in pool:
            if "Radar IGNITION" not in pool[tk]["motori"]:
                pool[tk]["motori"].append("Radar IGNITION")
        else:
            p_str = str(row_ig.get("Prezzo $", "0")).replace("$", "").replace("€", "").replace(",", "").strip()
            try:
                p_nat = float(p_str)
            except Exception:
                p_nat = 0.0
            if p_nat <= 0:
                continue
            stop_p = round(p_nat * 0.92, 2)
            targ_p = round(p_nat * 1.20, 2)
            rr_v = round((targ_p - p_nat) / max(0.01, p_nat - stop_p), 2)
            pool[tk] = {
                "ticker": tk,
                "motori": ["Radar IGNITION"],
                "is_breakout_matrix": False,
                "base_score": 56.0,
                "trigger_y": round(p_nat, 2),
                "max_entry": round(p_nat * 1.035, 2),
                "stop_price": stop_p,
                "target_price": targ_p,
                "rr": rr_v,
                "currency": "USD",
                "prezzo_nat": p_nat,
                "prezzo_eur": round(p_nat / eurusd_rate, 2),
                "orizzonte": "3-8 Settimane",
                "figura": "Radar IGNITION (Squeeze/SMA20)",
            }

    # 3) Setup Palantir AI (sola proposta)
    for row_pl in (palantir_candidati or []):
        if not isinstance(row_pl, dict):
            continue
        tk = str(row_pl.get("Ticker", "")).strip().upper()
        if not tk:
            continue
        if tk in pool:
            if "Setup Palantir AI" not in pool[tk]["motori"]:
                pool[tk]["motori"].append("Setup Palantir AI")
        else:
            p_nat = float(row_pl.get("Prezzo Nat") or 0.0)
            cur_v = str(row_pl.get("Currency", "USD") or "USD").upper()
            p_eur = float(row_pl.get("Prezzo EUR") or 0.0)
            if p_nat <= 0 and p_eur > 0:
                p_nat = round(p_eur * eurusd_rate if cur_v == "USD" else p_eur, 2)
            if p_nat <= 0:
                continue
            stop_p = round(p_nat * 0.92, 2)
            targ_p = round(p_nat * 1.22, 2)
            rr_v = round((targ_p - p_nat) / max(0.01, p_nat - stop_p), 2)
            pool[tk] = {
                "ticker": tk,
                "motori": ["Setup Palantir AI"],
                "is_breakout_matrix": False,
                "base_score": 60.0,
                "trigger_y": round(p_nat, 2),
                "max_entry": round(p_nat * 1.035, 2),
                "stop_price": stop_p,
                "target_price": targ_p,
                "rr": rr_v,
                "currency": cur_v,
                "prezzo_nat": p_nat,
                "prezzo_eur": p_eur if p_eur > 0 else round(p_nat / eurusd_rate if cur_v == "USD" else p_nat, 2),
                "orizzonte": "2-4 Mesi",
                "figura": "Setup Palantir AI",
            }

    if not pool:
        return None, None

    # Valuta Scudi 2 & 3 + Cooldown 21gg + calcola Super-Score Unificato (0-100)
    scelti = []
    metriche_scan = (st.session_state.get("dashboard_stats") or {}).get("metriche_scan") or {}
    for tk, cand in pool.items():
        # Cooldown Anti Ping-Pong (21 giorni) anche su IGNITION e Palantir
        if tk in cooldown_21g:
            continue
        # Scudo 3 — Veto Concentrazione (> 22% del portafoglio)
        if peso_port.get(tk, 0.0) > 22.0:
            continue

        # Scudo 2 — Veto Trimestrali (<= 10 giorni)
        gg_ut = (metriche_scan.get(tk) or {}).get("Giorni_Utili")
        if gg_ut is None:
            try:
                gg_ut, _, _ = controlla_earnings(yf.Ticker(tk))
            except Exception:
                gg_ut = None
        if gg_ut is not None and 0 <= int(gg_ut) <= 10:
            continue

        # Arricchimento qualità: S-Score, WinRate 60gg, Stagionalità 10y, Insider SEC Form 4 ("buys")
        s_sc = (metriche_scan.get(tk) or {}).get("S_Score")
        if s_sc is None:
            s_sc = calcola_s_score(_get_info_cached(tk))
        s_sc = int(s_sc or 50)

        df_c = _get_single_ohlc_cached(tk, period="1y")
        wr_60 = _calcola_winrate_storico_60gg(df_c)
        stag_txt = ""
        try:
            _, stag_txt = calcola_stagionalita_10y(tk)
        except Exception:
            stag_txt = ""

        sec_buys = 0
        sec_ins = 0
        try:
            sec_d = get_sec_insider_buys_90gg(tk, max_docs=8)
            if isinstance(sec_d, dict):
                sec_buys = int(sec_d.get("buys") or 0)
                sec_ins = int(sec_d.get("num_insider") or 0)
        except Exception:
            pass

        score = float(cand["base_score"])
        # Bonus confluenza multi-motore (+15 pt)
        if len(cand["motori"]) >= 2:
            score += 15.0
        # Bonus qualità S-Score
        if s_sc >= 75:
            score += 8.0
        elif s_sc >= 65:
            score += 4.0
        elif s_sc < 55:
            score -= 8.0
        # Bonus R/R
        if cand["rr"] >= 2.2:
            score += 6.0
        elif cand["rr"] >= 2.0:
            score += 3.0
        # Bonus/penalità WinRate 60gg
        if wr_60 is not None:
            if wr_60 >= 60.0:
                score += 5.0
            elif wr_60 < 45.0:
                score -= 5.0
        # Bonus/penalità Stagionalità 10 anni
        if stag_txt and str(stag_txt).startswith("+"):
            score += 5.0
        elif stag_txt and str(stag_txt).startswith("-"):
            score -= 5.0
        # Moltiplicatore Insider SEC Form 4 (90gg)
        if sec_ins >= 2 or sec_buys >= 3:
            score += 18.0
        elif sec_buys >= 1:
            score += 10.0
        # Bonus Sconto Multipli Tom Nash (+5 / +8 pt anti-Value Trap su _get_info_cached)
        tn_cand = _valuta_fondamentali_tom_nash(_get_info_cached(tk), s_score=s_sc)
        bonus_mult = int(tn_cand.get("bonus_multipli") or 0)
        if bonus_mult > 0:
            score += float(bonus_mult)

        cand["super_score"] = int(max(0, min(100, round(score))))
        cand["s_score"] = s_sc
        cand["winrate_60g"] = wr_60
        cand["stagionalita"] = stag_txt or "N/D"
        cand["sec_buys"] = sec_buys
        cand["sec_num_insider"] = sec_ins
        cand["bonus_multipli"] = bonus_mult
        cand["badge_multipli"] = str(tn_cand.get("badge_multipli") or "")
        scelti.append(cand)

    if not scelti:
        return None, None

    # Priorità assoluta: Breakout Matrix confermato o punteggio Super-Score più alto, poi R/R
    scelti.sort(key=lambda x: (x["super_score"], 1 if x["is_breakout_matrix"] else 0, x["rr"]), reverse=True)
    return scelti[0], None

def _calcola_dca_doppio_binario(portafoglio, salute_map, pattern_alerts, liq_libera, ignora_soglia_cassa=False, importo_ref_piano_b=200.0):
    """
    DCA Matematico Doppio Binario (esclude ticker in Cooldown Anti Ping-Pong 21 giorni):
    - Binario 1 (Priorità massima — Inversione / Figura Grafica): azienda sana (-5%..-35% dal PMC)
      con BUY MEDIAZIONE in pattern_engine.py oppure riconquista SMA 50/200 in Fase 1/2.
    - Binario 2 (Supporto su ritracciamento): azienda sana (-12%..-35% dal PMC) con stabilizzazione
      (RSI 30-50 e chiusura positiva Close >= PrevClose).
    Con ignora_soglia_cassa=True valuta un candidato DCA Binario 1 di alta qualità anche a cassa 0
    (con importo ipotetico di riferimento) per attivare il Piano B Qualitativo.
    """
    if (not ignora_soglia_cassa and liq_libera < 40.0) or not portafoglio:
        return None

    cooldown_21g = _get_tickers_cooldown_vendite(21)
    med_pat_map = {}
    for al in ((pattern_alerts or {}).get("buy_mediazione") or []):
        if isinstance(al, dict) and al.get("ticker"):
            med_pat_map[str(al["ticker"]).strip().upper()] = al

    candidati_dca = []
    imp_dca = round(min(liq_libera, 500.0), 2) if liq_libera >= 40.0 else round(float(importo_ref_piano_b or 200.0), 2)

    for pos in portafoglio:
        tk = str(pos.get("Ticker", "")).strip().upper()
        if not tk or tk in cooldown_21g:
            continue
        inf = (salute_map or {}).get(tk) or {}
        q_old = float(pos.get("Quantita", 0) or 0)
        pmc_old = float(pos.get("Prezzo_Medio", 0) or 0)
        p_att = float(pos.get("Prezzo_Attuale_EUR") or 0)
        if q_old <= 0 or pmc_old <= 0 or p_att <= 0:
            continue
        pnl_p = ((p_att / pmc_old) - 1.0) * 100.0
        s_sc = int(inf.get("s_score", 50) or 50)
        sec_b = int(inf.get("sec_buys", 0) or 0)
        azienda_sana = (s_sc >= 65) or (sec_b > 0)
        if not azienda_sana:
            continue

        fase_s = str(inf.get("fase", "N/D")).upper()
        sopra_50 = inf.get("sopra_sma50")
        sopra_200 = inf.get("sopra_sma200")
        rsi_v = float(inf.get("rsi", 50.0) or 50.0)
        c_og = inf.get("close_oggi")
        c_ie = inf.get("close_ieri")
        chiusura_pos = (c_og is not None and c_ie is not None and float(c_og) >= float(c_ie))

        binario = None
        motivo_dca = ""
        # Binario 1 (Priorità massima): -5% .. -35% + BUY MEDIAZIONE pattern_engine o riconquista SMA 50/200 in Fase 1/2
        if -35.0 <= pnl_p <= -5.0:
            if tk in med_pat_map:
                binario = 1
                fig_m = med_pat_map[tk].get("figura", "Inversione")
                motivo_dca = f"Binario 1 — Segnale BUY MEDIAZIONE confermato ({fig_m})"
            elif ("FASE 1" in fase_s or "FASE 2" in fase_s) and (sopra_50 is True or sopra_200 is True):
                binario = 1
                liv = "SMA 200" if sopra_200 is True else "SMA 50"
                motivo_dca = f"Binario 1 — Riconquista {liv} in {fase_s}"

        # Binario 2 (Supporto su ritracciamento): -12% .. -35% + stabilizzazione (RSI 30-50 e chiusura positiva)
        if binario is None and (-35.0 <= pnl_p <= -12.0):
            if (30.0 <= rsi_v <= 50.0) and chiusura_pos:
                # Filtro qualità istituzionale sul Binario 2 sotto SMA 200:
                # ammette solo titoli con Market Cap >= $5 Miliardi oppure >= 1 acquisto SEC Form 4 (90gg)
                if sopra_200 is not True:
                    mcap_usd = 0.0
                    try:
                        mcap_usd = float((_get_info_cached(tk) or {}).get("marketCap") or 0.0)
                    except Exception:
                        mcap_usd = 0.0
                    if (mcap_usd < 5_000_000_000.0) and (sec_b < 1):
                        continue
                binario = 2
                motivo_dca = f"Binario 2 — Stabilizzazione su supporto (RSI {rsi_v:.0f} + chiusura positiva)"

        if binario is None:
            continue

        # Impatto matematico esatto (Nuovo PMC e riduzione rimbalzo % per tornare a 0,00%)
        cap_old = q_old * pmc_old
        q_add = imp_dca / p_att
        pmc_new = (cap_old + imp_dca) / (q_old + q_add)
        rimb_prima = ((pmc_old / p_att) - 1.0) * 100.0
        rimb_dopo = ((pmc_new / p_att) - 1.0) * 100.0
        riduzione_rimb = rimb_prima - rimb_dopo

        # Filtro efficacia reale del DCA: scarta proposte marginali (< 6.0 punti % di riduzione)
        # a meno che il nuovo rimbalzo necessario non scenda già sotto +12.0%
        if riduzione_rimb < 6.0 and rimb_dopo >= 12.0:
            continue

        # Bonus Sconto Multipli Tom Nash (anti-Value Trap) per priorità DCA sui campioni fondamentali
        bonus_mult_dca = int(inf.get("bonus_multipli") or 0)
        badge_mult_dca = str(inf.get("badge_multipli") or "")
        if ("bonus_multipli" not in inf):
            tn_dca = _valuta_fondamentali_tom_nash(_get_info_cached(tk), s_score=s_sc)
            bonus_mult_dca = int(tn_dca.get("bonus_multipli") or 0)
            badge_mult_dca = str(tn_dca.get("badge_multipli") or "")

        candidati_dca.append({
            "binario": binario,
            "ticker": tk,
            "pnl_pct": round(pnl_p, 1),
            "s_score": s_sc,
            "sec_buys": sec_b,
            "bonus_multipli": bonus_mult_dca,
            "badge_multipli": badge_mult_dca,
            "motivo": motivo_dca,
            "importo_eur": imp_dca,
            "prezzo_eur": p_att,
            "pmc_old": round(pmc_old, 2),
            "pmc_new": round(pmc_new, 2),
            "rimb_prima": round(rimb_prima, 1),
            "rimb_dopo": round(rimb_dopo, 1),
            "riduzione_rimb": round(riduzione_rimb, 1),
        })

    if not candidati_dca:
        return None
    # Priorità DCA: Binario 1 > Binario 2, poi qualità combinata (S-Score + Bonus Sconto Multipli)
    candidati_dca.sort(key=lambda x: (x["binario"], -(x["s_score"] + int(x.get("bonus_multipli", 0))), x["pnl_pct"]))
    return candidati_dca[0]

# ==============================================================================
# BOX PERIODICO: PUNTO SETTIMANA / FINE MESE & RADAR ROTAZIONE BALENE
# ==============================================================================
ETF_SETTORI_BALENE = {
    "XLK": "Tecnologia & Software",
    "SMH": "Semiconduttori & AI",
    "XLC": "Comunicazione & Media",
    "XLY": "Consumi Discrezionali",
    "XLF": "Finanza & Banche",
    "XLE": "Energia & Petrolio",
    "XLV": "Sanità & Farmaceutica",
    "XLI": "Industria & Difesa",
    "XLU": "Utilities & Energia Elettrica",
    "XLB": "Materie Prime & Metalli",
    "XBI": "Biotecnologie",
}

def _get_now_italia():
    """Restituisce data e ora correnti nel fuso orario italiano (Europe/Rome), anche su Streamlit Cloud UTC."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Rome"))
    except Exception:
        from datetime import timezone
        return datetime.now(timezone(timedelta(hours=1)))

def _verifica_finestra_punto_periodico(now_it=None):
    """
    Determina se siamo nella finestra automatica del box periodico:
    - Fine mese: ultimi 3 giorni di calendario del mese -> modalità 'mensile' (21 sedute)
    - Weekend: venerdì >= 22:00 italiane fino a domenica 23:59 -> modalità 'settimanale' (5 sedute)
    Restituisce (attivo_auto: bool, modalita: 'mensile'|'settimanale', etichetta_finestra: str).
    """
    import calendar
    dt = now_it or _get_now_italia()
    ultimo_gg = calendar.monthrange(dt.year, dt.month)[1]
    is_fine_mese = (ultimo_gg - dt.day) <= 2
    is_weekend = (dt.weekday() == 4 and dt.hour >= 22) or (dt.weekday() in (5, 6))
    if is_fine_mese:
        return True, "mensile", "Bilancio di Fine Mese (ultimi 21 giorni di borsa)"
    if is_weekend:
        return True, "settimanale", "Riepilogo del Fine Settimana (ultimi 5 giorni di borsa)"
    return False, "settimanale", "Anteprima manuale (attivo automaticamente nel weekend e negli ultimi 3 giorni del mese)"

@st.cache_data(ttl=3600, show_spinner=False)
def _scarica_etf_punto_periodico_cached():
    """
    Scarica in un unico mini-batch (cache 1 ora) SPY, QQQ e gli 11 ETF settoriali USA
    calcolando rendimenti 5gg/21gg, posizione rispetto a SMA 50 e rapporto volumi 10gg/40gg.
    """
    simboli = ["SPY", "QQQ"] + list(ETF_SETTORI_BALENE.keys())
    out = {}
    try:
        raw = yf.download(
            simboli,
            period="4mo",
            interval="1d",
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=True,
        )
        if raw is None or raw.empty:
            return out
        for sym in simboli:
            try:
                sub = raw[sym].dropna(subset=["Close"]).copy() if isinstance(raw.columns, pd.MultiIndex) else raw.dropna(subset=["Close"]).copy()
                if sub.empty or len(sub) < 6:
                    continue
                closes = sub["Close"].dropna()
                vols = sub["Volume"].dropna() if "Volume" in sub.columns else pd.Series(dtype=float)
                p_now = float(closes.iloc[-1])
                p_5 = float(closes.iloc[-6]) if len(closes) >= 6 else float(closes.iloc[0])
                p_21 = float(closes.iloc[-22]) if len(closes) >= 22 else float(closes.iloc[0])
                pct_5 = round(((p_now / p_5) - 1.0) * 100.0, 2) if p_5 > 0 else 0.0
                pct_21 = round(((p_now / p_21) - 1.0) * 100.0, 2) if p_21 > 0 else 0.0
                sma50 = float(closes.rolling(50).mean().iloc[-1]) if len(closes) >= 50 else None
                sopra_sma50 = bool(p_now > sma50) if (sma50 is not None and pd.notna(sma50) and sma50 > 0) else False
                vol_ratio_10_40 = 1.0
                if len(vols) >= 40:
                    v10 = float(vols.tail(10).mean())
                    v40 = float(vols.tail(40).mean())
                    vol_ratio_10_40 = round(v10 / v40, 2) if v40 > 0 else 1.0
                out[sym] = {
                    "prezzo": round(p_now, 2),
                    "pct_5g": pct_5,
                    "pct_21g": pct_21,
                    "sma50": round(sma50, 2) if (sma50 is not None and pd.notna(sma50)) else None,
                    "sopra_sma50": sopra_sma50,
                    "vol_ratio_10_40": vol_ratio_10_40,
                }
            except Exception:
                continue
    except Exception:
        pass
    return out

def _mappa_titolo_etf_settoriale(ticker):
    """
    Mappatura ibrida a 2 livelli (industry fine + sector GICS) tramite _get_info_cached
    senza chiamate di rete extra. Restituisce il codice ETF tra gli 11 di ETF_SETTORI_BALENE.
    """
    tk = str(ticker or "").strip().upper()
    info = _get_info_cached(tk) if tk else {}
    ind = str((info or {}).get("industry") or "").lower()
    sec = str((info or {}).get("sector") or "").lower()

    # Livello 1: industry specifica (distingue Semiconduttori/AI e Biotech dal settore generico)
    if "semiconductor" in ind or tk in ("NVDA", "AMD", "AVGO", "TSM", "ASML", "ARM", "MU", "MRVL", "LRCX", "SMCI", "APLD", "IREN", "CRDO"):
        return "SMH"
    if "biotech" in ind:
        return "XBI"
    if "aerospace" in ind or "defense" in ind:
        return "XLI"
    if "oil" in ind or "gas" in ind or "drilling" in ind or "refining" in ind:
        return "XLE"

    # Livello 2: fallback automatico sul sector GICS di Yahoo Finance
    if "technology" in sec:
        return "XLK"
    if "communication" in sec:
        return "XLC"
    if "consumer cyclical" in sec or "consumer discretionary" in sec or "consumer defensive" in sec:
        return "XLY"
    if "financial" in sec:
        return "XLF"
    if "energy" in sec:
        return "XLE"
    if "health" in sec:
        return "XLV"
    if "industrial" in sec:
        return "XLI"
    if "utilit" in sec:
        return "XLU"
    if "basic material" in sec or "material" in sec:
        return "XLB"
    return "XLK"

def _render_box_punto_periodico_home(portafoglio):
    """
    Renderizza nella Home Page il box ad alto contrasto (testo bianco su card scura):
    '📅 Il Punto della Settimana / Fine Mese (Borsa, Tuoi Settori & Rotazione Balene)'.
    - Automaticamente aperto nel weekend (ven >= 22:00 italiane -> dom) e negli ultimi 3 giorni del mese.
    - Nei giorni feriali appare chiuso in una tendina discreta con caricamento on-demand (0 ms se non aperta).
    """
    attivo_auto, mod_default, etichetta_fin = _verifica_finestra_punto_periodico()

    if not attivo_auto:
        with st.expander("🗓️ Anteprima: Il Punto della Settimana / Fine Mese & Radar Rotazione Balene (auto nel weekend e fine mese)", expanded=False):
            if not st.session_state.get("home_anteprima_punto_attiva", False):
                st.caption("Nei giorni feriali questo riquadro resta spento per mantenere la Home istantanea. Puoi caricarlo su richiesta per testarlo subito.")
                if st.button("🔎 Carica anteprima ora", key="btn_carica_anteprima_punto", use_container_width=True):
                    st.session_state["home_anteprima_punto_attiva"] = True
                    st.rerun()
                return
            c_sw1, c_sw2 = st.columns([2.2, 1.0])
            with c_sw1:
                mod_scelta = st.radio(
                    "Orizzonte anteprima:",
                    ["Settimana (5gg)", "Fine Mese (21gg)"],
                    horizontal=True,
                    label_visibility="collapsed",
                    key="radio_anteprima_punto_mod",
                )
            with c_sw2:
                if st.button("✖️ Chiudi anteprima", key="btn_chiudi_anteprima_punto", use_container_width=True):
                    st.session_state["home_anteprima_punto_attiva"] = False
                    st.rerun()
            modalita = "mensile" if "21gg" in mod_scelta else "settimanale"
            _disegna_card_punto_periodico(portafoglio, modalita, etichetta_fin)
        return

    # Finestra attiva (Weekend o Ultimi 3 giorni del mese): mostra direttamente il box aperto
    _disegna_card_punto_periodico(portafoglio, mod_default, etichetta_fin)

def _disegna_card_punto_periodico(portafoglio, modalita, etichetta_fin):
    """Costruisce e renderizza la card HTML ad alto contrasto con le 3 righe del Punto Periodico."""
    dati_etf = _scarica_etf_punto_periodico_cached()
    if not dati_etf or "SPY" not in dati_etf:
        return

    is_mensile = (modalita == "mensile")
    chiave_pct = "pct_21g" if is_mensile else "pct_5g"
    periodo_txt = "nell'ultimo mese (21 sedute)" if is_mensile else "nell'ultima settimana (5 sedute)"
    titolo_box = (
        "📅 Il Punto di Fine Mese (Borsa, Tuoi Settori & Rotazione Balene)"
        if is_mensile
        else "📅 Il Punto della Settimana (Borsa, Tuoi Settori & Rotazione Balene)"
    )

    # 1) CLIMA GENERALE BORSA USA (SPY e QQQ)
    spy_pct = float(dati_etf.get("SPY", {}).get(chiave_pct, 0.0))
    qqq_pct = float(dati_etf.get("QQQ", {}).get(chiave_pct, 0.0))
    col_spy = "#4ADE80" if spy_pct >= 0 else "#F87171"
    col_qqq = "#4ADE80" if qqq_pct >= 0 else "#F87171"

    if spy_pct >= 1.5 and qqq_pct >= 1.5:
        frase_clima = "Clima decisamente positivo: la borsa americana ha corso bene e la fiducia degli investitori è alta."
    elif spy_pct >= 0.0 and qqq_pct >= 0.0:
        frase_clima = "Clima sereno e costruttivo: la borsa americana avanza con calma e senza strappi."
    elif spy_pct <= -2.0 or qqq_pct <= -3.0:
        frase_clima = "Settimana/mese di pausa e vendite diffuse: è una normale fase di respiro della borsa, resta tranquillo e non farti prendere dalla fretta."
    else:
        frase_clima = "Mercato laterale e prudente: pochi movimenti netti sugli indici, fase ideale per avere pazienza."

    riga_clima = (
        f"🌍 <b>CLIMA GENERALE BORSA USA:</b> {periodo_txt} l'indice generale <b>S&amp;P 500 (SPY)</b> ha fatto "
        f"<b style='color:{col_spy};'>{spy_pct:+.1f}%</b> e il tecnologico <b>Nasdaq (QQQ)</b> "
        f"<b style='color:{col_qqq};'>{qqq_pct:+.1f}%</b>. {frase_clima}"
    )

    # 2) I TUOI SETTORI (mappatura automatica dei titoli del portafoglio utente)
    settori_utente = {}
    for pos in (portafoglio or []):
        tk = str(pos.get("Ticker", "")).strip().upper()
        if not tk:
            continue
        etf_cod = _mappa_titolo_etf_settoriale(tk)
        settori_utente.setdefault(etf_cod, []).append(tk)

    if not settori_utente:
        riga_settori = (
            "🧩 <b>I TUOI SETTORI:</b> Al momento non hai titoli in portafoglio; appena inizierai a investire, "
            "qui vedrai come si muovono i tuoi settori rispetto al resto della borsa."
        )
    else:
        ordinati_u = sorted(settori_utente.items(), key=lambda x: len(x[1]), reverse=True)
        pezzi_s = []
        settori_in_calo = []
        settori_forti = []
        for etf_c, tks_u in ordinati_u[:3]:
            nome_s = ETF_SETTORI_BALENE.get(etf_c, etf_c)
            p_s = float(dati_etf.get(etf_c, {}).get(chiave_pct, 0.0))
            c_s = "#4ADE80" if p_s >= 0 else "#F87171"
            tks_lbl = ", ".join(tks_u[:4]) + ("..." if len(tks_u) > 4 else "")
            pezzi_s.append(f"<b>{nome_s} ({etf_c})</b> <b style='color:{c_s};'>{p_s:+.1f}%</b> <span style='color:#CBD5E1;'>[{tks_lbl}]</span>")
            if p_s < -1.0:
                settori_in_calo.append(nome_s)
            elif p_s >= spy_pct + 0.5:
                settori_forti.append(nome_s)

        if settori_in_calo:
            nota_rassicura = (
                f"Se vedi qualche oscillazione in rosso su questi titoli, dipende soprattutto dal calo dell'intero comparto "
                f"<b>{', '.join(settori_in_calo)}</b> e non da un problema della singola azienda."
            )
        elif settori_forti:
            nota_rassicura = (
                f"Ottimo posizionamento: i tuoi settori principali (<b>{', '.join(settori_forti)}</b>) stanno andando meglio della media di mercato."
            )
        else:
            nota_rassicura = "I tuoi settori si stanno muovendo in linea con l'andamento generale della borsa americana."

        riga_settori = (
            f"🧩 <b>I TUOI SETTORI:</b> {' • '.join(pezzi_s)}.<br>"
            f"<span style='color:#E2E8F0;'>{nota_rassicura}</span>"
        )

    # 3) 🐋 RADAR ROTAZIONE BALENE (11 ETF su 21gg vs SPY + filtri Prezzo > SMA 50 e Volumi 10gg >= 1.00x media 40gg)
    spy_21 = float(dati_etf.get("SPY", {}).get("pct_21g", 0.0))
    classifica_balene = []
    for etf_c, nome_s in ETF_SETTORI_BALENE.items():
        d_e = dati_etf.get(etf_c)
        if not d_e:
            continue
        r21 = float(d_e.get("pct_21g", 0.0))
        rel_vs_spy = round(r21 - spy_21, 1)
        classifica_balene.append({
            "etf": etf_c,
            "nome": nome_s,
            "pct_21g": r21,
            "rel_vs_spy": rel_vs_spy,
            "sopra_sma50": bool(d_e.get("sopra_sma50", False)),
            "vol_ratio": float(d_e.get("vol_ratio_10_40", 1.0)),
            "in_portafoglio": etf_c in settori_utente,
        })

    # Filtra i settori davvero guidati dalle balene: positivo, >= SPY + 3%, Prezzo > SMA 50, Volumi 10gg >= 1.00x media 40gg
    balene_valide = [
        b for b in classifica_balene
        if b["pct_21g"] > 0.0 and b["rel_vs_spy"] >= 3.0 and b["sopra_sma50"] and b["vol_ratio"] >= 1.00
    ]
    balene_valide.sort(key=lambda x: (x["rel_vs_spy"], x["pct_21g"]), reverse=True)

    leader_balena = balene_valide[0] if balene_valide else None
    if leader_balena and not leader_balena["in_portafoglio"]:
        riga_balene = (
            f"<div style='margin-top:8px; padding:0.70rem 0.90rem; background:#0B0E11; "
            f"border:1px solid #38BDF8; border-radius:8px; color:#F8FAFC; font-size:0.93rem; line-height:1.55;'>"
            f"🐋 <b>ROTAZIONE BALENE:</b> I grandi fondi stanno spostando capitali verso "
            f"<b style='color:#4ADE80;'>{leader_balena['nome']} ({leader_balena['etf']})</b> "
            f"(<b>{leader_balena['rel_vs_spy']:+.1f}%</b> nell'ultimo mese vs S&amp;P 500; rendimento 21gg: "
            f"<b>{leader_balena['pct_21g']:+.1f}%</b>, sopra SMA 50 con volumi {leader_balena['vol_ratio']:.2f}x). "
            f"Valuta con Gemini e l'Agente 3-4 leader di questo settore da inserire in Watchlist!</div>"
        )
    elif leader_balena and leader_balena["in_portafoglio"]:
        riga_balene = (
            f"🐋 <b>RADAR ROTAZIONE BALENE:</b> Il settore più forte dell'ultimo mese è "
            f"<b>{leader_balena['nome']} ({leader_balena['etf']})</b> ({leader_balena['rel_vs_spy']:+.1f}% vs S&amp;P 500) "
            f"ed è <b>già presente nel tuo portafoglio</b>: sei già nel flusso giusto dei grandi capitali."
        )
    else:
        riga_balene = (
            "🐋 <b>RADAR ROTAZIONE BALENE:</b> Nessuna rotazione di grandi capitali verso nuovi settori scoperti nell'ultimo mese "
            "(nessun settore supera S&amp;P 500 di almeno +3% con trend sano sopra SMA 50 e volumi in ingresso)."
        )

    # 4) Riga sintetica Bilancio Flussi del Mese (solo nella modalità Fine Mese)
    riga_flussi_html = ""
    if is_mensile:
        try:
            bil_m = _calcola_bilancio_mensile_flussi()
            ym_corr = _now_italia().strftime("%Y-%m")
            m_cor = next((x for x in bil_m if x["ym"] == ym_corr), bil_m[0] if bil_m else None)
            if m_cor:
                tks_v_str = ", ".join(m_cor["titoli_venduti"]) if m_cor["titoli_venduti"] else "nessuna"
                tks_a_str = ", ".join(m_cor["titoli_acquistati"]) if m_cor["titoli_acquistati"] else "nessuno"
                riga_flussi_html = (
                    f"<div style='color:#E0F2FE; font-size:0.90rem; line-height:1.55; margin-top:0.65rem; "
                    f"padding-top:0.60rem; border-top:1px solid #1E293B;'>"
                    f"💶 <b>FLUSSI CAPITALE ({m_cor['label']}):</b> "
                    f"Vendite nette <b>€ {m_cor['vendite_nette_eur']:,.2f}</b> ({tks_v_str}) • "
                    f"Nuova liquidità versata <b>€ {m_cor['nuova_liq_tot_eur']:,.2f}</b> "
                    f"(PAC € {m_cor['nuova_liq_pac_eur']:,.2f} / Spot € {m_cor['nuova_liq_spot_eur']:,.2f}) • "
                    f"Reinvestito da cassa <b>€ {m_cor['reinvestito_cassa_eur']:,.2f}</b> [{tks_a_str}].</div>"
                )
        except Exception:
            riga_flussi_html = ""

    # 0) TERMOMETRO MACRO TOM NASH (SPY Drawdown 52 settimane) in cima al Box Periodico
    riga_macro_tn_html = ""
    try:
        _sem_box = st.session_state.get("semaforo_mercato")
        if not isinstance(_sem_box, dict) or _sem_box.get("spy_drawdown_pct") is None:
            _sem_box = semaforo_header if ("semaforo_header" in globals() and isinstance(semaforo_header, dict) and semaforo_header.get("spy_drawdown_pct") is not None) else calcola_semaforo_mercato()
        _dd_box = _sem_box.get("spy_drawdown_pct") if isinstance(_sem_box, dict) else None
        _zona_box = str((_sem_box or {}).get("zona_sconto_tom_nash") or "normale").lower()
        if _dd_box is not None:
            _dd_it = f"{float(_dd_box):.1f}%".replace(".", ",")
            if _zona_box == "sconto":
                _bg_m, _brd_m, _fg_m = "#0F2436", "#38BDF8", "#E0F2FE"
                _txt_m = (
                    f"📉 <b>Contesto Macro SPY ({_dd_it} dai massimi 52w):</b> "
                    f"Modalità Sconto Istituzionale attiva — vietate vendite nel panico e priorità al DCA mirato sui campioni fondamentali."
                )
            elif _zona_box == "bear":
                _bg_m, _brd_m, _fg_m = "#2B1418", "#F59E0B", "#FEF3C7"
                _txt_m = (
                    f"🛡️ <b>Contesto Macro SPY ({_dd_it} dai massimi 52w):</b> "
                    f"Prudenza Bear Market — vietato svendere aziende sane nel panico, procedi solo con piccoli accumuli scaglionati."
                )
            else:
                _bg_m, _brd_m, _fg_m = "#0B0E11", "#334155", "#E2E8F0"
                _txt_m = (
                    f"📊 <b>Contesto Macro SPY ({_dd_it} dai massimi 52w):</b> "
                    f"Mercato vicino ai massimi (nessuna fascia sconto -8%/-10% attiva — operatività ordinaria con 3 Scudi attivi)."
                )
            riga_macro_tn_html = (
                f"<div style='background:{_bg_m}; border:1px solid {_brd_m}; border-left:4px solid {_brd_m}; "
                f"border-radius:8px; padding:0.55rem 0.85rem; margin-bottom:0.70rem; color:{_fg_m}; "
                f"font-size:0.91rem; line-height:1.5;'>{_txt_m}</div>"
            )
    except Exception:
        riga_macro_tn_html = ""

    # Costruzione HTML priva di indentazioni >= 4 spazi per rendering garantito su Markdown Streamlit
    _card_periodo_html = "".join([
        "<div style='background:#131722; border:1px solid #334155; border-left:5px solid #38BDF8; border-radius:12px; padding:1.25rem 1.45rem; margin-bottom:1.1rem;'>",
        f"<div style='font-size:1.14rem; font-weight:800; color:#F8FAFC; margin-bottom:0.20rem;'>{titolo_box}</div>",
        f"<div style='font-size:0.78rem; color:#CBD5E1; margin-bottom:0.85rem;'>{etichetta_fin}</div>",
        riga_macro_tn_html,
        f"<div style='color:#F8FAFC; font-size:0.93rem; line-height:1.58; margin-bottom:0.65rem;'>{riga_clima}</div>",
        f"<div style='color:#F8FAFC; font-size:0.93rem; line-height:1.58; margin-bottom:0.65rem;'>{riga_settori}</div>",
        f"<div style='color:#F8FAFC; font-size:0.93rem; line-height:1.58;'>{riga_balene}</div>",
        riga_flussi_html,
        "</div>",
    ])
    st.markdown(_card_periodo_html, unsafe_allow_html=True)

    # Pulsante manuale per testare/inviare su richiesta il Report Settimanale (Figure & Inversioni) su Telegram
    try:
        _chiave_u_btn = PROFILO_ATTIVO.get("chiave", "fabio")
        if st.button(
            "📨 Invia ora Report Settimanale su Telegram",
            key=f"btn_invia_report_sabato_tg_{modalita}",
            use_container_width=True,
            help="Analizza Portafoglio + Watchlist (figure di inversione, breakout e riconquiste SMA 50/200) e invia il riepilogo al tuo Telegram.",
        ):
            _imp_btn = carica_json(IMPOSTAZIONI_FILE, default={}) if "carica_json" in globals() else {}
            _wl_btn = str((_imp_btn if isinstance(_imp_btn, dict) else {}).get("lista_ticker_default") or "")
            _wl_l_b = [t.strip().upper() for t in _wl_btn.replace("\n", ",").split(",") if t.strip()]
            _pt_l_b = [str(p.get("Ticker", "")).strip().upper() for p in (portafoglio or []) if p.get("Ticker")]
            _tks_b = tuple(sorted(list(set(_wl_l_b + _pt_l_b))))
            _hub_b = _scarica_ohlc_batch_cached(_tks_b, period="1y") if _tks_b else {}
            _pat_b = st.session_state.get("pattern_alerts") or {}
            _sem_b = st.session_state.get("semaforo_mercato")
            _ok_tg, _msg_tg = _invia_report_settimanale_sabato_telegram(
                chiave_u=_chiave_u_btn,
                portafoglio=portafoglio,
                watchlist_str=_wl_btn,
                hub_ohlc=_hub_b,
                pattern_alerts=_pat_b,
                semaforo_loc=_sem_b,
                forza_invio=True,
            )
            if _ok_tg:
                st.toast(f"✅ {_msg_tg}", icon="📨")
                st.success(f"📨 {_msg_tg}")
            else:
                st.warning(f"⚠️ {_msg_tg}")
    except Exception:
        pass


def _rileva_inversioni_extra_settimanali(ticker, df_ohlc):
    """
    Micro-detector di sola lettura su hub_ohlc (senza modificare pattern_engine.py):
    1) Testa e Spalle Rovesciato (usando pattern_engine.trova_pivot già pubblico)
    2) Riconquista SMA 200 o SMA 50 negli ultimi 5 giorni di borsa con volumi >= 1.2x media 20gg.
    Restituisce lista di dizionari {ticker, figura, dettaglio, priorita}.
    """
    risultati = []
    try:
        if df_ohlc is None or df_ohlc.empty or len(df_ohlc) < 60:
            return risultati
        df = df_ohlc.dropna(subset=["Open", "High", "Low", "Close"]).copy()
        if len(df) < 60:
            return risultati
        closes = df["Close"].astype(float)
        opens = df["Open"].astype(float)
        vols = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series(0.0, index=df.index)
        p_now = float(closes.iloc[-1])
        if p_now <= 0:
            return risultati

        # 1) Riconquista SMA 200 / SMA 50 negli ultimi 5 giorni di borsa con volumi >= 1.2x media 20gg
        vol_med_20 = vols.rolling(20).mean()
        if len(df) >= 205:
            sma200 = closes.rolling(200).mean()
            s200_now = float(sma200.iloc[-1])
            s200_5 = sma200.iloc[-6:-1]
            c_5 = closes.iloc[-6:-1]
            era_sotto_200 = bool((c_5 < s200_5).any())
            if pd.notna(s200_now) and s200_now > 0 and p_now > s200_now and era_sotto_200:
                vol_r_max = 0.0
                for k_i in range(-5, 0):
                    vm = float(vol_med_20.iloc[k_i]) if pd.notna(vol_med_20.iloc[k_i]) else 0.0
                    if vm > 0 and float(closes.iloc[k_i]) >= float(opens.iloc[k_i]):
                        vol_r_max = max(vol_r_max, float(vols.iloc[k_i]) / vm)
                if vol_r_max >= 1.20:
                    dist_200 = ((p_now / s200_now) - 1.0) * 100.0
                    risultati.append({
                        "ticker": ticker,
                        "figura": "Riconquista SMA 200 + Volumi",
                        "dettaglio": f"+{dist_200:.1f}% sopra SMA 200 (vol. {vol_r_max:.1f}x)",
                        "priorita": 1,
                    })
        if not risultati and len(df) >= 60:
            sma50 = closes.rolling(50).mean()
            s50_now = float(sma50.iloc[-1])
            s50_5 = sma50.iloc[-6:-1]
            c_5 = closes.iloc[-6:-1]
            era_sotto_50 = bool((c_5 < s50_5).any())
            if pd.notna(s50_now) and s50_now > 0 and p_now > s50_now and era_sotto_50:
                vol_r_max = 0.0
                for k_i in range(-5, 0):
                    vm = float(vol_med_20.iloc[k_i]) if pd.notna(vol_med_20.iloc[k_i]) else 0.0
                    if vm > 0 and float(closes.iloc[k_i]) >= float(opens.iloc[k_i]):
                        vol_r_max = max(vol_r_max, float(vols.iloc[k_i]) / vm)
                if vol_r_max >= 1.20:
                    dist_50 = ((p_now / s50_now) - 1.0) * 100.0
                    risultati.append({
                        "ticker": ticker,
                        "figura": "Riconquista SMA 50 + Volumi",
                        "dettaglio": f"+{dist_50:.1f}% sopra SMA 50 (vol. {vol_r_max:.1f}x)",
                        "priorita": 2,
                    })

        # 2) Testa e Spalle Rovesciato (Inverted H&S) tramite pattern_engine.trova_pivot()
        sub_ihs = df.tail(120).reset_index(drop=True)
        if len(sub_ihs) >= 45 and hasattr(pattern_engine, "trova_pivot"):
            _, piv_lows = pattern_engine.trova_pivot(sub_ihs, ordine=3)
            if len(piv_lows) >= 3:
                (i1, l1), (i2, l2), (i3, l3) = piv_lows[-3], piv_lows[-2], piv_lows[-1]
                # Testa centrale almeno -4% sotto entrambe le spalle e spalle simmetriche entro ±8%
                if l2 > 0 and l1 > 0 and l3 > 0:
                    testa_bassa = (l2 <= l1 * 0.96) and (l2 <= l3 * 0.96)
                    spalle_simm = abs(l1 - l3) / max(l1, l3) <= 0.08
                    spalla_dx_recente = (len(sub_ihs) - 1 - i3) <= 22
                    if testa_bassa and spalle_simm and spalla_dx_recente and i1 < i2 < i3:
                        nk1 = float(sub_ihs["High"].iloc[i1 : i2 + 1].max())
                        nk2 = float(sub_ihs["High"].iloc[i2 : i3 + 1].max())
                        neckline = round(max(nk1, nk2), 2)
                        if neckline > 0 and (neckline * 0.94 <= p_now <= neckline * 1.06):
                            dist_nk = ((p_now / neckline) - 1.0) * 100.0
                            stato_nk = "ROTTURA CONFERMATA" if dist_nk >= 0 else f"a {dist_nk:+.1f}% da neckline"
                            risultati.append({
                                "ticker": ticker,
                                "figura": "Testa e Spalle Rovesciato",
                                "dettaglio": f"Neckline {neckline:.2f} ({stato_nk})",
                                "priorita": 1,
                            })
    except Exception:
        pass
    return risultati


def _costruisci_messaggio_report_sabato(chiave_u, portafoglio, watchlist_tks, hub_ohlc, pattern_alerts, semaforo_loc=None):
    """
    Costruisce un unico messaggio HTML Telegram compatto (< 3.800 caratteri) con le figure
    di inversione e cambiamento trend su Portafoglio e Watchlist per prepararsi al lunedì.
    """
    dt_it = _now_italia()
    sett_iso = dt_it.strftime("%G-W%V")
    nome_u = str(chiave_u or "Utente").strip().capitalize()

    port_set = {str(p.get("Ticker", "")).strip().upper() for p in (portafoglio or []) if p.get("Ticker")}
    wl_only = [tk for tk in dict.fromkeys(watchlist_tks or []) if tk and tk not in port_set]

    # Contesto Macro SPY
    sem = semaforo_loc if isinstance(semaforo_loc, dict) else (st.session_state.get("semaforo_mercato") or {})
    dd_spy = sem.get("spy_drawdown_pct")
    zona_tn = str(sem.get("zona_sconto_tom_nash") or "normale").upper()
    st_spy = str(sem.get("stato") or "giallo").upper()
    if dd_spy is not None:
        dd_s = f"{float(dd_spy):.1f}%".replace(".", ",")
        riga_macro = f"🌍 <b>Clima SPY:</b> {st_spy} (Drawdown 52w: {dd_s} • Fascia {zona_tn})"
    else:
        riga_macro = f"🌍 <b>Clima SPY:</b> {st_spy}"

    righe_port = []
    visti_port = set()
    righe_wl = []
    visti_wl = set()

    # 1) Segnali già rilevati da pattern_engine.py (riuso 100% senza toccare i filtri)
    if isinstance(pattern_alerts, dict):
        # Portafoglio: mediazione / incremento / sell / sorvegliati
        for cat_p, icona_p in (("buy_mediazione", "🟢"), ("buy_incremento", "🚀"), ("sell", "⚠️")):
            for al in (pattern_alerts.get(cat_p) or []):
                if not isinstance(al, dict):
                    continue
                tk = str(al.get("ticker", "")).strip().upper()
                if tk in port_set and (tk, al.get("figura")) not in visti_port:
                    visti_port.add((tk, al.get("figura")))
                    fig_n = str(al.get("figura") or "Pattern")
                    ty = float(al.get("trigger_y") or 0.0)
                    dist_y = float(al.get("dist_y_pct") or 0.0)
                    simb = "$" if str(al.get("currency", "USD")).upper() == "USD" else "€"
                    righe_port.append(f"• {icona_p} <b>{tk}</b>: {fig_n} (Trigger {simb}{ty:.2f}, {dist_y:+.1f}%)")

        # Watchlist: breakout confermati e sorvegliati speciali quasi pronti
        for al in (pattern_alerts.get("buy_nuovo") or [])[:6]:
            if not isinstance(al, dict):
                continue
            tk = str(al.get("ticker", "")).strip().upper()
            if tk and tk not in port_set and tk not in visti_wl:
                visti_wl.add(tk)
                fig_n = str(al.get("figura") or "Breakout")
                ty = float(al.get("trigger_y") or 0.0)
                dist_y = float(al.get("dist_y_pct") or 0.0)
                simb = "$" if str(al.get("currency", "USD")).upper() == "USD" else "€"
                righe_wl.append(f"• 🚀 <b>{tk}</b>: {fig_n} (Trigger {simb}{ty:.2f}, {dist_y:+.1f}%)")
        for sv in (pattern_alerts.get("sorvegliati_speciali") or [])[:6]:
            if not isinstance(sv, dict):
                continue
            tk = str(sv.get("ticker", "")).strip().upper()
            fig_n = str(sv.get("figura") or "Pre-Breakout")
            ty = float(sv.get("trigger_y") or 0.0)
            dist_y = float(sv.get("dist_y_pct") or 0.0)
            simb = "$" if str(sv.get("currency", "USD")).upper() == "USD" else "€"
            if tk in port_set and (tk, fig_n) not in visti_port:
                visti_port.add((tk, fig_n))
                righe_port.append(f"• 👀 <b>{tk}</b>: {fig_n} quasi pronto (Trigger {simb}{ty:.2f}, {dist_y:+.1f}%)")
            elif tk and tk not in port_set and tk not in visti_wl:
                visti_wl.add(tk)
                righe_wl.append(f"• 👀 <b>{tk}</b>: {fig_n} (Trigger {simb}{ty:.2f}, {dist_y:+.1f}%)")

    # 2) Micro-detector extra su hub_ohlc (Testa e Spalle Rovesciato + Riconquista SMA 50/200 + Volumi)
    if isinstance(hub_ohlc, dict):
        for tk_p in sorted(port_set):
            for ex in _rileva_inversioni_extra_settimanali(tk_p, hub_ohlc.get(tk_p)):
                if (tk_p, ex["figura"]) not in visti_port:
                    visti_port.add((tk_p, ex["figura"]))
                    righe_port.append(f"• 🔄 <b>{tk_p}</b>: {ex['figura']} ({ex['dettaglio']})")
        extra_wl = []
        for tk_w in wl_only:
            if tk_w in visti_wl:
                continue
            for ex in _rileva_inversioni_extra_settimanali(tk_w, hub_ohlc.get(tk_w)):
                extra_wl.append(ex)
        extra_wl.sort(key=lambda x: (x["priorita"], x["ticker"]))
        for ex in extra_wl[:8]:
            if ex["ticker"] not in visti_wl:
                visti_wl.add(ex["ticker"])
                righe_wl.append(f"• 🔄 <b>{ex['ticker']}</b>: {ex['figura']} ({ex['dettaglio']})")

    blocco_port = "\n".join(righe_port[:8]) if righe_port else "• Nessuna figura di inversione o rottura rilevata questa settimana sui tuoi titoli."
    blocco_wl = "\n".join(righe_wl[:10]) if righe_wl else "• Nessuna figura di inversione o breakout pronta in Watchlist questa settimana."

    msg = (
        f"📅 <b>REPORT SABATO MATRIX PRO ({sett_iso})</b>\n"
        f"Ciao {nome_u}, ecco la fotografia del fine settimana (mercati chiusi) per prepararti a lunedì:\n"
        f"{riga_macro}\n\n"
        f"💼 <b>SUL TUO PORTAFOGLIO:</b>\n{blocco_port}\n\n"
        f"🔎 <b>WATCHLIST — FIGURE &amp; INVERSIONI:</b>\n{blocco_wl}\n\n"
        f"<i>Analisi automatica MATRIX PRO (Portafoglio + Watchlist).</i>"
    )
    if len(msg) > 3800:
        msg = msg[:3760].rstrip() + "\n…\n<i>Apri MATRIX PRO per i dettagli completi.</i>"
    return msg


def _invia_report_settimanale_sabato_telegram(
    chiave_u,
    portafoglio,
    watchlist_str,
    hub_ohlc,
    pattern_alerts,
    semaforo_loc=None,
    forza_invio=False,
):
    """
    Invia 1 solo Report Settimanale ogni sabato (fuso Europe/Rome) sul Telegram dell'utente attivo
    salvando il flag anti-duplicato 'ultimo_report_sabato_tg': 'YYYY-Www' in impostazioni*.json (sync GitHub).
    Se forza_invio=True consente l'invio immediato su richiesta dal box Weekend.
    """
    try:
        dt_it = _now_italia()
        sett_iso = dt_it.strftime("%G-W%V")
        imp_disk = carica_json(IMPOSTAZIONI_FILE, default={})
        if not isinstance(imp_disk, dict):
            imp_disk = {}

        if not forza_invio:
            # Scatta automaticamente SOLO di sabato (weekday == 5) e 1 sola volta per settimana ISO
            if dt_it.weekday() != 5:
                return False, "Invio automatico attivo solo il sabato."
            if str(imp_disk.get("ultimo_report_sabato_tg") or "") == sett_iso:
                return False, f"Report {sett_iso} già inviato."

        wl_list = [t.strip().upper() for t in str(watchlist_str or "").replace("\n", ",").split(",") if t.strip()]
        msg = _costruisci_messaggio_report_sabato(
            chiave_u=chiave_u,
            portafoglio=portafoglio,
            watchlist_tks=wl_list,
            hub_ohlc=hub_ohlc,
            pattern_alerts=pattern_alerts,
            semaforo_loc=semaforo_loc,
        )
        ok = _invia_notifica_telegram(chiave_u, msg)
        if ok:
            imp_disk["ultimo_report_sabato_tg"] = sett_iso
            salva_json(IMPOSTAZIONI_FILE, imp_disk)
            return True, f"Report Settimanale ({sett_iso}) inviato su Telegram!"
        return False, "Secrets Telegram non configurati per questo utente (o invio non riuscito)."
    except Exception:
        return False, "Invio Report Settimanale non riuscito."

@st.cache_resource
def _get_home_force_counter_store():
    """Archivio in memoria di processo per il contatore di refresh manuale Home di ciascun utente."""
    return {}

class _NoOpProgress:
    """Progress bar fittizia usata dentro @st.cache_data per evitare widget replay/warning."""
    def progress(self, *args, **kwargs):
        return None
    def empty(self):
        return None

def _calcola_hash_portafoglio_cache(portafoglio, impostazioni):
    """
    Calcola un hash SHA-256 stabile della struttura del portafoglio e della watchlist dell'utente
    (ignorando i prezzi live volatili così il ricaricamento del browser mobile fa CACHE HIT istantaneo).
    """
    righe_strutt = []
    for p in (portafoglio or []):
        if not isinstance(p, dict):
            continue
        tk = str(p.get("Ticker", "")).strip().upper()
        if not tk:
            continue
        righe_strutt.append((
            tk,
            str(p.get("Tipo", "Spot")).strip().upper(),
            round(float(p.get("Quantita", 0) or 0), 6),
            round(float(p.get("Prezzo_Medio", 0) or 0), 4),
            str(p.get("Data_Acquisto") or p.get("data_acquisto") or "")[:10],
        ))
    righe_strutt.sort()
    imp_strutt = {
        "wl": str((impostazioni or {}).get("lista_ticker_default") or "").strip(),
        "cat": str((impostazioni or {}).get("catalizzatori") or "").strip(),
        "esc": str((impostazioni or {}).get("esclusioni") or "").strip(),
        "cap": (impostazioni or {}).get("capitale_versato"),
    }
    raw = json.dumps({"p": righe_strutt, "i": imp_strutt}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

@st.cache_resource
def _get_home_snapshot_cache_store():
    """Store in memoria di processo (TTL 1200s) per gli snapshot Home Page, con supporto a progress bar live su cache miss."""
    return {}

def _esegui_cascata_home_cached(
    utente_corrente,
    hash_portafoglio,
    force_refresh_counter,
    _portafoglio_raw,
    _impostazioni_raw,
    _semaforo_header_raw,
    progress_cb=None,
):
    """
    Esegue e mette in cache per 20 minuti (ttl=1200) l'intera cascata della Home Page Pilota Automatico:
    1) Quotazioni & Market Data Hub
    2) Salute Portafoglio, Tom Nash & Insider SEC
    3) Scansione principale + pattern_engine + Bacheca Segnali Attivi
    4) Radar IGNITION 80, Insider SEC & Setup Palantir AI
    5) Calcolo Top 1, Piano B Qualitativo & DCA Doppio Binario
    Su cache hit (< 1200s) restituisce istantaneamente lo snapshot; su cache miss aggiorna progress_cb live.
    """
    import time
    cache_store = _get_home_snapshot_cache_store()
    cache_key = (str(utente_corrente or "fabio").strip().lower(), str(hash_portafoglio or ""), int(force_refresh_counter or 0))
    now_ts = time.monotonic()
    cached_entry = cache_store.get(cache_key)
    if cached_entry is not None and (now_ts - cached_entry[0]) < 1200.0:
        return cached_entry[1]

    def _notify(pct, msg):
        if callable(progress_cb):
            try:
                progress_cb(pct, msg)
            except Exception:
                pass

    chiave_u = str(utente_corrente or "fabio").strip().lower()
    eurusd_live = get_live_eurusd()
    impostazioni_loc = dict(_impostazioni_raw or {})
    semaforo_loc = dict(_semaforo_header_raw or calcola_semaforo_mercato() or {})
    port_loc = [dict(p) for p in (_portafoglio_raw or []) if isinstance(p, dict)]

    # Fase 1/5: Quotazioni live portafoglio + Market Data Hub condiviso
    _notify(15, "Fase 1/5 — Aggiorno quotazioni portafoglio e scarico Market Data Hub...")
    try:
        if port_loc:
            port_loc = aggiorna_quotazioni_portafoglio(port_loc, eurusd_live)
            st.session_state.portafoglio = port_loc
            salva_ultimo_agg_prezzi()
    except Exception:
        pass

    wl_home = str(impostazioni_loc.get("lista_ticker_default") or "")
    cat_home = str(impostazioni_loc.get("catalizzatori") or "")
    esc_home = str(impostazioni_loc.get("esclusioni") or "")
    wl_list_h = [t.strip().upper() for t in wl_home.replace("\n", ",").split(",") if t.strip()]
    port_tks_h = [str(p.get("Ticker", "")).strip().upper() for p in port_loc if p.get("Ticker")]
    bt_list_h = [t.strip().upper() for t in BIG_TECH_GROWTH_LIST.split(",") if t.strip()]
    ig_list_h = list(IGNITION_UNIVERSE) if "IGNITION_UNIVERSE" in globals() else []
    tutti_tks_hub = tuple(sorted(list(set(wl_list_h + port_tks_h + bt_list_h + ig_list_h))))
    hub_ohlc = _scarica_ohlc_batch_cached(tutti_tks_hub, period="1y")

    # Fase 2/5: Salute Portafoglio (S-Score, Scudo Tom Nash, SEC Form 4 'buys', SMA 200, WinRate 60gg)
    _notify(35, "Fase 2/5 — Valuto salute portafoglio, Scudo Tom Nash e Insider SEC...")
    try:
        salute_h = _valuta_salute_portafoglio_home(port_loc, eurusd_live, ohlc_map=hub_ohlc)
    except Exception:
        salute_h = {}
    st.session_state["home_salute_portafoglio"] = salute_h
    # Sincronizza gli avvisi di Protezione Profitto (solo quote Spot, mai PAC) riusando hub_ohlc a zero chiamate API extra
    try:
        if "regia_tracker" in globals() and hasattr(regia_tracker, "sincronizza_avvisi_protezione_spot"):
            regia_tracker.sincronizza_avvisi_protezione_spot(port_loc, eurusd_rate=eurusd_live, ohlc_map=hub_ohlc, utente=chiave_u)
    except Exception:
        pass

    # Fase 3/5: Scansione Principale + pattern_engine + Bacheca Segnali Attivi
    _notify(58, "Fase 3/5 — Eseguo scansione tecnica, figure grafiche e Bacheca Segnali...")
    noop_pb = _NoOpProgress()
    esegui_scansione_completa_motore(
        impostazioni=impostazioni_loc,
        tickers_input=wl_home,
        catalizzatori_input=cat_home,
        esclusioni_input=esc_home,
        period="1y",
        sma_short=50,
        sma_long=200,
        eurusd_rate=eurusd_live,
        ignore_fase_4=True,
        semaforo_header=semaforo_loc,
        salva_impostazioni=False,
        progress_bar=noop_pb,
        mostra_info_avvio=False,
        ohlc_map=hub_ohlc,
        max_docs_sec=8,
    )
    if isinstance(st.session_state.get("portafoglio"), list) and st.session_state.get("portafoglio"):
        port_loc = [dict(p) for p in st.session_state.get("portafoglio")]
    salute_h = st.session_state.get("home_salute_portafoglio") or salute_h

    # Fase 4/5: Radar IGNITION 80 + Insider SEC leggero + Setup Palantir AI
    _notify(80, "Fase 4/5 — Analizzo Radar IGNITION 80, Insider SEC e Setup Palantir AI...")
    radar_rows = []
    try:
        radar_rows, _ = esegui_radar_ignition_80(watchlist_str=wl_home, ohlc_map=hub_ohlc, progress_bar=None)
    except Exception:
        radar_rows = []
    ins_rows = []
    try:
        ins_rows, _ = esegui_scansione_insider_sec(
            watchlist_str=wl_home,
            portafoglio=port_loc,
            solo_con_insider=True,
            min_s_score=55,
            max_dist_min=30,
            include_panier_esteso=False,
            max_docs_sec=8,
            progress_bar=None,
        )
    except Exception:
        ins_rows = []
    pal_cands = []
    try:
        pal_cands, _, _ = esegui_scansione_ai_palantir(
            watchlist_str=wl_home,
            period="1y",
            eurusd_rate=eurusd_live,
            ohlc_map=hub_ohlc,
            scrivi_paper=False,
            progress_bar=None,
        )
    except Exception:
        pal_cands = []

    # Fase 5/5: Calcolo Top 1 Unico, Piano B Qualitativo & DCA Doppio Binario
    _notify(95, "Fase 5/5 — Calcolo Top 1 Unico, Piano B Qualitativo e DCA Doppio Binario...")
    res_podc = None
    piano_alloc = None
    liq_reale_alloc = 0.0
    cap_inv_tmp = sum(float(p.get("Prezzo_Medio", 0) or 0) * float(p.get("Quantita", 0) or 0) for p in port_loc)
    val_pos_tmp = sum(
        float(p.get("Quantita", 0) or 0) * (float(p.get("Prezzo_Attuale_EUR")) if (p.get("Prezzo_Attuale_EUR") is not None and float(p.get("Prezzo_Attuale_EUR") or 0) > 0) else float(p.get("Prezzo_Medio", 0) or 0))
        for p in port_loc
    )
    if chiave_u == "fabio":
        liq_reale_alloc = round(max(0.0, float(calcola_liquidita_totale() or 0.0)), 2)
    else:
        cap_v_tmp = float(impostazioni_loc.get("capitale_versato")) if (impostazioni_loc.get("capitale_versato") is not None) else CAPITALE_VERSATO_DEFAULT
        liq_reale_alloc = round(max(0.0, cap_v_tmp - cap_inv_tmp), 2)

    spy_st = str(semaforo_loc.get("stato", "giallo")).lower()
    _, qqq_st, _ = _verifica_qqq_regime_verde()
    pat_alerts_snap = st.session_state.get("pattern_alerts") or {}
    val_tot_tmp = round(val_pos_tmp + liq_reale_alloc, 2)
    top1_c, veto_m = _calcola_top1_super_automatismo(
        portafoglio=port_loc,
        val_totale_port=val_tot_tmp,
        eurusd_rate=eurusd_live,
        spy_stato=spy_st,
        qqq_stato=qqq_st,
        pattern_alerts=pat_alerts_snap,
        radar_ignition_rows=radar_rows,
        palantir_candidati=pal_cands,
    )
    target_sc_buy = int(top1_c.get("super_score")) if isinstance(top1_c, dict) else None
    riserva_snap = _trova_riserva_liquidita_intelligente(
        port_loc, salute_h, target_score=target_sc_buy, modalita="BUY", liq_libera=liq_reale_alloc
    )
    dca_snap = _calcola_dca_doppio_binario(port_loc, salute_h, pat_alerts_snap, liq_reale_alloc)
    dca_piano_b_snap = None
    if liq_reale_alloc < 40.0 and port_loc:
        _dca_b1 = _calcola_dca_doppio_binario(
            port_loc, salute_h, pat_alerts_snap, liq_reale_alloc, ignora_soglia_cassa=True, importo_ref_piano_b=200.0
        )
        if _dca_b1 and int(_dca_b1.get("binario", 2)) == 1 and int(_dca_b1.get("s_score", 0)) >= 75 and float(_dca_b1.get("riduzione_rimb", 0)) >= 6.0:
            dca_piano_b_snap = _dca_b1

    snap_res = {
        "portafoglio": port_loc,
        "home_salute_portafoglio": salute_h,
        "dashboard_stats": st.session_state.get("dashboard_stats"),
        "pattern_alerts": pat_alerts_snap,
        "pyramiding_alerts": st.session_state.get("pyramiding_alerts") or [],
        "take_profit_alerts": st.session_state.get("take_profit_alerts") or [],
        "zona_interesse_alerts": st.session_state.get("zona_interesse_alerts") or [],
        "extended_hours_alerts": st.session_state.get("extended_hours_alerts") or [],
        "df_fortezza": st.session_state.get("df_fortezza"),
        "df_cavalli": st.session_state.get("df_cavalli"),
        "df_monitor": st.session_state.get("df_monitor"),
        "df_palantir": st.session_state.get("df_palantir"),
        "risultati_radar_ignition_80": radar_rows,
        "insider_results": ins_rows,
        "ai_palantir_candidati": pal_cands,
        "risultato_podc": None,
        "piano_allocazione": None,
        "liquidita_totale_alloc": liq_reale_alloc,
        "home_snapshot_decisionale": {
            "top1_cand": top1_c,
            "veto_regime_msg": veto_m,
            "riserva": riserva_snap,
            "dca_cand": dca_snap,
            "dca_piano_b": dca_piano_b_snap,
            "calcolato_alle": _now_italia().strftime("%d/%m/%Y %H:%M"),
        },
    }
    # Registra automaticamente i segnali confermati del Pilota nel Tracker (Origine='Metodo Sistema', anti-duplicati)
    try:
        if "regia_tracker" in globals() and hasattr(regia_tracker, "registra_segnali_pilota_automatico"):
            regia_tracker.registra_segnali_pilota_automatico(
                snap_res["home_snapshot_decisionale"],
                portafoglio=port_loc,
                eurusd_rate=eurusd_live,
                liq_libera=liq_reale_alloc,
            )
    except Exception:
        pass
    # Report Settimanale automatico del Sabato su Telegram (1 volta/settimana, flag YYYY-Www su impostazioni*.json/GitHub)
    try:
        _invia_report_settimanale_sabato_telegram(
            chiave_u=chiave_u,
            portafoglio=port_loc,
            watchlist_str=wl_home,
            hub_ohlc=hub_ohlc,
            pattern_alerts=pat_alerts_snap,
            semaforo_loc=semaforo_loc,
            forza_invio=False,
        )
    except Exception:
        pass
    cache_store[cache_key] = (time.monotonic(), snap_res)
    _notify(100, "Analisi completata!")
    return snap_res

def _applica_snapshot_home_a_session_state(snapshot):
    """Ripopola istantaneamente tutte le chiavi di st.session_state dallo snapshot cachato."""
    if not isinstance(snapshot, dict):
        return
    if isinstance(snapshot.get("portafoglio"), list):
        st.session_state["portafoglio"] = snapshot["portafoglio"]
    for k in (
        "home_salute_portafoglio",
        "dashboard_stats",
        "pattern_alerts",
        "pyramiding_alerts",
        "take_profit_alerts",
        "zona_interesse_alerts",
        "extended_hours_alerts",
        "df_fortezza",
        "df_cavalli",
        "df_monitor",
        "df_palantir",
        "risultati_radar_ignition_80",
        "insider_results",
        "ai_palantir_candidati",
        "risultato_podc",
        "piano_allocazione",
        "liquidita_totale_alloc",
        "home_snapshot_decisionale",
    ):
        if k in snapshot:
            st.session_state[k] = snapshot[k]
    st.session_state["scansione_completata"] = True
    st.session_state["home_cascata_eseguita"] = True

def _costruisci_righe_tabella_salute(port_h, salute_map):
    """Costruisce le righe formattate della Tabella Salute Portafoglio (usate sia nella Home sia nella Vista Grande)."""
    righe_sal = []
    for pos in (port_h or []):
        tk = str(pos.get("Ticker", "")).strip().upper()
        if not tk:
            continue
        inf = (salute_map or {}).get(tk) or {}
        # Variazione giornaliera "Oggi %" (con indicatore verde/rosso immediato)
        var_oggi = pos.get("Variazione_Pct")
        if var_oggi is None:
            var_oggi = inf.get("var_pct_oggi")
        if var_oggi is None:
            c_og_s = inf.get("close_oggi")
            c_ie_s = inf.get("close_ieri")
            if c_og_s is not None and c_ie_s is not None and float(c_ie_s) > 0:
                var_oggi = round(((float(c_og_s) / float(c_ie_s)) - 1.0) * 100.0, 2)
        if var_oggi is not None:
            vo_f = float(var_oggi)
            ico_vo = "🟢" if vo_f > 0 else ("🔴" if vo_f < 0 else "⚪")
            oggi_lbl = f"{ico_vo} {vo_f:+.2f}%"
        else:
            oggi_lbl = "⚪ N/D"

        s200 = inf.get("sopra_sma200")
        s200_lbl = "🟢 Sopra" if s200 is True else ("🔴 Sotto" if s200 is False else "⚪ N/D")
        wr = inf.get("winrate_60g")
        wr_lbl = f"{wr:.1f}%" if wr is not None else "N/D"
        sec_lbl = _formatta_badge_sec_tabella(
            inf.get("sec_buys", 0),
            inf.get("sec_valore_usd", 0.0),
            inf.get("sec_ultimo_acquisto", ""),
        )
        # Etichetta Tipo ultra-compatta anti-troncamento: PAC (🟢) / PAC (⏸️) / Spot / PAC+Spot
        q_pac_t, q_spot_t = _calcola_ripartizione_pac_spot(pos)
        pac_sosp_t = bool(pos.get("PAC_Sospeso", False))
        ico_pac_t = "⏸️" if pac_sosp_t else "🟢"
        if q_pac_t > 1e-6 and q_spot_t > 1e-6:
            tipo_sal_lbl = f"PAC+Spot ({ico_pac_t})"
        elif q_pac_t > 1e-6:
            tipo_sal_lbl = f"PAC ({ico_pac_t})"
        else:
            tipo_sal_lbl = "Spot"

        righe_sal.append({
            "Ticker": tk,
            "Oggi %": oggi_lbl,
            "P&L %": f"{float(inf.get('pnl_pct', 0) or 0):+.2f}%",
            "S-Score": f"{int(inf.get('s_score', 50) or 50)}/100",
            "Insider SEC (90gg)": sec_lbl,
            "SMA 200": s200_lbl,
            "Fase Weinstein": inf.get("fase", "N/D"),
            "WinRate 60gg": wr_lbl,
            "Tipo": tipo_sal_lbl,
        })
    return righe_sal


def render_vista_tabella_salute_fullscreen(impostazioni):
    """
    Schermata dedicata a 100% schermo intero (da bordo a bordo, senza sidebar) della
    Tabella Salute Portafoglio con caratteri normali e puliti (13.5px) e pulsante
    '🔄 Aggiorna Prezzi Live' sempre visibile in cima.
    """
    # Nasconde temporaneamente la sidebar e lascia spazio libero sotto l'header Streamlit Cloud
    st.markdown(
        "<style>"
        "section[data-testid='stSidebar'], button[data-testid='collapsedControl'] { display: none !important; }"
        "[data-testid='stMainBlockContainer'], .block-container { max-width: 100% !important; width: 100% !important; padding: 3.2rem 1.25rem 1.0rem 1.25rem !important; }"
        "div[data-testid='stHorizontalBlock'] { align-items: flex-start !important; }"
        "div[data-testid='stHorizontalBlock'] [data-testid='stMarkdownContainer'], "
        "div[data-testid='stHorizontalBlock'] div[data-testid='stButton'] { margin: 0 !important; }"
        "div[data-testid='stHorizontalBlock'] div[data-testid='stButton'] button { height: 42px !important; min-height: 42px !important; padding: 0 0.75rem !important; font-size: 0.88rem !important; line-height: 1.2 !important; margin: 0 !important; }"
        ".mx-salute-full-wrap { width: 100%; overflow-x: auto; border: 1px solid #334155; border-radius: 10px; background: #0B0E11; margin-top: 8px; }"
        ".mx-salute-full-tbl { width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; font-size: 13.5px; color: #F8FAFC; }"
        ".mx-salute-full-tbl thead th { background: #1E293B; color: #CBD5E1; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; padding: 9px 12px; text-align: left; border-bottom: 2px solid #334155; white-space: nowrap; }"
        ".mx-salute-full-tbl tbody tr { background: #111622; border-bottom: 1px solid #1E293B; }"
        ".mx-salute-full-tbl tbody tr:nth-child(even) { background: #0D121B; }"
        ".mx-salute-full-tbl tbody tr:hover { background: #1B2538; }"
        ".mx-salute-full-tbl tbody td { padding: 7px 12px; vertical-align: middle; white-space: nowrap; }"
        "</style>",
        unsafe_allow_html=True,
    )

    chiave_u = PROFILO_ATTIVO.get("chiave", "fabio")
    eurusd_live = get_live_eurusd()
    nascondi_eur = bool(st.session_state.get("nascondi_saldi", False))
    port_f = st.session_state.get("portafoglio") or []
    sal_f = st.session_state.get("home_salute_portafoglio") or {}

    c_top_l, c_top_m, c_top_r = st.columns([2.8, 1.0, 0.8])
    with c_top_m:
        if st.button("🔄 Aggiorna Prezzi Live", key="btn_full_aggiorna_prezzi_live", type="primary", use_container_width=True):
            with st.spinner("Aggiorno quotazioni live..."):
                port_f, sal_f, n_live = _aggiorna_solo_prezzi_live_portafoglio(
                    port_f, eurusd_live, salute_map=sal_f, chiave_u=chiave_u
                )
            if n_live > 0:
                st.toast(f"⚡ Prezzi live aggiornati su {n_live} titoli!", icon="🔄")
            else:
                st.toast("⚠️ Impossibile scaricare quotazioni live al momento.", icon="⚠️")
    with c_top_r:
        if st.button("✖️ Torna alla Home", key="btn_full_torna_home", use_container_width=True):
            st.session_state["vista_attiva"] = "home"
            st.rerun()

    # Riepilogo live aggiornato
    val_pos_f = 0.0
    cap_inv_f = 0.0
    for p_f in port_f:
        q_f = float(p_f.get("Quantita", 0) or 0)
        pmc_f = float(p_f.get("Prezzo_Medio", 0) or 0)
        att_f = p_f.get("Prezzo_Attuale_EUR")
        cap_inv_f += q_f * pmc_f
        val_pos_f += q_f * float(att_f) if (att_f is not None and float(att_f or 0) > 0) else q_f * pmc_f
    if chiave_u == "fabio":
        liq_f = round(max(0.0, float(calcola_liquidita_totale() or 0.0)), 2)
    else:
        cap_v_f = float(impostazioni.get("capitale_versato")) if (isinstance(impostazioni, dict) and impostazioni.get("capitale_versato") is not None) else CAPITALE_VERSATO_DEFAULT
        liq_f = round(max(0.0, cap_v_f - cap_inv_f), 2)
    val_tot_f = round(val_pos_f + liq_f, 2)
    pnl_e_f = val_pos_f - cap_inv_f
    pnl_p_f = ((val_pos_f / cap_inv_f) - 1.0) * 100.0 if cap_inv_f > 0 else 0.0
    col_f = "#4ADE80" if pnl_e_f >= 0 else "#F87171"
    str_vt_f = "€ ••••" if nascondi_eur else f"€ {val_tot_f:,.2f}"
    str_pe_f = "€ ••••" if nascondi_eur else f"€ {pnl_e_f:+,.2f}"
    ora_f = (st.session_state.get("home_snapshot_decisionale") or {}).get("calcolato_alle") or _now_italia().strftime("%d/%m/%Y %H:%M")

    with c_top_l:
        st.markdown(
            f"<div style='background:#131722; border:1px solid #334155; border-left:4px solid #38BDF8; "
            f"border-radius:10px; height:42px; box-sizing:border-box; display:flex; align-items:center; "
            f"padding:0 1.0rem; margin:0; color:#F8FAFC; font-size:0.95rem; font-weight:700; white-space:nowrap; overflow:hidden;'>"
            f"📊 Tabella Salute Portafoglio &nbsp;|&nbsp; "
            f"💼 Totale:&nbsp;<b>{str_vt_f}</b> &nbsp;•&nbsp; "
            f"📈 P&amp;L:&nbsp;<span style='color:{col_f};'>{str_pe_f} ({pnl_p_f:+.2f}%)</span> &nbsp;•&nbsp; "
            f"<span style='color:#CBD5E1; font-size:0.84rem;'>🕒 {ora_f}</span></div>",
            unsafe_allow_html=True,
        )

    righe_f = _costruisci_righe_tabella_salute(port_f, sal_f)
    trs_html = []
    for rg in righe_f:
        oggi_v = str(rg.get("Oggi %", ""))
        col_og = "#4ADE80" if "+" in oggi_v else ("#F87171" if "-" in oggi_v else "#E2E8F0")
        pnl_v = str(rg.get("P&L %", ""))
        col_pl = "#4ADE80" if pnl_v.startswith("+") else ("#F87171" if pnl_v.startswith("-") else "#E2E8F0")
        trs_html.append(
            "<tr>"
            f"<td style='font-weight:800; color:#F8FAFC;'>{rg['Ticker']}</td>"
            f"<td style='font-weight:700; color:{col_og};'>{oggi_v}</td>"
            f"<td style='font-weight:700; color:{col_pl};'>{pnl_v}</td>"
            f"<td style='font-weight:600; color:#E2E8F0;'>{rg['S-Score']}</td>"
            f"<td style='color:#E0F2FE;'>{rg['Insider SEC (90gg)']}</td>"
            f"<td style='font-weight:600;'>{rg['SMA 200']}</td>"
            f"<td style='color:#E2E8F0;'>{rg['Fase Weinstein']}</td>"
            f"<td style='color:#CBD5E1;'>{rg['WinRate 60gg']}</td>"
            f"<td style='font-weight:700; color:#F8FAFC;'>{rg['Tipo']}</td>"
            "</tr>"
        )
    tbl_html = "".join([
        "<div class='mx-salute-full-wrap'><table class='mx-salute-full-tbl'>",
        "<thead><tr>",
        "<th>Ticker</th><th>Oggi %</th><th>P&amp;L %</th><th>S-Score</th>",
        "<th>Insider SEC (90gg)</th><th>SMA 200</th><th>Fase Weinstein</th>",
        "<th>WinRate 60gg</th><th>Tipo</th>",
        "</tr></thead><tbody>",
        "".join(trs_html),
        "</tbody></table></div>",
    ])
    st.markdown(tbl_html, unsafe_allow_html=True)


def render_home_pilota_automatico(impostazioni, semaforo_header):
    """
    Renderizza la '🏠 Home Page — Pilota Automatico' con cache istantanea (@st.cache_data ttl=1200):
    1) Al primo ingresso o su click '🔄 Aggiorna Analisi' esegue la cascata completa.
    2) Al ricaricamento del browser mobile (es. ritorno da Trade Republic entro 20 min) ripopola
       istantaneamente Home Page e Terminale Completo in ~0.2 secondi senza barre di attesa.
    """
    nome_u = PROFILO_ATTIVO.get("nome") or st.session_state.get("utente_corrente") or "Utente"
    chiave_u = PROFILO_ATTIVO.get("chiave", "fabio")
    eurusd_live = get_live_eurusd()

    # Sincronizza lo stato privacy 'nascondi_saldi' con il Terminale Completo (privacy_saldi.json)
    _p_file_home = "privacy_saldi.json"
    if "nascondi_saldi" not in st.session_state:
        try:
            with open(_p_file_home, "r", encoding="utf-8") as _fh:
                st.session_state.nascondi_saldi = bool(json.load(_fh).get("nascondi", False))
        except Exception:
            st.session_state.nascondi_saldi = False

    # 1) Esecuzione / Ripristino istantaneo dalla cache (@st.cache_data ttl=1200)
    port_corrente_raw = st.session_state.get("portafoglio") or []
    hash_pf = _calcola_hash_portafoglio_cache(port_corrente_raw, impostazioni)
    force_store = _get_home_force_counter_store()
    force_cnt = int(force_store.get(chiave_u, 0))

    if (not st.session_state.get("home_cascata_eseguita", False)) or (st.session_state.get("_home_hash_caricato") != hash_pf):
        import time
        t0_home = time.monotonic()
        loading_slot = st.empty()
        with loading_slot.container():
            st.markdown(
                f"<div style='background:#131722; border:1px solid #334155; border-left:5px solid #10B981; "
                f"border-radius:12px; padding:1.25rem 1.45rem; margin-bottom:0.85rem;'>"
                f"<div style='font-size:1.28rem; font-weight:800; color:#F8FAFC;'>"
                f"👋 Ciao {nome_u}, analisi Pilota Automatico in corso...</div>"
                f"<div style='font-size:0.86rem; color:#E2E8F0; margin-top:5px;'>"
                f"Avanzamento live in 5 fasi (alla riapertura entro 20 minuti il ripristino sarà istantaneo).</div></div>",
                unsafe_allow_html=True,
            )
            prog_bar_home = st.progress(0)
            status_slot_home = st.empty()

            def _aggiorna_progresso_home(pct, msg):
                elapsed_s = time.monotonic() - t0_home
                prog_bar_home.progress(min(100, max(0, int(pct))))
                status_slot_home.markdown(
                    f"<div style='color:#E0F2FE; font-size:0.88rem; font-weight:600; padding:2px 4px;'>"
                    f"⏳ {msg} <span style='color:#94A3B8;'>(⏱️ {elapsed_s:.1f}s)</span></div>",
                    unsafe_allow_html=True,
                )

            _aggiorna_progresso_home(5, "Avvio motore Pilota Automatico...")
            snapshot = _esegui_cascata_home_cached(
                chiave_u,
                hash_pf,
                force_cnt,
                port_corrente_raw,
                impostazioni,
                semaforo_header,
                progress_cb=_aggiorna_progresso_home,
            )
        loading_slot.empty()
        _applica_snapshot_home_a_session_state(snapshot)
        st.session_state["_home_hash_caricato"] = hash_pf

    # 2) Banner automatico festività / chiusure anticipate Borsa USA (NYSE / Nasdaq)
    render_banner_calendario_borsa_usa()
    # 2b) Termometro Macro SPY Drawdown 52 settimane (Zona Sconto Tom Nash -8%..-18% / Bear Market > -18%)
    render_banner_termometro_tom_nash(semaforo_header)

    # 3) Intestazione pulita della Home Page + pulsanti '👁️ Nascondi importi' e '🔄 Aggiorna Analisi'
    # Usa sempre l'ora italiana reale (ZoneInfo Europe/Rome) salvata nello snapshot o in impostazioni
    _snap_ora_it = (st.session_state.get("home_snapshot_decisionale") or {}).get("calcolato_alle")
    _agg_ora_h = _snap_ora_it or leggi_ultimo_agg_prezzi() or _now_italia().strftime("%d/%m/%Y %H:%M")
    c_hdr_l, c_hdr_priv, c_hdr_r = st.columns([2.8, 0.95, 1.05])
    with c_hdr_l:
        st.markdown(
            f"""
            <div style="background:#131722; border:1px solid #334155; border-left:5px solid #10B981;
                        border-radius:12px; padding:1.05rem 1.35rem; margin-bottom:0.85rem;">
                <div style="font-size:1.35rem; font-weight:800; color:#F8FAFC; line-height:1.25;">
                    🏠 Home Page — Pilota Automatico
                </div>
                <div style="font-size:0.92rem; color:#E2E8F0; margin-top:4px;">
                    {SALUTO_UTENTE_CORRENTE} &nbsp;•&nbsp; <span style="color:#CBD5E1; font-size:0.82rem;">🕒 Aggiornato: {_agg_ora_h}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c_hdr_priv:
        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
        lbl_priv = "👁️ Mostra importi" if st.session_state.nascondi_saldi else "👁️ Nascondi importi"
        if st.button(lbl_priv, use_container_width=True, key="btn_home_privacy_importi"):
            st.session_state.nascondi_saldi = not st.session_state.nascondi_saldi
            try:
                with open(_p_file_home, "w", encoding="utf-8") as _fh_w:
                    json.dump({"nascondi": st.session_state.nascondi_saldi}, _fh_w)
            except Exception:
                pass
            st.rerun()
    with c_hdr_r:
        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Aggiorna Analisi", type="primary", use_container_width=True, key="btn_home_aggiorna_cascata"):
            # Incrementa force_refresh_counter per forzare il ricalcolo fresco della cascata
            force_store[chiave_u] = int(force_store.get(chiave_u, 0)) + 1
            st.session_state["home_cascata_eseguita"] = False
            st.rerun()

    # Calcolo esatto di Valore Azioni, Totale Investito, Liquidità Libera Reale e Valore Totale Portafoglio
    port_h = st.session_state.get("portafoglio") or []
    val_pos_h = 0.0
    cap_inv_h = 0.0
    for p in port_h:
        q_p = float(p.get("Quantita", 0) or 0)
        pmc_p = float(p.get("Prezzo_Medio", 0) or 0)
        att_p = p.get("Prezzo_Attuale_EUR")
        cap_inv_h += q_p * pmc_p
        if att_p is not None and float(att_p or 0) > 0:
            val_pos_h += q_p * float(att_p)
        else:
            val_pos_h += q_p * pmc_p

    # Liquidità Libera ESCLUSIVAMENTE reale (zero liquidita_aggiuntiva simulata)
    if chiave_u == "fabio":
        liq_libera_h = round(max(0.0, float(calcola_liquidita_totale() or 0.0)), 2)
    else:
        if isinstance(impostazioni, dict) and impostazioni.get("capitale_versato") is not None:
            cap_versato_u = float(impostazioni.get("capitale_versato") or 0.0)
        else:
            cap_versato_u = CAPITALE_VERSATO_DEFAULT
        liq_libera_h = round(max(0.0, cap_versato_u - cap_inv_h), 2)

    val_totale_port_h = round(val_pos_h + liq_libera_h, 2)
    pnl_eur_h = val_pos_h - cap_inv_h
    pnl_pct_h = ((val_pos_h / cap_inv_h) - 1.0) * 100.0 if cap_inv_h > 0 else 0.0
    col_pnl_h = "#4ADE80" if pnl_eur_h >= 0 else "#F87171"
    nascondi_eur = bool(st.session_state.get("nascondi_saldi", False))

    str_val_tot = "€ ••••" if nascondi_eur else f"€ {val_totale_port_h:,.2f}"
    str_val_az = "€ ••••" if nascondi_eur else f"€ {val_pos_h:,.2f}"
    str_liq_lib = "€ ••••" if nascondi_eur else f"€ {liq_libera_h:,.2f}"
    str_pnl_eur = "€ ••••" if nascondi_eur else f"€ {pnl_eur_h:+,.2f}"

    # 2 Metriche grandi ad alto contrasto (testi bianchi su card scure)
    m_c1, m_c2 = st.columns(2)
    with m_c1:
        st.markdown(
            f"""
            <div style="background:#131722; border:1px solid #334155; border-top:4px solid #38BDF8;
                        border-radius:12px; padding:1.25rem 1.4rem; margin-bottom:1rem;">
                <div style="font-size:0.92rem; font-weight:700; color:#E2E8F0; letter-spacing:0.02em;">
                    💼 Valore Totale Portafoglio
                </div>
                <div style="font-family:'JetBrains Mono', monospace; font-size:2.05rem; font-weight:800;
                            color:#F8FAFC; margin-top:6px;">
                    {str_val_tot}
                </div>
                <div style="font-size:0.82rem; color:#CBD5E1; margin-top:4px;">
                    Azioni: {str_val_az} &nbsp;|&nbsp; Liquidità libera: {str_liq_lib}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m_c2:
        st.markdown(
            f"""
            <div style="background:#131722; border:1px solid #334155; border-top:4px solid {col_pnl_h};
                        border-radius:12px; padding:1.25rem 1.4rem; margin-bottom:1rem;">
                <div style="font-size:0.92rem; font-weight:700; color:#E2E8F0; letter-spacing:0.02em;">
                    📈 Guadagno / Perdita Netta
                </div>
                <div style="font-family:'JetBrains Mono', monospace; font-size:2.05rem; font-weight:800;
                            color:{col_pnl_h}; margin-top:6px;">
                    {str_pnl_eur} <span style="font-size:1.30rem;">({pnl_pct_h:+.2f}%)</span>
                </div>
                <div style="font-size:0.82rem; color:#CBD5E1; margin-top:4px;">
                    Posizioni attive: {len(port_h)} titoli monitorati automaticamente
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 3) Riquadro unico "🧭 COSA DEVO FARE OGGI" (Portafoglio + Nuovi Acquisti Top 1 + DCA Doppio Binario)
    spy_stato = str((semaforo_header or {}).get("stato", "giallo")).lower()
    spy_verde = (spy_stato == "verde")
    qqq_verde, qqq_stato, qqq_nota = _verifica_qqq_regime_verde()
    mercato_pieno_verde = bool(spy_verde and qqq_verde)

    salute_map = st.session_state.get("home_salute_portafoglio") or {}
    vendite_azioni = []
    prese_profitto = []
    scudi_tom_nash = []
    monitora_recupero = []
    avvisi_speculativi = []
    tickers_port_nomi = []
    # Raccoglie le proposte di vendita / take profit / switch per i pulsanti rapidi "⏭️ Tengo/Ignora"
    bivi_home_oggi = []
    _bivi_home_seen = set()

    def _aggiungi_bivio_home(tk_b, prezzo_eur_b, motivo_b, label_b, pct_b=100):
        tk_u_b = str(tk_b or "").strip().upper()
        chiave_b = (tk_u_b, str(motivo_b or "").strip().upper())
        if not tk_u_b or chiave_b in _bivi_home_seen:
            return
        p_b = float(prezzo_eur_b or 0.0)
        if p_b <= 0:
            pos_f = next((x for x in port_h if str(x.get("Ticker", "")).strip().upper() == tk_u_b), None)
            if pos_f:
                p_b = float(pos_f.get("Prezzo_Attuale_EUR") or pos_f.get("Prezzo_Medio") or 0.0)
        if p_b <= 0:
            return
        _bivi_home_seen.add(chiave_b)
        bivi_home_oggi.append({
            "ticker": tk_u_b,
            "prezzo_eur": round(p_b, 2),
            "motivo": str(motivo_b),
            "label": str(label_b),
            "pct_vendita": int(round(float(pct_b or 100))),
        })

    for pos in port_h:
        tk = str(pos.get("Ticker", "")).strip().upper()
        if not tk:
            continue
        tickers_port_nomi.append(tk)
        info_s = salute_map.get(tk) or {}
        s_sc = int(info_s.get("s_score", 65) or 65)
        fase_s = str(info_s.get("fase", "N/D")).upper()
        sopra_200 = info_s.get("sopra_sma200")
        q_p = float(pos.get("Quantita", 0) or 0)
        pmc_p = float(pos.get("Prezzo_Medio", 0) or 0)
        att_p = float(pos.get("Prezzo_Attuale_EUR") or 0)
        pnl_p = ((att_p / pmc_p) - 1.0) * 100.0 if (att_p > 0 and pmc_p > 0) else float(info_s.get("pnl_pct", 0) or 0)
        pnl_e = (att_p - pmc_p) * q_p if (att_p > 0 and pmc_p > 0) else float(info_s.get("pnl_eur", 0) or 0)

        # Presa profitto parziale 50% su guadagni molto elevati (>= +35%) solo se rispetta soglia anti-briciole (>= € 100 netti)
        if pnl_p >= 35.0:
            _, q_spot_h = _calcola_ripartizione_pac_spot(pos)
            if q_spot_h > 1e-6 and q_p > 0:
                val_att_h = att_p * q_p if att_p > 0 else float(info_s.get("val_att", 0) or 0)
                val_car_h = pmc_p * q_p if pmc_p > 0 else float(info_s.get("val_car", 0) or 0)
                frac_50_h = min(1.0, q_spot_h / q_p) * 0.5
                v_l_50 = val_att_h * frac_50_h
                g_l_50 = max(0.0, (val_att_h - val_car_h) * frac_50_h)
                netto_50_h = round(v_l_50 - (g_l_50 * 0.26) - 2.0, 2)
                if netto_50_h >= SOGLIA_MIN_NETTO_FONTE_A:
                    str_gain_e = "€ ••••" if nascondi_eur else f"€ {pnl_e:+,.2f}"
                    str_net50_e = "€ ••••" if nascondi_eur else f"€ {netto_50_h:,.2f}"
                    prese_profitto.append(
                        f"💰 <b>CONSIDERA PRESA PROFITTO: {tk} ({pnl_p:+.1f}%)</b> ({str_gain_e}) — "
                        f"Puoi consolidare il 50% (~{str_net50_e} netti) oppure liberare liquidità per finanziare un nuovo segnale BUY."
                    )
                    _aggiungi_bivio_home(tk, att_p, "Presa Profitto >= +35%", "Presa Profitto", pct_b=50)
            continue

        # Chiave corretta "buys" per acquisti ufficiali SEC Form 4 (90gg)
        n_acq_sec = int(info_s.get("sec_buys") or 0)
        if n_acq_sec == 0 and ("sec_buys" not in info_s):
            try:
                sec_info_p = get_sec_insider_buys_90gg(tk, max_docs=8) if "get_sec_insider_buys_90gg" in globals() else None
                n_acq_sec = int((sec_info_p or {}).get("buys") or 0)
            except Exception:
                n_acq_sec = 0
        ha_insider_sec = n_acq_sec > 0

        # Scudo Fondamentale Tom Nash (zero chiamate API extra: dati già in salute_map / _get_info_cached)
        scudo_tn_attivo = bool(info_s.get("scudo_tom_nash"))
        scudo_tn_nota = str(info_s.get("scudo_tom_nash_nota") or "")
        if ("scudo_tom_nash" not in info_s):
            _tn_fb = _valuta_fondamentali_tom_nash(_get_info_cached(tk), s_score=s_sc)
            scudo_tn_attivo = bool(_tn_fb.get("scudo_tom_nash"))
            scudo_tn_nota = str(_tn_fb.get("scudo_tom_nash_nota") or "")

        # Su titoli in perdita significativa (<= -5%) con fondamentali sani mostra lo Scudo Tom Nash e blocca ogni vendita
        if pnl_p <= -5.0 and scudo_tn_attivo:
            scudi_tom_nash.append(
                f"🛡️ <b>SCUDO TOM NASH — {tk} ({pnl_p:+.1f}%):</b> Azienda sana ({scudo_tn_nota}) — "
                f"calo solo macro/settoriale, non vendere sullo schermo rosso."
            )
            continue

        # Blocco Anti-Panico Assoluto: MAI vendere in perdita aziende sane (S-Score >= 65, sopra SMA 200 o Scudo Tom Nash)
        azienda_sana = (s_sc >= 65) or (sopra_200 is True) or scudo_tn_attivo
        if azienda_sana:
            continue

        # Deterioramento potenziale (Fase 4 sotto SMA 200 con S-Score < 65)
        if ("FASE 4" in fase_s) and (sopra_200 is False) and (s_sc < 65):
            if (not mercato_pieno_verde) or ha_insider_sec:
                if ha_insider_sec and (not mercato_pieno_verde):
                    msg_mon = (
                        f"🟡 <b>MONITORA RECUPERO — {tk}</b> protetto da <b>{n_acq_sec} acquisti ufficiali Insider SEC Form 4 (90gg)</b> "
                        f"+ correzione generale di mercato (SPY={spy_stato.upper()} / {qqq_nota}): non vendere sui minimi "
                        f"<span style='color:#CBD5E1; font-size:0.84rem;'>(P&amp;L {pnl_p:+.1f}%)</span>."
                    )
                elif ha_insider_sec:
                    msg_mon = (
                        f"🟡 <b>MONITORA RECUPERO — {tk}</b> protetto da <b>{n_acq_sec} acquisti ufficiali Insider SEC Form 4 (90gg)</b>: "
                        f"i dirigenti stanno comprando sul calo, non vendere sui minimi "
                        f"<span style='color:#CBD5E1; font-size:0.84rem;'>(P&amp;L {pnl_p:+.1f}%)</span>."
                    )
                else:
                    msg_mon = (
                        f"🟡 <b>MONITORA RECUPERO — {tk}</b> risente della correzione generale/settoriale "
                        f"(SPY={spy_stato.upper()} / {qqq_nota}): non vendere sui minimi di mercato "
                        f"<span style='color:#CBD5E1; font-size:0.84rem;'>(P&amp;L {pnl_p:+.1f}%)</span>."
                    )
                monitora_recupero.append(msg_mon)
            else:
                if s_sc < 55 and pnl_p < -8.0:
                    avvisi_speculativi.append(
                        f"🟠 <b>POSIZIONE SPECULATIVA ({tk})</b> — Crollo isolato sotto SMA 200 in Fase 4 "
                        f"(S-Score {s_sc}/100, P&amp;L {pnl_p:+.1f}%): non svendere nel panico, pianifica l'uscita vicino al pareggio."
                    )
                else:
                    vendite_azioni.append(
                        f"🔴 <b>AZIONE: VENDI {tk}</b> — Deterioramento strutturale isolato con mercato SPY/QQQ in regime VERDE "
                        f"(<b>Fase 4 confermata</b> sotto SMA 200, S-Score <b>{s_sc}/100</b>, zero acquisti SEC, P&amp;L {pnl_p:+.1f}%)."
                    )
                    _aggiungi_bivio_home(tk, att_p, "Vendita Fase 4", "Vendita Fase 4", pct_b=100)

    # Costruisce blocco HTML "1) SUL PORTAFOGLIO ATTUALE"
    if not port_h:
        blocco_port_html = (
            "<div style='color:#F8FAFC; font-size:0.95rem; line-height:1.55;'>"
            "🟢 <b>PORTAFOGLIO VUOTO</b> — Non hai posizioni aperte al momento.</div>"
        )
    else:
        parti_port = []
        if vendite_azioni:
            for r in vendite_azioni:
                parti_port.append(f"<div style='color:#F8FAFC; font-size:0.95rem; line-height:1.55; margin-bottom:6px;'>{r}</div>")
        if prese_profitto:
            for r in prese_profitto:
                parti_port.append(f"<div style='color:#F8FAFC; font-size:0.95rem; line-height:1.55; margin-bottom:6px;'>{r}</div>")
        if scudi_tom_nash:
            for r in scudi_tom_nash:
                parti_port.append(
                    f"<div style='color:#E0F2FE; font-size:0.92rem; line-height:1.5; margin-bottom:6px; "
                    f"background:#0F2436; border-left:3px solid #38BDF8; padding:6px 10px; border-radius:6px;'>{r}</div>"
                )
        if monitora_recupero:
            for r in monitora_recupero:
                parti_port.append(f"<div style='color:#F8FAFC; font-size:0.93rem; line-height:1.55; margin-bottom:6px;'>{r}</div>")
        if not vendite_azioni:
            lista_tk_str = ", ".join(tickers_port_nomi)
            parti_port.insert(
                0,
                f"<div style='color:#F8FAFC; font-size:0.95rem; line-height:1.55; margin-bottom:6px;'>"
                f"🟢 <b>NESSUNA VENDITA</b> — I tuoi titoli (<b>{lista_tk_str}</b>) sono aziende solide: "
                f"resta fermo e lascia lavorare il portafoglio (o valuta eventuale DCA solo se hai liquidità dedicata).</div>"
            )
        if avvisi_speculativi:
            for r in avvisi_speculativi:
                parti_port.append(
                    f"<div style='color:#E2E8F0; font-size:0.88rem; line-height:1.5; margin-top:6px; "
                    f"padding-top:6px; border-top:1px solid #1E293B;'>{r}</div>"
                )
        blocco_port_html = "".join(parti_port)

    # Costruisce blocco HTML "2) NUOVI ACQUISTI (TOP 1 UNICO + 3 SCUDI + RISERVA INTELLIGENTE)"
    pat_alerts_h = st.session_state.get("pattern_alerts") or {}
    radar_ig_h = st.session_state.get("risultati_radar_ignition_80") or []
    palantir_h = st.session_state.get("ai_palantir_candidati") or []
    snap_dec = st.session_state.get("home_snapshot_decisionale") or {}

    if "top1_cand" in snap_dec:
        top1_cand = snap_dec.get("top1_cand")
        veto_regime_msg = snap_dec.get("veto_regime_msg")
    else:
        top1_cand, veto_regime_msg = _calcola_top1_super_automatismo(
            portafoglio=port_h,
            val_totale_port=val_totale_port_h,
            eurusd_rate=eurusd_live,
            spy_stato=spy_stato,
            qqq_stato=qqq_stato,
            pattern_alerts=pat_alerts_h,
            radar_ignition_rows=radar_ig_h,
            palantir_candidati=palantir_h,
        )

    ordine_buy_proposto = False
    if veto_regime_msg:
        blocco_acq_html = (
            f"<div style='color:#F8FAFC; font-size:0.95rem; line-height:1.55;'>"
            f"🛡️ <b>NESSUN ACQUISTO OGGI</b> — {veto_regime_msg}</div>"
        )
    elif liq_libera_h >= 40.0:
        if top1_cand is not None:
            ordine_buy_proposto = True
            imp_ord = round(min(liq_libera_h, 500.0), 2)
            taglia_str, nota_comm = _formatta_taglia_esecuzione_tr(imp_ord, top1_cand["prezzo_eur"], nascondi_eur=nascondi_eur)
            simb_o = "$" if top1_cand["currency"] == "USD" else "€"
            motori_str = " + ".join(top1_cand["motori"])
            sec_tag = f" • 🏛️ {top1_cand['sec_buys']} acq SEC" if top1_cand.get("sec_buys", 0) > 0 else ""
            mult_tag = f" • {top1_cand['badge_multipli']}" if top1_cand.get("badge_multipli") else ""
            blocco_acq_html = (
                f"<div style='color:#F8FAFC; font-size:0.95rem; line-height:1.65; "
                f"padding:0.85rem 1.0rem; background:#0B0E11; border:1px solid #10B981; border-radius:8px;'>"
                f"🚀 <b>ORDINE PRONTO (TOP 1):</b> Acquista <b>{taglia_str}</b> di <b>{top1_cand['ticker']}</b> a mercato "
                f"(dopo le 15:45 italiane per avere lo spread migliore), verificando che il prezzo non superi "
                f"<b>{simb_o}{top1_cand['max_entry']:.2f}</b> — Stop Loss a <b>{simb_o}{top1_cand['stop_price']:.2f}</b> — "
                f"Target a <b>{simb_o}{top1_cand['target_price']:.2f}</b> (Orizzonte: <b>{top1_cand['orizzonte']}</b>)."
                f"<div style='color:#CBD5E1; font-size:0.82rem; margin-top:6px;'>"
                f"🏆 Super-Score <b>{top1_cand['super_score']}/100</b> • R/R <b>1:{top1_cand['rr']:.2f}</b> • "
                f"Motori: <b>{motori_str}</b> • S-Score {top1_cand['s_score']}/100{sec_tag}{mult_tag}{nota_comm}</div></div>"
            )
        else:
            blocco_acq_html = (
                "<div style='color:#F8FAFC; font-size:0.95rem; line-height:1.55;'>"
                "⏳ <b>NESSUN ACQUISTO OGGI</b> — Attendi: nessun titolo ha superato tutti i filtri (rottura confermata entro +3.5%, no utili ≤ 10gg, concentrazione sicura).</div>"
            )
    else:
        # Liquidità Libera < 40 € -> PIANO B QUALITATIVO (Switch Qualitativo vs Portafoglio Intatto)
        top1_valido_pb = (
            top1_cand is not None
            and int(top1_cand.get("super_score", 0)) >= 85
            and float(top1_cand.get("rr", 0)) >= 2.0
            and (top1_cand.get("is_breakout_matrix") or len(top1_cand.get("motori") or []) >= 2)
        )
        riserva = (
            _trova_riserva_liquidita_intelligente(
                port_h, salute_map, target_score=int(top1_cand.get("super_score", 0)), modalita="BUY", liq_libera=liq_libera_h
            )
            if top1_valido_pb else None
        )
        if top1_valido_pb and riserva is not None:
            ordine_buy_proposto = True
            _aggiungi_bivio_home(
                riserva["ticker"],
                0.0,
                f"Switch Piano B -> {top1_cand['ticker']}",
                f"Switch -> {top1_cand['ticker']}",
                pct_b=riserva.get("pct_vendita", 100),
            )
            imp_sw = round(min(riserva["netto_eur"] + liq_libera_h, 500.0), 2)
            taglia_sw, nota_comm_sw = _formatta_taglia_esecuzione_tr(imp_sw, top1_cand["prezzo_eur"], nascondi_eur=nascondi_eur)
            simb_o = "$" if top1_cand["currency"] == "USD" else "€"
            str_netto_r = "€ ••••" if nascondi_eur else f"€ {riserva['netto_eur']:,.2f}"
            str_tasse_r = "€ ••••" if nascondi_eur else f"€ {riserva['tasse_eur']:,.2f}"
            delta_str = f" • Delta Qualitativo +{riserva['delta_qualita']} pt" if riserva.get("delta_qualita") is not None else ""
            blocco_acq_html = (
                f"<div style='color:#F8FAFC; font-size:0.95rem; line-height:1.65; "
                f"padding:0.85rem 1.0rem; background:#0B0E11; border:1px solid #38BDF8; border-radius:8px;'>"
                f"🔄 <b>PIANO B — SWITCH QUALITATIVO IN 2 PASSI (Super-Score {top1_cand['super_score']}/100, R/R 1:{top1_cand['rr']:.2f}{delta_str}):</b><br>"
                f"<b>Passo 1 (Libera Riserva — {riserva['fonte']}):</b> Vendi il <b>{riserva['pct_vendita']}%</b> di <b>{riserva['ticker']}</b> "
                f"({riserva['motivo']}) → liberi circa <b>{str_netto_r} netti</b> (già al netto di {str_tasse_r} tasse 26% sulla plusvalenza e € 2 commissioni TR).<br>"
                f"<b>Passo 2 (Ordine Pronto dopo le 15:45):</b> Acquista <b>{taglia_sw}</b> di <b>{top1_cand['ticker']}</b> a mercato, "
                f"verificando che il prezzo non superi <b>{simb_o}{top1_cand['max_entry']:.2f}</b> — Stop Loss a <b>{simb_o}{top1_cand['stop_price']:.2f}</b> — "
                f"Target a <b>{simb_o}{top1_cand['target_price']:.2f}</b> (Orizzonte: <b>{top1_cand['orizzonte']}</b>).{nota_comm_sw}</div>"
            )
        elif top1_valido_pb:
            ordine_buy_proposto = True
            imp_nuova = max(150.0, round(float(top1_cand.get("prezzo_eur") or 200.0), 0))
            str_imp_n = "€ ••••" if nascondi_eur else f"€ {imp_nuova:,.0f}"
            simb_o = "$" if top1_cand["currency"] == "USD" else "€"
            blocco_acq_html = (
                f"<div style='color:#F8FAFC; font-size:0.94rem; line-height:1.62; "
                f"padding:0.85rem 1.0rem; background:#0F2436; border:1px solid #38BDF8; border-radius:8px;'>"
                f"🛡️ <b>PORTAFOGLIO INTATTO — Nessun titolo da vendere (tutti i titoli sono solidi o in PAC).</b><br>"
                f"✨ Opportunità valida rilevata: <b>{top1_cand['ticker']}</b> (Super-Score <b>{top1_cand['super_score']}/100</b>, "
                f"R/R <b>1:{top1_cand['rr']:.2f}</b>, max ingresso {simb_o}{top1_cand['max_entry']:.2f}). "
                f"Se vuoi cogliere <b>{top1_cand['ticker']}</b>, versa <b>{str_imp_n}</b> di nuova liquidità dedicata su Trade Republic; "
                f"altrimenti resta fermo senza rimpianti.</div>"
            )
        else:
            blocco_acq_html = (
                "<div style='color:#F8FAFC; font-size:0.95rem; line-height:1.55;'>"
                "🟢 <b>NESSUN ACQUISTO</b> — Non devi fare nulla finché uno dei tuoi titoli non arriverà a target liberando nuova liquidità (o non scatti un setup eccezionale).</div>"
            )

    # Costruisce blocco HTML "3) DCA MATEMATICO DOPPIO BINARIO" (cassa >= 40 € oppure Piano B su DCA Binario 1 alta qualità)
    blocco_dca_html = ""
    if (not ordine_buy_proposto) and port_h:
        if liq_libera_h >= 40.0:
            dca_cand = snap_dec.get("dca_cand") if ("dca_cand" in snap_dec) else _calcola_dca_doppio_binario(port_h, salute_map, pat_alerts_h, liq_libera_h)
            if dca_cand is not None:
                taglia_dca, nota_comm_dca = _formatta_taglia_esecuzione_tr(dca_cand["importo_eur"], dca_cand["prezzo_eur"], nascondi_eur=nascondi_eur)
                str_pmc_old = "€ ••••" if nascondi_eur else f"€ {dca_cand['pmc_old']:.2f}"
                str_pmc_new = "€ ••••" if nascondi_eur else f"€ {dca_cand['pmc_new']:.2f}"
                mult_dca_tag = f" • {dca_cand['badge_multipli']}" if dca_cand.get("badge_multipli") else ""
                zona_tn_dca = " — 📉 Zona Sconto Tom Nash attiva" if str((semaforo_header or {}).get("zona_sconto_tom_nash") or "") == "sconto" else ""
                blocco_dca_html = (
                    f"<div style='height:1px; background:#2A2E39; margin:1.05rem 0;'></div>"
                    f"<div style='font-size:0.80rem; font-weight:700; color:#CBD5E1; text-transform:uppercase; "
                    f"letter-spacing:0.05em; margin-bottom:0.40rem;'>🧮 DCA Matematico Doppio Binario{zona_tn_dca}</div>"
                    f"<div style='color:#F8FAFC; font-size:0.94rem; line-height:1.6; "
                    f"padding:0.75rem 0.95rem; background:#0B0E11; border:1px solid #38BDF8; border-radius:8px;'>"
                    f"💡 <b>MEDIAZIONE CONSIGLIATA SU {dca_cand['ticker']} ({dca_cand['pnl_pct']:+.1f}%):</b> "
                    f"Valuta un DCA di <b>{taglia_dca}</b> ({dca_cand['motivo']}; S-Score {dca_cand['s_score']}/100{mult_dca_tag}).<br>"
                    f"📊 <b>Impatto immediato:</b> PMC da <b>{str_pmc_old}</b> a <b>{str_pmc_new}</b> — "
                    f"il rimbalzo per tornare in pari si riduce da <b>+{dca_cand['rimb_prima']:.1f}%</b> a "
                    f"<b style='color:#4ADE80;'>+{dca_cand['rimb_dopo']:.1f}%</b>.{nota_comm_dca}</div>"
                )
            else:
                blocco_dca_html = (
                    "<div style='height:1px; background:#2A2E39; margin:1.05rem 0;'></div>"
                    "<div style='font-size:0.80rem; font-weight:700; color:#CBD5E1; text-transform:uppercase; "
                    "letter-spacing:0.05em; margin-bottom:0.40rem;'>🧮 DCA Matematico Doppio Binario</div>"
                    "<div style='color:#E2E8F0; font-size:0.90rem; line-height:1.5;'>"
                    "⏸️ Nessun DCA attivo oggi: nessun titolo sano in ritracciamento ha ancora dato conferma di inversione o stabilizzazione.</div>"
                )
        else:
            # Cassa < 40 € -> verifica se esiste un DCA Binario 1 di alta qualità (S-Score >= 75, riduzione >= 6 pt)
            dca_pb = snap_dec.get("dca_piano_b")
            if dca_pb is None and "dca_piano_b" not in snap_dec:
                _tmp_b1 = _calcola_dca_doppio_binario(port_h, salute_map, pat_alerts_h, liq_libera_h, ignora_soglia_cassa=True, importo_ref_piano_b=200.0)
                if _tmp_b1 and int(_tmp_b1.get("binario", 2)) == 1 and int(_tmp_b1.get("s_score", 0)) >= 75 and float(_tmp_b1.get("riduzione_rimb", 0)) >= 6.0:
                    dca_pb = _tmp_b1
            if dca_pb is not None:
                score_dca_pb = min(100, int(dca_pb.get("s_score", 75)) + int(dca_pb.get("bonus_multipli", 0)))
                ris_dca = _trova_riserva_liquidita_intelligente(
                    port_h, salute_map, target_score=score_dca_pb, modalita="DCA", liq_libera=liq_libera_h
                )
                if ris_dca is not None and ris_dca.get("ticker") != dca_pb.get("ticker"):
                    _aggiungi_bivio_home(
                        ris_dca["ticker"],
                        0.0,
                        f"Switch DCA -> {dca_pb['ticker']}",
                        f"Switch DCA -> {dca_pb['ticker']}",
                        pct_b=ris_dca.get("pct_vendita", 100),
                    )
                    str_net_d = "€ ••••" if nascondi_eur else f"€ {ris_dca['netto_eur']:,.2f}"
                    blocco_dca_html = (
                        f"<div style='height:1px; background:#2A2E39; margin:1.05rem 0;'></div>"
                        f"<div style='font-size:0.80rem; font-weight:700; color:#CBD5E1; text-transform:uppercase; "
                        f"letter-spacing:0.05em; margin-bottom:0.40rem;'>🧮 Piano B — Switch Qualitativo per DCA Binario 1</div>"
                        f"<div style='color:#F8FAFC; font-size:0.93rem; line-height:1.6; "
                        f"padding:0.75rem 0.95rem; background:#0B0E11; border:1px solid #38BDF8; border-radius:8px;'>"
                        f"🔄 <b>Passo 1 ({ris_dca['fonte']}):</b> Vendi il <b>{ris_dca['pct_vendita']}%</b> di <b>{ris_dca['ticker']}</b> "
                        f"({ris_dca['motivo']}) → liberi ~<b>{str_net_d} netti</b>.<br>"
                        f"💡 <b>Passo 2 (DCA Binario 1):</b> Media <b>{dca_pb['ticker']}</b> (S-Score {dca_pb['s_score']}/100, {dca_pb['motivo']}).</div>"
                    )
                else:
                    str_imp_d = "€ ••••" if nascondi_eur else f"€ {dca_pb['importo_eur']:,.0f}"
                    blocco_dca_html = (
                        f"<div style='height:1px; background:#2A2E39; margin:1.05rem 0;'></div>"
                        f"<div style='font-size:0.80rem; font-weight:700; color:#CBD5E1; text-transform:uppercase; "
                        f"letter-spacing:0.05em; margin-bottom:0.40rem;'>🧮 Piano B — DCA Binario 1 (Cassa Libera € 0)</div>"
                        f"<div style='color:#F8FAFC; font-size:0.93rem; line-height:1.6; "
                        f"padding:0.75rem 0.95rem; background:#0F2436; border:1px solid #38BDF8; border-radius:8px;'>"
                        f"🛡️ <b>PORTAFOGLIO INTATTO — Nessun titolo da vendere (tutti i titoli sono solidi o in PAC).</b><br>"
                        f"💡 Occasione DCA Binario 1 su <b>{dca_pb['ticker']}</b> ({dca_pb['pnl_pct']:+.1f}%, S-Score {dca_pb['s_score']}/100): "
                        f"se vuoi coglierla, versa <b>{str_imp_d}</b> di nuova liquidità dedicata su Trade Republic "
                        f"(rimbalzo al pareggio da +{dca_pb['rimb_prima']:.1f}% a <b style='color:#4ADE80;'>+{dca_pb['rimb_dopo']:.1f}%</b>); "
                        f"altrimenti resta fermo senza rimpianti.</div>"
                    )

    # 3b) Sotto-sezione dedicata se l'utente ha inserito ticker in "📌 Titoli da Acquistare (Priorità)"
    blocco_prio_html = ""
    _prio_str_home = str(st.session_state.get("titoli_priorita_input") or "").strip()
    if _prio_str_home:
        _esiti_prio = _valuta_titoli_priorita_home(
            priorita_str=_prio_str_home,
            portafoglio=port_h,
            salute_map=salute_map,
            val_totale_port=val_totale_port_h,
            eurusd_rate=eurusd_live,
            spy_stato=spy_stato,
            qqq_stato=qqq_stato,
            pattern_alerts=pat_alerts_h,
            radar_rows=radar_ig_h,
            palantir_cands=palantir_h,
            liq_libera=liq_libera_h,
        )
        if _esiti_prio:
            _righe_pr = "".join(
                f"<div style='color:#F8FAFC; font-size:0.91rem; line-height:1.55; margin-bottom:5px;'>{e['testo']}</div>"
                for e in _esiti_prio
            )
            blocco_prio_html = (
                f"<div style='height:1px; background:#2A2E39; margin:1.05rem 0;'></div>"
                f"<div style='font-size:0.80rem; font-weight:700; color:#CBD5E1; text-transform:uppercase; "
                f"letter-spacing:0.05em; margin-bottom:0.40rem;'>📌 Valutazione Titoli Prioritari (Sidebar)</div>"
                f"{_righe_pr}"
            )

    # Calcola gli avvisi di Protezione Profitto pendenti (solo quote Spot, mai PAC) ed evita conflitti con Switch al 100%
    _tickers_switch_100 = {
        str(b.get("ticker") or "").strip().upper()
        for b in bivi_home_oggi
        if "SWITCH" in str(b.get("motivo") or "").upper() and int(b.get("pct_vendita") or 0) >= 100
    }
    _tickers_raccolto_parz = {
        str(b.get("ticker") or "").strip().upper()
        for b in bivi_home_oggi
        if ("PROFITTO" in str(b.get("motivo") or "").upper()) or (0 < int(b.get("pct_vendita") or 100) < 100)
    }
    avvisi_protezione_home = []
    try:
        if "regia_tracker" in globals() and hasattr(regia_tracker, "ottieni_avvisi_protezione_pendenti"):
            _raw_prot = regia_tracker.ottieni_avvisi_protezione_pendenti(port_h) or []
            avvisi_protezione_home = [
                av for av in _raw_prot
                if str(av.get("ticker") or "").strip().upper() not in _tickers_switch_100
            ]
    except Exception:
        avvisi_protezione_home = []

    if avvisi_protezione_home:
        _tks_prot_lbl = ", ".join(av["ticker"] for av in avvisi_protezione_home)
        blocco_port_html += (
            f"<div style='color:#E0F2FE; font-size:0.92rem; line-height:1.5; margin-top:6px; "
            f"background:#0F2436; border-left:3px solid #38BDF8; padding:6px 10px; border-radius:6px;'>"
            f"🛡️ <b>PROTEZIONE PROFITTO ATTIVA ({_tks_prot_lbl}):</b> segui la guida rapida su Trade Republic "
            f"nel riquadro azzurro qui sotto e conferma quando hai inserito lo Stop Loss.</div>"
        )

    bordo_box_oggi = "#EF4444" if vendite_azioni else ("#F59E0B" if monitora_recupero else "#10B981")
    # Costruzione HTML priva di qualsiasi indentazione iniziale (>= 4 spazi) per impedire a Markdown di renderizzare blocchi <code>
    _card_oggi_html = "".join([
        f"<div style='background:#131722; border:1px solid #334155; border-left:5px solid {bordo_box_oggi}; "
        f"border-radius:12px; padding:1.35rem 1.5rem; margin-bottom:1.1rem;'>",
        "<div style='font-size:1.22rem; font-weight:800; color:#F8FAFC; margin-bottom:0.95rem; letter-spacing:0.01em;'>🧭 COSA DEVO FARE OGGI</div>",
        "<div style='font-size:0.80rem; font-weight:700; color:#CBD5E1; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:0.40rem;'>📌 Sul Portafoglio Attuale</div>",
        blocco_port_html.strip(),
        "<div style='height:1px; background:#2A2E39; margin:1.05rem 0;'></div>",
        "<div style='font-size:0.80rem; font-weight:700; color:#CBD5E1; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:0.40rem;'>🎯 Sui Nuovi Acquisti (Top 1 Unico)</div>",
        blocco_acq_html.strip(),
        blocco_dca_html.strip(),
        blocco_prio_html.strip(),
        "</div>",
    ])
    st.markdown(_card_oggi_html, unsafe_allow_html=True)

    # Card azzurra guidata "Protezione Profitto" (solo quote Spot, linguaggio semplice passo-passo per Trade Republic)
    if avvisi_protezione_home:
        for idx_pr, av_p in enumerate(avvisi_protezione_home):
            tk_p = av_p["ticker"]
            pnl_s = f"{float(av_p.get('pnl_pct') or 0.0):+.1f}%".replace(".", ",")
            sl_f = float(av_p.get("sl_eur") or 0.0)
            pmc_f = float(av_p.get("pmc_eur") or 0.0)
            pr_f = float(av_p.get("prezzo_eur") or 0.0)
            mx_f = float(av_p.get("max_eur") or 0.0)
            sl_s = "€ ••••" if nascondi_eur else f"€ {sl_f:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
            max_s = "€ ••••" if nascondi_eur else f"€ {mx_f:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
            prezzo_s = "€ ••••" if nascondi_eur else f"€ {pr_f:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
            pmc_s = "€ ••••" if nascondi_eur else f"€ {pmc_f:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

            dist_att_f = av_p.get("dist_da_attuale_pct")
            if dist_att_f is None and pr_f > 0:
                dist_att_f = round(((sl_f / pr_f) - 1.0) * 100.0, 1)
            dist_att_s = f"{float(dist_att_f or 0.0):+.1f}%".replace(".", ",")

            gain_bl_f = av_p.get("gain_blindato_pct")
            if gain_bl_f is None and pmc_f > 0:
                gain_bl_f = round(((sl_f / pmc_f) - 1.0) * 100.0, 1)
            gain_bl_s = f"{float(gain_bl_f or 0.0):+.1f}%".replace(".", ",")

            if av_p.get("is_misto_pac_spot"):
                q_sp_raw = float(av_p.get("qta_spot") or 0.0)
                q_sp_lbl = f"{int(q_sp_raw)}" if abs(q_sp_raw - round(q_sp_raw)) < 1e-4 else f"{q_sp_raw:.2f}".replace(".", ",")
                nota_misto_p = f" sulle sole <b>{q_sp_lbl} azioni Spot</b> (lascia intatto il tuo PAC)"
            else:
                nota_misto_p = ""
            nota_racc_p = (
                " — <i>se consolidi il 50% (o scegli di tenere il titolo), applica questa protezione alla quota Spot che lasci correre</i>"
                if tk_p in _tickers_raccolto_parz else ""
            )

            if av_p.get("tipo_protezione") == "TRAILING":
                mot_gr_p = str(av_p.get("motivo_grafico") or "-6% dal massimo, calibrato sulla volatilità del titolo")
                tit_prot = f"🏆 PROTEGGI IL PROFITTO ACCUMULATO — {tk_p} ({pnl_s}, massimo {max_s}): alziamo la rete di sicurezza calibrata sul grafico del titolo."
                corpo_prot = (
                    f"👉 <b>Cosa fare su Trade Republic (30 secondi):</b> Apri <b>{tk_p}</b> → <b>Vendi</b> → "
                    f"<b>Ordine Stop</b> → sposta il prezzo di protezione a <b>{sl_s}</b> ({mot_gr_p}){nota_misto_p}{nota_racc_p}. "
                    f"Così lasci respirare il trend e la maggior parte del guadagno resta al sicuro!"
                )
                impatto_prot = (
                    f"📊 <b>Se scatta lo Stop:</b> <b>{dist_att_s}</b> rispetto al prezzo attuale ({prezzo_s}) → "
                    f"blindato un guadagno di <b style='color:#4ADE80;'>{gain_bl_s}</b> sul tuo prezzo di carico ({pmc_s})."
                )
            else:
                tit_prot = f"🛡️ METTI AL SICURO IL GUADAGNO — {tk_p} ({pnl_s}): ora possiamo azzerare il rischio di perdita."
                corpo_prot = (
                    f"👉 <b>Cosa fare su Trade Republic (30 secondi):</b> Apri <b>{tk_p}</b> → <b>Vendi</b> → "
                    f"<b>Ordine Stop</b> → imposta il prezzo a <b>{sl_s}</b> (il tuo prezzo di carico){nota_misto_p}{nota_racc_p}. "
                    f"Così se scende esci senza perdere un euro; se sale, lasci correre il guadagno!"
                )
                impatto_prot = (
                    f"📊 <b>Se scatta lo Stop:</b> <b>{dist_att_s}</b> rispetto al prezzo attuale ({prezzo_s}) → "
                    f"chiudi comunque a <b style='color:#4ADE80;'>0,0% (pareggio)</b> sul tuo prezzo di carico."
                )

            nota_notifica_prot = (
                "📲 Una volta inserito, <b>Trade Republic</b> ti avviserà subito se lo Stop scatta; "
                "<b>MATRIX</b> (e Telegram) ti avviseranno quando converrà alzare ancora la protezione o registrare la vendita."
            )
            _card_prot_html = "".join([
                "<div style='background:#0F2436; border:1px solid #38BDF8; border-left:5px solid #38BDF8; ",
                "border-radius:12px; padding:1.05rem 1.25rem; margin-bottom:0.45rem; color:#E0F2FE;'>",
                f"<div style='font-size:0.97rem; font-weight:800; color:#F8FAFC; line-height:1.45; margin-bottom:0.40rem;'>{tit_prot}</div>",
                f"<div style='font-size:0.92rem; color:#E0F2FE; line-height:1.55; margin-bottom:0.38rem;'>{corpo_prot}</div>",
                f"<div style='font-size:0.89rem; color:#BAE6FD; line-height:1.45; padding-top:0.32rem; border-top:1px solid rgba(56,189,248,0.25);'>{impatto_prot}</div>",
                f"<div style='font-size:0.84rem; color:#CBD5E1; line-height:1.42; margin-top:0.30rem;'>{nota_notifica_prot}</div>",
                "</div>",
            ])
            st.markdown(_card_prot_html, unsafe_allow_html=True)

            lbl_btn_sl = (
                "✅ Fatto, Stop Loss inserito su Trade Republic"
                if len(avvisi_protezione_home) == 1
                else f"✅ Fatto, Stop Loss su {tk_p} inserito su Trade Republic"
            )
            if st.button(lbl_btn_sl, key=f"btn_home_conferma_sl_{idx_pr}_{tk_p}", type="primary", use_container_width=True):
                if "regia_tracker" in globals() and hasattr(regia_tracker, "conferma_avviso_sl"):
                    regia_tracker.conferma_avviso_sl(tk_p, av_p.get("sl_eur"))
                st.toast(f"✅ Stop Loss confermato su {tk_p} ({sl_s}): avviso archiviato in Home e nel Tracker!", icon="🛡️")
                st.rerun()
            st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

    # Pulsanti rapidi Bivio "Tengo io vs Vende il Sistema" per proposte Vendita / Take Profit / Switch della Home
    if bivi_home_oggi and "regia_tracker" in globals() and hasattr(regia_tracker, "registra_bivio_tengo_vs_sistema"):
        st.caption("⚖️ **Vuoi ignorare una proposta di vendita/alleggerimento e tenere il titolo?** Registrala qui per confrontare nel tempo *Tengo io* vs *Vende il Sistema*:")
        cols_bv = st.columns(min(3, len(bivi_home_oggi)))
        for idx_bv, bv in enumerate(bivi_home_oggi):
            col_bv = cols_bv[idx_bv % len(cols_bv)]
            gia_reg_bv = False
            try:
                if hasattr(regia_tracker, "is_bivio_registrato_oggi"):
                    gia_reg_bv = bool(regia_tracker.is_bivio_registrato_oggi(bv["ticker"], bv["motivo"]))
            except Exception:
                gia_reg_bv = False
            with col_bv:
                if gia_reg_bv:
                    st.markdown(
                        f"<div style='background:#0F2436; border:1px solid #38BDF8; border-radius:8px; "
                        f"padding:0.48rem 0.70rem; color:#E0F2FE; font-size:0.82rem; font-weight:700; text-align:center;'>"
                        f"✅ {bv['ticker']}: Bivio Tengo vs Sistema registrato</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    btn_lbl = f"⏭️ Tengo {bv['ticker']} / Ignora ({bv['label']})"
                    if st.button(
                        btn_lbl,
                        key=f"btn_home_bivio_{idx_bv}_{bv['ticker']}",
                        use_container_width=True,
                        help=f"Congela la vendita virtuale del Sistema a € {bv['prezzo_eur']:.2f} e lascia aperto il tuo Portafoglio Reale per il confronto nel Tracker.",
                    ):
                        regia_tracker.registra_bivio_tengo_vs_sistema(
                            ticker=bv["ticker"],
                            prezzo_attuale_eur=bv["prezzo_eur"],
                            portafoglio=port_h,
                            motivo=bv["motivo"],
                            pct_vendita=bv["pct_vendita"],
                            eurusd_rate=eurusd_live,
                        )
                        st.toast(f"⚖️ Bivio registrato su {bv['ticker']}: Sistema congelato a € {bv['prezzo_eur']:.2f} vs Tengo io!", icon="⚖️")
                        st.rerun()

    # 3b) Box periodico: "Il Punto della Settimana / Fine Mese & Radar Rotazione Balene"
    _render_box_punto_periodico_home(port_h)

    # 4) Tabella Salute Portafoglio richiudibile con ordine colonne compatto:
    # [Ticker | Oggi % | P&L % | S-Score | Insider SEC (90gg) | SMA 200 | Fase Weinstein | WinRate 60gg | Tipo]
    if port_h and salute_map:
        with st.expander(
            "📊 Tabella Salute Portafoglio (Oggi % • P&L • S-Score • Insider SEC • SMA 200 • Fase)",
            expanded=bool(st.session_state.get("home_tabella_salute_aperta", False)),
        ):
            c_sal_l, c_sal_m, c_sal_r = st.columns([2.0, 1.05, 0.95])
            with c_sal_l:
                st.caption(f"🕒 Quotazioni aggiornate: **{_agg_ora_h}** — aggiorna in ~1 secondo durante Wall Street (15:30–22:00).")
            with c_sal_m:
                if st.button("🔄 Aggiorna Prezzi Live", key="btn_home_aggiorna_prezzi_live", use_container_width=True):
                    # Mantiene aperta la Tabella Salute anche se sopra compaiono nuovi avvisi dopo il refresh live
                    st.session_state["home_tabella_salute_aperta"] = True
                    with st.spinner("Aggiorno quotazioni live..."):
                        _, _, n_live = _aggiorna_solo_prezzi_live_portafoglio(
                            port_h, eurusd_live, salute_map=salute_map, chiave_u=chiave_u
                        )
                    if n_live > 0:
                        st.toast(f"⚡ Prezzi live aggiornati su {n_live} titoli!", icon="🔄")
                    else:
                        st.toast("⚠️ Impossibile scaricare quotazioni live al momento.", icon="⚠️")
                    st.rerun()
            with c_sal_r:
                if st.button("🔍 Vista Grande", key="btn_home_vista_grande_salute", use_container_width=True):
                    st.session_state["home_tabella_salute_aperta"] = True
                    st.session_state["vista_attiva"] = "tabella_salute_full"
                    st.rerun()

            righe_sal = _costruisci_righe_tabella_salute(port_h, salute_map)
            st.dataframe(pd.DataFrame(righe_sal), use_container_width=True, hide_index=True)

    # 5) Pulsante ben visibile in fondo alla Home Page per passare al Terminale Completo
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    if st.button(
        "🔬 Passa al Terminale Completo (Analisi Tecnica, Grafici, Portafoglio & Simulatore)",
        type="secondary",
        use_container_width=True,
        key="btn_vai_terminale_completo_bottom",
    ):
        st.session_state["vista_attiva"] = "terminale"
        st.rerun()

# ==============================================================================
# INTERFACCIA PRINCIPALE - ROUTING HOME PILOTA AUTOMATICO VS TERMINALE COMPLETO
# ==============================================================================
semaforo_header = calcola_semaforo_mercato()
_fp_impostazioni = _get_impostazioni_path()
_imp_caricate = carica_json(IMPOSTAZIONI_FILE, default={})
if isinstance(_imp_caricate, dict) and _imp_caricate:
    impostazioni = _imp_caricate
else:
    impostazioni = {"lista_ticker_default": "ADBE, RKLB, SOUN, IONQ, ASTS, PLTR, ZETA, NKE, AMD, CRWD, NU, NVDA, TSLA, MCD, DIS, SBUX, PEP, INTC, SOFI, NBIS, VRT, ANET", "catalizzatori": "", "esclusioni": ""}

if "vista_attiva" not in st.session_state:
    st.session_state["vista_attiva"] = "home"

if st.session_state.get("vista_attiva", "home") == "home":
    # Sidebar essenziale in modalità Home Semplificata (con campo Priorità sincronizzato)
    if st.sidebar.button("🔬 Passa al Terminale Completo", type="primary", use_container_width=True, key="btn_vai_terminale_sidebar"):
        st.session_state["vista_attiva"] = "terminale"
        st.rerun()
    st.sidebar.markdown("---")
    st.sidebar.text_input(
        "📌 Titoli da Acquistare (Priorità)",
        placeholder="es. PLTR, RKLB",
        key="titoli_priorita_input",
        help="Valutati automaticamente nella Home Page con Super-Score, 3 Scudi e Piano A/B.",
    )
    render_box_account_sidebar()
    render_home_pilota_automatico(impostazioni, semaforo_header)
    st.stop()
elif st.session_state.get("vista_attiva") == "tabella_salute_full":
    render_vista_tabella_salute_fullscreen(impostazioni)
    st.stop()

# ==============================================================================
# INTERFACCIA PRINCIPALE - TOP BAR TERMINALE COMPLETO
# ==============================================================================
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
# Banner automatico festività / chiusure anticipate Borsa USA (NYSE / Nasdaq)
render_banner_calendario_borsa_usa()
# Termometro Macro SPY Drawdown 52 settimane (Tom Nash)
render_banner_termometro_tom_nash(semaforo_header)

if st.sidebar.button("🏠 Torna alla Home Semplificata", use_container_width=True, key="btn_torna_home_sidebar"):
    st.session_state["vista_attiva"] = "home"
    st.rerun()
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
st.sidebar.subheader("🚫 Esclusioni Switch")
esclusioni_input = st.sidebar.text_area(
    "Titoli esclusi dal Piano B Switch (virgola):",
    value=impostazioni.get("esclusioni", ""),
    height=65,
    key="esclusioni_switch_input",
)

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
    esegui_scansione_completa_motore(
        impostazioni=impostazioni,
        tickers_input=tickers_input,
        catalizzatori_input=catalizzatori_input,
        esclusioni_input=esclusioni_input,
        period=period,
        sma_short=sma_short,
        sma_long=sma_long,
        eurusd_rate=eurusd_rate,
        ignore_fase_4=ignore_fase_4,
        semaforo_header=semaforo_header,
        salva_impostazioni=True,
        progress_bar=None,
        mostra_info_avvio=True,
    )
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
    "Portfolio AI", "🕵️ Insider & Stagionalità", "🩺 Check 4 Regole"])

with tab_riepilogo:
    st.subheader("🧭 Riepilogo Operativo Unificato (Allineato al Pilota Automatico)")
    st.caption("Stesso verdetto della Home Page Pilota Automatico (3 Scudi, Tom Nash, Protezione PAC, Piano B Qualitativo & Cooldown 21gg) + Bacheche tecniche complete.")

    col_r_btn1, col_r_btn2 = st.columns(2)
    with col_r_btn1:
        if st.button("🔄 Aggiorna Quotazioni Portafoglio", type="secondary", key="riep_upd_port"):
            with st.spinner("🔄 Aggiornamento quotazioni in corso..."):
                st.session_state.portafoglio = aggiorna_quotazioni_portafoglio(st.session_state.portafoglio, eurusd_rate)
                st.session_state.last_update = _now_italia().strftime("%H:%M:%S")
                salva_ultimo_agg_prezzi()
            st.rerun()
    with col_r_btn2:
        st.info("💡 Per aggiornare segnali e bacheche, usa **🚀 AVVIA SCANSIONE** nella barra a sinistra.")

    # Verdetto sintetico sincronizzato con la Home Page Pilota Automatico (zero contraddizioni)
    stats_riep = st.session_state.dashboard_stats
    port_riep = st.session_state.portafoglio or list()
    by_fabio_list = stats_riep.get('by_fabio_tickers', list()) if stats_riep else list()
    by_std_list = [t for t in (stats_riep.get('by_tickers', list()) if stats_riep else list()) if t not in by_fabio_list]
    tp_list = st.session_state.get('take_profit_alerts', list()) or list()
    ign_list = (st.session_state.get('dashboard_stats') or {}).get('ignition_oggi', [])

    _snap_r = st.session_state.get("home_snapshot_decisionale") or {}
    _salute_r = st.session_state.get("home_salute_portafoglio") or {}
    _liq_r = round(max(0.0, float(calcola_liquidita_totale() or 0.0)), 2)
    _spy_st_r = str((semaforo_header or {}).get("stato", "giallo")).upper()
    _top1_r = _snap_r.get("top1_cand")
    _veto_r = _snap_r.get("veto_regime_msg")
    _dca_r = _snap_r.get("dca_cand") or _snap_r.get("dca_piano_b")
    _cd21_r = _get_tickers_cooldown_vendite(21)

    _scudi_tn_r = []
    for _pr in port_riep:
        _tk_r = str(_pr.get("Ticker", "")).strip().upper()
        _is_r = _salute_r.get(_tk_r) or {}
        _pnl_r = float(_is_r.get("pnl_pct", _pr.get("PnL_%", 0)) or 0)
        if _pnl_r <= -5.0 and _is_r.get("scudo_tom_nash"):
            _scudi_tn_r.append(f"🛡️ **{_tk_r} ({_pnl_r:+.1f}%)**: {_is_r.get('scudo_tom_nash_nota', 'azienda sana')} — non vendere sullo schermo rosso")

    if _veto_r:
        _sintesi_buy_r = f"🛡️ **Nuovi Acquisti:** {_veto_r}"
    elif _top1_r:
        _simb_r = "$" if _top1_r.get("currency", "USD") == "USD" else "€"
        if _liq_r >= 40.0:
            _sintesi_buy_r = f"🚀 **Top 1 Pronto (Piano A — Cassa € {_liq_r:,.2f}):** **{_top1_r['ticker']}** (Super-Score {_top1_r['super_score']}/100, R/R 1:{_top1_r['rr']:.2f}, max {_simb_r}{_top1_r['max_entry']:.2f})."
        else:
            _ris_r = _trova_riserva_liquidita_intelligente(port_riep, _salute_r, target_score=int(_top1_r.get("super_score", 0)), modalita="BUY", liq_libera=_liq_r)
            if _ris_r:
                _sintesi_buy_r = f"🔄 **Piano B (Switch Qualitativo):** libera {_ris_r['pct_vendita']}% di **{_ris_r['ticker']}** (~€ {_ris_r['netto_eur']:,.2f} netti) → compra **{_top1_r['ticker']}** (Super-Score {_top1_r['super_score']}/100)."
            else:
                _sintesi_buy_r = f"🛡️ **Portafoglio Intatto (Cassa € {_liq_r:,.2f}):** nessun titolo da vendere (tutti solidi o in PAC). Opportunità **{_top1_r['ticker']}** (Super-Score {_top1_r['super_score']}/100) solo con nuova liquidità dedicata."
    else:
        _sintesi_buy_r = f"⏳ **Nuovi Acquisti:** nessun Top 1 confermato oggi (Cassa reale: € {_liq_r:,.2f} • Regime SPY: {_spy_st_r})."

    _sintesi_dca_r = (
        f"🧮 **DCA Consigliato:** **{_dca_r['ticker']} ({_dca_r['pnl_pct']:+.1f}%)** — {_dca_r['motivo']} (rimbalzo pareggio +{_dca_r['rimb_prima']:.1f}% → +{_dca_r['rimb_dopo']:.1f}%)."
        if isinstance(_dca_r, dict) else "🧮 **DCA:** nessun candidato attivo oggi."
    )
    _nota_cd_r = f" • 🚫 Cooldown 21gg: {', '.join(_cd21_r.keys())}" if _cd21_r else ""

    st.markdown(
        f"<div style='background:#131722; border:1px solid #334155; border-left:5px solid #10B981; "
        f"border-radius:10px; padding:1rem 1.25rem; margin-bottom:0.9rem; color:#F8FAFC; font-size:0.93rem; line-height:1.6;'>"
        f"<div style='font-weight:800; font-size:1.05rem; margin-bottom:6px;'>🧭 Verdetto Unificato (Sincronizzato con Home Page Pilota Automatico)</div>"
        f"<div>{_sintesi_buy_r}</div>"
        f"<div style='margin-top:4px;'>{_sintesi_dca_r}</div>"
        + ("".join([f"<div style='margin-top:5px; color:#E0F2FE;'>{s}</div>" for s in _scudi_tn_r]))
        + f"<div style='margin-top:6px; color:#CBD5E1; font-size:0.82rem;'>Regime SPY: <b>{_spy_st_r}</b> • Liquidità reale: <b>€ {_liq_r:,.2f}</b>{_nota_cd_r}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

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
        st.caption(f"Taglia per singolo ordine: **€ {_taglia_ok:,.2f}** | Allocazione automatica allineata a Tom Nash, protezione PAC & Cooldown 21gg:")
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
                    _parz = " + ".join(_fn_i) if _fn_i else "Portafoglio intatto (nessun titolo da vendere)"
                    st.warning(f"🛡️ **Risorse insufficienti:** {_parz}. **Mancano € {_cp_i:,.2f}**: versa nuova liquidità dedicata oppure resta fermo.")
    else:
        st.info("Nessun segnale BUY supera oggi i filtri di qualità (potenziale ≥ +10%, regola mediazione e Cooldown 21gg).")
    if _scart_ok:
        with st.expander("🚫 Segnali BUY scartati dai filtri di qualità / Cooldown 21gg"):
            for _sm in _scart_ok:
                st.markdown(f"- {_sm}")

    import importlib; importlib.reload(regia_tracker)
    regia_tracker.render_tracker_regia(_piano_ok, _port_ok, eurusd_rate, _taglia_ok)

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
                            st.plotly_chart(fig_c, use_container_width=True, config={"scrollZoom": True, "displaylogo": False, "responsive": True, "displayModeBar": False}, key=f"chart_conf_{t_curr}_{idx_c}_{j}")
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
            new_tipo_ui = st.selectbox("Tipo Acquisto", OPZIONI_TIPO_ACQUISTO_UI, key="sel_new_tp_port")
            new_tipo = _normalizza_tipo_operazione(new_tipo_ui)
        with col_add3:
            new_qta = st.number_input("Quantità", min_value=0.0001, step=0.0001, format="%.6f", key="num_new_qta_port")
        with col_add4:
            new_medio = st.number_input("Prezzo Medio €", min_value=0.01, step=0.01, key="num_new_pmc_port")
        _comm_def_port = _commissione_default_tr("ACQUISTO", new_tipo)
        _costo_stima_port = round((float(new_qta or 0) * float(new_medio or 0)) + _comm_def_port, 2)
        _cassa_disp_port = round(max(0.0, float(calcola_liquidita_totale() or 0.0)), 2)
        _fonte_def_port, _qc_def_port, _qn_def_port = _calcola_default_fonte_fondi(_costo_stima_port, tipo_acq=new_tipo, cassa_disp=_cassa_disp_port)
        _chiave_firma_ff_port = f"{new_tipo}|{_costo_stima_port:.2f}|{_cassa_disp_port:.2f}"
        if st.session_state.get("_last_ff_sig_port") != _chiave_firma_ff_port:
            st.session_state["_last_ff_sig_port"] = _chiave_firma_ff_port
            st.session_state["sel_fonte_fondi_port"] = _fonte_def_port
        if "sel_fonte_fondi_port" not in st.session_state or st.session_state["sel_fonte_fondi_port"] not in OPZIONI_FONTE_FONDI:
            st.session_state["sel_fonte_fondi_port"] = _fonte_def_port
        c_ff1, c_ff2 = st.columns([1.4, 1.6])
        with c_ff1:
            fonte_fondi_port = st.selectbox(
                "💳 Fonte Fondi (auto-rilevata, modificabile)",
                OPZIONI_FONTE_FONDI,
                key="sel_fonte_fondi_port",
            )
            _qc_port, _qn_port = _calcola_quote_fonte_fondi(fonte_fondi_port, _costo_stima_port, cassa_disp=_cassa_disp_port)
        with c_ff2:
            # Rilevamento automatico del motivo/segnale attivo appena cambia il ticker digitato
            _tk_hint_port = str(new_ticker).strip().upper()
            if st.session_state.get("_last_tk_motivo_port") != _tk_hint_port:
                st.session_state["_last_tk_motivo_port"] = _tk_hint_port
                st.session_state["sel_motivo_acq_port"] = _rileva_motivo_segnale_ticker(_tk_hint_port, "ACQUISTO")
            if "sel_motivo_acq_port" not in st.session_state or st.session_state["sel_motivo_acq_port"] not in OPZIONI_MOTIVO_ACQUISTO:
                st.session_state["sel_motivo_acq_port"] = "Manuale / Discrezionale"
            new_motivo_acq = st.selectbox(
                "🎯 Motivo Segnale (rilevato automaticamente, modificabile)",
                OPZIONI_MOTIVO_ACQUISTO,
                key="sel_motivo_acq_port",
            )
        st.caption(
            f"💸 Comm. TR default: **€ {_comm_def_port:.2f}** ({'PAC gratuito' if new_tipo == 'PAC' else 'ordine Spot'}) • "
            f"Cassa disponibile: **€ {_cassa_disp_port:,.2f}** → Da cassa: **€ {_qc_port:,.2f}** | Nuova liquidità: **€ {_qn_port:,.2f}**"
        )
        if st.button("✅ Conferma Acquisto in Portafoglio", type="primary", key="btn_add_port_direct"):
            _tk_clean = str(new_ticker).strip().upper()
            if _tk_clean and float(new_qta) > 0 and float(new_medio) > 0:
                _trovato_m = False
                # Fonde sempre sul ticker esistente con PMC fiscale unico Trade Republic,
                # tracciando separatamente Quantita_PAC e Quantita_Spot
                for _item_m in st.session_state.portafoglio:
                    if str(_item_m.get("Ticker", "")).strip().upper() == _tk_clean:
                        _q_old = float(_item_m.get("Quantita", 0) or 0)
                        _pmc_old = float(_item_m.get("Prezzo_Medio", 0) or 0)
                        _q_new = round(_q_old + float(new_qta), 6)
                        _pmc_new = round(((_q_old * _pmc_old) + (float(new_qta) * float(new_medio))) / _q_new, 4)
                        _aggiorna_ripartizione_acquisto(_item_m, float(new_qta), new_tipo)
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
                        registra_acquisto_storico(
                            _tk_clean, new_tipo, float(new_qta), float(new_medio),
                            nota="Mediazione PMC", motivo_segnale=new_motivo_acq, commissione_eur=_comm_def_port,
                            fonte_fondi=fonte_fondi_port, quota_da_cassa=_qc_port, quota_nuova_liquidita=_qn_port,
                        )
                        break
                if not _trovato_m:
                    _q_n = round(float(new_qta), 6)
                    _pm_n = round(float(new_medio), 4)
                    st.session_state.portafoglio.append({
                        "Ticker": _tk_clean,
                        "Tipo": str(new_tipo),
                        "Quantita": _q_n,
                        "Quantita_PAC": _q_n if new_tipo == "PAC" else 0.0,
                        "Quantita_Spot": _q_n if new_tipo == "Spot" else 0.0,
                        "Prezzo_Medio": _pm_n,
                        "Valore_Carico": round(_q_n * _pm_n, 2),
                        "Prezzo_Attuale_EUR": _pm_n,
                        "Valore_Attuale": round(_q_n * _pm_n, 2),
                        "PnL_EUR": 0.0,
                        "PnL_%": 0.0,
                        "Fonte_Fondi": fonte_fondi_port,
                        "Data_Acquisto": _now_italia().strftime("%Y-%m-%d")
                    })
                    salva_ultimo_agg_prezzi()
                    salva_json(PORTAFOGLIO_FILE, st.session_state.portafoglio)
                    registra_acquisto_storico(
                        _tk_clean, new_tipo, _q_n, _pm_n,
                        nota="Nuovo Acquisto", motivo_segnale=new_motivo_acq, commissione_eur=_comm_def_port,
                        fonte_fondi=fonte_fondi_port, quota_da_cassa=_qc_port, quota_nuova_liquidita=_qn_port,
                    )
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
                    st.plotly_chart(fig_side, use_container_width=True, config={"scrollZoom": True, "displaylogo": False, "responsive": True, "displayModeBar": False}, key=f"port_side_live_chart_{sel_t}")
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
                        stato_pac = _stato_pac_manuale(pos)
                        pill_bg = "#089981" if (var_pct is not None and not math.isnan(var_pct) and var_pct > 0) else ("#F23645" if (var_pct is not None and not math.isnan(var_pct) and var_pct < 0) else "#363A45")
                        pill_txt = f"{var_symbol} {var_pct:+.2f}%" if (var_pct is not None and not math.isnan(var_pct)) else "N/D"
                        _q_pac_c, _q_spot_c = _calcola_ripartizione_pac_spot(pos)
                        _badge_tipo_c = _formatta_badge_tipo_posizione(pos, con_dettaglio=False)
                        _ripart_html_c = (
                            f"<br><span style='color:#38BDF8;font-weight:700;'>🔀 PAC + Spot: {_q_pac_c:.2f} PAC + {_q_spot_c:.2f} Spot</span>"
                            if (_q_pac_c > 1e-6 and _q_spot_c > 1e-6) else ""
                        )
                        st.markdown(f"""<div style="background-color:#131722;border:1px solid #2A2E39;border-radius:8px;padding:0.85rem 1rem;margin-bottom:0.45rem;border-left:4px solid {border_color};"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.2rem;"><div><span style="font-size:1.35rem;color:#FFFFFF;font-weight:700;">{ticker}</span>{by_fabio_indicator}</div><span style="background-color:{pill_bg};color:#FFFFFF;font-family:'JetBrains Mono',monospace;font-size:0.82rem;font-weight:700;padding:3px 9px;border-radius:5px;">{pill_txt}</span></div><div style="font-size:0.78rem;color:#787B86;margin-bottom:0.55rem;border-bottom:1px solid #1E222D;padding-bottom:0.4rem;">{stato_pac} ({_badge_tipo_c}) &nbsp;•&nbsp; PMC €{prezzo_medio:.2f}<br><span style='color:#D1D4DC;font-weight:600;'>In carico: {quantita:.4f} az. &nbsp;•&nbsp; Valore €{(pos.get('Valore_Attuale') or (prezzo_medio * quantita)):.2f}</span>{_ripart_html_c}</div><div style="display:flex;justify-content:space-between;font-size:0.84rem;margin-bottom:0.22rem;"><span style="color:#787B86;">Prezzo Attuale</span><span style="font-family:'JetBrains Mono',monospace;color:#FFFFFF;font-weight:700;font-size:0.96rem;">€ {prezzo_display}</span></div><div style="display:flex;justify-content:space-between;font-size:0.84rem;margin-bottom:0.22rem;"><span style="color:#787B86;">P&L Totale</span><span style="font-family:'JetBrains Mono',monospace;color:{acqu_color};font-weight:600;">{acqu_symbol} {var_acquisto:+.1f}% | {netto_label}</span></div><div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:0.22rem;"><span style="color:#787B86;">Ultimo Segnale</span><span style="color:#D1D4DC;">{ultimo_segnale}</span></div><div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:0.4rem;"><span style="color:#787B86;">Trend</span><span style="color:#D1D4DC;">{trend}</span></div><div style="display:flex;justify-content:space-between;align-items:center;border-top:1px solid #1E222D;padding-top:0.4rem;font-size:0.78rem;"><span style="color:#787B86;">Target</span><div>{dots_display}</div></div></div>""", unsafe_allow_html=True)
                        # Controllo 100% manuale dello stato PAC (Attivo / Sospeso — Long) per posizioni con quote PAC
                        if _q_pac_c > 1e-6:
                            _pac_is_sosp = bool(pos.get("PAC_Sospeso", False))
                            _lbl_btn_pac = "▶️ Riattiva PAC" if _pac_is_sosp else "⏸️ Sospendi PAC"
                            if st.button(_lbl_btn_pac, key=f"toggle_pac_{ticker}_{idx_pos}", use_container_width=True):
                                pos["PAC_Sospeso"] = not _pac_is_sosp
                                pos["Stato_PAC"] = _stato_pac_manuale(pos)
                                st.session_state.portafoglio = portafoglio
                                salva_json(PORTAFOGLIO_FILE, portafoglio)
                                st.rerun()
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
                            st.markdown(f"<div style='background:#0B0E11;border:1px solid #2A2E39;border-radius:6px;padding:8px 10px;font-size:0.82rem;margin-bottom:6px;'><div style='display:flex;justify-content:space-between;'><span>Quantità: <b>{quantita:.4f}</b> ({_badge_tipo_c})</span><span>Prezzo: <b>€ {prezzo_display}</b></span></div><div style='display:flex;justify-content:space-between;margin-top:4px;'><span>P&L: <b style='color:{acqu_color};'>{netto_label}</b></span><span>Var: <b style='color:{acqu_color};'>{var_acquisto:+.1f}%</b></span></div></div>", unsafe_allow_html=True)
                            st.caption(f"📅 Prossimi Utili: {earnings}")
                            st.markdown("---")
                            st.markdown("**➕ Aggiungi Quote**")
                            col_a1, col_a2 = st.columns(2)
                            with col_a1:
                                nuova_qta = st.number_input("Nuova Qta", min_value=0.0001, step=0.0001, key=f"qta_{ticker}_{idx_pos}")
                            with col_a2:
                                nuovo_prezzo_acq = st.number_input("Prezzo Acquisto €", min_value=0.01, step=0.01, key=f"prezzo_acq_{ticker}_{idx_pos}")
                            # Default su Spot (tattico / segnale MATRIX); modificabile esplicitamente in PAC
                            tipo_acq_card_ui = st.selectbox("📂 Tipo Acquisto", OPZIONI_TIPO_ACQUISTO_UI, index=0, key=f"tp_acq_{ticker}_{idx_pos}")
                            tipo_acq_card = _normalizza_tipo_operazione(tipo_acq_card_ui)
                            _comm_card = _commissione_default_tr("ACQUISTO", tipo_acq_card)
                            _costo_card = round((float(nuova_qta or 0) * float(nuovo_prezzo_acq or 0)) + _comm_card, 2)
                            _cassa_card = round(max(0.0, float(calcola_liquidita_totale() or 0.0)), 2)
                            _ff_def_card, _, _ = _calcola_default_fonte_fondi(_costo_card, tipo_acq=tipo_acq_card, cassa_disp=_cassa_card)
                            _idx_ff_card = OPZIONI_FONTE_FONDI.index(_ff_def_card) if _ff_def_card in OPZIONI_FONTE_FONDI else 1
                            fonte_fondi_card = st.selectbox("💳 Fonte Fondi", OPZIONI_FONTE_FONDI, index=_idx_ff_card, key=f"ff_acq_{ticker}_{idx_pos}")
                            _qc_card, _qn_card = _calcola_quote_fonte_fondi(fonte_fondi_card, _costo_card, cassa_disp=_cassa_card)
                            st.caption(f"💸 Comm. TR: **€ {_comm_card:.2f}** • Da cassa: **€ {_qc_card:,.2f}** | Nuova liquidità: **€ {_qn_card:,.2f}**")
                            _mot_auto_acq = _rileva_motivo_segnale_ticker(ticker, "ACQUISTO")
                            _idx_mot_acq = OPZIONI_MOTIVO_ACQUISTO.index(_mot_auto_acq) if _mot_auto_acq in OPZIONI_MOTIVO_ACQUISTO else len(OPZIONI_MOTIVO_ACQUISTO) - 1
                            motivo_acq_card = st.selectbox("🎯 Motivo Segnale", OPZIONI_MOTIVO_ACQUISTO, index=_idx_mot_acq, key=f"mot_acq_{ticker}_{idx_pos}")
                            if st.button("✅ Conferma Aggiunta", key=f"add_{ticker}_{idx_pos}", use_container_width=True):
                                    if nuova_qta > 0 and nuovo_prezzo_acq > 0:
                                        vecchio_medio = pos['Prezzo_Medio']
                                        nuovo_medio = ((quantita * vecchio_medio) + (nuova_qta * nuovo_prezzo_acq)) / (quantita + nuova_qta)
                                        _aggiorna_ripartizione_acquisto(pos, nuova_qta, tipo_acq_card)
                                        pos['Quantita'] = round(quantita + nuova_qta, 6)
                                        pos['Prezzo_Medio'] = round(nuovo_medio, 4)
                                        pos['Valore_Carico'] = round(pos['Quantita'] * pos['Prezzo_Medio'], 2)
                                        salva_json(PORTAFOGLIO_FILE, portafoglio)
                                        st.session_state.portafoglio = portafoglio
                                        registra_acquisto_storico(
                                            ticker, tipo_acq_card, nuova_qta, nuovo_prezzo_acq,
                                            nota="Aggiunta Quote", motivo_segnale=motivo_acq_card, commissione_eur=_comm_card,
                                            fonte_fondi=fonte_fondi_card, quota_da_cassa=_qc_card, quota_nuova_liquidita=_qn_card,
                                        )
                                        st.success(f"✅ Aggiunte {nuova_qta} quote ({tipo_acq_card}) di {ticker}. Nuovo medio: €{nuovo_medio:.4f}")
                                        st.rerun()
                            st.markdown("---")
                            st.markdown("**➖ Vendi Quote**")
                            st.caption("💸 Commissione Trade Republic vendita: **€ 1.00** (applicata a tutte le vendite, incluse vendite/chiusure PAC)")
                            modalita_vendita = st.radio(f"Modalità vendita {ticker}", ["📊 Percentuale (%)", "🔢 Quantità specifica"], horizontal=True, key=f"modalita_{ticker}_{idx_pos}")
                            qta_da_vendere = 0
                            if modalita_vendita == "📊 Percentuale (%)":
                                pct_vendita = st.slider("Percentuale da vendere", min_value=1.0, max_value=100.0, value=100.0, step=1.0, key=f"pct_{ticker}_{idx_pos}")
                                qta_da_vendere = quantita * (pct_vendita / 100.0)
                                st.info(f"📊 Venderai {pct_vendita:.0f}% = {qta_da_vendere:.6f} quote")
                            else:
                                qta_da_vendere = st.number_input(f"Quantità da vendere (max {quantita:.6f})", min_value=0.0001, max_value=quantita, step=0.0001, value=min(quantita, 1.0), key=f"qta_vend_{ticker}_{idx_pos}")
                            prezzo_vendita = st.number_input("Prezzo di vendita €", min_value=0.01, step=0.01, value=float(prezzo_eur) if prezzo_eur else 0.01, key=f"prezzo_vend_{ticker}_{idx_pos}")
                            _mot_auto_vend = _rileva_motivo_segnale_ticker(ticker, "VENDITA")
                            _idx_mot_vend = OPZIONI_MOTIVO_VENDITA.index(_mot_auto_vend) if _mot_auto_vend in OPZIONI_MOTIVO_VENDITA else len(OPZIONI_MOTIVO_VENDITA) - 1
                            motivo_vend_card = st.selectbox("🎯 Motivo Segnale Vendita", OPZIONI_MOTIVO_VENDITA, index=_idx_mot_vend, key=f"mot_vend_{ticker}_{idx_pos}")
                            if qta_da_vendere > 0 and prezzo_vendita > 0 and prezzo_medio > 0:
                                pnl_lordo_prev = ((prezzo_vendita - prezzo_medio) * qta_da_vendere) - _commissione_default_tr("VENDITA")
                                pnl_pct_prev = ((prezzo_vendita / prezzo_medio) - 1) * 100
                                minusvalenze_disp = carica_json(MINUSVALENZE_FILE)
                                oggi_str = _now_italia().strftime("%Y-%m-%d")
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
                                        risultato = registra_vendita(ticker, qta_da_vendere, prezzo_medio, prezzo_vendita, motivo_segnale=motivo_vend_card)
                                        if risultato and 'regia_tracker' in globals() and hasattr(regia_tracker, 'salta_ticker_5gg'):
                                            regia_tracker.salta_ticker_5gg(ticker)
                                        if risultato:
                                            _aggiorna_ripartizione_vendita(pos, qta_da_vendere)
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
        st.markdown("#### 🧭 Console Unificata — Piano B Qualitativo, Simulatore Priorità & DCA")
        st.caption(
            "Collegata direttamente al motore della Home Page Pilota Automatico (cache Market Data Hub, Hold-Score, "
            "Scudo Tom Nash, protezione assoluta PAC e Cooldown Anti Ping-Pong 21 giorni). "
            "Per aggiungere, mediare o rimuovere titoli usa il punto unico nella tab **💼 Portafoglio**."
        )

        # Carica o aggiorna al volo salute_map dalla cache Hub (zero chiamate lente)
        salute_cons = st.session_state.get("home_salute_portafoglio") or {}
        if not salute_cons:
            with st.spinner("Caricamento metriche unificate dal Market Data Hub..."):
                salute_cons = _valuta_salute_portafoglio_home(portafoglio, eurusd_rate)
                st.session_state["home_salute_portafoglio"] = salute_cons

        liq_reale_cons = round(max(0.0, float(calcola_liquidita_totale() or 0.0)), 2)
        liq_sim_cons = round(liq_reale_cons + float(liq_aggiuntiva_sim or 0.0), 2)
        cooldown_cons = _get_tickers_cooldown_vendite(21)
        val_port_cons = sum(
            float(p.get("Quantita", 0) or 0) * float(p.get("Prezzo_Attuale_EUR") or p.get("Prezzo_Medio") or 0)
            for p in portafoglio
        ) + liq_reale_cons

        c_k1, c_k2, c_k3 = st.columns(3)
        c_k1.metric("💵 Liquidità Reale Conto", f"€ {liq_reale_cons:,.2f}", help="Saldo cassa reale Trade Republic (al netto delle sole Quote Da Cassa)")
        c_k2.metric("🏦 Disponibilità con Extra Sidebar", f"€ {liq_sim_cons:,.2f}", help="Liquidità reale + eventuale nuova liquidità digitata in sidebar")
        c_k3.metric("🚫 Titoli in Cooldown (21gg)", str(len(cooldown_cons)), ", ".join(cooldown_cons.keys()) if cooldown_cons else "Nessuno")

        st.markdown("---")
        # 1) Classifica Hold-Score & Eleggibilità Piano B Qualitativo del Portafoglio
        st.markdown("##### 📊 Classifica Hold-Score Portafoglio & Eleggibilità Switch (Piano B)")
        righe_hs = []
        for pos in portafoglio:
            tk = str(pos.get("Ticker", "")).strip().upper()
            if not tk:
                continue
            inf = salute_cons.get(tk) or {}
            hs = _calcola_hold_score_posizione(pos, inf)
            q_pac_p, q_spot_p = _calcola_ripartizione_pac_spot(pos)
            pnl_p = float(inf.get("pnl_pct", pos.get("PnL_%", 0)) or 0)
            rsi_v = float(inf.get("rsi", 50.0) or 50.0)
            s_sc = int(inf.get("s_score", 50) or 50)
            sec_b = int(inf.get("sec_buys") or 0)
            scudo_tn = bool(inf.get("scudo_tom_nash"))
            fase_s = str(inf.get("fase", "N/D"))
            if pnl_p >= 35.0 or (pnl_p >= 25.0 and rsi_v > 72.0):
                stato_sw = "💰 Fonte A (Raccolto 50%)"
            elif q_spot_p <= 1e-6:
                stato_sw = "🛡️ Protetto (Solo PAC)"
            elif scudo_tn:
                stato_sw = "🛡️ Protetto (Scudo Tom Nash)"
            elif sec_b > 0:
                stato_sw = f"🏛️ Protetto ({sec_b} acq SEC)"
            elif ("FASE 2" in fase_s.upper()) and (inf.get("sopra_sma50") is True) and s_sc >= 70:
                stato_sw = "🟢 Protetto (Fase 2 Forte)"
            elif -3.0 <= pnl_p <= 12.0:
                stato_sw = "🔄 Candidabile Fonte B (Solo Spot)"
            else:
                stato_sw = "⏸️ Hold / Monitora"
            righe_hs.append({
                "Ticker": tk,
                "Hold-Score": f"{hs}/100",
                "Tipo": _formatta_badge_tipo_posizione(pos, con_dettaglio=True),
                "P&L %": f"{pnl_p:+.1f}%",
                "S-Score": f"{s_sc}/100",
                "Fase Weinstein": fase_s,
                "Stato Piano B": stato_sw,
            })
        if righe_hs:
            st.dataframe(pd.DataFrame(righe_hs), use_container_width=True, hide_index=True)

        st.markdown("---")
        # 2) Simulatore Priorità & Verifica Setup (collegato a "📌 Titoli da Acquistare (Priorità)")
        st.markdown("##### 📌 Simulatore Priorità & Piano A / Piano B")
        c_pr1, c_pr2 = st.columns([2.4, 1.0])
        with c_pr1:
            prio_console_txt = st.text_input(
                "Ticker da valutare subito (pre-compilato dalla sidebar Priorità):",
                value=str(st.session_state.get("titoli_priorita_input") or ""),
                placeholder="es. PLTR, RKLB, NVDA",
                key="inp_prio_console_eval",
            )
        with c_pr2:
            st.markdown("<div style='height:26px;'></div>", unsafe_allow_html=True)
            btn_eval_prio = st.button("🔎 Valuta con Motore Unificato", type="primary", use_container_width=True, key="btn_eval_prio_console")

        if btn_eval_prio or prio_console_txt.strip():
            if prio_console_txt.strip():
                _, qqq_st_c, _ = _verifica_qqq_regime_verde()
                esiti_c = _valuta_titoli_priorita_home(
                    priorita_str=prio_console_txt,
                    portafoglio=portafoglio,
                    salute_map=salute_cons,
                    val_totale_port=val_port_cons,
                    eurusd_rate=eurusd_rate,
                    spy_stato=str((semaforo_header or {}).get("stato", "giallo")).lower(),
                    qqq_stato=qqq_st_c,
                    pattern_alerts=st.session_state.get("pattern_alerts") or {},
                    radar_rows=st.session_state.get("risultati_radar_ignition_80") or [],
                    palantir_cands=st.session_state.get("ai_palantir_candidati") or [],
                    liq_libera=liq_sim_cons,
                )
                for e_c in esiti_c:
                    b_col = "#10B981" if e_c.get("pronto") else "#38BDF8"
                    st.markdown(
                        f"<div style='background:#131722; border:1px solid #334155; border-left:4px solid {b_col}; "
                        f"border-radius:8px; padding:0.7rem 1rem; margin-bottom:0.5rem; color:#F8FAFC; font-size:0.92rem;'>"
                        f"{e_c['testo']}</div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.info("Inserisci uno o più ticker (separati da virgola) per valutarli con Super-Score, 3 Scudi e Piano A/B.")

        st.markdown("---")
        # 3) Stato DCA Doppio Binario coerente al 100% con la Home Page
        st.markdown("##### 🧮 Verifica DCA Doppio Binario (Coerente con Home Page)")
        pat_alerts_c = st.session_state.get("pattern_alerts") or {}
        dca_c = _calcola_dca_doppio_binario(
            portafoglio, salute_cons, pat_alerts_c, liq_sim_cons,
            ignora_soglia_cassa=(liq_sim_cons < 40.0), importo_ref_piano_b=200.0
        )
        if dca_c is not None:
            mult_c = f" • {dca_c['badge_multipli']}" if dca_c.get("badge_multipli") else ""
            nota_cassa_c = (
                f"su disponibilità € {liq_sim_cons:,.2f}"
                if liq_sim_cons >= 40.0
                else "simulato su € 200 di nuova liquidità (cassa reale € 0)"
            )
            st.success(
                f"💡 **{dca_c['ticker']} ({dca_c['pnl_pct']:+.1f}%)** — {dca_c['motivo']} "
                f"(S-Score {dca_c['s_score']}/100{mult_c}; {nota_cassa_c}): "
                f"PMC € {dca_c['pmc_old']:.2f} → € {dca_c['pmc_new']:.2f} | "
                f"Rimbalzo al pareggio +{dca_c['rimb_prima']:.1f}% → +{dca_c['rimb_dopo']:.1f}%."
            )
        else:
            st.info("⏸️ Nessun candidato DCA attivo oggi (nessun titolo sano soddisfa i filtri Binario 1/2, efficacia ≥ 6 pt e assenza Cooldown 21gg).")
        st.markdown("---")


with tab_scanner:
    if st.session_state.get('semaforo_mercato') is None:
        st.session_state.semaforo_mercato = calcola_semaforo_mercato()
    semaforo = st.session_state.semaforo_mercato
    _dd52 = semaforo.get("spy_drawdown_pct")
    _zona_tn_s = str(semaforo.get("zona_sconto_tom_nash") or "normale").upper()
    _dd52_txt = f" | SPY Drawdown 52w (Tom Nash): {float(_dd52):.1f}% [{_zona_tn_s}]" if _dd52 is not None else ""
    if semaforo['stato'] == 'verde':
        st.markdown(f'<div class="semaforo-box semaforo-verde"><h2 style="margin:0; color:white;">{semaforo["messaggio"]}</h2><p style="margin:0.5rem 0 0 0; color:#d1fae5;">SPY: ${semaforo["spy_prezzo"]} | SMA10: ${semaforo["spy_sma10"]} | VIX: {semaforo["vix"]}{_dd52_txt}</p></div>', unsafe_allow_html=True)
    elif semaforo['stato'] == 'rosso':
        st.markdown(f'<div class="semaforo-box semaforo-rosso"><h2 style="margin:0; color:white;">{semaforo["messaggio"]}</h2><p style="margin:0.5rem 0 0 0; color:#fee2e2;">SPY: ${semaforo["spy_prezzo"]} | SMA10: ${semaforo["spy_sma10"]} | VIX: {semaforo["vix"]}{_dd52_txt}</p></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="semaforo-box semaforo-giallo"><h2 style="margin:0; color:white;">{semaforo["messaggio"]}</h2><p style="margin:0.5rem 0 0 0; color:#fef3c7;">SPY: ${semaforo["spy_prezzo"]} | SMA10: ${semaforo["spy_sma10"]} | VIX: {semaforo["vix"]}{_dd52_txt}</p></div>', unsafe_allow_html=True)
    render_banner_termometro_tom_nash(semaforo)
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
            _pb_ig = st.progress(0, text="Scansione Radar IGNITION in corso...")
            esegui_radar_ignition_80(
                watchlist_str=st.session_state.get('tickers_input', ''),
                ohlc_map=None,
                progress_bar=_pb_ig,
            )
            _pb_ig.empty()
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
                if st.button("🩺 Check 4 Regole (Tecnica & Tom Nash)", key="btn_check_singola_3reg", use_container_width=True):
                    st.session_state["_run_check_singola"] = ticker_input.strip().upper()
            if st.session_state.get("_run_check_singola") == ticker_input.strip().upper():
                if 'regia_tracker' in globals() and hasattr(regia_tracker, 'render_check_3_regole'):
                    import importlib; importlib.reload(regia_tracker); regia_tracker.render_check_3_regole([ticker_input.strip().upper()], eurusd_rate, rileva_fase_fn=rileva_fase_weinstein, portafoglio=st.session_state.get("portafoglio"), tom_nash_fn=_valuta_fondamentali_tom_nash)
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
        _seg_coer_box, _att_sc_box, _mot_sc_box = _valuta_verdetto_coerente_scudi(r)
        if r.get('is_ipo_recente'):
            # Per le IPO recenti l'avviso esplicativo è già mostrato in testa alla scheda
            pass
        elif _att_sc_box:
            st.warning(f"**{_seg_coer_box}**: {_mot_sc_box} (Setup tecnico: {r.get('motivo_by', '')})")
        elif r.get('trigger_by_fabio'):
            st.success(f"**🟢 BY FABIO**: {r['motivo_by']}")
        elif "BY" in r['segnale']:
            st.success(f"**Motivo**: {r['motivo_by']}")
        elif "HOLD" in r['segnale']:
            st.warning(f"**Motivo**: {r['motivo_by']}")
        else:
            st.error("**Motivo**: Titolo in Fase 4 o S-Score troppo basso")

        # Box compatto Scudo Fondamentale Tom Nash & Stato PAC/Spot (se posseduto)
        _tk_an = str(r.get("ticker", "")).strip().upper()
        _tn_an = _valuta_fondamentali_tom_nash(_get_info_cached(_tk_an), s_score=r.get("s_score", 50))
        _pos_an = next((p for p in (st.session_state.get("portafoglio") or []) if str(p.get("Ticker", "")).strip().upper() == _tk_an), None)
        _stato_pos_an = ""
        if _pos_an:
            _st_pac_an = _stato_pac_manuale(_pos_an)
            _tp_det_an = _formatta_badge_tipo_posizione(_pos_an, con_dettaglio=True)
            _stato_pos_an = f" &nbsp;|&nbsp; 📂 In Portafoglio: <b>{_tp_det_an}</b> ({_st_pac_an})"
        _badge_m_an = f" &nbsp;|&nbsp; {_tn_an['badge_multipli']}" if _tn_an.get("badge_multipli") else ""
        _tn_lbl_an = (
            f"🛡️ <b>SCUDO TOM NASH ATTIVO</b> ({_tn_an['scudo_tom_nash_nota']})"
            if _tn_an.get("scudo_tom_nash")
            else f"ℹ️ <b>Fondamentali Tom Nash:</b> {_tn_an['scudo_tom_nash_nota']}"
        )
        st.markdown(
            f"<div style='background:#0F2436; border:1px solid #38BDF8; border-left:4px solid #38BDF8; "
            f"border-radius:8px; padding:0.65rem 1rem; margin:0.5rem 0; color:#E0F2FE; font-size:0.88rem;'>"
            f"{_tn_lbl_an}{_badge_m_an}{_stato_pos_an}</div>",
            unsafe_allow_html=True,
        )
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
            _salute_sim = st.session_state.get("home_salute_portafoglio") or {}
            _imp_req = float(sim_importo) if "sim_importo" in locals() else 200.0
            _tk_req = str(sim_ticker).upper().strip() if "sim_ticker" in locals() else "TITOLO"

            # Allineamento 100% con _trova_riserva_liquidita_intelligente(): somma Fonte A parziale + Fonte B (Delta >= +20 pt)
            _prof_sim = _calcola_profilo_target_simulazione(_tk_req, _port_src, eurusd_rate)
            _cands_ab_sim, _tot_vend_netto = _raccogli_candidati_switch_simulazione(
                portafoglio=_port_src,
                salute_map=_salute_sim,
                target_score=_prof_sim["target_score"],
                tk_target=_tk_req,
                liq_libera=_cassa_broker,
                esclusioni=_escl_set,
                catalizzatori_set=_cat_set,
            )
            _n_fa = sum(1 for c in _cands_ab_sim if c.get("codice_fonte") == "FONTE_A")
            _n_fb = sum(1 for c in _cands_ab_sim if c.get("codice_fonte") == "FONTE_B")
            if _n_fa > 0 and _n_fb > 0:
                _lbl_cands_ab = f"{len(_cands_ab_sim)} candidati ({_n_fa} Fonte A + {_n_fb} Fonte B)"
            else:
                _lbl_cands_ab = f"{len(_cands_ab_sim)} candidati Fonte A/B"

            _liq_extra = float(st.session_state.get("liq_aggiuntiva_sim", 0.0) or 0.0)
            _cassa_tot = round(_cassa_broker + _liq_extra, 2)
            _tot_disponibile = round(_cassa_tot + _tot_vend_netto, 2)
            _mancante = round(max(0.0, _imp_req - _tot_disponibile), 2)
            _c_r1, _c_r2, _c_r3 = st.columns(3)
            _c_r1.metric("💳 Cassa Broker + Extra", f"€ {_cassa_tot:,.2f}", f"Broker €{_cassa_broker:.2f} + Extra €{_liq_extra:.2f}")
            _c_r2.metric("🔄 Switch Qualitativi (Netto)", f"€ {_tot_vend_netto:,.2f}", _lbl_cands_ab)
            _c_r3.metric("🎯 Copertura Totale", f"€ {_tot_disponibile:,.2f}", "Pronto" if _mancante == 0 else f"Mancano € {_mancante:,.2f}", delta_color="normal" if _mancante == 0 else "inverse")
            # Mini-banner immediato del verdetto Pilota Automatico MATRIX già nella prima card
            if _prof_sim.get("approvato_matrix"):
                _bg_vm, _brd_vm, _fg_vm = "#0B2219", "#10B981", "#D1FAE5"
            else:
                _bg_vm, _brd_vm, _fg_vm = "#2A1F0D", "#F59E0B", "#FEF3C7"
            st.markdown(
                f"<div style='background:{_bg_vm}; border:1px solid {_brd_vm}; border-left:4px solid {_brd_vm}; "
                f"border-radius:8px; padding:0.55rem 0.90rem; margin:0.45rem 0 0.60rem 0; "
                f"color:{_fg_vm}; font-size:0.89rem; font-weight:700; line-height:1.4;'>"
                f"{_prof_sim['verdetto_matrix']}</div>",
                unsafe_allow_html=True,
            )
            if _mancante > 0:
                _nome_sim_u = PROFILO_ATTIVO.get("nome", "Utente")
                st.warning(f"🛡️ **{_nome_sim_u}, Portafoglio Intatto — per acquistare {_tk_req} da € {_imp_req:,.2f} mancano € {_mancante:,.2f}** (cassa € {_cassa_broker:,.2f} + extra € {_liq_extra:,.2f} + switch validi € {_tot_vend_netto:,.2f}): versa nuova liquidità dedicata oppure resta fermo.")
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
                for _cand_s in _cands_ab_sim:
                    if _residuo <= 0:
                        break
                    _piano_step.append(f"🔄 **Vendi {_cand_s['ticker']}** ({_cand_s['motivo']}) -> incasso netto **€ {_cand_s['netto_eur']:,.2f}**")
                    _residuo = round(max(0.0, _residuo - _cand_s['netto_eur']), 2)
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
                st.markdown(f"**Titolo:** {risultato['titolo']} | **Prezzo:** €{risultato['prezzo_eur']:.2f} | **Quantità acquistabile:** {risultato['quantita_acquistabile']:.6f} | **Score Target:** {risultato.get('target_score', 'N/D')}/100")
                st.markdown("---")
                scenari = risultato['scenari']
                if scenari['hold_catalizzatore']:
                    st.markdown("### 🛡️ Titoli Protetti (PAC / Scudo Tom Nash / Insider SEC)")
                    for item in scenari['hold_catalizzatore']:
                        st.info(item['messaggio'])
                if scenari['vendita_gain']:
                    st.markdown("### 💰 Scenario 1: Raccolto Profitti Parziale (Fonte A) & Posizioni in Gain")
                    for item in scenari['vendita_gain']:
                        st.warning(item['messaggio'])
                if scenari['vendita_loss']:
                    st.markdown("### 🔄 Scenario 2: Switch Qualitativo Spot (Fonte B — Rotazione da Titoli Stagnanti)")
                    for item in scenari['vendita_loss']:
                        st.success(item['messaggio'])
                if scenari['nuova_liquidita']:
                    st.markdown("### 🎯 Scenario 3: Nuova Liquidità Dedicata")
                    st.success("**OPZIONE MIGLIORE (Portafoglio Intatto).** Preservi tutte le posizioni sane, i PAC e i titoli protetti da Scudo Tom Nash.")
                st.markdown("---")
                st.markdown("### 🏁 CONSIGLIO FINALE DEL SISTEMA")
                _verdetto_m = str(risultato.get('verdetto_matrix') or '').strip()
                if not _verdetto_m:
                    _p_fb = _calcola_profilo_target_simulazione(risultato['titolo'], st.session_state.get("portafoglio") or [], eurusd_rate)
                    _verdetto_m = _p_fb["verdetto_matrix"]
                    _approv_m = _p_fb["approvato_matrix"]
                else:
                    _approv_m = bool(risultato.get('approvato_matrix', False))

                _cands_fin = risultato.get('candidati_fonte_ab') or []
                _netto_fin = float(risultato.get('switch_netto_tot') or 0.0)
                if _cands_fin:
                    _nomi_ab = ", ".join([f"{c['ticker']} ({c['fonte']})" for c in _cands_fin[:3]])
                    _consiglio_fin = (
                        f"Sul fronte finanziamento: puoi liberare fino a **€ {_netto_fin:,.2f} netti** tramite Switch Qualitativo "
                        f"({_nomi_ab}) oppure usare **nuova liquidità dedicata** di **€ {risultato['importo']:,.0f}**, "
                        f"senza mai toccare i PAC né i titoli protetti da Scudo Tom Nash / Insider SEC."
                    )
                else:
                    _consiglio_fin = (
                        f"Sul fronte finanziamento: **Portafoglio Intatto** — nessun titolo sacrificabile "
                        f"(tutti solidi, in PAC o protetti da Scudo Tom Nash / Insider SEC); se decidi di procedere, "
                        f"usa **nuova liquidità dedicata** di **€ {risultato['importo']:,.0f}**."
                    )

                _box_finale = f"**{_verdetto_m}**\n\n{_consiglio_fin}"
                if _approv_m:
                    st.success(_box_finale)
                else:
                    st.warning(_box_finale)

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
            fig = genera_grafico_baleine(st.session_state.grafico_ticker, tf_config['period'], 50, 200, prezzo_medio_eur=st.session_state.grafico_prezzo_medio, timeframe=tf_config['tf'], interval=tf_config['interval'], eurusd_rate=eurusd_rate, height=640, pattern_info=_pat_an)
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
                st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True, "displaylogo": False, "responsive": True, "displayModeBar": False})
            else:
                st.error("Impossibile generare il grafico")
            if st.button("✖️ Chiudi grafico", use_container_width=True):
                st.session_state.grafico_ticker = None
                st.session_state.grafico_prezzo_medio = None
                st.rerun()
with tab_registro:
    st.markdown("### 📅 Bilancio Mensile Flussi di Capitale")
    _bil_mesi = _calcola_bilancio_mensile_flussi()
    if _bil_mesi:
        _opz_mesi = [m["label"] for m in _bil_mesi]
        _mese_sel_lbl = st.selectbox("📆 Seleziona mese di dettaglio:", _opz_mesi, index=0, key="sel_mese_bilancio_flussi")
        _m_sel = next((m for m in _bil_mesi if m["label"] == _mese_sel_lbl), _bil_mesi[0])
        bm1, bm2, bm3, bm4 = st.columns(4)
        bm1.metric("💵 Vendite Nette Mese", f"€ {_m_sel['vendite_nette_eur']:,.2f}", ", ".join(_m_sel["titoli_venduti"]) if _m_sel["titoli_venduti"] else "Nessuna")
        bm2.metric("🏦 Nuova Liquidità Versata", f"€ {_m_sel['nuova_liq_tot_eur']:,.2f}", f"PAC € {_m_sel['nuova_liq_pac_eur']:,.2f} • Spot € {_m_sel['nuova_liq_spot_eur']:,.2f}")
        bm3.metric("♻️ Reinvestito da Cassa", f"€ {_m_sel['reinvestito_cassa_eur']:,.2f}", f"Tot. investito € {_m_sel['totale_investito_eur']:,.2f}")
        bm4.metric("📊 Flusso Netto Tasca", f"€ {_m_sel['flusso_netto_tasca_eur']:,.2f}", f"Comm. TR € {_m_sel['comm_totali_eur']:,.2f}")

        _righe_bm = []
        for _m in _bil_mesi:
            _righe_bm.append({
                "Mese": _m["label"],
                "Vendite Nette €": _m["vendite_nette_eur"],
                "Titoli Venduti": ", ".join(_m["titoli_venduti"]) or "—",
                "Nuova Liq. Versata €": _m["nuova_liq_tot_eur"],
                "Di cui PAC €": _m["nuova_liq_pac_eur"],
                "Di cui Spot €": _m["nuova_liq_spot_eur"],
                "Reinvestito da Cassa €": _m["reinvestito_cassa_eur"],
                "Titoli Acquistati": ", ".join(_m["titoli_acquistati"]) or "—",
                "Comm. TR €": _m["comm_totali_eur"],
            })
        df_bm = pd.DataFrame(_righe_bm)
        st.dataframe(df_bm, use_container_width=True, hide_index=True)

        c_det_v, c_det_a = st.columns(2)
        with c_det_v:
            st.markdown(f"**📥 Entrate da Vendite ({_m_sel['label']})**")
            if _m_sel["dettaglio_vendite"]:
                st.dataframe(pd.DataFrame(_m_sel["dettaglio_vendite"]), use_container_width=True, hide_index=True)
            else:
                st.caption("Nessuna vendita registrata in questo mese.")
        with c_det_a:
            st.markdown(f"**📤 Impieghi & Acquisti ({_m_sel['label']})**")
            if _m_sel["dettaglio_acquisti"]:
                st.dataframe(pd.DataFrame(_m_sel["dettaglio_acquisti"]), use_container_width=True, hide_index=True)
            else:
                st.caption("Nessun acquisto registrato in questo mese.")

        st.download_button(
            label="⬇️ Esporta Bilancio Mensile CSV",
            data=df_bm.to_csv(index=False).encode("utf-8"),
            file_name="bilancio_mensile_flussi_matrix.csv",
            mime="text/csv",
            key="btn_csv_bilancio_mensile",
        )
    else:
        st.info("Il Bilancio Mensile Flussi di Capitale si popolerà automaticamente al primo acquisto o vendita registrati.")

    st.markdown("---")
    st.markdown("### 📒 Registro Acquisti & Mediazioni")
    _dati_acq = carica_json(REGISTRO_ACQUISTI_FILE, default=[])
    if isinstance(_dati_acq, list) and _dati_acq:
        _righe_acq_norm = []
        for _ra in _dati_acq:
            if not isinstance(_ra, dict):
                continue
            _tp_ra = _normalizza_tipo_operazione(_ra.get("Tipo", "Spot"))
            _comm_ra = _ra.get("Commissione_EUR")
            if _comm_ra is None:
                _comm_ra = _commissione_default_tr("ACQUISTO", _tp_ra)
            _tot_ra = round(float(_ra.get("Totale_EUR") or (float(_ra.get("Quantita", 0) or 0) * float(_ra.get("Prezzo_EUR", 0) or 0))), 2)
            _ff_ra = _ra.get("Fonte_Fondi") or "Manuale / Storico"
            _qc_ra = _ra.get("Quota_Da_Cassa_EUR")
            _qn_ra = _ra.get("Quota_Nuova_Liquidita_EUR")
            if _qc_ra is None and _qn_ra is None:
                if "NUOVA" in str(_ff_ra).upper():
                    _qc_ra, _qn_ra = 0.0, _tot_ra
                else:
                    _qc_ra, _qn_ra = _tot_ra, 0.0
            _righe_acq_norm.append({
                "Data": _ra.get("Data", ""),
                "Ticker": _ra.get("Ticker", ""),
                "Operazione": _ra.get("Operazione", ""),
                "Motivo Segnale": _ra.get("Motivo_Segnale") or "Manuale / Storico",
                "Tipo": _tp_ra,
                "Fonte Fondi": _ff_ra,
                "Da Cassa €": round(float(_qc_ra or 0.0), 2),
                "Nuova Liq. €": round(float(_qn_ra or 0.0), 2),
                "Quantita": _ra.get("Quantita", 0),
                "Prezzo_EUR": _ra.get("Prezzo_EUR", 0),
                "Comm. TR €": round(float(_comm_ra), 2),
                "Totale_EUR": _tot_ra,
            })
        st.dataframe(pd.DataFrame(_righe_acq_norm), use_container_width=True, hide_index=True)
    else:
        st.info("Il registro acquisti si creerà automaticamente al primo nuovo acquisto o mediazione.")

    st.subheader("📋 Registro Vendite & Fiscalità")
    anni_disponibili = ["Tutti"] + [str(y) for y in range(2024, 2028)]
    anno_corrente = str(_now_italia().year)
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
            writer.writerow(['ID', 'Data', 'Ticker', 'Motivo Segnale', 'Qta Venduta', 'Prezzo Medio', 'Prezzo Vendita', 'P&L Lordo', 'P&L %', 'Minusvalenze Usate', 'Tasse', 'P&L Netto', 'Tipo'])
            for v in registro:
                writer.writerow([v.get('id', ''), v.get('Data', ''), v.get('Ticker', ''), v.get('Motivo_Segnale') or 'Manuale / Storico', v.get('Qta_Venduta', ''), v.get('Prezzo_Medio', ''), v.get('Prezzo_Vendita', ''), v.get('PnL_Lordo', ''), v.get('PnL_Pct', ''), v.get('Minusvalenze_Usate', ''), v.get('Tasse', ''), v.get('PnL_Netto', ''), v.get('Tipo', '')])
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
        if 'Motivo_Segnale' not in df_registro.columns:
            df_registro['Motivo_Segnale'] = 'Manuale / Storico'
        else:
            df_registro['Motivo_Segnale'] = df_registro['Motivo_Segnale'].fillna('').replace('', 'Manuale / Storico')
        df_display = df_registro[['id', 'Data', 'Ticker', 'Motivo_Segnale', 'Qta_Venduta', 'Prezzo_Medio', 'Prezzo_Vendita', 'PnL_Lordo', 'PnL_Pct', 'Minusvalenze_Usate', 'Tasse', 'PnL_Netto', 'Tipo']].copy()
        df_display.columns = ['ID', 'Data', 'Ticker', 'Motivo Segnale', 'Qta', 'P.Medio', 'P.Vendita', 'P&L Lordo', 'P&L %', 'MV Usate', 'Tasse', 'P&L Netto', 'Tipo']
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
            progress_bar = st.progress(0)
            candidati_palantir, nuovi_trade, n_scansionati = esegui_scansione_ai_palantir(
                watchlist_str=tickers_input,
                period=period,
                eurusd_rate=eurusd_rate,
                ohlc_map=None,
                scrivi_paper=True,
                progress_bar=progress_bar,
            )
            progress_bar.empty()
            if not candidati_palantir:
                st.warning("⚠️ Nessun Setup Palantir trovato nella scansione estesa.")
            elif nuovi_trade:
                st.success(f"✅ Aggiunti {len(nuovi_trade)} titoli al Paper Trading: {', '.join([t['Ticker'] for t in nuovi_trade])}")
                st.info(f"📊 Scansionati {n_scansionati} titoli (Watchlist + Big Tech). Trovati {len(candidati_palantir)} setup Palantir.")
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
                    # Usa la cache del Market Data Hub evitando download yf.Ticker().history() ridondanti
                    hist_1y = _get_ohlc_from_hub(ticker, ohlc_map=None, period='1y')
                    if hist_1y is not None and not hist_1y.empty:
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
    st.subheader('🩺 Check 4 Regole (Tecnica & Tom Nash — IGNITION • BY FABIO • BY Standard • Tom Nash & PAC)')
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
            import importlib; importlib.reload(regia_tracker); regia_tracker.render_check_3_regole(st.session_state['_multi_check_list'], eurusd_rate, solo_fase2=filtro_fase, min_score=min_score, solo_pre_ign=solo_pre_ign, rileva_fase_fn=rileva_fase_weinstein, portafoglio=st.session_state.get("portafoglio"), tom_nash_fn=_valuta_fondamentali_tom_nash)
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
        _wl_raw_ins = st.session_state.get('tickers_input') or (tickers_input if 'tickers_input' in locals() else '') or impostazioni.get('lista_ticker_default', '')
        prog_bar = st.progress(0, text="Analisi transazioni Insider e minimi in corso...")
        esegui_scansione_insider_sec(
            watchlist_str=_wl_raw_ins,
            portafoglio=st.session_state.get('portafoglio'),
            solo_con_insider=solo_con_insider,
            min_s_score=min_s_score_ins,
            max_dist_min=max_dist_min,
            include_panier_esteso=True,
            max_docs_sec=12,
            progress_bar=prog_bar,
        )
        prog_bar.empty()
        if st.session_state.get('insider_promossi_oggi'):
            st.info(f"📲 **Promossi in Watchlist MATRIX** (già saliti troppo, in attesa di pullback): {', '.join(st.session_state['insider_promossi_oggi'])}")

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
