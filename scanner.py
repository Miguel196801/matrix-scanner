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

st.set_page_config(page_title="MATRIX Mobile", layout="wide", page_icon="🛡️")

# ==============================================================================
# CONFIGURAZIONE MOBILE
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
    
    .signal-box {
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 0.5rem;
    }
    
    .signal-green {
        background-color: #d4edda;
        border-left: 5px solid #28a745;
    }
    
    .signal-yellow {
        background-color: #fff3cd;
        border-left: 5px solid #ffc107;
    }
    
    .signal-red {
        background-color: #f8d7da;
        border-left: 5px solid #dc3545;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# GESTIONE FILE
# ==============================================================================
PORTAFOGLIO_FILE = "portafoglio.json"
WATCHLIST_FILE = "watchlist.json"
STORICO_FILE = "storico_operazioni.json"

def carica_json(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def salva_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ==============================================================================
# PORTAFOGLIO INIZIALE (9 titoli)
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
            'grafico_ticker', 'grafico_prezzo_medio', 'spy_data', 'analisi_singola', 'analisi_risultati']:
    if key not in st.session_state:
        st.session_state[key] = None if key != 'pyramiding_alerts' else []

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
            return 0.0, " N/D"
        perf_ticker = (df_ticker['Close'].iloc[-1] / df_ticker['Close'].iloc[-60] - 1) * 100
        perf_spy = (df_spy['Close'].iloc[-1] / df_spy['Close'].iloc[-60] - 1) * 100
        rs_diff = perf_ticker - perf_spy
        if rs_diff > 5: return rs_diff, " Outperforming"
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
            return giorni_mancanti, f" Utili tra {giorni_mancanti}gg", False
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
            return sma200, "ALERTA", f"️ Sotto SMA200 ({sma200:.2f}) - Valuta uscita"
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

def genera_grafico_baleine(ticker, period, sma_short, sma_long, prezzo_medio_eur=None, timeframe='1d'):
    df = yf.Ticker(ticker).history(period=period)
    if df.empty: return None
    
    if timeframe == '1wk':
        df = df.resample('W').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'})
    
    df['SMA_Short'] = df['Close'].rolling(window=sma_short).mean()
    df['SMA_Long'] = df['Close'].rolling(window=sma_long).mean()
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['Vol_Media_20'] = df['Volume'].rolling(window=20).mean()
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.6, 0.2, 0.2],
                       subplot_titles=(f'{ticker} - {timeframe.upper()} | Rete delle Balene', 'Volumi', 'RSI'))
    
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Prezzo',
        increasing_line_color='#26a69a', increasing_fillcolor='#26a69a',
        decreasing_line_color='#ef5350', decreasing_fillcolor='#ef5350'
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_Short'], line=dict(color='#ff9800', width=2), name=f'SMA {sma_short}'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], line=dict(color='#9c27b0', width=1.5, dash='dash'), name='SMA 20'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_Long'], line=dict(color='#2196f3', width=2), name=f'SMA {sma_long}'), row=1, col=1)
    
    if prezzo_medio_eur is not None:
        fig.add_hline(y=prezzo_medio_eur, line_dash="dot", line_color="#00e676", line_width=2.5,
                     annotation_text=f"  Prezzo Medio: €{prezzo_medio_eur:.2f}", annotation_position="top left", row=1, col=1)
    
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_Short'], fill=None, mode='lines', line=dict(width=0), showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_Long'], fill='tonexty', mode='lines', line=dict(width=0), 
                            fillcolor='rgba(33, 150, 243, 0.12)', name='Zona Accumulo'), row=1, col=1)
    
    by_x, by_y, sell_x, sell_y = [], [], [], []
    for i in range(sma_long, len(df)):
        if (abs(df['Close'].iloc[i] - df['SMA_Short'].iloc[i]) / df['SMA_Short'].iloc[i] <= 0.02 and 
            df['Volume'].iloc[i] > df['Vol_Media_20'].iloc[i] and df['Close'].iloc[i] > df['Open'].iloc[i]):
            by_x.append(df.index[i]); by_y.append(df['Close'].iloc[i])
        if (df['Close'].iloc[i] < df['SMA_Long'].iloc[i] and df['Close'].iloc[i-1] >= df['SMA_Long'].iloc[i-1] and df['Volume'].iloc[i] > df['Vol_Media_20'].iloc[i]):
            sell_x.append(df.index[i]); sell_y.append(df['Close'].iloc[i])
    
    if by_x:
        fig.add_trace(go.Scatter(
            x=by_x, y=by_y, mode='markers',
            marker=dict(symbol='triangle-up', size=18, color='#00e676', line=dict(width=2, color='#00c853')),
            name='▲ BY (Buy)'
        ), row=1, col=1)
    
    if sell_x:
        fig.add_trace(go.Scatter(
            x=sell_x, y=sell_y, mode='markers',
            marker=dict(symbol='triangle-down', size=18, color='#ff1744', line=dict(width=2, color='#d50000')),
            name='▼ SELL'
        ), row=1, col=1)
    
    colors = ['#26a69a' if df['Close'].iloc[i] >= df['Open'].iloc[i] else '#ef5350' for i in range(len(df))]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='Volume', opacity=0.7), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Vol_Media_20'], line=dict(color='#9c27b0', width=2), name='Vol Medio 20'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#ff1744', width=2), name='RSI 14'), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#ff1744", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#00e676", row=3, col=1)
    fig.update_layout(height=600, xaxis_rangeslider_visible=False, template="plotly_white", 
                     legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return fig

def aggiorna_quotazioni_portafoglio(portafoglio, eurusd_rate):
    risultati = []
    for pos in portafoglio:
        ticker = pos['Ticker']
        try:
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info
            hist = ticker_obj.history(period="1d")
            if hist.empty:
                risultati.append({**pos, "Prezzo_Attuale_EUR": None, "Prezzo_Attuale_USD": None, "Valore_Attuale": None, "PnL_EUR": None, "PnL_%": None, "Trend": "N/D", "Earnings": "N/D"})
                continue
            
            currency = info.get('currency', 'USD')
            prezzo_raw = hist['Close'].iloc[-1]
            prezzo_eur = prezzo_raw / eurusd_rate if currency == 'USD' else prezzo_raw
            prezzo_usd = prezzo_raw if currency == 'USD' else prezzo_raw * eurusd_rate
            
            prezzo_medio = pos['Prezzo_Medio']
            quantita = pos['Quantita']
            valore_attuale = prezzo_eur * quantita
            valore_carico = prezzo_medio * quantita
            pnl_eur = valore_attuale - valore_carico
            pnl_pct = ((prezzo_eur / prezzo_medio) - 1) * 100 if prezzo_medio > 0 else 0
            
            trend = "🟢🟢 Forte +" if pnl_pct > 5 else ("🟢 +" if pnl_pct > 0 else ("🔴 -" if pnl_pct > -5 else "🔴 Forte -"))
            earnings_giorni, earnings_msg, _ = controlla_earnings(ticker_obj)
            
            risultati.append({**pos, "Prezzo_Attuale_EUR": round(prezzo_eur, 2), "Prezzo_Attuale_USD": round(prezzo_usd, 2),
                             "Valore_Attuale": round(valore_attuale, 2), "Valore_Carico": round(valore_carico, 2),
                             "PnL_EUR": round(pnl_eur, 2), "PnL_%": round(pnl_pct, 2), "Trend": trend,
                             "Earnings": earnings_msg})
        except Exception:
            risultati.append({**pos, "Prezzo_Attuale_EUR": None, "Prezzo_Attuale_USD": None, "Valore_Attuale": None, "PnL_EUR": None, "PnL_%": None, "Trend": "Errore", "Earnings": "N/D"})
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
    <h1>️ MATRIX DVMS</h1>
    <p style="margin: 0.5rem 0 0 0; opacity: 0.9;">Scanner Operativo Blindato v4.4</p>
</div>
""", unsafe_allow_html=True)

# Parametri (sidebar)
st.sidebar.header("⚙️ Parametri")
tickers_input = st.sidebar.text_area("Ticker (virgola):", "ADBE, RKLB, SOUN, IONQ, ASTS, BBAI, PLTR, ZETA, NKE, CRDO, AMD, CRWD, NU, NVDA, TSLA, S")tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
period = st.sidebar.selectbox("Periodo:", ["3mo", "6mo", "1y", "2y"], index=2)
sma_short = st.sidebar.slider("SMA Breve:", 10, 100, 50)
sma_long = st.sidebar.slider("SMA Lunga:", 50, 200, 200)

st.sidebar.markdown("---")
eurusd_rate = st.sidebar.number_input("EUR/USD:", min_value=0.8, max_value=1.5, value=1.12, step=0.001)
budget_psv = st.sidebar.number_input("Budget Spot ($):", min_value=100, max_value=5000, value=500, step=100)

st.sidebar.markdown("---")
st.sidebar.subheader(" Filtri")
filtro_s_score = st.sidebar.checkbox("Escludi S-Score < 60", True)
filtro_weinstein = st.sidebar.selectbox("Fase Weinstein minima", ["Tutte", "FASE 1 (Accumulazione)", "FASE 2 (Avanzamento)"])
ignore_fase_4 = st.sidebar.checkbox("Blocca Fase 4", True)
filtro_delisting = st.sidebar.checkbox("Blocca titoli <$1", True)

st.sidebar.markdown("---")
st.sidebar.subheader(" Protocolli Speciali")
show_insider = st.sidebar.checkbox("Mostra Insider", True)
show_balene = st.sidebar.checkbox("Mostra Balene", True)
show_short = st.sidebar.checkbox("Mostra Short Squeeze", True)
# Pulsante scansione
st.sidebar.markdown("---")
if st.sidebar.button("🔴 AVVIA SCANSIONE", type="primary", use_container_width=True):
    lista_fortezza, lista_cavalli, lista_monitor = [], [], []
    progress_bar = st.progress(0)
    watchlist_esistente = carica_json(WATCHLIST_FILE)
    if st.session_state.spy_data is None:
        try: st.session_state.spy_data = yf.Ticker("SPY").history(period=period)
        except: st.session_state.spy_data = None
    
    stats = {'by_count': 0, 'hold_count': 0, 'sell_count': 0, 'by_tickers': [], 'hold_tickers': [], 'sell_tickers': [], 'capital_used': 0, 'earnings_warnings': []}
    pyramiding_alerts = []
    
    portafoglio_attuale = st.session_state.portafoglio or carica_json(PORTAFOGLIO_FILE) or PORTAFOGLIO_INIZIALE
    ticker_in_portafoglio = {p['Ticker']: p for p in portafoglio_attuale}
    
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
                lista_cavalli.append({'Ticker': ticker, 'Prezzo EUR': prezzo_eur, 'Prezzo USD': prezzo_usd, 'S-Score': s_score, 'Fase': fase, 'Stato BY': " BY", 'Earnings': earnings_msg})
                stats['by_count'] += 1; stats['by_tickers'].append(ticker)
            elif is_fortezza_valida:
                stato_by_display = "🟢 BY" if trigger_by else " HOLD"
                lista_fortezza.append({'Ticker': ticker, 'Prezzo EUR': prezzo_eur, 'Prezzo USD': prezzo_usd, 'S-Score': s_score, 'Fase': fase, 'Stato BY': stato_by_display, 'Motivo BY': motivo_by, 'Trailing Stop': trailing_desc, 'Earnings': earnings_msg})
                if trigger_by: stats['by_count'] += 1; stats['by_tickers'].append(ticker)
                else: stats['hold_count'] += 1; stats['hold_tickers'].append(ticker)
            elif is_watchlist:
                motivi_hold = []
                if vol_ratio < 1.60: motivi_hold.append(f"Volumi bassi")
                if not figura_z: motivi_hold.append("No Figura Z")
                lista_monitor.append({'Ticker': ticker, 'Prezzo EUR': prezzo_eur, 'S-Score': s_score, 'Fase': fase, 'Motivo Hold': "; ".join(motivi_hold), 'Earnings': earnings_msg})
                stats['hold_count'] += 1; stats['hold_tickers'].append(ticker)
        except Exception:
            pass
            
    progress_bar.empty()
    stats['capital_used'] = sum(p.get('Capitale_USD', 0) for p in portafoglio_attuale)
    st.session_state.dashboard_stats = stats
    st.session_state.pyramiding_alerts = pyramiding_alerts
    
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
                <h3 style="margin: 0; color: #155724;">🟢 {stats['by_count']} Segnali BY</h3>
                <p style="margin: 0.5rem 0 0 0;">{', '.join(stats['by_tickers'])}</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="signal-box signal-yellow">
                <h3 style="margin: 0; color: #856404;">🟡 Nessun segnale BY oggi</h3>
                <p style="margin: 0.5rem 0 0 0;">Continua a monitorare</p>
            </div>
            """, unsafe_allow_html=True)
        
        if stats['hold_count'] > 0:
            st.markdown(f"""
            <div class="signal-box signal-yellow">
                <h4 style="margin: 0; color: #856404;">🟡 {stats['hold_count']} in Accumulo (HOLD)</h4>
                <p style="margin: 0.5rem 0 0 0;">{', '.join(stats['hold_tickers'])}</p>
            </div>
            """, unsafe_allow_html=True)
        
        if stats['earnings_warnings']:
            st.markdown(f"""
            <div class="signal-box signal-red">
                <h4 style="margin: 0; color: #721c24;">️ Attenzione Utili</h4>
                <p style="margin: 0.5rem 0 0 0;">{', '.join(stats['earnings_warnings'])}</p>
            </div>
            """, unsafe_allow_html=True)
        
        if st.session_state.pyramiding_alerts:
            st.markdown("---")
            st.subheader("🟢 Opportunità Pyramiding")
            for alert in st.session_state.pyramiding_alerts:
                ticker = alert['ticker']
                pyr = alert['pyramiding']
                st.markdown(f"""
                <div class="signal-box signal-green">
                    <h4 style="margin: 0; color: #155724;">{ticker} - Segnale BY</h4>
                    <p style="margin: 0.5rem 0;">
                        💶 Capitale: ~{pyr['capitale']}€<br>
                        📊 Azioni: {pyr['azioni']}<br>
                        📉 Stop: {pyr['stop_loss']}€<br>
                        🎯 Target: {pyr['target']}€
                    </p>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("👆 Clicca **🔴 AVVIA SCANSIONE** nella sidebar per vedere i segnali.")

# TAB 2: PORTAFOGLIO (MODIFICATO: mostra sempre i titoli)
with tab2:
    st.subheader("💼 Il Mio Portafoglio")
    
    if st.session_state.portafoglio is None:
        portafoglio_salvato = carica_json(PORTAFOGLIO_FILE)
        st.session_state.portafoglio = portafoglio_salvato if portafoglio_salvato else PORTAFOGLIO_INIZIALE
    
    # Pulsante aggiorna
    if st.button("🔄 Aggiorna Quotazioni", type="primary", use_container_width=True):
        st.session_state.portafoglio = aggiorna_quotazioni_portafoglio(st.session_state.portafoglio, eurusd_rate)
        st.session_state.last_update = datetime.now().strftime("%H:%M:%S")
        st.rerun()
    
    portafoglio = st.session_state.portafoglio
    
    if portafoglio:
        # Riepilogo totale (solo se ci sono quotazioni)
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
        
        # Separa Spot e PAC
        spot = [p for p in portafoglio if p.get('Tipo') == 'Spot']
        pac = [p for p in portafoglio if p.get('Tipo') == 'PAC']
        
        # Mostra SPOT
        if spot:
            st.markdown("### 📈 Azioni Singole (SPOT)")
            for pos in spot:
                pnl = pos.get('PnL_EUR', 0) or 0
                pnl_pct = pos.get('PnL_%', 0) or 0
                trend = pos.get('Trend', 'N/D')
                earnings = pos.get('Earnings', 'N/D')
                prezzo_attuale = pos.get('Prezzo_Attuale_EUR', 'N/A')
                
                if pnl > 0:
                    bg_color = "#d4edda"
                    text_color = "#155724"
                elif pnl < 0:
                    bg_color = "#f8d7da"
                    text_color = "#721c24"
                else:
                    bg_color = "#fff3cd"
                    text_color = "#856404"
                
                st.markdown(f"""
                <div style="background-color: {bg_color}; padding: 1rem; border-radius: 10px; margin-bottom: 0.5rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong style="font-size: 1.2rem;">{pos['Ticker']}</strong>
                            <span style="margin-left: 0.5rem; font-size: 0.9rem;">{trend}</span>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 1.1rem; font-weight: bold; color: {text_color};">
                                {pnl_pct:+.1f}%
                            </div>
                            <div style="font-size: 0.9rem; color: {text_color};">
                                {pnl:+.2f}€
                            </div>
                        </div>
                    </div>
                    <div style="margin-top: 0.5rem; font-size: 0.85rem; opacity: 0.8;">
                        {prezzo_attuale}€ | {earnings}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        # Mostra PAC
        if pac:
            st.markdown("### 🔄 Piani di Accumulo (PAC)")
            for pos in pac:
                pnl = pos.get('PnL_EUR', 0) or 0
                pnl_pct = pos.get('PnL_%', 0) or 0
                trend = pos.get('Trend', 'N/D')
                earnings = pos.get('Earnings', 'N/D')
                pac_sett = pos.get('PAC_Settimanale', 0)
                prezzo_attuale = pos.get('Prezzo_Attuale_EUR', 'N/A')
                
                if pnl > 0:
                    bg_color = "#d4edda"
                    text_color = "#155724"
                elif pnl < 0:
                    bg_color = "#f8d7da"
                    text_color = "#721c24"
                else:
                    bg_color = "#fff3cd"
                    text_color = "#856404"
                
                st.markdown(f"""
                <div style="background-color: {bg_color}; padding: 1rem; border-radius: 10px; margin-bottom: 0.5rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong style="font-size: 1.2rem;">{pos['Ticker']}</strong>
                            <span style="margin-left: 0.5rem; font-size: 0.9rem;">{trend}</span>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 1.1rem; font-weight: bold; color: {text_color};">
                                {pnl_pct:+.1f}%
                            </div>
                            <div style="font-size: 0.9rem; color: {text_color};">
                                {pnl:+.2f}€
                            </div>
                        </div>
                    </div>
                    <div style="margin-top: 0.5rem; font-size: 0.85rem; opacity: 0.8;">
                        {prezzo_attuale}€ | PAC: {pac_sett}€/sett | {earnings}
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("Portafoglio vuoto.")

# TAB 3: ANALISI SINGOLA (CORRETTO: risultati salvati in session state)
with tab3:
    st.subheader("🔍 Analisi Singola")
    ticker_input = st.text_input("Ticker:", value="ADBE")
    
    if st.button(" Analizza", type="primary", use_container_width=True):
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
                
                # Determina il segnale operativo
                if s_score >= 60 and "FASE 2" in fase:
                    if trigger_by:
                        segnale = "🟢 BY - Acquista"
                    else:
                        segnale = "🟡 HOLD - Monitora"
                elif 40 <= s_score <= 60 and ("FASE 1" in fase or "FASE 2" in fase) and vol_ratio >= 1.60 and figura_z:
                    segnale = " BY - Cavallo Pazzo"
                elif "FASE 4" in fase or s_score < 40:
                    segnale = "🔴 SELL - Evita"
                else:
                    segnale = "🟡 HOLD - In attesa"
                
                # SALVA I RISULTATI IN SESSION STATE (così sopravvivono al refresh)
                st.session_state.analisi_risultati = {
                    'ticker': ticker_s,
                    'segnale': segnale,
                    'prezzo_eur': prezzo_eur,
                    'prezzo_usd': prezzo_usd,
                    's_score': s_score,
                    'fase': fase,
                    'vol_ratio': vol_ratio,
                    'figura_z': figura_z,
                    'earnings_msg': earnings_msg,
                    'trigger_by': trigger_by,
                    'motivo_by': motivo_by
                }
        except Exception as e:
            st.error(f"Errore: {e}")
    
    # MOSTRA I RISULTATI (FUORI dal button, così persistono dopo il refresh)
    if st.session_state.analisi_risultati:
        r = st.session_state.analisi_risultati
        
        st.markdown(f"### {r['ticker']} - {r['segnale']}")
        
        col1, col2 = st.columns(2)
        col1.metric("💶 Prezzo EUR", f"€ {r['prezzo_eur']:.2f}")
        col2.metric("💵 Prezzo USD", f"$ {r['prezzo_usd']:.2f}")
        
        col3, col4 = st.columns(2)
        col3.metric("S-Score", r['s_score'])
        col4.metric("Fase", r['fase'])
        
        st.markdown(f"**Volume Ratio:** {r['vol_ratio']:.2f}")
        st.markdown(f"**Figura Z:** {'✅ Sì' if r['figura_z'] else '❌ No'}")
        st.markdown(f"**Prossimi Utili:** {r['earnings_msg']}")
        
        if "BY" in r['segnale']:
            st.success(f"**Segnale**: {r['motivo_by']}")
        elif "HOLD" in r['segnale']:
            st.warning(f"**Segnale**: {r['motivo_by']}")
        else:
            st.error("**Segnale**: Titolo in Fase 4 o S-Score troppo basso")
        
        # Pulsante grafico (ora funziona perché i risultati persistono)
        if st.button(f"📊 Mostra Grafico {r['ticker']}", type="secondary", use_container_width=True):
            st.session_state.grafico_ticker = r['ticker']
            st.session_state.grafico_prezzo_medio = None
            st.rerun()
    
    # MOSTRA IL GRAFICO (se selezionato)
    if st.session_state.grafico_ticker:
        st.markdown("---")
        st.subheader(f"📊 {st.session_state.grafico_ticker}")
        
        timeframe = st.selectbox("Timeframe:", ["1d (Daily)", "1wk (Weekly)"], index=0)
        tf_value = '1d' if "Daily" in timeframe else '1wk'
        
        fig = genera_grafico_baleine(st.session_state.grafico_ticker, period, sma_short, sma_long, 
                                      prezzo_medio_eur=st.session_state.grafico_prezzo_medio,
                                      timeframe=tf_value)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("Impossibile generare il grafico")
        
        if st.button("✖️ Chiudi grafico", use_container_width=True):
            st.session_state.grafico_ticker = None
            st.session_state.grafico_prezzo_medio = None
            st.rerun()
