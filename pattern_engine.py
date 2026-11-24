# -*- coding: utf-8 -*-
"""
Motore di rilevamento figure grafiche ad alta probabilità (Pattern Engine)
per MATRIX DVMS.

Caratteristiche principali:
- Analisi basata su pivot reali distanziati almeno 5-7 candele.
- Regole anti-ritardo: solo Pre-Breakout (-3.0%..0%) o Breakout fresco (0%..+3.5% con volumi >= 1.35x).
- Filtri qualità: RSI <= 72, titolo non esteso, R/R >= 1.8, controllo vicinanza earnings (< 5gg).
- Soglia dinamica di confidenza: >= 75/100 in regime normale, >= 82/100 se SPY è ribassista.
- Classificazione operativa in 4 categorie distinte per il Riepilogo Operativo.
- Tracciamento delle 3 linee orizzontali tratteggiate (Trigger Y, Target, Stop) sui grafici Plotly.
"""

from datetime import datetime
import numpy as np
import pandas as pd


# ==============================================================================
# COSTANTI DI CONFIGURAZIONE E CATEGORIE ALERT
# ==============================================================================
SOGLIA_SCORE_NORMALE = 75
SOGLIA_SCORE_RIBASSISTA = 82
MIN_RR = 1.8
MAX_RSI_BUY = 72.0
MAX_DIST_EMA20_BUY_PCT = 3.5       # Estensione massima consentita sopra EMA(20) giornaliera per tutti i BUY
MAX_GAIN_30G_SENZA_BASE_PCT = 15.0 # Corsa massima in 30 candele senza fascia stretta di 5 chiusure (< 4%) negli ultimi 10gg
MIN_CHIUSURE_FASCIA_STRETTA = 5    # Almeno 5 chiusure consecutive strette
FINESTRA_FASCIA_STRETTA_GG = 10    # Finestra recente in cui cercare le 5 chiusure strette
MAX_ESCURSIONE_FASCIA_PCT = 4.0    # Escursione massima (< 4%) delle 5 chiusure consecutive
MIN_GIORNI_BASE_CONSOLIDAMENTO = 5 # Durata minima (in candele) per base o manico Cup & Handle
LOOKBACK_PENDENZA_SMA50 = 10       # Candele di confronto per inclinazione positiva della SMA 50
PRE_BREAKOUT_MIN_PCT = -3.0
BREAKOUT_MAX_PCT = 3.5
MIN_VOL_RATIO_BREAKOUT = 1.35
MIN_DISTANZA_PIVOT = 6  # Distanza minima tra pivot reali (5-7 candele)

# Soglie per Priorità Portafoglio, Confluenza S-Score e Setup Irrinunciabile
MIN_SSCORE_NUOVO_STD = 75          # Confluenza minima S-Score per BUY NUOVO ACQUISTO (Top 3)
MAX_TOP_NUOVI_ACQUISTI = 3         # Numero massimo di nuovi acquisti in assenza di alert portafoglio
MIN_CONF_IRRINUNCIABILE = 92       # Confidenza minima per Setup Irrinunciabile
MIN_SSCORE_IRRINUNCIABILE = 85     # S-Score minimo per Setup Irrinunciabile
MIN_RR_IRRINUNCIABILE = 2.5        # R/R minimo per Setup Irrinunciabile
BANNER_PRIORITA_PORTAFOGLIO = (
    "🎯 PRIORITÀ PORTAFOGLIO: hai opportunità aperte su titoli già in portafoglio. "
    "Vengono mostrati solo eventuali nuovi acquisti fuori scala (Irrinunciabili)."
)

FIGURE_CONTINUAZIONE_BUY = {
    "VCP (Contrazione Volatilità)",
    "Triangolo Ascendente",
    "Cup & Handle",
    "Flat Base",
    "Bull Flag",
}

FIGURE_INVERSIONE_MEDIAZIONE = {
    "Doppio Minimo (W)",
    "Riconquista SMA 20 + Div. RSI",
}


