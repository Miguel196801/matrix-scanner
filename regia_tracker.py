import json, os
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
import yfinance as yf

SHADOW_FILE = 'shadow_regia.json'
SKIP_FILE = 'skip_regia.json'

def _risolvi_file_utente(path):
    """Risolve dinamicamente il file JSON in base all'utente autenticato in st.session_state."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    bname = os.path.basename(str(path))
    target_name = bname
    try:
        if bname == SHADOW_FILE:
            target_name = st.session_state.get('_regia_tracker_file') or SHADOW_FILE
        elif bname == SKIP_FILE:
            target_name = st.session_state.get('_skip_regia_file') or SKIP_FILE
        elif bname == 'impostazioni.json':
            target_name = st.session_state.get('_impostazioni_file') or 'impostazioni.json'
    except Exception:
        target_name = bname
    return os.path.join(base_dir, target_name), target_name

def _load_j(path, default):
    abs_fp, fname = _risolvi_file_utente(path)
    is_locale_pc = (os.name == 'nt')
    esiste_loc = os.path.exists(abs_fp)
    # Su Streamlit Cloud (o se manca su disco) prova a scaricare da GitHub il file dell'utente attivo
    try:
        sync_fn = st.session_state.get('_sync_github_file_fn')
        k_pull = f'_gh_pulled_{fname}'
        if callable(sync_fn) and ((not is_locale_pc) or (not esiste_loc)) and k_pull not in st.session_state:
            st.session_state[k_pull] = True
            rem_txt = sync_fn(fname, '', mode='pull')
            if rem_txt:
                try:
                    with open(abs_fp, 'w', encoding='utf-8') as fw:
                        fw.write(rem_txt)
                    esiste_loc = True
                except Exception:
                    pass
    except Exception:
        pass
    # Retrocompatibilità per Fabio: se regia_tracker.json non esiste ancora ma esiste shadow_regia.json, legge da quest'ultimo
    if not esiste_loc and fname == 'regia_tracker.json':
        legacy_fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), SHADOW_FILE)
        if os.path.exists(legacy_fp):
            abs_fp = legacy_fp
            esiste_loc = True
    if esiste_loc and os.path.exists(abs_fp):
        try:
            with open(abs_fp, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return default
    return default

def _save_j(path, data):
    abs_fp, fname = _risolvi_file_utente(path)
    content_str = json.dumps(data, indent=4, ensure_ascii=False)
    with open(abs_fp, 'w', encoding='utf-8') as f:
        f.write(content_str)
    # Sincronizza automaticamente su GitHub se la funzione di sync è disponibile
    try:
        sync_fn = st.session_state.get('_sync_github_file_fn')
        if callable(sync_fn):
            sync_fn(fname, content_str, mode='push')
    except Exception:
        pass

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

def _is_operazione_portafoglio_reale(rec):
    """Determina in modo affidabile se un'operazione (aperta o chiusa) appartiene al Portafoglio Reale o al Metodo Sistema."""
    if not isinstance(rec, dict):
        return False
    orig = str(rec.get('Origine') or '').strip().upper()
    if orig in ('PORTAFOGLIO REALE', 'PORTAFOGLIO_REALE', 'REALE'):
        return True
    if orig in ('METODO SISTEMA', 'METODO_SISTEMA', 'SISTEMA'):
        return False
    fonti = str(rec.get('Fonti') or '').strip().upper()
    segnale = str(rec.get('Segnale') or '').strip().upper()
    return ('PORTAFOGLIO REALE' in fonti) or ('PORTAFOGLIO REALE' in segnale)


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
        # Separa posizioni Spot e PAC: il Trailing Stop / Stop Loss -10% si applica SOLO ai titoli Spot
        port_map_all = {str(p.get('Ticker', '')).strip().upper(): p for p in (port_ok or []) if float(p.get('Quantita', 0) or 0) > 0}
        pac_tickers = {tk for tk, pos in port_map_all.items() if str(pos.get('Tipo', 'Spot')).strip().upper() == 'PAC'}
        port_map_spot = {tk: pos for tk, pos in port_map_all.items() if tk not in pac_tickers}

        # Allineamento automatico continuo con le posizioni Spot del portafoglio reale
        sync_upd = False
        sh_pulita = []
        for r_p in sh_list:
            is_pr = _is_operazione_portafoglio_reale(r_p)
            tk_p = str(r_p.get('Ticker', '')).strip().upper()
            # Rimuove eventuali vecchi alert attivi o da gestire generati erroneamente su titoli PAC
            if is_pr and tk_p in pac_tickers and (r_p.get('Stato') == 'Attivo' or str(r_p.get('Esito_Reale', '')) == 'Da Gestire'):
                sync_upd = True
                continue
            if is_pr and r_p.get('Stato') == 'Attivo':
                if tk_p not in port_map_spot:
                    r_p['Stato'] = 'Chiuso (Venduto Reale)'
                    r_p['Esito_Reale'] = 'Venduto Reale'
                    r_p['Avviso_SL'] = ''
                    r_p['Origine'] = 'Portafoglio Reale'
                    sync_upd = True
                else:
                    q_reale = float(port_map_spot[tk_p].get('Quantita', 0) or 0)
                    pmc_reale = round(float(port_map_spot[tk_p].get('Prezzo_Medio', r_p.get('Entry', 0)) or 0), 2)
                    taglia_reale = round(q_reale * pmc_reale, 2)
                    if pmc_reale > 0 and (abs(pmc_reale - float(r_p.get('Entry', 0))) > 0.01 or abs(taglia_reale - float(r_p.get('Taglia_EUR', 0))) > 1.0):
                        r_p['Entry'] = pmc_reale
                        r_p['Taglia_EUR'] = taglia_reale
                        sync_upd = True
                    if not r_p.get('Origine'):
                        r_p['Origine'] = 'Portafoglio Reale'
                        sync_upd = True
            sh_pulita.append(r_p)
        sh_list = sh_pulita
        if sync_upd:
            _save_j(SHADOW_FILE, sh_list)

        c1, c2, c3 = st.columns([1.8, 1.1, 1.1])
        c1.caption('Traccia metodo puro e posizioni Spot reali con Trailing Stop (i PAC sono esclusi dallo Stop Loss).')
        if c3.button('💼 Sync Portafoglio Reale', key='btn_sync_port_regia', use_container_width=True, disabled=not bool(port_map_spot)):
            oggi_p = datetime.now().strftime('%Y-%m-%d')
            att_port = {str(x.get('Ticker', '')).strip().upper() for x in sh_list if _is_operazione_portafoglio_reale(x) and x.get('Stato') == 'Attivo'}
            agg_p = 0
            # Importa esclusivamente posizioni di tipo Spot (esclude rigorosamente i PAC come CRWD)
            for tk_m, pos_m in port_map_spot.items():
                if tk_m in att_port:
                    continue
                if str(pos_m.get('Tipo', 'Spot')).strip().upper() == 'PAC':
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
                    'Ticker': tk_m, 'Segnale': '💼 PORTAFOGLIO REALE', 'Origine': 'Portafoglio Reale',
                    'Tipo_Posizione': 'Spot', 'Taglia_EUR': round(q_m * pmc_m, 2),
                    'Entry': pmc_m, 'Stop_Loss': sl_e, 'T1': t1_e, 'Target': t2_e,
                    'Max_Price': max(pmc_m, p_oggi_m), 'Step_Trailing': step_init, 'Avviso_SL': '',
                    'Data_Ingresso': str(pos_m.get('Data_Acquisto') or oggi_p)[:10],
                    'Fonti': 'Portafoglio Reale', 'Stato': 'Attivo', 'Esito_Reale': 'In Portafoglio'
                })
                agg_p += 1
            nota_pac = f" (esclusi {len(pac_tickers)} titoli PAC)" if pac_tickers else ""
            if agg_p > 0:
                _save_j(SHADOW_FILE, sh_list)
                st.success(f'✅ Importati {agg_p} titoli Spot del Portafoglio Reale nel Tracker{nota_pac}!')
                st.rerun()
            else:
                st.info(f'ℹ️ Tutti i titoli Spot del Portafoglio Reale sono già sincronizzati{nota_pac}.')
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
                            'Ticker': tk_s, 'Segnale': tp_s, 'Origine': 'Metodo Sistema',
                            'Taglia_EUR': round(float(taglia_ok), 2),
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
            # Conteggi esatti (aperte + chiuse) per ciascuna origine prima della selezione filtro
            tot_all = len(sh_list)
            tot_port = sum(1 for x in sh_list if _is_operazione_portafoglio_reale(x))
            tot_sist = tot_all - tot_port
            opzioni_filtro = [
                '📊 Tutte le Operazioni',
                '🤖 Solo Metodo Sistema',
                '💼 Solo Portafoglio Reale',
            ]
            filtro_vista = st.radio(
                f'Filtro Statistiche & Vista (Tutte: {tot_all} | Sistema: {tot_sist} | Portafoglio Reale: {tot_port}):',
                opzioni_filtro,
                horizontal=True,
                key='radio_filtro_tracker_regia'
            )
            upd, pnls, netti, rows, da_gestire, avvisi_sl = False, [], [], [], [], []
            for idx_s, r in enumerate(sh_list):
                tk_r, st_r = str(r.get('Ticker', '')).strip().upper(), str(r.get('Stato', 'Attivo'))
                is_port_reale = _is_operazione_portafoglio_reale(r)
                en_r = float(r.get('Entry', 0) or 0)
                sl_r = float(r.get('Stop_Loss', 0) or 0)
                t1_r = float(r.get('T1', 0) or round(en_r * 1.12, 2))
                tg_r = float(r.get('Target', 0) or 0)
                mx_r = float(r.get('Max_Price', en_r) or en_r)
                step_tr = int(r.get('Step_Trailing', 0) or 0)
                tg_e, dt_r, p_cur = float(r.get('Taglia_EUR', 200.0) or 200.0), str(r.get('Data_Ingresso', ''))[:10], en_r

                # Aggiornamento prezzi e Trailing Stop / SL (mai applicato ai PAC del portafoglio reale)
                if st_r == 'Attivo' and tk_r and en_r > 0:
                    try:
                        hr = yf.Ticker(tk_r).history(period='6mo', interval='1d')
                        if not hr.empty:
                            p_cur = round(float(hr['Close'].dropna().iloc[-1]) / rate, 2)
                            if not (is_port_reale and tk_r in pac_tickers):
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

                # Filtra sia operazioni aperte sia chiuse in base all'origine effettiva (Origine / Fonti / Segnale)
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
                    'Data': dt_r, 'Ticker': tk_r,
                    'Origine': '💼 Portafoglio Reale' if is_port_reale else '🤖 Metodo Sistema',
                    'Segnale': r.get('Segnale', ''),
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
                            if _is_operazione_portafoglio_reale(sh_list[ix_g]) and tk_g not in pac_tickers:
                                sh_list[ix_g]['Stato'] = 'Attivo'
                                sh_list[ix_g]['Stop_Loss'] = round(pr_g * 0.90, 2)
                                sh_list[ix_g]['Data_Ingresso'] = datetime.now().strftime('%Y-%m-%d')
                                sh_list[ix_g].pop('Prezzo_Uscita', None)
                            _save_j(SHADOW_FILE, sh_list); st.rerun()
                w = sum(1 for x in pnls if x > 0)
                n_op = len(pnls)
                n_att = sum(1 for x in rows if x['Stato'] == 'Attivo')
                n_chi = len(rows) - n_att
                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric('🎯 Win Rate Metodo', f'{(w/n_op)*100:.0f}%', f'{w} su {n_op}')
                k2.metric('📊 Rendimento Medio', f'{sum(pnls)/n_op:+.2f}%', 'Per trade')
                k3.metric('📈 P&L Cumulato', f'{sum(pnls):+.1f}%', 'Somma %')
                k4.metric('💶 Gain Netto (26%)', f'€ {sum(netti):+,.2f}', 'Netto tasse')
                k5.metric('📁 Operazioni', f'{len(rows)}', f"{n_att} attive • {n_chi} chiuse")
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

