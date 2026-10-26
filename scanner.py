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
from datetime import datetime

warnings.filterwarnings('ignore')

st.set_page_config(page_title="MATRIX Mobile V4.5", layout="wide", page_icon="🛡️")

# ==============================================================================
# CONFIGURAZIONE MOBILE - DARK MODE OPTIMIZED
# ==============================================================================
st.markdown("""
<style>
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
    }
    .stButton > button {
        width: 100%;
        padding: 0.75rem;
        font-size: 1.1rem;
        font-weight: bold;
    }
    footer {visibility: hidden;}
    .header-box {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 15px;
        text-align: center;
        margin-bottom: 1rem;
    }
    .header-box h1 {
        color: white;
        margin: 0;
        font-size: 1.8rem;
    }
    
    /* BOX PORTAFOGLIO DARK MODE MINIMALISTA */
    .portfolio-box {
        background-color: #1e293b;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 0.75rem;
        border-left: 5px solid #64748b;
    }
    .portfolio-box-green {
        background-color: #1e293b;
        border-left: 5px solid #10b981;
    }
    .portfolio-box-red {
        background-color: #1e293b;
        border-left: 5px solid #ef4444;
    }
    .portfolio-box-neutral {
        background-color: #1e293b;
        border-left: 5px solid #f59e0b;
    }
    .portfolio-ticker {
        color: #f8fafc;
        font-size: 1.3rem;
        font-weight: bold;
    }
    .portfolio-price {
        color: #cbd5e1;
        font-size: 0.9rem;
    }
    .portfolio-change-positive {
        color: #10b981;
        font-size: 1.2rem;
        font-weight: bold;
        text-align: right;
    }
    .portfolio-change-negative {
        color: #ef4444;
        font-size: 1.2rem;
        font-weight: bold;
        text-align: right;
    }
    .portfolio-change-neutral {
        color: #f59e0b;
        font-size: 1.2rem;
        font-weight: bold;
        text-align: right;
    }
    .portfolio-pnl {
        color: #94a3b8;
        font-size: 0.85rem;
        text-align: right;
    }
    .portfolio-info {
        color: #94a3b8;
        font-size: 0.8rem;
        margin-top: 0.3rem;
    }
    
    /* BOX ALLERTA */
    .signal-box {
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 0.5rem;
    }
    .signal-green {
        background-color: #064e3b;
        border-left: 5px solid #10b981;
        color: #d1fae5;
    }
    .signal-yellow {
        background-color: #451a03;
        border-left: 5px solid #f59e0b;
        color: #fef3c7;
    }
    .signal-red {
        background-color: #450a0a;
        border-left: 5px solid #ef4444;
        color: #fee2e2;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# GESTIONE FILE
# ==============================================================================
PORTAFOGLIO_FILE = "portafoglio.json"
WATCHLIST_FILE = "watchlist.json"
STORICO_FILE = "storico_operazioni.json"
IMPOSTAZIONI_FILE = "impostazioni.json"

def carica_json(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def salva_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ==============================================================================
# PORTAFOGLIO INIZIALE
# ==============================================================================
PORTAFOGLIO_INIZIALE = [
    {"Ticker": "TTWO", "Tipo": "Spot", "Quantita": 3.547945, "Prezzo_Medio": 187.55, "Categoria": "Azione"},
    {"Ticker": "ONDS", "Tipo": "Spot", "Quantita": 29.0, "Prezzo_Medio": 6.22, "Categoria": "Azione"},
    {"Ticker": "APP", "Tipo": "Spot", "Quantita": 0.48268, "Prezzo_Medio": 273.47, "Categoria": "Azione"},
    {"Ticker": "APLD", "Tipo": "PAC", "Quantita": 43.513985, "Prezzo_Medio": 21.07, "PAC_Settimanale": 30.0, "Categoria": "Azione"},
    {"Ticker": "SOFI", "Tipo": "PAC", "Quantita": 53.607426, "Prezzo_Medio": 14.31, "PAC_Settimanale": 15.0, "Categoria": "Azione"},
    {"Ticker": "NKE", "Tipo": "PAC", "Quantita": 5.485346, "Prezzo_Medio": 31.28, "PAC_Settimanale": 25.0, "Categoria": "Azione"},
    {"Ticker": "TTD", "Tipo": "PAC", "Quantita": 6.890467, "Prezzo_Medio": 13.60, "PAC_Settimanale": 5.0, "Categoria": "Azione"},
    {"Ticker": "VRT", "Tipo": "PAC", "Quantita": 0.335985, "Prezzo_Medio": 178.58, "PAC_Settimanale": 30.0, "Categoria": "Azione"},
    {"Ticker": "CRWD", "Tipo": "PAC", "Quantita": 0.092269, "Prezzo_Medio": 216.76, "PAC_Settimanale": 10.0, "Categoria": "Azione"},
]

# Session state
for key in ['portafoglio', 'last_update', 'dashboard_stats', 'pyramiding_alerts', 
            'scansione_completata', 'df_fortezza', 'df_cavalli', 'df_monitor',
            'grafico_ticker', 'grafico_prezzo_medio', 'spy_data', 'analisi_singola', 'analisi_risultati',
            'take_profit_alerts', 'zona_interesse_alerts']:
    if key not in st.session_state:
        st.session_state[key] = None if key not in ['pyramiding_alerts', 'take_profit_alerts', 'zona_interesse_alerts'] else []

# ==============================================================================
# FUNZIONI CORE
# ==============================================================================
def calcola_s_score(info):
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
    if len(df) < 200: return "Dati insufficienti"
    prezzo = df['Close'].iloc[-1]
    sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
    sma200_prev = df['Close'].rolling(window=200).mean().iloc[-20]
    pendenza = (sma200 - sma200_prev) / sma200_prev
    if prezzo < sma200 and pendenza < -0.01: return "FASE 4 (Declino)"
    elif prezzo > sma200 * 1.2 and pendenza > 0.02: return "FASE 3 (Distribuzione)"
    elif prezzo > sma200 and pendenza > 0.005: return "FASE 2 (Avanzamento)"
    else: return "FASE 1 (Accumulazione/Basing)"

def rileva_figura_z(df):
    if len(df) < 55: return False, "Dati insufficienti"
    sma50 = df['Close'].rolling(window=50).mean()
    for i in range(1, 6):
        idx_shakeout = -(i + 1)
        idx_close = -i
        if abs(idx_shakeout) >= len(df) or abs(idx_close) >= len(df): continue
        low_val = df['Low'].iloc[idx_shakeout]
        sma50_shake = sma50.iloc[idx_shakeout]
        close_val = df['Close'].iloc[idx_close]
        sma50_close = sma50.iloc[idx_close]
        if low_val < sma50_shake and close_val > sma50_close:
            return True, f"Figura Z confermata ({i} giorni fa)"
    return False, "Nessuna Figura Z negli ultimi 5 giorni"

def calcola_g_score_cavalli_pazzi(df, sma_short, sma_long):
    g_score = 40
    bonus_log = []
    prezzo = df['Close'].iloc[-1]
    sma_s = df['Close'].rolling(window=sma_short).mean().iloc[-1]
    sma_l = df['Close'].rolling(window=sma_long).mean().iloc[-1]
    vol_medio = df['Volume'].rolling(window=20).mean().iloc[-1]
    if df['Volume'].iloc[-1] > (vol_medio * 2.0) and prezzo > df['Open'].iloc[-1]:
        g_score += 10; bonus_log.append("Pocket Pivot (+10)")
    dist_medie = abs(sma_s - sma_l) / sma_l if sma_l != 0 else 0
    if dist_medie < 0.03:
        g_score += 5; bonus_log.append("Squeeze <3% (+5)")
    return g_score, ", ".join(bonus_log) if bonus_log else "Nessun bonus extra"

def calcola_g_score_fortezza(df, sma_short, sma_long, fase):
    g_score = 0
    bonus_log = []
    prezzo = df['Close'].iloc[-1]
    sma_s = df['Close'].rolling(window=sma_short).mean().iloc[-1]
    sma_l = df['Close'].rolling(window=sma_long).mean().iloc[-1]
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_oggi = rsi.iloc[-1] if not rsi.empty else 50
    if rsi_oggi is None: rsi_oggi = 50
    if "FASE 2" in fase or "FASE 3" in fase:
        if prezzo > sma_s > sma_l: g_score += 30; bonus_log.append("Trend perfetto (+30)")
        if df['Volume'].iloc[-1] > df['Volume'].rolling(window=20).mean().iloc[-1]: g_score += 20; bonus_log.append("Volume sopra media (+20)")
        if 50 <= rsi_oggi <= 70: g_score += 10; bonus_log.append("RSI sano (+10)")
        elif rsi_oggi > 70: g_score += 5; bonus_log.append("RSI ipercomprato (+5)")
    else:
        if prezzo < sma_s and prezzo < sma_l: g_score += 50; bonus_log.append("Compressione (+50)")
        dist_medie = abs(sma_s - sma_l) / sma_l if sma_l != 0 else 0
        if dist_medie < 0.03: g_score += 5; bonus_log.append("Squeeze <3% (+5)")
        vol_medio = df['Volume'].rolling(window=20).mean().iloc[-1]
        if df['Volume'].iloc[-1] > (vol_medio * 2.0) and df['Close'].iloc[-1] > df['Open'].iloc[-1]:
            g_score += 10; bonus_log.append("Pocket Pivot (+10)")
    return g_score, ", ".join(bonus_log) if bonus_log else "Nessun bonus"

def analizza_insider(ticker_obj, info, s_score, fase):
    alert = "Nessun dato"
    livello = "NEUTRO"
    try:
        insider_trans = ticker_obj.insider_transactions
        if insider_trans is None or insider_trans.empty: return alert, livello
        insider_trans = insider_trans.head(10)
        market_cap = info.get('marketCap', 0) or 0
        for _, row in insider_trans.iterrows():
            trans_type = str(row.get('Transaction', '')).upper()
            if 'PURCHASE' not in trans_type and 'BUY' not in trans_type: continue
            position = str(row.get('Position', '')).upper()
            value = row.get('Value', 0) or 0
            shares = row.get('Shares', 0) or 0
            is_top = any(x in position for x in ['CEO', 'CHIEF EXECUTIVE', 'PRESIDENT', 'CFO', 'CHIEF FINANCIAL'])
            if is_top and value > 1000000:
                alert = position + " ha acquistato $" + str(round(value, 0))
                livello = "FORTEZZA - BUY >1M$"
                break
            if market_cap > 0 and shares > 0:
                quota_pct = (shares * (value / shares if shares > 0 else 0)) / market_cap * 100
                if ('CEO' in position or 'PRESIDENT' in position) and quota_pct >= 0.05:
                    if s_score >= 60 and ("FASE 1" in fase or "FASE 2" in fase):
                        alert = position + " ha acquistato " + str(round(quota_pct, 3)) + "% MC"
                        livello = "ESTERNO - BUY >=0.05% MCAP"
                        break
    except Exception:
        return "Errore lettura insider", "NEUTRO"
    return alert, livello

def analizza_balene(ticker_obj):
    try:
        holders = ticker_obj.institutional_holders
        if holders is None or holders.empty: return "Nessun dato istituzionale"
        top3 = holders.head(3)
        holders_list = [row['Holder'] + " (" + str(row['Shares']) + ")" for _, row in top3.iterrows()]
        return "Top: " + ", ".join(holders_list)
    except Exception:
        return "Errore lettura balene"

def analizza_short_squeeze(info):
    si = info.get('shortPercentOfFloat', 0) or 0
    si_pct = si * 100
    dtc = info.get('shortRatio', 0) or 0
    stato = "POLVERIERA (>20%)" if si_pct > 20 else ("ATTENZIONE (>10%)" if si_pct > 10 else "Normale")
    return round(si_pct, 2), round(dtc, 2), stato, "SI" if dtc > 4 else "NO"

def verifica_delisting(info, df):
    prezzo = info.get('regularMarketPrice', 0) or (df['Close'].iloc[-1] if not df.empty else 0)
    return round(prezzo, 2), "CRITICO: Prezzo < $1" if prezzo < 1.0 else "OK"

def calcola_relative_strength(df_ticker, df_spy):
    try:
        if df_ticker is None or df_spy is None or len(df_ticker) < 60 or len(df_spy) < 60:
            return 0.0, "⚪ N/D"
        perf_ticker = (df_ticker['Close'].iloc[-1] / df_ticker['Close'].iloc[-60] - 1) * 100
        perf_spy = (df_spy['Close'].iloc[-1] / df_spy['Close'].iloc[-60] - 1) * 100
        rs_diff = perf_ticker - perf_spy
        if rs_diff > 5: return rs_diff, "🟢 Outperforming"
        elif rs_diff < -5: return rs_diff, "🔴 Underperforming"
        else: return rs_diff, "🟡 In linea"
    except:
        return 0.0, "⚪ N/D"

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
        elif giorni_mancanti <= 30:
            return giorni_mancanti, f"🟢 Utili tra {giorni_mancanti}gg", False
        else:
            return giorni_mancanti, f"⚪ Utili tra {giorni_mancanti}gg", False
    except:
        return None, "⚪ N/D", False

def calcola_trailing_stop(df, sma_short, sma_long):
    try:
        if len(df) < sma_long: return None, "N/D", "Dati insufficienti"
        prezzo = df['Close'].iloc[-1]
        sma50 = df['Close'].rolling(window=sma_short).mean().iloc[-1]
        sma200 = df['Close'].rolling(window=sma_long).mean().iloc[-1]
        if prezzo > sma50:
            return sma50, "SMA 50", f"Trailing: {sma50:.2f} (SMA50)"
        elif prezzo > sma200:
            return sma200, "SMA 200", f"Trailing: {sma200:.2f} (SMA200)"
        else:
            return sma200, "ALERTA", f"⚠️ Sotto SMA200 ({sma200:.2f}) - Valuta uscita"
    except:
        return None, "N/D", "Errore calcolo"

def verifica_trigger_by_fortezza(df, sma_short, ticker_obj=None):
    if len(df) < sma_short + 5: return False, "Dati insufficienti", False
    prezzo = df['Close'].iloc[-1]
    sma50 = df['Close'].rolling(window=sma_short).mean().iloc[-1]
    vol_medio = df['Volume'].rolling(window=20).mean().iloc[-1]
    vol_oggi = df['Volume'].iloc[-1]
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_oggi = rsi.iloc[-1] if not rsi.empty else 50
    
    distanza_sma50 = abs(prezzo - sma50) / sma50 * 100
    prezzo_vicino_sma50 = distanza_sma50 <= 3.0 or prezzo > sma50
    volume_ok = vol_oggi > vol_medio
    rsi_ok = rsi_oggi < 70 if rsi_oggi else True
    candela_verde = df['Close'].iloc[-1] > df['Open'].iloc[-1]
    
    earnings_giorni, earnings_msg, earnings_bloccato = controlla_earnings(ticker_obj) if ticker_obj else (None, "N/D", False)
    if earnings_bloccato: return False, earnings_msg, True
    
    if prezzo_vicino_sma50 and volume_ok and rsi_ok and candela_verde:
        return True, f"Pullback SMA50 completato (distanza: {distanza_sma50:.1f}%, Vol: {vol_oggi/vol_medio:.2f}x, RSI: {rsi_oggi:.0f})", False
    else:
        motivi = []
        if not prezzo_vicino_sma50:
            motivi.append(f"Prezzo troppo alto (+{distanza_sma50:.1f}% da SMA50)" if prezzo > sma50 * 1.05 else f"Prezzo sotto SMA50 (-{distanza_sma50:.1f}%)")
        if not volume_ok: motivi.append(f"Volume bassi ({vol_oggi/vol_medio:.2f}x media)")
        if not rsi_ok: motivi.append(f"RSI ipercomprato ({rsi_oggi:.0f})")
        if not candela_verde: motivi.append("Candela rossa")
        return False, "; ".join(motivi), False

def get_prezzi_corretti(ticker_obj, eurusd_rate):
    info = ticker_obj.info
    currency = info.get('currency', 'USD')
    history = ticker_obj.history(period='1d')
    if history.empty: return None, None, currency
    prezzo_raw = history['Close'].iloc[-1]
    if currency == 'USD':
        return round(prezzo_raw / eurusd_rate, 2), round(prezzo_raw, 2), currency
    else:
        return round(prezzo_raw, 2), round(prezzo_raw * eurusd_rate, 2), currency

def calcola_variazione_giornaliera(ticker_obj):
    """Calcola la variazione % giornaliera stile Yahoo Finance"""
    try:
        hist = ticker_obj.history(period="2d")
        if len(hist) < 2:
            return None, None
        prezzo_ieri = hist['Close'].iloc[-2]
        prezzo_oggi = hist['Close'].iloc[-1]
        variazione_pct = ((prezzo_oggi - prezzo_ieri) / prezzo_ieri) * 100
        variazione_abs = prezzo_oggi - prezzo_ieri
        return round(variazione_pct, 2), round(variazione_abs, 2)
    except:
        return None, None

def calcola_qualita_supporto(df):
    """Analizza come il prezzo arriva sul supporto"""
    try:
        if len(df) < 10:
            return "N/D", "Dati insufficienti"
        
        # Ultimi 3 giorni
        ultimi_3_vol = df['Volume'].iloc[-3:].mean()
        vol_medio_20 = df['Volume'].rolling(window=20).mean().iloc[-1]
        
        # Candele ultime 3 giornate
        candele_recenti = df.tail(3)
        ultima_candela = df.iloc[-1]
        corpo_candela = abs(ultima_candela['Close'] - ultima_candela['Open'])
        range_candela = ultima_candela['High'] - ultima_candela['Low']
        ombra_inferiore = min(ultima_candela['Open'], ultima_candela['Close']) - ultima_candela['Low']
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi_oggi = float(100 - (100 / (1 + rs)).iloc[-1]) if not rs.empty and not rs.iloc[-1] == 0 else 50
        
        # Analisi
        punti_positivi = 0
        punti_negativi = 0
        motivi = []
        
        # 1. Volumi in calo = positivo (esaurimento venditori)
        if ultimi_3_vol < vol_medio_20 * 0.8:
            punti_positivi += 2
            motivi.append("Volumi in esaurimento")
        elif ultimi_3_vol > vol_medio_20 * 1.3:
            punti_negativi += 2
            motivi.append("Volumi aggressivi")
        
        # 2. Candela con ombra inferiore lunga = rigetto (positivo)
        if range_candela > 0 and ombra_inferiore / range_candela > 0.5:
            punti_positivi += 2
            motivi.append("Ombra inferiore (rigetto)")
        
        # 3. Candela verde = positivo
        if ultima_candela['Close'] > ultima_candela['Open']:
            punti_positivi += 1
            motivi.append("Candela verde")
        else:
            punti_negativi += 1
            motivi.append("Candela rossa")
        
        # 4. RSI ipervenduto ma in ripresa
        if rsi_oggi < 35:
            punti_positivi += 1
            motivi.append("RSI ipervenduto")
        elif rsi_oggi > 60:
            punti_negativi += 1
        
        # Verdetto
        if punti_positivi >= punti_negativi + 2:
            return "ALTA", " " + "; ".join(motivi[:3])
        elif punti_negativi > punti_positivi:
            return "BASSA", " " + "; ".join(motivi[:3])
        else:
            return "MEDIA", "🟡 " + "; ".join(motivi[:3])
    except:
        return "N/D", "Errore calcolo"

def rileva_gap_storico(df, soglia_minima_pct=5.0):
    """Trova il gap storico non chiuso più significativo sotto il prezzo attuale"""
    try:
        if len(df) < 30:
            return None
        
        prezzo_attuale = df['Close'].iloc[-1]
        max_gap_sotto = None
        max_gap_size = 0
        
        # Scansione ultimi 6 mesi
        df_scan = df.tail(120).copy()
        df_scan['Prev_Close'] = df_scan['Close'].shift(1)
        
        for idx, row in df_scan.iterrows():
            if pd.isna(row['Prev_Close']):
                continue
            open_price = row['Open']
            prev_close = row['Prev_Close']
            
            # Gap down: open molto sotto prev close
            if open_price < prev_close:
                gap_pct = ((prev_close - open_price) / prev_close) * 100
                gap_bottom = open_price
                
                # Il gap è sotto il prezzo attuale e non è stato chiuso
                if gap_bottom < prezzo_attuale and gap_pct >= soglia_minima_pct:
                    # Verifica che il gap non sia stato riempito (nessun close sotto l'open dopo il gap)
                    mask_post = df_scan.index > idx
                    if mask_post.any():
                        post_gap = df_scan.loc[mask_post]
                        min_post = post_gap['Low'].min()
                        if min_post >= gap_bottom * 0.98:  # gap ancora aperto
                            if gap_pct > max_gap_size:
                                max_gap_size = gap_pct
                                max_gap_sotto = gap_bottom
        
        return round(max_gap_sotto, 2) if max_gap_sotto else None
    except:
        return None

def genera_grafico_baleine(ticker, period, sma_short, sma_long, prezzo_medio_eur=None, timeframe='1d'):
    df = yf.Ticker(ticker).history(period=period)
    if df.empty: return None
    
    if timeframe == '1wk':
        df = df.resample('W').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'})
    
    # Medie mobili
    df['SMA_Short'] = df['Close'].rolling(window=sma_short).mean()
    df['SMA_Long'] = df['Close'].rolling(window=sma_long).mean()
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['Vol_Media_20'] = df['Volume'].rolling(window=20).mean()
    df['VWAP'] = (df['Volume'] * (df['High'] + df['Low'] + df['Close']) / 3).cumsum() / df['Volume'].cumsum()
    
    # BOLLINGER BANDS (SMA 20 ± 2 deviazioni standard)
    df['BB_Middle'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['BB_Middle'] + (df['BB_Std'] * 2)
    df['BB_Lower'] = df['BB_Middle'] - (df['BB_Std'] * 2)
    
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    
    # Supporti/Resistenze
    recent_df = df.tail(60)
    supporto = recent_df['Low'].min()
    resistenza = recent_df['High'].max()
    
    # Rileva gap storico
    gap_level = rileva_gap_storico(df, soglia_minima_pct=5.0)
    
    prezzo_attuale = df['Close'].iloc[-1]
    
    # Layout migliorato: 4 righe (Prezzo 70%, Volumi 15%, BB RSI 15%)
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, 
        row_heights=[0.70, 0.15, 0.15],
        subplot_titles=(f'{ticker} ${prezzo_attuale:.2f} - {timeframe.upper()} | Rete delle Balene', 'Volumi', 'RSI')
    )
    
    # === PANNELLO PREZZO ===
        # Bollinger Bands (banda molto tenue, non disturba)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['BB_Upper'], line=dict(color='rgba(200, 200, 200, 0.2)', width=1, dash='dot'),
        name='BB Upper', showlegend=False
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['BB_Lower'], line=dict(color='rgba(200, 200, 200, 0.2)', width=1, dash='dot'),
        fill='tonexty', fillcolor='rgba(200, 200, 200, 0.03)',
        name='Bollinger Bands', showlegend=False
    ), row=1, col=1)
    
    # Candele
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Prezzo',
        increasing_line_color='#00e676', increasing_fillcolor='#00e676',
        decreasing_line_color='#ff1744', decreasing_fillcolor='#ff1744',
        increasing_line_width=1, decreasing_line_width=1
    ), row=1, col=1)
    
    # Medie mobili
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_Short'], line=dict(color='#ff9800', width=1.5), name=f'SMA {sma_short}'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], line=dict(color='#9c27b0', width=1.5, dash='dash'), name='SMA 20'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_Long'], line=dict(color='#2196f3', width=1.5), name=f'SMA {sma_long}'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['VWAP'], line=dict(color='#ffeb3b', width=1.5, dash='dot'), name='VWAP'), row=1, col=1)
    
    # Prezzo medio di carico
    if prezzo_medio_eur is not None:
        fig.add_hline(y=prezzo_medio_eur, line_dash="dot", line_color="#00e676", line_width=2,
                     annotation_text=f"  Prezzo Medio: €{prezzo_medio_eur:.2f}", annotation_position="top left", row=1, col=1)
    
        # Rete delle Balene (zona tra SMA 50 e SMA 200) - PIÙ EVIDENTE
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_Short'], fill=None, mode='lines', line=dict(width=0), showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_Long'], fill='tonexty', mode='lines', line=dict(width=0), 
                            fillcolor='rgba(59, 130, 246, 0.25)', name='🐋 Rete Balene'), row=1, col=1)
    
    # Supporto/Resistenza
    fig.add_hline(y=supporto, line_dash="dash", line_color="#00e676", line_width=1.5, 
                 annotation_text=f"  Supporto: {supporto:.2f}", annotation_position="bottom right", row=1, col=1)
    fig.add_hline(y=resistenza, line_dash="dash", line_color="#ff1744", line_width=1.5,
                 annotation_text=f"  Resistenza: {resistenza:.2f}", annotation_position="top right", row=1, col=1)
    
    # LINEA GAP (se presente)
    if gap_level:
        fig.add_hline(y=gap_level, line_dash="dot", line_color="#f59e0b", line_width=2,
                     annotation_text=f"  ️ Target Gap: {gap_level}", annotation_position="bottom left", row=1, col=1)
    
    # Marker BY e SELL
    by_x, by_y, sell_x, sell_y = [], [], [], []
    for i in range(sma_long, len(df)):
        if (abs(df['Close'].iloc[i] - df['SMA_Short'].iloc[i]) / df['SMA_Short'].iloc[i] <= 0.02 and 
            df['Volume'].iloc[i] > df['Vol_Media_20'].iloc[i] and df['Close'].iloc[i] > df['Open'].iloc[i]):
            by_x.append(df.index[i]); by_y.append(df['Close'].iloc[i])
        if (df['Close'].iloc[i] < df['SMA_Long'].iloc[i] and df['Close'].iloc[i-1] >= df['SMA_Long'].iloc[i-1] and df['Volume'].iloc[i] > df['Vol_Media_20'].iloc[i]):
            sell_x.append(df.index[i]); sell_y.append(df['Close'].iloc[i])
    
    if by_x:
        fig.add_trace(go.Scatter(x=by_x, y=by_y, mode='markers', marker=dict(symbol='triangle-up', size=18, color='#00e676', line=dict(width=2, color='#00c853')), name='▲ BY (Buy)'), row=1, col=1)
    if sell_x:
        fig.add_trace(go.Scatter(x=sell_x, y=sell_y, mode='markers', marker=dict(symbol='triangle-down', size=18, color='#ff1744', line=dict(width=2, color='#d50000')), name='▼ SELL'), row=1, col=1)
    
    # === PANNELLO VOLUMI ===
    colors = ['#00e676' if df['Close'].iloc[i] >= df['Open'].iloc[i] else '#ff1744' for i in range(len(df))]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='Volume', opacity=0.7, showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Vol_Media_20'], line=dict(color='#9c27b0', width=1.5), name='Vol Medio 20', showlegend=False), row=2, col=1)
    
    # === PANNELLO RSI ===
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#ff1744', width=1.5), name='RSI 14', showlegend=False), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#ff1744", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#00e676", row=3, col=1)
    
    # Layout ottimizzato per mobile
    fig.update_layout(
        height=1100,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        paper_bgcolor='#0f172a',
        plot_bgcolor='#1e293b',
        font=dict(color='#e2e8f0', size=11, family='Arial'),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, 
                   bgcolor='rgba(15, 23, 42, 0.9)', font=dict(size=9, color='#e2e8f0')),
        margin=dict(l=50, r=50, t=80, b=40),
        xaxis=dict(showgrid=True, gridcolor='#334155', gridwidth=0.5),
        yaxis=dict(showgrid=True, gridcolor='#334155', gridwidth=0.5)
    )
    
    return fig

def aggiorna_quotazioni_portafoglio(portafoglio, eurusd_rate):
    risultati = []
    for pos in portafoglio:
        ticker = pos['Ticker']
        try:
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info
            hist = ticker_obj.history(period="2d")
            if hist.empty:
                risultati.append({**pos, "Prezzo_Attuale_EUR": None, "Prezzo_Attuale_USD": None, 
                                 "Valore_Attuale": None, "PnL_EUR": None, "PnL_%": None, 
                                 "Trend": "N/D", "Earnings": "N/D", "Variazione_Pct": None, "Variazione_Abs": None})
                continue
            
            currency = info.get('currency', 'USD')
            prezzo_raw = hist['Close'].iloc[-1]
            prezzo_eur = prezzo_raw / eurusd_rate if currency == 'USD' else prezzo_raw
            prezzo_usd = prezzo_raw if currency == 'USD' else prezzo_raw * eurusd_rate
            
            # Variazione giornaliera
            var_pct, var_abs = calcola_variazione_giornaliera(ticker_obj)
            
            prezzo_medio = pos['Prezzo_Medio']
            quantita = pos['Quantita']
            valore_attuale = prezzo_eur * quantita
            valore_carico = prezzo_medio * quantita
            pnl_eur = valore_attuale - valore_carico
            pnl_pct = ((prezzo_eur / prezzo_medio) - 1) * 100 if prezzo_medio > 0 else 0
            
            trend = "🟢 Forte +" if pnl_pct > 5 else (" +" if pnl_pct > 0 else (" -" if pnl_pct > -5 else "🔴 Forte -"))
            earnings_giorni, earnings_msg, _ = controlla_earnings(ticker_obj)
            
            risultati.append({**pos, "Prezzo_Attuale_EUR": round(prezzo_eur, 2), "Prezzo_Attuale_USD": round(prezzo_usd, 2),
                             "Valore_Attuale": round(valore_attuale, 2), "Valore_Carico": round(valore_carico, 2),
                             "PnL_EUR": round(pnl_eur, 2), "PnL_%": round(pnl_pct, 2), "Trend": trend, 
                             "Earnings": earnings_msg, "Variazione_Pct": var_pct, "Variazione_Abs": var_abs})
        except Exception:
            risultati.append({**pos, "Prezzo_Attuale_EUR": None, "Prezzo_Attuale_USD": None, 
                             "Valore_Attuale": None, "PnL_EUR": None, "PnL_%": None, 
                             "Trend": "Errore", "Earnings": "N/D", "Variazione_Pct": None, "Variazione_Abs": None})
    return risultati

def calcola_pyramiding(posizione, prezzo_attuale_eur, budget_modulo=100.0):
    try:
        vecchia_qta = posizione['Quantita']
        vecchio_medio = posizione['Prezzo_Medio']
        azioni = math.floor(budget_modulo / prezzo_attuale_eur)
        if azioni <= 0: return None
        capitale = azioni * prezzo_attuale_eur
        stop_loss = prezzo_attuale_eur * 0.88
        target = prezzo_attuale_eur * 1.50
        rischio = (prezzo_attuale_eur - stop_loss) * azioni
        nuovo_valore = (vecchia_qta * vecchio_medio) + (azioni * prezzo_attuale_eur)
        nuova_qta = vecchia_qta + azioni
        nuovo_medio = nuovo_valore / nuova_qta
        return {'azioni': azioni, 'capitale': round(capitale, 2), 'stop_loss': round(stop_loss, 2),
                'target': round(target, 2), 'nuovo_medio': round(nuovo_medio, 2), 'rischio': round(rischio, 2),
                'vecchio_medio': vecchio_medio, 'nuova_qta': round(nuova_qta, 6)}
    except:
        return None

# ==============================================================================
# INTERFACCIA MOBILE-FIRST
# ==============================================================================
st.markdown("""
<div class="header-box">
    <h1>🛡️ MATRIX DVMS V4.5</h1>
    <p style="margin: 0.5rem 0 0 0; opacity: 0.9;">Scanner Operativo Blindato</p>
</div>
""", unsafe_allow_html=True)

# --- MEMORIA LISTA TICKER ---
if os.path.exists(IMPOSTAZIONI_FILE):
    with open(IMPOSTAZIONI_FILE, 'r', encoding='utf-8') as f:
        impostazioni = json.load(f)
else:
    impostazioni = {"lista_ticker_default": "ADBE, RKLB, SOUN, IONQ, ASTS, BBAI, PLTR, ZETA, NKE, CRDO, AMD, CRWD, NU, NVDA, TSLA, MCD, DIS, SBUX, PEP, INTC"}
    with open(IMPOSTAZIONI_FILE, 'w', encoding='utf-8') as f:
        json.dump(impostazioni, f)

st.sidebar.header("⚙️ Parametri")
tickers_input = st.sidebar.text_area("Ticker (virgola):", value=impostazioni.get("lista_ticker_default", "ADBE, RKLB, SOUN, IONQ, ASTS, BBAI, PLTR, ZETA, NKE, CRDO, AMD, CRWD, NU, NVDA, TSLA, MCD, DIS, SBUX, PEP, INTC"))
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
period = st.sidebar.selectbox("Periodo:", ["3mo", "6mo", "1y", "2y"], index=2)
sma_short = st.sidebar.slider("SMA Breve:", 10, 100, 50)
sma_long = st.sidebar.slider("SMA Lunga:", 50, 200, 200)

st.sidebar.markdown("---")
eurusd_rate = st.sidebar.number_input("EUR/USD:", min_value=0.8, max_value=1.5, value=1.12, step=0.001)
budget_psv = st.sidebar.number_input("Budget Spot ($):", min_value=100, max_value=5000, value=500, step=100)

st.sidebar.markdown("---")
st.sidebar.subheader("🔒 Filtri")
filtro_s_score = st.sidebar.checkbox("Escludi S-Score < 60", True)
filtro_weinstein = st.sidebar.selectbox("Fase Weinstein minima", ["Tutte", "FASE 1 (Accumulazione)", "FASE 2 (Avanzamento)"])
ignore_fase_4 = st.sidebar.checkbox("Blocca Fase 4", True)
filtro_delisting = st.sidebar.checkbox("Blocca titoli <$1", True)

st.sidebar.markdown("---")
st.sidebar.subheader("👁️ Protocolli Speciali")
show_insider = st.sidebar.checkbox("Mostra Insider", True)
show_balene = st.sidebar.checkbox("Mostra Balene", True)
show_short = st.sidebar.checkbox("Mostra Short Squeeze", True)

# Pulsante scansione
st.sidebar.markdown("---")
if st.sidebar.button("🔴 AVVIA SCANSIONE", type="primary", use_container_width=True):
    
    impostazioni["lista_ticker_default"] = tickers_input
    with open(IMPOSTAZIONI_FILE, 'w', encoding='utf-8') as f:
        json.dump(impostazioni, f)

    lista_fortezza, lista_cavalli, lista_monitor = [], [], []
    progress_bar = st.progress(0)
    watchlist_esistente = carica_json(WATCHLIST_FILE)
    if st.session_state.spy_data is None:
        try: st.session_state.spy_data = yf.Ticker("SPY").history(period=period)
        except: st.session_state.spy_data = None
    
    stats = {'by_count': 0, 'hold_count': 0, 'sell_count': 0, 'by_tickers': [], 'hold_tickers': [], 'sell_tickers': [], 'capital_used': 0, 'earnings_warnings': []}
    pyramiding_alerts = []
    take_profit_alerts = []
    zona_interesse_alerts = []
    
    portafoglio_attuale = st.session_state.portafoglio or carica_json(PORTAFOGLIO_FILE) or PORTAFOGLIO_INIZIALE
    ticker_in_portafoglio = {p['Ticker']: p for p in portafoglio_attuale}
    
    ticker_portafoglio = list(ticker_in_portafoglio.keys())
    tickers = list(set(tickers + ticker_portafoglio))
    tickers.sort()
    
    st.info(f"🔄 Scansione avviata per {len(tickers)} titoli (inclusi automaticamente i {len(ticker_portafoglio)} del portafoglio).")
    
    for i, ticker in enumerate(tickers):
        progress_bar.progress((i + 1) / len(tickers))
        try:
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period=period)
            info = ticker_obj.info
            if df.empty or len(df) < max(sma_long, 50): continue
            
            prezzo_eur, prezzo_usd, currency = get_prezzi_corretti(ticker_obj, eurusd_rate)
            if prezzo_eur is None: continue
            
            df['SMA_Short'] = df['Close'].rolling(window=sma_short).mean()
            df['SMA_Long'] = df['Close'].rolling(window=sma_long).mean()
            df['Vol_Media_20'] = df['Volume'].rolling(window=20).mean()
            
            vol_ratio = df.iloc[-1]['Volume'] / df.iloc[-1]['Vol_Media_20'] if df.iloc[-1]['Vol_Media_20'] > 0 else 0
            s_score = calcola_s_score(info)
            fase = rileva_fase_weinstein(df)
            figura_z, figura_z_msg = rileva_figura_z(df)
            g_score_cp, vector_cp = calcola_g_score_cavalli_pazzi(df, sma_short, sma_long)
            g_score_f, vector_f = calcola_g_score_fortezza(df, sma_short, sma_long, fase)
            si_pct, dtc, stato_short, trappola = analizza_short_squeeze(info)
            insider_alert, insider_livello = analizza_insider(ticker_obj, info, s_score, fase)
            balene_info = analizza_balene(ticker_obj)
            prezzo_usd_delisting, rischio_delisting = verifica_delisting(info, df)
            trigger_by, motivo_by, earnings_bloccato = verifica_trigger_by_fortezza(df, sma_short, ticker_obj)
            rs_pct, rs_indicatore = calcola_relative_strength(df, st.session_state.spy_data)
            trailing_level, trailing_tipo, trailing_desc = calcola_trailing_stop(df, sma_short, sma_long)
            earnings_giorni, earnings_msg, earnings_bloccato2 = controlla_earnings(ticker_obj)
            if earnings_bloccato2: stats['earnings_warnings'].append(f"{ticker} ({earnings_msg})")
            
            # Range 52 settimane
            range52_high = info.get('fiftyTwoWeekHigh')
            range52_low = info.get('fiftyTwoWeekLow')
            
            # --- CONTROLLO TAKE PROFIT (RSI >= 75) ---
            if ticker in ticker_in_portafoglio:
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi_oggi = float(100 - (100 / (1 + rs)).iloc[-1]) if not rs.empty and not rs.iloc[-1] == 0 else 50
                
                if rsi_oggi >= 75:
                    pos = ticker_in_portafoglio[ticker]
                    prezzo_medio = pos['Prezzo_Medio']
                    gain_pct = ((prezzo_eur / prezzo_medio) - 1) * 100 if prezzo_medio > 0 else 0
                    take_profit_alerts.append({
                        'ticker': ticker, 'rsi': round(rsi_oggi, 1), 'prezzo_attuale_eur': prezzo_eur,
                        'gain_pct': round(gain_pct, 1), 'tipo': pos.get('Tipo', 'Spot'),
                        'range52_high': range52_high, 'range52_low': range52_low
                    })
            
            # --- CONTROLLO ZONA DI INTERESSE + QUALITÀ SUPPORTO ---
            if ticker in ticker_in_portafoglio or s_score >= 60:
                sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
                distanza_sma200_pct = abs(df['Close'].iloc[-1] - sma200) / sma200 * 100
                if s_score >= 60 and distanza_sma200_pct <= 15.0:
                    qualita_sup, motivi_qualita = calcola_qualita_supporto(df)
                    zona_interesse_alerts.append({
                        'ticker': ticker, 'prezzo_attuale_eur': prezzo_eur,
                        'sma200_eur': round(sma200 / eurusd_rate if currency == 'USD' else sma200, 2),
                        'distanza_pct': round(distanza_sma200_pct, 1), 's_score': s_score,
                        'qualita_supporto': qualita_sup, 'motivi_qualita': motivi_qualita,
                        'range52_high': range52_high, 'range52_low': range52_low
                    })

            if filtro_delisting and "CRITICO" in rischio_delisting: 
                stats['sell_count'] += 1; stats['sell_tickers'].append(ticker); continue
            if ignore_fase_4 and "FASE 4" in fase: continue
            
            is_cp_valido = (40 <= s_score <= 60 and ("FASE 1" in fase or "FASE 2" in fase) and vol_ratio >= 1.60 and figura_z)
            is_fortezza_valida = (s_score >= 60 and "FASE 2" in fase)
            is_watchlist = (s_score >= 40 and ("FASE 1" in fase or "FASE 2" in fase) and not is_cp_valido and not is_fortezza_valida)
            
            if ticker in ticker_in_portafoglio and trigger_by:
                pos = ticker_in_portafoglio[ticker]
                pyramiding = calcola_pyramiding(pos, prezzo_eur, budget_modulo=100.0)
                if pyramiding:
                    pyramiding_alerts.append({'ticker': ticker, 'tipo': pos.get('Tipo', 'Spot'), 'prezzo_attuale': prezzo_eur, 'pyramiding': pyramiding})
            
            if is_cp_valido:
                lista_cavalli.append({'Ticker': ticker, 'Prezzo EUR': prezzo_eur, 'Prezzo USD': prezzo_usd, 'S-Score': s_score, 'Fase': fase, 'Stato BY': "🟢 BY", 'Earnings': earnings_msg})
                stats['by_count'] += 1; stats['by_tickers'].append(ticker)
            elif is_fortezza_valida:
                stato_by_display = "🟢 BY" if trigger_by else "🟡 HOLD"
                lista_fortezza.append({'Ticker': ticker, 'Prezzo EUR': prezzo_eur, 'Prezzo USD': prezzo_usd, 'S-Score': s_score, 'Fase': fase, 'Stato BY': stato_by_display, 'Motivo BY': motivo_by, 'Trailing Stop': trailing_desc, 'Earnings': earnings_msg})
                if trigger_by: stats['by_count'] += 1; stats['by_tickers'].append(ticker)
                else: stats['hold_count'] += 1; stats['hold_tickers'].append(ticker)
            elif is_watchlist:
                motivi_hold = []
                if vol_ratio < 1.60: motivi_hold.append("Volumi bassi")
                if not figura_z: motivi_hold.append("No Figura Z")
                lista_monitor.append({'Ticker': ticker, 'Prezzo EUR': prezzo_eur, 'S-Score': s_score, 'Fase': fase, 'Motivo Hold': "; ".join(motivi_hold), 'Earnings': earnings_msg})
                stats['hold_count'] += 1; stats['hold_tickers'].append(ticker)
        except Exception:
            pass
            
    progress_bar.empty()
    stats['capital_used'] = sum(p.get('Capitale_USD', 0) for p in portafoglio_attuale)
    st.session_state.dashboard_stats = stats
    st.session_state.pyramiding_alerts = pyramiding_alerts
    st.session_state.take_profit_alerts = take_profit_alerts
    st.session_state.zona_interesse_alerts = zona_interesse_alerts
    
    if lista_fortezza or lista_cavalli or lista_monitor:
        st.session_state.df_fortezza = pd.DataFrame(lista_fortezza) if lista_fortezza else None
        st.session_state.df_cavalli = pd.DataFrame(lista_cavalli) if lista_cavalli else None
        st.session_state.df_monitor = pd.DataFrame(lista_monitor) if lista_monitor else None
        st.session_state.scansione_completata = True
        st.rerun()
    else:
        st.warning("Nessun titolo soddisfa i criteri.")

# ==============================================================================
# TAB PRINCIPALI
# ==============================================================================
tab1, tab2, tab3 = st.tabs([" Dashboard", "💼 Portafoglio", "🔍 Analisi"])

# TAB 1: DASHBOARD
with tab1:
    st.subheader("📊 Segnali Operativi Oggi")
    
    if st.session_state.dashboard_stats:
        stats = st.session_state.dashboard_stats
        
        if stats['by_count'] > 0:
            st.markdown(f"""
            <div class="signal-box signal-green">
                <h3 style="margin: 0;">🟢 {stats['by_count']} Segnali BY</h3>
                <p style="margin: 0.5rem 0 0 0;">{', '.join(stats['by_tickers'])}</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="signal-box signal-yellow">
                <h3 style="margin: 0;">🟡 Nessun segnale BY oggi</h3>
                <p style="margin: 0.5rem 0 0 0;">Continua a monitorare</p>
            </div>
            """, unsafe_allow_html=True)
        
        if stats['hold_count'] > 0:
            st.markdown(f"""
            <div class="signal-box signal-yellow">
                <h4 style="margin: 0;">🟡 {stats['hold_count']} in Accumulo (HOLD)</h4>
                <p style="margin: 0.5rem 0 0 0;">{', '.join(stats['hold_tickers'])}</p>
            </div>
            """, unsafe_allow_html=True)
        
        if stats['earnings_warnings']:
            st.markdown(f"""
            <div class="signal-box signal-red">
                <h4 style="margin: 0;">️ Attenzione Utili</h4>
                <p style="margin: 0.5rem 0 0 0;">{', '.join(stats['earnings_warnings'])}</p>
            </div>
            """, unsafe_allow_html=True)
        
        # PYRAMIDING
        if st.session_state.pyramiding_alerts:
            st.markdown("---")
            st.subheader("🟢 Opportunità Pyramiding")
            for alert in st.session_state.pyramiding_alerts:
                ticker = alert['ticker']
                pyr = alert['pyramiding']
                st.markdown(f"""
                <div class="signal-box signal-green">
                    <h4 style="margin: 0;">{ticker} - Segnale BY</h4>
                    <p style="margin: 0.5rem 0;">
                        💶 Capitale: ~{pyr['capitale']}€<br>
                        📊 Azioni: {pyr['azioni']}<br>
                         Stop: {pyr['stop_loss']}€<br>
                        🎯 Target: {pyr['target']}€
                    </p>
                </div>
                """, unsafe_allow_html=True)

        # ZONA DI INTERESSE (con Qualità Supporto + Range 52s)
        if st.session_state.get('zona_interesse_alerts'):
            st.markdown("---")
            st.subheader("🟡 ZONA DI INTERESSE (Supporto + Rete delle Balene)")
            st.markdown("*Titoli solidi (Fortezze) che stanno testando un supporto chiave (SMA 200).*")
            for alert in st.session_state.zona_interesse_alerts:
                # Calcolo posizione nel range 52s
                range52_info = ""
                if alert.get('range52_high') and alert.get('range52_low'):
                    h, l = alert['range52_high'], alert['range52_low']
                    pos_pct = ((alert['prezzo_attuale_eur'] - l) / (h - l) * 100) if h != l else 50
                    range52_info = f"<br>📏 <strong>Range 52s:</strong> {l:.2f}€ - {h:.2f}€ (sei al {pos_pct:.0f}% del range)"
                
                st.markdown(f"""
                <div class="signal-box signal-yellow">
                    <h4 style="margin: 0;"> {alert['ticker']} (S-Score: {alert['s_score']})</h4>
                    <p style="margin: 0.5rem 0;">
                        💶 <strong>Prezzo attuale:</strong> {alert['prezzo_attuale_eur']}€<br>
                        🛡️ <strong>Supporto SMA 200:</strong> {alert['sma200_eur']}€ (Distanza: {alert['distanza_pct']}%)<br>
                        ⚖️ <strong>Qualità Supporto:</strong> {alert['motivi_qualita']}{range52_info}
                    </p>
                    <p style="margin: 0; font-size: 0.9rem;">
                        💡 <strong>Azione:</strong> Il titolo è in "Rete" su un supporto. Valuta un ordine limite o tienilo nella watchlist per il prossimo BY.
                    </p>
                </div>
                """, unsafe_allow_html=True)

        # TAKE PROFIT (con Range 52s)
        if st.session_state.get('take_profit_alerts'):
            st.markdown("---")
            st.subheader("🎯 ALLERTA TAKE PROFIT (Porta a casa tutto)")
            st.markdown("*Titoli in forte ipercomprato. Momento ottimale per vendere.*")
            for alert in st.session_state.take_profit_alerts:
                ticker = alert['ticker']
                gain_color = "#10b981" if alert['gain_pct'] > 0 else "#ef4444"
                
                range52_info = ""
                if alert.get('range52_high') and alert.get('range52_low'):
                    h, l = alert['range52_high'], alert['range52_low']
                    pos_pct = ((alert['prezzo_attuale_eur'] - l) / (h - l) * 100) if h != l else 50
                    range52_info = f"<br>📏 <strong>Range 52s:</strong> {l:.2f}€ - {h:.2f}€ (sei al {pos_pct:.0f}% del range)"
                
                st.markdown(f"""
                <div class="signal-box signal-red">
                    <h4 style="margin: 0;">🔴 {ticker} ({alert['tipo']}) - RSI: {alert['rsi']}</h4>
                    <p style="margin: 0.5rem 0;">
                        💶 <strong>Prezzo attuale:</strong> {alert['prezzo_attuale_eur']}€<br>
                        📈 <strong>Gain dal tuo medio:</strong> <span style="color: {gain_color}; font-weight: bold;">+{alert['gain_pct']}%</span>{range52_info}
                    </p>
                    <p style="margin: 0; font-size: 0.9rem;">
                        💡 <strong>Azione:</strong> Vendi l'intera posizione su Trade Republic e aggiorna il portafoglio.
                    </p>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info(" Clicca **🔴 AVVIA SCANSIONE** nella sidebar per vedere i segnali.")

# TAB 2: PORTAFOGLIO (REDESIGN DARK MODE)
with tab2:
    st.subheader("💼 Il Mio Portafoglio")
    
    if st.session_state.portafoglio is None:
        portafoglio_salvato = carica_json(PORTAFOGLIO_FILE)
        st.session_state.portafoglio = portafoglio_salvato if portafoglio_salvato else PORTAFOGLIO_INIZIALE
    
    if st.button("🔄 Aggiorna Quotazioni", type="primary", use_container_width=True):
        st.session_state.portafoglio = aggiorna_quotazioni_portafoglio(st.session_state.portafoglio, eurusd_rate)
        st.session_state.last_update = datetime.now().strftime("%H:%M:%S")
        st.rerun()
    
    portafoglio = st.session_state.portafoglio
    
    if portafoglio:
        has_live_data = any(p.get('Prezzo_Attuale_EUR') is not None for p in portafoglio)
        
        if has_live_data:
            totale_valore = sum(p.get('Valore_Attuale', 0) or 0 for p in portafoglio)
            totale_carico = sum(p.get('Valore_Carico', p.get('Prezzo_Medio', 0) * p.get('Quantita', 0)) for p in portafoglio)
            totale_pnl = totale_valore - totale_carico
            totale_pnl_pct = ((totale_valore / totale_carico) - 1) * 100 if totale_carico > 0 else 0
            
            col1, col2 = st.columns(2)
            col1.metric("💰 Valore Totale", f"€ {totale_valore:,.0f}")
            col2.metric("📈 P&L Totale", f"€ {totale_pnl:,.0f}", f"{totale_pnl_pct:+.1f}%")
            st.markdown("---")
        
        spot = [p for p in portafoglio if p.get('Tipo') == 'Spot']
        pac = [p for p in portafoglio if p.get('Tipo') == 'PAC']
        
        # Funzione helper per box dark mode
        def render_box_dark(pos):
            pnl = pos.get('PnL_EUR', 0) or 0
            pnl_pct = pos.get('PnL_%', 0) or 0
            trend = pos.get('Trend', 'N/D')
            earnings = pos.get('Earnings', 'N/D')
            prezzo_eur = pos.get('Prezzo_Attuale_EUR')
            prezzo_usd = pos.get('Prezzo_Attuale_USD')
            var_pct = pos.get('Variazione_Pct')
            var_abs = pos.get('Variazione_Abs')
            pac_sett = pos.get('PAC_Settimanale', 0)
            
            # Classe box in base al P&L
            if pnl > 0: box_class = "portfolio-box-green"
            elif pnl < 0: box_class = "portfolio-box-red"
            else: box_class = "portfolio-box-neutral"
            
            # Variazione giornaliera stile Yahoo
            if var_pct is not None:
                if var_pct > 0:
                    var_class = "portfolio-change-positive"
                    var_symbol = "▲"
                elif var_pct < 0:
                    var_class = "portfolio-change-negative"
                    var_symbol = "▼"
                else:
                    var_class = "portfolio-change-neutral"
                    var_symbol = "●"
                var_display = f"{var_symbol} {abs(var_pct):.2f}% ({var_abs:+.2f}€)"
            else:
                var_class = "portfolio-change-neutral"
                var_display = "N/D"
            
            # Info aggiuntive
            info_extra = f"{prezzo_eur}€" if prezzo_eur else "N/A"
            if prezzo_usd:
                info_extra += f" | ${prezzo_usd}"
            if pac_sett > 0:
                info_extra += f" | PAC: {pac_sett}€/sett"
            if earnings and earnings != "N/D":
                info_extra += f" | {earnings}"
            
            st.markdown(f"""
            <div class="portfolio-box {box_class}">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div>
                        <div class="portfolio-ticker">{pos['Ticker']}</div>
                        <div class="portfolio-info">{info_extra}</div>
                    </div>
                    <div>
                        <div class="{var_class}">{var_display}</div>
                        <div class="portfolio-pnl">{pnl_pct:+.1f}% | {pnl:+.2f}€</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        if spot:
            st.markdown("### 📈 Azioni Singole (SPOT)")
            for pos in spot:
                render_box_dark(pos)
        
        if pac:
            st.markdown("### 🔄 Piani di Accumulo (PAC)")
            for pos in pac:
                render_box_dark(pos)
    else:
        st.info("Portafoglio vuoto.")

# TAB 3: ANALISI SINGOLA
with tab3:
    st.subheader(" Analisi Singola")
    ticker_input = st.text_input("Ticker:", value="ADBE")
    
    if st.button("🔎 Analizza", type="primary", use_container_width=True):
        ticker_s = ticker_input.strip().upper()
        try:
            ticker_obj = yf.Ticker(ticker_s)
            df = ticker_obj.history(period=period)
            info = ticker_obj.info
            if df.empty or len(df) < 50:
                st.error("Dati insufficienti")
            else:
                prezzo_eur, prezzo_usd, currency = get_prezzi_corretti(ticker_obj, eurusd_rate)
                df['SMA_Short'] = df['Close'].rolling(window=sma_short).mean()
                df['SMA_Long'] = df['Close'].rolling(window=sma_long).mean()
                df['Vol_Media_20'] = df['Volume'].rolling(window=20).mean()
                vol_ratio = df.iloc[-1]['Volume'] / df.iloc[-1]['Vol_Media_20'] if df.iloc[-1]['Vol_Media_20'] > 0 else 0
                s_score = calcola_s_score(info)
                fase = rileva_fase_weinstein(df)
                figura_z, figura_z_msg = rileva_figura_z(df)
                trigger_by, motivo_by, earnings_bloccato = verifica_trigger_by_fortezza(df, sma_short, ticker_obj)
                earnings_giorni, earnings_msg, _ = controlla_earnings(ticker_obj)
                var_pct, var_abs = calcola_variazione_giornaliera(ticker_obj)
                
                if s_score >= 60 and "FASE 2" in fase:
                    segnale = "🟢 BY - Acquista" if trigger_by else "🟡 HOLD - Monitora"
                elif 40 <= s_score <= 60 and ("FASE 1" in fase or "FASE 2" in fase) and vol_ratio >= 1.60 and figura_z:
                    segnale = "🟢 BY - Cavallo Pazzo"
                elif "FASE 4" in fase or s_score < 40:
                    segnale = "🔴 SELL - Evita"
                else:
                    segnale = "🟡 HOLD - In attesa"
                
                st.session_state.analisi_risultati = {
                    'ticker': ticker_s, 'segnale': segnale, 'prezzo_eur': prezzo_eur, 'prezzo_usd': prezzo_usd,
                    's_score': s_score, 'fase': fase, 'vol_ratio': vol_ratio, 'figura_z': figura_z,
                    'earnings_msg': earnings_msg, 'trigger_by': trigger_by, 'motivo_by': motivo_by,
                    'var_pct': var_pct, 'var_abs': var_abs
                }
        except Exception as e:
            st.error(f"Errore: {e}")
    
    if st.session_state.analisi_risultati:
        r = st.session_state.analisi_risultati
        st.markdown(f"### {r['ticker']} - {r['segnale']}")
        
        col1, col2 = st.columns(2)
        col1.metric("💶 Prezzo EUR", f"€ {r['prezzo_eur']:.2f}")
        col2.metric(" Prezzo USD", f"$ {r['prezzo_usd']:.2f}")
        
        col3, col4 = st.columns(2)
        col3.metric("S-Score", r['s_score'])
        col4.metric("Fase", r['fase'])
        
        if r.get('var_pct') is not None:
            var_color = "green" if r['var_pct'] > 0 else "red"
            st.markdown(f"**Variazione oggi:** <span style='color:{var_color};font-weight:bold'>{r['var_pct']:+.2f}% ({r['var_abs']:+.2f}€)</span>", unsafe_allow_html=True)
        
        st.markdown(f"**Volume Ratio:** {r['vol_ratio']:.2f}")
        st.markdown(f"**Figura Z:** {'✅ Sì' if r['figura_z'] else '❌ No'}")
        st.markdown(f"**Prossimi Utili:** {r['earnings_msg']}")
        
        if "BY" in r['segnale']: st.success(f"**Segnale**: {r['motivo_by']}")
        elif "HOLD" in r['segnale']: st.warning(f"**Segnale**: {r['motivo_by']}")
        else: st.error("**Segnale**: Titolo in Fase 4 o S-Score troppo basso")
        
        if st.button(f"📊 Mostra Grafico {r['ticker']}", type="secondary", use_container_width=True):
            st.session_state.grafico_ticker = r['ticker']
            st.session_state.grafico_prezzo_medio = None
            st.rerun()
    
    if st.session_state.grafico_ticker:
        st.markdown("---")
        st.subheader(f"📊 {st.session_state.grafico_ticker}")
        timeframe = st.selectbox("Timeframe:", ["1d (Daily)", "1wk (Weekly)"], index=0)
        tf_value = '1d' if "Daily" in timeframe else '1wk'
        
        fig = genera_grafico_baleine(st.session_state.grafico_ticker, period, sma_short, sma_long, 
                                      prezzo_medio_eur=st.session_state.grafico_prezzo_medio, timeframe=tf_value)
        if fig:
            # ZOOM ABILITATO con due dita
            st.plotly_chart(fig, use_container_width=True, config={
                'scrollZoom': True,
                'displayModeBar': True,
                'modeBarButtonsToRemove': ['lasso2d', 'select2d']
            })
        else:
            st.error("Impossibile generare il grafico")
        
        if st.button("✖️ Chiudi grafico", use_container_width=True):
            st.session_state.grafico_ticker = None
            st.session_state.grafico_prezzo_medio = None
            st.rerun()
