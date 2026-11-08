import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import math
import warnings
import json
import os
import re
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')
st.set_page_config(page_title="MATRIX Mobile V6.1.3", layout="wide", page_icon="🛡️")

# ==============================================================================
# CSS MOBILE COMPATTO
# ==============================================================================
st.markdown("""
<style>
.main .block-container { padding-top: 1rem; padding-bottom: 1rem; }
.stButton > button { width: 100%; padding: 0.75rem; font-size: 1rem; font-weight: bold; }
footer {visibility: hidden;}
.header-box { background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); color: white; padding: 1.5rem; border-radius: 12px; text-align: center; margin-bottom: 1rem; }
.header-box h1 { color: white; margin: 0; font-size: 1.6rem; }
.portfolio-box { background-color: #1e293b; border-radius: 10px; padding: 1rem; margin-bottom: 0.75rem; border-left: 5px solid #64748b; }
.portfolio-ticker { color: #f8fafc; font-size: 1.2rem; font-weight: bold; }
.portfolio-info { color: #94a3b8; font-size: 0.75rem; margin-top: 0.3rem; }
.signal-box { padding: 0.8rem; border-radius: 8px; margin-bottom: 0.5rem; }
.signal-green { background-color: #064e3b; border-left: 4px solid #10b981; color: #d1fae5; }
.signal-yellow { background-color: #451a03; border-left: 4px solid #f59e0b; color: #fef3c7; }
.signal-red { background-color: #450a0a; border-left: 4px solid #ef4444; color: #fee2e2; }
.signal-history-box { background-color: #1e293b; border-radius: 8px; padding: 1rem; margin: 1rem 0; border: 2px solid #334155; }
.signal-history-title { color: #f8fafc; font-size: 1rem; font-weight: bold; margin-bottom: 0.5rem; }
.target-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }
.target-dot-achieved { background-color: #10b981; box-shadow: 0 0 4px #10b981; }
.target-dot-pending { background-color: #64748b; }
.target-tooltip { font-size: 0.7rem; color: #94a3b8; margin-left: 4px; }
.by-fabio-badge { background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 3px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: bold; margin-left: 8px; display: inline-block; box-shadow: 0 2px 6px rgba(16, 185, 129, 0.4); }
.breakout-card { background-color: #451a03; border-left: 5px solid #f59e0b; padding: 1rem; border-radius: 8px; margin-bottom: 0.5rem; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# GESTIONE FILE
# ==============================================================================
PORTAFOGLIO_FILE = "portafoglio.json"
PORTAFOGLIO_INIZIALE = [
    {"Ticker": "TTWO", "Tipo": "Spot", "Quantita": 3.547945, "Prezzo_Medio": 187.55},
    {"Ticker": "SOFI", "Tipo": "PAC", "Quantita": 53.607426, "Prezzo_Medio": 14.31, "PAC_Settimanale": 15.0},
]
PAPER_TRADING_FILE = "paper_trading.json"
SEGNALI_STORICI_FILE = "segnali_storici.json"
REGISTRO_VENDITE_FILE = "registro_vendite.json"
MINUSVALENZE_FILE = "minusvalenze.json"
IMPOSTAZIONI_FILE = "impostazioni.json"

def carica_json(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def salva_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ==============================================================================
# SEMAFORO DI MERCATO
# ==============================================================================
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
            if not vix.empty: vix_valore = float(vix['Close'].iloc[-1])
        except: pass
        if vix_valore is not None:
            if spy_prezzo > spy_sma10 and vix_valore < 20: stato, messaggio = 'verde', '🟢 MERCATO RIALZISTA'
            elif spy_prezzo < spy_sma10 or vix_valore > 30: stato, messaggio = 'rosso', '🔴 MERCATO RIBASSISTA'
            else: stato, messaggio = 'giallo', '🟡 MERCATO LATERALE'
        else:
            if spy_prezzo > spy_sma10: stato, messaggio = 'verde', '🟢 SPY RIALZISTA'
            elif spy_prezzo < spy_sma10: stato, messaggio = 'rosso', '🔴 SPY RIBASSISTA'
            else: stato, messaggio = 'giallo', '🟡 SPY LATERALE'
        return {'stato': stato, 'spy_prezzo': round(spy_prezzo, 2), 'spy_sma10': round(spy_sma10, 2), 'vix': round(vix_valore, 2) if vix_valore else None, 'messaggio': messaggio}
    except Exception as e:
        return {'stato': 'giallo', 'spy_prezzo': None, 'spy_sma10': None, 'vix': None, 'messaggio': f'Errore: {str(e)}'}

# ==============================================================================
# S-SCORE CON FALLBACK
# ==============================================================================
def calcola_s_score(info, ticker=None):
    fallback_scores = {
        'META': 90, 'NVDA': 100, 'MSFT': 95, 'AAPL': 90, 'GOOGL': 90, 'AMZN': 85, 
        'PLTR': 80, 'ADBE': 85, 'AVGO': 85, 'CRM': 80, 'NOW': 85, 'PANW': 80,
        'FTNT': 75, 'INTU': 80, 'QCOM': 75, 'MU': 70, 'MRVL': 75, 'CRDO': 70, 
        'TSLA': 70, 'AMD': 80, 'NKE': 75, 'CRWD': 80, 'SOFI': 65, 'VRT': 70,
        'TTWO': 70, 'APP': 65, 'TTD': 65, 'APLD': 60, 'BBAI': 55, 'IONQ': 60, 
        'RKLB': 65, 'SOUN': 60, 'ASTS': 55, 'ZETA': 60, 'NU': 75, 'MCD': 85, 
        'DIS': 75, 'SBUX': 70, 'PEP': 80, 'INTC': 65, 'NBIS': 60, 'WDC': 70, 
        'COHR': 70, 'LLY': 90, 'GLW': 75, 'TXN': 80
    }
    try:
        if ticker:
            ticker_upper = str(ticker).strip().upper()
            if ticker_upper in fallback_scores: return fallback_scores[ticker_upper]
        symbol = str(info.get('symbol', '')).upper()
        if symbol and symbol in fallback_scores: return fallback_scores[symbol]
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
    except: return 50

# ==============================================================================
# WEINSTEIN AVANZATO
# ==============================================================================
def rileva_fase_weinstein(df):
    if len(df) < 200: return "Dati insufficienti"
    prezzo = df['Close'].iloc[-1]
    sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
    sma200_prev = df['Close'].rolling(window=200).mean().iloc[-20]
    sma50 = df['Close'].rolling(window=50).mean().iloc[-1]
    slope_sma200 = (sma200 - sma200_prev) / sma200_prev if sma200_prev > 0 else 0
    if prezzo < sma200 and slope_sma200 < -0.01:
        return "FASE 1 (Accumulazione)" if (prezzo > sma50 and abs(prezzo - sma200)/sma200 < 0.03) else "FASE 4 (Declino Strutturale)"
    if prezzo < sma50 and prezzo > sma200 and slope_sma200 > 0.005:
        return "CORREZIONE in Trend (Pullback Fase 2)"
    if prezzo > sma200 * 1.2 and slope_sma200 > 0.02: return "FASE 3 (Distribuzione)"
    if prezzo > sma200 and slope_sma200 > 0.005: return "FASE 2 (Avanzamento)"
    return "FASE 1 (Accumulazione)"

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
    return False, "Nessuna Figura Z"

# ==============================================================================
# VERIFICA BY FORTEZZA (3 valori di ritorno)
# ==============================================================================
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
    rsi_oggi = float(100 - (100 / (1 + (gain/loss))).iloc[-1]) if not (gain/loss).empty else 50
    fase = rileva_fase_weinstein(df)
    if "FASE 4" in fase: return False, f"❌ Bloccato: {fase}", False
    if rsi_oggi > 70: return False, f"❌ Bloccato: RSI ipercomprato ({rsi_oggi:.0f})", False
    distanza_sma50 = abs(prezzo - sma50) / sma50 * 100
    prezzo_vicino_sma50 = distanza_sma50 <= 3.0 or prezzo > sma50
    volume_ok = vol_oggi > vol_medio
    rsi_ok = rsi_oggi < 70
    candela_verde = df['Close'].iloc[-1] > df['Open'].iloc[-1]
    earnings_giorni, earnings_msg, earnings_bloccato = controlla_earnings(ticker_obj) if ticker_obj else (None, "N/D", False)
    if earnings_bloccato: return False, earnings_msg, True
    if rsi_oggi < 30 and fase in ["FASE 1 (Accumulazione)", "FASE 2 (Avanzamento)"] and vol_oggi > vol_medio * 1.5:
        return True, f"✅ Oversold bounce: RSI {rsi_oggi:.0f}, {fase}, Vol {vol_oggi/vol_medio:.2f}x", False
    if prezzo_vicino_sma50 and volume_ok and rsi_ok and candela_verde:
        return True, f"Pullback SMA50 completato (Vol: {vol_oggi/vol_medio:.2f}x, RSI: {rsi_oggi:.0f})", False
    motivi = []
    if not prezzo_vicino_sma50: motivi.append(f"Prezzo fuori SMA50 ({distanza_sma50:.1f}%)")
    if not volume_ok: motivi.append(f"Volume bassi ({vol_oggi/vol_medio:.2f}x)")
    if not rsi_ok: motivi.append(f"RSI ipercomprato ({rsi_oggi:.0f})")
    if not candela_verde: motivi.append("Candela rossa")
    return False, "; ".join(motivi), False

# ==============================================================================
# BY FABIO
# ==============================================================================
def verifica_by_fabio(df, sma_short, ticker_obj=None):
    if len(df) < sma_short + 5: return False, "Dati insufficienti"
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
    rsi_oggi = float(100 - (100 / (1 + rs)).iloc[-1]) if not rs.empty else 50
    slope_sma200 = (sma200 - sma200_prev) / sma200_prev if sma200_prev > 0 else 0
    s_score = calcola_s_score(ticker_obj.info, ticker_obj.ticker) if ticker_obj else 50
    if s_score < 70: return False, f"S-Score {s_score} < 70"
    if prezzo > sma50 and vol_oggi > vol_medio * 1.3 and 40 <= rsi_oggi <= 65:
        if df['Close'].iloc[-2] < df['Close'].rolling(window=sma_short).mean().iloc[-2]:
            return True, f"✅ BREAKOUT Fortezza: S-Score {s_score}, Vol {vol_oggi/vol_medio:.2f}x, RSI {rsi_oggi:.0f}"
    distanza_sma200 = (prezzo - sma200) / sma200 * 100
    if 0 <= distanza_sma200 <= 3.0 and slope_sma200 > 0 and 40 <= rsi_oggi <= 60:
        return True, f"✅ PULLBACK Fortezza: S-Score {s_score}, Distanza SMA200 {distanza_sma200:.1f}%, RSI {rsi_oggi:.0f}"
    return False, f"Condizioni geometriche non soddisfatte"

# ==============================================================================
# TARGET GRAFICI
# ==============================================================================
def calcola_target(ticker_obj, prezzo_medio, prezzo_attuale):
    try:
        hist = ticker_obj.history(period='1y')
        if hist.empty: return None
        rendimenti = hist['Close'].pct_change().dropna()
        volatilita = rendimenti.std() * math.sqrt(252) if len(rendimenti) > 0 else 0.15
        high_52w = hist['High'].max()
        picchi = []
        for i in range(20, len(hist) - 20):
            if hist['High'].iloc[i] == hist['High'].iloc[i-20:i+21].max():
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
            if not current or not entry or not target or target <= entry: return 100.0
            return max(0.0, min(100.0, round(((current - entry) / (target - entry)) * 100, 1)))
        return {
            't1': round(t1, 2), 'prog1': calc_progress(prezzo_attuale, prezzo_medio, t1), 'upside1': round(((t1 / prezzo_attuale) - 1) * 100, 1) if prezzo_attuale > 0 else 0,
            't2': round(t2, 2), 'prog2': calc_progress(prezzo_attuale, prezzo_medio, t2), 'upside2': round(((t2 / prezzo_attuale) - 1) * 100, 1) if prezzo_attuale > 0 else 0,
            't3': round(t3, 2), 'prog3': calc_progress(prezzo_attuale, prezzo_medio, t3), 'upside3': round(((t3 / prezzo_attuale) - 1) * 100, 1) if prezzo_attuale > 0 else 0,
            'sl': round(sl, 2), 'sl_down': round(((sl / prezzo_attuale) - 1) * 100, 1) if prezzo_attuale > 0 else 0
        }
    except: return None

# ==============================================================================
# PODC
# ==============================================================================
def avvia_podc(portafoglio, eurusd_rate, catalizzatori_input):
    catalizzatori = {}
    if catalizzatori_input:
        for item in catalizzatori_input.split(';'):
            if ':' in item:
                ticker, resto = item.split(':', 1)
                match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', resto)
                if match:
                    anno = '20' + match.group(3) if len(match.group(3)) == 2 else match.group(3)
                    try: catalizzatori[ticker.strip().upper()] = datetime(int(anno), int(match.group(2)), int(match.group(1)))
                    except: pass
    registro_vendite = carica_json(REGISTRO_VENDITE_FILE)
    oggi = datetime.now()
    ticker_venduti_recenti = {v.get('Ticker', '').strip().upper() for v in registro_vendite if (oggi - datetime.strptime(v.get('Data', ''), "%Y-%m-%d")).days <= 5}
    gain_suggestions, loss_candidates, gain_analyzed, loss_rejected = [], [], [], []
    total_capital_freed = 0.0
    for pos in portafoglio:
        ticker = pos['Ticker']
        try:
            prezzo_attuale = pos.get('Prezzo_Attuale_EUR')
            if not prezzo_attuale: continue
            ticker_obj = yf.Ticker(ticker)
            hist = ticker_obj.history(period='1y')
            info = ticker_obj.info
            prezzo_medio = pos['Prezzo_Medio']
            qty = pos['Quantita']
            pnl_pct = ((prezzo_attuale / prezzo_medio) - 1) * 100
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = float(100 - (100 / (1 + rs)).iloc[-1]) if not rs.empty else 50
            s_score = calcola_s_score(info)
            fase = rileva_fase_weinstein(hist)
            targets = calcola_target(ticker_obj, prezzo_medio, prezzo_attuale)
            upside1 = targets['upside1'] if targets else 100
            pos_data = {'ticker': ticker, 'prezzo_attuale': prezzo_attuale, 'prezzo_medio': prezzo_medio, 'qty': qty, 'pnl_pct': pnl_pct, 'rsi': rsi, 's_score': s_score, 'fase': fase, 'upside1': upside1, 'valore_totale': prezzo_attuale * qty}
            if pnl_pct >= 0:
                if ticker in ticker_venduti_recenti:
                    gain_analyzed.append({'ticker': ticker, 'pnl_pct': pnl_pct, 'reason': f"Gain +{pnl_pct:.1f}% - ✅ Vendita già registrata negli ultimi 5 giorni."})
                    continue
                if pnl_pct >= 5.0 and (upside1 < 10.0 or rsi > 70):
                    capital_freed = pos_data['valore_totale'] * 0.5
                    total_capital_freed += capital_freed
                    gain_suggestions.append({**pos_data, 'capital_freed': capital_freed})
                    gain_analyzed.append({'ticker': ticker, 'pnl_pct': pnl_pct, 'reason': f"Gain +{pnl_pct:.1f}%, Upside {upside1:.1f}%, RSI {rsi:.1f} -> Vendi 50%"})
                else:
                    gain_analyzed.append({'ticker': ticker, 'pnl_pct': pnl_pct, 'reason': f"Gain +{pnl_pct:.1f}% -> Mantieni"})
            else:
                if pnl_pct < -5.0:
                    if fase == "FASE 4 (Declino Strutturale)" or s_score < 65: loss_rejected.append({'ticker': ticker, 'pnl_pct': pnl_pct, 'reason': "Fase 4 o S-Score < 65"})
                    elif s_score >= 70 and "FASE" in fase and rsi < 40: loss_candidates.append(pos_data)
                    else: loss_rejected.append({'ticker': ticker, 'pnl_pct': pnl_pct, 'reason': "Non soddisfa criteri Fortezza"})
                else:
                    loss_rejected.append({'ticker': ticker, 'pnl_pct': pnl_pct, 'reason': "Loss < 5%"})
        except Exception as e:
            loss_rejected.append({'ticker': ticker, 'pnl_pct': 0, 'reason': f"Errore: {str(e)}"})
    suggestions = []
    for cand_a in gain_suggestions:
        for cand_b in loss_candidates:
            capital = cand_a['capital_freed']
            if capital < 50: continue
            new_qty = cand_b['qty'] + (capital / cand_b['prezzo_attuale'])
            new_avg = ((cand_b['qty'] * cand_b['prezzo_medio']) + capital) / new_qty
            new_pnl_pct = ((cand_b['prezzo_attuale'] / new_avg) - 1) * 100
            if (new_pnl_pct - cand_b['pnl_pct']) >= 2.0 or (cand_b['pnl_pct'] < -10 and new_pnl_pct > -5):
                suggestions.append({'sell_ticker': cand_a['ticker'], 'sell_pct': 50, 'capital_freed': capital, 'buy_ticker': cand_b['ticker'], 'old_avg': cand_b['prezzo_medio'], 'new_avg': new_avg, 'old_pnl': cand_b['pnl_pct'], 'new_pnl': new_pnl_pct})
    return {'suggestions': suggestions, 'gain_analyzed': gain_analyzed, 'loss_rejected': loss_rejected, 'loss_candidates': loss_candidates, 'total_capital_freed': total_capital_freed}

# ==============================================================================
# ALLOCAZIONE DINAMICA
# ==============================================================================
def genera_piano_allocazione(portafoglio, liquidita_totale, eurusd_rate):
    by_fabio_tickers, pac_ottimali, watchlist_breakout = [], [], []
    for pos in portafoglio:
        ticker = pos['Ticker']
        try:
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period='1y')
            info = ticker_obj.info
            if df.empty: continue
            s_score = calcola_s_score(info, ticker)
            fase = rileva_fase_weinstein(df)
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_oggi = float(100 - (100 / (1 + rs)).iloc[-1]) if not rs.empty else 50
            prezzo = df['Close'].iloc[-1]
            sma50 = df['Close'].rolling(window=50).mean().iloc[-1]
            vol_medio = df['Volume'].rolling(window=20).mean().iloc[-1]
            vol_oggi = df['Volume'].iloc[-1]
            trigger_by_fabio, _ = verifica_by_fabio(df, 50, ticker_obj)
            if trigger_by_fabio:
                by_fabio_tickers.append({'ticker': ticker, 's_score': s_score, 'fase': fase, 'rsi': rsi_oggi, 'prezzo': prezzo})
                continue
            if pos.get('Tipo') == 'PAC' and fase in ["FASE 2 (Avanzamento)", "FASE 1 (Accumulazione)"]:
                pac_ottimali.append({'ticker': ticker, 's_score': s_score, 'fase': fase, 'rsi': rsi_oggi, 'prezzo': prezzo})
                continue
            if s_score >= 65 and prezzo < sma50 * 0.95 and 30 <= rsi_oggi <= 50 and vol_oggi > vol_medio * 1.2:
                watchlist_breakout.append({'ticker': ticker, 's_score': s_score, 'fase': fase, 'rsi': rsi_oggi, 'prezzo': prezzo})
        except: continue
    capitale_residuo = liquidita_totale
    allocazioni = []
    if by_fabio_tickers:
        importo = (capitale_residuo * 0.45) / len(by_fabio_tickers)
        for t in by_fabio_tickers:
            allocazioni.append({'ticker': t['ticker'], 'importo': round(importo, 2), 'motivazione': f"BY FABIO attivo | S-Score {t['s_score']} | {t['fase']}", 'priorita': 1})
        capitale_residuo -= importo * len(by_fabio_tickers)
    if pac_ottimali and capitale_residuo > 0:
        importo = (capitale_residuo * 0.30) / len(pac_ottimali)
        for t in pac_ottimali:
            allocazioni.append({'ticker': t['ticker'], 'importo': round(importo, 2), 'motivazione': f"PAC Ottimale | {t['fase']} | S-Score {t['s_score']}", 'priorita': 2})
        capitale_residuo -= importo * len(pac_ottimali)
    if watchlist_breakout and capitale_residuo > 0:
        importo = (capitale_residuo * 0.20) / len(watchlist_breakout)
        for t in watchlist_breakout:
            allocazioni.append({'ticker': t['ticker'], 'importo': round(importo, 2), 'motivazione': f"Breakout Imminente | S-Score {t['s_score']} | RSI {t['rsi']:.0f}", 'priorita': 3})
        capitale_residuo -= importo * len(watchlist_breakout)
    return {'allocazioni': allocazioni, 'liquidita_residua': round(capitale_residuo, 2), 'by_fabio_count': len(by_fabio_tickers), 'pac_ottimali_count': len(pac_ottimali), 'watchlist_breakout_count': len(watchlist_breakout)}

# ==============================================================================
# BREAKOUT IMMINENTE
# ==============================================================================
def trova_breakout_imminenti(portafoglio, eurusd_rate):
    breakout_tickers = []
    for pos in portafoglio:
        ticker = pos['Ticker']
        try:
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period='1y')
            info = ticker_obj.info
            if df.empty or len(df) < 50: continue
            s_score = calcola_s_score(info, ticker)
            if s_score < 65: continue
            prezzo = df['Close'].iloc[-1]
            sma50 = df['Close'].rolling(window=50).mean().iloc[-1]
            distanza_sma50 = (sma50 - prezzo) / sma50 * 100
            if distanza_sma50 > 5.0 or prezzo > sma50: continue
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_oggi = float(100 - (100 / (1 + rs)).iloc[-1]) if not rs.empty else 50
            rsi_5gg_fa = float(100 - (100 / (1 + rs)).iloc[-6]) if len(rs) >= 6 else rsi_oggi
            if not (rsi_oggi > rsi_5gg_fa and 30 <= rsi_oggi <= 50): continue
            vol_medio = df['Volume'].rolling(window=20).mean().iloc[-1]
            vol_oggi = df['Volume'].iloc[-1]
            if vol_oggi <= vol_medio * 1.2: continue
            breakout_tickers.append({'ticker': ticker, 's_score': s_score, 'prezzo': round(prezzo / eurusd_rate if info.get('currency', 'USD') == 'USD' else prezzo, 2), 'sma50': round(sma50 / eurusd_rate if info.get('currency', 'USD') == 'USD' else sma50, 2), 'distanza_sma50': round(distanza_sma50, 1), 'rsi': round(rsi_oggi, 1), 'rsi_5gg_fa': round(rsi_5gg_fa, 1), 'volume_ratio': round(vol_oggi / vol_medio, 2)})
        except: continue
    return breakout_tickers

# ==============================================================================
# SEGNALI STORICI
# ==============================================================================
def registra_segnale(ticker, tipo_segnale, prezzo_usd, data_segnale=None):
    try:
        segnali = carica_json(SEGNALI_STORICI_FILE)
        data_segnale = data_segnale or datetime.now().strftime("%Y-%m-%d")
        ticker_norm = ticker.strip().upper()
        if any(s.get('Ticker', '').strip().upper() == ticker_norm and s.get('Data') == data_segnale for s in segnali): return
        segnali.append({'Ticker': ticker_norm, 'Tipo': tipo_segnale, 'Data': data_segnale, 'Prezzo': round(prezzo_usd, 2)})
        salva_json(SEGNALI_STORICI_FILE, segnali)
    except: pass

def get_ultimo_segnale(ticker):
    try:
        segnali = carica_json(SEGNALI_STORICI_FILE)
        ticker_norm = ticker.strip().upper()
        segnali_ticker = [s for s in segnali if s.get('Ticker', '').strip().upper() == ticker_norm]
        return sorted(segnali_ticker, key=lambda x: x.get('Data', ''), reverse=True)[0] if segnali_ticker else None
    except: return None

def calcola_performance_segnale(segnale, prezzo_attuale):
    if not segnale or not segnale.get('Prezzo'): return None, None, None
    try:
        data_segnale = datetime.strptime(segnale.get('Data', ''), "%Y-%m-%d")
        return (((prezzo_attuale - segnale.get('Prezzo', 0)) / segnale.get('Prezzo', 1)) * 100), (datetime.now() - data_segnale).days, segnale.get('Prezzo', 0)
    except: return None, None, None

def formatta_data_europea(data_iso):
    try: return datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except: return data_iso

def format_ultimo_segnale_display(ticker, prezzo_attuale_usd):
    try:
        if not prezzo_attuale_usd: return "N/D"
        ultimo_segnale = get_ultimo_segnale(ticker)
        if not ultimo_segnale or not ultimo_segnale.get('Prezzo'): return "N/D"
        prezzo_segnale = ultimo_segnale.get('Prezzo', 0)
        var_pct = ((prezzo_attuale_usd - prezzo_segnale) / prezzo_segnale) * 100
        data_fmt = formatta_data_europea(ultimo_segnale.get('Data', ''))
        tipo = ultimo_segnale.get('Tipo', 'N/D')
        segno = "+" if var_pct > 0 else ""
        if tipo == 'BY': return f"🟢 BY: {data_fmt} ({segno}{var_pct:.1f}%)" if var_pct >= 0 else f"🔴 BY: {data_fmt} ({segno}{var_pct:.1f}%)"
        elif tipo == 'BY_FABIO': return f"🟢 BY FABIO: {data_fmt} ({segno}{var_pct:.1f}%)" if var_pct >= 0 else f"🔴 BY FABIO: {data_fmt} ({segno}{var_pct:.1f}%)"
        else: return f"🟢 SELL: {data_fmt} ({segno}{var_pct:.1f}%)" if var_pct <= 0 else f"🟠 SELL: {data_fmt} ({segno}{var_pct:.1f}%)"
    except: return "N/D"

# ==============================================================================
# REGISTRO VENDITE
# ==============================================================================
ALIQUOTA_TASSE = 0.26
ANNI_COMPENSAZIONE = 4

def registra_vendita(ticker, qta_venduta, prezzo_medio, prezzo_vendita, data_vendita=None):
    try:
        data_vendita = data_vendita or datetime.now().strftime("%Y-%m-%d")
        pnl_lordo = (prezzo_vendita - prezzo_medio) * qta_venduta
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
                    if residuo <= 0: break
            tasse = residuo * 0.26
            pnl_netto = pnl_lordo - tasse
        else:
            tipo_operazione = "minusvalenza"
            pnl_netto = pnl_lordo
            scadenza = (datetime.strptime(data_vendita, "%Y-%m-%d") + timedelta(days=365*4)).strftime("%Y-%m-%d")
            minusvalenze.append({'Data': data_vendita, 'Scadenza': scadenza, 'Importo': abs(pnl_lordo), 'Ticker': ticker.strip().upper()})
        minusvalenze = [m for m in minusvalenze if m.get('Importo', 0) > 0]
        salva_json(MINUSVALENZE_FILE, minusvalenze)
        registro = carica_json(REGISTRO_VENDITE_FILE)
        id_op = max([v.get('id', 0) for v in registro], default=0) + 1
        registro.append({'id': id_op, 'Data': data_vendita, 'Ticker': ticker.strip().upper(), 'Qta_Venduta': round(qta_venduta, 6), 'Prezzo_Medio': round(prezzo_medio, 4), 'Prezzo_Vendita': round(prezzo_vendita, 4), 'PnL_Lordo': round(pnl_lordo, 2), 'PnL_Pct': round(pnl_pct, 2), 'Minusvalenze_Usate': round(minusvalenze_usate, 2), 'Tasse': round(tasse, 2), 'PnL_Netto': round(pnl_netto, 2), 'Tipo': tipo_operazione})
        salva_json(REGISTRO_VENDITE_FILE, registro)
        return {'id': id_op, 'pnl_lordo': pnl_lordo, 'pnl_pct': pnl_pct, 'tasse': tasse, 'pnl_netto': pnl_netto, 'minusvalenze_usate': minusvalenze_usate, 'tipo': tipo_operazione}
    except Exception as e:
        print(f"Errore: {e}")
        return None

def calcola_riepilogo_fiscale(anno=None):
    registro = carica_json(REGISTRO_VENDITE_FILE)
    if anno: registro = [v for v in registro if v.get('Data', '').startswith(str(anno))]
    gain_totale = sum(v.get('PnL_Lordo', 0) for v in registro if v.get('PnL_Lordo', 0) > 0)
    loss_totale = sum(v.get('PnL_Lordo', 0) for v in registro if v.get('PnL_Lordo', 0) < 0)
    tasse_totali = sum(v.get('Tasse', 0) for v in registro)
    netto_reale = gain_totale + loss_totale - tasse_totali
    minusvalenze = carica_json(MINUSVALENZE_FILE)
    oggi = datetime.now().strftime("%Y-%m-%d")
    pool_disponibile = sum(m.get('Importo', 0) for m in minusvalenze if m.get('Scadenza', '') >= oggi)
    return {'gain_totale': round(gain_totale, 2), 'loss_totale': round(loss_totale, 2), 'tasse_totali': round(tasse_totali, 2), 'netto_reale': round(netto_reale, 2), 'pool_minusvalenze': round(pool_disponibile, 2), 'num_operazioni': len(registro)}

def calcola_liquidita_totale():
    registro = carica_json(REGISTRO_VENDITE_FILE)
    return round(sum((v.get('Prezzo_Vendita', 0) * v.get('Qta_Venduta', 0)) - v.get('Tasse', 0) for v in registro), 2)

def reset_registro_vendite():
    try:
        salva_json(REGISTRO_VENDITE_FILE, [])
        salva_json(MINUSVALENZE_FILE, [])
        return True
    except: return False

# ==============================================================================
# FUNZIONI CORE
# ==============================================================================
def controlla_earnings(ticker_obj):
    try:
        earnings_dates = ticker_obj.earnings_dates
        if earnings_dates is None or earnings_dates.empty: return None, "⚪ N/D", False
        oggi = datetime.now()
        for data in earnings_dates.index:
            data_naive = data.tz_localize(None) if hasattr(data, 'tz_localize') else data
            if data_naive > oggi:
                giorni = (data_naive - oggi).days
                if giorni <= 7: return giorni, f"🔴 UTILI tra {giorni}gg", True
                elif giorni <= 14: return giorni, f"🟡 Utili tra {giorni}gg", False
                else: return giorni, f"⚪ Utili tra {giorni}gg", False
        return None, "⚪ N/D", False
    except: return None, "⚪ N/D", False

def get_prezzi_corretti(ticker_obj, eurusd_rate):
    info = ticker_obj.info
    currency = info.get('currency', 'USD')
    history = ticker_obj.history(period='1d')
    if history.empty: return None, None, currency
    prezzo_raw = history['Close'].iloc[-1]
    if currency == 'USD': return round(prezzo_raw / eurusd_rate, 2), round(prezzo_raw, 2), currency
    else: return round(prezzo_raw, 2), round(prezzo_raw * eurusd_rate, 2), currency

def calcola_variazione_giornaliera(ticker_obj):
    try:
        hist = ticker_obj.history(period="2d")
        if len(hist) < 2: return None, None
        return round(((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100, 2), round(hist['Close'].iloc[-1] - hist['Close'].iloc[-2], 2)
    except: return None, None

def aggiorna_quotazioni_portafoglio(portafoglio, eurusd_rate):
    risultati = []
    for pos in portafoglio:
        ticker = pos['Ticker']
        try:
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info
            hist = ticker_obj.history(period="1y")
            if hist.empty:
                risultati.append({**pos, "Prezzo_Attuale_EUR": None, "Prezzo_Attuale_USD": None, "PnL_EUR": None, "PnL_%": None, "Trend": "N/D", "Earnings": "N/D", "Variazione_Pct": None, "Variazione_Abs": None, "Stato_PAC": "N/D", "Ultimo_Segnale": "N/D"})
                continue
            currency = info.get('currency', 'USD')
            prezzo_raw = hist['Close'].iloc[-1]
            prezzo_eur = prezzo_raw / eurusd_rate if currency == 'USD' else prezzo_raw
            prezzo_usd = prezzo_raw if currency == 'USD' else prezzo_raw * eurusd_rate
            var_pct, var_abs = calcola_variazione_giornaliera(ticker_obj)
            prezzo_medio = pos['Prezzo_Medio']
            quantita = pos['Quantita']
            valore_attuale = prezzo_eur * quantita
            valore_carico = prezzo_medio * quantita
            pnl_eur = valore_attuale - valore_carico
            pnl_pct = ((prezzo_eur / prezzo_medio) - 1) * 100 if prezzo_medio > 0 else 0
            trend = "🟢 Forte +" if pnl_pct > 5 else (" +" if pnl_pct > 0 else (" -" if pnl_pct > -5 else "🔴 Forte -"))
            earnings_giorni, earnings_msg, _ = controlla_earnings(ticker_obj)
            s_score = calcola_s_score(info)
            fase = rileva_fase_weinstein(hist)
            rev_growth = info.get('revenueGrowth', 0.0) or 0.0
            stato_pac = "🔴 PAC SOSPESO" if ("FASE 4" in fase or s_score < 50 or rev_growth < 0) else "🟢 PAC ATTIVO"
            ultimo_segnale_display = format_ultimo_segnale_display(ticker, prezzo_usd)
            risultati.append({**pos, "Prezzo_Attuale_EUR": round(prezzo_eur, 2), "Prezzo_Attuale_USD": round(prezzo_usd, 2), "Valore_Attuale": round(valore_attuale, 2), "Valore_Carico": round(valore_carico, 2), "PnL_EUR": round(pnl_eur, 2), "PnL_%": round(pnl_pct, 2), "Trend": trend, "Earnings": earnings_msg, "Variazione_Pct": var_pct, "Variazione_Abs": var_abs, "Stato_PAC": stato_pac, "Ultimo_Segnale": ultimo_segnale_display})
        except Exception:
            risultati.append({**pos, "Prezzo_Attuale_EUR": None, "Prezzo_Attuale_USD": None, "PnL_EUR": None, "PnL_%": None, "Trend": "Errore", "Earnings": "N/D", "Variazione_Pct": None, "Variazione_Abs": None, "Stato_PAC": "Errore", "Ultimo_Segnale": "N/D"})
    return risultati

# ==============================================================================
# INIZIALIZZAZIONE SESSION STATE
# ==============================================================================
for key in ['dashboard_stats', 'pyramiding_alerts', 'take_profit_alerts', 'zona_interesse_alerts', 'extended_hours_alerts', 'df_palantir', 'df_fortezza', 'df_cavalli', 'df_monitor', 'scansione_completata', 'analisi_risultati', 'grafico_ticker', 'piano_ribilanciamento', 'portafoglio', 'last_update', 'analisi_ticker_precompilato', 'piano_allocazione', 'risultato_podc', 'liquidita_totale_alloc']:
    if key not in st.session_state:
        st.session_state[key] = None if key not in ['pyramiding_alerts', 'take_profit_alerts', 'zona_interesse_alerts', 'extended_hours_alerts'] else []

# ==============================================================================
# HEADER
# ==============================================================================
semaforo_header = calcola_semaforo_mercato()
sem_color = {"verde": "#10b981", "rosso": "#ef4444", "giallo": "#f59e0b"}.get(semaforo_header['stato'], "#f59e0b")
sem_icon = {"verde": "🟢", "rosso": "🔴", "giallo": "🟡"}.get(semaforo_header['stato'], "🟡")
sem_msg = {"verde": "MERCATO RIALZISTA", "rosso": "MERCATO RIBASSISTA", "giallo": "MERCATO LATERALE"}.get(semaforo_header['stato'], "MERCATO LATERALE")
sem_display = f"{sem_icon} {sem_msg} | SPY: ${semaforo_header['spy_prezzo']} | VIX: {semaforo_header['vix']}" if semaforo_header['spy_prezzo'] else "🟡 DATI MERCATO N/D"

st.markdown(f'''
<div class="header-box">
    <h1>🛡️ MATRIX Mobile V6.1.3</h1>
    <p style="margin: 0.5rem 0 0 0; opacity: 0.9;">Scanner Operativo Blindato</p>
    <p style="margin: 0.8rem 0 0 0; font-size: 1rem; font-weight: bold; color: {sem_color};">{sem_display}</p>
</div>
''', unsafe_allow_html=True)

# ==============================================================================
# SIDEBAR
# ==============================================================================
if os.path.exists(IMPOSTAZIONI_FILE):
    with open(IMPOSTAZIONI_FILE, 'r', encoding='utf-8') as f:
        impostazioni = json.load(f)
else:
    impostazioni = {"lista_ticker_default": "ADBE, RKLB, SOUN, IONQ, ASTS, BBAI, PLTR, ZETA, NKE, CRDO, AMD, CRWD, NU, NVDA, TSLA, MCD, DIS, SBUX, PEP, INTC", "catalizzatori": "", "esclusioni": ""}

st.sidebar.header("⚙️ Parametri")
tickers_input = st.sidebar.text_area("Ticker (virgola):", value=impostazioni.get("lista_ticker_default", ""))
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
period = st.sidebar.selectbox("Periodo:", ["3mo", "6mo", "1y", "2y"], index=2)
sma_short = st.sidebar.slider("SMA Breve:", 10, 100, 50)
sma_long = st.sidebar.slider("SMA Lunga:", 50, 200, 200)
eurusd_rate = st.sidebar.number_input("EUR/USD:", min_value=0.8, max_value=1.5, value=1.12, step=0.001)
st.sidebar.markdown("---")
st.sidebar.subheader("📅 Catalizzatori Eventi")
catalizzatori_input = st.sidebar.text_area("Formato: TICKER: Descrizione - GG/MM/AA", value=impostazioni.get("catalizzatori", ""), height=80)
st.sidebar.markdown("---")
st.sidebar.subheader("🚫 Esclusioni Ribilanciamento")
esclusioni_input = st.sidebar.text_area("Titoli da escludere (virgola):", value=impostazioni.get("esclusioni", ""), height=60)
st.sidebar.markdown("---")
st.sidebar.subheader("🔒 Filtri")
ignore_fase_4 = st.sidebar.checkbox("Blocca Fase 4", True)
filtro_delisting = st.sidebar.checkbox("Blocca titoli <$1", True)

if st.sidebar.button("🔴 AVVIA SCANSIONE", type="primary", use_container_width=True):
    impostazioni["lista_ticker_default"] = tickers_input
    impostazioni["catalizzatori"] = catalizzatori_input
    impostazioni["esclusioni"] = esclusioni_input
    with open(IMPOSTAZIONI_FILE, 'w', encoding='utf-8') as f:
        json.dump(impostazioni, f)
    lista_fortezza, lista_cavalli, lista_monitor, lista_palantir = [], [], [], []
    progress_bar = st.progress(0)
    stats = {'by_count': 0, 'hold_count': 0, 'sell_count': 0, 'by_tickers': [], 'hold_tickers': [], 'sell_tickers': [], 'earnings_warnings': []}
    pyramiding_alerts, take_profit_alerts, zona_interesse_alerts, extended_hours_alerts = [], [], [], []
    portafoglio_attuale = st.session_state.get('portafoglio') or carica_json(PORTAFOGLIO_FILE) or PORTAFOGLIO_INIZIALE
    ticker_in_portafoglio = {p['Ticker']: p for p in portafoglio_attuale}
    tickers = list(set(tickers + list(ticker_in_portafoglio.keys())))
    tickers.sort()
    st.info(f"🔄 Scansione avviata per {len(tickers)} titoli.")
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
            s_score = calcola_s_score(info, ticker)
            fase = rileva_fase_weinstein(df)
            figura_z, _ = rileva_figura_z(df)
            trigger_by, motivo_by, earnings_bloccato = verifica_trigger_by_fortezza(df, sma_short, ticker_obj)
            trigger_by_fabio, motivo_by_fabio = verifica_by_fabio(df, sma_short, ticker_obj)
            earnings_giorni, earnings_msg, earnings_bloccato2 = controlla_earnings(ticker_obj)
            if earnings_bloccato2: stats['earnings_warnings'].append(f"{ticker} ({earnings_msg})")
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_oggi = float(100 - (100 / (1 + rs)).iloc[-1]) if not (gain/loss).empty else 50
            revenue_growth = info.get('revenueGrowth', 0.0) or 0.0
            peg_ratio = info.get('pegRatio', 0.0) or 0.0
            sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
            prezzo_attuale = df['Close'].iloc[-1]
            distanza_sma200_pct = abs(prezzo_attuale - sma200) / sma200 * 100 if sma200 > 0 else 999
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
            if ticker in ticker_in_portafoglio and rsi_oggi >= 75:
                pos = ticker_in_portafoglio[ticker]
                gain_pct = ((prezzo_eur / pos['Prezzo_Medio']) - 1) * 100 if pos['Prezzo_Medio'] > 0 else 0
                take_profit_alerts.append({'ticker': ticker, 'rsi': round(rsi_oggi, 1), 'prezzo_attuale_eur': prezzo_eur, 'gain_pct': round(gain_pct, 1), 'tipo': pos.get('Tipo', 'Spot')})
            if ticker in ticker_in_portafoglio or s_score >= 40:
                if s_score >= 40 and distanza_sma200_pct <= 5.0 and (prezzo_attuale >= sma200 or distanza_sma200_pct <= 1.0):
                    zona_interesse_alerts.append({'ticker': ticker, 'prezzo_attuale_eur': prezzo_eur, 'sma200_eur': round(sma200 / eurusd_rate if currency == 'USD' else sma200, 2), 'distanza_pct': round(distanza_sma200_pct, 1), 's_score': s_score})
            if filtro_delisting:
                prezzo_delisting = info.get('regularMarketPrice', 0) or (df['Close'].iloc[-1] if not df.empty else 0)
                if prezzo_delisting < 1.0:
                    stats['sell_count'] += 1; stats['sell_tickers'].append(ticker); continue
            if ignore_fase_4 and "FASE 4" in fase: continue
            is_cp_valido = (40 <= s_score <= 60 and ("FASE 1" in fase or "FASE 2" in fase) and vol_ratio >= 1.60)
            is_fortezza_valida = (s_score >= 60 and "FASE 2" in fase)
            is_watchlist = (s_score >= 40 and ("FASE 1" in fase or "FASE 2" in fase or "CORREZIONE" in fase) and not is_cp_valido and not is_fortezza_valida)
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
                if distanza <= 0.02 and vol_oggi > vol_medio_oggi and prezzo_oggi > open_oggi: trigger_by_tecnico_oggi = True
                prezzo_ieri = df['Close'].iloc[idx_oggi-1]
                sma200_oggi = df['SMA_Long'].iloc[idx_oggi]
                sma200_ieri = df['SMA_Long'].iloc[idx_oggi-1]
                if prezzo_oggi < sma200_oggi and prezzo_ieri >= sma200_ieri and vol_oggi > vol_medio_oggi: trigger_sell_tecnico_oggi = True
            if trigger_by_tecnico_oggi: registra_segnale(ticker, 'BY', prezzo_usd, oggi_str)
            elif trigger_sell_tecnico_oggi: registra_segnale(ticker, 'SELL', prezzo_usd, oggi_str)
            if ticker in ticker_in_portafoglio and (trigger_by or trigger_by_fabio):
                pos = ticker_in_portafoglio[ticker]
                azioni = math.floor(100.0 / prezzo_eur)
                if azioni > 0:
                    pyramiding_alerts.append({'ticker': ticker, 'tipo': pos.get('Tipo', 'Spot'), 'prezzo_attuale': prezzo_eur, 'pyramiding': {'azioni': azioni, 'capitale': round(azioni * prezzo_eur, 2), 'stop_loss': round(prezzo_eur * 0.88, 2), 'target': round(prezzo_eur * 1.50, 2)}})
            if is_cp_valido:
                registra_segnale(ticker, 'BY', prezzo_usd, oggi_str)
                lista_cavalli.append({'Ticker': ticker, 'Prezzo EUR': prezzo_eur, 'S-Score': s_score, 'Fase': fase, 'Stato BY': "🟢 BY", 'Earnings': earnings_msg})
                stats['by_count'] += 1; stats['by_tickers'].append(ticker)
            elif is_fortezza_valida:
                if trigger_by_fabio:
                    registra_segnale(ticker, 'BY_FABIO', prezzo_usd, oggi_str)
                    stato_by_display, motivo_display = "🟢 BY FABIO", motivo_by_fabio
                elif trigger_by:
                    registra_segnale(ticker, 'BY', prezzo_usd, oggi_str)
                    stato_by_display, motivo_display = "🟢 BY", motivo_by
                else:
                    stato_by_display, motivo_display = "🟡 HOLD", motivo_by
                lista_fortezza.append({'Ticker': ticker, 'Prezzo EUR': prezzo_eur, 'S-Score': s_score, 'Fase': fase, 'Stato BY': stato_by_display, 'Motivo BY': motivo_display, 'Earnings': earnings_msg})
                if trigger_by or trigger_by_fabio:
                    stats['by_count'] += 1; stats['by_tickers'].append(ticker)
                else:
                    stats['hold_count'] += 1; stats['hold_tickers'].append(ticker)
            elif is_watchlist:
                motivi_hold = []
                if vol_ratio < 1.60: motivi_hold.append("Volumi bassi")
                lista_monitor.append({'Ticker': ticker, 'Prezzo EUR': prezzo_eur, 'S-Score': s_score, 'Fase': fase, 'Motivo Hold': "; ".join(motivi_hold), 'Earnings': earnings_msg})
                stats['hold_count'] += 1; stats['hold_tickers'].append(ticker)
        except Exception: pass
    progress_bar.empty()
    st.session_state.dashboard_stats = stats
    st.session_state.pyramiding_alerts = pyramiding_alerts
    st.session_state.take_profit_alerts = take_profit_alerts
    st.session_state.zona_interesse_alerts = zona_interesse_alerts
    st.session_state.extended_hours_alerts = extended_hours_alerts
    st.session_state.df_palantir = pd.DataFrame(lista_palantir) if lista_palantir else None
    st.session_state.df_fortezza = pd.DataFrame(lista_fortezza) if lista_fortezza else None
    st.session_state.df_cavalli = pd.DataFrame(lista_cavalli) if lista_cavalli else None
    st.session_state.df_monitor = pd.DataFrame(lista_monitor) if lista_monitor else None
    st.session_state.scansione_completata = True
    st.rerun()

# ==============================================================================
# TAB PRINCIPALI
# ==============================================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "💼 Portafoglio", "🔍 Analisi", "📋 Registro", "🤖 Portfolio AI"])

with tab1:
    st.subheader("📊 Segnali Operativi Oggi")
    if st.session_state.get('dashboard_stats'):
        stats = st.session_state.dashboard_stats
        if stats['by_count'] > 0:
            st.markdown(f"""<div class="signal-box signal-green"><h3 style="margin: 0;">🟢 {stats['by_count']} Segnali BY</h3><p style="margin: 0.5rem 0 0 0;">{', '.join(stats['by_tickers'])}</p></div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="signal-box signal-yellow"><h3 style="margin: 0;">🟡 Nessun segnale BY oggi</h3><p style="margin: 0.5rem 0 0 0;">Continua a monitorare</p></div>""", unsafe_allow_html=True)
        if stats['hold_count'] > 0:
            st.markdown(f"""<div class="signal-box signal-yellow"><h4 style="margin: 0;">🟡 {stats['hold_count']} in Accumulo (HOLD)</h4><p style="margin: 0.5rem 0 0 0;">{', '.join(stats['hold_tickers'])}</p></div>""", unsafe_allow_html=True)
        if stats['earnings_warnings']:
            st.markdown(f"""<div class="signal-box signal-red"><h4 style="margin: 0;">⚠️ Attenzione Utili</h4><p style="margin: 0.5rem 0 0 0;">{', '.join(stats['earnings_warnings'])}</p></div>""", unsafe_allow_html=True)
        if st.session_state.get('extended_hours_alerts'):
            st.markdown("---"); st.subheader("⚡ ALERT MOVIMENTI ANOMALI")
            for alert in st.session_state.extended_hours_alerts:
                box_class = "signal-green" if alert['variazione'] > 0 else "signal-red"
                st.markdown(f"""<div class="signal-box {box_class}"><h4 style="margin:0">{alert['colore']} {alert['ticker']} - {alert['sessione']}</h4><p style="margin:0.5rem 0">Var: <strong>{alert['variazione']:+.2f}%</strong> | €{alert['prezzo_eur']:.2f}</p></div>""", unsafe_allow_html=True)
        if st.session_state.get('zona_interesse_alerts'):
            st.markdown("---"); st.subheader("🟡 ZONA DI INTERESSE (S-Score >= 40)")
            for alert in st.session_state.zona_interesse_alerts:
                st.markdown(f"""<div class="signal-box signal-yellow"><h4 style="margin: 0;">🟡 {alert['ticker']} (S-Score: {alert['s_score']})</h4><p style="margin: 0.5rem 0;">💶 {alert['prezzo_attuale_eur']}€ | 🛡️ SMA200: {alert['sma200_eur']}€ ({alert['distanza_pct']}%)</p></div>""", unsafe_allow_html=True)
        st.markdown("---")
        st.subheader("⚠️ Watchlist Breakout Imminente")
        port_attuale = st.session_state.get('portafoglio') or carica_json(PORTAFOGLIO_FILE) or []
        breakout_tickers = trova_breakout_imminenti(port_attuale, eurusd_rate)
        if breakout_tickers:
            st.info(f"🎯 Trovati {len(breakout_tickers)} titoli con breakout imminente")
            for bt in breakout_tickers:
                st.markdown(f"""
<div class="signal-box signal-yellow">
<strong>🟡 {bt['ticker']}</strong> <span style="color: #fcd34d;">Breakout Imminente</span><br>
<small>Prezzo: €{bt['prezzo']:.2f} | SMA50: €{bt['sma50']:.2f} | Distanza: -{bt['distanza_sma50']}% | RSI: {bt['rsi']:.0f} (↑ da {bt['rsi_5gg_fa']:.0f}) | Vol: {bt['volume_ratio']:.2f}x</small>
</div>
""", unsafe_allow_html=True)
        else:
            st.info("Nessun titolo con breakout imminente al momento.")
        if st.session_state.get('df_palantir') is not None and not st.session_state.df_palantir.empty:
            st.markdown("---"); st.subheader("🤖 Setup Palantir Rilevati")
            st.dataframe(st.session_state.df_palantir, use_container_width=True)
    else:
        st.info("👆 Clicca **🔴 AVVIA SCANSIONE** nella sidebar.")

with tab2:
    st.subheader("💼 Il Mio Portafoglio")
    if 'portafoglio' not in st.session_state or st.session_state.portafoglio is None:
        st.session_state.portafoglio = carica_json(PORTAFOGLIO_FILE) or PORTAFOGLIO_INIZIALE
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
            
            # === DASHBOARD LIQUIDITÀ & PATRIMONIO ===
            st.markdown("### 🏦 Dashboard Liquidità & Patrimonio")
            liquidita_totale = calcola_liquidita_totale()
            riepilogo_fiscale = calcola_riepilogo_fiscale(None)
            patrimonio_totale = liquidita_totale + totale_valore
            col_pat1, col_pat2, col_pat3, col_pat4 = st.columns(4)
            with col_pat1: st.metric("💰 Liquidità Netta", f"€ {liquidita_totale:,.2f}", help="Incassi netti da vendite")
            with col_pat2: st.metric("📈 Valore Portafoglio", f"€ {totale_valore:,.2f}", help="Valore attuale posizioni")
            with col_pat3: st.metric("🏦 Patrimonio Totale", f"€ {patrimonio_totale:,.2f}", help="Liquidità + Portafoglio")
            with col_pat4:
                pnl_percentuale = ((patrimonio_totale / totale_carico) - 1) * 100 if totale_carico > 0 else 0
                st.metric("📊 Rendimento Totale", f"{pnl_percentuale:+.2f}%", help=f"Su capitale: € {totale_carico:,.2f}")
            st.markdown("---")
            
            # === PODC ===
            st.markdown("### 🛡️ Protocollo di Ottimizzazione Dinamica del Capitale (PODC)")
            if st.button("🛡️ Avvia Protocollo Ottimizzazione (PODC)", type="primary", use_container_width=True):
                with st.spinner("🔄 Analisi efficienza capitale in corso..."):
                    st.session_state.risultato_podc = avvia_podc(portafoglio, eurusd_rate, catalizzatori_input)
            if st.session_state.get('risultato_podc'):
                res = st.session_state.risultato_podc
                st.markdown("#### 🛡️ PROTOCOLLO DI OTTIMIZZAZIONE (PODC)")
                if not res['suggestions'] and not res['gain_analyzed']:
                    st.info("✅ Nessuna ottimizzazione necessaria al momento.")
                else:
                    for sug in res['suggestions']:
                        st.markdown(f"""
                        <div style="background-color: #1e293b; padding: 1rem; border-radius: 8px; border-left: 4px solid #10b981; margin-bottom: 1rem;">
                            <p style="margin: 0.2rem 0;"><strong>1. LIBERA:</strong> Vendi {sug['sell_pct']}% di {sug['sell_ticker']} → Libera <strong>€{sug['capital_freed']:.2f}</strong>.</p>
                            <p style="margin: 0.2rem 0;"><strong>2. MEDIA:</strong> Usa €{sug['capital_freed']:.2f} per {sug['buy_ticker']}.</p>
                            <p style="margin: 0.2rem 0;"><strong>3. RISULTATO:</strong> Prezzo medio scende a <strong>€{sug['new_avg']:.2f}</strong>. PnL passa a <strong style="color: #10b981;">{sug['new_pnl']:.1f}%</strong>.</p>
                        </div>
                        """, unsafe_allow_html=True)
                st.markdown("#### 📊 RIEPILOGO ANALISI PODC:")
                st.markdown(f"**✅ Titoli in Gain analizzati:** {len(res['gain_analyzed'])}")
                for g in res['gain_analyzed']: st.markdown(f"- **{g['ticker']}**: {g['reason']}")
                st.markdown(f"<br>**❌ Titoli in Loss NON candidati:** {len(res['loss_rejected'])}", unsafe_allow_html=True)
                for r_item in res['loss_rejected']: st.markdown(f"- **{r_item['ticker']}**: {r_item['reason']}")
                st.markdown(f"<br>**🎯 Candidati validi per media:** {len(res['loss_candidates'])}", unsafe_allow_html=True)
                for c in res['loss_candidates']:
                    hypothetical_new_avg = ((c['qty'] * c['prezzo_medio']) + res['total_capital_freed']) / (c['qty'] + (res['total_capital_freed'] / c['prezzo_attuale'])) if res['total_capital_freed'] > 0 else c['prezzo_medio']
                    st.markdown(f"- **{c['ticker']}**: S-Score {c['s_score']}, Fase {c['fase']}, RSI {c['rsi']:.1f}, Prezzo medio attuale €{c['prezzo_medio']:.2f}, Nuovo prezzo medio ipotetico €{hypothetical_new_avg:.2f}")
                liquidita_reale = calcola_liquidita_totale()
                capitale_proposto = res['total_capital_freed']
                totale_disponibile = liquidita_reale + capitale_proposto
                st.markdown("#### 💰 DISPONIBILITÀ CAPITALE")
                col_liq1, col_liq2, col_liq3 = st.columns(3)
                with col_liq1: st.metric("💵 Liquidità reale", f"€ {liquidita_reale:,.2f}")
                with col_liq2: st.metric("🎯 Capitale liberabile", f"€ {capitale_proposto:,.2f}")
                with col_liq3: st.metric("🏦 TOTALE DISPONIBILE", f"€ {totale_disponibile:,.2f}")

            # === MOTORE DI RIBILANCIAMENTO MENSILE ===
            st.markdown("---")
            st.markdown("### 📊 Motore di Ribilanciamento Mensile")
            if st.button("📊 Genera Piano di Rotazione", type="secondary", use_container_width=True):
                with st.spinner("🔄 Analisi in corso..."):
                    semaforo = calcola_semaforo_mercato()
                    catalizzatori = {}
                    if catalizzatori_input:
                        for item in catalizzatori_input.split(';'):
                            if ':' in item:
                                ticker, resto = item.split(':', 1)
                                match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', resto)
                                if match:
                                    anno = '20' + match.group(3) if len(match.group(3)) == 2 else match.group(3)
                                    try: catalizzatori[ticker.strip().upper()] = datetime(int(anno), int(match.group(2)), int(match.group(1)))
                                    except: pass
                    esclusioni_list = [t.strip().upper() for t in esclusioni_input.split(",") if t.strip()]
                    piano = {'vendite': [], 'monitor': [], 'acquisti': [], 'semaforo': semaforo['stato']}
                    for pos in portafoglio:
                        pnl = ((pos.get('Prezzo_Attuale_EUR', 0) / pos.get('Prezzo_Medio', 1)) - 1) * 100 if pos.get('Prezzo_Medio', 0) > 0 else 0
                        if pnl < -10: piano['vendite'].append({'ticker': pos['Ticker'], 'score': 30, 'messaggio': "Loss > 10%"})
                        elif pnl > 20: piano['monitor'].append({'ticker': pos['Ticker'], 'score': 80, 'messaggio': "Gain > 20%, monitora"})
                    st.session_state.piano_ribilanciamento = piano
            if st.session_state.get('piano_ribilanciamento'):
                piano = st.session_state.piano_ribilanciamento
                st.markdown(f"**Stato Mercato:** {piano['semaforo'].upper()}")
                if piano['vendite']:
                    st.markdown("#### 🔴 Da Vendere")
                    for item in piano['vendite']:
                        st.markdown(f"""<div class="signal-box signal-red"><strong>{item['ticker']}</strong><br><small>{item.get('messaggio', '')}</small></div>""", unsafe_allow_html=True)
                if piano['monitor']:
                    st.markdown("#### 🟡 Da Monitorare")
                    for item in piano['monitor']:
                        st.markdown(f"""<div class="signal-box signal-yellow"><strong>{item['ticker']}</strong><br><small>{item.get('messaggio', '')}</small></div>""", unsafe_allow_html=True)
                st.markdown("---")
                st.subheader("💡 AZIONE CONSIGLIATA DAL SISTEMA")
                if piano['vendite']:
                    st.info(f"1. **Ottimizza:** Valuta la vendita di {', '.join([v['ticker'] for v in piano['vendite'][:3]])} per liberare liquidità.")
                else:
                    st.info("Mantieni la rotta. Il portafoglio è ben bilanciato.")

            # === PIANO DI ALLOCAZIONE DINAMICA ===
            st.markdown("---")
            st.subheader("💰 Piano di Allocazione Dinamica")
            if st.button("💰 Genera Piano di Allocazione", type="secondary", use_container_width=True):
                with st.spinner("🔄 Calcolo allocazione ottimale..."):
                    liquidita_reale = calcola_liquidita_totale()
                    liquidita_totale_alloc = liquidita_reale + 500
                    piano_alloc = genera_piano_allocazione(portafoglio, liquidita_totale_alloc, eurusd_rate)
                    st.session_state.piano_allocazione = piano_alloc
                    st.session_state.liquidita_totale_alloc = liquidita_totale_alloc
            if st.session_state.get('piano_allocazione'):
                piano = st.session_state.piano_allocazione
                liquidita_totale_alloc = st.session_state.get('liquidita_totale_alloc', 0)
                st.markdown(f"**Liquidità Totale Disponibile:** € {liquidita_totale_alloc:,.2f}")
                st.markdown(f"**BY FABIO attivi:** {piano['by_fabio_count']} | **PAC ottimali:** {piano['pac_ottimali_count']} | **Breakout imminenti:** {piano['watchlist_breakout_count']}")
                if piano['allocazioni']:
                    df_alloc = pd.DataFrame(piano['allocazioni'])
                    df_alloc.columns = ['Ticker', 'Importo (€)', 'Motivazione', 'Priorità']
                    st.dataframe(df_alloc, use_container_width=True, height=200)
                st.metric("💵 Liquidità Residua", f"€ {piano['liquidita_residua']:,.2f}")
            
            st.markdown("---")
            # === LOOP PORTAFOGLIO CON PALLINI E BY FABIO ===
            for idx_pos, pos in enumerate(portafoglio):
                ticker = pos['Ticker']
                prezzo_eur = pos.get('Prezzo_Attuale_EUR')
                var_pct = pos.get('Variazione_Pct')
                var_abs = pos.get('Variazione_Abs', 0) or 0
                pnl_pct = pos.get('PnL_%', 0) or 0
                stato_pac = pos.get('Stato_PAC', 'N/A')
                ultimo_segnale = pos.get('Ultimo_Segnale', 'N/D')
                prezzo_medio = pos.get('Prezzo_Medio', 0)
                quantita = pos.get('Quantita', 0)
                pnl_eur = pos.get('PnL_EUR', 0) or 0
                var_acquisto = ((prezzo_eur / prezzo_medio) - 1) * 100 if (prezzo_medio > 0 and prezzo_eur) else 0
                if var_pct is not None:
                    var_day_color = "#10b981" if var_pct > 0 else "#ef4444"
                    var_day_symbol = "▲" if var_pct > 0 else "▼" if var_pct < 0 else "●"
                    var_day_display = f"{var_day_symbol} {abs(var_pct):.2f}% ({var_abs:+.2f}€)"
                else:
                    var_day_color = "#94a3b8"
                    var_day_display = "N/D"
                if var_acquisto > 0: acqu_color, acqu_symbol = "#10b981", "▲"
                elif var_acquisto < 0: acqu_color, acqu_symbol = "#ef4444", "▼"
                else: acqu_color, acqu_symbol = "#94a3b8", "●"
                if pnl_pct > 0: border_color = "#10b981"
                elif pnl_pct < 0: border_color = "#ef4444"
                else: border_color = "#64748b"
                prezzo_display = f"{prezzo_eur:.2f}" if prezzo_eur is not None else "N/D"
                
                # 3 Pallini Target
                ticker_obj = yf.Ticker(ticker)
                targets = calcola_target(ticker_obj, prezzo_medio, prezzo_eur)
                if targets:
                    target_raggiunti = sum(1 for p in [targets['prog1'], targets['prog2'], targets['prog3']] if p >= 100.0)
                    if target_raggiunti == 0:
                        dots_html = '<span class="target-dot target-dot-pending" title="Nessun target raggiunto"></span>' * 3
                    elif target_raggiunti == 1:
                        dots_html = '<span class="target-dot target-dot-achieved" title="Target 1 raggiunto"></span><span class="target-dot target-dot-pending" title="Target 2"></span><span class="target-dot target-dot-pending" title="Target 3"></span>'
                    elif target_raggiunti == 2:
                        dots_html = '<span class="target-dot target-dot-achieved" title="Target 1"></span><span class="target-dot target-dot-achieved" title="Target 2"></span><span class="target-dot target-dot-pending" title="Target 3"></span>'
                    else:
                        dots_html = '<span class="target-dot target-dot-achieved" title="Target 1"></span><span class="target-dot target-dot-achieved" title="Target 2"></span><span class="target-dot target-dot-achieved" title="Target 3"></span>'
                    dots_display = f'{dots_html} <span class="target-tooltip">{target_raggiunti}/3</span>'
                else:
                    dots_display = '<span class="target-tooltip">N/D</span>'
                
                # BY FABIO Badge
                trigger_by_fabio, motivo_by_fabio = verifica_by_fabio(ticker_obj.history(period='1y'), 50, ticker_obj) if not ticker_obj.history(period='1y').empty else (False, "")
                by_fabio_indicator = '<span class="by-fabio-badge" title="Ingresso matematicamente validato">🟢 BY FABIO</span>' if trigger_by_fabio else ''
                
                st.markdown(f"""
                <div class="portfolio-box" style="border-left-color: {border_color};">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div style="flex: 1;">
                            <div class="portfolio-ticker">{ticker} {by_fabio_indicator}</div>
                            <div class="portfolio-info">{stato_pac} | {ultimo_segnale}</div>
                            <div class="portfolio-info" style="color: {acqu_color}; font-weight: bold; margin-top: 0.5rem;">
                                {acqu_symbol} {var_acquisto:+.1f}% | {pnl_eur:+.2f}€ {dots_display}
                            </div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 1.2rem; color: #f8fafc; font-weight: bold;">€ {prezzo_display}</div>
                            <div style="color: {var_day_color}; font-size: 1.1rem; font-weight: bold;">{var_day_display} oggi</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button(f"🔍 {ticker}", key=f"btn_analisi_{ticker}", use_container_width=True):
                    st.session_state['analisi_ticker_precompilato'] = ticker
                    st.rerun()
                
                with st.expander(f"📋 Operazioni - {ticker}"):
                    col_info1, col_info2, col_info3 = st.columns(3)
                    with col_info1: st.metric("Quantità", f"{quantita:.6f}")
                    with col_info2: st.metric("Prezzo Medio", f"€ {prezzo_medio:.2f}")
                    with col_info3: st.metric("Valore Totale", f"€ {prezzo_eur * quantita:.2f}" if prezzo_eur else "N/D")
                    st.markdown("---")
                    st.markdown("**➖ Vendi Quote**")
                    modalita_vendita = st.radio(f"Modalità vendita {ticker}", ["📊 Percentuale (%)", "🔢 Quantità specifica"], horizontal=True, key=f"modalita_vend_{ticker}_{idx_pos}")
                    qta_da_vendere = 0
                    if modalita_vendita == "📊 Percentuale (%)":
                        pct_vendita = st.slider(f"Percentuale da vendere", min_value=1.0, max_value=100.0, value=100.0, step=1.0, key=f"pct_vend_{ticker}_{idx_pos}")
                        qta_da_vendere = quantita * (pct_vendita / 100.0)
                        st.info(f"📊 Venderai {pct_vendita:.0f}% = {qta_da_vendere:.6f} quote")
                    else:
                        qta_da_vendere = st.number_input(f"Quantità da vendere (max {quantita:.6f})", min_value=0.0001, max_value=quantita, step=0.0001, value=min(quantita, 1.0), key=f"qta_vend_{ticker}_{idx_pos}")
                    prezzo_vendita = st.number_input(f"Prezzo di vendita €", min_value=0.01, step=0.01, value=float(prezzo_eur) if prezzo_eur else 0.01, key=f"prezzo_vend_{ticker}_{idx_pos}")
                    if qta_da_vendere > 0 and prezzo_vendita > 0 and prezzo_medio > 0:
                        pnl_lordo_prev = (prezzo_vendita - prezzo_medio) * qta_da_vendere
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
                                    if residuo <= 0: break
                            tasse_sim = residuo * 0.26
                        pnl_netto_prev = pnl_lordo_prev - tasse_sim
                        st.markdown(f"""
                        <div style="background-color: #1e293b; padding: 1rem; border-radius: 8px; margin: 1rem 0; border: 1px solid #334155;">
                            <div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">
                                <div>
                                    <div style="color: #94a3b8; font-size: 0.9rem;">P&L Lordo</div>
                                    <div style="color: {'#10b981' if pnl_lordo_prev > 0 else '#ef4444'}; font-size: 1.3rem; font-weight: bold;">€ {pnl_lordo_prev:+.2f} ({pnl_pct_prev:+.1f}%)</div>
                                </div>
                                <div>
                                    <div style="color: #94a3b8; font-size: 0.9rem;">Tasse stimate (26%)</div>
                                    <div style="color: #ef4444; font-size: 1.3rem; font-weight: bold;">€ -{tasse_sim:.2f}</div>
                                </div>
                                <div>
                                    <div style="color: #94a3b8; font-size: 0.9rem;">Netto reale</div>
                                    <div style="color: {'#10b981' if pnl_netto_prev > 0 else '#ef4444'}; font-size: 1.3rem; font-weight: bold;">€ {pnl_netto_prev:+.2f}</div>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        if st.button(f"🔴 Conferma Vendita {ticker}", key=f"vend_{ticker}_{idx_pos}", type="primary"):
                            if qta_da_vendere <= quantita:
                                risultato = registra_vendita(ticker, qta_da_vendere, prezzo_medio, prezzo_vendita)
                                if risultato:
                                    pos['Quantita'] = round(quantita - qta_da_vendere, 6)
                                    if pos['Quantita'] <= 0:
                                        portafoglio = [p for p in portafoglio if p['Ticker'] != ticker]
                                    st.session_state.portafoglio = portafoglio
                                    salva_json(PORTAFOGLIO_FILE, portafoglio)
                                    st.success(f"✅ Vendute {qta_da_vendere:.6f} quote di {ticker}. P&L Netto: €{risultato['pnl_netto']:+.2f}")
                                    st.rerun()
                            else:
                                st.error("Quantità da vendere superiore alle quote disponibili")
                    st.markdown("---")
                    st.markdown("**➕ Aggiungi Quote**")
                    col_a1, col_a2 = st.columns(2)
                    with col_a1:
                        nuova_qta = st.number_input("Qta", min_value=0.0001, step=0.0001, key=f"mqta_{ticker}_{idx_pos}")
                    with col_a2:
                        nuovo_prezzo_acq = st.number_input("Prezzo €", min_value=0.01, step=0.01, key=f"mprezzo_{ticker}_{idx_pos}")
                    if st.button(f"✅ Aggiungi", key=f"madd_{ticker}_{idx_pos}"):
                        if nuova_qta > 0 and nuovo_prezzo_acq > 0:
                            vecchio_medio = pos['Prezzo_Medio']
                            nuovo_medio = ((quantita * vecchio_medio) + (nuova_qta * nuovo_prezzo_acq)) / (quantita + nuova_qta)
                            pos['Quantita'] = round(quantita + nuova_qta, 6)
                            pos['Prezzo_Medio'] = round(nuovo_medio, 4)
                            salva_json(PORTAFOGLIO_FILE, portafoglio)
                            st.session_state.portafoglio = portafoglio
                            st.success(f"✅ Aggiunte. Nuovo medio: €{nuovo_medio:.4f}")
                            st.rerun()
                    st.markdown("---")
                    if st.button(f"🗑️ Rimuovi", key=f"mremove_{ticker}_{idx_pos}"):
                        portafoglio[:] = [p for p in portafoglio if p['Ticker'] != ticker]
                        st.session_state.portafoglio = portafoglio
                        salva_json(PORTAFOGLIO_FILE, portafoglio)
                        st.success(f"✅ {ticker} rimosso")
                        st.rerun()
    else:
        st.info("Portafoglio vuoto.")

with tab3:
    st.subheader("🔍 Analisi Singola")
    
    # TASTO ESCI IN ALTO
    if st.button("← Torna al Portafoglio", key="btn_torna_portafoglio", use_container_width=True):
        st.session_state.analisi_risultati = None
        st.session_state.grafico_ticker = None
        st.rerun()
    
    default_ticker = st.session_state.get('analisi_ticker_precompilato', "ADBE")
    ticker_input = st.text_input("Ticker:", value=default_ticker)
    
    if 'analisi_ticker_precompilato' in st.session_state and st.session_state.analisi_ticker_precompilato:
        ticker_s = st.session_state.analisi_ticker_precompilato
        del st.session_state.analisi_ticker_precompilato
        try:
            ticker_obj = yf.Ticker(ticker_s)
            df = ticker_obj.history(period="1y")
            info = ticker_obj.info
            if not df.empty and len(df) >= 50:
                prezzo_eur, prezzo_usd, currency = get_prezzi_corretti(ticker_obj, eurusd_rate)
                df['SMA_Short'] = df['Close'].rolling(window=50).mean()
                df['SMA_Long'] = df['Close'].rolling(window=200).mean()
                vol_ratio = df.iloc[-1]['Volume'] / df['Volume'].rolling(window=20).mean().iloc[-1] if df['Volume'].rolling(window=20).mean().iloc[-1] > 0 else 0
                s_score = calcola_s_score(info, ticker_s)
                fase = rileva_fase_weinstein(df)
                figura_z, _ = rileva_figura_z(df)
                trigger_by, motivo_by, _ = verifica_trigger_by_fortezza(df, 50, ticker_obj)
                trigger_by_fabio, motivo_by_fabio = verifica_by_fabio(df, 50, ticker_obj)
                earnings_giorni, earnings_msg, _ = controlla_earnings(ticker_obj)
                var_pct, var_abs = calcola_variazione_giornaliera(ticker_obj)
                sma50_usd = round(df['Close'].rolling(window=50).mean().iloc[-1], 2)
                sma200_usd = round(df['Close'].rolling(window=200).mean().iloc[-1], 2)
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi_val = float(100 - (100 / (1 + rs)).iloc[-1]) if not rs.empty else 50
                supporto = round(df.tail(60)['Low'].min(), 2)
                resistenza = round(df.tail(60)['High'].max(), 2)
                pm_price = info.get('preMarketPrice')
                pm_change = info.get('preMarketChangePercent')
                am_price = info.get('postMarketPrice')
                am_change = info.get('postMarketChangePercent')
                if am_price and am_change: market_extra = f"🌙 After-Hours: ${am_price:.2f} ({am_change:+.2f}%)"
                elif pm_price and pm_change: market_extra = f"🌅 Pre-Market: ${pm_price:.2f} ({pm_change:+.2f}%)"
                else: market_extra = "🌞 Regular Market"
                distanza_medie_pct = abs(sma50_usd - sma200_usd) / sma200_usd * 100 if sma200_usd != 0 else 0
                pre_golden_cross = distanza_medie_pct < 3.0 and sma50_usd < sma200_usd
                pre_death_cross = distanza_medie_pct < 3.0 and sma50_usd > sma200_usd
                if trigger_by_fabio: segnale = "🟢 BY FABIO - Ingresso Matematico"
                elif trigger_by: segnale = "🟢 BY - Acquista"
                elif "FASE 4" in fase or s_score < 40: segnale = "🔴 SELL - Evita"
                elif s_score >= 60 and "FASE 2" in fase: segnale = "🟡 HOLD - Monitora"
                else: segnale = "🟡 HOLD - In attesa"
                motivo_display = motivo_by_fabio if trigger_by_fabio else motivo_by
                st.session_state.analisi_risultati = {
                    'ticker': ticker_s, 'segnale': segnale, 'prezzo_eur': prezzo_eur, 'prezzo_usd': prezzo_usd,
                    's_score': s_score, 'fase': fase, 'vol_ratio': vol_ratio, 'figura_z': figura_z,
                    'earnings_msg': earnings_msg, 'motivo_by': motivo_display, 'var_pct': var_pct, 'var_abs': var_abs,
                    'sma50_usd': sma50_usd, 'sma200_usd': sma200_usd, 'rsi': round(rsi_val, 1),
                    'supporto': supporto, 'resistenza': resistenza, 'market_extra': market_extra,
                    'volume_oggi': int(df['Volume'].iloc[-1]),
                    'volume_medio': int(df['Volume'].rolling(window=20).mean().iloc[-1]),
                    'trigger_by_fabio': trigger_by_fabio,
                    'pre_golden_cross': pre_golden_cross,
                    'pre_death_cross': pre_death_cross
                }
        except Exception: pass
    
    if st.button("🔎 Analizza", type="primary", use_container_width=True):
        ticker_s = ticker_input.strip().upper()
        try:
            ticker_obj = yf.Ticker(ticker_s)
            df = ticker_obj.history(period="1y")
            info = ticker_obj.info
            if df.empty or len(df) < 50:
                st.error("Dati insufficienti")
            else:
                prezzo_eur, prezzo_usd, currency = get_prezzi_corretti(ticker_obj, eurusd_rate)
                df['SMA_Short'] = df['Close'].rolling(window=50).mean()
                df['SMA_Long'] = df['Close'].rolling(window=200).mean()
                vol_ratio = df.iloc[-1]['Volume'] / df['Volume'].rolling(window=20).mean().iloc[-1] if df['Volume'].rolling(window=20).mean().iloc[-1] > 0 else 0
                s_score = calcola_s_score(info, ticker_s)
                fase = rileva_fase_weinstein(df)
                figura_z, _ = rileva_figura_z(df)
                trigger_by, motivo_by, _ = verifica_trigger_by_fortezza(df, 50, ticker_obj)
                trigger_by_fabio, motivo_by_fabio = verifica_by_fabio(df, 50, ticker_obj)
                earnings_giorni, earnings_msg, _ = controlla_earnings(ticker_obj)
                var_pct, var_abs = calcola_variazione_giornaliera(ticker_obj)
                sma50_usd = round(df['Close'].rolling(window=50).mean().iloc[-1], 2)
                sma200_usd = round(df['Close'].rolling(window=200).mean().iloc[-1], 2)
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi_val = float(100 - (100 / (1 + rs)).iloc[-1]) if not rs.empty else 50
                supporto = round(df.tail(60)['Low'].min(), 2)
                resistenza = round(df.tail(60)['High'].max(), 2)
                pm_price = info.get('preMarketPrice')
                pm_change = info.get('preMarketChangePercent')
                am_price = info.get('postMarketPrice')
                am_change = info.get('postMarketChangePercent')
                if am_price and am_change: market_extra = f"🌙 After-Hours: ${am_price:.2f} ({am_change:+.2f}%)"
                elif pm_price and pm_change: market_extra = f"🌅 Pre-Market: ${pm_price:.2f} ({pm_change:+.2f}%)"
                else: market_extra = "🌞 Regular Market"
                distanza_medie_pct = abs(sma50_usd - sma200_usd) / sma200_usd * 100 if sma200_usd != 0 else 0
                pre_golden_cross = distanza_medie_pct < 3.0 and sma50_usd < sma200_usd
                pre_death_cross = distanza_medie_pct < 3.0 and sma50_usd > sma200_usd
                if trigger_by_fabio: segnale = "🟢 BY FABIO - Ingresso Matematico"
                elif trigger_by: segnale = "🟢 BY - Acquista"
                elif "FASE 4" in fase or s_score < 40: segnale = "🔴 SELL - Evita"
                elif s_score >= 60 and "FASE 2" in fase: segnale = "🟡 HOLD - Monitora"
                else: segnale = "🟡 HOLD - In attesa"
                motivo_display = motivo_by_fabio if trigger_by_fabio else motivo_by
                st.session_state.analisi_risultati = {
                    'ticker': ticker_s, 'segnale': segnale, 'prezzo_eur': prezzo_eur, 'prezzo_usd': prezzo_usd,
                    's_score': s_score, 'fase': fase, 'vol_ratio': vol_ratio, 'figura_z': figura_z,
                    'earnings_msg': earnings_msg, 'motivo_by': motivo_display, 'var_pct': var_pct, 'var_abs': var_abs,
                    'sma50_usd': sma50_usd, 'sma200_usd': sma200_usd, 'rsi': round(rsi_val, 1),
                    'supporto': supporto, 'resistenza': resistenza, 'market_extra': market_extra,
                    'volume_oggi': int(df['Volume'].iloc[-1]),
                    'volume_medio': int(df['Volume'].rolling(window=20).mean().iloc[-1]),
                    'trigger_by_fabio': trigger_by_fabio,
                    'pre_golden_cross': pre_golden_cross,
                    'pre_death_cross': pre_death_cross
                }
        except Exception as e:
            st.error(f"Errore: {e}")
    
    if st.session_state.get('analisi_risultati'):
        r = st.session_state.analisi_risultati
        st.markdown(f"### {r['ticker']} - {r['segnale']}")
        
        col1, col2 = st.columns(2)
        col1.metric("💶 Prezzo EUR", f"€ {r['prezzo_eur']:.2f}")
        col2.metric("💵 Prezzo USD", f"$ {r['prezzo_usd']:.2f}")
        col3, col4 = st.columns(2)
        col3.metric("⚡ S-Score", r['s_score'])
        col4.metric("📊 Fase", r['fase'])
        col5, col6 = st.columns(2)
        col5.metric("📈 RSI", r['rsi'])
        col6.metric("📊 Volume Ratio", f"{r['vol_ratio']:.2f}x")
        
        # FIX: Volume Oggi e Medio
        col7, col8 = st.columns(2)
        col7.metric("📊 Volume Oggi", f"{r.get('volume_oggi', 'N/D'):,}" if isinstance(r.get('volume_oggi'), (int, float)) else r.get('volume_oggi', 'N/D'))
        col8.metric("📊 Volume Medio", f"{r.get('volume_medio', 'N/D'):,}" if isinstance(r.get('volume_medio'), (int, float)) else r.get('volume_medio', 'N/D'))
        
        if r.get('var_pct') is not None:
            var_color = "#10b981" if r['var_pct'] > 0 else "#ef4444"
            st.markdown(f"**Variazione oggi:** <span style='color:{var_color};font-weight:bold'>{r['var_pct']:+.2f}% ({r['var_abs']:+.2f}€)</span>", unsafe_allow_html=True)
        
        st.markdown(f"**{r['market_extra']}**")
        st.markdown(f"**SMA 50:** ${r['sma50_usd']:.2f} | **SMA 200:** ${r['sma200_usd']:.2f}")
        st.markdown(f"**🛡️ Sup:** ${r['supporto']:.2f} | **🎯 Res:** ${r['resistenza']:.2f}")
        st.markdown(f"**Figura Z:** {'✅ Sì' if r['figura_z'] else '❌ No'} | **Prossimi Utili:** {r['earnings_msg']}")
        
        if r.get('pre_golden_cross'): st.success("🚀 **Pre-Golden Cross**: La SMA 50 sta per incrociare la SMA 200 dal basso!")
        elif r.get('pre_death_cross'): st.warning("⚠️ **Pre-Death Cross**: La SMA 50 sta per incrociare la SMA 200 dall'alto. Attenzione!")
        
        if "BY FABIO" in r['segnale']: st.success(f"**🟢 BY FABIO**: {r['motivo_by']}")
        elif "BY" in r['segnale']: st.success(f"**Motivo**: {r['motivo_by']}")
        elif "HOLD" in r['segnale']: st.warning(f"**Motivo**: {r['motivo_by']}")
        else: st.error("**Motivo**: Titolo in Fase 4 o S-Score troppo basso")
        
        # Target Grafici
        port_att = st.session_state.get('portafoglio') or carica_json(PORTAFOGLIO_FILE) or []
        prezzo_medio_analisi = r['prezzo_eur']
        for p in port_att:
            if p['Ticker'] == r['ticker']:
                prezzo_medio_analisi = p.get('Prezzo_Medio', r['prezzo_eur'])
                break
        targets_analisi = calcola_target(ticker_obj, prezzo_medio_analisi, r['prezzo_eur'])
        if targets_analisi:
            st.markdown(f"""
            <div style="background-color: #1e293b; padding: 0.8rem; border-radius: 8px; margin: 1rem 0; border: 1px solid #334155;">
                <h4 style="margin-top:0; color: #f59e0b; font-size: 1rem;">🎯 TARGET DI PREZZO (Resistenze):</h4>
                <p style="margin: 0.2rem 0; font-size: 0.9rem;">• <strong>T1:</strong> €{targets_analisi['t1']} (+{targets_analisi['upside1']}%) | Prog: {targets_analisi['prog1']}%</p>
                <p style="margin: 0.2rem 0; font-size: 0.9rem;">• <strong>T2:</strong> €{targets_analisi['t2']} (+{targets_analisi['upside2']}%) | Prog: {targets_analisi['prog2']}%</p>
                <p style="margin: 0.2rem 0; font-size: 0.9rem;">• <strong>T3:</strong> €{targets_analisi['t3']} (+{targets_analisi['upside3']}%) | Prog: {targets_analisi['prog3']}%</p>
                <hr style="border-color: #334155; margin: 0.5rem 0;">
                <h4 style="margin-top:0; color: #ef4444; font-size: 1rem;">🛡️ STOP LOSS: €{targets_analisi['sl']} ({targets_analisi['sl_down']}%)</h4>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        st.subheader("💰 Simulatore di Acquisto")
        col_sim1, col_sim2 = st.columns([2, 1])
        with col_sim1: sim_ticker = st.text_input("Titolo:", value=r['ticker'])
        with col_sim2: sim_importo = st.number_input("Importo (€):", min_value=100, value=200, step=100)
        if st.button("🔍 Analizza Finanziamento", use_container_width=True):
            st.success(f"🎯 **Consiglio:** Acquista {sim_ticker} con nuova liquidità di {sim_importo}€.")
        
        st.markdown("---")
        st.markdown('<div class="signal-history-box"><div class="signal-history-title">📊 STORICO SEGNALI</div></div>', unsafe_allow_html=True)
        ultimo_segnale = get_ultimo_segnale(r['ticker'])
        if ultimo_segnale:
            var_pct_segnale, giorni_trascorsi, prezzo_segnale = calcola_performance_segnale(ultimo_segnale, r['prezzo_usd'])
            if var_pct_segnale is not None:
                if ultimo_segnale['Tipo'] in ['BY', 'BY_FABIO']:
                    colore_var = "#10b981" if var_pct_segnale >= 0 else "#ef4444"
                    testo = "✅ Segnale vincente" if var_pct_segnale >= 0 else "❌ Segnale perdente"
                else:
                    colore_var = "#10b981" if var_pct_segnale <= 0 else "#f59e0b"
                    testo = "✅ Ha evitato perdita" if var_pct_segnale <= 0 else "⚠️ Opportunità mancata"
                data_fmt = formatta_data_europea(ultimo_segnale.get('Data', ''))
                segno = "+" if var_pct_segnale > 0 else ""
                tipo_display = '🟢 BY FABIO' if ultimo_segnale['Tipo'] == 'BY_FABIO' else ('🟢 BY' if ultimo_segnale['Tipo'] == 'BY' else '🔴 SELL')
                st.markdown(f"""
                <div style="background-color: #064e3b; padding: 1rem; border-radius: 8px; margin: 1rem 0;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                        <div>
                            <strong>Ultimo:</strong> {tipo_display} {data_fmt}<br>
                            <strong>Prezzo:</strong> ${prezzo_segnale:.2f}
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 1.5rem; font-weight: bold; color: {colore_var};">{segno}{var_pct_segnale:.1f}%</div>
                            <div style="font-size: 0.85rem; color: {colore_var};">{testo}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        # Pulsante Mostra Grafico
        if st.button("📊 Mostra Grafico", use_container_width=True):
            st.session_state.grafico_ticker = r['ticker']
            
    if st.session_state.get('grafico_ticker'):
        st.markdown("---")
        st.subheader(f"📊 {st.session_state.grafico_ticker}")
        tf_options = {"1GG": "1d", "5GG": "5d", "1M": "1mo", "3M": "3mo", "6M": "6mo", "1A": "1y"}
        tf_choice = st.radio("Periodo:", list(tf_options.keys()), horizontal=True, index=5)
        tf_value = tf_options[tf_choice]
        if tf_choice == "1GG":
            fetch_period, interval, hide_sma = '5d', '15m', True
        else:
            fetch_period, interval, hide_sma = tf_value, '1d', False
        fig = genera_grafico_baleine(st.session_state.grafico_ticker, fetch_period, 50, 200, timeframe=tf_value, interval=interval, hide_sma=hide_sma)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True})
        if st.button("✖️ Chiudi grafico", use_container_width=True):
            st.session_state.grafico_ticker = None
            st.rerun()    else:
        st.info("📭 Portfolio vuoto.")
