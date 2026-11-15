import json, os
from datetime import datetime
import pandas as pd
import streamlit as st
import yfinance as yf

SHADOW_FILE = 'shadow_regia.json'

def carica_shadow():
    if os.path.exists(SHADOW_FILE):
        try:
            with open(SHADOW_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
                return d if isinstance(d, list) else []
        except Exception:
            return []
    return []

def salva_shadow(data):
    with open(SHADOW_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_ticker_attivi_shadow():
    return {str(x.get('Ticker', '')).strip().upper() for x in carica_shadow() if str(x.get('Stato', '')) == 'Attivo'}

def render_tracker_regia(piano_ok, port_ok, eurusd_rate, taglia_ok):
    with st.expander('📊 Statistiche & Tracker Regia Reale (Gain Netto Tasse)', expanded=True):
        sh_list = carica_shadow()
        fin_oggi = [x for x in (piano_ok or []) if x[-1] <= 0]
        c1, c2 = st.columns([2.2, 1])
        c1.caption('Traccia la performance reale al netto del 26% di tasse degli ordini finanziati dalla Regia.')
        if c2.button('📥 Registra Piano di Oggi', key='btn_reg_shadow_regia', use_container_width=True, disabled=not bool(fin_oggi)):
            oggi_sh = datetime.now().strftime('%Y-%m-%d')
            att_sh = {(x.get('Ticker'), x.get('Data_Ingresso')) for x in sh_list}
            agg = 0
            for item in fin_oggi:
                _, tk_s, tp_s, _, _, _, fn_s, _ = item
                if (tk_s, oggi_sh) in att_sh:
                    continue
                try:
                    h1 = yf.Ticker(tk_s).history(period='2d')
                    if not h1.empty:
                        p_eur = round(float(h1['Close'].dropna().iloc[-1]) / float(eurusd_rate or 1.12), 2)
                        sh_list.append({'Ticker': tk_s, 'Segnale': tp_s, 'Taglia_EUR': round(float(taglia_ok), 2), 'Entry': p_eur, 'Stop_Loss': round(p_eur * 0.92, 2), 'Target': round(p_eur * 1.20, 2), 'Data_Ingresso': oggi_sh, 'Fonti': ' + '.join([f.replace('**', '') for f in fn_s]), 'Stato': 'Attivo'})
                        agg += 1
                except Exception:
                    pass
            if agg > 0:
                salva_shadow(sh_list); st.success(f'✅ Registrati {agg} ordini!'); st.rerun()
        if sh_list:
            upd, pnls, netti, rows = False, [], [], []
            for idx_s, r in enumerate(sh_list):
                tk_r, st_r = str(r.get('Ticker', '')).upper(), str(r.get('Stato', 'Attivo'))
                en_r, sl_r, tg_r = float(r.get('Entry', 0) or 0), float(r.get('Stop_Loss', 0) or 0), float(r.get('Target', 0) or 0)
                tg_e, dt_r, p_cur = float(r.get('Taglia_EUR', 200.0) or 200.0), str(r.get('Data_Ingresso', ''))[:10], en_r
                if st_r == 'Attivo' and tk_r and en_r > 0:
                    try:
                        hr = yf.Ticker(tk_r).history(period='6mo', interval='1d')
                        if not hr.empty:
                            p_cur = round(float(hr['Close'].dropna().iloc[-1]) / float(eurusd_rate or 1.12), 2)
                            sr = hr[hr.index.strftime('%Y-%m-%d') >= dt_r] if dt_r else hr.tail(1)
                            lo = float(sr['Low'].min()) / float(eurusd_rate or 1.12) if not sr.empty else p_cur
                            hi = float(sr['High'].max()) / float(eurusd_rate or 1.12) if not sr.empty else p_cur
                            if sl_r > 0 and lo <= sl_r:
                                st_r, p_cur, upd = 'Chiuso (SL)', sl_r, True
                                sh_list[idx_s]['Stato'], sh_list[idx_s]['Prezzo_Uscita'] = st_r, sl_r
                            elif tg_r > 0 and hi >= tg_r:
                                st_r, p_cur, upd = 'Chiuso (TP)', tg_r, True
                                sh_list[idx_s]['Stato'], sh_list[idx_s]['Prezzo_Uscita'] = st_r, tg_r
                    except Exception:
                        pass
                else:
                    p_cur = float(r.get('Prezzo_Uscita') or en_r)
                pct = ((p_cur - en_r) / en_r) * 100 if en_r > 0 else 0.0
                lordo = tg_e * (pct / 100.0)
                netto = round(lordo - max(0.0, lordo * 0.26), 2)
                pnls.append(pct); netti.append(netto)
                rows.append({'Data': dt_r, 'Ticker': tk_r, 'Segnale': r.get('Segnale', ''), 'Taglia €': f'€ {tg_e:.0f}', 'Entry €': en_r, 'Attuale €': p_cur, 'Stato': st_r, 'P&L %': f'{pct:+.1f}%', 'Netto Tasse €': f'€ {netto:+.2f}', 'Fonti': r.get('Fonti', '')})
            if upd: salva_shadow(sh_list)
            w = sum(1 for x in pnls if x > 0)
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric('🎯 Win Rate Regia', f'{(w/len(pnls))*100:.0f}%', f'{w} su {len(pnls)}')
            k2.metric('📊 Rendimento Medio', f'{sum(pnls)/len(pnls):+.2f}%', 'Per trade')
            k3.metric('📈 P&L Cumulato', f'{sum(pnls):+.1f}%', 'Somma %')
            k4.metric('💶 Gain Netto (26%)', f'€ {sum(netti):+,.2f}', 'Netto tasse')
            k5.metric('📁 Operazioni', f'{len(rows)}', f"{sum(1 for x in rows if x['Stato']=='Attivo')} attive")
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info('📭 Nessuna operazione registrata. Clicca Registra Piano di Oggi per iniziare.')