def _rileva_fase_weinstein_ufficiale(df):
    """Replica esattamente la regola ufficiale rileva_fase_weinstein(df) di scanner.py."""
    if df is None or len(df) < 200:
        return "Dati insufficienti"
    prezzo = df['Close'].iloc[-1]
    sma200_serie = df['Close'].rolling(window=200).mean()
    sma200 = sma200_serie.iloc[-1]
    sma200_prev = sma200_serie.iloc[-20]
    sma50 = df['Close'].rolling(window=50).mean().iloc[-1]
    slope_sma200 = (sma200 - sma200_prev) / sma200_prev if pd.notna(sma200_prev) and sma200_prev > 0 else 0
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


def render_check_3_regole(
    tickers_list,
    eurusd_rate=1.08,
    solo_fase2=False,
    min_score=0,
    solo_pre_ign=False,
    rileva_fase_fn=None,
    portafoglio=None,
    tom_nash_fn=None,
):
    tks = []
    for x in (tickers_list or []):
        t_c = str(x).strip().upper()
        if t_c and t_c not in tks:
            tks.append(t_c)
    if not tks:
        st.info("Inserisci almeno un ticker valido per avviare il controllo.")
        return
    # Mappa posizioni possedute per la 4a riga diagnostica (Scudo Tom Nash & Stato PAC/Spot)
    _port_src = portafoglio if portafoglio is not None else (st.session_state.get("portafoglio") or [])
    port_map_chk = {
        str(p.get("Ticker", "")).strip().upper(): p
        for p in _port_src
        if isinstance(p, dict) and p.get("Ticker")
    }
    salute_map_chk = st.session_state.get("home_salute_portafoglio") or {}
    righe = []
    with st.spinner(f"Verifica 3 Regole in corso su {len(tks)} titoli..."):
        for tk in tks:
            # Inizializza subito _tk_full prima del blocco try/except per evitare UnboundLocalError
            _nome_init = _NOMI_USA.get(tk, '')
            _tk_full = f'{_nome_init} ({tk})' if _nome_init else tk
            try:
                t_obj = yf.Ticker(tk)
                h = t_obj.history(period="1y", interval="1d")
                if h is not None and not h.empty:
                    h = h.dropna(subset=["Open", "High", "Low", "Close"]).copy()
                if h is None or h.empty or len(h) < 50:
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

                # Usa la funzione ufficiale rileva_fase_weinstein passata da scanner.py (o la replica identica di fallback)
                fase_ufficiale = rileva_fase_fn(h) if callable(rileva_fase_fn) else _rileva_fase_weinstein_ufficiale(h)
                _fu_up = str(fase_ufficiale or "").upper()
                if "FASE 2" in _fu_up or "PULLBACK FASE 2" in _fu_up or "2" in _fu_up:
                    fase = 2
                    fase_disp = "FASE 2 (Pullback)" if "PULLBACK" in _fu_up else "FASE 2"
                elif "FASE 4" in _fu_up:
                    fase = 4
                    fase_disp = "FASE 4"
                elif "FASE 3" in _fu_up:
                    fase = 3
                    fase_disp = "FASE 3"
                elif "FASE 1" in _fu_up:
                    fase = 1
                    fase_disp = "FASE 1"
                else:
                    fase = 0
                    fase_disp = "N/D (<200g)"

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
                    f"{'✅' if c_f2 else '❌'} {fase_disp} (req. F2)",
                    f"{'✅' if c_verde else '❌'} Candela {'Verde' if c_verde else 'Rossa'}",
                    f"{'✅' if c_sma20 else '❌'} Prezzo > SMA20",
                    f"{'✅' if c_vpoc else '❌'} Prezzo > VPOC",
                    f"{'✅' if c_vol_ign else '❌'} Volumi {vol_rel:.1f}x (≥1.35)",
                    f"{'✅' if c_rsi_ign else '❌'} RSI {rsi:.0f} (45-63)",
                    f"{'✅' if c_pot else '❌'} Potenziale {pot:+.1f}% (≥10%)"
                ])
                det_fab = " | ".join([
                    f"{'✅' if c_f2 else '❌'} {fase_disp} (req. F2)",
                    f"{'✅' if c_verde else '❌'} Candela {'Verde' if c_verde else 'Rossa'}",
                    f"{'✅' if c_sma20 else '❌'} Prezzo > SMA20",
                    f"{'✅' if c_vpoc else '❌'} Prezzo > VPOC",
                    f"{'✅' if c_vol_fab else '❌'} Volumi {vol_rel:.1f}x (≥1.10)",
                    f"{'✅' if c_rsi_fab else '❌'} RSI {rsi:.0f} (45-68)",
                    f"{'✅' if c_pot else '❌'} Potenziale {pot:+.1f}% (≥10%)"
                ])
                det_std = " | ".join([
                    f"{'✅' if c_f2 else '❌'} {fase_disp} (req. F2)",
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

                # 4a riga diagnostica per i titoli posseduti in portafoglio: Scudo Tom Nash & Stato PAC/Spot
                if tk in port_map_chk:
                    pos_p = port_map_chk[tk]
                    inf_sal = salute_map_chk.get(tk) if isinstance(salute_map_chk, dict) else None
                    # Calcola stato PAC/Spot (gestione 100% manuale del flag PAC_Sospeso)
                    q_tot_p = float(pos_p.get("Quantita", 0) or 0)
                    has_split = (pos_p.get("Quantita_PAC") is not None) or (pos_p.get("Quantita_Spot") is not None)
                    if has_split:
                        q_pac_p = float(pos_p.get("Quantita_PAC", 0) or 0)
                        q_spot_p = float(pos_p.get("Quantita_Spot", 0) or 0)
                    else:
                        is_pac_tp = str(pos_p.get("Tipo", "Spot")).strip().upper().startswith("PAC")
                        q_pac_p = q_tot_p if is_pac_tp else 0.0
                        q_spot_p = 0.0 if is_pac_tp else q_tot_p
                    pac_sosp = bool(pos_p.get("PAC_Sospeso", False))
                    if q_pac_p > 1e-6 and q_spot_p > 1e-6:
                        stato_pac_lbl = f"{'⏸️ PAC Sospeso — Long' if pac_sosp else '🟢 PAC Attivo'} + Spot ({q_pac_p:.2f} PAC + {q_spot_p:.2f} Spot)"
                    elif q_pac_p > 1e-6:
                        stato_pac_lbl = "⏸️ PAC Sospeso — Long (quote PAC 100% protette)" if pac_sosp else "🟢 PAC Attivo (quote PAC 100% protette)"
                    else:
                        stato_pac_lbl = "📂 Posizione Spot"

                    # Recupera dati Tom Nash da salute_map o calcolandoli con tom_nash_fn
                    if isinstance(inf_sal, dict) and ("scudo_tom_nash" in inf_sal):
                        scudo_ok = bool(inf_sal.get("scudo_tom_nash"))
                        nota_tn = str(inf_sal.get("scudo_tom_nash_nota") or "")
                        badge_m = str(inf_sal.get("badge_multipli") or "")
                    else:
                        _inf_raw = {}
                        try:
                            _inf_raw = t_obj.info or {}
                        except Exception:
                            _inf_raw = {}
                        if callable(tom_nash_fn):
                            _tn_r = tom_nash_fn(_inf_raw, s_score=s_score)
                            scudo_ok = bool(_tn_r.get("scudo_tom_nash"))
                            nota_tn = str(_tn_r.get("scudo_tom_nash_nota") or "")
                            badge_m = str(_tn_r.get("badge_multipli") or "")
                        else:
                            rg = _inf_raw.get("revenueGrowth")
                            fpe = _inf_raw.get("forwardPE")
                            scudo_ok = bool(rg is not None and float(rg) >= 0.05 and fpe is not None and 0 < float(fpe) < 65)
                            parti_tn = []
                            if rg is not None:
                                parti_tn.append(f"Fatturato {float(rg)*100:+.0f}%")
                            if fpe is not None and float(fpe) > 0:
                                parti_tn.append(f"Forward P/E {float(fpe):.1f}x")
                            nota_tn = ", ".join(parti_tn) if parti_tn else "Dati fondamentali N/D"
                            badge_m = ""

                    esito_tn = "🛡️ PROTETTO" if (scudo_ok or q_pac_p > 1e-6) else "⚪ MONITORA"
                    pezzi_det = [
                        f"{'🛡️ Scudo Tom Nash ATTIVO' if scudo_ok else 'ℹ️ Scudo Tom Nash non attivo'} ({nota_tn})",
                        stato_pac_lbl,
                    ]
                    if badge_m:
                        pezzi_det.append(badge_m)
                    righe.append({
                        "Titolo": _tk_full,
                        "Motore": "🛡️ Tom Nash & PAC",
                        "Esito": esito_tn,
                        "Dettaglio Criteri (✅ Passa | ❌ Manca)": " | ".join(pezzi_det),
                    })
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
