# -*- coding: utf-8 -*-
"""
Monitor Telegram Headless per MATRIX DVMS V6.1.3 PRO (GitHub Actions / Cron).
Standalone puro (zero dipendenze da Streamlit):
- Legge le credenziali esclusivamente da variabili d'ambiente (GitHub Secrets):
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID_FABIO, TELEGRAM_CHAT_ID_LISI, TELEGRAM_CHAT_ID_ALESSIA.
- Gestisce 3 alert identici al centesimo a regia_tracker.py / scanner.py:
  1) Protezione Profitti Spot (Pareggio T1 / Trailing Stop Adattivo T2: 2xATR14 + SMA 20)
  2) Traguardi Gain Spot (+35% / +50% / +70%, solo con netto >= € 100,00)
  3) Report Settimanale del Sabato (pattern_engine.py + Riconquista SMA 50/200 + Inverted H&S)
- Legge stato incrociato da regia_tracker*.json / shadow_regia.json / impostazioni*.json
  e scrive il proprio stato anti-spam SOLO su telegram_monitor_state.json (zero conflitti Cloud).
"""

import argparse
import json
import math
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

# Directory radice del progetto (dove risiedono i JSON e pattern_engine.py)
BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "telegram_monitor_state.json"

# Suffissi titoli quotati direttamente in EUR (nessuna conversione EUR/USD)
_SUFFISSI_EUR = (".DE", ".MI", ".PA", ".AS", ".BR", ".MC", ".LS", ".VI", ".F", ".SW")

# Soglia minima anti-briciole in Euro netti (allineata a scanner.py / regia_tracker.py)
SOGLIA_MIN_NETTO_GAIN = 100.0

# Profili Famiglia multi-utente sul repository GitHub
PROFILI_MONITOR = {
    "fabio": {
        "nome": "Fabio",
        "env_chat_id": "TELEGRAM_CHAT_ID_FABIO",
        "portafoglio": "portafoglio.json",
        "impostazioni": "impostazioni.json",
        "tracker": "regia_tracker.json",
        "tracker_legacy": "shadow_regia.json",
    },
    "lisi": {
        "nome": "Lisi",
        "env_chat_id": "TELEGRAM_CHAT_ID_LISI",
        "portafoglio": "portafoglio_lisi.json",
        "impostazioni": "impostazioni_lisi.json",
        "tracker": "regia_tracker_lisi.json",
        "tracker_legacy": None,
    },
    "alessia": {
        "nome": "Alessia",
        "env_chat_id": "TELEGRAM_CHAT_ID_ALESSIA",
        "portafoglio": "portafoglio_alessia.json",
        "impostazioni": "impostazioni_alessia.json",
        "tracker": "regia_tracker_alessia.json",
        "tracker_legacy": None,
    },
}


# ==============================================================================
# 1. FUSO ORARIO ITALIANO & CALENDARIO FESTIVITÀ / ORARI RIDOTTI NYSE / NASDAQ
# ==============================================================================

def _now_italia():
    """Restituisce l'ora attuale nel fuso italiano (Europe/Rome, ora solare/legale automatica)."""
    return datetime.now(ZoneInfo("Europe/Rome"))


def _calcola_pasqua_gregoriana(anno):
    """Algoritmo di Gauss/Meeus per calcolare la domenica di Pasqua gregoriana."""
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
    """Restituisce l'n-esimo giorno della settimana (0=Lun..6=Dom) nel mese indicato."""
    primo = date(anno, mese, 1)
    delta = (weekday - primo.weekday()) % 7
    return primo + timedelta(days=delta + (n - 1) * 7)


def _last_weekday_of_month(anno, mese, weekday):
    """Restituisce l'ultimo giorno della settimana (0=Lun..6=Dom) nel mese indicato."""
    succ = date(anno + 1, 1, 1) if mese == 12 else date(anno, mese + 1, 1)
    ultimo = succ - timedelta(days=1)
    delta = (ultimo.weekday() - weekday) % 7
    return ultimo - timedelta(days=delta)


def _osservanza_nyse(data_fissa):
    """Regola di osservanza NYSE: sabato -> venerdì precedente, domenica -> lunedì successivo."""
    if data_fissa.weekday() == 5:
        return data_fissa - timedelta(days=1)
    if data_fissa.weekday() == 6:
        return data_fissa + timedelta(days=1)
    return data_fissa


def _get_calendario_nyse_anno(anno):
    """Restituisce (chiusure: dict[date, str], orari_ridotti: dict[date, str]) NYSE/Nasdaq per l'anno."""
    chiusure = {}
    orari_ridotti = {}

    capodanno = _osservanza_nyse(date(anno, 1, 1))
    if capodanno.year == anno:
        chiusure[capodanno] = "Capodanno"
    capodanno_next = _osservanza_nyse(date(anno + 1, 1, 1))
    if capodanno_next.year == anno:
        chiusure[capodanno_next] = "Capodanno (osservato)"

    chiusure[_nth_weekday_of_month(anno, 1, 0, 3)] = "Martin Luther King Jr. Day"
    chiusure[_nth_weekday_of_month(anno, 2, 0, 3)] = "Presidents' Day"
    chiusure[_calcola_pasqua_gregoriana(anno) - timedelta(days=2)] = "Venerdì Santo / Good Friday"
    chiusure[_last_weekday_of_month(anno, 5, 0)] = "Memorial Day"
    chiusure[_osservanza_nyse(date(anno, 6, 19))] = "Juneteenth"
    chiusure[_osservanza_nyse(date(anno, 7, 4))] = "Independence Day"
    chiusure[_nth_weekday_of_month(anno, 9, 0, 1)] = "Labor Day"
    thanksgiving = _nth_weekday_of_month(anno, 11, 3, 4)
    chiusure[thanksgiving] = "Thanksgiving Day"
    chiusure[_osservanza_nyse(date(anno, 12, 25))] = "Natale / Christmas Day"

    # 3 giornate a chiusura anticipata alle 19:00 italiane (13:00 ET)
    black_friday = thanksgiving + timedelta(days=1)
    if black_friday.weekday() < 5 and black_friday not in chiusure:
        orari_ridotti[black_friday] = "Black Friday"
    vig_luglio = date(anno, 7, 3)
    if vig_luglio.weekday() < 5 and vig_luglio not in chiusure:
        orari_ridotti[vig_luglio] = "Vigilia Independence Day"
    vig_natale = date(anno, 12, 24)
    if vig_natale.weekday() < 5 and vig_natale not in chiusure:
        orari_ridotti[vig_natale] = "Vigilia di Natale"

    return chiusure, orari_ridotti


