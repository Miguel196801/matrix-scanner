import json, os
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
import yfinance as yf

SHADOW_FILE = 'shadow_regia.json'
SKIP_FILE = 'skip_regia.json'

def _load_j(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return default
    return default

def _save_j(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_ticker_saltati_5gg():
    sk = _load_j(SKIP_FILE, {})
    oggi = datetime.now().strftime('%Y-%m-%d')
    return {k.upper() for k, v in sk.items() if str(v) >= oggi}

def salta_ticker_5gg(tk):
    sk = _load_j(SKIP_FILE, {})
    sk[tk.upper()] = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')
    _save_j(SKIP_FILE, sk)

@st.cache_data(ttl=900, show_spinner=False)
def _fetch_metriche_pro(tk, rate):
    t_obj = yf.Ticker(tk)
    h = t_obj.history(period='3mo', interval='1d')
    inf = t_obj.info if isinstance(t_obj.info, dict) else {}
    if h.empty or len(h) < 15:
        return None
    p_usd = float(h['Close'].dropna().iloc[-1])
    sma20 = float(h['Close'].rolling(20).mean().iloc[-1]) if len(h) >= 20 else p_usd * 0.95
    atr14 = float((h['High'] - h['Low']).tail(14).mean())
    sl_atr = p_usd - (2.0 * atr14)
    sl_sma = sma20 * 0.985
    candidati = [x for x in (sl_sma, sl_atr) if 0.895 * p_usd <= x <= 0.955 * p_usd]
    sl_usd = max(candidati) if candidati else max(p_usd * 0.895, min(p_usd * 0.955, sl_atr))
    rischio = max(0.01, p_usd - sl_usd)
    t1_usd = p_usd + (1.5 * rischio)
    t2_usd = p_usd + (2.5 * rischio)
    tgt_an = float(inf.get('targetMeanPrice') or 0)
    up_an = ((tgt_an - p_usd) / p_usd * 100.0) if (tgt_an > 0 and p_usd > 0) else None
    up_t2 = ((t2_usd - p_usd) / p_usd) * 100.0
    pot_reale = round(up_an if up_an is not None else up_t2, 1)
    sl_pct = round(((sl_usd - p_usd) / p_usd) * 100.0, 1)
    return {
        'sl_eur': round(sl_usd / rate, 2),
        'sl_pct': sl_pct,
        't1_eur': round(t1_usd / rate, 2),
        't1_pct': round(((t1_usd - p_usd) / p_usd) * 100.0, 1),
        't2_eur': round(t2_usd / rate, 2),
        't2_pct': round(up_t2, 1),
        'pot_reale': pot_reale,
        'has_analyst': up_an is not None
    }

def calcola_sl_tp_tecnico(tk, info, eurusd_rate):
    rate = float(eurusd_rate or 1.12)
    try:
        m = _fetch_metriche_pro(str(tk).strip().upper(), rate)
        if m:
            return m['sl_eur'], m['sl_pct'], m['t2_eur']
    except Exception:
        pass
    p_usd = float(info.get('Prezzo') or info.get('Close') or 0)
    return round((p_usd * 0.92) / rate, 2), -8.0, round((p_usd * 1.20) / rate, 2)

def render_tracker_regia(piano_ok, port_ok, eurusd_rate, taglia_ok):
    rate = float(eurusd_rate or 1.12)
    fin_oggi = [x for x in (piano_ok or []) if x[-1] <= 0]
    if fin_oggi:
        cols_sk = st.columns(min(4, len(fin_oggi)))
        for i_sk, item_sk in enumerate(fin_oggi):
            _, tk_sk, _, _, _, _, _, _ = item_sk
            if cols_sk[i_sk % len(cols_sk)].button(f'⏭️ Salta {tk_sk} (5 gg)', key=f'btn_skip_{tk_sk}', use_container_width=True):
                salta_ticker_5gg(tk_sk)
                st.rerun()

    with st.expander('📊 Statistiche & Tracker Regia Reale (Gain Netto Tasse)', expanded=True):
        sh_list = _load_j(SHADOW_FILE, [])
        # Allineamento automatico continuo con portafoglio reale (port_ok)
        port_map = {str(p.get('Ticker', '')).upper(): p for p in (port_ok or []) if float(p.get('Quantita', 0) or 0) > 0}
        sync_upd = False
        for ix_p, r_p in enumerate(sh_list):
            if r_p.get('Segnale') == '💼 PORTAFOGLIO REALE' and r_p.get('Stato') == 'Attivo':
                tk_p = str(r_p.get('Ticker', '')).upper()
                if tk_p not in port_map:
                    sh_list[ix_p]['Stato'] = 'Chiuso (Venduto Reale)'
                    sh_list[ix_p]['Esito_Reale'] = 'Venduto Reale'
                    sh_list[ix_p]['Avviso_SL'] = ''
                    sync_upd = True
                else:
                    q_reale = float(port_map[tk_p].get('Quantita', 0) or 0)
                    pmc_reale = round(float(port_map[tk_p].get('Prezzo_Medio', r_p.get('Entry', 0)) or 0), 2)
                    taglia_reale = round(q_reale * pmc_reale, 2)
                    if pmc_reale > 0 and (abs(pmc_reale - float(r_p.get('Entry', 0))) > 0.01 or abs(taglia_reale - float(r_p.get('Taglia_EUR', 0))) > 1.0):
                        sh_list[ix_p]['Entry'] = pmc_reale
                        sh_list[ix_p]['Taglia_EUR'] = taglia_reale
                        sync_upd = True
        if sync_upd:
            _save_j(SHADOW_FILE, sh_list)

        c1, c2, c3 = st.columns([1.8, 1.1, 1.1])
        c1.caption('Traccia metodo puro e portafoglio reale con Trailing Stop e avvisi per Trade Republic.')
        if c3.button('💼 Sync Portafoglio Reale', key='btn_sync_port_regia', use_container_width=True, disabled=not bool(port_map)):
            oggi_p = datetime.now().strftime('%Y-%m-%d')
            att_port = {str(x.get('Ticker', '')).upper() for x in sh_list if x.get('Segnale') == '💼 PORTAFOGLIO REALE' and x.get('Stato') == 'Attivo'}
            agg_p = 0
            for tk_m, pos_m in port_map.items():
                if tk_m in att_port:
                    continue
                q_m = float(pos_m.get('Quantita', 0) or 0)
                pmc_m = round(float(pos_m.get('Prezzo_Medio', 0) or 0), 2)
                if q_m <= 0 or pmc_m <= 0:
                    continue
                mp = _fetch_metriche_pro(tk_m, rate)
                sl_pct_m = abs(mp['sl_pct']) / 100.0 if mp else 0.08
                # Legge Prezzo_Attuale_EUR (chiave reale di portafoglio.json) con fallback legacy
                p_oggi_m = round(float(pos_m.get('Prezzo_Attuale_EUR') or pos_m.get('Prezzo_Attuale') or pmc_m), 2)
                if p_oggi_m > pmc_m * 1.03:
                    sl_e = round(max(pmc_m, p_oggi_m * 0.94), 2)
                    step_init = 2 if p_oggi_m >= pmc_m * (1.0 + 2.5 * sl_pct_m) else 1
                else:
                    sl_e = round(pmc_m * (1.0 - sl_pct_m), 2)
                    step_init = 0
                t1_e = round(pmc_m * (1.0 + 1.5 * sl_pct_m), 2)
                t2_e = round(pmc_m * (1.0 + 2.5 * sl_pct_m), 2)
                sh_list.append({
                    'Ticker': tk_m, 'Segnale': '💼 PORTAFOGLIO REALE', 'Taglia_EUR': round(q_m * pmc_m, 2),
                    'Entry': pmc_m, 'Stop_Loss': sl_e, 'T1': t1_e, 'Target': t2_e,
                    'Max_Price': max(pmc_m, p_oggi_m), 'Step_Trailing': step_init, 'Avviso_SL': '',
                    'Data_Ingresso': str(pos_m.get('Data_Acquisto') or oggi_p)[:10],
                    'Fonti': 'Portafoglio Reale', 'Stato': 'Attivo', 'Esito_Reale': 'In Portafoglio'
                })
                agg_p += 1
            if agg_p > 0:
                _save_j(SHADOW_FILE, sh_list)
                st.success(f'✅ Importati {agg_p} titoli del Portafoglio Reale nel Tracker!')
                st.rerun()
            else:
                st.info('ℹ️ Tutti i titoli del Portafoglio Reale sono già sincronizzati.')
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
                        p_eur = round(float(h1['Close'].dropna().iloc[-1]) / rate, 2)
                        mp = _fetch_metriche_pro(tk_s, rate)
                        sl_e = mp['sl_eur'] if mp else round(p_eur * 0.92, 2)
                        t1_e = mp['t1_eur'] if mp else round(p_eur * 1.12, 2)
                        t2_e = mp['t2_eur'] if mp else round(p_eur * 1.20, 2)
                        sh_list.append({
                            'Ticker': tk_s, 'Segnale': tp_s, 'Taglia_EUR': round(float(taglia_ok), 2),
                            'Entry': p_eur, 'Stop_Loss': sl_e, 'T1': t1_e, 'Target': t2_e,
                            'Max_Price': p_eur, 'Step_Trailing': 0, 'Avviso_SL': '',
                            'Data_Ingresso': oggi_sh, 'Fonti': ' + '.join([f.replace('**', '') for f in fn_s]),
                            'Stato': 'Attivo', 'Esito_Reale': 'In Attesa'
                        })
                        agg += 1
                except Exception:
                    pass
            if agg > 0:
                _save_j(SHADOW_FILE, sh_list)
                st.success(f'✅ Registrati {agg} ordini nel Tracker!')
                st.rerun()

        if sh_list:
            filtro_vista = st.radio(
                'Filtro Statistiche & Vista:',
                ['📊 Tutte le Operazioni', '🤖 Solo Metodo Sistema', '💼 Solo Portafoglio Reale'],
                horizontal=True,
                key='radio_filtro_tracker_regia'
            )
            upd, pnls, netti, rows, da_gestire, avvisi_sl = False, [], [], [], [], []
            for idx_s, r in enumerate(sh_list):
                tk_r, st_r = str(r.get('Ticker', '')).upper(), str(r.get('Stato', 'Attivo'))
                en_r = float(r.get('Entry', 0) or 0)
                sl_r = float(r.get('Stop_Loss', 0) or 0)
                t1_r = float(r.get('T1', 0) or round(en_r * 1.12, 2))
                tg_r = float(r.get('Target', 0) or 0)
                mx_r = float(r.get('Max_Price', en_r) or en_r)
                step_tr = int(r.get('Step_Trailing', 0) or 0)
                tg_e, dt_r, p_cur = float(r.get('Taglia_EUR', 200.0) or 200.0), str(r.get('Data_Ingresso', ''))[:10], en_r
                if st_r == 'Attivo' and tk_r and en_r > 0:
                    try:
                        hr = yf.Ticker(tk_r).history(period='6mo', interval='1d')
                        if not hr.empty:
                            p_cur = round(float(hr['Close'].dropna().iloc[-1]) / rate, 2)
                            sr = hr[hr.index.strftime('%Y-%m-%d') >= dt_r] if dt_r else hr.tail(1)
                            lo = float(sr['Low'].min()) / rate if not sr.empty else p_cur
                            hi = float(sr['High'].max()) / rate if not sr.empty else p_cur
                            if hi > mx_r:
                                mx_r = round(hi, 2)
                                sh_list[idx_s]['Max_Price'] = mx_r
                                upd = True
                            if step_tr < 1 and t1_r > 0 and hi >= t1_r and sl_r < en_r:
                                sl_r = round(en_r, 2)
                                sh_list[idx_s]['Stop_Loss'] = sl_r
                                sh_list[idx_s]['Step_Trailing'] = 1
                                sh_list[idx_s]['Avviso_SL'] = f"🛡️ {tk_r}: T1 (€ {t1_r:.2f}) raggiunto! Sposta SL a PAREGGIO (€ {sl_r:.2f}) su Trade Republic."
                                upd = True
                            if tg_r > 0 and hi >= tg_r:
                                nuovo_sl = round(max(t1_r, mx_r * 0.94), 2)
                                if nuovo_sl > sl_r:
                                    sl_r = nuovo_sl
                                    sh_list[idx_s]['Stop_Loss'] = sl_r
                                    sh_list[idx_s]['Step_Trailing'] = 2
                                    sh_list[idx_s]['Avviso_SL'] = f"🚀 {tk_r}: T2 superato (Max € {mx_r:.2f})! Alza Trailing SL a € {sl_r:.2f} su Trade Republic."
                                    upd = True
                            if sl_r > 0 and lo <= sl_r:
                                st_r = 'Chiuso (Trailing)' if step_tr >= 1 else 'Chiuso (SL)'
                                p_cur, upd = sl_r, True
                                sh_list[idx_s]['Stato'], sh_list[idx_s]['Prezzo_Uscita'], sh_list[idx_s]['Esito_Reale'] = st_r, sl_r, 'Da Gestire'
                                sh_list[idx_s]['Avviso_SL'] = ''
                    except Exception:
                        pass
                else:
                    p_cur = float(r.get('Prezzo_Uscita') or en_r)

                is_port_reale = (str(r.get('Segnale', '')) == '💼 PORTAFOGLIO REALE')
                if filtro_vista == '🤖 Solo Metodo Sistema' and is_port_reale:
                    continue
                if filtro_vista == '💼 Solo Portafoglio Reale' and not is_port_reale:
                    continue

                if st_r == 'Attivo' and str(r.get('Avviso_SL', '')).strip():
                    avvisi_sl.append((idx_s, tk_r, str(r.get('Avviso_SL'))))
                pct = ((p_cur - en_r) / en_r) * 100 if en_r > 0 else 0.0
                lordo = tg_e * (pct / 100.0)
                netto = round(lordo - max(0.0, lordo * 0.26), 2)
                pnls.append(pct); netti.append(netto)
                if st_r != 'Attivo' and str(r.get('Esito_Reale', 'Da Gestire')) == 'Da Gestire':
                    da_gestire.append((idx_s, tk_r, st_r, p_cur, pct, netto))
                rows.append({
                    'Data': dt_r, 'Ticker': tk_r, 'Segnale': r.get('Segnale', ''),
                    'Entry €': en_r, 'SL €': sl_r, 'T1 €': t1_r, 'T2 €': tg_r, 'Attuale €': p_cur,
                    'Stato': st_r, 'Reale': r.get('Esito_Reale', 'In Attesa'),
                    'P&L %': f'{pct:+.1f}%', 'Netto €': f'€ {netto:+.2f}'
                })

            if upd:
                _save_j(SHADOW_FILE, sh_list)

            if rows:
                if avvisi_sl:
                    for ix_a, tk_a, msg_a in avvisi_sl:
                        ca1, ca2 = st.columns([3.5, 1])
                        ca1.info(msg_a)
                        if ca2.button('✅ SL Aggiornato', key=f'btn_ack_sl_{ix_a}_{tk_a}', use_container_width=True):
                            sh_list[ix_a]['Avviso_SL'] = ''; _save_j(SHADOW_FILE, sh_list); st.rerun()
                if da_gestire:
                    st.warning('🔔 **Chiusure Automatiche del Sistema (Trailing / SL) da confermare nel reale:**')
                    for ix_g, tk_g, st_g, pr_g, pc_g, nt_g in da_gestire:
                        cg1, cg2, cg3 = st.columns([2.5, 1, 1])
                        cg1.markdown(f'**{tk_g}** — {st_g} @ **€ {pr_g:.2f}** ({pc_g:+.1f}% | Netto **€ {nt_g:+.2f}**)')
                        if cg2.button('✅ Replicata', key=f'btn_rep_{ix_g}_{tk_g}', use_container_width=True):
                            sh_list[ix_g]['Esito_Reale'] = 'Replicata'; _save_j(SHADOW_FILE, sh_list); st.rerun()
                        if cg3.button('⏭️ Tengo/Ignora', key=f'btn_ign_{ix_g}_{tk_g}', use_container_width=True):
                            sh_list[ix_g]['Esito_Reale'] = 'Ignorata (Tengo)'
                            if sh_list[ix_g].get('Segnale') == '💼 PORTAFOGLIO REALE':
                                sh_list[ix_g]['Stato'] = 'Attivo'
                                sh_list[ix_g]['Stop_Loss'] = round(pr_g * 0.90, 2)
                                sh_list[ix_g]['Data_Ingresso'] = datetime.now().strftime('%Y-%m-%d')
                                sh_list[ix_g].pop('Prezzo_Uscita', None)
                            _save_j(SHADOW_FILE, sh_list); st.rerun()
                w = sum(1 for x in pnls if x > 0)
                n_op = len(pnls)
                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric('🎯 Win Rate Metodo', f'{(w/n_op)*100:.0f}%', f'{w} su {n_op}')
                k2.metric('📊 Rendimento Medio', f'{sum(pnls)/n_op:+.2f}%', 'Per trade')
                k3.metric('📈 P&L Cumulato', f'{sum(pnls):+.1f}%', 'Somma %')
                k4.metric('💶 Gain Netto (26%)', f'€ {sum(netti):+,.2f}', 'Netto tasse')
                k5.metric('📁 Operazioni', f'{len(rows)}', f"{sum(1 for x in rows if x['Stato']=='Attivo')} attive")
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.info('📭 Nessuna operazione presente per questo filtro.')
        else:
            st.info('📭 Nessuna operazione registrata. Clicca Registra Piano di Oggi per iniziare.')


def render_stella_watchlist(tk, key_suffix="main"):
    tk_u = str(tk or "").strip().upper()
    if not tk_u:
        return
    imp_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "impostazioni.json")
    imp = _load_j(imp_file, {})
    if not isinstance(imp, dict):
        imp = {}
    # Usa sempre lista_ticker_default come Watchlist principale dello Scanner (con fallback alle chiavi legacy)
    raw_str = str(imp.get("lista_ticker_default", "") or st.session_state.get("tickers_input", "") or imp.get("tickers", "") or imp.get("watchlist", "") or "")
    lista_tk = []
    for x in raw_str.replace("\n", ",").split(","):
        t_clean = x.strip().upper()
        if t_clean and t_clean not in lista_tk:
            lista_tk.append(t_clean)
    presente = tk_u in lista_tk
    lbl = "⭐ In Watchlist" if presente else "☆ Aggiungi a Watchlist"
    tip = "Clicca per rimuovere dalla Watchlist dello Scanner" if presente else "Clicca per aggiungere alla Watchlist dello Scanner"
    if st.button(lbl, key=f"star_wl_{tk_u}_{key_suffix}", help=tip, use_container_width=True):
        if presente:
            lista_tk = [x for x in lista_tk if x != tk_u]
        else:
            lista_tk.append(tk_u)
        nuova_str = ", ".join(lista_tk)
        imp["lista_ticker_default"] = nuova_str
        # Mantiene allineate anche le chiavi secondarie rimuovendo eventuali residui se tolto
        for k_legacy in ("tickers", "watchlist"):
            if k_legacy in imp and isinstance(imp[k_legacy], str):
                leg_l = [x.strip().upper() for x in imp[k_legacy].replace("\n", ",").split(",") if x.strip()]
                if presente:
                    leg_l = [x for x in leg_l if x != tk_u]
                elif tk_u not in leg_l:
                    leg_l.append(tk_u)
                imp[k_legacy] = ", ".join(leg_l)
        _save_j(imp_file, imp)
        # Aggiorna il widget sidebar al prossimo rerun senza conflitto StreamlitAPIException
        st.session_state["_pending_tickers_input"] = nuova_str
        for k_ss in ("watchlist_input", "custom_tickers"):
            if k_ss in st.session_state:
                st.session_state[k_ss] = nuova_str
        st.rerun()


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_indici_usa():
    specs = [("S&P 500", "^GSPC"), ("Dow 30", "^DJI"), ("Nasdaq", "^IXIC")]
    out = []
    for nome, sym in specs:
        try:
            t = yf.Ticker(sym)
            h5 = t.history(period="5d", interval="1d")
            prev_c = float(h5["Close"].dropna().iloc[-2]) if len(h5["Close"].dropna()) >= 2 else 0.0
            h1 = t.history(period="1d", interval="15m")
            closes = [float(x) for x in h1["Close"].dropna().tolist()] if not h1.empty else []
            if not closes and not h5.empty:
                closes = [float(h5["Close"].dropna().iloc[-1])]
            if closes:
                cur = closes[-1]
                if prev_c <= 0:
                    prev_c = closes[0]
                diff = cur - prev_c
                pct = (diff / prev_c) * 100.0 if prev_c > 0 else 0.0
                out.append({"nome": nome, "val": cur, "diff": diff, "pct": pct, "pts": closes[-25:]})
        except Exception:
            pass
    return out

def render_barra_indici_usa():
    dati = _fetch_indici_usa()
    if not dati:
        return
    cards = []
    for d in dati:
        pos = d["diff"] >= 0
        col = "#22c55e" if pos else "#ef4444"
        fill = "rgba(34,197,94,0.16)" if pos else "rgba(239,68,68,0.16)"
        pts = d["pts"]
        svg = ""
        if len(pts) >= 2:
            mn, mx = min(pts), max(pts)
            rng = (mx - mn) if mx != mn else 1.0
            w, h = 84, 28
            coords = [f"{(i/(len(pts)-1))*w:.1f},{h - 3 - ((v-mn)/rng)*(h-6):.1f}" for i, v in enumerate(pts)]
            poly = " ".join(coords)
            area = f"0,{h} " + poly + f" {w},{h}"
            lx, ly = coords[-1].split(",")
            svg = f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}"><polygon points="{area}" fill="{fill}"/><polyline fill="none" stroke="{col}" stroke-width="1.6" points="{poly}"/><circle cx="{lx}" cy="{ly}" r="2.3" fill="{col}"/></svg>'
        cards.append(
            f'<div style="flex:1;min-width:210px;background:rgba(15,23,42,0.75);border:1px solid rgba(148,163,184,0.18);border-radius:8px;padding:7px 12px;display:flex;justify-content:space-between;align-items:center;">'
            f'<div><div style="color:#60a5fa;font-size:0.80rem;font-weight:700;">{d["nome"]}</div>'
            f'<div style="color:#f8fafc;font-size:1.02rem;font-weight:700;line-height:1.2;">{d["val"]:,.2f}</div>'
            f'<div style="color:{col};font-size:0.78rem;font-weight:600;">{d["diff"]:+,.2f} ({d["pct"]:+.2f}%)</div></div>'
            f'<div>{svg}</div></div>'
        )
    st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:0.65rem;">{"".join(cards)}</div>', unsafe_allow_html=True)

