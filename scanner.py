# MATRIX DVMS V6.1.3 Desktop - Versione Finale Blindata (17 Modifiche Applicate)
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
import urllib.request
import io
from datetime import datetime, timedelta
warnings.filterwarnings('ignore')
st.set_page_config(page_title="MATRIX DVMS V6.1.3 Desktop", layout="wide", page_icon="🛡️")
# ==============================================================================
# CSS CON FONT INGRANDITI
# ==============================================================================
st.markdown("""
<style>
.main .block-container { padding-top: 1rem; padding-bottom: 2rem; font-size: 13px !important; }
.stButton > button { width: 100%; padding: 0.85rem; font-size: 1.1rem; font-weight: bold; }
footer {visibility: hidden;}
.header-box {
background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
color: white; padding: 1.5rem; border-radius: 12px; text-align: center; margin-bottom: 1.5rem;
}
.header-box h1 { color: white; margin: 0; font-size: 2.2rem !important; }
.header-box p { font-size: 1.1rem !important; }
.signal-box { padding: 1.2rem; border-radius: 8px; margin-bottom: 0.5rem; font-size: 13px !important; }
.signal-green { background-color: #064e3b; border-left: 5px solid #10b981; color: #d1fae5; }
.signal-yellow { background-color: #451a03; border-left: 5px solid #f59e0b; color: #fef3c7; }
.signal-red { background-color: #450a0a; border-left: 5px solid #ef4444; color: #fee2e2; }
.signal-blue { background-color: #1e3a5f; border-left: 5px solid #3b82f6; color: #dbeafe; }
.signal-fabio { background: linear-gradient(135deg, #064e3b 0%, #065f46 100%); border-left: 5px solid #10b981; color: #d1fae5; box-shadow: 0 0 15px rgba(16, 185, 129, 0.3); font-size: 14px !important; }
.signal-fabio h3 { font-size: 1.5rem !important; margin-bottom: 0.5rem !important; }
.signal-fabio p { font-size: 1.1rem !important; }
.dataframe { background-color: #1e293b !important; color: #e2e8f0 !important; border-radius: 8px; overflow: hidden; font-size: 14px !important; }
.dataframe th { background-color: #334155 !important; color: #f8fafc !important; font-size: 15px !important; font-weight: bold; }
.signal-history-box { background-color: #1e293b; border-radius: 8px; padding: 1rem; margin: 1rem 0; border: 2px solid #334155; }
.signal-history-title { color: #f8fafc; font-size: 1.1rem; font-weight: bold; margin-bottom: 0.5rem; }
.semaforo-box { padding: 1.5rem; border-radius: 12px; margin-bottom: 1.5rem; text-align: center; }
.semaforo-verde { background: linear-gradient(135deg, #064e3b 0%, #065f46 100%); border: 2px solid #10b981; }
.semaforo-giallo { background: linear-gradient(135deg, #451a03 0%, #78350f 100%); border: 2px solid #f59e0b; }
.semaforo-rosso { background: linear-gradient(135deg, #450a0a 0%, #7f1d1d 100%); border: 2px solid #ef4444; }
.target-dot { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; vertical-align: middle; cursor: help; transition: all 0.3s ease; }
.target-dot-achieved { background-color: #10b981; box-shadow: 0 0 8px #10b981; }
.target-dot-pending { background-color: #64748b; box-shadow: 0 0 4px #64748b; }
.target-dot:hover { transform: scale(1.3); }
.target-tooltip { font-size: 0.75rem; color: #94a3b8; font-style: italic; margin-left: 8px; }
.by-fabio-badge { background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 4px 12px; border-radius: 6px; font-size: 0.85rem; font-weight: bold; margin-left: 10px; display: inline-block; box-shadow: 0 2px 8px rgba(16, 185, 129, 0.4); }
.breakout-card { background-color: #451a03; border-left: 5px solid #f59e0b; padding: 1rem; border-radius: 8px; margin-bottom: 0.5rem; }
</style>
""", unsafe_allow_html=True)
# ==============================================================================
# GESTIONE FILE
# ==============================================================================
PORTAFOGLIO_FILE = "portafoglio.json"
WATCHLIST_FILE = "watchlist.json"
PAPER_TRADING_FILE = "paper_trading.json"
SEGNALI_STORICI_FILE = "segnali_storici.json"
REGISTRO_VENDITE_FILE = "registro_vendite.json"
REGISTRO_ACQUISTI_FILE = "registro_acquisti.json"
MINUSVALENZE_FILE = "minusvalenze.json"
IMPOSTAZIONI_FILE = "impostazioni.json"
LOG_PROPOSTE_FILE = "log_proposte.json"
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
# FUNZIONE REGISTRA PROPOSTA (LOG)
# ==============================================================================
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
# ==============================================================================
# MODULO 1: FILTRO MACRO DOPPIO (SEMAFORO DI MERCATO)
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
if not vix.empty:
vix_valore = float(vix['Close'].iloc[-1])
except:
pass
if vix_valore is not None:
if spy_prezzo > spy_sma10 and vix_valore < 20:
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
scenari = {'vendita_gain': [], 'vendita_loss': [], 'hold_catalizzatore': [], 'nuova_liquidita': True}
if esclusioni_list is None: esclusioni_list = []
catalizzatori = {}
if catalizzatori_input:
for item in catalizzatori_input.split(';'):
item = item.strip()
if ':' in item:
ticker, resto = item.split(':', 1)
ticker = ticker.strip().upper()
match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', resto)
if match:
giorno, mese, anno = match.groups()
if len(anno) == 2: anno = '20' + anno
try:
data_cat = datetime(int(anno), int(mese), int(giorno))
catalizzatori[ticker] = {'descrizione': resto.split('-')[0].strip() if '-' in resto else resto.strip(), 'data': data_cat}
except: pass
oggi = datetime.now()
try:
ticker_obj = yf.Ticker(titolo)
info = ticker_obj.info
hist = ticker_obj.history(period='1y')
if hist.empty: return {'errore': f'Impossibile recuperare dati per {titolo}'}
currency = info.get('currency', 'USD')
prezzo_raw = hist['Close'].iloc[-1]
prezzo_eur = prezzo_raw / eurusd_rate if currency == 'USD' else prezzo_raw
quantita_acquistabile = importo / prezzo_eur
for pos in portafoglio:
ticker_pos = pos['Ticker']
if ticker_pos in esclusioni_list: continue
try:
ticker_obj_pos = yf.Ticker(ticker_pos)
hist_pos = ticker_obj_pos.history(period='1y')
info_pos = ticker_obj_pos.info
if hist_pos.empty: continue
currency_pos = info_pos.get('currency', 'USD')
prezzo_raw_pos = hist_pos['Close'].iloc[-1]
prezzo_eur_pos = prezzo_raw_pos / eurusd_rate if currency_pos == 'USD' else prezzo_raw_pos
prezzo_medio = pos['Prezzo_Medio']
pnl_pct = ((prezzo_eur_pos / prezzo_medio) - 1) * 100 if prezzo_medio > 0 else 0
trend_30gg = 0
if len(hist_pos) >= 30: trend_30gg = ((hist_pos['Close'].iloc[-1] / hist_pos['Close'].iloc[-30]) - 1) * 100
s_score = calcola_s_score(info_pos)
fase = rileva_fase_weinstein(hist_pos)
kill_switch = ("FASE 4" in fase or s_score < 50)
has_catalizzatore = False
if ticker_pos in catalizzatori:
if catalizzatori[ticker_pos]['data'] >= oggi: has_catalizzatore = True
if has_catalizzatore:
scenari['hold_catalizzatore'].append({'ticker': ticker_pos, 'messaggio': f"⚠️ {ticker_pos} ha un catalizzatore imminente. Non vendere nonostante la perdita."})
elif pnl_pct > 0 and trend_30gg > 0:
scenari['vendita_gain'].append({'ticker': ticker_pos, 'pnl_pct': round(pnl_pct, 2), 'trend_30gg': round(trend_30gg, 2), 'quantita': pos['Quantita'], 'valore': round(prezzo_eur_pos * pos['Quantita'], 2), 'messaggio': f'⚠️ NON VENDERE: {ticker_pos} è in gain (+{pnl_pct:.1f}%) con trend positivo (+{trend_30gg:.1f}% in 30gg). Ha impiegato mesi per caricarsi ed è ora pronto a ripartire.'})
elif pnl_pct < 0 or kill_switch:
supporto = hist_pos['Low'].tail(20).min()
distanza_supporto = ((prezzo_eur_pos - supporto) / supporto) * 100 if supporto > 0 else 0
scenari['vendita_loss'].append({'ticker': ticker_pos, 'pnl_pct': round(pnl_pct, 2), 'kill_switch': kill_switch, 'distanza_supporto': round(distanza_supporto, 2), 'quantita': pos['Quantita'], 'valore': round(prezzo_eur_pos * pos['Quantita'], 2), 'messaggio': f'✅ CONSIDERA VENDITA: {ticker_pos} è in loss ({pnl_pct:.1f}%) {"con Kill Switch attivo" if kill_switch else ""}. Ottimizzazione fiscale possibile.'})
except: continue
if scenari['vendita_loss']: scenari['nuova_liquidita'] = False
return {'titolo': titolo, 'prezzo_eur': round(prezzo_eur, 2), 'quantita_acquistabile': round(quantita_acquistabile, 6), 'importo': importo, 'scenari': scenari}
except Exception as e:
return {'errore': str(e)}
# ==============================================================================
# MODULO 3: MOTORE DI RIBILANCIAMENTO MENSILE
# ==============================================================================
def parse_catalizzatori(testo):
catalizzatori = {}
if not testo: return catalizzatori
for item in testo.split(';'):
item = item.strip()
if ':' in item:
ticker, resto = item.split(':', 1)
ticker = ticker.strip().upper()
match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', resto)
if match:
giorno, mese, anno = match.groups()
if len(anno) == 2: anno = '20' + anno
try:
data_cat = datetime(int(anno), int(mese), int(giorno))
catalizzatori[ticker] = {'descrizione': resto.split('-')[0].strip() if '-' in resto else resto.strip(), 'data': data_cat}
except: pass
return catalizzatori
def calcola_score_ribilanciamento(ticker, df, info, insider_data=None):
score = 0
fase = rileva_fase_weinstein(df)
if "FASE 2" in fase: score += 30
elif "FASE 1" in fase: score += 20
elif "FASE 3" in fase: score += 10
elif "CORREZIONE" in fase: score += 25
else: score += 0
s_score = calcola_s_score(info)
score += (s_score / 100) * 25
if len(df) >= 30:
trend_30gg = ((df['Close'].iloc[-1] / df['Close'].iloc[-30]) - 1) * 100
if trend_30gg > 10: score += 20
elif trend_30gg > 5: score += 15
elif trend_30gg > 0: score += 10
elif trend_30gg > -5: score += 5
else: score += 10
delta = df['Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
rsi_val = float((100 - (100 / (1 + rs))).iloc[-1]) if not rs.empty else 50
if 40 <= rsi_val <= 60: score += 15
elif 30 <= rsi_val < 40: score += 12
elif 60 < rsi_val <= 70: score += 10
else: score += 5
if insider_data:
if insider_data.get('has_buy'): score += 10
elif insider_data.get('has_sell'): score += 0
else: score += 5
else: score += 5
return min(100, max(0, round(score, 1)))
def genera_piano_ribilanciamento(portafoglio, watchlist_tickers, semaforo, catalizzatori, esclusioni, eurusd_rate):
oggi = datetime.now()
vendite, monitor, acquisti = [], [], []
for pos in portafoglio:
ticker = pos['Ticker']
if ticker in esclusioni: continue
try:
ticker_obj = yf.Ticker(ticker)
df = ticker_obj.history(period='1y')
info = ticker_obj.info
if df.empty: continue
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
except: continue
BIG_TECH_GROWTH_LIST = "GOOGL, AMZN, PLTR, META, MSFT, AAPL, TSLA, AVGO, CRM, ADBE, NOW, PANW, FTNT, CRDO, SMCI, ARMR, MRVL, QCOM, MU, INTU"
watchlist_tickers = [t.strip().upper() for t in BIG_TECH_GROWTH_LIST.split(",")]
for ticker in watchlist_tickers:
if any(p['Ticker'] == ticker for p in portafoglio) or ticker in esclusioni: continue
try:
ticker_obj = yf.Ticker(ticker)
df = ticker_obj.history(period='1y')
info = ticker_obj.info
if df.empty: continue
score = calcola_score_ribilanciamento(ticker, df, info, {'has_buy': False, 'has_sell': False})
fase = rileva_fase_weinstein(df)
prezzo_eur = round((df['Close'].iloc[-1] / eurusd_rate) if info.get('currency', 'USD') == 'USD' else df['Close'].iloc[-1], 2)
delta = df['Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
rsi_val = float((100 - (100 / (1 + rs))).iloc[-1]) if not rs.empty else 50
sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
prezzo_attuale = df['Close'].iloc[-1]
distanza_sma200_pct = abs(prezzo_attuale - sma200) / sma200 * 100 if sma200 > 0 else 999
s_score = calcola_s_score(info)
is_extreme_oversold = (s_score >= 85 and rsi_val < 30)
if score > 75 or is_extreme_oversold:
if semaforo['stato'] == 'rosso':
msg = "⚠️ Titolo pronto all'acquisto, ma acquisti sospesi per mercato ribassista. Ricontrolla tra 7 giorni."
if is_extreme_oversold: msg = "⚠️ Rimbalzo Tecnico Estremo: Titolo ipervenduto con fondamentali solidi. Alto rischio/alto rendimento. Valuta ingresso con position sizing ridotto. (Acquisti sospesi per mercato ribassista)."
else:
msg = "✅ Setup valido e mercato favorevole."
if is_extreme_oversold: msg = "⚠️ Rimbalzo Tecnico Estremo: Titolo ipervenduto con fondamentali solidi. Alto rischio/alto rendimento. Valuta ingresso con position sizing ridotto."
acquisti.append({'ticker': ticker, 'score': score, 'fase': fase, 'prezzo_eur': prezzo_eur, 'stato_mercato': 'sospeso' if semaforo['stato'] == 'rosso' else 'attivo', 'messaggio': msg, 's_score': s_score, 'rsi': rsi_val, 'distanza_sma': distanza_sma200_pct})
except: continue
acquisti_sorted = sorted(acquisti, key=lambda x: (-x.get('s_score', 0), x.get('rsi', 50), x.get('distanza_sma', 100)))
for idx, item in enumerate(acquisti_sorted):
rank = idx + 1
if rank == 1: badge = "🥇 PRIORITÀ 1"
elif rank == 2: badge = "🥈 PRIORITÀ 2"
elif rank == 3: badge = "🥉 PRIORITÀ 3"
else: badge = f"🎯 PRIORITÀ {rank}"
upside_msg = " | Upside stimato: Alto" if item.get('s_score', 0) >= 85 and item.get('rsi', 50) < 30 else ""
item['badge'] = f"{badge}{upside_msg}"
return {'vendite': sorted(vendite, key=lambda x: x['score']), 'monitor': sorted(monitor, key=lambda x: x['score'], reverse=True), 'acquisti': acquisti_sorted, 'semaforo': semaforo['stato']}
# ==============================================================================
# REGISTRO ACQUISTI
# ==============================================================================
def registra_acquisto(ticker, qta_acquistata, prezzo_acquisto, data_acquisto=None):
try:
if data_acquisto is None: data_acquisto = datetime.now().strftime("%Y-%m-%d")
importo_totale = prezzo_acquisto * qta_acquistata
registro = carica_json(REGISTRO_ACQUISTI_FILE)
id_op = max([v.get('id', 0) for v in registro], default=0) + 1
registro.append({'id': id_op, 'Data': data_acquisto, 'Ticker': ticker.strip().upper(), 'Qta_Acquistata': round(qta_acquistata, 6), 'Prezzo_Acquisto': round(prezzo_acquisto, 4), 'Importo_Totale': round(importo_totale, 2)})
salva_json(REGISTRO_ACQUISTI_FILE, registro)
return {'id': id_op, 'importo_totale': round(importo_totale, 2)}
except Exception as e:
print(f"Errore registrazione acquisto: {e}")
return None
# ==============================================================================
# ALLOCAZIONE DINAMICA
# ==============================================================================
def genera_piano_allocazione(portafoglio, liquidita_totale, eurusd_rate, watchlist_tickers=None, registro_acquisti=None):
if watchlist_tickers is None: watchlist_tickers = []
if registro_acquisti is None: registro_acquisti = carica_json(REGISTRO_ACQUISTI_FILE)
oggi = datetime.now()
ticker_acquistati_recenti = set()
for v in registro_acquisti:
try:
data_acquisto = datetime.strptime(v.get('Data', ''), "%Y-%m-%d")
giorni_fa = (oggi - data_acquisto).days
if giorni_fa <= 5: ticker_acquistati_recenti.add(v.get('Ticker', '').strip().upper())
except: pass
watchlist_filtrata = [t for t in watchlist_tickers if t not in ticker_acquistati_recenti]
by_fabio_tickers, pac_ottimali, watchlist_breakout, nuove_entrate = [], [], [], []
for pos in portafoglio:
ticker = pos['Ticker']
try:
ticker_obj = yf.Ticker(ticker)
df = ticker_obj.history(period='1y')
info = ticker_obj.info
if df.empty: continue
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
by_fabio_tickers.append({'ticker': ticker, 's_score': s_score, 'fase': fase, 'rsi': rsi_oggi, 'prezzo': prezzo, 'motivo': motivo_by_fabio, 'tipo': 'pyramiding'})
continue
if pos.get('Tipo') == 'PAC' and fase in ["FASE 2 (Avanzamento)", "CORREZIONE in Trend (Pullback Fase 2)"]:
pac_ottimali.append({'ticker': ticker, 's_score': s_score, 'fase': fase, 'rsi': rsi_oggi, 'prezzo': prezzo, 'tipo': 'pac_extra'})
continue
except: continue
ticker_in_portafoglio = {p['Ticker'] for p in portafoglio}
for ticker in watchlist_filtrata:
if ticker in ticker_in_portafoglio: continue
try:
ticker_obj = yf.Ticker(ticker)
df = ticker_obj.history(period='1y')
info = ticker_obj.info
if df.empty: continue
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
except: continue
capitale_residuo = liquidita_totale
allocazioni = []
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
if data_segnale is None: data_segnale = datetime.now().strftime("%Y-%m-%d")
ticker_norm = ticker.strip().upper()
for segnale in segnali:
if segnale.get('Ticker', '').strip().upper() == ticker_norm and segnale.get('Data') == data_segnale: return
segnali.append({'Ticker': ticker_norm, 'Tipo': tipo_segnale, 'Data': data_segnale, 'Prezzo': round(prezzo_usd, 2)})
salva_json(SEGNALI_STORICI_FILE, segnali)
except: pass
def get_ultimo_segnale(ticker):
try:
segnali = carica_json(SEGNALI_STORICI_FILE)
if not segnali: return None
ticker_norm = ticker.strip().upper()
segnali_ticker = [s for s in segnali if s.get('Ticker', '').strip().upper() == ticker_norm]
if not segnali_ticker: return None
segnali_ticker.sort(key=lambda x: x.get('Data', ''), reverse=True)
return segnali_ticker[0]
except: return None
def calcola_performance_segnale(segnale, prezzo_attuale):
if segnale is None: return None, None, None
try:
prezzo_segnale = segnale.get('Prezzo', 0)
if prezzo_segnale is None or prezzo_segnale == 0: return None, None, None
data_segnale = datetime.strptime(segnale.get('Data', ''), "%Y-%m-%d")
giorni_trascorsi = (datetime.now() - data_segnale).days
variazione_pct = ((prezzo_attuale - prezzo_segnale) / prezzo_segnale) * 100
return variazione_pct, giorni_trascorsi, prezzo_segnale
except: return None, None, None
def formatta_data_europea(data_iso):
try: return datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
except: return data_iso
def format_ultimo_segnale_display(ticker, prezzo_attuale_usd):
try:
if prezzo_attuale_usd is None or prezzo_attuale_usd == 0: return "N/D"
ultimo_segnale = get_ultimo_segnale(ticker)
if not ultimo_segnale: return "N/D"
prezzo_segnale = ultimo_segnale.get('Prezzo', 0)
if prezzo_segnale is None or prezzo_segnale == 0: return "N/D"
var_pct = ((prezzo_attuale_usd - prezzo_segnale) / prezzo_segnale) * 100
data_fmt = formatta_data_europea(ultimo_segnale.get('Data', ''))
tipo = ultimo_segnale.get('Tipo', 'N/D')
segno = "+" if var_pct > 0 else ""
if tipo == 'BY': return f"🟢 BY: {data_fmt} ({segno}{var_pct:.1f}%)" if var_pct >= 0 else f"🔴 BY: {data_fmt} ({segno}{var_pct:.1f}%)"
elif tipo == 'BY_FABIO': return f"🟢 BY FABIO: {data_fmt} ({segno}{var_pct:.1f}%)" if var_pct >= 0 else f"🔴 BY FABIO: {data_fmt} ({segno}{var_pct:.1f}%)"
else: return f"🟢 SELL: {data_fmt} ({segno}{var_pct:.1f}%)" if var_pct <= 0 else f"🟠 SELL: {data_fmt} ({segno}{var_pct:.1f}%)"
except: return "N/D"
# ==============================================================================
# SISTEMA REGISTRO VENDITE & FISCALITÀ
# ==============================================================================
ALIQUOTA_TASSE = 0.26
ANNI_COMPENSAZIONE = 4
def registra_vendita(ticker, qta_venduta, prezzo_medio, prezzo_vendita, data_vendita=None):
try:
if data_vendita is None: data_vendita = datetime.now().strftime("%Y-%m-%d")
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
liquidita_totale = 0.0
for v in registro:
qta = v.get('Qta_Venduta', 0)
prezzo_vendita = v.get('Prezzo_Vendita', 0)
tasse = v.get('Tasse', 0)
incasso = (prezzo_vendita * qta) - tasse
liquidita_totale += incasso
return round(liquidita_totale, 2)
def elimina_operazione_vendita(id_op):
try:
registro = carica_json(REGISTRO_VENDITE_FILE)
registro = [v for v in registro if v.get('id') != id_op]
salva_json(REGISTRO_VENDITE_FILE, registro)
return True
except: return False
def reset_registro_vendite():
try:
salva_json(REGISTRO_VENDITE_FILE, [])
salva_json(MINUSVALENZE_FILE, [])
return True
except: return False
# ==============================================================================
# FUNZIONI DI RICOSTRUZIONE
# ==============================================================================
def prepara_dataframe_per_segnali(df, sma_short=50, sma_long=200):
df = df.copy()
df['SMA_Short'] = df['Close'].rolling(window=sma_short).mean()
df['SMA_Long'] = df['Close'].rolling(window=sma_long).mean()
df['Vol_Media_20'] = df['Volume'].rolling(window=20).mean()
return df
def trova_segnali_by(df, sma_short=50, sma_long=200):
by_signals = []
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
except: continue
return by_signals
def trova_segnali_sell(df, sma_short=50, sma_long=200):
sell_signals = []
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
except: continue
return sell_signals
def ricostruisci_segnali_retroattivi(ticker, anni_indietro=1):
try:
ticker_obj = yf.Ticker(ticker)
df = ticker_obj.history(period=f"{anni_indietro}y")
if df.empty or len(df) < 250: return 0
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
# PORTAFOGLIO INIZIALE
# ==============================================================================
PORTAFOGLIO_INIZIALE = [
{"Ticker": "TTWO", "Tipo": "Spot", "Quantita": 3.547945, "Prezzo_Medio": 187.55},
{"Ticker": "SOFI", "Tipo": "PAC", "Quantita": 53.607426, "Prezzo_Medio": 14.31, "PAC_Settimanale": 15.0},
{"Ticker": "VRT", "Tipo": "PAC", "Quantita": 0.335985, "Prezzo_Medio": 178.58, "PAC_Settimanale": 30.0},
{"Ticker": "CRWD", "Tipo": "PAC", "Quantita": 0.092269, "Prezzo_Medio": 216.76, "PAC_Settimanale": 10.0},
]
BIG_TECH_GROWTH_LIST = "GOOGL, AMZN, PLTR, META, MSFT, AAPL, TSLA, AVGO, CRM, ADBE, NOW, PANW, FTNT, CRDO, SMCI, ARMR, MRVL, QCOM, MU, INTU"
for key in ['df_fortezza', 'df_cavalli', 'df_monitor', 'df_palantir', 'scansione_completata', 'analisi_risultati', 'grafico_ticker', 'grafico_prezzo_medio', 'spy_data', 'dashboard_stats', 'portafoglio', 'last_update', 'pyramiding_alerts', 'take_profit_alerts', 'zona_interesse_alerts', 'semaforo_mercato', 'piano_ribilanciamento', 'risultato_simulazione', 'risultato_podc', 'piano_allocazione', 'breakout_tickers', 'liquidita_totale_alloc']:
if key not in st.session_state:
st.session_state[key] = None if key not in ['pyramiding_alerts', 'take_profit_alerts', 'zona_interesse_alerts', 'breakout_tickers'] else []
if st.session_state.portafoglio is None or not st.session_state.portafoglio:
st.session_state.portafoglio = carica_json(PORTAFOGLIO_FILE) or PORTAFOGLIO_INIZIALE
if not os.path.exists(PORTAFOGLIO_FILE):
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
if len(df) < 200: return "Dati insufficienti"
prezzo = df['Close'].iloc[-1]
sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
sma200_prev = df['Close'].rolling(window=200).mean().iloc[-20]
sma50 = df['Close'].rolling(window=50).mean().iloc[-1]
slope_sma200 = (sma200 - sma200_prev) / sma200_prev if sma200_prev > 0 else 0
if prezzo < sma200 and slope_sma200 < -0.01:
distanza_sma200 = abs(prezzo - sma200) / sma200
if prezzo > sma50 and distanza_sma200 < 0.03: return "FASE 1 (Accumulazione/Basing)"
return "FASE 4 (Declino Strutturale)"
if prezzo < sma50 and prezzo > sma200 and slope_sma200 > 0.005: return "CORREZIONE in Trend (Pullback Fase 2)"
if prezzo > sma200 * 1.2 and slope_sma200 > 0.02: return "FASE 3 (Distribuzione)"
if prezzo > sma200 and slope_sma200 > 0.005: return "FASE 2 (Avanzamento)"
return "FASE 1 (Accumulazione/Basing)"
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
def controlla_earnings(ticker_obj):
try:
earnings_dates = ticker_obj.earnings_dates
if earnings_dates is None or earnings_dates.empty: return None, "⚪ N/D", False
oggi = datetime.now()
prossima_data = None
for data in earnings_dates.index:
data_naive = data.tz_localize(None) if hasattr(data, 'tz_localize') else data
if data_naive > oggi:
prossima_data = data_naive
break
if prossima_data is None: return None, "⚪ N/D", False
giorni_mancanti = (prossima_data - oggi).days
if giorni_mancanti <= 7: return giorni_mancanti, f"🔴 UTILI tra {giorni_mancanti}gg", True
elif giorni_mancanti <= 14: return giorni_mancanti, f"🟡 Utili tra {giorni_mancanti}gg", False
else: return giorni_mancanti, f"⚪ Utili tra {giorni_mancanti}gg", False
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
variazione_pct = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
return round(variazione_pct, 2), round(hist['Close'].iloc[-1] - hist['Close'].iloc[-2], 2)
except: return None, None
def rileva_gap_storico(df, soglia_minima_pct=3.0):
try:
if len(df) < 30: return None
prezzo_attuale = df['Close'].iloc[-1]
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
except: return None
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
rsi_oggi = float((100 - (100 / (1 + (gain/loss)))).iloc[-1]) if not (gain/loss).empty else 50
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
if rsi_oggi < 30 and fase in ["FASE 1 (Accumulazione/Basing)", "FASE 2 (Avanzamento)"] and vol_oggi > vol_medio * 1.5:
return True, f"✅ Oversold bounce: RSI {rsi_oggi:.0f}, {fase}, Vol {vol_oggi/vol_medio:.2f}x", False
if prezzo_vicino_sma50 and volume_ok and rsi_ok and candela_verde:
return True, f"Pullback SMA50 completato (Vol: {vol_oggi/vol_medio:.2f}x, RSI: {rsi_oggi:.0f})", False
else:
motivi = []
if not prezzo_vicino_sma50: motivi.append(f"Prezzo fuori SMA50 ({distanza_sma50:.1f}%)")
if not volume_ok: motivi.append(f"Volume bassi ({vol_oggi/vol_medio:.2f}x)")
if not rsi_ok: motivi.append(f"RSI ipercomprato ({rsi_oggi:.0f})")
if not candela_verde: motivi.append("Candela rossa")
return False, "; ".join(motivi), False
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
rsi_oggi = float((100 - (100 / (1 + rs))).iloc[-1]) if not rs.empty else 50
slope_sma200 = (sma200 - sma200_prev) / sma200_prev if sma200_prev > 0 else 0
if ticker_obj:
info = ticker_obj.info
s_score = calcola_s_score(info)
else:
return False, "S-Score non disponibile"
if s_score < 70: return False, f"S-Score {s_score} < 70 (non Fortezza)"
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
breakout_tickers = []
for pos in portafoglio:
ticker = pos['Ticker']
try:
ticker_obj = yf.Ticker(ticker)
df = ticker_obj.history(period='1y')
info = ticker_obj.info
if df.empty or len(df) < 50: continue
s_score = calcola_s_score(info)
if s_score < 65: continue
prezzo = df['Close'].iloc[-1]
sma50 = df['Close'].rolling(window=50).mean().iloc[-1]
distanza_sma50 = (sma50 - prezzo) / sma50 * 100
if distanza_sma50 > 5.0 or prezzo > sma50: continue
delta = df['Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
rsi_oggi = float((100 - (100 / (1 + rs))).iloc[-1]) if not rs.empty else 50
rsi_5gg_fa = float((100 - (100 / (1 + rs))).iloc[-6]) if len(rs) >= 6 else rsi_oggi
if not (rsi_oggi > rsi_5gg_fa and 30 <= rsi_oggi <= 50): continue
vol_medio = df['Volume'].rolling(window=20).mean().iloc[-1]
vol_oggi = df['Volume'].iloc[-1]
if vol_oggi <= vol_medio * 1.2: continue
breakout_tickers.append({'ticker': ticker, 's_score': s_score, 'prezzo': round(prezzo / eurusd_rate if info.get('currency', 'USD') == 'USD' else prezzo, 2), 'sma50': round(sma50 / eurusd_rate if info.get('currency', 'USD') == 'USD' else sma50, 2), 'distanza_sma50': round(distanza_sma50, 1), 'rsi': round(rsi_oggi, 1), 'rsi_5gg_fa': round(rsi_5gg_fa, 1), 'volume_ratio': round(vol_oggi / vol_medio, 2)})
except: continue
return breakout_tickers
def genera_grafico_baleine(ticker, period, sma_short, sma_long, prezzo_medio_eur=None, timeframe='1d', interval='1d', eurusd_rate=1.12):
df = yf.Ticker(ticker).history(period=period, interval=interval)
if df.empty: return None
if timeframe == '1wk' and interval == '1d':
df = df.resample('W').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'})
window_s = min(sma_short, len(df))
window_l = min(sma_long, len(df))
window_v = min(20, len(df))
df['SMA_Short'] = df['Close'].rolling(window=window_s).mean()
df['SMA_Long'] = df['Close'].rolling(window=window_l).mean()
df['Vol_Media_20'] = df['Volume'].rolling(window=window_v).mean()
delta = df['Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
df['RSI'] = 100 - (100 / (1 + (gain / loss)))
recent_df = df.tail(60)
supporto = recent_df['Low'].min()
resistenza = recent_df['High'].max()
gap_level = rileva_gap_storico(df, soglia_minima_pct=3.0)
prezzo_attuale = df['Close'].iloc[-1]
fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.65, 0.2, 0.15], subplot_titles=(f'{ticker} ${prezzo_attuale:.2f} - {timeframe.upper()}', 'Volumi', 'RSI'))
fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Prezzo', increasing_line_color='#00e676', increasing_fillcolor='#00e676', decreasing_line_color='#ff1744', decreasing_fillcolor='#ff1744'), row=1, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['SMA_Short'], line=dict(color='#ff9800', width=1.5), name=f'SMA {sma_short}'), row=1, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['SMA_Long'], line=dict(color='#2196f3', width=1.5), name=f'SMA {sma_long}'), row=1, col=1)
if prezzo_medio_eur is not None:
prezzo_medio_usd = prezzo_medio_eur * eurusd_rate
fig.add_hline(y=prezzo_medio_usd, line_dash="dot", line_color="#00e676", line_width=2, annotation_text=f" Medio: ${prezzo_medio_usd:.2f} (€{prezzo_medio_eur:.2f})", row=1, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['SMA_Short'], fill=None, mode='lines', line=dict(width=0), showlegend=False), row=1, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['SMA_Long'], fill='tonexty', mode='lines', line=dict(width=0), fillcolor='rgba(33, 150, 243, 0.15)', name='Rete Balene'), row=1, col=1)
fig.add_hline(y=supporto, line_dash="dash", line_color="#00e676", line_width=1.5, annotation_text=f" Sup: {supporto:.2f}", row=1, col=1)
fig.add_hline(y=resistenza, line_dash="dash", line_color="#ff1744", line_width=1.5, annotation_text=f" Res: {resistenza:.2f}", row=1, col=1)
if gap_level:
fig.add_hline(y=gap_level, line_dash="dot", line_color="#f59e0b", line_width=2, annotation_text=f" Gap: {gap_level}", row=1, col=1)
by_x, by_y, sell_x, sell_y = [], [], [], []
for i in range(window_l, len(df)):
if (abs(df['Close'].iloc[i] - df['SMA_Short'].iloc[i]) / df['SMA_Short'].iloc[i] <= 0.02 and df['Volume'].iloc[i] > df['Vol_Media_20'].iloc[i] and df['Close'].iloc[i] > df['Open'].iloc[i]):
by_x.append(df.index[i])
by_y.append(df['Close'].iloc[i])
if (df['Close'].iloc[i] < df['SMA_Long'].iloc[i] and df['Close'].iloc[i-1] >= df['SMA_Long'].iloc[i-1] and df['Volume'].iloc[i] > df['Vol_Media_20'].iloc[i]):
sell_x.append(df.index[i])
sell_y.append(df['Close'].iloc[i])
if by_x:
fig.add_trace(go.Scatter(x=[by_x[-1]], y=[by_y[-1]], mode='markers', marker=dict(symbol='triangle-up', size=18, color='#00e676', line=dict(width=2, color='#00c853')), name='▲ Ultimo BY'))
if sell_x:
fig.add_trace(go.Scatter(x=[sell_x[-1]], y=[sell_y[-1]], mode='markers', marker=dict(symbol='triangle-down', size=18, color='#ff1744', line=dict(width=2, color='#d50000')), name='▼ Ultimo SELL'))
colors = ['#00e676' if df['Close'].iloc[i] >= df['Open'].iloc[i] else '#ff1744' for i in range(len(df))]
fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='Volume', opacity=0.7), row=2, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#ff1744', width=1.5), name='RSI 14'), row=3, col=1)
fig.add_hline(y=70, line_dash="dash", line_color="#ff1744", row=3, col=1)
fig.add_hline(y=30, line_dash="dash", line_color="#00e676", row=3, col=1)
fig.update_layout(height=900, xaxis_rangeslider_visible=False, template="plotly_dark", paper_bgcolor='#0f172a', plot_bgcolor='#1e293b', font=dict(color='#e2e8f0', size=13), legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5, bgcolor='rgba(15, 23, 42, 0.9)'))
return fig
def valuta_stato_pac(info, df_storico):
try:
s_score = calcola_s_score(info)
fase = rileva_fase_weinstein(df_storico)
rev_growth = info.get('revenueGrowth', 0.0) or 0.0
if "FASE 4" in fase or s_score < 50 or rev_growth < 0: return "🔴 PAC SOSPESO"
return "🟢 PAC ATTIVO"
except: return "⚪ N/D"
def aggiorna_quotazioni_portafoglio(portafoglio, eurusd_rate):
risultati = []
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
trend = "🟢 Forte +" if pnl_pct > 5 else ("🟢 +" if pnl_pct > 0 else (" -" if pnl_pct > -5 else "🔴 Forte -"))
earnings_giorni, earnings_msg, _ = controlla_earnings(ticker_obj)
stato_pac = valuta_stato_pac(info, hist) if pos.get('Tipo') == 'PAC' else "N/A"
ultimo_segnale_display = format_ultimo_segnale_display(ticker, prezzo_usd)
risultati.append({**pos, "Prezzo_Attuale_EUR": round(prezzo_eur, 2), "Prezzo_Attuale_USD": round(prezzo_usd, 2), "Valore_Attuale": round(valore_attuale, 2), "PnL_EUR": round(pnl_eur, 2), "PnL_%": round(pnl_pct, 2), "Trend": trend, "Earnings": earnings_msg, "Variazione_Pct": var_pct, "Stato_PAC": stato_pac, "Ultimo_Segnale": ultimo_segnale_display})
except Exception:
risultati.append({**pos, "Prezzo_Attuale_EUR": None, "Prezzo_Attuale_USD": None, "PnL_EUR": None, "PnL_%": None, "Trend": "Errore", "Earnings": "N/D", "Variazione_Pct": None, "Stato_PAC": "Errore", "Ultimo_Segnale": "N/D"})
return risultati
def calcola_target(ticker_obj, prezzo_medio, prezzo_attuale):
try:
hist = ticker_obj.history(period='1y')
if hist.empty: return None
rendimenti = hist['Close'].pct_change().dropna()
volatilita = rendimenti.std() * math.sqrt(252) if len(rendimenti) > 0 else 0.15
high_52w = hist['High'].max()
picchi = []
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
if not current or not entry or not target: return 0.0
if target <= entry: return 100.0
progress = ((current - entry) / (target - entry)) * 100
if math.isnan(progress) or math.isinf(progress): return 0.0
return max(0.0, min(100.0, round(progress, 1)))
except: return 0.0
prog1 = calc_progress(prezzo_attuale, prezzo_medio, t1)
prog2 = calc_progress(prezzo_attuale, prezzo_medio, t2)
prog3 = calc_progress(prezzo_attuale, prezzo_medio, t3)
upside1 = round(((t1 / prezzo_attuale) - 1) * 100, 1) if prezzo_attuale and prezzo_attuale > 0 else 0
upside2 = round(((t2 / prezzo_attuale) - 1) * 100, 1) if prezzo_attuale and prezzo_attuale > 0 else 0
upside3 = round(((t3 / prezzo_attuale) - 1) * 100, 1) if prezzo_attuale and prezzo_attuale > 0 else 0
sl_down = round(((sl / prezzo_attuale) - 1) * 100, 1) if prezzo_attuale and prezzo_attuale > 0 else 0
return {'t1': round(t1, 2), 'prog1': prog1, 'upside1': upside1, 't2': round(t2, 2), 'prog2': prog2, 'upside2': upside2, 't3': round(t3, 2), 'prog3': prog3, 'upside3': upside3, 'sl': round(sl, 2), 'sl_down': sl_down}
except: return None
# ==============================================================================
# PODC CON LOG COMPLETO
# ==============================================================================
def avvia_podc(portafoglio, eurusd_rate, catalizzatori_input, stato_mercato="N/D"):
catalizzatori = {}
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
except: continue
if data_vendita is None:
print(f"⚠️ Formato data non riconosciuto: {data_str}")
continue
giorni_fa = (oggi - data_vendita).days
if giorni_fa <= 5:
ticker_venduti_recenti.add(v.get('Ticker', '').strip().upper())
print(f"✅ {v.get('Ticker')} venduto {giorni_fa} giorni fa - escluso da PODC")
except Exception as e:
print(f"Errore controllo 5 giorni: {e}")
registra_proposta("PODC", "PODC_AVVIATO", "SISTEMA", f"PODC avviato. Titoli in portafoglio: {len(portafoglio)}. Stato mercato: {stato_mercato}", stato_mercato)
gain_suggestions, loss_candidates, gain_analyzed, loss_rejected = [], [], [], []
total_capital_freed = 0.0
for pos in portafoglio:
ticker = pos['Ticker']
try:
prezzo_attuale = pos.get('Prezzo_Attuale_EUR')
if not prezzo_attuale: continue
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
suggestions = []
for cand_a in gain_suggestions:
for cand_b in loss_candidates:
capital = cand_a['capital_freed']
if capital < 50: continue
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
# INTERFACCIA PRINCIPALE
# ==============================================================================
semaforo_header = calcola_semaforo_mercato()
if semaforo_header['stato'] == 'verde':
sem_color, sem_icon, sem_msg = "#10b981", "🟢", "MERCATO RIALZISTA"
elif semaforo_header['stato'] == 'rosso':
sem_color, sem_icon, sem_msg = "#ef4444", "🔴", "MERCATO RIBASSISTA"
else:
sem_color, sem_icon, sem_msg = "#f59e0b", "🟡", "MERCATO LATERALE"
if semaforo_header['spy_prezzo'] is None or semaforo_header['vix'] is None:
sem_display = "🟡 DATI MERCATO N/D"
else:
sem_display = f"{sem_icon} {sem_msg} | SPY: ${semaforo_header['spy_prezzo']} | VIX: {semaforo_header['vix']}"
st.markdown(f'''
<div class="header-box">
<h1>🛡️ MATRIX DVMS V6.1.3 Desktop</h1>
<p style="margin: 0.5rem 0 0 0; opacity: 0.9;">Scanner Operativo Blindato & Gestione Portafoglio</p>
<p style="margin: 0.8rem 0 0 0; font-size: 1.1rem; font-weight: bold; color: {sem_color};">{sem_display}</p>
</div>
''', unsafe_allow_html=True)
if os.path.exists(IMPOSTAZIONI_FILE):
with open(IMPOSTAZIONI_FILE, 'r', encoding='utf-8') as f:
impostazioni = json.load(f)
else:
impostazioni = {"lista_ticker_default": "ADBE, RKLB, SOUN, IONQ, ASTS, PLTR, ZETA, NKE, AMD, CRWD, NU, NVDA, TSLA, MCD, DIS, SBUX, PEP, INTC, SOFI, NBIS, VRT, ANET", "catalizzatori": "", "esclusioni": ""}
st.sidebar.header("⚙️ Parametri Matrix")
tickers_input = st.sidebar.text_area("Ticker (virgola):", value=impostazioni.get("lista_ticker_default", ""))
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
period = st.sidebar.selectbox("Periodo:", ["3mo", "6mo", "1y", "2y"], index=2)
sma_short = st.sidebar.slider("SMA Breve:", 10, 100, 50)
sma_long = st.sidebar.slider("SMA Lunga:", 50, 200, 200)
eurusd_rate = st.sidebar.number_input("EUR/USD:", min_value=0.8, max_value=1.5, value=1.12, step=0.001)
st.sidebar.markdown("---")
ignore_fase_4 = st.sidebar.checkbox("Blocca Fase 4", True)
st.sidebar.markdown("---")
st.sidebar.subheader("📅 Catalizzatori Eventi")
catalizzatori_input = st.sidebar.text_area("Formato: TICKER: Descrizione - GG/MM/AA", value=impostazioni.get("catalizzatori", ""), height=100, help="Es: TTWO: Lancio GTA VI - 15/12/2026; AAPL: Evento - 20/12/2026")
st.sidebar.markdown("---")
st.sidebar.subheader("🚫 Esclusioni Ribilanciamento")
esclusioni_input = st.sidebar.text_area("Titoli da escludere (separati da virgola):", value=impostazioni.get("esclusioni", ""), height=80, help="Es: SOFI, TTD. Non appariranno nelle proposte di vendita.")
st.sidebar.markdown("---")
st.sidebar.subheader("🔧 Debug Segnali")
if st.sidebar.button("🔍 Verifica Segnali Storici"):
segnali = carica_json(SEGNALI_STORICI_FILE)
if segnali:
st.sidebar.info(f"Totale segnali: {len(segnali)}")
for s in reversed(segnali[-10:] if len(segnali) > 10 else segnali):
st.sidebar.text(f"{s.get('Ticker', 'N/D')}: {s.get('Tipo', 'N/D')} - {s.get('Data', 'N/D')} - ${s.get('Prezzo', 'N/D')}")
else:
st.sidebar.warning("Nessun segnale registrato")
if st.sidebar.button("🔄 Ricostruisci Segnali Retroattivi (1 anno)"):
tickers_da_scansionare = list(set(tickers + [t.strip().upper() for t in BIG_TECH_GROWTH_LIST.split(",")]))
progress_bar = st.progress(0)
totale = 0
for i, ticker in enumerate(tickers_da_scansionare):
progress_bar.progress((i + 1) / len(tickers_da_scansionare))
try:
totale += ricostruisci_segnali_retroattivi(ticker, anni_indietro=1)
except Exception as e:
st.sidebar.error(f"Errore su {ticker}: {e}")
progress_bar.empty()
st.success(f"✅ Ricostruzione completata! Aggiunti {totale} segnali storici.")
st.rerun()
if st.sidebar.button("🔴 AVVIA SCANSIONE", type="primary", use_container_width=True):
impostazioni["lista_ticker_default"] = tickers_input
impostazioni["catalizzatori"] = catalizzatori_input
impostazioni["esclusioni"] = esclusioni_input
with open(IMPOSTAZIONI_FILE, 'w', encoding='utf-8') as f:
json.dump(impostazioni, f)
progress_bar = st.progress(0)
if st.session_state.spy_data is None:
try: st.session_state.spy_data = yf.Ticker("SPY").history(period=period)
except: st.session_state.spy_data = None
stats = {'by_count': 0, 'hold_count': 0, 'sell_count': 0, 'by_tickers': [], 'hold_tickers': [], 'sell_tickers': [], 'earnings_warnings': [], 'error_tickers': [], 'by_fabio_tickers': [], 'smci_tickers': []}
pyramiding_alerts, take_profit_alerts, zona_interesse_alerts, extended_hours_alerts = [], [], [], []
lista_fortezza, lista_cavalli, lista_monitor, lista_palantir = [], [], [], []
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
if df.empty or len(df) < max(sma_long, 50): continue
prezzo_eur, prezzo_usd, currency = get_prezzi_corretti(ticker_obj, eurusd_rate)
if prezzo_eur is None: continue
df['SMA_Short'] = df['Close'].rolling(window=sma_short).mean()
df['SMA_Long'] = df['Close'].rolling(window=sma_long).mean()
df['Vol_Media_20'] = df['Volume'].rolling(window=20).mean()
vol_ratio = df.iloc[-1]['Volume'] / df.iloc[-1]['Vol_Media_20'] if df.iloc[-1]['Vol_Media_20'] > 0 else 0
s_score = calcola_s_score(info)
fase = rileva_fase_weinstein(df)
figura_z, _ = rileva_figura_z(df)
trigger_by, motivo_by, earnings_bloccato = verifica_trigger_by_fortezza(df, sma_short, ticker_obj)
earnings_giorni, earnings_msg, earnings_bloccato2 = controlla_earnings(ticker_obj)
if earnings_bloccato2: stats['earnings_warnings'].append(f"{ticker} ({earnings_msg})")
trigger_by_fabio, motivo_by_fabio = verifica_by_fabio(df, sma_short, ticker_obj)
if trigger_by_fabio:
print(f"🟢 BY FABIO RILEVATO: {ticker}")
stats.setdefault('by_fabio_tickers', []).append(ticker)
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
prezzo_attuale = df['Close'].iloc[-1]
distanza_sma200_pct = abs(prezzo_attuale - sma200) / sma200 * 100 if sma200 > 0 else 999
if s_score >= 75 and "FASE 1" in fase and prezzo_attuale < sma50 and 35 <= rsi_oggi <= 50:
# Calcolo R/R per ordinamento
targets_smci = calcola_target(ticker_obj, prezzo_eur, prezzo_eur)
rr_smci = 0.0
if targets_smci:
upside = targets_smci.get('upside1', 0)
risk = abs(targets_smci.get('sl_down', 1))
rr_smci = round(upside / risk, 2) if risk > 0 else 0
stats.setdefault('smci_tickers', []).append({'ticker': ticker, 'rr': rr_smci, 's_score': s_score})
# MODIFICA 3b: Log SMCI
registra_proposta("SCANSIONE", "TIPOLOGIA_SMCI", ticker, f"Pattern SMCI: S-Score {s_score}, FASE 1, RSI {rsi_oggi:.0f}, R/R: {rr_smci}", stato="N/D")
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
if trigger_by_tecnico_oggi: registra_segnale(ticker, 'BY', prezzo_usd, oggi_str)
elif trigger_sell_tecnico_oggi: registra_segnale(ticker, 'SELL', prezzo_usd, oggi_str)
if ignore_fase_4 and "FASE 4" in fase:
stats['sell_count'] += 1; stats['sell_tickers'].append(ticker); continue
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
stats['by_count'] += 1; stats['by_tickers'].append(ticker)
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
stats['by_count'] += 1; stats['by_tickers'].append(ticker)
else:
stats['hold_count'] += 1; stats['hold_tickers'].append(ticker)
elif is_watchlist:
motivi_hold = []
if vol_ratio < 1.60: motivi_hold.append("Volumi bassi")
if not figura_z: motivi_hold.append("No Figura Z")
lista_monitor.append({'Ticker': ticker, 'Prezzo EUR': prezzo_eur, 'S-Score': s_score, 'Fase': fase, 'Motivo Hold': "; ".join(motivi_hold), 'Earnings': earnings_msg})
stats['hold_count'] += 1; stats['hold_tickers'].append(ticker)
except Exception as e:
error_msg = str(e)[:100]
print(f"❌ ERRORE su {ticker}: {error_msg}")
stats.setdefault('error_tickers', []).append(f"{ticker}: {error_msg}")
registra_proposta("SCANSIONE", "RIEPILOGO_SCANSIONE", "SISTEMA", f"BY: {stats['by_count']}, HOLD: {stats['hold_count']}, SELL: {stats['sell_count']}, BY_FABIO: {len(stats.get('by_fabio_tickers', []))}, SMCI: {len(stats.get('smci_tickers', []))}", stato="N/D")
progress_bar.empty()
st.session_state.dashboard_stats = stats
st.session_state.pyramiding_alerts = pyramiding_alerts
st.session_state.take_profit_alerts = take_profit_alerts
st.session_state.zona_interesse_alerts = zona_interesse_alerts
st.session_state.extended_hours_alerts = extended_hours_alerts
st.session_state.df_palantir = pd.DataFrame(lista_palantir) if lista_palantir else None
if lista_fortezza or lista_cavalli or lista_monitor or lista_palantir:
st.session_state.df_fortezza = pd.DataFrame(lista_fortezza) if lista_fortezza else None
st.session_state.df_cavalli = pd.DataFrame(lista_cavalli) if lista_cavalli else None
st.session_state.df_monitor = pd.DataFrame(lista_monitor) if lista_monitor else None
st.session_state.scansione_completata = True
st.rerun()
# ==============================================================================
# TAB PRINCIPALI
# ==============================================================================
tab_portafoglio, tab_scanner, tab_analisi, tab_registro, tab_paper = st.tabs(["💼 Portafoglio", "🔍 Scanner Dashboard", "📊 Analisi Singola", "📋 Registro Vendite", "🤖 Portfolio Sperimentale AI"])
with tab_portafoglio:
st.subheader("Portafoglio Reale - Quotazioni Live")
col_upd1, col_upd2 = st.columns([4, 1])
with col_upd1: st.caption(f"Ultimo aggiornamento: {st.session_state.last_update or 'Mai - Clicca il pulsante'}")
with col_upd2:
if st.button("🔄 Aggiorna Quotazioni", type="primary"):
with st.spinner("🔄 Aggiornamento quotazioni in corso..."):
st.session_state.portafoglio = aggiorna_quotazioni_portafoglio(st.session_state.portafoglio, eurusd_rate)
st.session_state.last_update = datetime.now().strftime("%H:%M:%S")
st.rerun()
st.markdown("---")
with st.expander("⚙️ Modifica Portafoglio (Aggiungi/Rimuovi Titoli)"):
col_add1, col_add2, col_add3, col_add4 = st.columns([2, 1, 1, 1])
with col_add1: new_ticker = st.text_input("Ticker (es. AAPL)").upper()
with col_add2: new_tipo = st.selectbox("Tipo", ["Spot", "PAC"])
with col_add3: new_qta = st.number_input("Quantità", min_value=0.0001, step=0.0001)
with col_add4: new_medio = st.number_input("Prezzo Medio €", min_value=0.01, step=0.01)
if st.button("➕ Aggiungi al Portafoglio"):
if new_ticker:
port_att = st.session_state.portafoglio or carica_json(PORTAFOGLIO_FILE) or PORTAFOGLIO_INIZIALE
posizione_esistente = None
for i, p in enumerate(port_att):
if p['Ticker'] == new_ticker and p.get('Tipo') == new_tipo:
posizione_esistente = i
break
if posizione_esistente is not None:
port_att[posizione_esistente]['Quantita'] = new_qta
port_att[posizione_esistente]['Prezzo_Medio'] = new_medio
st.warning(f"⚠️ {new_ticker} ({new_tipo}) già esistente. Aggiornato con nuovi valori.")
else:
port_att.append({"Ticker": new_ticker, "Tipo": new_tipo, "Quantita": new_qta, "Prezzo_Medio": new_medio})
st.success(f"✅ {new_ticker} ({new_tipo}) aggiunto!")
st.session_state.portafoglio = port_att
salva_json(PORTAFOGLIO_FILE, port_att)
st.rerun()
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
portafoglio = st.session_state.portafoglio
if not portafoglio or len(portafoglio) == 0:
st.warning("⚠️ Portafoglio vuoto. Aggiungi titoli usando l'expander sopra o carica il file portafoglio.json")
else:
has_live_data = any(p.get('Prezzo_Attuale_EUR') is not None for p in portafoglio)
if not has_live_data:
st.info("👆 Clicca **🔄 Aggiorna Quotazioni** per caricare i dati di mercato")
else:
totale_valore = sum(p.get('Valore_Attuale', 0) or (p.get('Prezzo_Attuale_EUR', 0) * p.get('Quantita', 0)) for p in portafoglio)
totale_carico = sum(p.get('Prezzo_Medio', 0) * p.get('Quantita', 0) for p in portafoglio)
col_tot1, col_tot2, col_tot3 = st.columns(3)
col_tot1.metric("💰 Valore Totale", f"€ {totale_valore:,.2f}")
col_tot2.metric("💼 Investito", f"€ {totale_carico:,.2f}")
col_tot3.metric("📈 P&L Totale", f"€ {totale_valore - totale_carico:,.2f}", f"{((totale_valore/totale_carico)-1)*100 if totale_carico>0 else 0:+.2f}%")
st.markdown("---")
st.markdown("### 🏦 Dashboard Liquidità & Patrimonio")
liquidita_totale = calcola_liquidita_totale()
riepilogo_fiscale = calcola_riepilogo_fiscale(None)
patrimonio_totale = liquidita_totale + totale_valore
col_pat1, col_pat2, col_pat3, col_pat4 = st.columns(4)
with col_pat1: st.metric("💰 Liquidità Netta", f"€ {liquidita_totale:,.2f}", help="Incassi netti da vendite (prezzo × qta - tasse)")
with col_pat2: st.metric("📈 Valore Portafoglio", f"€ {totale_valore:,.2f}", help="Valore attuale delle posizioni aperte")
with col_pat3: st.metric("🏦 Patrimonio Totale", f"€ {patrimonio_totale:,.2f}", help="Liquidità + Valore Portafoglio")
with col_pat4:
pnl_percentuale = ((patrimonio_totale / totale_carico) - 1) * 100 if totale_carico > 0 else 0
st.metric("📊 Rendimento Totale", f"{pnl_percentuale:+.2f}%", help=f"Su capitale investito iniziale: € {totale_carico:,.2f}")
st.markdown("---")
st.markdown("### 🛡️ Protocollo di Ottimizzazione Dinamica del Capitale (PODC)")
if st.button("🛡️ Avvia Protocollo Ottimizzazione (PODC)", type="primary", use_container_width=True):
with st.spinner("🔄 Analisi efficienza capitale in corso..."):
semaforo_podc = calcola_semaforo_mercato()
st.session_state.risultato_podc = avvia_podc(portafoglio, eurusd_rate, catalizzatori_input, semaforo_podc['stato'])
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
for sug in res['suggestions']:
st.markdown(f"""
<div style="background-color: #1e293b; padding: 1rem; border-radius: 8px; border-left: 4px solid #10b981; margin-bottom: 1rem;">
<p style="margin: 0.2rem 0;"><strong>1. LIBERA CAPITALE:</strong> Vendi {sug['sell_pct']}% di <span style="color: #10b981;">{sug['sell_ticker']}</span> → Libera circa <strong>€{sug['capital_freed']:.2f}</strong>.</p>
<p style="margin: 0.2rem 0;"><strong>2. MEDIA STRATEGICA:</strong> Usa €{sug['capital_freed']:.2f} per comprare <span style="color: #3b82f6;">{sug['buy_ticker']}</span>.</p>
<p style="margin: 0.2rem 0;"><strong>3. RISULTATO:</strong> Il prezzo medio di {sug['buy_ticker']} scende da €{sug['old_avg']:.2f} a <strong>€{sug['new_avg']:.2f}</strong>. Il tuo PnL passa da {sug['old_pnl']:.1f}% a <strong style="color: #10b981;">{sug['new_pnl']:.1f}%</strong>.</p>
</div>
""", unsafe_allow_html=True)
st.markdown("---")
st.markdown("#### 📊 RIEPILOGO ANALISI PODC:")
st.markdown(f"**✅ Titoli in Gain analizzati:** {len(res['gain_analyzed'])}")
for g in res['gain_analyzed']: st.markdown(f"- **{g['ticker']}**: {g['reason']}")
st.markdown(f"<br>**❌ Titoli in Loss NON candidati alla media:** {len(res['loss_rejected'])}", unsafe_allow_html=True)
for r_item in res['loss_rejected']: st.markdown(f"- **{r_item['ticker']}**: {r_item['reason']}")
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
with col_liq1: st.metric("💵 Liquidità reale in cassa", f"€ {liquidita_reale:,.2f}", help="Soldi già incassati dalle vendite passate (netto tasse)")
with col_liq2: st.metric("🎯 Capitale liberabile proposto", f"€ {capitale_proposto:,.2f}", help="Soldi che il PODC suggerisce di liberare ora")
with col_liq3: st.metric("🏦 TOTALE DISPONIBILE", f"€ {totale_disponibile:,.2f}", help="Liquidità reale + Capitale liberabile = Totale per nuovi acquisti")
st.markdown("---")
st.markdown("### 📊 Motore di Ribilanciamento Mensile")
if st.button("📊 Genera Piano di Rotazione Mensile", type="secondary", use_container_width=True):
with st.spinner("🔄 Analisi in corso..."):
semaforo = calcola_semaforo_mercato()
catalizzatori = parse_catalizzatori(catalizzatori_input)
esclusioni_list = [t.strip().upper() for t in esclusioni_input.split(",") if t.strip()]
st.session_state.piano_ribilanciamento = genera_piano_ribilanciamento(portafoglio, tickers, semaforo, catalizzatori, esclusioni_list, eurusd_rate)
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
consigli = []
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
for c in consigli: st.info(c)
st.markdown("---")
st.subheader("💰 Piano di Allocazione Dinamica")
if st.button("💰 Genera Piano di Allocazione", type="secondary", use_container_width=True):
with st.spinner("🔄 Calcolo allocazione ottimale..."):
liquidita_reale = calcola_liquidita_totale()
liquidita_totale_alloc = liquidita_reale + 500
st.session_state.piano_allocazione = genera_piano_allocazione(portafoglio, liquidita_totale_alloc, eurusd_rate, tickers)
st.session_state.liquidita_totale_alloc = liquidita_totale_alloc
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
<div style="background-color: #1e293b; padding: 1rem; border-radius: 8px; margin-top: 1rem; border: 1px solid #334155; font-size: 13px;">
<h4 style="margin-top: 0; color: #f59e0b;">📋 LEGENDA PRIORITÀ:</h4>
<p style="margin: 0.3rem 0;"><strong>🥇 PRIORITÀ 1 - BY FABIO (45% capitale):</strong> Segnale d'élite. S-Score ≥ 70 + geometria perfetta (Breakout su SMA50 con volume > 1.3x OPPURE Pullback su SMA200 con distanza 0-3% e RSI 40-60).</p>
<p style="margin: 0.3rem 0;"><strong>🥈 PRIORITÀ 2 - PAC EXTRA (30% capitale):</strong> Rinforzo strategico su PAC esistenti in Fase 2 o Correzione sana. Non è il PAC settimanale automatico.</p>
<p style="margin: 0.3rem 0;"><strong>🥉 PRIORITÀ 3 - BREAKOUT (20% capitale):</strong> Titolo sotto SMA50 di oltre 5%, RSI in risalita (30-50), volume > 1.2x. Si prepara a rompere al rialzo.</p>
<p style="margin: 0.3rem 0; color: #fbbf24;"><strong>⚠️ NOTA:</strong> Solo i primi 3 titoli con importo ≥ €50 sono contrassegnati come "Proposto ✅ SÌ". Gli altri sono candidati ma non prioritari.</p>
</div>
""", unsafe_allow_html=True)
st.metric("💵 Liquidità Residua", f"€ {piano['liquidita_residua']:,.2f}")
if st.button("✖️ Nascondi Piano di Allocazione"):
st.session_state.piano_allocazione = None
st.session_state.liquidita_totale_alloc = None
st.rerun()
st.markdown("---")
for idx_pos, pos in enumerate(portafoglio):
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
if prezzo_medio > 0 and prezzo_eur: var_acquisto = ((prezzo_eur / prezzo_medio) - 1) * 100
else: var_acquisto = 0
if var_pct is not None:
var_color = "#10b981" if var_pct > 0 else "#ef4444"
var_symbol = "▲" if var_pct > 0 else "▼" if var_pct < 0 else "●"
var_display = f"{var_symbol} {var_pct:+.2f}%"
else:
var_color, var_symbol, var_display = "#94a3b8", "●", "N/D"
if var_acquisto > 0: acqu_color, acqu_symbol = "#10b981", "▲"
elif var_acquisto < 0: acqu_color, acqu_symbol = "#ef4444", "▼"
else: acqu_color, acqu_symbol = "#94a3b8", "●"
if pnl_pct > 0: border_color = "#10b981"
elif pnl_pct < 0: border_color = "#ef4444"
else: border_color = "#64748b"
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
if target_raggiunti == 0: dots_html = '<span class="target-dot target-dot-pending" title="Nessun target raggiunto"></span><span class="target-dot target-dot-pending" title="Nessun target raggiunto"></span><span class="target-dot target-dot-pending" title="Nessun target raggiunto"></span>'
elif target_raggiunti == 1: dots_html = '<span class="target-dot target-dot-achieved" title="Target 1 raggiunto"></span><span class="target-dot target-dot-pending" title="Target 2 non raggiunto"></span><span class="target-dot target-dot-pending" title="Target 3 non raggiunto"></span>'
elif target_raggiunti == 2: dots_html = '<span class="target-dot target-dot-achieved" title="Target 1 raggiunto"></span><span class="target-dot target-dot-achieved" title="Target 2 raggiunto"></span><span class="target-dot target-dot-pending" title="Target 3 non raggiunto"></span>'
else: dots_html = '<span class="target-dot target-dot-achieved" title="Target 1 raggiunto"></span><span class="target-dot target-dot-achieved" title="Target 2 raggiunto"></span><span class="target-dot target-dot-achieved" title="Target 3 raggiunto"></span>'
dots_display = f'{dots_html} <span class="target-tooltip">{target_raggiunti}/3 Target</span>'
else:
dots_display = '<span class="target-tooltip">N/D</span>'
trigger_by_fabio, motivo_by_fabio = verifica_by_fabio(ticker_obj.history(period='1y'), 50, ticker_obj) if not ticker_obj.history(period='1y').empty else (False, "")
by_fabio_indicator = '<span class="by-fabio-badge" title="Ingresso matematicamente validato: Fortezza + Grafico">🟢 BY FABIO</span>' if trigger_by_fabio else ''
st.markdown(f"""
<div style="background-color: #1e293b; border-radius: 10px; padding: 1rem; margin-bottom: 0.75rem; border-left: 5px solid {border_color};">
<div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
<div style="flex: 1; min-width: 150px; border-right: 1px solid #334155; padding-right: 1rem;">
<div style="font-size: 1.6rem; color: #f8fafc; font-weight: bold;">{ticker} {by_fabio_indicator}</div>
<div style="font-size: 1rem; color: #94a3b8; margin-top: 0.3rem;">{stato_pac}</div>
</div>
<div style="flex: 2; min-width: 200px; border-right: 1px solid #334155; padding-right: 1rem; text-align: center;">
<div style="font-size: 1.4rem; color: #f8fafc; font-weight: bold;">€ {prezzo_display}</div>
<div style="color: {var_color}; font-size: 1.1rem; font-weight: bold; margin-top: 0.3rem;">{var_display} oggi</div>
<div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.2rem;">
<div style="color: {acqu_color}; font-size: 1rem;">{acqu_symbol} {var_acquisto:+.1f}% | {netto_label} dall'acquisto</div>
<div style="font-size: 0.9rem;">{dots_display}</div>
</div>
</div>
<div style="flex: 1; min-width: 150px; text-align: right;">
<div style="font-size: 1rem; color: #cbd5e1;">{ultimo_segnale}</div>
<div style="font-size: 1rem; color: #cbd5e1; margin-top: 0.3rem;">{trend}</div>
</div>
</div>
</div>
""", unsafe_allow_html=True)
with st.expander(f"🎯 Target e Stop Loss - {ticker}"):
if targets:
st.markdown(f"""
<div style="background-color: #1e293b; padding: 1rem; border-radius: 8px; border: 1px solid #334155;">
<h4 style="margin-top:0; color: #f59e0b;">🎯 TARGET DI PREZZO (Basati su resistenze grafiche):</h4>
<p style="margin: 0.2rem 0;">• <strong>Target 1:</strong> € {targets['t1']} (Upside: +{targets['upside1']}% | Progresso: {targets['prog1']}%)</p>
<p style="margin: 0.2rem 0;">• <strong>Target 2:</strong> € {targets['t2']} (Upside: +{targets['upside2']}% | Progresso: {targets['prog2']}%)</p>
<p style="margin: 0.2rem 0;">• <strong>Target 3:</strong> € {targets['t3']} (Upside: +{targets['upside3']}% | Progresso: {targets['prog3']}%)</p>
<hr style="border-color: #334155; margin: 0.5rem 0;">
<h4 style="margin-top:0; color: #ef4444;">🛡️ STOP LOSS DINAMICO: € {targets['sl']} ({targets['sl_down']}% dal prezzo attuale)</h4>
<ul style="font-size: 0.9rem; color: #cbd5e1; margin-bottom: 0;">
<li>⚠️ Quando raggiungi Target 1 → sposta stop a € {prezzo_medio:.2f} (break-even)</li>
<li>⚠️ Quando raggiungi Target 2 → sposta stop a € {targets['t1']}</li>
<li>⚠️ Quando raggiungi Target 3 → sposta stop a € {targets['t2']}</li>
</ul>
</div>
""", unsafe_allow_html=True)
else:
st.info("Dati insufficienti per calcolare i target.")
with st.expander(f"📋 Dettagli e Operazioni - {ticker}"):
col_d1, col_d2, col_d3, col_d4 = st.columns(4)
with col_d1: st.metric("Quantità", f"{quantita:.6f}")
with col_d2: st.metric("Prezzo Medio", f"€ {prezzo_medio:.2f}")
with col_d3: st.metric("P&L €", f"€ {pnl_eur:.2f}")
with col_d4: st.metric("P&L %", f"{pnl_pct:+.2f}%")
st.caption(f"📅 Prossimi Utili: {earnings}")
st.markdown("---")
st.markdown("**➕ Aggiungi Quote**")
col_a1, col_a2, col_a3 = st.columns([1, 1, 1])
with col_a1: nuova_qta = st.number_input(f"Nuova Qta", min_value=0.0001, step=0.0001, key=f"qta_{ticker}_{idx_pos}")
with col_a2: nuovo_prezzo_acq = st.number_input(f"Prezzo Acquisto €", min_value=0.01, step=0.01, key=f"prezzo_acq_{ticker}_{idx_pos}")
with col_a3:
st.write(""); st.write("")
if st.button(f"✅ Conferma Aggiunta", key=f"add_{ticker}_{idx_pos}"):
if nuova_qta > 0 and nuovo_prezzo_acq > 0:
vecchio_medio = pos['Prezzo_Medio']
nuovo_medio = ((quantita * vecchio_medio) + (nuova_qta * nuovo_prezzo_acq)) / (quantita + nuova_qta)
pos['Quantita'] = round(quantita + nuova_qta, 6)
pos['Prezzo_Medio'] = round(nuovo_medio, 4)
salva_json(PORTAFOGLIO_FILE, portafoglio)
st.session_state.portafoglio = portafoglio
st.success(f"✅ Aggiunte {nuova_qta} quote di {ticker}. Nuovo medio: €{nuovo_medio:.4f}")
st.rerun()
st.markdown("---")
st.markdown("**➖ Vendi Quote**")
modalita_vendita = st.radio(f"Modalità vendita {ticker}", ["📊 Percentuale (%)", "🔢 Quantità specifica"], horizontal=True, key=f"modalita_{ticker}_{idx_pos}")
qta_da_vendere = 0
if modalita_vendita == "📊 Percentuale (%)":
pct_vendita = st.slider(f"Percentuale da vendere", min_value=1.0, max_value=100.0, value=100.0, step=1.0, key=f"pct_{ticker}_{idx_pos}")
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
tasse_sim = residuo * ALIQUOTA_TASSE
pnl_netto_prev = pnl_lordo_prev - tasse_sim
st.markdown(f"""
<div style="background-color: #1e293b; padding: 1rem; border-radius: 8px; margin: 1rem 0; border: 1px solid #334155;">
<div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">
<div><div style="color: #94a3b8; font-size: 0.9rem;">P&L Lordo</div><div style="color: {'#10b981' if pnl_lordo_prev > 0 else '#ef4444'}; font-size: 1.3rem; font-weight: bold;">€ {pnl_lordo_prev:+.2f} ({pnl_pct_prev:+.1f}%)</div></div>
<div><div style="color: #94a3b8; font-size: 0.9rem;">Tasse stimate (26%)</div><div style="color: #ef4444; font-size: 1.3rem; font-weight: bold;">€ -{tasse_sim:.2f}</div></div>
<div><div style="color: #94a3b8; font-size: 0.9rem;">Netto reale</div><div style="color: {'#10b981' if pnl_netto_prev > 0 else '#ef4444'}; font-size: 1.3rem; font-weight: bold;">€ {pnl_netto_prev:+.2f}</div></div>
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
st.markdown("---")
if st.button(f"🗑️ Rimuovi {ticker} dal Portafoglio", key=f"remove_{ticker}_{idx_pos}"):
portafoglio = [p for p in portafoglio if p['Ticker'] != ticker]
st.session_state.portafoglio = portafoglio
salva_json(PORTAFOGLIO_FILE, portafoglio)
st.success(f"✅ {ticker} rimosso dal portafoglio")
st.rerun()
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
if stats['earnings_warnings']: st.warning(f"⚠️ **Attenzione Utili**: {', '.join(stats['earnings_warnings'])}")
if stats.get('by_fabio_tickers'):
st.markdown("---")
st.subheader("🚨 SEGNALI BY FABIO RILEVATI (Ingresso Matematico)")
st.markdown(f"""
<div class="signal-box signal-fabio">
<h3 style="margin: 0;">🟢 {len(stats['by_fabio_tickers'])} Titoli con segnale BY FABIO</h3>
<p style="margin: 0.8rem 0 0 0; font-size: 1.3rem; font-weight: bold;"><strong>{', '.join(stats['by_fabio_tickers'])}</strong></p>
<p style="margin: 0.5rem 0 0 0; font-size: 1.05rem; opacity: 0.9;">✅ Ingresso matematicamente validato: Fortezza (S-Score ≥ 70) + Grafico (Breakout/Pullback)</p>
<p style="margin: 0.3rem 0 0 0; font-size: 0.95rem; color: #fbbf24;">🎯 Priorità 1 - Allocazione 45% del capitale disponibile</p>
</div>
""", unsafe_allow_html=True)
if stats.get('error_tickers'):
st.markdown("---")
st.subheader("❌ Titoli con Errori di Scansione")
for err in stats['error_tickers']: st.warning(f"⚠️ {err}")
if stats.get('smci_tickers'):
# Ordina per R/R decrescente
smci_sorted = sorted(stats['smci_tickers'], key=lambda x: x.get('rr', 0), reverse=True)
ticker_list = ", ".join([f"{t['ticker']} (R/R: {t['rr']})" for t in smci_sorted])
st.markdown("---")
st.subheader("🎯 TITOLI TIPOLOGIA 'SMCI' (Ordinati per R/R)")
st.markdown(f"""
<div class="signal-box signal-blue" style="border-left: 5px solid #3b82f6; background-color: #1e3a5f;">
<h3 style="margin: 0; color: #dbeafe;">🧬 {len(stats['smci_tickers'])} Titoli con geometria SMCI</h3>
<p style="margin: 0.5rem 0 0 0; font-size: 1.1rem; font-weight: bold; color: #dbeafe;">{ticker_list}</p>
<p style="margin: 0.3rem 0 0 0; font-size: 0.9rem; opacity: 0.9;">S-Score ≥ 75 | FASE 1 | Prezzo < SMA50 | RSI 35-50. Ordinati dal miglior Rapporto Rischio/Rendimento.</p>
</div>
""", unsafe_allow_html=True)
if st.session_state.get('extended_hours_alerts'):
st.markdown("---"); st.subheader("⚡ ALERT MOVIMENTI ANOMALI (Fuori Orario)")
col_a1, col_a2 = st.columns(2)
for idx, alert in enumerate(st.session_state.extended_hours_alerts):
box_class = "signal-green" if alert['variazione'] > 0 else "signal-red"
html_block = f"""<div class="signal-box {box_class}"><h4 style="margin:0">{alert['colore']} {alert['ticker']} - {alert['sessione']}</h4><p style="margin:0.5rem 0">Variazione: <strong>{alert['variazione']:+.2f}%</strong> | Prezzo: €{alert['prezzo_eur']:.2f}</p></div>"""
if idx % 2 == 0: col_a1.markdown(html_block, unsafe_allow_html=True)
else: col_a2.markdown(html_block, unsafe_allow_html=True)
if st.session_state.pyramiding_alerts:
st.markdown("---"); st.subheader("🟢 Opportunità Pyramiding")
for alert in st.session_state.pyramiding_alerts:
pyr = alert['pyramiding']
st.markdown(f"""<div class="signal-box signal-green"><h4 style="margin:0">{alert['ticker']} ({alert['tipo']})</h4><p style="margin:0.5rem 0">💶 Capitale: ~{pyr['capitale']}€ | 📊 Azioni: {pyr['azioni']} | 🛑 Stop: {pyr['stop_loss']}€ | 🎯 Target: {pyr['target']}€</p></div>""", unsafe_allow_html=True)
if st.session_state.get('zona_interesse_alerts'):
st.markdown("---"); st.subheader("🟡 Zona di Interesse (Supporto SMA 200)")
for alert in st.session_state.zona_interesse_alerts:
st.markdown(f"""<div class="signal-box signal-yellow"><h4 style="margin:0">🟡 {alert['ticker']} (S-Score: {alert['s_score']})</h4><p style="margin:0.5rem 0">💶 Prezzo: {alert['prezzo_attuale_eur']}€ | 🛡️ SMA 200: {alert['sma200_eur']}€ (Distanza: {alert['distanza_pct']}%)</p></div>""", unsafe_allow_html=True)
if st.session_state.get('take_profit_alerts'):
st.markdown("---"); st.subheader("🎯 Allerta Take Profit")
for alert in st.session_state.take_profit_alerts:
st.markdown(f"""<div class="signal-box signal-red"><h4 style="margin:0">🔴 {alert['ticker']} ({alert['tipo']}) - RSI: {alert['rsi']}</h4><p style="margin:0.5rem 0">💶 Prezzo: {alert['prezzo_attuale_eur']}€ | 📈 Gain: <span style="color:#10b981;font-weight:bold">+{alert['gain_pct']}%</span></p></div>""", unsafe_allow_html=True)
st.markdown("---")
st.subheader("⚠️ Watchlist Breakout Imminente")
breakout_tickers = trova_breakout_imminenti(portafoglio, eurusd_rate)
if breakout_tickers:
st.info(f"🎯 Trovati {len(breakout_tickers)} titoli con breakout imminente")
for bt in breakout_tickers:
st.markdown(f"""
<div class="breakout-card">
<div style="display: flex; justify-content: space-between; align-items: center;">
<div><strong style="font-size: 1.2rem;">🟡 {bt['ticker']}</strong><span style="margin-left: 10px; color: #fcd34d;">Breakout Imminente</span></div>
<div style="text-align: right;">
<div style="font-size: 0.9rem; color: #fef3c7;">Prezzo: €{bt['prezzo']:.2f} | SMA50: €{bt['sma50']:.2f}</div>
<div style="font-size: 0.9rem; color: #fef3c7;">Distanza: -{bt['distanza_sma50']}% | RSI: {bt['rsi']:.0f} (↑ da {bt['rsi_5gg_fa']:.0f}) | Vol: {bt['volume_ratio']:.2f}x</div>
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
if st.session_state.df_fortezza is not None: st.dataframe(st.session_state.df_fortezza, use_container_width=True, height=400)
else: st.info("Nessun titolo in Fortezza.")
with tab_c:
st.subheader("Arena Speculativa (S-Score 40-60, Vol > +60%, Fase 1/2, Figura Z)")
if st.session_state.df_cavalli is not None: st.dataframe(st.session_state.df_cavalli, use_container_width=True, height=400)
else: st.info("Nessun titolo ha superato i 3 filtri rigidi.")
with tab_m:
st.subheader("👁️ Watchlist Permanente - Titoli da Monitorare")
if st.session_state.df_monitor is not None: st.dataframe(st.session_state.df_monitor, use_container_width=True, height=400)
else: st.info("La watchlist è vuota.")
with tab_p:
st.subheader("🤖 Setup Palantir (Growth Esplosiva + Sconto Irrazionale)")
st.markdown("*Filtri: S-Score ≥ 75, Revenue Growth ≥ 20%, PEG < 1.5, RSI < 45, Distanza SMA 200 ≤ 5%*")
if st.session_state.df_palantir is not None and not st.session_state.df_palantir.empty:
st.dataframe(st.session_state.df_palantir, use_container_width=True, height=400)
else:
st.info("Nessun titolo soddisfa attualmente i rigorosi criteri del Setup Palantir. Avvia una scansione.")
else:
st.info("Clicca **🔴 AVVIA SCANSIONE** nella sidebar.")
with tab_analisi:
st.subheader("🔍 Analisi Singola & Grafico")
col_in1, col_in2 = st.columns([2, 1])
with col_in1: ticker_input = st.text_input("Inserisci Ticker:", value="SOFI")
with col_in2:
st.write(""); st.write("")
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
df['Vol_Media_20'] = df['Volume'].rolling(window=20).mean()
vol_ratio = df.iloc[-1]['Volume'] / df.iloc[-1]['Vol_Media_20'] if df.iloc[-1]['Vol_Media_20'] > 0 else 0
s_score = calcola_s_score(info, ticker_s)
fase = rileva_fase_weinstein(df)
figura_z, _ = rileva_figura_z(df)
trigger_by, motivo_by, _ = verifica_trigger_by_fortezza(df, 50, ticker_obj)
trigger_by_fabio, motivo_by_fabio = verifica_by_fabio(df, 50, ticker_obj)
earnings_giorni, earnings_msg, _ = controlla_earnings(ticker_obj)
var_pct, var_abs = calcola_variazione_giornaliera(ticker_obj)
sma50_usd = round(df['Close'].rolling(window=50).mean().iloc[-1], 2)
sma200_usd = round(df['Close'].rolling(window=200).mean().iloc[-1], 2)
vol_oggi = df['Volume'].iloc[-1]
vol_medio = round(df['Volume'].rolling(window=20).mean().iloc[-1], 0)
supporto = round(df.tail(60)['Low'].min(), 2)
resistenza = round(df.tail(60)['High'].max(), 2)
delta_rsi = df['Close'].diff()
gain_rsi = (delta_rsi.where(delta_rsi > 0, 0)).rolling(window=14).mean()
loss_rsi = (-delta_rsi.where(delta_rsi < 0, 0)).rolling(window=14).mean()
rs_rsi = gain_rsi / loss_rsi
rsi_oggi = float((100 - (100 / (1 + rs_rsi))).iloc[-1]) if not rs_rsi.empty else 50
post_price = info.get('postMarketPrice')
post_change = info.get('postMarketChangePercent')
pre_price = info.get('preMarketPrice')
pre_change = info.get('preMarketChangePercent')
if post_price and post_change: market_msg = f"🌙 After-Hours: ${post_price:.2f} ({post_change:+.2f}%)"
elif pre_price and pre_change: market_msg = f"🌅 Pre-Market: ${pre_price:.2f} ({pre_change:+.2f}%)"
else: market_msg = "🌞 Regular Market (o N/D fuori orario)"
distanza_medie_pct = abs(sma50_usd - sma200_usd) / sma200_usd * 100 if sma200_usd != 0 else 0
pre_golden_cross = distanza_medie_pct < 3.0 and sma50_usd < sma200_usd
pre_death_cross = distanza_medie_pct < 3.0 and sma50_usd > sma200_usd
if trigger_by_fabio: segnale = "🟢 BY FABIO - Ingresso Matematico"
elif trigger_by: segnale = "🟢 BY - Acquista"
elif "FASE 4" in fase or s_score < 40: segnale = "🔴 SELL - Evita"
elif s_score >= 60 and "FASE 2" in fase: segnale = "🟡 HOLD - Monitora"
else: segnale = "🟡 HOLD - In attesa"
hist_intraday = ticker_obj.history(period='5d', interval='1d')
if not hist_intraday.empty:
last_day = hist_intraday.iloc[-1]
min_oggi, max_oggi = round(last_day['Low'], 2), round(last_day['High'], 2)
else:
min_oggi, max_oggi = "N/D", "N/D"
st.session_state.analisi_risultati = {
'ticker': ticker_s, 'segnale': segnale, 'prezzo_eur': prezzo_eur, 'prezzo_usd': prezzo_usd,
's_score': s_score, 'fase': fase, 'vol_ratio': vol_ratio, 'figura_z': figura_z,
'earnings_msg': earnings_msg, 'motivo_by': motivo_by_fabio if trigger_by_fabio else motivo_by,
'var_pct': var_pct, 'var_abs': var_abs, 'sma50_usd': sma50_usd, 'sma200_usd': sma200_usd,
'vol_oggi': vol_oggi, 'vol_medio': vol_medio, 'supporto': supporto, 'resistenza': resistenza,
'market_msg': market_msg, 'pre_death_cross': pre_death_cross, 'min_oggi': min_oggi,
'max_oggi': max_oggi, 'rsi': rsi_oggi, 'trigger_by_fabio': trigger_by_fabio
}
except Exception as e:
st.error(f"Errore: {e}")
if st.session_state.analisi_risultati:
r = st.session_state.analisi_risultati
st.markdown(f"### {r['ticker']} - {r['segnale']}")
col1, col2 = st.columns(2)
col1.metric("💶 Prezzo EUR", f"€ {r['prezzo_eur']:.2f}")
col2.metric("💵 Prezzo USD", f"$ {r['prezzo_usd']:.2f}")
col3, col4 = st.columns(2)
col3.metric("⚡ S-Score", r['s_score'])
col4.metric("📊 Fase", r['fase'])
col5, col6 = st.columns(2)
col5.metric("📈 RSI", f"{r.get('rsi', 50):.1f}")
col6.metric("📉 Minimo Oggi", f"${r['min_oggi']}" if isinstance(r['min_oggi'], (int, float)) else r['min_oggi'])
col7, col8 = st.columns(2)
col7.metric("📈 Massimo Oggi", f"${r['max_oggi']}" if isinstance(r['max_oggi'], (int, float)) else r['max_oggi'])
col8.metric("📈 SMA 50", f"$ {r['sma50_usd']:.2f}")
col9, col10 = st.columns(2)
col9.metric("📉 SMA 200", f"$ {r['sma200_usd']:.2f}")
col10.metric("📊 Volume Oggi", f"{r['vol_oggi']:,.0f}")
col11, col12 = st.columns(2)
col11.metric("📊 Volume Medio", f"{r['vol_medio']:,.0f}")
if r.get('var_pct') is not None:
var_color = "#10b981" if r['var_pct'] > 0 else "#ef4444"
st.markdown(f"**Variazione oggi:** <span style='color:{var_color};font-weight:bold'>{r['var_pct']:+.2f}% ({r['var_abs']:+.2f}€)</span>", unsafe_allow_html=True)
st.markdown(f"**{r['market_msg']}**")
if r.get('pre_golden_cross'): st.success("🚀 **Pre-Golden Cross**: La SMA 50 sta per incrociare la SMA 200 dal basso!")
elif r.get('pre_death_cross'): st.warning("⚠️ **Pre-Death Cross**: La SMA 50 sta per incrociare la SMA 200 dall'alto. Attenzione!")
st.markdown(f"**Volume Ratio:** {r['vol_ratio']:.2f} | **Figura Z:** {'✅ Sì' if r['figura_z'] else '❌ No'} | **Prossimi Utili:** {r['earnings_msg']}")
st.markdown(f"**🛡️ Sup:** ${r['supporto']:.2f} | **🎯 Res:** ${r['resistenza']:.2f}")
ticker_obj_analisi = yf.Ticker(r['ticker'])
targets_analisi = calcola_target(ticker_obj_analisi, r['prezzo_eur'], r['prezzo_usd'])
if targets_analisi:
rischio_pct = round(((targets_analisi['sl'] / r['prezzo_usd']) - 1) * 100, 1)
rapporto_rr = round(targets_analisi['upside1'] / abs(rischio_pct), 1) if rischio_pct != 0 else 1.5
st.markdown(f"""
<div style="background-color: #1e293b; padding: 1rem; border-radius: 8px; margin: 1rem 0; border: 1px solid #334155;">
<h4 style="margin-top:0; color: #f59e0b;">🎯 TARGET DI PREZZO (Basati su resistenze grafiche):</h4>
<p style="margin: 0.2rem 0;">• <strong>Target 1:</strong> ${targets_analisi['t1']} (+{targets_analisi['upside1']}%)</p>
<p style="margin: 0.2rem 0;">• <strong>Target 2:</strong> ${targets_analisi['t2']} (+{targets_analisi['upside2']}%)</p>
<p style="margin: 0.2rem 0;">• <strong>Target 3:</strong> ${targets_analisi['t3']} (+{targets_analisi['upside3']}%)</p>
<hr style="border-color: #334155; margin: 0.5rem 0;">
<h4 style="margin-top:0; color: #cbd5e1;">⚖️ RAPPORTO RISCHIO/RENDIMENTO:</h4>
<p style="margin: 0.2rem 0;">Rischio: <span style="color: #ef4444;">{rischio_pct}%</span> (fino allo Stop Loss) | Rendimento: <span style="color: #10b981;">+{targets_analisi['upside1']}%</span> (fino al Target 1)</p>
<p style="margin: 0.2rem 0;"><strong>Rapporto:</strong> 1:{rapporto_rr} ✅</p>
</div>
""", unsafe_allow_html=True)
if r.get('trigger_by_fabio'): st.success(f"**🟢 BY FABIO**: {r['motivo_by']}")
elif "BY" in r['segnale']: st.success(f"**Motivo**: {r['motivo_by']}")
elif "HOLD" in r['segnale']: st.warning(f"**Motivo**: {r['motivo_by']}")
else: st.error("**Motivo**: Titolo in Fase 4 o S-Score troppo basso")
st.markdown("---")
st.subheader("💰 Simulatore di Acquisto Intelligente")
col_sim1, col_sim2 = st.columns([2, 1])
with col_sim1: sim_ticker = st.text_input("Titolo da acquistare:", value=r['ticker'])
with col_sim2: sim_importo = st.number_input("Importo (€):", min_value=100, max_value=100000, value=200, step=100)
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
for item in scenari['hold_catalizzatore']: st.warning(item['messaggio'])
if scenari['vendita_gain']:
st.markdown("### ⚠️ Scenario 1: Vendita Titoli in Gain")
for item in scenari['vendita_gain']: st.warning(item['messaggio'])
if scenari['vendita_loss']:
st.markdown("### ✅ Scenario 2: Vendita Titoli in Loss/Kill Switch")
for item in scenari['vendita_loss']: st.success(item['messaggio'])
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
msg_parts = []
if hold_tickers: msg_parts.append(f"**NON VENDERE** {hold_tickers} (catalizzatore imminente).")
if loss_tickers: msg_parts.append(f"Valuta prima di vendere {loss_tickers} per ottimizzazione fiscale.")
st.warning(f"⚠️ {' '.join(msg_parts)} Se decidi di non vendere, procedi pure con la nuova liquidità.")
else:
st.info("Valuta attentamente le opzioni sopra prima di procedere.")
st.markdown("---")
st.markdown('<div class="signal-history-box"><div class="signal-history-title">📊 STORICO SEGNALI MATRIX</div></div>', unsafe_allow_html=True)
ultimo_segnale_check = get_ultimo_segnale(r['ticker'])
if not ultimo_segnale_check:
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
if var_pct_segnale >= 0: colore_var, testo_successo = "#10b981", "✅ Segnale vincente"
else: colore_var, testo_successo = "#ef4444", "❌ Segnale perdente"
elif ultimo_segnale['Tipo'] == 'BY_FABIO':
if var_pct_segnale >= 0: colore_var, testo_successo = "#10b981", "✅ Segnale BY FABIO vincente"
else: colore_var, testo_successo = "#ef4444", "❌ Segnale BY FABIO perdente"
else:
if var_pct_segnale <= 0: colore_var, testo_successo = "#10b981", "✅ Ha evitato perdita"
else: colore_var, testo_successo = "#f59e0b", "⚠️ Opportunità mancata"
data_fmt = formatta_data_europea(ultimo_segnale.get('Data', ''))
segno = "+" if var_pct_segnale > 0 else ""
st.markdown(f"""
<div style="background-color: #064e3b; padding: 1rem; border-radius: 8px; margin: 1rem 0;">
<div style="display: flex; justify-content: space-between; align-items: center;">
<div>
<strong>Ultimo segnale:</strong> {'🟢 BY FABIO' if ultimo_segnale['Tipo'] == 'BY_FABIO' else ('🟢 BY' if ultimo_segnale['Tipo'] == 'BY' else '🔴 SELL/EVITA')}<br>
<strong>Data:</strong> {data_fmt} ({giorni_trascorsi} giorni fa)<br>
<strong>Prezzo al segnale:</strong> ${prezzo_segnale:.2f}
</div>
<div style="text-align: right;">
<div style="font-size: 1.5rem; font-weight: bold; color: {colore_var};">{segno}{var_pct_segnale:.1f}%</div>
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
port_att = st.session_state.portafoglio or carica_json(PORTAFOGLIO_FILE) or []
st.session_state.grafico_prezzo_medio = next((p['Prezzo_Medio'] for p in port_att if p['Ticker'] == r['ticker']), None)
if st.session_state.get('grafico_ticker'):
st.markdown("---")
st.subheader(f"📊 {st.session_state.grafico_ticker}")
timeframe_options = {
"1GG (1 giorno, 15min)": {"period": "5d", "interval": "15m", "tf": "15m"},
"5GG (5 giorni, 1h)": {"period": "1mo", "interval": "1h", "tf": "1h"},
"1M (1 mese)": {"period": "1mo", "interval": "1d", "tf": "1M"},
"3M (3 mesi)": {"period": "3mo", "interval": "1d", "tf": "3M"},
"6M (6 mesi)": {"period": "6mo", "interval": "1d", "tf": "6M"},
"1A (1 anno)": {"period": "1y", "interval": "1d", "tf": "1A"},
"Da Inizio Anno": {"period": "ytd", "interval": "1d", "tf": "YTD"},
"1d (Daily)": {"period": "1y", "interval": "1d", "tf": "1d"},
"1wk (Weekly)": {"period": "2y", "interval": "1wk", "tf": "1wk"}
}
tf_choice = st.selectbox("Timeframe:", list(timeframe_options.keys()), index=7)
tf_config = timeframe_options[tf_choice]
fig = genera_grafico_baleine(st.session_state.grafico_ticker, tf_config['period'], 50, 200, prezzo_medio_eur=st.session_state.grafico_prezzo_medio, timeframe=tf_config['tf'], interval=tf_config['interval'], eurusd_rate=eurusd_rate)
if fig:
st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True})
else:
st.error("Impossibile generare il grafico")
if st.button("✖️ Chiudi grafico", use_container_width=True):
st.session_state.grafico_ticker = None
st.session_state.grafico_prezzo_medio = None
st.rerun()
with tab_registro:
st.subheader("📋 Registro Vendite & Fiscalità")
anni_disponibili = ["Tutti"] + [str(y) for y in range(2024, 2028)]
anno_corrente = str(datetime.now().year)
index_default = anni_disponibili.index(anno_corrente) if anno_corrente in anni_disponibili else 0
anno_filter = st.selectbox("📅 Filtra per anno:", anni_disponibili, index=index_default)
anno_val = None if anno_filter == "Tutti" else int(anno_filter)
liquidita_totale = calcola_liquidita_totale()
riepilogo = calcola_riepilogo_fiscale(None)
col_liq1, col_liq2, col_liq3, col_liq4 = st.columns(4)
with col_liq1: st.metric("💰 Liquidità Netta da Vendite", f"€ {liquidita_totale:,.2f}", help="Somma incassi netti (prezzo × qta - tasse) da tutte le vendite")
with col_liq2: st.metric("📈 P&L Realizzato Netto", f"€ {riepilogo['netto_reale']:+,.2f}", help="Utile netto dopo tasse e compensazione minusvalenze")
with col_liq3: st.metric("🏛️ Tasse Pagate Totali", f"€ {riepilogo['tasse_totali']:,.2f}", help="Totale tasse 26% pagate su plusvalenze")
with col_liq4: st.metric("📊 Pool Minusvalenze", f"€ {riepilogo['pool_minusvalenze']:,.2f}", help="Minusvalenze disponibili per compensazione futura")
st.markdown("---")
riepilogo = calcola_riepilogo_fiscale(anno_val)
col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
with col_f1: st.metric("💰 Gain Totale", f"€ {riepilogo['gain_totale']:+.2f}")
with col_f2: st.metric("📉 Loss Totale", f"€ {riepilogo['loss_totale']:+.2f}")
with col_f3: st.metric("🏛️ Tasse (26%)", f"€ {riepilogo['tasse_totali']:.2f}")
with col_f4: st.metric("✅ Netto Reale", f"€ {riepilogo['netto_reale']:+.2f}")
with col_f5: st.metric("📊 Pool Minusvalenze", f"€ {riepilogo['pool_minusvalenze']:.2f}")
st.caption(f"📊 {riepilogo['num_operazioni']} operazioni registrate" + (f" nel {anno_filter}" if anno_val else ""))
st.markdown("---")
registro = carica_json(REGISTRO_VENDITE_FILE)
if anno_val: registro = [v for v in registro if v.get('Data', '').startswith(str(anno_val))]
col_act1, col_act2, col_act3 = st.columns(3)
with col_act1:
st.markdown("**🗑️ Cancella Operazione (Testing)**")
if registro:
id_da_cancellare = st.selectbox("Seleziona ID", [v['id'] for v in registro])
if st.button("Elimina operazione"):
if elimina_operazione_vendita(id_da_cancellare):
st.success(f"✅ Operazione #{id_da_cancellare} eliminata")
st.rerun()
else: st.info("Nessuna operazione da eliminare")
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
else: st.info("Nessun dato da esportare")
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
return 'color: #10b981; font-weight: bold' if v > 0 else ('color: #ef4444; font-weight: bold' if v < 0 else '')
except: return ''
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
candidati_palantir = []
for i, ticker in enumerate(tutti_tickers):
progress_bar.progress((i + 1) / len(tutti_tickers))
try:
ticker_obj = yf.Ticker(ticker)
df = ticker_obj.history(period=period)
info = ticker_obj.info
if df.empty or len(df) < 200: continue
prezzo_eur, prezzo_usd, currency = get_prezzi_corretti(ticker_obj, eurusd_rate)
if prezzo_eur is None: continue
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
prezzo_attuale = df['Close'].iloc[-1]
distanza_sma200_pct = abs(prezzo_attuale - sma200) / sma200 * 100 if sma200 > 0 else 999
is_palantir = (s_score >= 75 and revenue_growth >= 0.20 and (peg_ratio > 0 and peg_ratio < 1.5) and rsi_oggi < 45 and distanza_sma200_pct <= 5.0)
if is_palantir:
candidati_palantir.append({'Ticker': ticker, 'Prezzo EUR': prezzo_eur, 'S-Score': s_score, 'RSI': round(rsi_oggi, 1), 'PEG': round(peg_ratio, 2) if peg_ratio > 0 else 'N/D', 'Rev Growth': f"{revenue_growth*100:.1f}%", 'Distanza SMA200': f"{distanza_sma200_pct:.1f}%"})
except: pass
progress_bar.empty()
if not candidati_palantir:
st.warning("⚠️ Nessun Setup Palantir trovato nella scansione estesa.")
else:
candidati_palantir.sort(key=lambda x: x['S-Score'], reverse=True)
top_3 = candidati_palantir[:3]
attivi_tickers = [p['Ticker'] for p in paper_port if p.get('Stato') == 'Attivo']
nuovi_trade = []
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
pnl_virtuali, ultimo_segnale_col = [], []
for idx, row in df_paper.iterrows():
ticker = row['Ticker']
if row['Stato'] == 'Attivo':
try:
current_price_usd = yf.Ticker(ticker).history(period='1d')['Close'].iloc[-1]
current_price_eur = current_price_usd / eurusd_rate
pnl_pct = ((current_price_eur - row['Entry']) / row['Entry']) * 100
pnl_virtuali.append(f"{pnl_pct:+.1f}%")
ultimo_segnale_display = format_ultimo_segnale_display(ticker, current_price_usd)
ultimo_segnale_col.append(ultimo_segnale_display)
except:
pnl_virtuali.append("N/D")
ultimo_segnale_col.append("N/D")
else:
pnl_virtuali.append("Chiuso")
ultimo_segnale_col.append("Chiuso")
df_paper['P&L Virtuale'] = pnl_virtuali
df_paper['Ultimo Segnale'] = ultimo_segnale_col
st.dataframe(df_paper[['Ticker', 'Entry', 'Stop_Loss', 'Target', 'Data_Ingresso', 'Stato', 'P&L Virtuale', 'Ultimo Segnale']], use_container_width=True, height=400)
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
salva_json(PAPER_TRADING_FILE, paper_port)
st.success(f"Posizione {ticker_da_chiudere} chiusa e archiviata.")
st.rerun()
else:
st.info("Nessuna posizione attiva da chiudere.")
else:
st.info("📭 Il portfolio sperimentale è vuoto. Usa il pulsante 'Scansione AI' per iniziare a tracciare i setup.")