# ==============================================================================
# 2. UTILITÀ I/O JSON & INVIO TELEGRAM
# ==============================================================================

def _carica_json(path_rel, default):
    fp = BASE_DIR / path_rel
    if not fp.exists():
        return default
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return default


def _salva_stato(state_dict):
    STATE_FILE.write_text(
        json.dumps(state_dict, indent=4, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _invia_telegram(bot_token, chat_id, messaggio):
    """Invia un messaggio HTML su Telegram con timeout breve; non solleva mai eccezioni."""
    if not bot_token or not chat_id or not str(messaggio or "").strip():
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": str(chat_id).strip(),
            "text": str(messaggio),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        resp = requests.post(url, json=payload, timeout=8)
        if resp.status_code == 200:
            return True
        print(f"[TELEGRAM] HTTP {resp.status_code} su invio messaggio.", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"[TELEGRAM] Errore rete: {exc}", file=sys.stderr)
        return False


def _eur_it(val):
    return f"€ {float(val or 0.0):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


# ==============================================================================
# 3. LOGICA MATEMATICA IDENTICA A REGIA_TRACKER.PY (PAC/SPOT, T1, T2, ANTI-RUMORE)
# ==============================================================================

def _ripartizione_pac_spot(pos):
    """Restituisce (qta_pac, qta_spot) allineata a scanner.py / regia_tracker.py."""
    if not isinstance(pos, dict):
        return 0.0, 0.0
    q_tot = max(0.0, float(pos.get("Quantita", 0.0) or 0.0))
    if q_tot <= 0:
        return 0.0, 0.0
    if ("Quantita_PAC" in pos) or ("Quantita_Spot" in pos):
        q_pac = max(0.0, float(pos.get("Quantita_PAC", 0.0) or 0.0))
        q_spot = max(0.0, float(pos.get("Quantita_Spot", 0.0) or 0.0))
        somma = q_pac + q_spot
        if somma > 0 and abs(somma - q_tot) > 1e-4:
            q_pac = round(min(q_tot, q_pac * (q_tot / somma)), 6)
            q_spot = round(max(0.0, q_tot - q_pac), 6)
        return round(q_pac, 6), round(q_spot, 6)
    tipo_s = str(pos.get("Tipo", "Spot") or "Spot").strip().upper()
    if tipo_s == "PAC":
        return round(q_tot, 6), 0.0
    return 0.0, round(q_tot, 6)


def _fattore_cambio_ticker(tk, eurusd_rate):
    tk_u = str(tk or "").strip().upper()
    if any(tk_u.endswith(s) for s in _SUFFISSI_EUR):
        return 1.0
    return float(eurusd_rate or 1.12)


def _sl_merita_nuovo_avviso(sl_nuovo, sl_rif):
    """Filtro anti-rumore identico a regia_tracker.py: nuovo avviso solo se SL sale di >= +1% o +0,50 €."""
    s_new = float(sl_nuovo or 0.0)
    s_old = float(sl_rif or 0.0)
    if s_new <= 0:
        return False
    if s_old <= 0:
        return True
    if s_new <= s_old:
        return False
    return (s_new - s_old) >= max(0.50, s_old * 0.01)


def _calcola_sl_pct_da_ohlc(df_ohlc, fallback=0.08):
    """Calcola lo stop percentuale tecnico (4.5%..10.5%) dai dati OHLC."""
    try:
        if df_ohlc is None or df_ohlc.empty or len(df_ohlc) < 15:
            return fallback
        closes = df_ohlc["Close"].dropna()
        if len(closes) < 15:
            return fallback
        p_cur = float(closes.iloc[-1])
        if p_cur <= 0:
            return fallback
        sma20 = float(closes.rolling(20).mean().iloc[-1]) if len(closes) >= 20 else p_cur * 0.95
        atr14 = float((df_ohlc["High"] - df_ohlc["Low"]).tail(14).mean())
        sl_atr = p_cur - (2.0 * atr14)
        sl_sma = sma20 * 0.985
        candidati = [x for x in (sl_sma, sl_atr) if 0.895 * p_cur <= x <= 0.955 * p_cur]
        sl_nat = max(candidati) if candidati else max(p_cur * 0.895, min(p_cur * 0.955, sl_atr))
        return max(0.045, min(0.105, abs((sl_nat - p_cur) / p_cur)))
    except Exception:
        return fallback


def _calcola_trailing_stop_adattivo_grafico(df_ohlc, mx_eur, p_live_eur, pmc_eur, t1_eur, conv=1.0):
    """
    Replica al centesimo _calcola_trailing_stop_adattivo_grafico di regia_tracker.py:
    combina 2xATR14 (clampato -6%..-11% dal massimo) e SMA 20 x 0.985,
    lasciando almeno -5% di respiro dal prezzo attuale e pavimento >= max(PMC, T1).
    """
    mx = float(mx_eur or p_live_eur or pmc_eur or 0.0)
    pl = float(p_live_eur or mx or pmc_eur or 0.0)
    pmc = float(pmc_eur or 0.0)
    t1 = float(t1_eur or pmc)
    cv = float(conv or 1.0) if float(conv or 1.0) > 0 else 1.0

    dist_atr = 0.08
    sl_sma20 = None
    ha_dati_graf = False
    try:
        if df_ohlc is not None and not df_ohlc.empty and len(df_ohlc) >= 15:
            closes = df_ohlc["Close"].dropna()
            highs = df_ohlc["High"].dropna()
            lows = df_ohlc["Low"].dropna()
            if len(closes) >= 15 and len(highs) >= 14 and len(lows) >= 14:
                atr14_nat = float((highs - lows).tail(14).mean())
                mx_nat = max(float(highs.tail(60).max()), mx * cv)
                if mx_nat > 0 and atr14_nat > 0:
                    dist_atr = max(0.06, min(0.11, (2.0 * atr14_nat) / mx_nat))
                    ha_dati_graf = True
                if len(closes) >= 20:
                    sma20_nat = float(closes.rolling(20).mean().iloc[-1])
                    if sma20_nat > 0:
                        sl_sma20 = round((sma20_nat / cv) * 0.985, 2)
    except Exception:
        pass

    sl_atr = round(mx * (1.0 - dist_atr), 2)
    pavimento = round(max(pmc, t1), 2)
    if pavimento >= pl * 0.995:
        pavimento = pmc

    scelto_sma = False
    if sl_sma20 is not None and sl_sma20 >= pavimento:
        cand_alto = max(sl_atr, sl_sma20)
        cand_basso = min(sl_atr, sl_sma20)
        if cand_alto <= pl * 0.95:
            sl_fin = cand_alto
            scelto_sma = (cand_alto == sl_sma20 and abs(sl_sma20 - sl_atr) > 0.05)
        elif cand_basso <= pl * 0.95:
            sl_fin = cand_basso
            scelto_sma = (cand_basso == sl_sma20 and abs(sl_sma20 - sl_atr) > 0.05)
        else:
            sl_fin = round(max(pavimento, min(sl_atr, pl * 0.95)), 2)
    else:
        sl_fin = round(max(pavimento, sl_atr), 2)
        if sl_fin > pl * 0.95 and pavimento <= pl * 0.95:
            sl_fin = round(max(pavimento, pl * 0.95), 2)

    sl_fin = round(max(pmc, sl_fin), 2)
    if pl > 0 and sl_fin >= pl * 0.995:
        sl_fin = round(max(pmc, pl * 0.95), 2)

    dist_eff = round(((mx - sl_fin) / mx) * 100.0, 1) if mx > 0 else round(dist_atr * 100.0, 1)
    dist_eff = max(1.0, dist_eff)
    if scelto_sma:
        motivo = f"appoggiato sotto la media a 20 giorni (~-{dist_eff:.0f}% dal massimo)"
    elif ha_dati_graf:
        motivo = f"-{dist_eff:.0f}% dal massimo, calibrato sulla volatilità del titolo"
    else:
        motivo = f"-{dist_eff:.0f}% dal massimo raggiunto"
    return sl_fin, dist_eff, motivo


def _estrai_df_da_batch(raw_df, tk, multi_ticker):
    """Estrae in modo sicuro il DataFrame OHLC di un singolo ticker da yf.download()."""
    if raw_df is None or raw_df.empty:
        return pd.DataFrame()
    try:
        if multi_ticker and isinstance(raw_df.columns, pd.MultiIndex):
            if tk in raw_df.columns.get_level_values(0):
                sub = raw_df[tk].copy()
            elif tk in raw_df.columns.get_level_values(1):
                sub = raw_df.xs(tk, axis=1, level=1).copy()
            else:
                return pd.DataFrame()
        else:
            sub = raw_df.copy()
        cols = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in sub.columns]
        if "Close" not in cols:
            return pd.DataFrame()
        return sub[cols].dropna(subset=["Close"])
    except Exception:
        return pd.DataFrame()


def _scarica_batch_ohlc(tickers, period="3mo"):
    """Scarica in 1 solo batch i dati OHLC Daily + EURUSD=X per ridurre i tempi di esecuzione."""
    unici = sorted({str(t).strip().upper() for t in tickers if str(t).strip()})
    if not unici:
        return {}, 1.12
    tutti = list(dict.fromkeys(unici + ["EURUSD=X"]))
    try:
        raw = yf.download(
            tickers=tutti if len(tutti) > 1 else tutti[0],
            period=period,
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
    except Exception as exc:
        print(f"[YFINANCE] Errore download batch: {exc}", file=sys.stderr)
        return {}, 1.12

    multi = len(tutti) > 1
    eur_df = _estrai_df_da_batch(raw, "EURUSD=X", multi)
    eurusd = 1.12
    if not eur_df.empty:
        try:
            v_eur = float(eur_df["Close"].dropna().iloc[-1])
            if 0.70 <= v_eur <= 1.60:
                eurusd = round(v_eur, 4)
        except Exception:
            pass

    mappa = {}
    for tk in unici:
        df_tk = _estrai_df_da_batch(raw, tk, multi)
        if not df_tk.empty:
            mappa[tk] = df_tk
    return mappa, eurusd


# ==============================================================================
# 4. FORMATTAZIONE MESSAGGI TELEGRAM (IDENTICI A REGIA_TRACKER.PY / SCANNER.PY)
# ==============================================================================

def _formatta_msg_sl(nome_u, tk, tipo_prot, pnl_pct, max_eur, prezzo_eur, pmc_eur, sl_eur, mot_g, is_misto, q_spot):
    pnl_s = f"{pnl_pct:+.1f}%".replace(".", ",")
    dist_pct = ((sl_eur / prezzo_eur) - 1.0) * 100.0 if prezzo_eur > 0 else 0.0
    gain_bl_pct = ((sl_eur / pmc_eur) - 1.0) * 100.0 if pmc_eur > 0 else 0.0
    dist_s = f"{dist_pct:+.1f}%".replace(".", ",")
    gain_b_s = f"{gain_bl_pct:+.1f}%".replace(".", ",")
    saluto = f"Ciao {nome_u}, " if nome_u else ""
    if is_misto:
        q_lbl = f"{int(q_spot)}" if abs(q_spot - round(q_spot)) < 1e-4 else f"{q_spot:.2f}".replace(".", ",")
        nota_misto = f" sulle sole <b>{q_lbl} azioni Spot</b> (lascia intatto il tuo PAC)"
    else:
        nota_misto = ""

    if tipo_prot == "TRAILING":
        riga_imp = (
            f"📊 <b>Se scatta lo Stop:</b> <b>{dist_s}</b> rispetto al prezzo attuale ({_eur_it(prezzo_eur)}) → "
            f"blindato un guadagno di <b>{gain_b_s}</b> sul tuo prezzo di carico ({_eur_it(pmc_eur)})."
        )
        return (
            f"🏆 <b>MATRIX PRO — PROTEGGI IL PROFITTO ({tk})</b>\n"
            f"{saluto}<b>{tk}</b> è a <b>{pnl_s}</b> (massimo {_eur_it(max_eur)}): alziamo la rete di sicurezza calibrata sul grafico del titolo!\n\n"
            f"👉 <b>Trade Republic (30 secondi):</b>\n"
            f"Apri <b>{tk}</b> → Vendi → Ordine Stop → imposta il prezzo a <b>{_eur_it(sl_eur)}</b> ({mot_g}){nota_misto}.\n"
            f"{riga_imp}\n"
            f"Poi clicca <i>✅ Fatto, Stop Loss inserito</i> nell'app MATRIX."
        )
    riga_imp_p = (
        f"📊 <b>Se scatta lo Stop:</b> <b>{dist_s}</b> rispetto al prezzo attuale ({_eur_it(prezzo_eur)}) → "
        f"esci in <b>pareggio (0%)</b> senza perdere il capitale ({_eur_it(pmc_eur)})."
    )
    return (
        f"🛡️ <b>MATRIX PRO — METTI AL SICURO IL CAPITALE ({tk})</b>\n"
        f"{saluto}<b>{tk}</b> è in guadagno del <b>{pnl_s}</b>: è il momento di portarti al sicuro sul pareggio!\n\n"
        f"👉 <b>Trade Republic (30 secondi):</b>\n"
        f"Apri <b>{tk}</b> → Vendi → Ordine Stop → imposta il prezzo a <b>{_eur_it(sl_eur)}</b> (il tuo prezzo di carico){nota_misto}.\n"
        f"{riga_imp_p}\n"
        f"Poi clicca <i>✅ Fatto, Stop Loss inserito</i> nell'app MATRIX."
    )


def _formatta_msg_gain(nome_u, tk, pnl_pct, val_spot, gain_netto_tot, netto_50, netto_100, sl_prot, is_misto, q_spot, scaglione):
    pnl_s = f"{pnl_pct:+.1f}%".replace(".", ",")
    saluto = f"Ciao {nome_u}, " if nome_u else ""
    if is_misto:
        q_lbl = f"{int(q_spot)}" if abs(q_spot - round(q_spot)) < 1e-4 else f"{q_spot:.2f}".replace(".", ",")
        nota_q = f"sulla tua quota Spot (<b>{q_lbl} azioni</b>, lasciando intatto il PAC)"
    else:
        nota_q = "sulla tua posizione Spot"

    if scaglione >= 70:
        titolo = f"🚀 <b>MATRIX PRO — GAIN ECCEZIONALE ({tk} {pnl_s})</b>"
    elif scaglione >= 50:
        titolo = f"💰 <b>MATRIX PRO — TRAGUARDO +50% ({tk} {pnl_s})</b>"
    else:
        titolo = f"🎯 <b>MATRIX PRO — TRAGUARDO +35% ({tk} {pnl_s})</b>"

    return (
        f"{titolo}\n"
        f"{saluto}<b>{tk}</b> ha superato <b>+{scaglione}%</b> {nota_q}!\n\n"
        f"📊 <b>Valore attuale Spot:</b> {_eur_it(val_spot)} (guadagno netto stimato: <b>+{_eur_it(gain_netto_tot)}</b> dopo 26% tasse e € 1 TR)\n"
        f"• <b>Opzione 1 (Raccolto 50%):</b> incassi ~<b>{_eur_it(netto_50)} netti</b> e lasci correre l'altra metà gratis.\n"
        f"• <b>Opzione 2 (Chiudi 100%):</b> porti a casa ~<b>{_eur_it(netto_100)} netti</b> sul conto.\n"
        f"• <b>Opzione 3 (Lascia correre protetto):</b> mantieni lo Stop Loss di protezione su Trade Republic almeno a <b>{_eur_it(sl_prot)}</b>."
    )


# ==============================================================================
# 5. MODALITÀ INTRADAY (PROTEZIONE PROFITTI T1/T2 + GAIN SPOT >= € 100 NETTI)
# ==============================================================================

def _leggi_mappa_tracker_reale(prof):
    """Legge i record Portafoglio Reale attivi dal file regia_tracker*.json (con fallback shadow_regia.json)."""
    dati = _carica_json(prof["tracker"], None)
    if not isinstance(dati, list) and prof.get("tracker_legacy"):
        dati = _carica_json(prof["tracker_legacy"], [])
    if not isinstance(dati, list):
        return {}
    out = {}
    for r in dati:
        if not isinstance(r, dict):
            continue
        orig = str(r.get("Origine") or "").strip().upper()
        if orig in ("METODO SISTEMA", "METODO_SISTEMA", "SISTEMA"):
            continue
        if str(r.get("Stato") or "") != "Attivo":
            continue
        tk = str(r.get("Ticker") or "").strip().upper()
        if tk and tk not in out:
            out[tk] = r
    return out


def esegui_intraday(bot_token, state, profili_attivi):
    """Controlla Protezione Profitti Spot (T1/T2) e Gain Spot >= € 100 netti sui profili con chat_id."""
    portafogli = {}
    tutti_tks = []
    for u_key, (prof, _) in profili_attivi.items():
        port = _carica_json(prof["portafoglio"], [])
        if not isinstance(port, list):
            port = []
        portafogli[u_key] = port
        for pos in port:
            _, q_sp = _ripartizione_pac_spot(pos)
            tk = str(pos.get("Ticker") or "").strip().upper()
            if tk and q_sp > 1e-6:
                tutti_tks.append(tk)

    if not tutti_tks:
        print("[INTRADAY] Nessuna posizione Spot attiva sui profili configurati.")
        return False

    ohlc_map, eurusd = _scarica_batch_ohlc(tutti_tks, period="3mo")
    print(f"[INTRADAY] Scaricati {len(ohlc_map)}/{len(set(tutti_tks))} titoli Spot | EUR/USD={eurusd:.4f}")

    mod_state = False
    now_str = _now_italia().strftime("%Y-%m-%d %H:%M")

    for u_key, (prof, chat_id) in profili_attivi.items():
        u_state = state.setdefault(u_key, {})
        sl_not_map = u_state.setdefault("sl_notificato", {})
        gain_not_map = u_state.setdefault("gain_notificato", {})
        max_map = u_state.setdefault("max_price", {})
        tracker_map = _leggi_mappa_tracker_reale(prof)

        for pos in portafogli.get(u_key, []):
            tk = str(pos.get("Ticker") or "").strip().upper()
            q_pac, q_spot = _ripartizione_pac_spot(pos)
            if not tk or q_spot <= 1e-6:
                continue
            pmc = round(float(pos.get("Prezzo_Medio") or 0.0), 2)
            if pmc <= 0:
                continue
            df_ohlc = ohlc_map.get(tk)
            if df_ohlc is None or df_ohlc.empty:
                continue
            conv = _fattore_cambio_ticker(tk, eurusd)
            p_live = round(float(df_ohlc["Close"].dropna().iloc[-1]) / conv, 2)
            if p_live <= 0:
                continue

            rec_tr = tracker_map.get(tk) or {}
            dt_chk = str(rec_tr.get("Data_Check_SL") or rec_tr.get("Data_Ingresso") or pos.get("Data_Acquisto") or "")[:10]
            hi_eur = p_live
            if dt_chk and "High" in df_ohlc.columns:
                try:
                    sr = df_ohlc[df_ohlc.index.strftime("%Y-%m-%d") >= dt_chk]
                    if not sr.empty:
                        hi_eur = max(hi_eur, round(float(sr["High"].dropna().max()) / conv, 2))
                except Exception:
                    pass

            mx_r = round(max(
                pmc,
                p_live,
                hi_eur,
                float(rec_tr.get("Max_Price") or 0.0),
                float(max_map.get(tk) or 0.0),
            ), 2)

            sl_pct = _calcola_sl_pct_da_ohlc(df_ohlc, fallback=0.08)
            t1_r = float(rec_tr.get("T1") or round(pmc * (1.0 + 1.5 * sl_pct), 2))
            t2_r = float(rec_tr.get("Target") or round(pmc * (1.0 + 2.5 * sl_pct), 2))
            sl_conf_tr = float(rec_tr.get("SL_Confermato_TR") or 0.0)
            sl_not_prev = max(
                sl_conf_tr,
                float(rec_tr.get("SL_Notificato_Telegram") or 0.0),
                float(sl_not_map.get(tk) or 0.0),
            )
            pnl_pct = ((p_live / pmc) - 1.0) * 100.0
            is_misto = bool(q_pac > 1e-6)

            # 1) Controllo Protezione Profitti (T2 Trailing Adattivo / T1 Pareggio)
            tipo_prot = None
            sl_cand = 0.0
            mot_graf = ""
            if t2_r > 0 and mx_r >= t2_r and p_live > pmc * 1.02:
                sl_cand, _, mot_graf = _calcola_trailing_stop_adattivo_grafico(
                    df_ohlc=df_ohlc, mx_eur=mx_r, p_live_eur=p_live,
                    pmc_eur=pmc, t1_eur=t1_r, conv=conv,
                )
                tipo_prot = "TRAILING"
            elif t1_r > 0 and mx_r >= t1_r and p_live > pmc * 1.005:
                sl_cand = pmc
                mot_graf = "pareggio al prezzo di carico"
                tipo_prot = "PAREGGIO"

            if tipo_prot and sl_cand > 0 and p_live > sl_cand * 0.995 and _sl_merita_nuovo_avviso(sl_cand, sl_not_prev):
                msg_sl = _formatta_msg_sl(
                    nome_u=prof["nome"], tk=tk, tipo_prot=tipo_prot,
                    pnl_pct=pnl_pct, max_eur=mx_r, prezzo_eur=p_live,
                    pmc_eur=pmc, sl_eur=sl_cand, mot_g=mot_graf,
                    is_misto=is_misto, q_spot=q_spot,
                )
                if _invia_telegram(bot_token, chat_id, msg_sl):
                    sl_not_map[tk] = round(sl_cand, 2)
                    max_map[tk] = mx_r
                    u_state["ultimo_aggiornamento"] = now_str
                    mod_state = True
                    print(f"[INTRADAY] Push {tipo_prot} inviato -> {u_key}:{tk} SL=€{sl_cand:.2f}")

            # 2) Controllo Traguardi Gain Spot (+35% / +50% / +70%) con soglia anti-briciole >= € 100 netti
            scaglione = 70 if pnl_pct >= 70.0 else (50 if pnl_pct >= 50.0 else (35 if pnl_pct >= 35.0 else 0))
            gain_prev = max(int(rec_tr.get("Gain_Notificato_Telegram") or 0), int(gain_not_map.get(tk) or 0))
            if scaglione > 0 and scaglione > gain_prev:
                val_spot = round(q_spot * p_live, 2)
                carico_spot = round(q_spot * pmc, 2)
                gain_lordo = max(0.0, val_spot - carico_spot)
                tasse_tot = gain_lordo * 0.26
                gain_netto_tot = round(max(0.0, gain_lordo - tasse_tot - 1.0), 2)
                netto_100 = round(max(0.0, val_spot - tasse_tot - 1.0), 2)
                netto_50 = round(max(0.0, (val_spot * 0.5) - (gain_lordo * 0.5 * 0.26) - 1.0), 2)
                if netto_50 >= SOGLIA_MIN_NETTO_GAIN or netto_100 >= SOGLIA_MIN_NETTO_GAIN:
                    sl_prot = round(max(pmc, sl_cand if sl_cand > 0 else float(rec_tr.get("Stop_Loss") or pmc)), 2)
                    if sl_prot >= p_live * 0.995:
                        sl_prot = round(max(pmc, p_live * 0.94), 2)
                    msg_g = _formatta_msg_gain(
                        nome_u=prof["nome"], tk=tk, pnl_pct=pnl_pct,
                        val_spot=val_spot, gain_netto_tot=gain_netto_tot,
                        netto_50=netto_50, netto_100=netto_100, sl_prot=sl_prot,
                        is_misto=is_misto, q_spot=q_spot, scaglione=scaglione,
                    )
                    if _invia_telegram(bot_token, chat_id, msg_g):
                        gain_not_map[tk] = scaglione
                        u_state["ultimo_aggiornamento"] = now_str
                        mod_state = True
                        print(f"[INTRADAY] Push GAIN +{scaglione}% inviato -> {u_key}:{tk}")

    return mod_state


# ==============================================================================
# 6. MODALITÀ SABATO (REPORT SETTIMANALE CON PATTERN_ENGINE.PY + INVERSIONI)
# ==============================================================================

def _rileva_fase_weinstein_semplice(df):
    """Classificazione fase Weinstein coerente con scanner.py per pattern_engine.analizza_pattern_titolo."""
    if df is None or len(df) < 50:
        return "FASE 1 (Accumulazione/Basing)"
    closes = df["Close"].dropna()
    p = float(closes.iloc[-1])
    sma50 = float(closes.rolling(50).mean().iloc[-1])
    if len(closes) >= 200:
        sma200_s = closes.rolling(200).mean()
        sma200 = float(sma200_s.iloc[-1])
        sma200_prev = float(sma200_s.iloc[-20]) if len(closes) >= 220 else sma200
        if p > sma200 and p > sma50 and sma200 >= sma200_prev * 0.995:
            return "FASE 2 (Trend Rialzista)"
        if p > sma200 and p <= sma50:
            return "CORREZIONE in Trend (Pullback Fase 2)"
        if p < sma200 and sma200 < sma200_prev * 0.995:
            return "FASE 4 (Declino Strutturale)"
    return "FASE 1 (Accumulazione/Basing)"


def _rileva_inversioni_extra_settimanali(ticker, df, pat_mod=None):
    """Riconquista SMA 200 / SMA 50 con volumi >= 1.2x + Testa e Spalle Rovesciato (identico a scanner.py)."""
    risultati = []
    if df is None or df.empty or len(df) < 60:
        return risultati
    try:
        closes = df["Close"].dropna()
        opens = df["Open"].reindex(closes.index).fillna(closes)
        vols = df["Volume"].reindex(closes.index).fillna(0)
        if len(closes) < 60:
            return risultati
        p_now = float(closes.iloc[-1])
        vol_med_20 = vols.rolling(20).mean()

        if len(closes) >= 205:
            sma200 = closes.rolling(200).mean()
            s200_now = float(sma200.iloc[-1])
            era_sotto = bool((closes.iloc[-6:-1] < sma200.iloc[-6:-1]).any())
            if pd.notna(s200_now) and s200_now > 0 and p_now > s200_now and era_sotto:
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
        if not risultati and len(closes) >= 60:
            sma50 = closes.rolling(50).mean()
            s50_now = float(sma50.iloc[-1])
            era_sotto = bool((closes.iloc[-6:-1] < sma50.iloc[-6:-1]).any())
            if pd.notna(s50_now) and s50_now > 0 and p_now > s50_now and era_sotto:
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

        # Testa e Spalle Rovesciato (Inverted H&S) tramite pattern_engine.trova_pivot
        sub_ihs = df.tail(120).reset_index(drop=True)
        if pat_mod is not None and len(sub_ihs) >= 45 and hasattr(pat_mod, "trova_pivot"):
            _, piv_lows = pat_mod.trova_pivot(sub_ihs, ordine=3)
            if len(piv_lows) >= 3:
                (i1, l1), (i2, l2), (i3, l3) = piv_lows[-3], piv_lows[-2], piv_lows[-1]
                if l1 > 0 and l2 > 0 and l3 > 0 and i1 < i2 < i3:
                    testa_bassa = (l2 <= l1 * 0.96) and (l2 <= l3 * 0.96)
                    spalle_simm = abs(l1 - l3) / max(l1, l3) <= 0.08
                    spalla_dx_rec = (len(sub_ihs) - 1 - i3) <= 22
                    if testa_bassa and spalle_simm and spalla_dx_rec:
                        nk1 = float(sub_ihs["High"].iloc[i1 : i2 + 1].max())
                        nk2 = float(sub_ihs["High"].iloc[i2 : i3 + 1].max())
                        neckline = round(max(nk1, nk2), 2)
                        if neckline > 0 and (neckline * 0.94 <= p_now <= neckline * 1.06):
                            dist_nk = ((p_now / neckline) - 1.0) * 100.0
                            st_nk = "ROTTURA CONFERMATA" if dist_nk >= 0 else f"a {dist_nk:+.1f}% da neckline"
                            risultati.append({
                                "ticker": ticker,
                                "figura": "Testa e Spalle Rovesciato",
                                "dettaglio": f"Neckline {neckline:.2f} ({st_nk})",
                                "priorita": 1,
                            })
    except Exception:
        pass
    return risultati


def esegui_report_sabato(bot_token, state, profili_attivi, forza=False):
    """Invia 1 solo Report Settimanale per profilo configurato (anti-duplicato YYYY-Www)."""
    dt_it = _now_italia()
    sett_iso = dt_it.strftime("%G-W%V")
    now_str = dt_it.strftime("%Y-%m-%d %H:%M")

    try:
        sys.path.insert(0, str(BASE_DIR))
        import pattern_engine as pat_mod
    except Exception as exc:
        print(f"[SABATO] Impossibile importare pattern_engine.py: {exc}", file=sys.stderr)
        pat_mod = None

    # Filtra solo gli utenti che non hanno ancora ricevuto il report di questa settimana
    da_inviare = {}
    tutti_tks = ["SPY", "^VIX"]
    for u_key, (prof, chat_id) in profili_attivi.items():
        u_state = state.get(u_key) or {}
        imp = _carica_json(prof["impostazioni"], {})
        gia_stato = str(u_state.get("ultimo_report_sabato_tg") or "") == sett_iso
        gia_imp = isinstance(imp, dict) and str(imp.get("ultimo_report_sabato_tg") or "") == sett_iso
        if (not forza) and (gia_stato or gia_imp):
            print(f"[SABATO] Report {sett_iso} già inviato per {u_key}, salto.")
            continue
        port = _carica_json(prof["portafoglio"], [])
        if not isinstance(port, list):
            port = []
        wl_raw = str((imp if isinstance(imp, dict) else {}).get("lista_ticker_default") or "")
        wl = [t.strip().upper() for t in wl_raw.replace("\n", ",").split(",") if t.strip()]
        port_tks = [str(p.get("Ticker") or "").strip().upper() for p in port if p.get("Ticker")]
        da_inviare[u_key] = (prof, chat_id, port, wl)
        tutti_tks.extend(port_tks)
        tutti_tks.extend(wl)

    if not da_inviare:
        return False

    ohlc_map, eurusd = _scarica_batch_ohlc(tutti_tks, period="1y")
    print(f"[SABATO] Scaricati {len(ohlc_map)} titoli (1y) | EUR/USD={eurusd:.4f}")

    # Clima Macro SPY / VIX
    spy_df = ohlc_map.get("SPY")
    vix_df = ohlc_map.get("^VIX")
    riga_macro = "🌍 <b>Clima SPY:</b> N/D"
    spy_regime = "giallo"
    if spy_df is not None and not spy_df.empty:
        c_spy = spy_df["Close"].dropna()
        p_spy = float(c_spy.iloc[-1])
        sma10 = float(c_spy.rolling(10).mean().iloc[-1]) if len(c_spy) >= 10 else p_spy
        hi52 = float(spy_df["High"].dropna().max()) if "High" in spy_df.columns else float(c_spy.max())
        dd_spy = round(min(0.0, ((p_spy / hi52) - 1.0) * 100.0), 1) if hi52 > 0 else 0.0
        vix_v = float(vix_df["Close"].dropna().iloc[-1]) if (vix_df is not None and not vix_df.empty) else None
        if vix_v is not None:
            spy_regime = "verde" if (p_spy > sma10 and vix_v < 18.5) else ("rosso" if (p_spy < sma10 or vix_v > 30.0) else "giallo")
        else:
            spy_regime = "verde" if p_spy > sma10 else "rosso"
        zona = "BEAR" if (dd_spy <= -18.0 or (vix_v and vix_v > 35.0)) else ("SCONTO" if dd_spy <= -8.0 else "NORMALE")
        dd_s = f"{dd_spy:.1f}%".replace(".", ",")
        vix_s = f" • VIX {vix_v:.1f}" if vix_v is not None else ""
        riga_macro = f"🌍 <b>Clima SPY:</b> {spy_regime.upper()} (Drawdown 52w: {dd_s}{vix_s} • Fascia {zona})"

    mod_state = False
    for u_key, (prof, chat_id, port, wl) in da_inviare.items():
        port_map = {str(p.get("Ticker") or "").strip().upper(): p for p in port if p.get("Ticker")}
        port_set = set(port_map.keys())
        wl_only = [tk for tk in dict.fromkeys(wl) if tk and tk not in port_set]

        righe_port = []
        visti_port = set()
        righe_wl = []
        visti_wl = set()

        # 1) Analisi figure tramite pattern_engine.py (se disponibile)
        if pat_mod is not None and hasattr(pat_mod, "analizza_pattern_titolo"):
            for tk in sorted(port_set) + wl_only:
                df_t = ohlc_map.get(tk)
                if df_t is None or len(df_t) < 60:
                    continue
                in_port = tk in port_set
                pos_p = port_map.get(tk)
                pmc_eur = float(pos_p.get("Prezzo_Medio") or 0.0) if pos_p else None
                cur_t = "EUR" if any(tk.endswith(s) for s in _SUFFISSI_EUR) else "USD"
                fase_t = _rileva_fase_weinstein_semplice(df_t)
                try:
                    res = pat_mod.analizza_pattern_titolo(
                        ticker=tk,
                        df=df_t,
                        in_portafoglio=in_port,
                        prezzo_medio_eur=pmc_eur,
                        s_score=75,
                        fase_weinstein=fase_t,
                        currency=cur_t,
                        eurusd_rate=eurusd,
                        spy_regime=spy_regime,
                    )
                except Exception:
                    res = None
                if not isinstance(res, dict):
                    continue
                al = res.get("alert")
                sv = res.get("sorvegliato")
                if isinstance(al, dict):
                    fig_n = str(al.get("figura") or "Pattern")
                    ty = float(al.get("trigger_y") or 0.0)
                    dist_y = float(al.get("dist_y_pct") or 0.0)
                    simb = "€" if cur_t == "EUR" else "$"
                    cat = str(al.get("categoria") or "")
                    if in_port and (tk, fig_n) not in visti_port:
                        ico = "⚠️" if "sell" in cat else ("🟢" if "mediazione" in cat else "🚀")
                        visti_port.add((tk, fig_n))
                        righe_port.append(f"• {ico} <b>{tk}</b>: {fig_n} (Trigger {simb}{ty:.2f}, {dist_y:+.1f}%)")
                    elif (not in_port) and cat == "buy_nuovo" and tk not in visti_wl:
                        visti_wl.add(tk)
                        righe_wl.append(f"• 🚀 <b>{tk}</b>: {fig_n} (Trigger {simb}{ty:.2f}, {dist_y:+.1f}%)")
                elif isinstance(sv, dict):
                    fig_n = str(sv.get("figura") or "Pre-Breakout")
                    ty = float(sv.get("trigger_y") or 0.0)
                    dist_y = float(sv.get("dist_y_pct") or 0.0)
                    simb = "€" if cur_t == "EUR" else "$"
                    if in_port and (tk, fig_n) not in visti_port:
                        visti_port.add((tk, fig_n))
                        righe_port.append(f"• 👀 <b>{tk}</b>: {fig_n} quasi pronto (Trigger {simb}{ty:.2f}, {dist_y:+.1f}%)")
                    elif (not in_port) and tk not in visti_wl and len(righe_wl) < 10:
                        visti_wl.add(tk)
                        righe_wl.append(f"• 👀 <b>{tk}</b>: {fig_n} (Trigger {simb}{ty:.2f}, {dist_y:+.1f}%)")

        # 2) Micro-detector extra (Riconquista SMA 50/200 + Testa e Spalle Rovesciato)
        for tk_p in sorted(port_set):
            for ex in _rileva_inversioni_extra_settimanali(tk_p, ohlc_map.get(tk_p), pat_mod=pat_mod):
                if (tk_p, ex["figura"]) not in visti_port:
                    visti_port.add((tk_p, ex["figura"]))
                    righe_port.append(f"• 🔄 <b>{tk_p}</b>: {ex['figura']} ({ex['dettaglio']})")
        extra_wl = []
        for tk_w in wl_only:
            if tk_w not in visti_wl:
                extra_wl.extend(_rileva_inversioni_extra_settimanali(tk_w, ohlc_map.get(tk_w), pat_mod=pat_mod))
        extra_wl.sort(key=lambda x: (x["priorita"], x["ticker"]))
        for ex in extra_wl[:8]:
            if ex["ticker"] not in visti_wl:
                visti_wl.add(ex["ticker"])
                righe_wl.append(f"• 🔄 <b>{ex['ticker']}</b>: {ex['figura']} ({ex['dettaglio']})")

        blocco_port = "\n".join(righe_port[:8]) if righe_port else "• Nessuna figura di inversione o rottura rilevata questa settimana sui tuoi titoli."
        blocco_wl = "\n".join(righe_wl[:10]) if righe_wl else "• Nessuna figura di inversione o breakout pronta in Watchlist questa settimana."

        msg = (
            f"📅 <b>REPORT SABATO MATRIX PRO ({sett_iso})</b>\n"
            f"Ciao {prof['nome']}, ecco la fotografia del fine settimana (mercati chiusi) per prepararti a lunedì:\n"
            f"{riga_macro}\n\n"
            f"💼 <b>SUL TUO PORTAFOGLIO:</b>\n{blocco_port}\n\n"
            f"🔎 <b>WATCHLIST — FIGURE &amp; INVERSIONI:</b>\n{blocco_wl}\n\n"
            f"<i>Analisi automatica MATRIX PRO (Portafoglio + Watchlist).</i>"
        )
        if len(msg) > 3800:
            msg = msg[:3760].rstrip() + "\n…\n<i>Apri MATRIX PRO per i dettagli completi.</i>"

        if _invia_telegram(bot_token, chat_id, msg):
            u_state = state.setdefault(u_key, {})
            u_state["ultimo_report_sabato_tg"] = sett_iso
            u_state["ultimo_aggiornamento"] = now_str
            mod_state = True
            print(f"[SABATO] Report {sett_iso} inviato -> {u_key}")

    return mod_state


# ==============================================================================
# 7. ENTRYPOINT CLI (--mode auto|intraday|sabato|test)
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="MATRIX PRO — Monitor Telegram Headless")
    parser.add_argument(
        "--mode",
        choices=("auto", "intraday", "sabato", "test"),
        default="auto",
        help="Modalità di esecuzione (default: auto guidata da Europe/Rome).",
    )
    args = parser.parse_args()

    bot_token = str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not bot_token:
        print("[MONITOR] TELEGRAM_BOT_TOKEN non configurato: uscita pulita.")
        return 0

    profili_attivi = {}
    for u_key, prof in PROFILI_MONITOR.items():
        cid = str(os.environ.get(prof["env_chat_id"]) or "").strip()
        if cid:
            profili_attivi[u_key] = (prof, cid)

    if not profili_attivi:
        print("[MONITOR] Nessun TELEGRAM_CHAT_ID_* configurato: uscita pulita.")
        return 0

    now_it = _now_italia()
    oggi_d = now_it.date()
    hm = now_it.hour * 60 + now_it.minute

    if args.mode == "test":
        for u_key, (prof, cid) in profili_attivi.items():
            msg_test = (
                f"✅ <b>MATRIX PRO Monitor Telegram attivo!</b>\n"
                f"Ciao {prof['nome']}, collegamento verificato il <b>{now_it.strftime('%d/%m/%Y %H:%M')}</b> (ora italiana).\n"
                f"Riceverai in automatico: Protezione Profitti Spot (T1/T2), Gain Spot &gt;= € 100 netti e Report del Sabato."
            )
            ok = _invia_telegram(bot_token, cid, msg_test)
            print(f"[TEST] {u_key}: {'OK' if ok else 'ERRORE'}")
        return 0

    mode_eff = args.mode
    if mode_eff == "auto":
        # Sabato 09:00–12:00 italiane -> Report Settimanale
        if oggi_d.weekday() == 5:
            if 9 * 60 <= hm <= 12 * 60:
                mode_eff = "sabato"
            else:
                print(f"[AUTO] Sabato {now_it.strftime('%H:%M')} fuori finestra Report (09:00-12:00): uscita.")
                return 0
        # Domenica -> nessuna azione
        elif oggi_d.weekday() == 6:
            print("[AUTO] Domenica (mercati chiusi): uscita.")
            return 0
        # Lun–Ven -> verifica festività USA e finestra Wall Street (15:30–22:15 o 19:15 ridotto)
        else:
            chiusure, orari_ridotti = _get_calendario_nyse_anno(oggi_d.year)
            if oggi_d in chiusure:
                print(f"[AUTO] Borsa USA chiusa oggi ({chiusure[oggi_d]}): uscita.")
                return 0
            fine_hm = 19 * 60 + 15 if oggi_d in orari_ridotti else 22 * 60 + 15
            if 15 * 60 + 30 <= hm <= fine_hm:
                mode_eff = "intraday"
            else:
                print(f"[AUTO] {now_it.strftime('%H:%M')} italiane fuori fascia Wall Street: uscita.")
                return 0

    state = _carica_json(STATE_FILE.name, {})
    if not isinstance(state, dict):
        state = {}

    if mode_eff == "intraday":
        mod = esegui_intraday(bot_token, state, profili_attivi)
    elif mode_eff == "sabato":
        mod = esegui_report_sabato(bot_token, state, profili_attivi, forza=(args.mode == "sabato"))
    else:
        mod = False

    if mod:
        _salva_stato(state)
        print(f"[MONITOR] Stato aggiornato in {STATE_FILE.name}.")
    else:
        print("[MONITOR] Nessuna nuova notifica da salvare.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