_NOMI_USA = {'AAPL': 'Apple', 'MSFT': 'Microsoft', 'NVDA': 'NVIDIA', 'GOOGL': 'Alphabet', 'GOOG': 'Alphabet', 'AMZN': 'Amazon', 'META': 'Meta Platforms', 'TSLA': 'Tesla', 'AVGO': 'Broadcom', 'ORCL': 'Oracle', 'CRM': 'Salesforce', 'AMD': 'AMD', 'NFLX': 'Netflix', 'ADBE': 'Adobe', 'QCOM': 'Qualcomm', 'INTC': 'Intel', 'MU': 'Micron', 'AMAT': 'Applied Materials', 'LRCX': 'Lam Research', 'KLAC': 'KLA Corp', 'PANW': 'Palo Alto Net', 'CRWD': 'CrowdStrike', 'FTNT': 'Fortinet', 'SNOW': 'Snowflake', 'PLTR': 'Palantir', 'SHOP': 'Shopify', 'UBER': 'Uber', 'ABNB': 'Airbnb', 'COIN': 'Coinbase', 'SQ': 'Block', 'PYPL': 'PayPal', 'SOFI': 'SoFi Tech', 'HOOD': 'Robinhood', 'AFRM': 'Affirm', 'UPST': 'Upstart', 'JPM': 'JPMorgan', 'BAC': 'Bank of America', 'WFC': 'Wells Fargo', 'GS': 'Goldman Sachs', 'MS': 'Morgan Stanley', 'V': 'Visa', 'MA': 'Mastercard', 'AXP': 'American Express', 'BLK': 'BlackRock', 'SCHW': 'Charles Schwab', 'UNH': 'UnitedHealth', 'LLY': 'Eli Lilly', 'JNJ': 'Johnson & Johnson', 'ABBV': 'AbbVie', 'MRK': 'Merck', 'PFE': 'Pfizer', 'TMO': 'Thermo Fisher', 'ABT': 'Abbott', 'AMGN': 'Amgen', 'GILD': 'Gilead', 'WMT': 'Walmart', 'COST': 'Costco', 'HD': 'Home Depot', 'LOW': "Lowe's", 'TGT': 'Target', 'NKE': 'Nike', 'SBUX': 'Starbucks', 'MCD': "McDonald's", 'KO': 'Coca-Cola', 'PEP': 'PepsiCo', 'PG': 'Procter & Gamble', 'DIS': 'Disney', 'CMCSA': 'Comcast', 'T': 'AT&T', 'VZ': 'Verizon', 'XOM': 'Exxon Mobil', 'CVX': 'Chevron', 'COP': 'ConocoPhillips', 'SLB': 'Schlumberger', 'OXY': 'Occidental', 'CAT': 'Caterpillar', 'DE': 'Deere & Co', 'BA': 'Boeing', 'GE': 'GE Aerospace', 'HON': 'Honeywell', 'LMT': 'Lockheed Martin', 'RTX': 'RTX Corp', 'NOC': 'Northrop Grumman', 'GD': 'General Dynamics', 'UPS': 'UPS', 'O': 'Realty Income', 'AMT': 'American Tower', 'PLD': 'Prologis', 'EQIX': 'Equinix', 'SPG': 'Simon Property', 'APP': 'AppLovin', 'TTWO': 'Take-Two', 'TTD': 'The Trade Desk', 'VRT': 'Vertiv', 'SMCI': 'Super Micro', 'APLD': 'Applied Digital', 'ONDS': 'Ondas Holdings', 'ARM': 'Arm Holdings', 'ASML': 'ASML', 'TSM': 'TSMC', 'DELL': 'Dell Tech', 'HPE': 'Hewlett Packard', 'IBM': 'IBM', 'CSCO': 'Cisco', 'ANET': 'Arista Networks'}