# ==============================================================================
# INDICATORI TECNICI E RILEVAMENTO PIVOT REALI
# ==============================================================================
def _calcola_indicatori(df):
    """Calcola gli indicatori tecnici necessari su una copia pulita del DataFrame OHLCV."""
    d = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).copy()
    if len(d) < 60:
        return None

    # Medie mobili semplici, esponenziali e volumi medi
    d["EMA_10"] = d["Close"].ewm(span=10, adjust=False).mean()
    d["EMA_20"] = d["Close"].ewm(span=20, adjust=False).mean()
    d["SMA_20"] = d["Close"].rolling(window=20).mean()
    d["SMA_50"] = d["Close"].rolling(window=50).mean()
    d["SMA_200"] = d["Close"].rolling(window=min(200, len(d))).mean()
    d["Vol_Media_20"] = d["Volume"].rolling(window=20).mean()

    # RSI a 14 periodi con protezione divisione per zero
    delta = d["Close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    d["RSI"] = (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)

    # True Range e ATR a 14 periodi
    prev_close = d["Close"].shift(1)
    tr = pd.concat(
        [
            d["High"] - d["Low"],
            (d["High"] - prev_close).abs(),
            (d["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    d["ATR_14"] = tr.rolling(window=14).mean()

    return d


def trova_pivot(df, ordine=3, min_distanza=MIN_DISTANZA_PIVOT):
    """
    Individua pivot high e pivot low reali usando una finestra simmetrica
    e applica una spaziatura minima di almeno 5-7 candele tra pivot dello stesso tipo.
    Restituisce due liste di tuple: (indice_posizionale, prezzo).
    """
    highs = df["High"].to_numpy(dtype=float)
    lows = df["Low"].to_numpy(dtype=float)
    n = len(df)

    raw_highs = []
    raw_lows = []
    for i in range(ordine, n - ordine):
        win_h = highs[i - ordine : i + ordine + 1]
        win_l = lows[i - ordine : i + ordine + 1]
        if highs[i] == np.max(win_h) and np.isfinite(highs[i]):
            raw_highs.append((i, float(highs[i])))
        if lows[i] == np.min(win_l) and np.isfinite(lows[i]):
            raw_lows.append((i, float(lows[i])))

    # Filtra i massimi troppo vicini mantenendo il picco più alto
    pivot_highs = []
    for idx, val in raw_highs:
        if not pivot_highs:
            pivot_highs.append((idx, val))
        elif idx - pivot_highs[-1][0] < min_distanza:
            if val > pivot_highs[-1][1]:
                pivot_highs[-1] = (idx, val)
        else:
            pivot_highs.append((idx, val))

    # Filtra i minimi troppo vicini mantenendo il minimo più profondo
    pivot_lows = []
    for idx, val in raw_lows:
        if not pivot_lows:
            pivot_lows.append((idx, val))
        elif idx - pivot_lows[-1][0] < min_distanza:
            if val < pivot_lows[-1][1]:
                pivot_lows[-1] = (idx, val)
        else:
            pivot_lows.append((idx, val))

    return pivot_highs, pivot_lows


def _verifica_divergenza_rialzista_rsi(df, pivot_lows, lookback_candele=65):
    """
    Verifica se gli ultimi due pivot low reali recenti mostrano una divergenza rialzista su RSI:
    secondo minimo di prezzo più basso o quasi uguale al primo, ma RSI nettamente più alto.
    """
    n = len(df)
    lows_rec = [(i, p) for (i, p) in pivot_lows if i >= n - lookback_candele]
    if len(lows_rec) < 2:
        return False, None, None

    (i1, p1), (i2, p2) = lows_rec[-2], lows_rec[-1]
    if i2 - i1 < MIN_DISTANZA_PIVOT:
        return False, None, None

    rsi_1 = float(df["RSI"].iloc[i1])
    rsi_2 = float(df["RSI"].iloc[i2])

    # Prezzo sul secondo minimo <= primo (+2% tolleranza doppio minimo) e RSI cresciuto almeno di 2.5 punti
    if p2 <= p1 * 1.025 and rsi_2 >= rsi_1 + 2.5 and rsi_2 >= 32.0:
        return True, (i1, p1, rsi_1), (i2, p2, rsi_2)
    return False, None, None


def _verifica_divergenza_ribassista_rsi(df, pivot_highs, lookback_candele=65):
    """Verifica divergenza ribassista RSI sugli ultimi due massimi di pivot."""
    n = len(df)
    highs_rec = [(i, p) for (i, p) in pivot_highs if i >= n - lookback_candele]
    if len(highs_rec) < 2:
        return False
    (i1, p1), (i2, p2) = highs_rec[-2], highs_rec[-1]
    if i2 - i1 < MIN_DISTANZA_PIVOT:
        return False
    rsi_1 = float(df["RSI"].iloc[i1])
    rsi_2 = float(df["RSI"].iloc[i2])
    return bool(p2 >= p1 * 0.98 and rsi_2 <= rsi_1 - 2.5)


def _controllo_anti_ritardo_buy(prezzo, trigger_y, vol_ratio):
    """
    Applica le regole anti-ritardo sul lato BUY:
    - Pre-Breakout: tra -3.0% e 0.0% dal Trigger Y.
    - Breakout fresco: tra 0.0% e +3.5% da Y con volumi >= 1.35x media 20gg.
    """
    if trigger_y is None or trigger_y <= 0:
        return False, None, 0.0
    dist_pct = ((prezzo - trigger_y) / trigger_y) * 100.0
    if PRE_BREAKOUT_MIN_PCT <= dist_pct < 0.0:
        return True, "PRE-BREAKOUT", dist_pct
    if 0.0 <= dist_pct <= BREAKOUT_MAX_PCT and vol_ratio >= MIN_VOL_RATIO_BREAKOUT:
        return True, "BREAKOUT FRESCO", dist_pct
    return False, None, dist_pct


def _controllo_anti_ritardo_sell(prezzo, trigger_y, vol_ratio, richiede_volumi_alti=False):
    """
    Applica la finestra operativa tempestiva sul lato SELL:
    - Rottura fresca sotto Y fino a -4.5% (con volumi alti se richiesto).
    - Test imminente di rottura fino a +2.5% sopra Y.
    """
    if trigger_y is None or trigger_y <= 0:
        return False, None, 0.0
    dist_pct = ((prezzo - trigger_y) / trigger_y) * 100.0
    if -4.5 <= dist_pct <= 0.0:
        if richiede_volumi_alti and vol_ratio < MIN_VOL_RATIO_BREAKOUT:
            return False, None, dist_pct
        return True, "ROTTURA RIBASSISTA", dist_pct
    if 0.0 < dist_pct <= 2.5 and not richiede_volumi_alti:
        return True, "TEST SUPPORTO", dist_pct
    return False, None, dist_pct


def _ha_fascia_stretta_5_chiusure_in_10gg(
    df,
    giorni_stretta=MIN_CHIUSURE_FASCIA_STRETTA,
    finestra_giorni=FINESTRA_FASCIA_STRETTA_GG,
    max_escursione_pct=MAX_ESCURSIONE_FASCIA_PCT,
):
    """
    Verifica se negli ultimi `finestra_giorni` giorni esistono almeno `giorni_stretta`
    chiusure consecutive contenute dentro una fascia stretta (< `max_escursione_pct`% di escursione).
    Serve a distinguere un vero consolidamento stretto da un titolo già corso per settimane senza pausa.
    """
    if len(df) < giorni_stretta:
        return False
    chiusure = df["Close"].iloc[-finestra_giorni:].to_numpy(dtype=float)
    if len(chiusure) < giorni_stretta:
        return False
    for start in range(0, len(chiusure) - giorni_stretta + 1):
        blocco = chiusure[start : start + giorni_stretta]
        if not np.all(np.isfinite(blocco)):
            continue
        c_min = float(np.min(blocco))
        c_max = float(np.max(blocco))
        if c_min > 0 and ((c_max - c_min) / c_min) * 100.0 < max_escursione_pct:
            return True
    return False


def _passa_filtro_weinstein_buy(df, trigger_y):
    """
    Filtro Trend Weinstein obbligatorio per BUY NUOVO ACQUISTO e BUY INCREMENTO (+):
    1) Prezzo corrente oppure Trigger Y strettamente sopra la SMA 200 giornaliera.
    2) SMA 50 inclinata al rialzo (SMA 50 oggi > SMA 50 di 10 giorni fa).
    """
    if len(df) < 50 + LOOKBACK_PENDENZA_SMA50:
        return False

    prezzo = float(df["Close"].iloc[-1])
    sma200_val = df["SMA_200"].iloc[-1]
    sma50_oggi = df["SMA_50"].iloc[-1]
    sma50_prec = df["SMA_50"].iloc[-1 - LOOKBACK_PENDENZA_SMA50]

    if pd.isna(sma200_val) or pd.isna(sma50_oggi) or pd.isna(sma50_prec):
        return False

    sma200 = float(sma200_val)
    if sma200 <= 0:
        return False

    # Condizione 1: prezzo corrente oppure Trigger Y sopra la SMA 200
    if max(prezzo, float(trigger_y or 0.0)) <= sma200:
        return False

    # Condizione 2: SMA 50 inclinata positivamente rispetto a 10 giorni fa
    if float(sma50_oggi) <= float(sma50_prec):
        return False

    return True


def _titolo_esteso_buy(df):
    """
    Filtri istituzionali anti-estensione per qualsiasi segnale BUY:
    - RSI > 72
    - Prezzo corrente oltre +3.5% sopra la EMA(20) giornaliera
    - Corsa > +15% nelle ultime 30 candele senza almeno 5 chiusure consecutive in fascia stretta (< 4%) negli ultimi 10gg
    - Estensione estrema sopra SMA 50 (> +22%)
    """
    prezzo = float(df["Close"].iloc[-1])
    rsi = float(df["RSI"].iloc[-1])
    ema20 = float(df["EMA_20"].iloc[-1]) if pd.notna(df["EMA_20"].iloc[-1]) else prezzo
    sma50 = float(df["SMA_50"].iloc[-1]) if pd.notna(df["SMA_50"].iloc[-1]) else prezzo

    if rsi > MAX_RSI_BUY:
        return True
    if ema20 > 0 and ((prezzo / ema20) - 1.0) * 100.0 > MAX_DIST_EMA20_BUY_PCT:
        return True
    if sma50 > 0 and ((prezzo / sma50) - 1.0) * 100.0 > 22.0:
        return True

    # Scarta titoli già corsi > +15% nelle ultime 30 candele senza pausa stretta (5 chiusure < 4% negli ultimi 10gg)
    if len(df) >= 31:
        close_30 = float(df["Close"].iloc[-31])
        low_30 = float(df["Low"].iloc[-30:].min())
        gain_close_30 = ((prezzo / close_30) - 1.0) * 100.0 if close_30 > 0 else 0.0
        gain_low_30 = ((prezzo / low_30) - 1.0) * 100.0 if low_30 > 0 else 0.0
        if max(gain_close_30, gain_low_30) > MAX_GAIN_30G_SENZA_BASE_PCT:
            if not _ha_fascia_stretta_5_chiusure_in_10gg(df):
                return True

    return False


def _calcola_rr_e_valida(lato, prezzo, trigger_y, target, stop):
    """
    Calcola R/R conservativo e verifica il vincolo R/R >= 1.8.
    Restituisce (valido, rr, target_pct, stop_pct).
    """
    if trigger_y <= 0 or target <= 0 or stop <= 0:
        return False, 0.0, 0.0, 0.0

    if lato == "BUY":
        entry_ref = max(prezzo, trigger_y)
        if stop >= entry_ref * 0.99 or target <= entry_ref * 1.02:
            return False, 0.0, 0.0, 0.0
        rischio = entry_ref - stop
        rendimento = target - entry_ref
        rr = rendimento / rischio if rischio > 0 else 0.0
        target_pct = ((target - entry_ref) / entry_ref) * 100.0
        stop_pct = ((stop - entry_ref) / entry_ref) * 100.0
        return (rr >= MIN_RR and abs(stop_pct) <= 16.0), round(rr, 2), round(target_pct, 1), round(stop_pct, 1)

    # Lato SELL: target sotto l'ingresso, stop sopra l'ingresso
    entry_ref = min(prezzo, trigger_y)
    if stop <= entry_ref * 1.01 or target >= entry_ref * 0.98:
        return False, 0.0, 0.0, 0.0
    rischio = stop - entry_ref
    rendimento = entry_ref - target
    rr = rendimento / rischio if rischio > 0 else 0.0
    target_pct = ((target - entry_ref) / entry_ref) * 100.0  # Negativo (es. -12.5%)
    stop_pct = ((stop - entry_ref) / entry_ref) * 100.0      # Positivo (es. +5.0%)
    return (rr >= MIN_RR and stop_pct <= 15.0), round(rr, 2), round(target_pct, 1), round(stop_pct, 1)


# ==============================================================================
# DETECTOR FIGURE LATO BUY
# ==============================================================================
def _rileva_vcp(df, pivot_highs, pivot_lows, vol_ratio):
    """Rileva VCP: contrazione progressiva di volatilità, ritracciamenti e volumi."""
    n = len(df)
    if n < 70:
        return None

    prezzo = float(df["Close"].iloc[-1])
    sma50 = float(df["SMA_50"].iloc[-1]) if pd.notna(df["SMA_50"].iloc[-1]) else 0.0
    sma200 = float(df["SMA_200"].iloc[-1]) if pd.notna(df["SMA_200"].iloc[-1]) else 0.0
    if sma200 > 0 and prezzo < sma200 * 0.98:
        return None

    # Analizza la base degli ultimi 65 giorni suddivisa in 3 segmenti temporali
    base = df.tail(65)
    seg1 = base.iloc[:22]
    seg2 = base.iloc[22:44]
    seg3 = base.iloc[44:]

    amp1 = ((float(seg1["High"].max()) - float(seg1["Low"].min())) / float(seg1["High"].max())) * 100.0
    amp2 = ((float(seg2["High"].max()) - float(seg2["Low"].min())) / float(seg2["High"].max())) * 100.0
    amp3 = ((float(seg3["High"].max()) - float(seg3["Low"].min())) / float(seg3["High"].max())) * 100.0

    # Contrazione progressiva reale: prima oscillazione ampia, ultima stretta
    if not (amp1 >= 9.0 and amp1 > amp2 * 1.12 and amp2 > amp3 * 1.10 and amp3 <= 8.5):
        return None

    # Verifica pivot reali dentro la base
    highs_base = [(i, p) for (i, p) in pivot_highs if i >= n - 65]
    lows_base = [(i, p) for (i, p) in pivot_lows if i >= n - 65]
    if len(highs_base) < 2 or len(lows_base) < 2:
        return None
    # I minimi devono salire o stabilizzarsi nella parte destra della base
    if lows_base[-1][1] < lows_base[0][1] * 0.99:
        return None

    trigger_y = max(p for (_, p) in highs_base[-2:])
    ok_timing, stato_trig, dist_y = _controllo_anti_ritardo_buy(prezzo, trigger_y, vol_ratio)
    if not ok_timing:
        return None

    # Contrazione volumi nei 5 giorni precedenti rispetto alla media 20gg
    vol_5 = float(df["Volume"].iloc[-6:-1].mean())
    vol_20 = float(df["Vol_Media_20"].iloc[-1]) if pd.notna(df["Vol_Media_20"].iloc[-1]) else 1.0
    vol_dryup = vol_20 > 0 and (vol_5 / vol_20) <= 0.92

    if stato_trig == "PRE-BREAKOUT" and not vol_dryup:
        return None

    atr = float(df["ATR_14"].iloc[-1]) if pd.notna(df["ATR_14"].iloc[-1]) else prezzo * 0.02
    stop = min(float(seg3["Low"].min()), lows_base[-1][1]) - 0.35 * atr
    altezza_base = max(trigger_y - float(base["Low"].min()), (trigger_y - stop) * 2.2)
    target = trigger_y + max(altezza_base, (trigger_y - stop) * 2.1)

    ok_rr, rr, tgt_pct, stp_pct = _calcola_rr_e_valida("BUY", prezzo, trigger_y, target, stop)
    if not ok_rr:
        return None

    score = 68
    if amp3 <= 6.0:
        score += 7
    if vol_dryup:
        score += 6
    if stato_trig == "BREAKOUT FRESCO" and vol_ratio >= 1.50:
        score += 8
    elif stato_trig == "BREAKOUT FRESCO":
        score += 5
    if sma50 > 0 and prezzo >= sma50:
        score += 5
    if sma200 > 0 and sma50 > sma200:
        score += 5
    if rr >= 2.5:
        score += 4

    motivo = f"Contrazioni {amp1:.1f}% → {amp2:.1f}% → {amp3:.1f}% con {'dry-up volumi' if vol_dryup else 'spinta volumi'}"
    return {
        "lato": "BUY",
        "figura": "VCP (Contrazione Volatilità)",
        "confidenza": min(98, int(round(score))),
        "stato_trigger": stato_trig,
        "trigger_y": round(trigger_y, 2),
        "dist_y_pct": round(dist_y, 2),
        "target_price": round(target, 2),
        "target_pct": tgt_pct,
        "stop_price": round(stop, 2),
        "stop_pct": stp_pct,
        "rr": rr,
        "motivo": motivo,
    }


def _rileva_triangolo_ascendente(df, pivot_highs, pivot_lows, vol_ratio):
    """Rileva Triangolo Ascendente: resistenza piatta (>=2 pivot high) + minimi crescenti (>=2 pivot low)."""
    n = len(df)
    if n < 60:
        return None

    prezzo = float(df["Close"].iloc[-1])
    highs_rec = [(i, p) for (i, p) in pivot_highs if i >= n - 75]
    lows_rec = [(i, p) for (i, p) in pivot_lows if i >= n - 75]
    if len(highs_rec) < 2 or len(lows_rec) < 2:
        return None

    # Trova almeno due massimi quasi allineati orizzontalmente
    h1_i, h1_p = highs_rec[-2]
    h2_i, h2_p = highs_rec[-1]
    if h2_i - h1_i < MIN_DISTANZA_PIVOT:
        return None
    if abs(h2_p - h1_p) / max(h1_p, h2_p) > 0.024:
        return None

    # Verifica minimi chiaramente crescenti
    l1_i, l1_p = lows_rec[-2]
    l2_i, l2_p = lows_rec[-1]
    if l2_i - l1_i < MIN_DISTANZA_PIVOT:
        return None
    if not (l2_p > l1_p * 1.02):
        return None

    trigger_y = max(h1_p, h2_p)
    altezza = trigger_y - l1_p
    if altezza / trigger_y < 0.06:
        return None

    ok_timing, stato_trig, dist_y = _controllo_anti_ritardo_buy(prezzo, trigger_y, vol_ratio)
    if not ok_timing:
        return None

    atr = float(df["ATR_14"].iloc[-1]) if pd.notna(df["ATR_14"].iloc[-1]) else prezzo * 0.02
    stop = l2_p - 0.35 * atr
    target = trigger_y + max(altezza, (trigger_y - stop) * 2.0)

    ok_rr, rr, tgt_pct, stp_pct = _calcola_rr_e_valida("BUY", prezzo, trigger_y, target, stop)
    if not ok_rr:
        return None

    sma50 = float(df["SMA_50"].iloc[-1]) if pd.notna(df["SMA_50"].iloc[-1]) else 0.0
    sma200 = float(df["SMA_200"].iloc[-1]) if pd.notna(df["SMA_200"].iloc[-1]) else 0.0

    score = 67
    if len(highs_rec) >= 3 and abs(highs_rec[-3][1] - trigger_y) / trigger_y <= 0.03:
        score += 7
    if len(lows_rec) >= 3 and lows_rec[-2][1] > lows_rec[-3][1]:
        score += 5
    if stato_trig == "BREAKOUT FRESCO":
        score += 8 if vol_ratio >= 1.50 else 5
    if sma50 > 0 and prezzo >= sma50:
        score += 5
    if sma200 > 0 and prezzo >= sma200:
        score += 4
    if rr >= 2.3:
        score += 4

    motivo = f"Resistenza orizzontale ~${trigger_y:.2f} con minimi crescenti (${l1_p:.2f} → ${l2_p:.2f})"
    return {
        "lato": "BUY",
        "figura": "Triangolo Ascendente",
        "confidenza": min(97, int(round(score))),
        "stato_trigger": stato_trig,
        "trigger_y": round(trigger_y, 2),
        "dist_y_pct": round(dist_y, 2),
        "target_price": round(target, 2),
        "target_pct": tgt_pct,
        "stop_price": round(stop, 2),
        "stop_pct": stp_pct,
        "rr": rr,
        "motivo": motivo,
    }


def _rileva_cup_and_handle(df, pivot_highs, pivot_lows, vol_ratio):
    """Rileva Cup & Handle: tazza arrotondata (12%-38%) seguita da manico stretto (5-25 candele)."""
    n = len(df)
    if n < 85:
        return None

    prezzo = float(df["Close"].iloc[-1])
    win_start = max(0, n - 150)

    # Cerca bordo destro recente lasciando almeno 5 candele reali di manico dopo il picco
    candidati_dx = [
        (i, p)
        for (i, p) in pivot_highs
        if n - 26 <= i <= n - (MIN_GIORNI_BASE_CONSOLIDAMENTO + 1)
    ]
    if not candidati_dx:
        return None
    dx_i, dx_p = max(candidati_dx, key=lambda x: x[1])

    # Cerca bordo sinistro almeno 20 candele prima del bordo destro su livello simile
    candidati_sx = [
        (i, p)
        for (i, p) in pivot_highs
        if win_start <= i <= dx_i - 20 and abs(p - dx_p) / max(p, dx_p) <= 0.05
    ]
    if not candidati_sx:
        return None
    sx_i, sx_p = max(candidati_sx, key=lambda x: x[1])

    # Fondo della tazza tra bordo sinistro e bordo destro
    cup_slice = df.iloc[sx_i : dx_i + 1]
    cup_low = float(cup_slice["Low"].min())
    bordo = max(sx_p, dx_p)
    prof_cup_pct = ((bordo - cup_low) / bordo) * 100.0
    if not (12.0 <= prof_cup_pct <= 38.0):
        return None

    # Verifica manico di almeno 5 candele complete, stretto e nella metà superiore della tazza
    handle_slice = df.iloc[dx_i + 1 :]
    if len(handle_slice) < MIN_GIORNI_BASE_CONSOLIDAMENTO:
        return None
    handle_low = float(handle_slice["Low"].min())
    prof_handle_pct = ((dx_p - handle_low) / dx_p) * 100.0
    if not (2.0 <= prof_handle_pct <= 12.0):
        return None
    if handle_low < cup_low + (bordo - cup_low) * 0.55:
        return None

    trigger_y = dx_p
    ok_timing, stato_trig, dist_y = _controllo_anti_ritardo_buy(prezzo, trigger_y, vol_ratio)
    if not ok_timing:
        return None

    atr = float(df["ATR_14"].iloc[-1]) if pd.notna(df["ATR_14"].iloc[-1]) else prezzo * 0.02
    stop = handle_low - 0.35 * atr
    target = trigger_y + (bordo - cup_low)

    ok_rr, rr, tgt_pct, stp_pct = _calcola_rr_e_valida("BUY", prezzo, trigger_y, target, stop)
    if not ok_rr:
        return None

    vol_handle = float(handle_slice["Volume"].iloc[:-1].mean()) if len(handle_slice) > 2 else float(handle_slice["Volume"].mean())
    vol_cup = float(cup_slice["Volume"].mean())
    vol_calmi_manico = vol_cup > 0 and vol_handle < vol_cup * 0.92

    score = 70
    if vol_calmi_manico:
        score += 7
    if prof_handle_pct <= 8.0:
        score += 5
    if stato_trig == "BREAKOUT FRESCO":
        score += 8 if vol_ratio >= 1.50 else 5
    sma200 = float(df["SMA_200"].iloc[-1]) if pd.notna(df["SMA_200"].iloc[-1]) else 0.0
    if sma200 > 0 and prezzo > sma200:
        score += 5
    if rr >= 2.5:
        score += 4

    motivo = f"Tazza (-{prof_cup_pct:.1f}%) + manico {len(handle_slice)}gg (-{prof_handle_pct:.1f}%)"
    return {
        "lato": "BUY",
        "figura": "Cup & Handle",
        "confidenza": min(98, int(round(score))),
        "stato_trigger": stato_trig,
        "trigger_y": round(trigger_y, 2),
        "dist_y_pct": round(dist_y, 2),
        "target_price": round(target, 2),
        "target_pct": tgt_pct,
        "stop_price": round(stop, 2),
        "stop_pct": stp_pct,
        "rr": rr,
        "motivo": motivo,
    }


def _rileva_flat_base(df, pivot_highs, pivot_lows, vol_ratio):
    """Rileva Flat Base: consolidamento laterale <= 15% per 20-50 candele dopo un impulso rialzista."""
    n = len(df)
    if n < 80:
        return None

    prezzo = float(df["Close"].iloc[-1])
    base = df.iloc[-35:-1] if n >= 36 else df.iloc[:-1]
    pre_base = df.iloc[max(0, n - 90) : max(1, n - 35)]

    max_base = float(base["High"].max())
    min_base = float(base["Low"].min())
    amp_base_pct = ((max_base - min_base) / max_base) * 100.0
    if not (4.0 <= amp_base_pct <= 15.0):
        return None

    # Richiede un trend precedente costruttivo (almeno +14% dal minimo pre-base)
    min_pre = float(pre_base["Low"].min())
    if min_pre <= 0 or ((max_base / min_pre) - 1.0) * 100.0 < 14.0:
        return None

    # Almeno 2 pivot reali nella zona della base per confermare consolidamento vero
    piv_in_base = [i for (i, _) in pivot_highs + pivot_lows if i >= n - 40]
    if len(piv_in_base) < 2:
        return None

    trigger_y = max_base
    ok_timing, stato_trig, dist_y = _controllo_anti_ritardo_buy(prezzo, trigger_y, vol_ratio)
    if not ok_timing:
        return None

    atr = float(df["ATR_14"].iloc[-1]) if pd.notna(df["ATR_14"].iloc[-1]) else prezzo * 0.02
    stop = min_base - 0.30 * atr
    altezza_base = max_base - min_base
    target = trigger_y + max(altezza_base * 2.0, (trigger_y - stop) * 2.0)

    ok_rr, rr, tgt_pct, stp_pct = _calcola_rr_e_valida("BUY", prezzo, trigger_y, target, stop)
    if not ok_rr:
        return None

    sma50 = float(df["SMA_50"].iloc[-1]) if pd.notna(df["SMA_50"].iloc[-1]) else 0.0
    sma200 = float(df["SMA_200"].iloc[-1]) if pd.notna(df["SMA_200"].iloc[-1]) else 0.0
    if sma50 > 0 and prezzo < sma50 * 0.97:
        return None

    score = 67
    if amp_base_pct <= 11.0:
        score += 6
    if sma50 > 0 and prezzo >= sma50:
        score += 5
    if sma200 > 0 and sma50 > sma200:
        score += 5
    if stato_trig == "BREAKOUT FRESCO":
        score += 8 if vol_ratio >= 1.50 else 5
    if rr >= 2.2:
        score += 4

    motivo = f"Base piatta ordinata (escursione {amp_base_pct:.1f}%) sopra supporti chiave"
    return {
        "lato": "BUY",
        "figura": "Flat Base",
        "confidenza": min(96, int(round(score))),
        "stato_trigger": stato_trig,
        "trigger_y": round(trigger_y, 2),
        "dist_y_pct": round(dist_y, 2),
        "target_price": round(target, 2),
        "target_pct": tgt_pct,
        "stop_price": round(stop, 2),
        "stop_pct": stp_pct,
        "rr": rr,
        "motivo": motivo,
    }


def _rileva_bull_flag(df, pivot_highs, pivot_lows, vol_ratio):
    """Rileva Bull Flag: asta rialzista forte (>= +10%) seguita da pullback compatto a volumi ridotti."""
    n = len(df)
    if n < 50:
        return None

    prezzo = float(df["Close"].iloc[-1])

    # Cerca un pivot high recente che segni la cima dell'asta (tra 5 e 16 candele fa)
    cime_asta = [(i, p) for (i, p) in pivot_highs if n - 17 <= i <= n - 5]
    if not cime_asta:
        return None
    peak_i, peak_p = max(cime_asta, key=lambda x: x[1])

    # Asta nei 15 giorni precedenti alla cima
    pole_start = max(0, peak_i - 18)
    pole_slice = df.iloc[pole_start : peak_i + 1]
    pole_low = float(pole_slice["Low"].min())
    if pole_low <= 0:
        return None
    pole_gain_pct = ((peak_p - pole_low) / pole_low) * 100.0
    if pole_gain_pct < 10.0:
        return None

    # Bandiera dalla cima fino a oggi (esclusa eventualmente l'ultima candela di breakout)
    flag_slice = df.iloc[peak_i : n - 1] if n - 1 > peak_i else df.iloc[peak_i:]
    if len(flag_slice) < 4:
        return None
    flag_low = float(flag_slice["Low"].min())
    retrace_pct = ((peak_p - flag_low) / (peak_p - pole_low)) * 100.0
    prof_flag_pct = ((peak_p - flag_low) / peak_p) * 100.0
    if not (retrace_pct <= 50.0 and 2.0 <= prof_flag_pct <= 11.5):
        return None

    # Contrazione dei volumi nella bandiera rispetto all'asta
    vol_pole = float(pole_slice["Volume"].mean())
    vol_flag = float(flag_slice["Volume"].mean())
    vol_ridotti = vol_pole > 0 and vol_flag < vol_pole * 0.90

    trigger_y = float(flag_slice["High"].tail(min(6, len(flag_slice))).max())
    ok_timing, stato_trig, dist_y = _controllo_anti_ritardo_buy(prezzo, trigger_y, vol_ratio)
    if not ok_timing:
        return None

    atr = float(df["ATR_14"].iloc[-1]) if pd.notna(df["ATR_14"].iloc[-1]) else prezzo * 0.02
    stop = flag_low - 0.30 * atr
    target = trigger_y + (peak_p - pole_low) * 0.90

    ok_rr, rr, tgt_pct, stp_pct = _calcola_rr_e_valida("BUY", prezzo, trigger_y, target, stop)
    if not ok_rr:
        return None

    score = 68
    if pole_gain_pct >= 15.0:
        score += 5
    if vol_ridotti:
        score += 7
    if retrace_pct <= 38.0:
        score += 5
    if stato_trig == "BREAKOUT FRESCO":
        score += 8 if vol_ratio >= 1.50 else 5
    if rr >= 2.4:
        score += 4

    motivo = f"Asta +{pole_gain_pct:.1f}% + bandiera ordinata (-{prof_flag_pct:.1f}%)"
    return {
        "lato": "BUY",
        "figura": "Bull Flag",
        "confidenza": min(97, int(round(score))),
        "stato_trigger": stato_trig,
        "trigger_y": round(trigger_y, 2),
        "dist_y_pct": round(dist_y, 2),
        "target_price": round(target, 2),
        "target_pct": tgt_pct,
        "stop_price": round(stop, 2),
        "stop_pct": stp_pct,
        "rr": rr,
        "motivo": motivo,
    }


def _rileva_doppio_minimo_w(df, pivot_highs, pivot_lows, vol_ratio):
    """Rileva Doppio Minimo ('W') con secondo minimo confermato e neckline chiara."""
    n = len(df)
    if n < 55:
        return None

    prezzo = float(df["Close"].iloc[-1])
    lows_rec = [(i, p) for (i, p) in pivot_lows if i >= n - 85]
    if len(lows_rec) < 2:
        return None

    (i1, l1), (i2, l2) = lows_rec[-2], lows_rec[-1]
    if i2 - i1 < 7 or i2 >= n - 2:
        return None
    # I due minimi devono trovarsi su una zona di supporto analoga (entro 4.5%)
    if abs(l2 - l1) / min(l1, l2) > 0.045:
        return None

    # Trova il massimo intermedio (neckline) tra i due minimi
    highs_between = [(i, p) for (i, p) in pivot_highs if i1 < i < i2]
    if highs_between:
        neck_i, neckline = max(highs_between, key=lambda x: x[1])
    else:
        neckline = float(df["High"].iloc[i1 : i2 + 1].max())
        neck_i = i1 + int(np.argmax(df["High"].iloc[i1 : i2 + 1].to_numpy()))

    altezza_w = neckline - min(l1, l2)
    if altezza_w / neckline < 0.055:
        return None

    # Conferma secondo minimo: rimbalzo reale da L2 e nessuna caduta libera
    if prezzo < l2 * 1.03:
        return None
    if float(df["Low"].iloc[-3:].min()) < min(l1, l2) * 0.99:
        return None

    trigger_y = neckline
    ok_timing, stato_trig, dist_y = _controllo_anti_ritardo_buy(prezzo, trigger_y, vol_ratio)
    if not ok_timing:
        return None

    atr = float(df["ATR_14"].iloc[-1]) if pd.notna(df["ATR_14"].iloc[-1]) else prezzo * 0.02
    stop = min(l1, l2) - 0.35 * atr
    # Proiezione misurata minima 1.85x rischio o altezza W (per garantire setup profittevoli)
    target = trigger_y + max(altezza_w * 1.25, (trigger_y - stop) * 1.95)

    ok_rr, rr, tgt_pct, stp_pct = _calcola_rr_e_valida("BUY", prezzo, trigger_y, target, stop)
    if not ok_rr:
        return None

    div_rsi, _, _ = _verifica_divergenza_rialzista_rsi(df, pivot_lows)
    sma20 = float(df["SMA_20"].iloc[-1]) if pd.notna(df["SMA_20"].iloc[-1]) else 0.0

    score = 70
    if div_rsi:
        score += 9
    if l2 >= l1 * 0.995:
        score += 4
    if sma20 > 0 and prezzo > sma20:
        score += 5
    if stato_trig == "BREAKOUT FRESCO":
        score += 7 if vol_ratio >= 1.50 else 5
    if rr >= 2.2:
        score += 3

    motivo = f"Doppio minimo confermato (${l1:.2f} / ${l2:.2f}), neckline ${neckline:.2f}" + (" + divergenza RSI" if div_rsi else "")
    return {
        "lato": "BUY",
        "figura": "Doppio Minimo (W)",
        "confidenza": min(98, int(round(score))),
        "stato_trigger": stato_trig,
        "trigger_y": round(trigger_y, 2),
        "dist_y_pct": round(dist_y, 2),
        "target_price": round(target, 2),
        "target_pct": tgt_pct,
        "stop_price": round(stop, 2),
        "stop_pct": stp_pct,
        "rr": rr,
        "motivo": motivo,
    }


def _rileva_riconquista_sma20_div_rsi(df, pivot_highs, pivot_lows, vol_ratio):
    """
    Rileva inversione confermata: riconquista SMA 20 con volumi + divergenza rialzista RSI.
    Richiesta specifica per autorizzare BUY MEDIAZIONE (-) senza mai mediare in caduta libera.
    """
    n = len(df)
    if n < 50:
        return None

    prezzo = float(df["Close"].iloc[-1])
    open_oggi = float(df["Open"].iloc[-1])
    sma20 = float(df["SMA_20"].iloc[-1]) if pd.notna(df["SMA_20"].iloc[-1]) else 0.0
    if sma20 <= 0:
        return None

    # Deve provenire da sotto SMA 20 nei 10 giorni precedenti (vera riconquista)
    sotto_prima = int((df["Close"].iloc[-12:-2] < df["SMA_20"].iloc[-12:-2]).sum())
    if sotto_prima < 4:
        return None

    # Protezione anti-caduta libera: nessun nuovo minimo negli ultimi 3 giorni e tenuta rialzista
    min_20 = float(df["Low"].iloc[-20:].min())
    min_3 = float(df["Low"].iloc[-3:].min())
    if min_3 <= min_20 * 1.005 or prezzo < min_20 * 1.025:
        return None

    # Divergenza rialzista RSI obbligatoria su pivot reali
    div_ok, p1_info, p2_info = _verifica_divergenza_rialzista_rsi(df, pivot_lows)
    if not div_ok or not p2_info:
        return None

    trigger_y = sma20
    ok_timing, stato_trig, dist_y = _controllo_anti_ritardo_buy(prezzo, trigger_y, vol_ratio)
    if not ok_timing:
        return None

    # Per la riconquista richiediamo volumi robusti se già sopra SMA 20, oppure pressione compratrice in pre-breakout
    if stato_trig == "BREAKOUT FRESCO" and prezzo < open_oggi:
        return None

    atr = float(df["ATR_14"].iloc[-1]) if pd.notna(df["ATR_14"].iloc[-1]) else prezzo * 0.02
    stop = p2_info[1] - 0.35 * atr

    # Target verso la resistenza di swing precedente o SMA 50 (minimo R/R >= 1.8)
    highs_rec = [p for (i, p) in pivot_highs if i >= n - 60 and p > trigger_y * 1.06]
    sma50 = float(df["SMA_50"].iloc[-1]) if pd.notna(df["SMA_50"].iloc[-1]) else 0.0
    cand_tgt = max(highs_rec) if highs_rec else max(sma50, trigger_y * 1.12)
    target = max(cand_tgt, trigger_y + (trigger_y - stop) * 2.0)

    ok_rr, rr, tgt_pct, stp_pct = _calcola_rr_e_valida("BUY", prezzo, trigger_y, target, stop)
    if not ok_rr:
        return None

    score = 72
    if stato_trig == "BREAKOUT FRESCO" and vol_ratio >= 1.50:
        score += 9
    elif stato_trig == "BREAKOUT FRESCO":
        score += 6
    if p2_info[2] - p1_info[2] >= 5.0:
        score += 6
    if prezzo > open_oggi:
        score += 4
    if rr >= 2.2:
        score += 4

    motivo = f"Riconquista SMA 20 (${sma20:.2f}) con divergenza rialzista RSI ({p1_info[2]:.0f} → {p2_info[2]:.0f})"
    return {
        "lato": "BUY",
        "figura": "Riconquista SMA 20 + Div. RSI",
        "confidenza": min(96, int(round(score))),
        "stato_trigger": stato_trig,
        "trigger_y": round(trigger_y, 2),
        "dist_y_pct": round(dist_y, 2),
        "target_price": round(target, 2),
        "target_pct": tgt_pct,
        "stop_price": round(stop, 2),
        "stop_pct": stp_pct,
        "rr": rr,
        "motivo": motivo,
    }


# ==============================================================================
# DETECTOR FIGURE LATO SELL (SOLO PER TITOLI IN PORTAFOGLIO)
# ==============================================================================
def _rileva_doppio_massimo_m(df, pivot_highs, pivot_lows, vol_ratio):
    """Rileva Doppio Massimo ('M') su titoli in portafoglio."""
    n = len(df)
    if n < 55:
        return None

    prezzo = float(df["Close"].iloc[-1])
    highs_rec = [(i, p) for (i, p) in pivot_highs if i >= n - 85]
    if len(highs_rec) < 2:
        return None

    (i1, h1), (i2, h2) = highs_rec[-2], highs_rec[-1]
    if i2 - i1 < 7 or i2 >= n - 2:
        return None
    if abs(h2 - h1) / max(h1, h2) > 0.038:
        return None

    # Neckline intermedia tra i due massimi
    lows_between = [(i, p) for (i, p) in pivot_lows if i1 < i < i2]
    if lows_between:
        _, neckline = min(lows_between, key=lambda x: x[1])
    else:
        neckline = float(df["Low"].iloc[i1 : i2 + 1].min())

    altezza_m = max(h1, h2) - neckline
    if altezza_m / max(h1, h2) < 0.05:
        return None

    trigger_y = neckline
    ok_timing, stato_trig, dist_y = _controllo_anti_ritardo_sell(prezzo, trigger_y, vol_ratio, richiede_volumi_alti=False)
    if not ok_timing:
        return None

    atr = float(df["ATR_14"].iloc[-1]) if pd.notna(df["ATR_14"].iloc[-1]) else prezzo * 0.02
    stop = min(max(h1, h2), float(df["High"].iloc[i2:].max())) + 0.30 * atr
    # Per avere un target protettivo leggibile e R/R >= 1.8
    target = max(0.01, trigger_y - max(altezza_m * 1.2, (stop - trigger_y) * 1.9))

    ok_rr, rr, tgt_pct, stp_pct = _calcola_rr_e_valida("SELL", prezzo, trigger_y, target, stop)
    if not ok_rr:
        return None

    div_rib = _verifica_divergenza_ribassista_rsi(df, pivot_highs)
    score = 72
    if div_rib:
        score += 8
    if stato_trig == "ROTTURA RIBASSISTA":
        score += 7 if vol_ratio >= 1.35 else 4
    if h2 <= h1:
        score += 4
    if rr >= 2.2:
        score += 4

    motivo = f"Doppio massimo (${h1:.2f} / ${h2:.2f}), neckline ${neckline:.2f}" + (" + divergenza ribassista RSI" if div_rib else "")
    return {
        "lato": "SELL",
        "figura": "Doppio Massimo (M)",
        "confidenza": min(97, int(round(score))),
        "stato_trigger": stato_trig,
        "trigger_y": round(trigger_y, 2),
        "dist_y_pct": round(dist_y, 2),
        "target_price": round(target, 2),
        "target_pct": tgt_pct,
        "stop_price": round(stop, 2),
        "stop_pct": stp_pct,
        "rr": rr,
        "motivo": motivo,
    }


def _rileva_testa_e_spalle(df, pivot_highs, pivot_lows, vol_ratio):
    """Rileva Testa e Spalle (Head & Shoulders) con 3 pivot high distinti e neckline."""
    n = len(df)
    if n < 70:
        return None

    prezzo = float(df["Close"].iloc[-1])
    highs_rec = [(i, p) for (i, p) in pivot_highs if i >= n - 110]
    if len(highs_rec) < 3:
        return None

    (i_ls, p_ls), (i_h, p_h), (i_rs, p_rs) = highs_rec[-3], highs_rec[-2], highs_rec[-1]
    if (i_h - i_ls) < MIN_DISTANZA_PIVOT or (i_rs - i_h) < MIN_DISTANZA_PIVOT:
        return None

    # Testa nettamente più alta delle due spalle, spalle su livelli comparabili
    if not (p_h > p_ls * 1.03 and p_h > p_rs * 1.03):
        return None
    if abs(p_ls - p_rs) / max(p_ls, p_rs) > 0.065:
        return None

    # Due minimi di neckline tra LS-H e H-RS
    n1 = float(df["Low"].iloc[i_ls : i_h + 1].min())
    n2 = float(df["Low"].iloc[i_h : i_rs + 1].min())
    neckline = (n1 + n2) / 2.0
    altezza = p_h - neckline
    if altezza / p_h < 0.06:
        return None

    trigger_y = neckline
    ok_timing, stato_trig, dist_y = _controllo_anti_ritardo_sell(prezzo, trigger_y, vol_ratio, richiede_volumi_alti=False)
    if not ok_timing:
        return None

    atr = float(df["ATR_14"].iloc[-1]) if pd.notna(df["ATR_14"].iloc[-1]) else prezzo * 0.02
    stop = p_rs + 0.30 * atr
    target = max(0.01, trigger_y - max(altezza, (stop - trigger_y) * 1.9))

    ok_rr, rr, tgt_pct, stp_pct = _calcola_rr_e_valida("SELL", prezzo, trigger_y, target, stop)
    if not ok_rr:
        return None

    score = 74
    if stato_trig == "ROTTURA RIBASSISTA":
        score += 8 if vol_ratio >= 1.35 else 4
    if p_rs < p_ls:
        score += 4
    if _verifica_divergenza_ribassista_rsi(df, pivot_highs):
        score += 6
    if rr >= 2.2:
        score += 4

    motivo = f"Testa ${p_h:.2f} tra spalle ${p_ls:.2f}/${p_rs:.2f}, neckline ${neckline:.2f}"
    return {
        "lato": "SELL",
        "figura": "Testa e Spalle",
        "confidenza": min(98, int(round(score))),
        "stato_trigger": stato_trig,
        "trigger_y": round(trigger_y, 2),
        "dist_y_pct": round(dist_y, 2),
        "target_price": round(target, 2),
        "target_pct": tgt_pct,
        "stop_price": round(stop, 2),
        "stop_pct": stp_pct,
        "rr": rr,
        "motivo": motivo,
    }


def _rileva_rottura_supporto_sma50(df, pivot_lows, vol_ratio):
    """Rileva rottura di supporto chiave / SMA 50 con volumi alti (>= 1.35x)."""
    n = len(df)
    if n < 55:
        return None

    prezzo = float(df["Close"].iloc[-1])
    open_oggi = float(df["Open"].iloc[-1])
    sma50 = float(df["SMA_50"].iloc[-1]) if pd.notna(df["SMA_50"].iloc[-1]) else 0.0
    if sma50 <= 0 or vol_ratio < MIN_VOL_RATIO_BREAKOUT:
        return None

    # Determina il livello chiave violato: SMA 50 o supporto di pivot recente
    sopra_sma50_prima = int((df["Close"].iloc[-10:-1] >= df["SMA_50"].iloc[-10:-1]).sum())
    lows_prev = [p for (i, p) in pivot_lows if n - 55 <= i <= n - 6]
    sup_pivot = min(lows_prev[-2:]) if len(lows_prev) >= 2 else (lows_prev[-1] if lows_prev else 0.0)

    trigger_y = None
    desc_liv = ""
    if sopra_sma50_prima >= 4 and prezzo < sma50:
        trigger_y = sma50
        desc_liv = f"SMA 50 (${sma50:.2f})"
    elif sup_pivot > 0 and prezzo < sup_pivot and float(df["Close"].iloc[-2]) >= sup_pivot * 0.995:
        trigger_y = sup_pivot
        desc_liv = f"supporto chiave (${sup_pivot:.2f})"

    if trigger_y is None:
        return None

    ok_timing, stato_trig, dist_y = _controllo_anti_ritardo_sell(prezzo, trigger_y, vol_ratio, richiede_volumi_alti=True)
    if not ok_timing:
        return None

    atr = float(df["ATR_14"].iloc[-1]) if pd.notna(df["ATR_14"].iloc[-1]) else prezzo * 0.02
    stop = max(trigger_y, float(df["High"].iloc[-3:].max())) + 0.30 * atr
    sma200 = float(df["SMA_200"].iloc[-1]) if pd.notna(df["SMA_200"].iloc[-1]) else 0.0
    target_tecnico = sma200 if (0 < sma200 < prezzo * 0.94) else prezzo - (stop - prezzo) * 2.1
    target = max(0.01, min(target_tecnico, prezzo - (stop - prezzo) * 1.95))

    ok_rr, rr, tgt_pct, stp_pct = _calcola_rr_e_valida("SELL", prezzo, trigger_y, target, stop)
    if not ok_rr:
        return None

    score = 74
    if vol_ratio >= 1.65:
        score += 8
    elif vol_ratio >= 1.45:
        score += 5
    if prezzo < open_oggi:
        score += 5
    if float(df["RSI"].iloc[-1]) < 48.0:
        score += 4
    if rr >= 2.2:
        score += 4

    motivo = f"Rottura {desc_liv} con volumi {vol_ratio:.2f}x"
    return {
        "lato": "SELL",
        "figura": "Rottura Supporto / SMA 50",
        "confidenza": min(97, int(round(score))),
        "stato_trigger": stato_trig,
        "trigger_y": round(trigger_y, 2),
        "dist_y_pct": round(dist_y, 2),
        "target_price": round(target, 2),
        "target_pct": tgt_pct,
        "stop_price": round(stop, 2),
        "stop_pct": stp_pct,
        "rr": rr,
        "motivo": motivo,
    }


def _rileva_distribuzione_sma20(df, vol_ratio):
    """Rileva distribuzione su SMA 20 dopo una forte corsa rialzista."""
    n = len(df)
    if n < 70:
        return None

    prezzo = float(df["Close"].iloc[-1])
    sma20 = float(df["SMA_20"].iloc[-1]) if pd.notna(df["SMA_20"].iloc[-1]) else 0.0
    sma50 = float(df["SMA_50"].iloc[-1]) if pd.notna(df["SMA_50"].iloc[-1]) else 0.0
    if sma20 <= 0:
        return None

    # Verifica forte corsa precedente (>= +22% dai minimi degli ultimi 70 giorni)
    min_70 = float(df["Low"].iloc[-70:-10].min())
    max_20 = float(df["High"].iloc[-20:].max())
    if min_70 <= 0:
        return None
    corsa_pct = ((max_20 - min_70) / min_70) * 100.0
    if corsa_pct < 22.0:
        return None

    # Conta giornate di distribuzione negli ultimi 10 giorni (chiusura rossa con volumi >= 1.2x media)
    ultimi_10 = df.iloc[-10:]
    giorni_dist = int(
        (
            (ultimi_10["Close"] < ultimi_10["Open"])
            & (ultimi_10["Volume"] >= ultimi_10["Vol_Media_20"] * 1.20)
        ).sum()
    )
    if giorni_dist < 2:
        return None

    trigger_y = sma20
    ok_timing, stato_trig, dist_y = _controllo_anti_ritardo_sell(prezzo, trigger_y, vol_ratio, richiede_volumi_alti=False)
    if not ok_timing:
        return None
    # Richiede debolezza concreta (sotto SMA 20 oppure volumi in vendita oggi)
    if prezzo > sma20 and not (vol_ratio >= 1.30 and prezzo < float(df["Open"].iloc[-1])):
        return None

    atr = float(df["ATR_14"].iloc[-1]) if pd.notna(df["ATR_14"].iloc[-1]) else prezzo * 0.02
    stop = max_20 + 0.25 * atr
    target_cand = sma50 if (0 < sma50 < prezzo * 0.94) else prezzo - (stop - prezzo) * 2.0
    target = max(0.01, min(target_cand, prezzo - (stop - prezzo) * 1.9))

    ok_rr, rr, tgt_pct, stp_pct = _calcola_rr_e_valida("SELL", prezzo, trigger_y, target, stop)
    if not ok_rr:
        return None

    score = 72
    if giorni_dist >= 3:
        score += 7
    if corsa_pct >= 35.0:
        score += 5
    if stato_trig == "ROTTURA RIBASSISTA" and vol_ratio >= 1.35:
        score += 7
    elif stato_trig == "ROTTURA RIBASSISTA":
        score += 4
    if rr >= 2.2:
        score += 3

    motivo = f"Distribuzione ({giorni_dist} sedute rosse ad alti volumi) su SMA 20 dopo corsa +{corsa_pct:.0f}%"
    return {
        "lato": "SELL",
        "figura": "Distribuzione su SMA 20",
        "confidenza": min(96, int(round(score))),
        "stato_trigger": stato_trig,
        "trigger_y": round(trigger_y, 2),
        "dist_y_pct": round(dist_y, 2),
        "target_price": round(target, 2),
        "target_pct": tgt_pct,
        "stop_price": round(stop, 2),
        "stop_pct": stp_pct,
        "rr": rr,
        "motivo": motivo,
    }


def _rileva_perdita_ema10_trailing_profit(df, vol_ratio, pnl_pct):
    """
    Segnale anticipato di protezione profitti (solo lato SELL su titoli in Portafoglio):
    - Guadagno aperto >= +15%.
    - Titolo sopra la EMA 10 giornaliera per almeno 7 sedute consecutive precedenti.
    - Chiusura odierna sotto la EMA 10 giornaliera.
    - Conferma con volumi >= 1.2x media 20gg oppure chiusura nel terzo inferiore della candela.
    """
    if pnl_pct is None or float(pnl_pct) < 15.0:
        return None
    if len(df) < 20 or pd.isna(df["EMA_10"].iloc[-1]):
        return None

    prezzo = float(df["Close"].iloc[-1])
    ema10 = float(df["EMA_10"].iloc[-1])
    if ema10 <= 0 or prezzo >= ema10:
        return None

    # Conta le sedute consecutive immediatamente precedenti a oggi chiuse sopra EMA 10
    streak_sopra = 0
    for k in range(len(df) - 2, -1, -1):
        c_k = df["Close"].iloc[k]
        e_k = df["EMA_10"].iloc[k]
        if pd.notna(c_k) and pd.notna(e_k) and float(c_k) > float(e_k):
            streak_sopra += 1
        else:
            break
    if streak_sopra < 7:
        return None

    # Verifica pressione di vendita: volumi >= 1.2x media 20gg oppure chiusura nel terzo inferiore
    high_oggi = float(df["High"].iloc[-1])
    low_oggi = float(df["Low"].iloc[-1])
    range_oggi = high_oggi - low_oggi
    chiusura_terzo_inf = range_oggi > 0 and ((prezzo - low_oggi) / range_oggi) <= (1.0 / 3.0)
    volumi_ok = vol_ratio >= 1.20
    if not (volumi_ok or chiusura_terzo_inf):
        return None

    trigger_y = ema10
    dist_y = ((prezzo - trigger_y) / trigger_y) * 100.0
    atr = float(df["ATR_14"].iloc[-1]) if pd.notna(df["ATR_14"].iloc[-1]) else prezzo * 0.02
    max_3g = float(df["High"].iloc[-3:].max())
    stop_raw = max(trigger_y, max_3g) + 0.25 * atr
    stop = max(trigger_y * 1.015, min(stop_raw, prezzo * 1.12))

    entry_ref = min(prezzo, trigger_y)
    sma20 = float(df["SMA_20"].iloc[-1]) if pd.notna(df["SMA_20"].iloc[-1]) else 0.0
    sma50 = float(df["SMA_50"].iloc[-1]) if pd.notna(df["SMA_50"].iloc[-1]) else 0.0
    target_rif = sma50 if (0 < sma50 < entry_ref * 0.94) else (sma20 if (0 < sma20 < entry_ref * 0.95) else entry_ref - (stop - entry_ref) * 2.0)
    target = max(0.01, min(target_rif, entry_ref - (stop - entry_ref) * 1.95))

    ok_rr, rr, tgt_pct, stp_pct = _calcola_rr_e_valida("SELL", prezzo, trigger_y, target, stop)
    if not ok_rr:
        return None

    score = 78
    if volumi_ok:
        score += 5
        if vol_ratio >= 1.50:
            score += 3
    if chiusura_terzo_inf:
        score += 5
    if float(pnl_pct) >= 25.0:
        score += 4
    if streak_sopra >= 10:
        score += 4

    conferme = []
    if volumi_ok:
        conferme.append(f"volumi {vol_ratio:.2f}x")
    if chiusura_terzo_inf:
        conferme.append("chiusura nel terzo inferiore")
    motivo = (
        f"Gain aperto +{float(pnl_pct):.1f}%: chiusura sotto EMA 10 (${ema10:.2f}) dopo {streak_sopra} sedute sopra "
        f"({', '.join(conferme)})"
    )
    return {
        "lato": "SELL",
        "figura": "Perdita EMA 10 (Trailing Profit)",
        "confidenza": min(97, int(round(score))),
        "stato_trigger": "ROTTURA RIBASSISTA",
        "trigger_y": round(trigger_y, 2),
        "dist_y_pct": round(dist_y, 2),
        "target_price": round(target, 2),
        "target_pct": tgt_pct,
        "stop_price": round(stop, 2),
        "stop_pct": stp_pct,
        "rr": rr,
        "motivo": motivo,
    }


# ==============================================================================
# MOTORE PRINCIPALE PER SINGOLO TITOLO
# ==============================================================================
def analizza_pattern_titolo(
    ticker,
    df,
    in_portafoglio=False,
    pnl_pct=None,
    eurusd_rate=1.12,
    currency="USD",
    earnings_giorni=None,
    spy_regime="verde",
    s_score=None,
):
    """
    Analizza un singolo titolo e restituisce la lista di alert validi (massimo 1 BUY e/o 1 SELL)
    già filtrati per anti-ritardo, RSI, R/R >= 1.8, earnings, Trend Weinstein e soglia score dinamica.
    """
    d = _calcola_indicatori(df)
    if d is None:
        return []

    soglia_score = SOGLIA_SCORE_RIBASSISTA if str(spy_regime).lower() == "rosso" else SOGLIA_SCORE_NORMALE
    s_score_val = int(round(float(s_score))) if s_score is not None else None
    prezzo_nat = float(d["Close"].iloc[-1])
    vol_media = float(d["Vol_Media_20"].iloc[-1]) if pd.notna(d["Vol_Media_20"].iloc[-1]) else 0.0
    vol_ratio = float(d["Volume"].iloc[-1]) / vol_media if vol_media > 0 else 0.0
    rsi_oggi = float(d["RSI"].iloc[-1])

    ema20_oggi = float(d["EMA_20"].iloc[-1]) if pd.notna(d["EMA_20"].iloc[-1]) else 0.0
    dist_ema20_pct = ((prezzo_nat - ema20_oggi) / ema20_oggi) * 100.0 if ema20_oggi > 0 else 999.0

    # Avviso e penalità earnings (< 5 giorni)
    earnings_vicini = earnings_giorni is not None and 0 <= int(earnings_giorni) < 5
    earnings_warning = f"⚠️ Earnings tra {int(earnings_giorni)}gg" if earnings_vicini else ""

    pivot_highs, pivot_lows = trova_pivot(d, ordine=3, min_distanza=MIN_DISTANZA_PIVOT)

    def _to_eur(val_nat):
        return round(val_nat / eurusd_rate, 2) if str(currency).upper() == "USD" and eurusd_rate > 0 else round(val_nat, 2)

    risultati = []

    # 1) RILEVAMENTO LATO BUY (vincolo rigoroso dist_ema20_pct <= 3.5%, non esteso e RSI <= 72 su TUTTE le figure BUY)
    if dist_ema20_pct <= MAX_DIST_EMA20_BUY_PCT and not _titolo_esteso_buy(d):
        candidati_buy = []

        if not in_portafoglio:
            # Watchlist -> tutte le 6 figure BUY
            for fn in (
                lambda: _rileva_vcp(d, pivot_highs, pivot_lows, vol_ratio),
                lambda: _rileva_triangolo_ascendente(d, pivot_highs, pivot_lows, vol_ratio),
                lambda: _rileva_cup_and_handle(d, pivot_highs, pivot_lows, vol_ratio),
                lambda: _rileva_flat_base(d, pivot_highs, pivot_lows, vol_ratio),
                lambda: _rileva_bull_flag(d, pivot_highs, pivot_lows, vol_ratio),
                lambda: _rileva_doppio_minimo_w(d, pivot_highs, pivot_lows, vol_ratio),
            ):
                res = fn()
                if res:
                    candidati_buy.append(res)
            cat_buy = "buy_nuovo"
            badge_buy = "🟢 BUY NUOVO ACQUISTO"
            color_buy = "#089981"
        elif pnl_pct is not None and float(pnl_pct) >= 0.0:
            # Portafoglio in gain -> solo figure di continuazione ordinate
            for fn in (
                lambda: _rileva_vcp(d, pivot_highs, pivot_lows, vol_ratio),
                lambda: _rileva_triangolo_ascendente(d, pivot_highs, pivot_lows, vol_ratio),
                lambda: _rileva_cup_and_handle(d, pivot_highs, pivot_lows, vol_ratio),
                lambda: _rileva_flat_base(d, pivot_highs, pivot_lows, vol_ratio),
                lambda: _rileva_bull_flag(d, pivot_highs, pivot_lows, vol_ratio),
            ):
                res = fn()
                if res:
                    candidati_buy.append(res)
            cat_buy = "buy_incremento"
            badge_buy = "🔵 BUY INCREMENTO (+)"
            color_buy = "#2962FF"
        else:
            # Portafoglio in perdita -> SOLO inversione confermata (Doppio Minimo o Riconquista SMA 20 + Div. RSI)
            for fn in (
                lambda: _rileva_doppio_minimo_w(d, pivot_highs, pivot_lows, vol_ratio),
                lambda: _rileva_riconquista_sma20_div_rsi(d, pivot_highs, pivot_lows, vol_ratio),
            ):
                res = fn()
                if res:
                    candidati_buy.append(res)
            cat_buy = "buy_mediazione"
            badge_buy = "🟠 BUY MEDIAZIONE (-)"
            color_buy = "#F59E0B"

        # Applica filtro Trend Weinstein (obbligatorio su BUY NUOVO ACQUISTO e BUY INCREMENTO (+)),
        # eventuale penalità earnings (< 5gg) e soglia di confidenza
        validi_buy = []
        richiede_weinstein = cat_buy in ("buy_nuovo", "buy_incremento")
        for c in candidati_buy:
            if richiede_weinstein and not _passa_filtro_weinstein_buy(d, c.get("trigger_y")):
                continue
            score_eff = c["confidenza"] - (10 if earnings_vicini else 0)
            if score_eff >= soglia_score:
                c["confidenza"] = score_eff
                validi_buy.append(c)

        if validi_buy:
            best_buy = max(validi_buy, key=lambda x: (x["confidenza"], x["rr"]))
            best_buy.update(
                {
                    "ticker": str(ticker).upper(),
                    "categoria": cat_buy,
                    "badge": badge_buy,
                    "badge_color": color_buy,
                    "prezzo_usd": round(prezzo_nat, 2),
                    "prezzo_eur": _to_eur(prezzo_nat),
                    "trigger_y_eur": _to_eur(best_buy["trigger_y"]),
                    "target_price_eur": _to_eur(best_buy["target_price"]),
                    "stop_price_eur": _to_eur(best_buy["stop_price"]),
                    "vol_ratio": round(vol_ratio, 2),
                    "rsi": round(rsi_oggi, 1),
                    "dist_ema20_pct": round(dist_ema20_pct, 2),
                    "earnings_giorni": earnings_giorni,
                    "earnings_warning": earnings_warning,
                    "pnl_pct": round(float(pnl_pct), 2) if pnl_pct is not None else None,
                    "s_score": s_score_val,
                    "currency": currency,
                }
            )
            risultati.append(best_buy)

    # 2) RILEVAMENTO LATO SELL (SOLO su titoli in Portafoglio)
    if in_portafoglio:
        candidati_sell = []
        for fn in (
            lambda: _rileva_perdita_ema10_trailing_profit(d, vol_ratio, pnl_pct),
            lambda: _rileva_doppio_massimo_m(d, pivot_highs, pivot_lows, vol_ratio),
            lambda: _rileva_testa_e_spalle(d, pivot_highs, pivot_lows, vol_ratio),
            lambda: _rileva_rottura_supporto_sma50(d, pivot_lows, vol_ratio),
            lambda: _rileva_distribuzione_sma20(d, vol_ratio),
        ):
            res = fn()
            if res and res["confidenza"] >= soglia_score:
                candidati_sell.append(res)

        if candidati_sell:
            best_sell = max(candidati_sell, key=lambda x: (x["confidenza"], x["rr"]))
            best_sell.update(
                {
                    "ticker": str(ticker).upper(),
                    "categoria": "sell_protezione",
                    "badge": "🔴 SELL PROTEZIONE / TAKE PROFIT",
                    "badge_color": "#F23645",
                    "prezzo_usd": round(prezzo_nat, 2),
                    "prezzo_eur": _to_eur(prezzo_nat),
                    "trigger_y_eur": _to_eur(best_sell["trigger_y"]),
                    "target_price_eur": _to_eur(best_sell["target_price"]),
                    "stop_price_eur": _to_eur(best_sell["stop_price"]),
                    "vol_ratio": round(vol_ratio, 2),
                    "rsi": round(rsi_oggi, 1),
                    "dist_ema20_pct": round(dist_ema20_pct, 2),
                    "earnings_giorni": earnings_giorni,
                    "earnings_warning": earnings_warning,
                    "pnl_pct": round(float(pnl_pct), 2) if pnl_pct is not None else None,
                    "s_score": s_score_val,
                    "currency": currency,
                }
            )
            risultati.append(best_sell)

    return risultati


def crea_contenitore_pattern_alerts(spy_regime="verde"):
    """Crea la struttura dati vuota da popolare durante AVVIA SCANSIONE e salvare in st.session_state."""
    soglia = SOGLIA_SCORE_RIBASSISTA if str(spy_regime).lower() == "rosso" else SOGLIA_SCORE_NORMALE
    return {
        "sell_protezione": [],
        "buy_incremento": [],
        "buy_mediazione": [],
        "buy_nuovo": [],
        "buy_nuovo_raw": [],
        "sorvegliati_speciali": [],
        "priorita_portafoglio": False,
        "per_ticker": {},
        "soglia_score": soglia,
        "spy_regime": str(spy_regime).lower(),
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


def registra_alert_in_contenitore(contenitore, alert_list):
    """Inserisce gli alert di un titolo nel contenitore e aggiorna la mappa veloce per_ticker."""
    if not alert_list:
        return
    for al in alert_list:
        cat = al.get("categoria")
        if cat == "buy_nuovo":
            contenitore.setdefault("buy_nuovo_raw", []).append(al)
        if cat in contenitore and isinstance(contenitore[cat], list):
            contenitore[cat].append(al)

        tk = str(al.get("ticker", "")).upper()
        if not tk:
            continue
        # Su un titolo in portafoglio con alert SELL e BUY insieme, sul grafico diamo priorità al SELL di protezione
        attuale = contenitore["per_ticker"].get(tk)
        if attuale is None:
            contenitore["per_ticker"][tk] = al
        elif al.get("lato") == "SELL" and attuale.get("lato") != "SELL":
            contenitore["per_ticker"][tk] = al
        elif al.get("lato") == attuale.get("lato") and al.get("confidenza", 0) > attuale.get("confidenza", 0):
            contenitore["per_ticker"][tk] = al


def _estrai_mappa_s_score_da_sessione(session_state):
    """
    Recupera una mappa {TICKER: S-Score} dai risultati di scansione presenti in st.session_state
    come fallback automatico nel caso un chiamante non abbia passato s_score direttamente.
    """
    mappa = {}
    if session_state is None:
        return mappa
    try:
        for chiave_df in ("df_fortezza", "df_cavalli", "df_monitor", "df_palantir"):
            df_s = session_state.get(chiave_df)
            if isinstance(df_s, pd.DataFrame) and not df_s.empty:
                if "Ticker" in df_s.columns and "S-Score" in df_s.columns:
                    for _, row in df_s.iterrows():
                        tk = str(row.get("Ticker", "")).strip().upper()
                        sc = row.get("S-Score")
                        if tk and pd.notna(sc):
                            try:
                                mappa[tk] = int(round(float(sc)))
                            except Exception:
                                pass
        for z in (session_state.get("zona_interesse_alerts") or []):
            if isinstance(z, dict):
                tk = str(z.get("ticker", "")).strip().upper()
                sc = z.get("s_score")
                if tk and sc is not None and tk not in mappa:
                    try:
                        mappa[tk] = int(round(float(sc)))
                    except Exception:
                        pass
    except Exception:
        pass
    return mappa


def _calcola_punteggio_combinato(al):
    """Calcola il punteggio combinato (Confidenza tecnica + S-Score fondamentale + R/R)."""
    conf = float(al.get("confidenza", 0) or 0)
    sc = float(al.get("s_score", 0) or 0)
    rr = float(al.get("rr", 0) or 0)
    return round(0.55 * conf + 0.35 * sc + min(rr, 4.0) * 2.5, 1)


def applica_priorita_portafoglio(contenitore, s_score_map=None):
    """
    Applica la regola di Priorità Portafoglio e filtro 'Setup Irrinunciabile':
    1) Ordina prima gli alert sui titoli in Portafoglio (SELL PROTEZIONE, BUY INCREMENTO, BUY MEDIAZIONE).
    2) Se esiste almeno un alert attivo di BUY INCREMENTO (+) o BUY MEDIAZIONE (-):
       filtra BUY NUOVO ACQUISTO lasciando passare solo i '💎 SETUP IRRINUNCIABILE'
       (Confidenza >= 92, S-Score >= 85, R/R >= 2.5, regime SPY non ribassista).
    3) Altrimenti applica la confluenza S-Score >= 75 e tiene al massimo i Top 3 per punteggio combinato.
    """
    if not isinstance(contenitore, dict):
        return contenitore

    # 1) Valuta e ordina prima il Portafoglio (SELL -> INCREMENTO -> MEDIAZIONE)
    for chiave in ("sell_protezione", "buy_incremento", "buy_mediazione"):
        lista_p = contenitore.get(chiave, []) or []
        if chiave != "sell_protezione":
            # Controllo difensivo rigoroso dist_ema20_pct <= 3.5% su tutti i BUY
            lista_p = [
                x for x in lista_p
                if x.get("dist_ema20_pct") is None or float(x.get("dist_ema20_pct")) <= MAX_DIST_EMA20_BUY_PCT
            ]
        if s_score_map:
            for item in lista_p:
                if item.get("s_score") is None:
                    tk_i = str(item.get("ticker", "")).upper()
                    if tk_i in s_score_map:
                        item["s_score"] = s_score_map[tk_i]
        contenitore[chiave] = sorted(
            lista_p,
            key=lambda x: (x.get("confidenza", 0), x.get("rr", 0)),
            reverse=True,
        )

    # Preserva sempre la lista grezza dei candidati Nuovi Acquisti per poter ricalcolare il filtro in modo idempotente
    if "buy_nuovo_raw" not in contenitore or (not contenitore["buy_nuovo_raw"] and contenitore.get("buy_nuovo")):
        contenitore["buy_nuovo_raw"] = [dict(x) for x in (contenitore.get("buy_nuovo") or [])]

    candidati_nuovi = [
        dict(x)
        for x in (contenitore.get("buy_nuovo_raw") or [])
        if x.get("dist_ema20_pct") is None or float(x.get("dist_ema20_pct")) <= MAX_DIST_EMA20_BUY_PCT
    ]
    if s_score_map:
        for item in candidati_nuovi:
            if item.get("s_score") is None:
                tk_i = str(item.get("ticker", "")).upper()
                if tk_i in s_score_map:
                    item["s_score"] = s_score_map[tk_i]

    ha_opportunita_portafoglio = bool(contenitore.get("buy_incremento") or contenitore.get("buy_mediazione"))
    spy_ribassista = str(contenitore.get("spy_regime", "verde")).lower() == "rosso"
    contenitore["priorita_portafoglio"] = ha_opportunita_portafoglio

    filtrati_nuovi = []
    if ha_opportunita_portafoglio:
        # 2) Modalità Priorità Portafoglio -> passano solo i Setup Irrinunciabili (fuori scala)
        if not spy_ribassista:
            for al in candidati_nuovi:
                conf = float(al.get("confidenza", 0) or 0)
                sc = al.get("s_score")
                rr = float(al.get("rr", 0) or 0)
                if (
                    conf >= MIN_CONF_IRRINUNCIABILE
                    and sc is not None
                    and float(sc) >= MIN_SSCORE_IRRINUNCIABILE
                    and rr >= MIN_RR_IRRINUNCIABILE
                ):
                    al["badge"] = "💎 SETUP IRRINUNCIABILE"
                    al["badge_color"] = "#8B5CF6"
                    al["irrinunciabile"] = True
                    al["score_combinato"] = _calcola_punteggio_combinato(al)
                    filtrati_nuovi.append(al)
        filtrati_nuovi.sort(
            key=lambda x: (x.get("score_combinato", 0), x.get("confidenza", 0), x.get("rr", 0)),
            reverse=True,
        )
    else:
        # 3) Nessun alert di incremento/mediazione su portafoglio -> Confluenza S-Score >= 75 + Top 3
        for al in candidati_nuovi:
            sc = al.get("s_score")
            if sc is not None and float(sc) >= MIN_SSCORE_NUOVO_STD:
                al["badge"] = "🟢 BUY NUOVO ACQUISTO"
                al["badge_color"] = "#089981"
                al["irrinunciabile"] = False
                al["score_combinato"] = _calcola_punteggio_combinato(al)
                filtrati_nuovi.append(al)
        filtrati_nuovi.sort(
            key=lambda x: (x.get("score_combinato", 0), x.get("confidenza", 0), x.get("s_score", 0), x.get("rr", 0)),
            reverse=True,
        )
        filtrati_nuovi = filtrati_nuovi[:MAX_TOP_NUOVI_ACQUISTI]

    contenitore["buy_nuovo"] = filtrati_nuovi

    # Ricostruisce la mappa veloce per_ticker dando priorità agli alert di Portafoglio (SELL > BUY) e poi ai nuovi promossi
    nuova_mappa = {}
    for chiave in ("buy_nuovo", "buy_mediazione", "buy_incremento", "sell_protezione"):
        for al in contenitore.get(chiave, []):
            tk = str(al.get("ticker", "")).upper()
            if tk:
                nuova_mappa[tk] = al
    contenitore["per_ticker"] = nuova_mappa
    return contenitore


def ordina_contenitore_pattern_alerts(contenitore, s_score_map=None):
    """Ordina le 4 liste di alert e applica la Priorità Portafoglio / filtro Setup Irrinunciabile."""
    return applica_priorita_portafoglio(contenitore, s_score_map=s_score_map)


# ==============================================================================
# INTEGRAZIONE GRAFICO PLOTLY (TRIGGER Y, TARGET, STOP)
# ==============================================================================
def aggiungi_livelli_pattern_al_grafico(fig, pattern_info):
    """
    Traccia sul grafico Plotly (row=1, col=1) le 3 linee orizzontali tratteggiate
    con etichetta per un titolo con pattern attivo: Trigger Y, Target e Stop.
    """
    if fig is None or not isinstance(pattern_info, dict):
        return fig

    try:
        trigger_y = float(pattern_info.get("trigger_y") or 0)
        target_p = float(pattern_info.get("target_price") or 0)
        stop_p = float(pattern_info.get("stop_price") or 0)
        if trigger_y <= 0 or target_p <= 0 or stop_p <= 0:
            return fig

        simb = "$" if str(pattern_info.get("currency", "USD")).upper() == "USD" else "€"
        figura = pattern_info.get("figura", "Pattern")
        conf = pattern_info.get("confidenza", 0)
        tgt_pct = pattern_info.get("target_pct", 0.0)
        stp_pct = pattern_info.get("stop_pct", 0.0)
        rr = pattern_info.get("rr", 0.0)

        # Linea 1: Trigger Y
        fig.add_hline(
            y=trigger_y,
            line_dash="dash",
            line_color="#F59E0B",
            line_width=1.8,
            annotation_text=f" ⚡ Trigger Y ({figura} {conf}%): {simb}{trigger_y:.2f} ",
            annotation_position="top right",
            annotation_bgcolor="rgba(11, 14, 17, 0.90)",
            annotation_font=dict(color="#F59E0B", size=11),
            row=1,
            col=1,
        )

        # Linea 2: Target
        fig.add_hline(
            y=target_p,
            line_dash="dash",
            line_color="#00E676",
            line_width=1.8,
            annotation_text=f" 🎯 Target ({tgt_pct:+.1f}% | R/R 1:{rr:.1f}): {simb}{target_p:.2f} ",
            annotation_position="top right",
            annotation_bgcolor="rgba(11, 14, 17, 0.90)",
            annotation_font=dict(color="#00E676", size=11),
            row=1,
            col=1,
        )

        # Linea 3: Stop
        fig.add_hline(
            y=stop_p,
            line_dash="dash",
            line_color="#FF1744",
            line_width=1.8,
            annotation_text=f" 🛑 Stop ({stp_pct:+.1f}%): {simb}{stop_p:.2f} ",
            annotation_position="bottom right",
            annotation_bgcolor="rgba(11, 14, 17, 0.90)",
            annotation_font=dict(color="#FF1744", size=11),
            row=1,
            col=1,
        )

        # Se l'asse Y ha un range bloccato dal timeframe, lo allarghiamo per rendere sempre visibili i 3 livelli
        cur_range = getattr(fig.layout.yaxis, "range", None)
        if cur_range and len(cur_range) == 2:
            y_lo = min(float(cur_range[0]), min(trigger_y, target_p, stop_p) * 0.97)
            y_hi = max(float(cur_range[1]), max(trigger_y, target_p, stop_p) * 1.03)
            fig.update_yaxes(range=[y_lo, y_hi], row=1, col=1)
    except Exception:
        pass

    return fig


# ==============================================================================
# RENDERING DEI 4 ALERT NEL RIEPILOGO OPERATIVO (STREAMLIT)
# ==============================================================================
def _render_card_alert(st, al):
    """Renderizza una singola card compatta stile terminale per un alert pattern."""
    simb = "$" if str(al.get("currency", "USD")).upper() == "USD" else "€"
    b_col = al.get("badge_color", "#2962FF")
    pnl_txt = f" &nbsp;|&nbsp; P&L: <b>{al['pnl_pct']:+.1f}%</b>" if al.get("pnl_pct") is not None else ""
    sscore_txt = f" &nbsp;|&nbsp; S-Score: <b>{int(al['s_score'])}/100</b>" if al.get("s_score") is not None else ""
    ema20_txt = f" &nbsp;|&nbsp; EMA20: <b>{al['dist_ema20_pct']:+.1f}%</b>" if al.get("dist_ema20_pct") is not None else ""
    comb_txt = f" &nbsp;|&nbsp; Comb: <b>{al['score_combinato']:.1f}</b>" if al.get("score_combinato") is not None else ""
    warn_html = (
        f"<div style='margin-top:6px; padding:4px 8px; border-radius:5px; background:rgba(245,158,11,0.16); "
        f"border:1px solid rgba(245,158,11,0.45); color:#FBBF24; font-size:0.78rem; font-weight:700;'>"
        f"{al['earnings_warning']} — Attenzione rischio gap</div>"
        if al.get("earnings_warning")
        else ""
    )

    st.markdown(
        f"""
        <div style="background:#131722; border:1px solid #2A2E39; border-left:4px solid {b_col};
                    border-radius:8px; padding:0.75rem 0.95rem; margin-bottom:0.55rem;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:0.35rem;">
                <div>
                    <span style="background:{b_col}; color:#FFFFFF; font-size:0.70rem; font-weight:800;
                                 padding:2px 7px; border-radius:4px; letter-spacing:0.02em;">{al.get('badge')}</span>
                    <span style="font-size:1.08rem; font-weight:800; color:#FFFFFF; margin-left:8px;">{al.get('ticker')}</span>
                    <span style="color:#CBD5E1; font-size:0.86rem; font-weight:600; margin-left:6px;">• {al.get('figura')}</span>
                </div>
                <span style="font-family:'JetBrains Mono', monospace; background:#0B0E11; border:1px solid #2A2E39;
                             color:#E2E8F0; font-size:0.78rem; font-weight:700; padding:2px 8px; border-radius:5px;">
                    Confidenza {al.get('confidenza')}% &nbsp;|&nbsp; {al.get('stato_trigger')}
                </span>
            </div>
            <div style="display:flex; flex-wrap:wrap; gap:14px; font-family:'JetBrains Mono', monospace;
                        font-size:0.82rem; color:#E2E8F0; margin-bottom:0.30rem;">
                <span>⚡ <b>Trigger Y:</b> {simb}{al.get('trigger_y'):.2f} (€{al.get('trigger_y_eur'):.2f})</span>
                <span style="color:#4ADE80;">🎯 <b>Target:</b> {al.get('target_pct'):+.1f}% ({simb}{al.get('target_price'):.2f} / €{al.get('target_price_eur'):.2f})</span>
                <span style="color:#F87171;">🛑 <b>Stop:</b> {al.get('stop_pct'):+.1f}% ({simb}{al.get('stop_price'):.2f} / €{al.get('stop_price_eur'):.2f})</span>
                <span style="color:#38BDF8;">⚖️ <b>R/R:</b> 1:{al.get('rr'):.2f}</span>
            </div>
            <div style="font-size:0.78rem; color:#94A3B8;">
                {al.get('motivo')} &nbsp;|&nbsp; Vol: <b>{al.get('vol_ratio'):.2f}x</b> &nbsp;|&nbsp; RSI: <b>{al.get('rsi'):.1f}</b>{ema20_txt}{sscore_txt}{comb_txt}{pnl_txt}
            </div>
            {warn_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sezione_pattern_riepilogo(st, pattern_alerts):
    """
    Renderizza nel Riepilogo Operativo i 4 blocchi distinti di alert Pattern Engine
    dando priorità ai titoli già in Portafoglio (SELL -> INCREMENTO -> MEDIAZIONE -> NUOVI ACQUISTI).
    """
    st.subheader("📐 Alert Figure Grafiche ad Alta Probabilità")

    if not pattern_alerts or not isinstance(pattern_alerts, dict):
        st.info("👆 Avvia **🚀 AVVIA SCANSIONE** nella sidebar per calcolare le figure grafiche ad alta probabilità su Watchlist e Portafoglio.")
        return

    # Arricchisce eventuali S-Score mancanti da st.session_state e riapplica la priorità portafoglio
    s_score_map = _estrai_mappa_s_score_da_sessione(getattr(st, "session_state", None))
    pattern_alerts = applica_priorita_portafoglio(pattern_alerts, s_score_map=s_score_map)

    soglia = pattern_alerts.get("soglia_score", SOGLIA_SCORE_NORMALE)
    regime = str(pattern_alerts.get("spy_regime", "verde")).upper()
    ts = pattern_alerts.get("timestamp", "-")
    priorita_port = bool(pattern_alerts.get("priorita_portafoglio", False))

    st.caption(
        f"Soglia attiva: **≥ {soglia}/100** (Regime SPY: **{regime}**) • "
        f"Trend Weinstein `> SMA 200` + `SMA 50 ↑` • Max `+3.5%` da EMA 20 • "
        f"Anti-ritardo `-3.0% / +3.5%` • R/R ≥ `1.8` • Aggiornato: `{ts}`"
    )

    l_sell = pattern_alerts.get("sell_protezione", [])
    l_incr = pattern_alerts.get("buy_incremento", [])
    l_med = pattern_alerts.get("buy_mediazione", [])
    l_nuovo = pattern_alerts.get("buy_nuovo", [])

    # Fascia contatori rapidi nell'ordine di priorità (prima Portafoglio, poi Nuovi Acquisti)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🔴 SELL PROTEZIONE / TP", len(l_sell), ", ".join(x["ticker"] for x in l_sell[:3]) or "Nessuno")
    k2.metric("🔵 BUY INCREMENTO (+)", len(l_incr), ", ".join(x["ticker"] for x in l_incr[:3]) or "Nessuno")
    k3.metric("🟠 BUY MEDIAZIONE (-)", len(l_med), ", ".join(x["ticker"] for x in l_med[:3]) or "Nessuno")
    lbl_nuovi = "💎 NUOVI (IRRINUNCIABILI)" if priorita_port else "🟢 BUY NUOVO (TOP 3)"
    k4.metric(lbl_nuovi, len(l_nuovo), ", ".join(x["ticker"] for x in l_nuovo[:3]) or "Nessuno")

    # 1-3) Sezioni prioritarie su titoli già in Portafoglio
    sezioni_portafoglio = [
        ("🔴 SELL PROTEZIONE / TAKE PROFIT (Portafoglio)", l_sell, "Nessun segnale di distribuzione, perdita EMA 10 o rottura ribassista sui titoli in portafoglio."),
        ("🔵 BUY INCREMENTO (+) (Portafoglio in Gain)", l_incr, "Nessuna figura di continuazione ordinata sui titoli in portafoglio in gain."),
        ("🟠 BUY MEDIAZIONE (-) (Portafoglio in Perdita — Solo Inversione Confermata)", l_med, "Nessuna inversione confermata (Doppio Minimo / Riconquista SMA 20 + Div. RSI) sui titoli in perdita."),
    ]
    for titolo_sez, lista_al, msg_vuoto in sezioni_portafoglio:
        with st.expander(f"{titolo_sez} — {len(lista_al)}", expanded=bool(lista_al)):
            if lista_al:
                for al in lista_al:
                    _render_card_alert(st, al)
            else:
                st.caption(msg_vuoto)

    # 4) Sezione Nuovi Acquisti (con banner Priorità Portafoglio o Top 3 con confluenza S-Score >= 75)
    if priorita_port:
        titolo_nuovi = f"💎 BUY NUOVO ACQUISTO — Solo Setup Irrinunciabili — {len(l_nuovo)}"
        msg_vuoto_nuovi = (
            "Nessun nuovo acquisto soddisfa i criteri di Setup Irrinunciabile "
            "(Confidenza ≥ 92/100, S-Score ≥ 85/100, R/R ≥ 2.5 e SPY non ribassista)."
        )
    else:
        titolo_nuovi = f"🟢 BUY NUOVO ACQUISTO (Watchlist • Confluenza S-Score ≥ 75 • Top 3) — {len(l_nuovo)}"
        msg_vuoto_nuovi = "Nessun setup BUY ad alta probabilità con S-Score ≥ 75 sui titoli Watchlist fuori portafoglio."

    with st.expander(titolo_nuovi, expanded=bool(l_nuovo) or priorita_port):
        if priorita_port:
            st.warning(BANNER_PRIORITA_PORTAFOGLIO)
        if l_nuovo:
            for al in l_nuovo:
                _render_card_alert(st, al)
        else:
            st.caption(msg_vuoto_nuovi)

    # 5) Riquadro richiudibile "Sorvegliati Speciali — Luce Arancione" (max 8 titoli: fino a 3 Figure Quasi Pronte + Top Insider SEC)
    l_sorv = pattern_alerts.get("sorvegliati_speciali", []) or []
    with st.expander(
        f"🟠 Sorvegliati Speciali — Luce Arancione (In attesa di condizioni BUY) — {len(l_sorv)}",
        expanded=False,
    ):
        if l_sorv:
            st.caption(
                "Include fino a 3 📐 Figure Quasi Pronte (R/R ≥ 1.8, non in Fase 4) insieme ai migliori "
                "🏛️ Insider SEC Form 4 e 💪 Forza Alta (S-Score ≥ 75). I filtri severi BUY verdi restano invariati."
            )
            for sv in l_sorv:
                _render_card_sorvegliato(st, sv)
        else:
            st.caption(
                "Nessun Sorvegliato Speciale nella Watchlist attuale "
                "(richiesta una Figura Quasi Pronta R/R ≥ 1.8, Insider SEC Form 4 ≥ 2 acq / ≥ $300.000 oppure S-Score ≥ 75 in Fase 1/2)."
            )


# ==============================================================================
# SORVEGLIATI SPECIALI — LUCE ARANCIONE (FIGURE QUASI PRONTE + TOP INSIDER SEC)
# ==============================================================================
def _rileva_figura_quasi_pronta_sorvegliato(d, vol_ratio, s_val, fase_up, spy_regime):
    """
    Cerca una figura tecnica valida (Cup & Handle, Bull Flag, VCP o Triangolo Ascendente)
    con R/R >= 1.8 fuori da Fase 4 che sia quasi pronta ma non ancora BUY verde per un solo dettaglio
    (es. prezzo fino a -4% sotto Trigger Y, estensione temporanea +3.5%..+6% da EMA 20, o S-Score 70..soglia).
    Non altera in alcun modo i filtri severi dei segnali BUY verdi.
    """
    if d is None or len(d) < 60 or "FASE 4" in fase_up:
        return None

    prezzo = float(d["Close"].iloc[-1])
    ema20 = float(d["EMA_20"].iloc[-1]) if pd.notna(d["EMA_20"].iloc[-1]) else 0.0
    dist_ema20 = ((prezzo - ema20) / ema20) * 100.0 if ema20 > 0 else 999.0
    rsi = float(d["RSI"].iloc[-1]) if pd.notna(d["RSI"].iloc[-1]) else 50.0
    if prezzo <= 0 or dist_ema20 > 6.0 or rsi > 75.0:
        return None

    pivot_highs, pivot_lows = trova_pivot(d, ordine=3, min_distanza=MIN_DISTANZA_PIVOT)
    candidati = []
    for fn in (
        lambda: _rileva_cup_and_handle(d, pivot_highs, pivot_lows, vol_ratio),
        lambda: _rileva_bull_flag(d, pivot_highs, pivot_lows, vol_ratio),
        lambda: _rileva_vcp(d, pivot_highs, pivot_lows, vol_ratio),
        lambda: _rileva_triangolo_ascendente(d, pivot_highs, pivot_lows, vol_ratio),
    ):
        try:
            res = fn()
            if res and float(res.get("rr", 0) or 0) >= MIN_RR:
                candidati.append(res)
        except Exception:
            pass

    if candidati:
        return max(candidati, key=lambda x: (float(x.get("confidenza", 0)), float(x.get("rr", 0))))

    # Controllo dedicato per fascia pre-breakout appena sotto il limite BUY (-4.0% .. -3.0% sotto Trigger Y)
    try:
        fin = d.tail(45)
        if len(fin) >= 25:
            trig_y = float(fin["High"].iloc[:-1].max())
            dist_trig_pct = ((prezzo - trig_y) / trig_y) * 100.0 if trig_y > 0 else -99.0
            if -4.0 <= dist_trig_pct < PRE_BREAKOUT_MIN_PCT:
                low_rec = float(d["Low"].tail(12).min())
                low_base = float(fin["Low"].min())
                # Verifica struttura rialzista ordinata (minimi recenti più alti della base -> VCP / Triangolo / Flag)
                if low_rec > low_base * 1.01 and low_rec < prezzo:
                    stop_p = round(min(low_rec * 0.99, prezzo * 0.94), 2)
                    rischio = trig_y - stop_p
                    altezza = trig_y - low_base
                    if rischio > 0 and altezza > 0:
                        target_p = round(trig_y + max(altezza * 0.85, rischio * 2.0), 2)
                        rr_val = round((target_p - trig_y) / rischio, 2)
                        if rr_val >= MIN_RR:
                            # Classifica la figura in base alla contrazione di volatilità o corsa precedente
                            gain_impulso = ((trig_y - low_base) / low_base) * 100.0 if low_base > 0 else 0.0
                            if gain_impulso >= 14.0:
                                nome_fig = "Bull Flag"
                            elif (float(d["High"].tail(10).max()) - low_rec) / max(low_rec, 1e-6) <= 0.07:
                                nome_fig = "VCP (Contrazione Volatilità)"
                            else:
                                nome_fig = "Triangolo Ascendente"
                            return {
                                "figura": nome_fig,
                                "trigger_y": round(trig_y, 2),
                                "target_price": target_p,
                                "stop_price": stop_p,
                                "rr": rr_val,
                                "confidenza": 74,
                                "stato_trigger": "QUASI PRE-BREAKOUT",
                            }
    except Exception:
        pass
    return None


def valuta_sorvegliato_speciale(
    ticker,
    df,
    s_score,
    fase_weinstein,
    currency="USD",
    eurusd_rate=1.12,
    spy_regime="verde",
    sec_insider=None,
):
    """
    Valuta se un titolo Watchlist (NON ancora BUY) entra nei
    '🟠 Sorvegliati Speciali — Luce Arancione' per uno o più motivi forti:
      - Figura Grafica Quasi Pronta (Cup & Handle, Bull Flag, VCP, Triangolo con R/R >= 1.8, non Fase 4)
      - Motivo A: Insider SEC Form 4 ultimi 90gg (>= 2 acquisti OPPURE >= $300.000, con data GG/MM/AAAA)
      - Motivo B: Forza Alta (S-Score >= 75 in Fase 1 o Fase 2 Weinstein)
    Non allenta in alcun modo i filtri BUY verdi.
    """
    try:
        tk_up = str(ticker or "").strip().upper()
        if not tk_up or df is None or len(df) < 60:
            return None

        # Verifica Motivo A (Insider SEC Form 4 ultimi 90gg con data ultimo acquisto GG/MM/AAAA)
        sec_buys = int((sec_insider or {}).get("buys", 0) or 0)
        sec_val = float((sec_insider or {}).get("valore_usd", 0.0) or 0.0)
        sec_num_dir = int((sec_insider or {}).get("num_insider", 0) or 0)
        sec_ult_raw = str((sec_insider or {}).get("ultimo_acquisto") or "").strip()[:10]
        sec_ult_it = ""
        if sec_ult_raw:
            try:
                sec_ult_it = datetime.strptime(sec_ult_raw, "%Y-%m-%d").strftime("%d/%m/%Y")
            except Exception:
                sec_ult_it = sec_ult_raw
        _ult_tag = f" — ultimo: {sec_ult_it}" if sec_ult_it else ""
        has_motivo_a = (sec_buys >= 2) or (sec_val >= 300000.0)

        # Verifica Motivo B (Forza Alta S-Score >= 75 in Fase 1 o Fase 2)
        s_val = int(round(float(s_score))) if s_score is not None else 0
        fase_str = str(fase_weinstein or "N/D").strip()
        fase_up = fase_str.upper()
        in_fase_1_o_2 = ("FASE 1" in fase_up) or ("FASE 2" in fase_up) or ("PULLBACK FASE 2" in fase_up)
        has_motivo_b = (s_val >= 75) and in_fase_1_o_2

        d = _calcola_indicatori(df)
        if d is None or d.empty:
            return None

        prezzo = float(d["Close"].iloc[-1])
        if prezzo <= 0:
            return None
        vol_m = float(d["Vol_Media_20"].iloc[-1]) if pd.notna(d["Vol_Media_20"].iloc[-1]) else 0.0
        vol_ratio = float(d["Volume"].iloc[-1]) / vol_m if vol_m > 0 else 1.0

        # Verifica Figura Grafica Quasi Pronta (Cup & Handle, Bull Flag, VCP, Triangolo, R/R >= 1.8, non Fase 4)
        fig_qp = _rileva_figura_quasi_pronta_sorvegliato(d, vol_ratio, s_val, fase_up, spy_regime)
        has_figura_qp = fig_qp is not None

        if not (has_figura_qp or has_motivo_a or has_motivo_b):
            return None

        simb = "$" if str(currency).upper() == "USD" else "€"
        prezzo_eur = round(prezzo / eurusd_rate, 2) if (str(currency).upper() == "USD" and eurusd_rate > 0) else round(prezzo, 2)

        ema20 = float(d["EMA_20"].iloc[-1]) if pd.notna(d["EMA_20"].iloc[-1]) else prezzo
        sma50 = float(d["SMA_50"].iloc[-1]) if pd.notna(d["SMA_50"].iloc[-1]) else prezzo
        sma50_prev = (
            float(d["SMA_50"].iloc[-1 - LOOKBACK_PENDENZA_SMA50])
            if len(d) > 50 + LOOKBACK_PENDENZA_SMA50 and pd.notna(d["SMA_50"].iloc[-1 - LOOKBACK_PENDENZA_SMA50])
            else None
        )
        sma200 = float(d["SMA_200"].iloc[-1]) if pd.notna(d["SMA_200"].iloc[-1]) else 0.0
        rsi = float(d["RSI"].iloc[-1]) if pd.notna(d["RSI"].iloc[-1]) else 50.0
        dist_ema20_pct = ((prezzo - ema20) / ema20) * 100.0 if ema20 > 0 else 0.0
        soglia_din = SOGLIA_SCORE_RIBASSISTA if str(spy_regime).lower() == "rosso" else SOGLIA_SCORE_NORMALE

        if has_figura_qp:
            trigger_y_ref = float(fig_qp.get("trigger_y") or prezzo)
            fig_nome = str(fig_qp.get("figura", "Breakout"))
            fig_short = "VCP" if "VCP" in fig_nome else ("Triangolo" if "Triangolo" in fig_nome else fig_nome)
            fig_rr = float(fig_qp.get("rr", 0.0) or 0.0)
            fig_conf = int(fig_qp.get("confidenza", 0) or 0)
        else:
            finestra_res = d["High"].iloc[-min(40, len(d)):]
            trigger_y_ref = float(finestra_res.max()) if not finestra_res.empty else prezzo
            fig_nome, fig_short, fig_rr, fig_conf = "", "", 0.0, 0

        # Costruzione badge e riga "Perché è sorvegliato" (integrando Figura Quasi Pronta + Insider SEC + S-Score)
        ins_label = f"🏛️ Insider SEC ({sec_buys} acq / ${sec_val:,.0f}{_ult_tag})"
        if has_figura_qp and has_motivo_a:
            priorita = 3
            badge_motivo = f"📐 Figura Quasi Pronta ({fig_short}) + {ins_label}"
            perche_txt = f"{fig_nome} con R/R 1:{fig_rr:.1f} (S-Score {s_val}) + {ins_label}"
        elif has_motivo_a and has_motivo_b:
            priorita = 3
            badge_motivo = f"{ins_label} + 💪 S-Score {s_val}"
            perche_txt = f"{ins_label} + 💪 Forza Alta (S-Score {s_val})"
        elif has_figura_qp:
            priorita = 2
            badge_motivo = f"📐 Figura Quasi Pronta ({fig_short})"
            perche_txt = f"{fig_nome} con R/R 1:{fig_rr:.1f} (S-Score {s_val})"
        elif has_motivo_a:
            priorita = 1
            badge_motivo = ins_label
            perche_txt = f"🏛️ Insider SEC ({sec_buys} acq / ${sec_val:,.0f}{_ult_tag} — {max(1, sec_num_dir)} dir. in 90gg)"
        else:
            priorita = 0
            badge_motivo = f"💪 Forza Alta (S-Score {s_val})"
            perche_txt = f"💪 Forza Alta (S-Score {s_val} in {fase_str})"

        # Diagnostica esatta con numeri reali: "Cosa manca al BUY" (sempre con riferimento Trigger Y $)
        blocchi = []
        if has_figura_qp:
            if trigger_y_ref > prezzo * 1.001:
                pct_trig = ((trigger_y_ref - prezzo) / prezzo) * 100.0
                blocchi.append(f"Prezzo ancora -{pct_trig:.1f}% sotto il Trigger Y ({simb}{trigger_y_ref:.2f})")
            if dist_ema20_pct > MAX_DIST_EMA20_BUY_PCT:
                blocchi.append(
                    f"Estensione temporanea {dist_ema20_pct:+.1f}% sopra EMA 20 ({simb}{ema20:.2f}, max +{MAX_DIST_EMA20_BUY_PCT:.1f}%): attendere pausa verso Trigger Y ({simb}{trigger_y_ref:.2f})"
                )
            if sma200 > 0 and prezzo <= sma200 and trigger_y_ref <= sma200:
                pct_200 = ((sma200 - prezzo) / prezzo) * 100.0
                blocchi.append(f"Manca +{pct_200:.1f}% per superare SMA 200 ({simb}{sma200:.2f})")
            elif sma50_prev is not None and sma50 <= sma50_prev:
                blocchi.append(f"SMA 50 ({simb}{sma50:.2f}) non ancora inclinata al rialzo (Trigger Y {simb}{trigger_y_ref:.2f})")
            if s_val < MIN_SSCORE_NUOVO_STD:
                blocchi.append(f"S-Score {s_val}/100 (soglia BUY {MIN_SSCORE_NUOVO_STD}) — Trigger Y {simb}{trigger_y_ref:.2f}")
            elif fig_conf < soglia_din:
                blocchi.append(f"Confidenza {fig_conf}/100 (soglia SPY {str(spy_regime).upper()}: {soglia_din}) — Trigger Y {simb}{trigger_y_ref:.2f}")
            if prezzo >= trigger_y_ref and vol_ratio < MIN_VOL_RATIO_BREAKOUT:
                blocchi.append(f"Volumi {vol_ratio:.2f}x (servono ≥ {MIN_VOL_RATIO_BREAKOUT:.2f}x sul Trigger Y {simb}{trigger_y_ref:.2f})")
        else:
            if sma200 > 0 and prezzo <= sma200:
                pct_200 = ((sma200 - prezzo) / prezzo) * 100.0
                blocchi.append(f"Manca +{pct_200:.1f}% per superare SMA 200 ({simb}{sma200:.2f})")
            elif sma50_prev is not None and sma50 <= sma50_prev:
                blocchi.append(f"SMA 50 ({simb}{sma50:.2f}) non ancora in salita rispetto a 10 sedute fa ({simb}{sma50_prev:.2f})")

            if dist_ema20_pct > MAX_DIST_EMA20_BUY_PCT:
                blocchi.append(
                    f"Troppo esteso ({dist_ema20_pct:+.1f}% sopra EMA 20 {simb}{ema20:.2f}, max +{MAX_DIST_EMA20_BUY_PCT:.1f}%): attendere pausa"
                )

            if len(d) >= 31:
                p_30g_fa = float(d["Close"].iloc[-31])
                if p_30g_fa > 0:
                    gain_30g = ((prezzo - p_30g_fa) / p_30g_fa) * 100.0
                    if gain_30g > MAX_GAIN_30G_SENZA_BASE_PCT and not _ha_fascia_stretta_5_chiusure_in_10gg(d):
                        blocchi.append(
                            f"Corsa {gain_30g:+.1f}% in 30gg senza pausa stretta (<4% per 5 chiusure): attendere consolidamento"
                        )

            if rsi > MAX_RSI_BUY:
                blocchi.append(f"RSI ipercomprato ({rsi:.1f}, max {MAX_RSI_BUY:.0f}): attendere scarico")

            if trigger_y_ref > prezzo * 1.002:
                pct_trig = ((trigger_y_ref - prezzo) / prezzo) * 100.0
                blocchi.append(f"Manca +{pct_trig:.1f}% al Trigger Y ({simb}{trigger_y_ref:.2f})")
            elif vol_ratio < MIN_VOL_RATIO_BREAKOUT:
                blocchi.append(f"Volumi ancora bassi ({vol_ratio:.2f}x, servono ≥ {MIN_VOL_RATIO_BREAKOUT:.2f}x sul breakout)")

            if str(spy_regime).lower() != "verde":
                blocchi.append(f"Regime SPY {str(spy_regime).upper()} (non verde — soglia confidenza {soglia_din})")

            if s_val < MIN_SSCORE_NUOVO_STD:
                blocchi.append(f"S-Score {s_val}/100 (< {MIN_SSCORE_NUOVO_STD} richiesto per BUY Nuovo)")

        if not blocchi:
            blocchi.append(f"In attesa di conferma finale sul Trigger Y ({simb}{trigger_y_ref:.2f})")

        # Mostra i 2 blocchi principali più immediati e leggibili
        cosa_manca_txt = " • ".join(blocchi[:2])

        return {
            "ticker": tk_up,
            "prezzo": round(prezzo, 2),
            "prezzo_eur": prezzo_eur,
            "simbolo": simb,
            "fase": fase_str,
            "s_score": s_val,
            "priorita": priorita,
            "is_figura_qp": has_figura_qp,
            "has_insider": has_motivo_a,
            "fig_rr": round(fig_rr, 2),
            "fig_conf": fig_conf,
            "trigger_y": round(trigger_y_ref, 2),
            "badge_motivo": badge_motivo,
            "perche_sorvegliato": perche_txt,
            "cosa_manca": cosa_manca_txt,
            "sec_buys": sec_buys,
            "sec_val_usd": round(sec_val, 2),
            "sec_ultimo_acquisto": sec_ult_it,
            "dist_ema20_pct": round(dist_ema20_pct, 1),
            "rsi": round(rsi, 1),
        }
    except Exception:
        return None


def ordina_sorvegliati_speciali(lista_candidati, buy_tickers_set=None, max_items=8, max_grafici=3):
    """
    Esclude i titoli già BUY verdi, deduplica per ticker e compone la lista unificata
    (max 6-8 titoli totali): fino ai migliori 3 candidati grafici quasi pronti +
    migliori Top Insider SEC e Forza Alta, dando priorità massima ai titoli con doppio catalizzatore.
    """
    esclusi = {str(t).strip().upper() for t in (buy_tickers_set or set()) if t}
    visti = {}
    for item in (lista_candidati or []):
        if not isinstance(item, dict):
            continue
        tk = str(item.get("ticker", "")).strip().upper()
        if not tk or tk in esclusi:
            continue
        prev = visti.get(tk)
        if prev is None or (item.get("priorita", 0), item.get("fig_rr", 0), item.get("sec_val_usd", 0), item.get("s_score", 0)) > (
            prev.get("priorita", 0), prev.get("fig_rr", 0), prev.get("sec_val_usd", 0), prev.get("s_score", 0)
        ):
            visti[tk] = item

    tutti = list(visti.values())
    # Seleziona fino ai migliori `max_grafici` (3) candidati con Figura Quasi Pronta
    grafici = sorted(
        [x for x in tutti if x.get("is_figura_qp")],
        key=lambda x: (
            int(bool(x.get("has_insider"))),
            float(x.get("fig_rr", 0.0)),
            int(x.get("fig_conf", 0)),
            int(x.get("s_score", 0)),
        ),
        reverse=True,
    )[: int(max_grafici)]
    scelti_tk = {x["ticker"] for x in grafici}

    # Completa la lista con i migliori Top Insider SEC e Forza Alta senza duplicati
    altri = sorted(
        [x for x in tutti if x["ticker"] not in scelti_tk],
        key=lambda x: (
            int(x.get("priorita", 0)),
            float(x.get("sec_val_usd", 0.0)),
            int(x.get("s_score", 0)),
            -abs(float(x.get("dist_ema20_pct", 0.0))),
        ),
        reverse=True,
    )

    unificati = grafici + altri
    unificati.sort(
        key=lambda x: (
            int(x.get("priorita", 0)),
            int(bool(x.get("is_figura_qp"))),
            float(x.get("sec_val_usd", 0.0)),
            float(x.get("fig_rr", 0.0)),
            int(x.get("s_score", 0)),
        ),
        reverse=True,
    )
    return unificati[: int(max_items)]


def _render_card_sorvegliato(st, sv):
    """
    Renderizza una card ad alto contrasto (astigmatismo-friendly) con cornice sinistra arancione (#F59E0B)
    e testi rigorosamente bianco puro (#F8FAFC) e grigio molto chiaro (#E2E8F0) su sfondo scuro.
    """
    simb = sv.get("simbolo", "$")
    p_val = float(sv.get("prezzo", 0) or 0)
    p_eur = float(sv.get("prezzo_eur", 0) or 0)
    prezzo_disp = f"{simb}{p_val:.2f} (€{p_eur:.2f})" if simb == "$" else f"€{p_val:.2f}"
    st.markdown(
        f"""
        <div style="background:#131722; border:1px solid #334155; border-left:4px solid #F59E0B;
                    border-radius:8px; padding:0.78rem 0.98rem; margin-bottom:0.55rem;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:0.40rem;">
                <div>
                    <span style="background:#1E293B; color:#F8FAFC; border:1px solid #F59E0B;
                                 font-size:0.74rem; font-weight:700; padding:3px 9px; border-radius:4px;">{sv.get('badge_motivo')}</span>
                    <span style="font-size:1.10rem; font-weight:800; color:#F8FAFC; margin-left:8px;">{sv.get('ticker')}</span>
                    <span style="font-family:'JetBrains Mono', monospace; color:#F8FAFC; font-size:0.90rem; font-weight:700; margin-left:8px;">{prezzo_disp}</span>
                </div>
                <span style="background:#0B0E11; border:1px solid #334155; color:#E2E8F0;
                             font-size:0.78rem; font-weight:700; padding:2px 8px; border-radius:5px;">
                    {sv.get('fase')} &nbsp;|&nbsp; RSI {sv.get('rsi', 0):.1f}
                </span>
            </div>
            <div style="font-size:0.84rem; color:#E2E8F0; margin-bottom:0.28rem; line-height:1.45;">
                📌 <b style="color:#F8FAFC;">Perché è sorvegliato:</b> {sv.get('perche_sorvegliato')}
            </div>
            <div style="font-size:0.84rem; color:#E2E8F0; line-height:1.45;">
                ⏳ <b style="color:#F8FAFC;">Cosa manca al BUY:</b> <span style="color:#F8FAFC; font-weight:600;">{sv.get('cosa_manca')}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