def render_check_3_regole(tickers_list, eurusd_rate=1.08, solo_fase2=False, min_score=0, solo_pre_ign=False):
    tks = []
    for x in (tickers_list or []):
        t_c = str(x).strip().upper()
        if t_c and t_c not in tks:
            tks.append(t_c)
    if not tks:
        st.info("Inserisci almeno un ticker valido per avviare il controllo.")
        return
    righe = []
    with st.spinner(f"Verifica 3 Regole in corso su {len(tks)} titoli..."):
        for tk in tks:
            # Inizializza subito _tk_full prima del blocco try/except per evitare UnboundLocalError
            _nome_init = _NOMI_USA.get(tk, '')
            _tk_full = f'{_nome_init} ({tk})' if _nome_init else tk
            try:
                t_obj = yf.Ticker(tk)
                h = t_obj.history(period="1y", interval="1d")
                if h.empty or len(h) < 50:
                    if (solo_fase2 and solo_fase2 != 'Tutte le Fasi') or solo_pre_ign or min_score > 0:
                        continue
                    righe.append({"Titolo": _tk_full, "Motore": "Tutti", "Esito": "❌", "Dettaglio Criteri (✅ Passa | ❌ Manca)": "❌ Dati storici insufficienti (<50 barre)"})
                    continue
                c = h["Close"].dropna()
                o = h["Open"].dropna()
                v = h["Volume"].dropna()
                p_cur = float(c.iloc[-1])
                p_open = float(o.iloc[-1])
                p_prev = float(c.iloc[-2]) if len(c) >= 2 else p_cur
                var_pct = ((p_cur - p_prev) / p_prev * 100.0) if p_prev > 0 else 0.0

                sma20 = float(c.tail(20).mean())
                sma50 = float(c.tail(50).mean())
                sma200 = float(c.tail(200).mean()) if len(c) >= 200 else sma50
                sma200_prev = float(c.iloc[-21:-1].tail(200).mean()) if len(c) >= 200 else sma200

                if p_cur > sma200 and sma200 >= sma200_prev:
                    fase = 2
                elif p_cur < sma200 and sma200 <= sma200_prev:
                    fase = 4
                elif p_cur > sma200:
                    fase = 3
                else:
                    fase = 1

                delta = c.diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain.iloc[-1] / loss.iloc[-1] if float(loss.iloc[-1]) > 0 else 100.0
                rsi = float(100.0 - (100.0 / (1.0 + rs)))

                vol_med = float(v.iloc[-21:-1].mean()) if len(v) >= 21 else float(v.mean())
                vol_rel = float(v.iloc[-1]) / vol_med if vol_med > 0 else 1.0

                h60 = h.tail(60)
                vpoc = float(h60.loc[h60["Volume"].idxmax(), "Close"]) if not h60.empty else sma20

                mp = _fetch_metriche_pro(tk, eurusd_rate)
                pot = float(mp["pot_reale"]) if mp else 0.0

                c_f2 = (fase == 2)
                c_verde = (p_cur > p_open)
                c_sma20 = (p_cur > sma20)
                c_vpoc = (p_cur > vpoc)
                c_vol_ign = (vol_rel >= 1.35)
                c_vol_fab = (vol_rel >= 1.10)
                c_rsi_ign = (45.0 <= rsi <= 63.0)
                c_rsi_fab = (45.0 <= rsi <= 68.0)
                c_rsi_std = (rsi < 70.0)
                c_pot = (pot >= 10.0)

                ok_ign = all([c_f2, c_verde, c_sma20, c_vpoc, c_vol_ign, c_rsi_ign, c_pot])
                ok_fab = all([c_f2, c_verde, c_sma20, c_vpoc, c_vol_fab, c_rsi_fab, c_pot])
                ok_std = all([c_f2, c_sma20, c_rsi_std, c_pot])

                det_ign = " | ".join([
                    f"{'✅' if c_f2 else '❌'} Fase {fase} (req. F2)",
                    f"{'✅' if c_verde else '❌'} Candela {'Verde' if c_verde else 'Rossa'}",
                    f"{'✅' if c_sma20 else '❌'} Prezzo > SMA20",
                    f"{'✅' if c_vpoc else '❌'} Prezzo > VPOC",
                    f"{'✅' if c_vol_ign else '❌'} Volumi {vol_rel:.1f}x (≥1.35)",
                    f"{'✅' if c_rsi_ign else '❌'} RSI {rsi:.0f} (45-63)",
                    f"{'✅' if c_pot else '❌'} Potenziale {pot:+.1f}% (≥10%)"
                ])
                det_fab = " | ".join([
                    f"{'✅' if c_f2 else '❌'} Fase {fase} (req. F2)",
                    f"{'✅' if c_verde else '❌'} Candela {'Verde' if c_verde else 'Rossa'}",
                    f"{'✅' if c_sma20 else '❌'} Prezzo > SMA20",
                    f"{'✅' if c_vpoc else '❌'} Prezzo > VPOC",
                    f"{'✅' if c_vol_fab else '❌'} Volumi {vol_rel:.1f}x (≥1.10)",
                    f"{'✅' if c_rsi_fab else '❌'} RSI {rsi:.0f} (45-68)",
                    f"{'✅' if c_pot else '❌'} Potenziale {pot:+.1f}% (≥10%)"
                ])
                det_std = " | ".join([
                    f"{'✅' if c_f2 else '❌'} Fase {fase} (req. F2)",
                    f"{'✅' if c_sma20 else '❌'} Prezzo > SMA20",
                    f"{'✅' if c_rsi_std else '❌'} RSI {rsi:.0f} (<70)",
                    f"{'✅' if c_pot else '❌'} Potenziale {pot:+.1f}% (≥10%)"
                ])

                s_score = 0
                if c_f2: s_score += 30
                elif fase in (1, 3): s_score += 15
                if p_cur > sma50: s_score += 20
                if c_sma20: s_score += 15
                if c_vpoc: s_score += 15
                if 45.0 <= rsi <= 68.0: s_score += 10
                if c_pot: s_score += 10
                is_pre_ign = (fase in (1, 2)) and (p_cur >= sma20 * 0.94) and (40.0 <= rsi <= 68.0) and (not ok_ign)
                if solo_fase2 == '✅ Solo Fase 2 (Rialzo)' and not c_f2:
                    continue
                if solo_fase2 == '🧱 Solo Fase 1 (Accumulo)' and fase != 1:
                    continue
                if solo_fase2 is True and not c_f2:
                    continue
                if solo_pre_ign and not is_pre_ign:
                    continue
                if s_score < min_score:
                    continue
                pre_tag = " | ⏳ PRE-IGNITION" if is_pre_ign else ""
                _nome_az = _NOMI_USA.get(tk, '')
                if not _nome_az:
                    try:
                        _inf = t_obj.info or {}
                        _nome_az = str(_inf.get('shortName') or _inf.get('longName') or '').strip()[:24]
                    except Exception:
                        pass
                _tk_full = f'{_nome_az} ({tk})' if _nome_az else tk
                hdr_tk = f'{_tk_full} — Score {s_score}{pre_tag} | ${p_cur:.2f} ({var_pct:+.1f}%)'
                righe.append({"Titolo": hdr_tk, "Motore": "🚀 IGNITION", "Esito": "✅ PASSA" if ok_ign else "❌ NO", "Dettaglio Criteri (✅ Passa | ❌ Manca)": det_ign})
                righe.append({"Titolo": _tk_full, "Motore": "🟢 BY FABIO", "Esito": "✅ PASSA" if ok_fab else "❌ NO", "Dettaglio Criteri (✅ Passa | ❌ Manca)": det_fab})
                righe.append({"Titolo": _tk_full, "Motore": "🔵 BY Standard", "Esito": "✅ PASSA" if ok_std else "❌ NO", "Dettaglio Criteri (✅ Passa | ❌ Manca)": det_std})
            except Exception as ex:
                righe.append({"Titolo": _tk_full, "Motore": "Errore", "Esito": "❌", "Dettaglio Criteri (✅ Passa | ❌ Manca)": str(ex)[:50]})
    if not righe:
        _f_attivi = [str(solo_fase2)] if (solo_fase2 and solo_fase2 != 'Tutte le Fasi') else []
        if solo_pre_ign:
            _f_attivi.append('⏳ Solo PRE-IGNITION')
        if min_score > 0:
            _f_attivi.append(f'🎯 S-Score ≥ {min_score}')
        _lbl_f = ' | '.join(_f_attivi) if _f_attivi else 'Tutti i titoli'
        st.info(f'ℹ️ Nessun titolo tra i {len(tks)} analizzati soddisfa i filtri selezionati ({_lbl_f}).')
        return
    st.dataframe(
        pd.DataFrame(righe),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Titolo": st.column_config.TextColumn("Titolo", width="large"),
            "Motore": st.column_config.TextColumn("Motore", width="small"),
            "Esito": st.column_config.TextColumn("Esito", width="small"),
            "Dettaglio Criteri (✅ Passa | ❌ Manca)": st.column_config.TextColumn("Dettaglio Criteri (✅ Passa | ❌ Manca)", width="large"),
        },
    )
