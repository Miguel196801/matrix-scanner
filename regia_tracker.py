import json, os, re
from datetime import datetime, timedelta, timezone
import pandas as pd
import streamlit as st
import yfinance as yf

SHADOW_FILE = 'shadow_regia.json'
SKIP_FILE = 'skip_regia.json'

_SUFFISSI_EUR = ('.MI', '.DE', '.PA', '.AS', '.F', '.MC', '.BR', '.VI', '.HE', '.LS')


def _oggi_italia_str():
    """Restituisce la data odierna (YYYY-MM-DD) nel fuso orario italiano Europe/Rome."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo('Europe/Rome')).strftime('%Y-%m-%d')
    except Exception:
        return datetime.now(timezone(timedelta(hours=1))).strftime('%Y-%m-%d')


def _fattore_cambio_ticker(tk, eurusd_rate, currency_hint=None):
    """Restituisce 1.0 se il titolo è quotato in EUR, altrimenti il cambio EUR/USD."""
    cur = str(currency_hint or '').strip().upper()
    if cur == 'EUR':
        return 1.0
    tk_u = str(tk or '').strip().upper()
    if any(tk_u.endswith(suf) for suf in _SUFFISSI_EUR):
        return 1.0
    return float(eurusd_rate or 1.12)


def _normalizza_motivo_bivio(motivo):
    """Genera un codice stabile dal motivo del bivio per costruire Bivio_ID univoci."""
    txt = str(motivo or 'VENDITA').strip().upper()
    slug = re.sub(r'[^A-Z0-9]+', '_', txt).strip('_')
    return slug[:28] or 'VENDITA'


def _calcola_netto_eur_trade(entry_eur, exit_o_cur_eur, taglia_eur):
    """Calcola (pct, netto_eur) post tasse italiane 26% sulla sola plusvalenza."""
    en = float(entry_eur or 0.0)
    ex = float(exit_o_cur_eur or en)
    tg = float(taglia_eur or 200.0)
    pct = ((ex - en) / en) * 100.0 if en > 0 else 0.0
    lordo = tg * (pct / 100.0)
    netto = round(lordo - max(0.0, lordo * 0.26), 2)
    return pct, netto

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


def _inferisci_tipo_segnale_sistema(rec):
    """Restituisce il tipo normalizzato di un record Metodo Sistema per la protezione anti-duplicati."""
    tp = str((rec or {}).get('Tipo_Segnale') or '').strip().upper()
    if tp:
        return tp
    seg = str((rec or {}).get('Segnale') or '').strip().upper()
    if 'TOP 1' in seg or 'TOP1' in seg:
        return 'TOP1_BUY'
    if 'DCA' in seg:
        return 'DCA_B2' if '2' in seg else 'DCA_B1'
    if 'CHIUSURA' in seg or 'SL' in seg or 'TRAILING' in seg:
        return 'CHIUSURA_SL_AUTO'
    if 'BIVIO' in seg:
        return 'BIVIO_VENDITA'
    return 'MANUALE'


def _is_protetto_anti_panico_tracker(tk):
    """
    Replica in regia_tracker.py la stessa identica regola Anti-Panico / Scudo Tom Nash
    della Home Page Pilota Automatico (usando solo i dati già in st.session_state, 0 API extra).
    Blocca esclusivamente le chiusure in perdita (Step_Trailing == 0, SL < Entry):
    mai bloccare invece il Pareggio o il Trailing Stop in guadagno (Step_Trailing >= 1).
    """
    tk_u = str(tk or '').strip().upper()
    try:
        sem = st.session_state.get('semaforo_mercato') or {}
    except Exception:
        sem = {}
    if isinstance(sem, dict):
        zona_tn = str(sem.get('zona_sconto_tom_nash') or 'normale').lower()
        if zona_tn in ('sconto', 'bear'):
            return True, f"Termometro Macro ({zona_tn.upper()})"
        if bool(sem.get('fear_greed_paura_estrema')):
            return True, "Paura Estrema (Fear & Greed <= 25)"
        st_spy = str(sem.get('stato') or '').lower()
        if st_spy in ('rosso', 'giallo'):
            return True, f"Mercato SPY {st_spy.upper()} (no vendite su correzione)"

    try:
        sal_map = st.session_state.get('home_salute_portafoglio') or {}
    except Exception:
        sal_map = {}
    inf = sal_map.get(tk_u) if isinstance(sal_map, dict) else None
    if isinstance(inf, dict):
        if bool(inf.get('scudo_tom_nash')):
            return True, "Scudo Fondamentale Tom Nash"
        if int(inf.get('s_score') or 0) >= 65:
            return True, f"S-Score sano ({int(inf.get('s_score') or 0)}/100)"
        if inf.get('sopra_sma200') is True:
            return True, "Trend sopra SMA 200"
        if int(inf.get('sec_buys') or 0) > 0:
            return True, f"Insider SEC 90gg ({int(inf.get('sec_buys') or 0)} acq.)"
    return False, ""


def _crea_copia_sistema_chiusura_sl(sh_list, rec_reale, st_chiusura, prezzo_uscita, data_uscita):
    """
    Crea (senza mai duplicare) 1 copia congelata Origine='Metodo Sistema' nel momento in cui
    una posizione Portafoglio Reale viene chiusa automaticamente per SL o Trailing Stop.
    Usa un Bivio_ID univoco condiviso col record reale e con il pulsante '⏭️ Tengo/Ignora'.
    Restituisce True se ha aggiunto un nuovo record Metodo Sistema.
    """
    if not isinstance(sh_list, list) or not isinstance(rec_reale, dict):
        return False
    tk_u = str(rec_reale.get('Ticker') or '').strip().upper()
    if not tk_u:
        return False
    dt_u = str(data_uscita or _oggi_italia_str())[:10]
    p_u = round(float(prezzo_uscita or rec_reale.get('Prezzo_Uscita') or rec_reale.get('Stop_Loss') or 0), 2)
    bivio_id = str(rec_reale.get('Bivio_ID') or '').strip()
    if not bivio_id:
        bivio_id = f"{tk_u}_{dt_u}_SL_AUTO"
        rec_reale['Bivio_ID'] = bivio_id

    for x in sh_list:
        if not isinstance(x, dict) or _is_operazione_portafoglio_reale(x):
            continue
        if str(x.get('Bivio_ID') or '').strip() == bivio_id:
            return False
        if (
            str(x.get('Ticker') or '').strip().upper() == tk_u
            and str(x.get('Data_Uscita') or '')[:10] == dt_u
            and abs(float(x.get('Prezzo_Uscita') or 0) - p_u) <= 0.02
            and str(x.get('Stato') or '').startswith('Chiuso')
        ):
            rec_reale['Bivio_ID'] = str(x.get('Bivio_ID') or bivio_id)
            return False

    en_v = round(float(rec_reale.get('Entry') or p_u), 2)
    sh_list.append({
        'Ticker': tk_u,
        'Segnale': f'🤖 {st_chiusura}',
        'Tipo_Segnale': 'CHIUSURA_SL_AUTO',
        'Origine': 'Metodo Sistema',
        'Bivio_ID': bivio_id,
        'Bivio_Motivo': str(st_chiusura),
        'Pct_Vendita_Bivio': 100,
        'Currency': rec_reale.get('Currency') or ('EUR' if any(tk_u.endswith(s) for s in _SUFFISSI_EUR) else 'USD'),
        'Taglia_EUR': round(float(rec_reale.get('Taglia_EUR') or 200.0), 2),
        'Entry': en_v,
        'Stop_Loss': p_u,
        'T1': round(float(rec_reale.get('T1') or en_v * 1.12), 2),
        'Target': round(float(rec_reale.get('Target') or en_v * 1.20), 2),
        'Max_Price': round(float(rec_reale.get('Max_Price') or max(en_v, p_u)), 2),
        'Step_Trailing': int(rec_reale.get('Step_Trailing') or 0),
        'Avviso_SL': '',
        'Data_Ingresso': str(rec_reale.get('Data_Ingresso') or dt_u)[:10],
        'Data_Uscita': dt_u,
        'Prezzo_Uscita': p_u,
        'Fonti': f'Chiusura Automatica Sistema ({st_chiusura})',
        'Stato': str(st_chiusura),
        'Esito_Reale': 'Chiusura Automatica',
    })
    return True


def _deduplica_e_allinea_tracker_list(sh_list):
    """
    Pulisce automaticamente i duplicati in regia_tracker*.json (es. 3x NBIS/MU generati da
    ri-sincronizzazioni su record 'Da Gestire') mantenendo 1 solo record per posizione reale
    e retro-allineando 1 copia congelata Origine='Metodo Sistema' per ogni chiusura SL/Trailing.
    Restituisce (lista_pulita, modificata: bool).
    """
    if not isinstance(sh_list, list):
        return [], False
    pulita = []
    mod = False
    # Indici di deduplicazione per Portafoglio Reale e Metodo Sistema
    visti_reali_attivi = {}       # tk -> indice in pulita
    visti_reali_chiusi = {}       # chiave -> indice in pulita
    visti_sys = set()

    def _punteggio_completezza(rec):
        pts = 0
        if float(rec.get('SL_Confermato_TR') or 0) > 0:
            pts += 5
        if str(rec.get('Bivio_ID') or '').strip():
            pts += 3
        if str(rec.get('Esito_Reale') or '') not in ('', 'Da Gestire', 'In Attesa'):
            pts += 4
        if float(rec.get('Max_Price') or 0) > float(rec.get('Entry') or 0):
            pts += 2
        if str(rec.get('Data_Uscita') or ''):
            pts += 1
        return pts

    for r in sh_list:
        if not isinstance(r, dict):
            mod = True
            continue
        tk = str(r.get('Ticker') or '').strip().upper()
        if not tk:
            mod = True
            continue
        st_r = str(r.get('Stato') or 'Attivo')
        dt_in = str(r.get('Data_Ingresso') or '')[:10]
        en_r = round(float(r.get('Entry') or 0), 2)
        is_pr = _is_operazione_portafoglio_reale(r)

        if is_pr:
            if st_r == 'Attivo':
                if tk in visti_reali_attivi:
                    idx_ex = visti_reali_attivi[tk]
                    if _punteggio_completezza(r) > _punteggio_completezza(pulita[idx_ex]):
                        pulita[idx_ex] = r
                    mod = True
                    continue
                visti_reali_attivi[tk] = len(pulita)
                pulita.append(r)
            else:
                # Per chiusure reali SL/Trailing ancora 'Da Gestire' o identiche su (tk, dt_in, entry, stato): 1 solo record
                es_r = str(r.get('Esito_Reale') or '')
                if es_r == 'Da Gestire' and st_r in ('Chiuso (SL)', 'Chiuso (Trailing)'):
                    k_ch = (tk, 'DA_GESTIRE_SL')
                else:
                    k_ch = (tk, dt_in, en_r, st_r, str(r.get('Data_Uscita') or '')[:10])
                if k_ch in visti_reali_chiusi:
                    idx_ex = visti_reali_chiusi[k_ch]
                    if _punteggio_completezza(r) > _punteggio_completezza(pulita[idx_ex]):
                        pulita[idx_ex] = r
                    mod = True
                    continue
                visti_reali_chiusi[k_ch] = len(pulita)
                pulita.append(r)
        else:
            # I record virtuali 'Metodo Sistema' aggiornano SL/Trailing in silenzio: pulisce eventuali Avviso_SL residui
            if str(r.get('Avviso_SL') or '').strip():
                r['Avviso_SL'] = ''
                r['Avviso_SL_Tipo'] = ''
                mod = True
            bid = str(r.get('Bivio_ID') or '').strip()
            tp_s = _inferisci_tipo_segnale_sistema(r)
            if bid:
                k_sys = ('BIVIO', bid)
            else:
                k_sys = ('SYS', tk, tp_s, dt_in, st_r, str(r.get('Data_Uscita') or '')[:10])
            if k_sys in visti_sys:
                mod = True
                continue
            visti_sys.add(k_sys)
            pulita.append(r)

    # Retro-allineamento: per ogni chiusura automatica SL/Trailing del Portafoglio Reale priva di copia Metodo Sistema, la crea 1 sola volta
    for r in list(pulita):
        if _is_operazione_portafoglio_reale(r) and str(r.get('Stato') or '') in ('Chiuso (SL)', 'Chiuso (Trailing)'):
            p_u = float(r.get('Prezzo_Uscita') or r.get('Stop_Loss') or r.get('Entry') or 0)
            dt_u = str(r.get('Data_Uscita') or r.get('Data_Check_SL') or _oggi_italia_str())[:10]
            if p_u > 0:
                if _crea_copia_sistema_chiusura_sl(pulita, r, str(r.get('Stato')), p_u, dt_u):
                    mod = True

    return pulita, mod


def registra_segnali_pilota_automatico(snapshot_dec, portafoglio=None, eurusd_rate=1.12, liq_libera=0.0, taglia_default=200.0):
    """
    Registra automaticamente (senza duplicati) in regia_tracker*.json (Origine='Metodo Sistema')
    i segnali operativi confermati emessi dal Pilota Automatico della Home Page:
    - Top 1 BUY sbloccato (con cassa >= 40 € oppure Piano B valido Super-Score >= 85 & R/R >= 2.0)
    - DCA Doppio Binario (quando non scatta un Top 1 BUY)
    Restituisce il numero di nuovi segnali registrati.
    """
    if not isinstance(snapshot_dec, dict):
        return 0
    rate = float(eurusd_rate or 1.12)
    liq = max(0.0, float(liq_libera or 0.0))
    oggi = _oggi_italia_str()

    sh_list = _load_j(SHADOW_FILE, [])
    if not isinstance(sh_list, list):
        sh_list = []

    # Set anti-duplicati: blocca stesso (Ticker, Tipo_Segnale) se già Attivo o già registrato oggi
    attivi_sys = set()
    oggi_sys = set()
    for r in sh_list:
        if not isinstance(r, dict) or _is_operazione_portafoglio_reale(r):
            continue
        tk_e = str(r.get('Ticker') or '').strip().upper()
        tp_e = _inferisci_tipo_segnale_sistema(r)
        dt_e = str(r.get('Data_Ingresso') or '')[:10]
        if not tk_e:
            continue
        if str(r.get('Stato') or '') == 'Attivo':
            attivi_sys.add((tk_e, tp_e))
        if dt_e == oggi:
            oggi_sys.add((tk_e, tp_e))

    aggiunti = 0
    top1_emesso = False

    # 1) TOP 1 BUY confermato dal Pilota Automatico (senza veto regime)
    veto_msg = snapshot_dec.get('veto_regime_msg')
    top1_cand = snapshot_dec.get('top1_cand')
    riserva = snapshot_dec.get('riserva')
    if (not veto_msg) and isinstance(top1_cand, dict) and top1_cand.get('ticker'):
        sbloccato_cassa = liq >= 40.0
        sbloccato_pb = (
            (not sbloccato_cassa)
            and int(top1_cand.get('super_score', 0) or 0) >= 85
            and float(top1_cand.get('rr', 0) or 0) >= 2.0
            and (bool(top1_cand.get('is_breakout_matrix')) or len(top1_cand.get('motori') or []) >= 2)
        )
        if sbloccato_cassa or sbloccato_pb:
            top1_emesso = True
            tk = str(top1_cand.get('ticker') or '').strip().upper()
            tipo_sig = 'TOP1_BUY'
            if tk and (tk, tipo_sig) not in attivi_sys and (tk, tipo_sig) not in oggi_sys:
                cur = str(top1_cand.get('currency') or 'USD').strip().upper()
                conv = _fattore_cambio_ticker(tk, rate, cur)
                p_eur = float(top1_cand.get('prezzo_eur') or 0.0)
                if p_eur <= 0:
                    p_nat = float(top1_cand.get('prezzo_nat') or 0.0)
                    p_eur = round(p_nat / conv, 2) if p_nat > 0 else 0.0
                if p_eur > 0:
                    p_eur = round(p_eur, 2)
                    stop_nat = float(top1_cand.get('stop_price') or 0.0)
                    targ_nat = float(top1_cand.get('target_price') or 0.0)
                    sl_e = round(stop_nat / conv, 2) if stop_nat > 0 else 0.0
                    t2_e = round(targ_nat / conv, 2) if targ_nat > 0 else 0.0
                    if sl_e <= 0 or sl_e >= p_eur or t2_e <= p_eur:
                        mp = _fetch_metriche_pro(tk, rate)
                        if sl_e <= 0 or sl_e >= p_eur:
                            sl_e = mp['sl_eur'] if (mp and 0.70 * p_eur <= mp['sl_eur'] < p_eur) else round(p_eur * 0.92, 2)
                        if t2_e <= p_eur:
                            t2_e = mp['t2_eur'] if (mp and mp['t2_eur'] > p_eur * 1.03) else round(p_eur * 1.20, 2)
                    t1_e = round(p_eur + 0.60 * (t2_e - p_eur), 2) if t2_e > p_eur else round(p_eur * 1.12, 2)

                    if sbloccato_cassa:
                        taglia_e = round(min(liq, 500.0), 2)
                    elif isinstance(riserva, dict) and float(riserva.get('netto_eur') or 0) > 0:
                        taglia_e = round(min(float(riserva.get('netto_eur') or 0) + liq, 500.0), 2)
                    else:
                        taglia_e = round(max(150.0, float(taglia_default or 200.0)), 2)

                    motori_lbl = ' + '.join([str(m) for m in (top1_cand.get('motori') or ['Breakout'])])
                    sh_list.append({
                        'Ticker': tk,
                        'Segnale': f'🚀 TOP 1 PILOTA ({motori_lbl})',
                        'Tipo_Segnale': tipo_sig,
                        'Origine': 'Metodo Sistema',
                        'Currency': cur,
                        'Super_Score': int(top1_cand.get('super_score') or 0),
                        'Taglia_EUR': taglia_e,
                        'Entry': p_eur,
                        'Stop_Loss': sl_e,
                        'T1': t1_e,
                        'Target': t2_e,
                        'Max_Price': p_eur,
                        'Step_Trailing': 0,
                        'Avviso_SL': '',
                        'Data_Ingresso': oggi,
                        'Data_Check_SL': oggi,
                        'Fonti': f'Pilota Automatico — {motori_lbl}',
                        'Stato': 'Attivo',
                        'Esito_Reale': 'In Attesa',
                    })
                    attivi_sys.add((tk, tipo_sig))
                    oggi_sys.add((tk, tipo_sig))
                    aggiunti += 1

    # 2) DCA DOPPIO BINARIO (solo se non è scattato un ordine Top 1 BUY)
    if not top1_emesso:
        dca_cand = snapshot_dec.get('dca_cand') if liq >= 40.0 else snapshot_dec.get('dca_piano_b')
        if isinstance(dca_cand, dict) and dca_cand.get('ticker'):
            tk_d = str(dca_cand.get('ticker') or '').strip().upper()
            bin_d = int(dca_cand.get('binario') or 1)
            tipo_sig_d = f'DCA_B{bin_d}'
            if tk_d and (tk_d, tipo_sig_d) not in attivi_sys and (tk_d, tipo_sig_d) not in oggi_sys:
                p_eur_d = round(float(dca_cand.get('prezzo_eur') or 0.0), 2)
                if p_eur_d > 0:
                    cur_d = 'EUR' if any(tk_d.endswith(s) for s in _SUFFISSI_EUR) else 'USD'
                    mp_d = _fetch_metriche_pro(tk_d, rate)
                    if mp_d and 0.72 * p_eur_d <= mp_d['sl_eur'] < p_eur_d:
                        sl_d = mp_d['sl_eur']
                        t1_d = mp_d['t1_eur'] if mp_d['t1_eur'] > p_eur_d * 1.02 else round(p_eur_d * 1.12, 2)
                        t2_d = mp_d['t2_eur'] if mp_d['t2_eur'] > t1_d else round(p_eur_d * 1.22, 2)
                    else:
                        sl_d = round(p_eur_d * 0.90, 2)
                        t1_d = round(p_eur_d * 1.12, 2)
                        t2_d = round(p_eur_d * 1.22, 2)
                    taglia_d = round(float(dca_cand.get('importo_eur') or taglia_default or 200.0), 2)
                    mot_d = str(dca_cand.get('motivo') or f'DCA Binario {bin_d}')
                    sh_list.append({
                        'Ticker': tk_d,
                        'Segnale': f'🧮 DCA Binario {bin_d} (Pilota)',
                        'Tipo_Segnale': tipo_sig_d,
                        'Origine': 'Metodo Sistema',
                        'Currency': cur_d,
                        'Taglia_EUR': taglia_d,
                        'Entry': p_eur_d,
                        'Stop_Loss': sl_d,
                        'T1': t1_d,
                        'Target': t2_d,
                        'Max_Price': p_eur_d,
                        'Step_Trailing': 0,
                        'Avviso_SL': '',
                        'Data_Ingresso': oggi,
                        'Data_Check_SL': oggi,
                        'Fonti': f'Pilota Automatico — {mot_d}',
                        'Stato': 'Attivo',
                        'Esito_Reale': 'In Attesa',
                    })
                    attivi_sys.add((tk_d, tipo_sig_d))
                    oggi_sys.add((tk_d, tipo_sig_d))
                    aggiunti += 1

    if aggiunti > 0:
        _save_j(SHADOW_FILE, sh_list)
    return aggiunti


def is_bivio_registrato_oggi(ticker, motivo=''):
    """Verifica se per il ticker (e motivo) è già stato registrato oggi un bivio Tengo vs Sistema."""
    tk = str(ticker or '').strip().upper()
    if not tk:
        return False
    oggi = _oggi_italia_str()
    slug = _normalizza_motivo_bivio(motivo) if motivo else ''
    bivio_atteso = f'{tk}_{oggi}_{slug}' if slug else ''
    sh_list = _load_j(SHADOW_FILE, [])
    if not isinstance(sh_list, list):
        return False
    for r in sh_list:
        if not isinstance(r, dict) or _is_operazione_portafoglio_reale(r):
            continue
        if bivio_atteso and str(r.get('Bivio_ID') or '') == bivio_atteso:
            return True
        if (not bivio_atteso) and str(r.get('Ticker') or '').strip().upper() == tk:
            if str(r.get('Tipo_Segnale') or '') == 'BIVIO_VENDITA' and str(r.get('Data_Uscita') or '')[:10] == oggi:
                return True
    return False


def registra_bivio_tengo_vs_sistema(
    ticker,
    prezzo_attuale_eur,
    portafoglio=None,
    motivo='Vendita / Switch',
    pct_vendita=100,
    eurusd_rate=1.12,
    record_reale_idx=None,
):
    """
    Gestisce in modo atomico lo sdoppiamento in 2 rami quando l'utente clicca '⏭️ Tengo/Ignora'
    su una proposta di vendita / take profit / switch / SL-Trailing del sistema:
    1) RAMO METODO SISTEMA (congelato): crea un record chiuso al prezzo live del momento
       (Origine='Metodo Sistema', Stato='Chiuso (Vendita Sistema)', Prezzo_Uscita=prezzo_attuale_eur).
    2) RAMO PORTAFOGLIO REALE (aperto): mantiene/apre il record reale con il PMC originale intatto
       e Data_Check_SL=oggi, così i due rami restano confrontabili 1-a-1 tramite Bivio_ID.
    Restituisce (creato_bivio: bool, bivio_id: str).
    """
    tk = str(ticker or '').strip().upper()
    p_now = round(float(prezzo_attuale_eur or 0.0), 2)
    if not tk or p_now <= 0:
        return False, ''

    oggi = _oggi_italia_str()
    slug = _normalizza_motivo_bivio(motivo)
    bivio_id = f'{tk}_{oggi}_{slug}'
    pct_v = max(1, min(100, int(round(float(pct_vendita or 100)))))

    sh_list = _load_j(SHADOW_FILE, [])
    if not isinstance(sh_list, list):
        sh_list = []

    port_src = portafoglio if portafoglio is not None else (st.session_state.get('portafoglio') or [])
    pos_reale = next(
        (p for p in (port_src or []) if isinstance(p, dict) and str(p.get('Ticker') or '').strip().upper() == tk),
        None,
    )

    rec_ref = None
    if record_reale_idx is not None and 0 <= int(record_reale_idx) < len(sh_list):
        rec_ref = sh_list[int(record_reale_idx)]

    # Recupera PMC originale, quantità, tipo posizione e data di ingresso senza mai snaturare il PMC reale
    qta_tot = float((pos_reale or {}).get('Quantita') or 0.0)
    pmc_orig = round(float((pos_reale or {}).get('Prezzo_Medio') or 0.0), 2)
    if pmc_orig <= 0 and isinstance(rec_ref, dict):
        pmc_orig = round(float(rec_ref.get('Entry') or 0.0), 2)
    if pmc_orig <= 0:
        pmc_orig = p_now

    tipo_pos_raw = str((pos_reale or {}).get('Tipo') or (rec_ref or {}).get('Tipo_Posizione') or 'Spot').strip()
    is_pac_puro = tipo_pos_raw.upper() == 'PAC'
    cur_tk = str((rec_ref or {}).get('Currency') or ('EUR' if any(tk.endswith(s) for s in _SUFFISSI_EUR) else 'USD')).upper()

    data_acq_orig = ''
    if isinstance(rec_ref, dict) and rec_ref.get('Data_Ingresso'):
        data_acq_orig = str(rec_ref.get('Data_Ingresso'))[:10]
    elif isinstance(pos_reale, dict) and (pos_reale.get('Data_Acquisto') or pos_reale.get('data_acquisto')):
        data_acq_orig = str(pos_reale.get('Data_Acquisto') or pos_reale.get('data_acquisto'))[:10]
    if not data_acq_orig:
        data_acq_orig = oggi

    if qta_tot > 0 and pmc_orig > 0:
        taglia_tot = round(qta_tot * pmc_orig, 2)
        taglia_bivio = round(taglia_tot * (pct_v / 100.0), 2)
    elif isinstance(rec_ref, dict) and float(rec_ref.get('Taglia_EUR') or 0) > 0:
        taglia_tot = round(float(rec_ref.get('Taglia_EUR')), 2)
        taglia_bivio = round(taglia_tot * (pct_v / 100.0), 2)
    else:
        taglia_tot = 200.0
        taglia_bivio = round(200.0 * (pct_v / 100.0), 2)

    # 1) RAMO SISTEMA CONGELATO (anti-duplicato tramite Bivio_ID condiviso anche con chiusura SL/Trailing automatica)
    bid_ref = str(rec_ref.get('Bivio_ID') or '').strip() if isinstance(rec_ref, dict) else ''
    sys_esistente = next(
        (
            x for x in sh_list
            if isinstance(x, dict)
            and (not _is_operazione_portafoglio_reale(x))
            and (
                str(x.get('Bivio_ID') or '') == bivio_id
                or (bid_ref and str(x.get('Bivio_ID') or '') == bid_ref)
            )
        ),
        None,
    )
    esiste_sys_bivio = sys_esistente is not None
    if esiste_sys_bivio:
        bivio_id = str(sys_esistente.get('Bivio_ID') or bivio_id)
        sys_esistente['Esito_Reale'] = 'Ignorata (Tengo)'
        sys_esistente['Bivio_Motivo'] = str(motivo)
        # Se era un gemello 'ALLINEAMENTO_START' ancora Attivo, lo congela ora come Bivio Vendita al prezzo live
        if str(sys_esistente.get('Stato') or '') == 'Attivo':
            sys_esistente['Segnale'] = f'🤖 Bivio Vendita ({motivo})'
            sys_esistente['Tipo_Segnale'] = 'BIVIO_VENDITA'
            sys_esistente['Taglia_EUR'] = taglia_bivio
            sys_esistente['Pct_Vendita_Bivio'] = pct_v
            sys_esistente['Stato'] = 'Chiuso (Vendita Sistema)'
            sys_esistente['Prezzo_Uscita'] = p_now
            sys_esistente['Data_Uscita'] = oggi
            sys_esistente['Fonti'] = f'Bivio Tengo vs Sistema — {motivo}'
    else:
        sh_list.append({
            'Ticker': tk,
            'Segnale': f'🤖 Bivio Vendita ({motivo})',
            'Tipo_Segnale': 'BIVIO_VENDITA',
            'Origine': 'Metodo Sistema',
            'Bivio_ID': bivio_id,
            'Bivio_Motivo': str(motivo),
            'Pct_Vendita_Bivio': pct_v,
            'Currency': cur_tk,
            'Taglia_EUR': taglia_bivio,
            'Entry': pmc_orig,
            'Stop_Loss': p_now,
            'T1': round(pmc_orig * 1.12, 2),
            'Target': round(pmc_orig * 1.20, 2),
            'Max_Price': round(max(pmc_orig, p_now), 2),
            'Step_Trailing': 0,
            'Avviso_SL': '',
            'Data_Ingresso': data_acq_orig,
            'Data_Uscita': oggi,
            'Prezzo_Uscita': p_now,
            'Fonti': f'Bivio Tengo vs Sistema — {motivo}',
            'Stato': 'Chiuso (Vendita Sistema)',
            'Esito_Reale': 'Ignorata (Tengo)',
        })

    # 2) RAMO PORTAFOGLIO REALE APERTO (preserva sempre PMC originale e Data_Ingresso)
    if isinstance(rec_ref, dict) and _is_operazione_portafoglio_reale(rec_ref):
        rec_ref['Origine'] = 'Portafoglio Reale'
        rec_ref['Entry'] = pmc_orig
        rec_ref['Stato'] = 'Attivo'
        rec_ref['Esito_Reale'] = 'Tengo (vs Sistema)'
        rec_ref['Bivio_ID'] = bivio_id
        rec_ref['Bivio_Taglia_Ref'] = taglia_bivio
        rec_ref['Data_Check_SL'] = oggi
        rec_ref['Avviso_SL'] = ''
        rec_ref.pop('Prezzo_Uscita', None)
        if not is_pac_puro:
            rec_ref['Stop_Loss'] = round(p_now * 0.90, 2)
        else:
            rec_ref['Stop_Loss'] = 0.0
    else:
        # Cerca un record Portafoglio Reale già attivo per lo stesso ticker
        rec_att_port = next(
            (
                x for x in sh_list
                if isinstance(x, dict)
                and _is_operazione_portafoglio_reale(x)
                and str(x.get('Ticker') or '').strip().upper() == tk
                and str(x.get('Stato') or '') == 'Attivo'
            ),
            None,
        )
        if rec_att_port is not None:
            rec_att_port['Entry'] = pmc_orig
            rec_att_port['Taglia_EUR'] = taglia_tot
            rec_att_port['Esito_Reale'] = 'Tengo (vs Sistema)'
            rec_att_port['Bivio_ID'] = bivio_id
            rec_att_port['Bivio_Taglia_Ref'] = taglia_bivio
            rec_att_port['Data_Check_SL'] = oggi
            rec_att_port['Avviso_SL'] = ''
        else:
            sh_list.append({
                'Ticker': tk,
                'Segnale': '💼 PORTAFOGLIO REALE',
                'Origine': 'Portafoglio Reale',
                'Tipo_Posizione': 'PAC' if is_pac_puro else tipo_pos_raw,
                'Currency': cur_tk,
                'Taglia_EUR': taglia_tot,
                'Bivio_ID': bivio_id,
                'Bivio_Taglia_Ref': taglia_bivio,
                'Entry': pmc_orig,
                'Stop_Loss': 0.0 if is_pac_puro else round(p_now * 0.90, 2),
                'T1': round(pmc_orig * 1.12, 2),
                'Target': round(pmc_orig * 1.20, 2),
                'Max_Price': round(max(pmc_orig, p_now), 2),
                'Step_Trailing': 0,
                'Avviso_SL': '',
                'Data_Ingresso': data_acq_orig,
                'Data_Check_SL': oggi,
                'Fonti': 'Portafoglio Reale (Bivio)',
                'Stato': 'Attivo',
                'Esito_Reale': 'Tengo (vs Sistema)',
            })

    _save_j(SHADOW_FILE, sh_list)
    return (not esiste_sys_bivio), bivio_id


def _ripartizione_pac_spot_tracker(pos):
    """Restituisce (q_pac, q_spot) coerente con la ripartizione PAC/Spot di scanner.py."""
    if not isinstance(pos, dict):
        return 0.0, 0.0
    q_tot = round(max(0.0, float(pos.get('Quantita', 0) or 0)), 6)
    if q_tot <= 0:
        return 0.0, 0.0
    has_pac = pos.get('Quantita_PAC') is not None
    has_spot = pos.get('Quantita_Spot') is not None
    if has_pac or has_spot:
        q_pac = round(max(0.0, float(pos.get('Quantita_PAC', 0) or 0)), 6)
        q_spot = round(max(0.0, float(pos.get('Quantita_Spot', 0) or 0)), 6)
        somma = round(q_pac + q_spot, 6)
        if abs(somma - q_tot) > 1e-4:
            if somma > 0:
                q_pac = round(min(q_pac, q_tot), 6)
                q_spot = round(max(0.0, q_tot - q_pac), 6)
            else:
                tp_s = str(pos.get('Tipo', 'Spot')).strip().upper()
                return (q_tot, 0.0) if (tp_s.startswith('PAC') and 'SPOT' not in tp_s) else (0.0, q_tot)
        return q_pac, q_spot
    tp_s = str(pos.get('Tipo', 'Spot')).strip().upper()
    if tp_s.startswith('PAC') and 'SPOT' not in tp_s:
        return q_tot, 0.0
    return 0.0, q_tot


def _sl_merita_nuovo_avviso(nuovo_sl, sl_confermato_tr):
    """
    Filtro anti-rumore per gli avvisi Stop Loss:
    - Se l'utente non ha mai confermato uno SL su Trade Republic (<= 0): emette l'avviso.
    - Altrimenti ri-avvisa solo se il nuovo prezzo di protezione sale di almeno +1% oppure +0,50 €.
    """
    ns = float(nuovo_sl or 0.0)
    sc = float(sl_confermato_tr or 0.0)
    if ns <= 0:
        return False
    if sc <= 0:
        return True
    return (ns >= sc * 1.01) or ((ns - sc) >= 0.50)


def _calcola_sl_pct_da_ohlc(df_ohlc, fallback=0.08):
    """Calcola lo stop percentuale tecnico (4.5%..10.5%) dai dati OHLC già in memoria (zero API extra)."""
    try:
        if df_ohlc is None or df_ohlc.empty or len(df_ohlc) < 15:
            return fallback
        closes = df_ohlc['Close'].dropna()
        if len(closes) < 15:
            return fallback
        p_cur = float(closes.iloc[-1])
        if p_cur <= 0:
            return fallback
        sma20 = float(closes.rolling(20).mean().iloc[-1]) if len(closes) >= 20 else p_cur * 0.95
        atr14 = float((df_ohlc['High'] - df_ohlc['Low']).tail(14).mean())
        sl_atr = p_cur - (2.0 * atr14)
        sl_sma = sma20 * 0.985
        candidati = [x for x in (sl_sma, sl_atr) if 0.895 * p_cur <= x <= 0.955 * p_cur]
        sl_p = max(candidati) if candidati else max(p_cur * 0.895, min(p_cur * 0.955, sl_atr))
        pct = abs((sl_p - p_cur) / p_cur)
        return max(0.045, min(0.105, pct))
    except Exception:
        return fallback


def _calcola_trailing_stop_adattivo_grafico(
    df_ohlc,
    mx_eur,
    p_live_eur,
    pmc_eur,
    t1_eur,
    conv=1.0,
    dist_prec_pct=None,
):
    """
    Calcola il Trailing Stop adattivo per i titoli in forte guadagno (Caso 2 / oltre T2)
    combinando volatilità reale (2 x ATR14, clampata tra -6% e -11% dal massimo) e supporto
    grafico della media mobile a 20 giorni (SMA 20 x 0.985), lasciando almeno -5% di respiro
    dal prezzo attuale se possibile e restando sempre sopra il PMC (prezzo di carico).
    Restituisce (sl_finale_eur, dist_dal_max_pct, motivo_grafico_str).
    """
    mx = float(mx_eur or p_live_eur or pmc_eur or 0.0)
    pl = float(p_live_eur or mx or pmc_eur or 0.0)
    pmc = float(pmc_eur or 0.0)
    t1 = float(t1_eur or pmc)
    cv = float(conv or 1.0) if float(conv or 1.0) > 0 else 1.0

    dist_atr = float(dist_prec_pct) / 100.0 if (dist_prec_pct is not None and 5.5 <= float(dist_prec_pct) <= 12.0) else 0.08
    sl_sma20 = None
    ha_dati_graf = False

    try:
        if df_ohlc is not None and not df_ohlc.empty and len(df_ohlc) >= 15:
            closes = df_ohlc['Close'].dropna()
            highs = df_ohlc['High'].dropna()
            lows = df_ohlc['Low'].dropna()
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
    # Se il prezzo live è vicino o sotto T1, garantisce comunque il pavimento almeno al PMC
    if pavimento >= pl * 0.995:
        pavimento = pmc

    scelto_sma = False
    if sl_sma20 is not None and sl_sma20 >= pavimento:
        # Sceglie il più alto tra sl_atr e sl_sma20 purché lasci almeno -5% di respiro dal prezzo attuale
        cand_alto = max(sl_atr, sl_sma20)
        cand_basso = min(sl_atr, sl_sma20)
        if cand_alto <= pl * 0.95:
            sl_fin = cand_alto
            scelto_sma = (cand_alto == sl_sma20 and abs(sl_sma20 - sl_atr) > 0.05)
        elif cand_basso <= pl * 0.95:
            sl_fin = cand_basso
            scelto_sma = (cand_basso == sl_sma20)
        else:
            sl_fin = cand_basso
            scelto_sma = (cand_basso == sl_sma20)
    else:
        sl_fin = sl_atr

    sl_fin = round(max(pavimento, sl_fin), 2)
    # Su Trade Republic un Ordine Stop di vendita deve essere sempre sotto il prezzo di mercato attuale
    if sl_fin >= pl * 0.995:
        sl_fin = round(max(pmc, pl * (1.0 - dist_atr)), 2)

    dist_max_eff = round(max(0.0, ((mx - sl_fin) / mx) * 100.0), 1) if mx > 0 else round(dist_atr * 100.0, 1)
    dist_str = f"{dist_max_eff:.1f}".replace('.', ',')
    if scelto_sma:
        motivo = f"-{dist_str}% dal massimo, appena sotto il supporto della media a 20 giorni"
    elif ha_dati_graf and sl_sma20 is not None:
        motivo = f"-{dist_str}% dal massimo, calibrato sulla volatilità del titolo / supporto media 20 giorni"
    else:
        motivo = f"-{dist_str}% dal massimo, calibrato sulla volatilità del titolo"
    return sl_fin, dist_max_eff, motivo


def _costruisci_dict_avviso_protezione(rec, pos_reale):
    """Costruisce il dizionario strutturato per la card azzurra Protezione Profitto della Home Page."""
    tk = str(rec.get('Ticker') or '').strip().upper()
    q_pac, q_spot = _ripartizione_pac_spot_tracker(pos_reale)
    pmc = round(float(pos_reale.get('Prezzo_Medio') or rec.get('Entry') or 0.0), 2)
    p_live = round(float(pos_reale.get('Prezzo_Attuale_EUR') or rec.get('Max_Price') or pmc), 2)
    sl_val = round(float(rec.get('Stop_Loss') or pmc), 2)
    mx_val = round(max(float(rec.get('Max_Price') or p_live), p_live, pmc), 2)
    pnl_pct = round(((p_live / pmc) - 1.0) * 100.0, 1) if (pmc > 0 and p_live > 0) else 0.0
    dist_att_pct = round(((sl_val / p_live) - 1.0) * 100.0, 1) if p_live > 0 else 0.0
    gain_blind_pct = round(((sl_val / pmc) - 1.0) * 100.0, 1) if pmc > 0 else 0.0
    step_tr = int(rec.get('Step_Trailing') or 0)
    tipo_prot = str(rec.get('Avviso_SL_Tipo') or '').strip().upper()
    if tipo_prot not in ('PAREGGIO', 'TRAILING'):
        tipo_prot = 'TRAILING' if (step_tr >= 2 or sl_val > pmc * 1.01) else 'PAREGGIO'
    motivo_gr = str(rec.get('Avviso_SL_Motivo_Grafico') or '').strip()
    if not motivo_gr and tipo_prot == 'TRAILING':
        d_m = round(max(0.0, ((mx_val - sl_val) / mx_val) * 100.0), 1) if mx_val > 0 else 6.0
        motivo_gr = f"-{str(d_m).replace('.', ',')}% dal massimo, calibrato sulla volatilità del titolo"
    return {
        'ticker': tk,
        'tipo_protezione': tipo_prot,
        'sl_eur': sl_val,
        'pmc_eur': pmc,
        'prezzo_eur': p_live,
        'max_eur': mx_val,
        'pnl_pct': pnl_pct,
        'dist_da_attuale_pct': dist_att_pct,
        'gain_blindato_pct': gain_blind_pct,
        'motivo_grafico': motivo_gr,
        'is_misto_pac_spot': bool(q_pac > 1e-6 and q_spot > 1e-6),
        'qta_spot': round(q_spot, 4),
        'qta_pac': round(q_pac, 4),
        'avviso_testo': str(rec.get('Avviso_SL') or ''),
    }


def _invia_notifica_telegram(utente, messaggio):
    """
    Invia una notifica push Telegram separata al singolo membro della famiglia leggendo
    ESCLUSIVAMENTE da st.secrets (zero token o chat_id salvati nel codice o nei JSON su GitHub):
    - TELEGRAM_BOT_TOKEN
    - TELEGRAM_CHAT_ID_FABIO / TELEGRAM_CHAT_ID_LISI / TELEGRAM_CHAT_ID_ALESSIA
    Se i secrets non sono configurati o la rete non risponde, fallisce silenziosamente (False).
    """
    try:
        u_key = str(utente or '').strip().lower()
        if not u_key or not str(messaggio or '').strip():
            return False
        sec = st.secrets
        token = str(sec.get('TELEGRAM_BOT_TOKEN', '') or '').strip()
        if not token and 'telegram' in sec:
            try:
                token = str(sec['telegram'].get('BOT_TOKEN', '') or '').strip()
            except Exception:
                token = ''
        if not token:
            return False

        chiave_chat = f'TELEGRAM_CHAT_ID_{u_key.upper()}'
        chat_id = str(sec.get(chiave_chat, '') or '').strip()
        if not chat_id and 'telegram' in sec:
            try:
                chat_id = str(sec['telegram'].get(f'CHAT_ID_{u_key.upper()}', '') or '').strip()
            except Exception:
                chat_id = ''
        if not chat_id:
            return False

        import requests
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        payload = {
            'chat_id': chat_id,
            'text': str(messaggio),
            'parse_mode': 'HTML',
            'disable_web_page_preview': True,
        }
        resp = requests.post(url, json=payload, timeout=6)
        return resp.status_code == 200
    except Exception:
        return False


def _formatta_messaggio_telegram_sl(av_d, utente=''):
    """Compone un messaggio push Telegram chiaro e guidato passo-passo per Trade Republic (senza sigle tecniche)."""
    def _eur_it(v):
        return f"€ {float(v or 0.0):,.2f}".replace(',', '_').replace('.', ',').replace('_', '.')

    tk = str(av_d.get('ticker') or '').strip().upper()
    pnl_s = f"{float(av_d.get('pnl_pct') or 0.0):+.1f}%".replace('.', ',')
    sl_s = _eur_it(av_d.get('sl_eur'))
    max_s = _eur_it(av_d.get('max_eur'))
    prezzo_s = _eur_it(av_d.get('prezzo_eur'))
    pmc_s = _eur_it(av_d.get('pmc_eur'))
    dist_s = f"{float(av_d.get('dist_da_attuale_pct') or 0.0):+.1f}%".replace('.', ',')
    gain_b_f = float(av_d.get('gain_blindato_pct') or 0.0)
    gain_b_s = f"{gain_b_f:+.1f}%".replace('.', ',')
    mot_g = str(av_d.get('motivo_grafico') or '-6% dal massimo')
    nome_u = str(utente or '').strip().capitalize()
    saluto = f"Ciao {nome_u}, " if nome_u else ""
    if av_d.get('is_misto_pac_spot'):
        q_sp = float(av_d.get('qta_spot') or 0.0)
        q_lbl = f"{int(q_sp)}" if abs(q_sp - round(q_sp)) < 1e-4 else f"{q_sp:.2f}".replace('.', ',')
        nota_misto = f" sulle sole <b>{q_lbl} azioni Spot</b> (lascia intatto il tuo PAC)"
    else:
        nota_misto = ''

    if av_d.get('tipo_protezione') == 'TRAILING':
        riga_impatto = (
            f"📊 <b>Se scatta lo Stop:</b> <b>{dist_s}</b> rispetto al prezzo attuale ({prezzo_s}) → "
            f"blindato un guadagno di <b>{gain_b_s}</b> sul tuo prezzo di carico ({pmc_s})."
        )
        return (
            f"🏆 <b>MATRIX PRO — PROTEGGI IL PROFITTO ({tk})</b>\n"
            f"{saluto}<b>{tk}</b> è a <b>{pnl_s}</b> (massimo {max_s}): alziamo la rete di sicurezza calibrata sul grafico del titolo!\n\n"
            f"👉 <b>Trade Republic (30 secondi):</b>\n"
            f"Apri <b>{tk}</b> → Vendi → Ordine Stop → imposta il prezzo a <b>{sl_s}</b> ({mot_g}){nota_misto}.\n"
            f"{riga_impatto}\n"
            f"Poi clicca <i>✅ Fatto, Stop Loss inserito</i> nell'app MATRIX."
        )
    riga_impatto_p = (
        f"📊 <b>Se scatta lo Stop:</b> <b>{dist_s}</b> rispetto al prezzo attuale ({prezzo_s}) → "
        f"chiudi comunque a <b>0,0% (pareggio)</b> sul tuo prezzo di carico."
    )
    return (
        f"🛡️ <b>MATRIX PRO — METTI AL SICURO IL GUADAGNO ({tk})</b>\n"
        f"{saluto}<b>{tk}</b> è a <b>{pnl_s}</b>: ora possiamo azzerare il rischio di perdita!\n\n"
        f"👉 <b>Trade Republic (30 secondi):</b>\n"
        f"Apri <b>{tk}</b> → Vendi → Ordine Stop → imposta il prezzo a <b>{sl_s}</b> (prezzo di carico){nota_misto}.\n"
        f"{riga_impatto_p}\n"
        f"Poi clicca <i>✅ Fatto, Stop Loss inserito</i> nell'app MATRIX."
    )


def _formatta_messaggio_telegram_gain(
    tk,
    pnl_pct,
    val_spot,
    gain_netto_tot,
    netto_50,
    netto_100,
    sl_prot,
    is_misto,
    q_spot,
    scaglione,
    utente='',
):
    """
    Compone un alert Telegram chiaro per Presa Profitto / Chiusura Gain sulle sole quote Spot (mai PAC):
    - Se il 50% netto >= € 100: consiglia raccolto parziale 50% + protezione del resto con Stop Loss.
    - Se il 50% netto < € 100 (posizione piccola): consiglia chiusura intera o lasciar correre con Stop Loss.
    """
    def _eur_it(v):
        return f"€ {float(v or 0.0):,.2f}".replace(',', '_').replace('.', ',').replace('_', '.')

    pnl_s = f"{float(pnl_pct or 0.0):+.1f}%".replace('.', ',')
    nome_u = str(utente or '').strip().capitalize()
    saluto = f"Ciao {nome_u}, " if nome_u else ""
    if is_misto:
        q_lbl = f"{int(q_spot)}" if abs(q_spot - round(q_spot)) < 1e-4 else f"{q_spot:.2f}".replace('.', ',')
        nota_misto = f" (solo sulle <b>{q_lbl} azioni Spot</b> — lascia intatto il tuo PAC)"
    else:
        nota_misto = ""

    if float(netto_50 or 0.0) >= 100.0:
        consiglio = (
            f"👉 <b>Azione consigliata:</b> valuta raccolto parziale <b>50% ({_eur_it(netto_50)} netti)</b> "
            f"e proteggi il resto con Stop Loss a <b>{_eur_it(sl_prot)}</b> su Trade Republic."
        )
    else:
        consiglio = (
            f"👉 <b>Posizione piccola — 2 opzioni:</b> valuta chiusura intera per incassare "
            f"<b>{_eur_it(netto_100)} netti</b> (guadagno netto {_eur_it(gain_netto_tot)}) "
            f"oppure lascia correre proteggendo con Stop Loss a <b>{_eur_it(sl_prot)}</b>."
        )

    return (
        f"💰 <b>MATRIX PRO — TRAGUARDO GAIN +{int(scaglione)}% ({tk})</b>\n"
        f"{saluto}<b>{tk}</b> ha raggiunto <b>{pnl_s}</b>{nota_misto}!\n"
        f"• Controvalore Spot: <b>{_eur_it(val_spot)}</b>\n"
        f"• Guadagno netto stimato (post 26% tasse e € 1 TR): <b>{_eur_it(gain_netto_tot)}</b>\n\n"
        f"{consiglio}"
    )


def sincronizza_avvisi_protezione_spot(portafoglio, eurusd_rate=1.12, ohlc_map=None, utente=None):
    """
    Sincronizza automaticamente tutte le posizioni con quote Spot (q_spot > 0, escludendo al 100% i PAC puri
    attivi o sospesi Long) in regia_tracker*.json usando i dati OHLC già in memoria (zero chiamate API lente).
    Rileva i passaggi di protezione profitto (Pareggio al PMC o Trailing -6% dal massimo) applicando il filtro
    anti-rumore su SL_Confermato_TR (+1% o +0,50 €) e invia 1 sola notifica push Telegram al telefono
    del singolo utente interessato tramite SL_Notificato_Telegram.
    Restituisce la lista di avvisi pendenti pronti per la Home Page.
    """
    if not portafoglio:
        return []
    rate = float(eurusd_rate or 1.12)
    oggi = _oggi_italia_str()
    utente_eff = str(
        utente
        or st.session_state.get('utente_corrente')
        or st.session_state.get('utente_autenticato')
        or 'fabio'
    ).strip().lower()
    sh_list = _load_j(SHADOW_FILE, [])
    if not isinstance(sh_list, list):
        sh_list = []

    sh_list, dedup_mod = _deduplica_e_allinea_tracker_list(sh_list)
    upd = bool(dedup_mod)
    avvisi_home = []

    for pos in (portafoglio or []):
        if not isinstance(pos, dict):
            continue
        tk = str(pos.get('Ticker') or '').strip().upper()
        if not tk:
            continue
        q_pac, q_spot = _ripartizione_pac_spot_tracker(pos)
        # Esclusione assoluta per titoli solo PAC (attivi o sospesi Long)
        if q_spot <= 1e-6:
            continue

        pmc = round(float(pos.get('Prezzo_Medio') or 0.0), 2)
        if pmc <= 0:
            continue
        p_live = round(float(pos.get('Prezzo_Attuale_EUR') or pos.get('Prezzo_Attuale') or pmc), 2)
        cur_tk = 'EUR' if any(tk.endswith(s) for s in _SUFFISSI_EUR) else 'USD'
        conv = _fattore_cambio_ticker(tk, rate, cur_tk)
        is_misto = bool(q_pac > 1e-6)
        tipo_lbl = 'PAC + Spot' if is_misto else 'Spot'
        taglia_spot = round(q_spot * pmc, 2)
        data_acq = str(pos.get('Data_Acquisto') or pos.get('data_acquisto') or oggi)[:10]

        df_ohlc = (ohlc_map or {}).get(tk) if isinstance(ohlc_map, dict) else None
        # Trova il record Portafoglio Reale attivo in regia_tracker*.json
        rec = next(
            (
                x for x in sh_list
                if isinstance(x, dict)
                and _is_operazione_portafoglio_reale(x)
                and str(x.get('Ticker') or '').strip().upper() == tk
                and str(x.get('Stato') or '') == 'Attivo'
            ),
            None,
        )
        # Protezione anti-duplicato: se esiste già una chiusura SL/Trailing 'Da Gestire' o sulla stessa posizione reale, non ri-crea doppioni
        if rec is None:
            gia_chiuso_pendente = any(
                isinstance(x, dict)
                and _is_operazione_portafoglio_reale(x)
                and str(x.get('Ticker') or '').strip().upper() == tk
                and str(x.get('Stato') or '') in ('Chiuso (SL)', 'Chiuso (Trailing)')
                and (
                    str(x.get('Esito_Reale') or '') == 'Da Gestire'
                    or (
                        str(x.get('Data_Ingresso') or '')[:10] == data_acq
                        and abs(float(x.get('Entry') or 0) - pmc) <= 0.02
                    )
                )
                for x in sh_list
            )
            if gia_chiuso_pendente:
                continue
        if rec is None:
            sl_pct = _calcola_sl_pct_da_ohlc(df_ohlc, fallback=0.08)
            t1_e = round(pmc * (1.0 + 1.5 * sl_pct), 2)
            t2_e = round(pmc * (1.0 + 2.5 * sl_pct), 2)
            sl_init = round(pmc * (1.0 - sl_pct), 2)
            rec = {
                'Ticker': tk,
                'Segnale': '💼 PORTAFOGLIO REALE',
                'Origine': 'Portafoglio Reale',
                'Tipo_Posizione': tipo_lbl,
                'Quantita_Spot': round(q_spot, 6),
                'Quantita_PAC': round(q_pac, 6),
                'Currency': cur_tk,
                'Taglia_EUR': taglia_spot,
                'Entry': pmc,
                'Stop_Loss': sl_init,
                'T1': t1_e,
                'Target': t2_e,
                'Max_Price': max(pmc, p_live),
                'Step_Trailing': 0,
                'SL_Confermato_TR': 0.0,
                'SL_Notificato_Telegram': 0.0,
                'Gain_Notificato_Telegram': 0,
                'Avviso_SL': '',
                'Avviso_SL_Tipo': '',
                'Data_Ingresso': data_acq,
                'Data_Check_SL': data_acq,
                'Fonti': 'Portafoglio Reale',
                'Stato': 'Attivo',
                'Esito_Reale': 'In Portafoglio',
            }
            sh_list.append(rec)
            upd = True
        else:
            # Allinea PMC, quota Spot e metadati se variati
            if abs(float(rec.get('Entry') or 0) - pmc) > 0.01 or abs(float(rec.get('Taglia_EUR') or 0) - taglia_spot) > 1.0:
                rec['Entry'] = pmc
                rec['Taglia_EUR'] = taglia_spot
                upd = True
            if rec.get('Tipo_Posizione') != tipo_lbl or abs(float(rec.get('Quantita_Spot') or 0) - q_spot) > 1e-4:
                rec['Tipo_Posizione'] = tipo_lbl
                rec['Quantita_Spot'] = round(q_spot, 6)
                rec['Quantita_PAC'] = round(q_pac, 6)
                upd = True

        # Calcola massimo raggiunto in EUR combinando OHLC dalla data ingresso/check e prezzo live
        dt_chk = str(rec.get('Data_Check_SL') or rec.get('Data_Ingresso') or oggi)[:10]
        hi_eur = p_live
        if df_ohlc is not None and not df_ohlc.empty and 'High' in df_ohlc.columns:
            try:
                sr = df_ohlc[df_ohlc.index.strftime('%Y-%m-%d') >= dt_chk] if dt_chk else df_ohlc.tail(20)
                if not sr.empty:
                    hi_ohlc = round(float(sr['High'].dropna().max()) / conv, 2)
                    hi_eur = max(hi_eur, hi_ohlc)
            except Exception:
                pass

        mx_r = round(max(float(rec.get('Max_Price') or pmc), hi_eur, p_live), 2)
        if mx_r > float(rec.get('Max_Price') or 0) + 0.005:
            rec['Max_Price'] = mx_r
            upd = True

        t1_r = float(rec.get('T1') or round(pmc * 1.12, 2))
        t2_r = float(rec.get('Target') or round(pmc * 1.20, 2))
        sl_r = float(rec.get('Stop_Loss') or round(pmc * 0.92, 2))
        sl_conf = float(rec.get('SL_Confermato_TR') or 0.0)
        step_tr = int(rec.get('Step_Trailing') or 0)

        # Valutazione Protezione Profitto: solo se il prezzo attuale è sopra il livello Stop da inserire su TR
        if t2_r > 0 and mx_r >= t2_r and p_live > pmc * 1.02:
            nuovo_sl, dist_mx_pct, mot_graf = _calcola_trailing_stop_adattivo_grafico(
                df_ohlc=df_ohlc,
                mx_eur=mx_r,
                p_live_eur=p_live,
                pmc_eur=pmc,
                t1_eur=t1_r,
                conv=conv,
                dist_prec_pct=rec.get('Avviso_SL_Dist_Max_Pct'),
            )
            # Se l'utente non ha ancora confermato lo SL su TR, adotta subito il nuovo Trailing calibrato sul grafico;
            # una volta confermato (sl_conf > 0), lo Stop Loss si alza soltanto e non scende mai.
            aggiorna_sl_t2 = (nuovo_sl > sl_r) or (sl_conf <= 0 and df_ohlc is not None and abs(nuovo_sl - sl_r) >= 0.05)
            if aggiorna_sl_t2:
                rec['Stop_Loss'] = nuovo_sl
                sl_r = nuovo_sl
                upd = True
            if rec.get('Avviso_SL_Motivo_Grafico') != mot_graf or rec.get('Avviso_SL_Dist_Max_Pct') != dist_mx_pct:
                rec['Avviso_SL_Motivo_Grafico'] = mot_graf
                rec['Avviso_SL_Dist_Max_Pct'] = dist_mx_pct
                upd = True
            if step_tr < 2:
                rec['Step_Trailing'] = 2
                upd = True
            if p_live > sl_r and _sl_merita_nuovo_avviso(sl_r, sl_conf):
                rec['Avviso_SL_Tipo'] = 'TRAILING'
                rec['Avviso_SL'] = f"🏆 {tk}: Proteggi il profitto accumulato — sposta lo Stop Loss su Trade Republic a € {sl_r:.2f} ({mot_graf})."
                upd = True
        elif t1_r > 0 and mx_r >= t1_r and p_live > pmc * 1.005:
            if sl_r < pmc:
                rec['Stop_Loss'] = pmc
                sl_r = pmc
                upd = True
            if step_tr < 1:
                rec['Step_Trailing'] = 1
                upd = True
            if _sl_merita_nuovo_avviso(pmc, sl_conf):
                rec['Avviso_SL_Tipo'] = 'PAREGGIO'
                rec['Avviso_SL'] = f"🛡️ {tk}: Metti al sicuro il capitale — imposta lo Stop Loss su Trade Republic a € {pmc:.2f} (pareggio)."
                upd = True

        # Se esiste un avviso pendente ancora coerente col prezzo live, lo aggiunge alla lista Home e notifica su Telegram 1 sola volta
        if str(rec.get('Avviso_SL') or '').strip():
            sl_curr_val = float(rec.get('Stop_Loss') or pmc)
            if p_live > sl_curr_val * 0.995 and _sl_merita_nuovo_avviso(sl_curr_val, float(rec.get('SL_Confermato_TR') or 0.0)):
                av_d = _costruisci_dict_avviso_protezione(rec, pos)
                avvisi_home.append(av_d)
                # Notifica push Telegram dedicata al singolo utente solo per un nuovo livello SL non ancora notificato
                sl_not_tg = float(rec.get('SL_Notificato_Telegram') or 0.0)
                if _sl_merita_nuovo_avviso(sl_curr_val, sl_not_tg):
                    msg_tg = _formatta_messaggio_telegram_sl(av_d, utente_eff)
                    if _invia_notifica_telegram(utente_eff, msg_tg):
                        rec['SL_Notificato_Telegram'] = round(sl_curr_val, 2)
                        rec['Data_Notifica_Telegram'] = oggi
                        upd = True
            else:
                rec['Avviso_SL'] = ''
                upd = True

        # Alert Telegram automatico Presa Profitto / Chiusura Gain (SOLO quote Spot, scaglioni 35% / 50% / 70%, soglia anti-briciole >= € 100 netti)
        pnl_pct_spot = ((p_live / pmc) - 1.0) * 100.0 if (pmc > 0 and p_live > 0) else 0.0
        scaglione_gain = 70 if pnl_pct_spot >= 70.0 else (50 if pnl_pct_spot >= 50.0 else (35 if pnl_pct_spot >= 35.0 else 0))
        gain_not_prev = int(rec.get('Gain_Notificato_Telegram') or 0)
        if scaglione_gain > 0 and scaglione_gain > gain_not_prev:
            val_spot_g = round(q_spot * p_live, 2)
            carico_spot_g = round(q_spot * pmc, 2)
            gain_lordo_g = max(0.0, val_spot_g - carico_spot_g)
            tasse_tot_g = gain_lordo_g * 0.26
            gain_netto_tot_g = round(max(0.0, gain_lordo_g - tasse_tot_g - 1.0), 2)
            netto_100_g = round(max(0.0, val_spot_g - tasse_tot_g - 1.0), 2)
            netto_50_g = round(max(0.0, (val_spot_g * 0.5) - (gain_lordo_g * 0.5 * 0.26) - 1.0), 2)
            if netto_50_g >= 100.0 or netto_100_g >= 100.0:
                sl_prot_g = round(max(pmc, float(rec.get('Stop_Loss') or pmc)), 2)
                if sl_prot_g >= p_live * 0.995:
                    sl_prot_g = round(max(pmc, p_live * 0.94), 2)
                msg_gain_tg = _formatta_messaggio_telegram_gain(
                    tk=tk,
                    pnl_pct=pnl_pct_spot,
                    val_spot=val_spot_g,
                    gain_netto_tot=gain_netto_tot_g,
                    netto_50=netto_50_g,
                    netto_100=netto_100_g,
                    sl_prot=sl_prot_g,
                    is_misto=is_misto,
                    q_spot=q_spot,
                    scaglione=scaglione_gain,
                    utente=utente_eff,
                )
                if _invia_notifica_telegram(utente_eff, msg_gain_tg):
                    rec['Gain_Notificato_Telegram'] = scaglione_gain
                    rec['Data_Notifica_Gain_Telegram'] = oggi
                    upd = True

    if upd:
        _save_j(SHADOW_FILE, sh_list)
    return avvisi_home


def ottieni_avvisi_protezione_pendenti(portafoglio=None):
    """
    Restituisce istantaneamente (zero chiamate di rete) gli avvisi Protezione Profitto pendenti
    per le sole posizioni con quote Spot presenti nel portafoglio corrente.
    """
    port_src = portafoglio if portafoglio is not None else (st.session_state.get('portafoglio') or [])
    if not port_src:
        return []
    port_spot_map = {}
    for pos in port_src:
        if not isinstance(pos, dict):
            continue
        tk = str(pos.get('Ticker') or '').strip().upper()
        if not tk:
            continue
        _, q_spot = _ripartizione_pac_spot_tracker(pos)
        if q_spot > 1e-6:
            port_spot_map[tk] = pos

    if not port_spot_map:
        return []

    sh_list = _load_j(SHADOW_FILE, [])
    if not isinstance(sh_list, list):
        return []

    avvisi = []
    visti = set()
    for rec in sh_list:
        if not isinstance(rec, dict) or not _is_operazione_portafoglio_reale(rec):
            continue
        if str(rec.get('Stato') or '') != 'Attivo':
            continue
        tk = str(rec.get('Ticker') or '').strip().upper()
        if not tk or tk in visti or tk not in port_spot_map:
            continue
        if not str(rec.get('Avviso_SL') or '').strip():
            continue
        sl_v = float(rec.get('Stop_Loss') or 0.0)
        sl_conf = float(rec.get('SL_Confermato_TR') or 0.0)
        if not _sl_merita_nuovo_avviso(sl_v, sl_conf):
            continue
        avvisi.append(_costruisci_dict_avviso_protezione(rec, port_spot_map[tk]))
        visti.add(tk)
    return avvisi


def conferma_avviso_sl(ticker, nuovo_sl=None):
    """
    Archivia l'avviso Protezione Profitto sia nella Home Page sia nel Tracker salvando
    SL_Confermato_TR su regia_tracker*.json (con sincronizzazione GitHub automatica) e
    sincronizzando la conferma anche sull'eventuale record gemello con lo stesso Bivio_ID.
    """
    tk = str(ticker or '').strip().upper()
    if not tk:
        return False
    sh_list = _load_j(SHADOW_FILE, [])
    if not isinstance(sh_list, list):
        return False
    oggi = _oggi_italia_str()
    mod = False
    bivi_confermati = set()
    sl_conf_ref = round(float(nuovo_sl), 2) if (nuovo_sl is not None and float(nuovo_sl or 0) > 0) else 0.0

    # 1) Conferma sui record attivi del ticker (priorità Portafoglio Reale) e raccoglie gli eventuali Bivio_ID
    for rec in sh_list:
        if not isinstance(rec, dict):
            continue
        if str(rec.get('Ticker') or '').strip().upper() != tk:
            continue
        if str(rec.get('Stato') or '') != 'Attivo':
            continue
        if _is_operazione_portafoglio_reale(rec) or str(rec.get('Avviso_SL') or '').strip():
            sl_val = round(float(sl_conf_ref if sl_conf_ref > 0 else (rec.get('Stop_Loss') or 0.0)), 2)
            if sl_val > 0 and sl_conf_ref <= 0:
                sl_conf_ref = sl_val
            rec['Avviso_SL'] = ''
            rec['Avviso_SL_Tipo'] = ''
            if sl_val > 0:
                rec['SL_Confermato_TR'] = sl_val
                rec['SL_Notificato_Telegram'] = max(float(rec.get('SL_Notificato_Telegram') or 0.0), sl_val)
            rec['Data_Conferma_SL'] = oggi
            bid_c = str(rec.get('Bivio_ID') or '').strip()
            if bid_c:
                bivi_confermati.add(bid_c)
            mod = True

    # 2) Sincronizza la conferma anche sull'eventuale record gemello (stesso Bivio_ID o virtuale dello stesso ticker)
    for rec in sh_list:
        if not isinstance(rec, dict) or str(rec.get('Stato') or '') != 'Attivo':
            continue
        bid_r = str(rec.get('Bivio_ID') or '').strip()
        tk_r = str(rec.get('Ticker') or '').strip().upper()
        if (bid_r and bid_r in bivi_confermati) or (tk_r == tk and not _is_operazione_portafoglio_reale(rec)):
            if str(rec.get('Avviso_SL') or '').strip():
                rec['Avviso_SL'] = ''
                rec['Avviso_SL_Tipo'] = ''
                mod = True
            if sl_conf_ref > 0:
                if float(rec.get('SL_Confermato_TR') or 0.0) < sl_conf_ref:
                    rec['SL_Confermato_TR'] = sl_conf_ref
                    mod = True
                if float(rec.get('Stop_Loss') or 0.0) < sl_conf_ref:
                    rec['Stop_Loss'] = sl_conf_ref
                    mod = True
            if rec.get('Data_Conferma_SL') != oggi:
                rec['Data_Conferma_SL'] = oggi
                mod = True

    if mod:
        _save_j(SHADOW_FILE, sh_list)
    return mod


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
        sh_list, dedup_init_mod = _deduplica_e_allinea_tracker_list(sh_list)
        # Separa posizioni con quote Spot e PAC puri: lo Stop Loss si applica SOLO alle quote Spot (mai PAC attivi o sospesi)
        port_map_all = {str(p.get('Ticker', '')).strip().upper(): p for p in (port_ok or []) if float(p.get('Quantita', 0) or 0) > 0}
        pac_tickers = {tk for tk, pos in port_map_all.items() if _ripartizione_pac_spot_tracker(pos)[1] <= 1e-6}
        port_map_spot = {tk: pos for tk, pos in port_map_all.items() if tk not in pac_tickers}

        # Allineamento automatico continuo con le posizioni del portafoglio reale
        sync_upd = bool(dedup_init_mod)
        sh_pulita = []
        mappa_reali_sync = {}  # bivio_id -> (Entry, Taglia_EUR, Currency) per tenere al centesimo i gemelli START
        for r_p in sh_list:
            is_pr = _is_operazione_portafoglio_reale(r_p)
            tk_p = str(r_p.get('Ticker', '')).strip().upper()
            bid_p = str(r_p.get('Bivio_ID') or '').strip()
            has_bivio = bool(bid_p)
            # Un Bivio_ID che termina con '_START' è un allineamento iniziale solo Spot (non un bivio vendita su PAC)
            has_bivio_vendita = has_bivio and (not bid_p.endswith('_START'))
            # Rimuove eventuali vecchi alert SL generati erroneamente su titoli PAC (preservando quelli tracciati per un Bivio)
            if is_pr and tk_p in pac_tickers and (not has_bivio_vendita) and (r_p.get('Stato') == 'Attivo' or str(r_p.get('Esito_Reale', '')) == 'Da Gestire'):
                sync_upd = True
                continue
            if is_pr and r_p.get('Stato') == 'Attivo':
                # Chiude come Venduto Reale se il titolo non è più nel portafoglio (per i bivi vendita verifica port_map_all, inclusi PAC)
                mappa_ref = port_map_all if has_bivio_vendita else port_map_spot
                if tk_p not in mappa_ref:
                    r_p['Stato'] = 'Chiuso (Venduto Reale)'
                    r_p['Esito_Reale'] = 'Venduto Reale'
                    r_p['Avviso_SL'] = ''
                    r_p['Origine'] = 'Portafoglio Reale'
                    sync_upd = True
                else:
                    pos_ref = mappa_ref[tk_p]
                    _, q_spot_ref = _ripartizione_pac_spot_tracker(pos_ref)
                    q_reale = q_spot_ref if (q_spot_ref > 1e-6 and not has_bivio_vendita) else float(pos_ref.get('Quantita', 0) or 0)
                    pmc_reale = round(float(pos_ref.get('Prezzo_Medio', r_p.get('Entry', 0)) or 0), 2)
                    taglia_reale = round(q_reale * pmc_reale, 2)
                    if pmc_reale > 0 and (abs(pmc_reale - float(r_p.get('Entry', 0))) > 0.01 or abs(taglia_reale - float(r_p.get('Taglia_EUR', 0))) > 0.01):
                        r_p['Entry'] = pmc_reale
                        r_p['Taglia_EUR'] = taglia_reale
                        sync_upd = True
                    if not r_p.get('Origine'):
                        r_p['Origine'] = 'Portafoglio Reale'
                        sync_upd = True
                    if bid_p and bid_p.endswith('_START'):
                        mappa_reali_sync[bid_p] = (
                            round(float(r_p.get('Entry') or pmc_reale), 2),
                            round(float(r_p.get('Taglia_EUR') or taglia_reale), 2),
                            r_p.get('Currency') or ('EUR' if any(tk_p.endswith(s) for s in _SUFFISSI_EUR) else 'USD'),
                        )
            sh_pulita.append(r_p)
        # Allinea al centesimo Entry, Taglia_EUR e Currency sui gemelli 'ALLINEAMENTO_START' attivi
        if mappa_reali_sync:
            for r_s in sh_pulita:
                if (not _is_operazione_portafoglio_reale(r_s)) and str(r_s.get('Stato') or '') == 'Attivo':
                    bid_s = str(r_s.get('Bivio_ID') or '').strip()
                    if bid_s in mappa_reali_sync and _inferisci_tipo_segnale_sistema(r_s) == 'ALLINEAMENTO_START':
                        en_ref, tg_ref, cur_ref = mappa_reali_sync[bid_s]
                        if (
                            abs(float(r_s.get('Entry') or 0) - en_ref) > 0.005
                            or abs(float(r_s.get('Taglia_EUR') or 0) - tg_ref) > 0.005
                            or r_s.get('Currency') != cur_ref
                        ):
                            r_s['Entry'] = en_ref
                            r_s['Taglia_EUR'] = tg_ref
                            r_s['Currency'] = cur_ref
                            sync_upd = True
        sh_list = sh_pulita
        if sync_upd:
            _save_j(SHADOW_FILE, sh_list)

        c1, c2, c3 = st.columns([1.8, 1.1, 1.1])
        c1.caption('Traccia automaticamente i segnali del Pilota Automatico, i bivi Tengo vs Sistema e le posizioni Spot reali.')
        if c3.button('💼 Sync Portafoglio Reale', key='btn_sync_port_regia', use_container_width=True, disabled=not bool(port_map_spot)):
            oggi_p = _oggi_italia_str()
            # Protezione anti-duplicato: esclude ticker già Attivi o con chiusura SL/Trailing 'Da Gestire' / stessa posizione
            att_port = {
                str(x.get('Ticker', '')).strip().upper()
                for x in sh_list
                if _is_operazione_portafoglio_reale(x)
                and (
                    x.get('Stato') == 'Attivo'
                    or (
                        str(x.get('Stato') or '') in ('Chiuso (SL)', 'Chiuso (Trailing)')
                        and str(x.get('Esito_Reale') or '') == 'Da Gestire'
                    )
                )
            }
            pos_chiuse_same = {
                (str(x.get('Ticker', '')).strip().upper(), str(x.get('Data_Ingresso') or '')[:10], round(float(x.get('Entry') or 0), 2))
                for x in sh_list
                if _is_operazione_portafoglio_reale(x) and str(x.get('Stato') or '') in ('Chiuso (SL)', 'Chiuso (Trailing)')
            }
            agg_p = 0
            # Importa esclusivamente posizioni di tipo Spot (esclude rigorosamente i PAC puri)
            for tk_m, pos_m in port_map_spot.items():
                if tk_m in att_port:
                    continue
                if str(pos_m.get('Tipo', 'Spot')).strip().upper() == 'PAC':
                    continue
                q_m = float(pos_m.get('Quantita', 0) or 0)
                pmc_m = round(float(pos_m.get('Prezzo_Medio', 0) or 0), 2)
                dt_acq_m = str(pos_m.get('Data_Acquisto') or oggi_p)[:10]
                if q_m <= 0 or pmc_m <= 0 or (tk_m, dt_acq_m, pmc_m) in pos_chiuse_same:
                    continue
                mp = _fetch_metriche_pro(tk_m, rate)
                sl_pct_m = abs(mp['sl_pct']) / 100.0 if mp else 0.08
                t1_e = round(pmc_m * (1.0 + 1.5 * sl_pct_m), 2)
                t2_e = round(pmc_m * (1.0 + 2.5 * sl_pct_m), 2)
                # Legge Prezzo_Attuale_EUR (chiave reale di portafoglio.json) con fallback legacy
                p_oggi_m = round(float(pos_m.get('Prezzo_Attuale_EUR') or pos_m.get('Prezzo_Attuale') or pmc_m), 2)
                cur_m = 'EUR' if any(tk_m.endswith(s) for s in _SUFFISSI_EUR) else 'USD'
                conv_m = _fattore_cambio_ticker(tk_m, rate, cur_m)
                if p_oggi_m >= t2_e:
                    try:
                        df_m = yf.Ticker(tk_m).history(period='3mo', interval='1d')
                    except Exception:
                        df_m = None
                    sl_e, _, _ = _calcola_trailing_stop_adattivo_grafico(
                        df_ohlc=df_m,
                        mx_eur=max(pmc_m, p_oggi_m),
                        p_live_eur=p_oggi_m,
                        pmc_eur=pmc_m,
                        t1_eur=t1_e,
                        conv=conv_m,
                    )
                    step_init = 2
                elif p_oggi_m >= t1_e:
                    sl_e = pmc_m
                    step_init = 1
                else:
                    sl_e = round(pmc_m * (1.0 - sl_pct_m), 2)
                    step_init = 0
                sh_list.append({
                    'Ticker': tk_m, 'Segnale': '💼 PORTAFOGLIO REALE', 'Origine': 'Portafoglio Reale',
                    'Tipo_Posizione': 'Spot', 'Taglia_EUR': round(q_m * pmc_m, 2),
                    'Currency': cur_m,
                    'Entry': pmc_m, 'Stop_Loss': sl_e, 'T1': t1_e, 'Target': t2_e,
                    'Max_Price': max(pmc_m, p_oggi_m), 'Step_Trailing': step_init, 'Avviso_SL': '',
                    'Data_Ingresso': dt_acq_m,
                    'Data_Check_SL': oggi_p,
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
            oggi_sh = _oggi_italia_str()
            att_sh = {(x.get('Ticker'), x.get('Data_Ingresso')) for x in sh_list}
            agg = 0
            for item in fin_oggi:
                _, tk_s, tp_s, _, _, _, fn_s, _ = item
                if (tk_s, oggi_sh) in att_sh:
                    continue
                try:
                    h1 = yf.Ticker(tk_s).history(period='2d')
                    if not h1.empty:
                        conv_s = _fattore_cambio_ticker(tk_s, rate)
                        p_eur = round(float(h1['Close'].dropna().iloc[-1]) / conv_s, 2)
                        mp = _fetch_metriche_pro(tk_s, rate)
                        sl_e = mp['sl_eur'] if mp else round(p_eur * 0.92, 2)
                        t1_e = mp['t1_eur'] if mp else round(p_eur * 1.12, 2)
                        t2_e = mp['t2_eur'] if mp else round(p_eur * 1.20, 2)
                        sh_list.append({
                            'Ticker': tk_s, 'Segnale': tp_s, 'Tipo_Segnale': 'MANUALE', 'Origine': 'Metodo Sistema',
                            'Currency': 'EUR' if conv_s == 1.0 else 'USD',
                            'Taglia_EUR': round(float(taglia_ok), 2),
                            'Entry': p_eur, 'Stop_Loss': sl_e, 'T1': t1_e, 'Target': t2_e,
                            'Max_Price': p_eur, 'Step_Trailing': 0, 'Avviso_SL': '',
                            'Data_Ingresso': oggi_sh, 'Data_Check_SL': oggi_sh,
                            'Fonti': ' + '.join([f.replace('**', '') for f in fn_s]),
                            'Stato': 'Attivo', 'Esito_Reale': 'In Attesa'
                        })
                        agg += 1
                except Exception:
                    pass
            if agg > 0:
                _save_j(SHADOW_FILE, sh_list)
                st.success(f'✅ Registrati {agg} ordini nel Tracker!')
                st.rerun()

        # Pulsante pratico di reset pulito: azzera il vecchio storico sporco e fa ripartire Sistema = Reale da oggi
        if st.button(
            '🔄 Azzera Storico e Riparti da Oggi (Allinea Sistema = Reale)',
            key='btn_reset_allinea_tracker_oggi',
            use_container_width=True,
            disabled=not bool(port_map_spot),
            help='Azzera tutti i vecchi record del profilo corrente e crea 1 record Portafoglio Reale + 1 gemello Metodo Sistema per ogni posizione Spot attiva da oggi.',
        ):
            oggi_rst = _oggi_italia_str()
            nuova_sh = []
            n_coppie = 0
            for tk_m, pos_m in port_map_spot.items():
                q_pac_m, q_spot_m = _ripartizione_pac_spot_tracker(pos_m)
                if q_spot_m <= 1e-6:
                    continue
                pmc_m = round(float(pos_m.get('Prezzo_Medio') or 0), 2)
                if pmc_m <= 0:
                    continue
                p_oggi_m = round(float(pos_m.get('Prezzo_Attuale_EUR') or pos_m.get('Prezzo_Attuale') or pmc_m), 2)
                cur_m = 'EUR' if any(tk_m.endswith(s) for s in _SUFFISSI_EUR) else 'USD'
                conv_m = _fattore_cambio_ticker(tk_m, rate, cur_m)
                taglia_spot_m = round(q_spot_m * pmc_m, 2)
                tipo_pos_m = 'PAC + Spot' if q_pac_m > 1e-6 else 'Spot'
                try:
                    df_m = yf.Ticker(tk_m).history(period='3mo', interval='1d')
                except Exception:
                    df_m = None
                sl_pct_m = _calcola_sl_pct_da_ohlc(df_m, fallback=0.08)
                t1_e = round(pmc_m * (1.0 + 1.5 * sl_pct_m), 2)
                t2_e = round(pmc_m * (1.0 + 2.5 * sl_pct_m), 2)
                mx_init = round(max(pmc_m, p_oggi_m), 2)
                if p_oggi_m >= t2_e:
                    sl_e, _, _ = _calcola_trailing_stop_adattivo_grafico(
                        df_ohlc=df_m,
                        mx_eur=mx_init,
                        p_live_eur=p_oggi_m,
                        pmc_eur=pmc_m,
                        t1_eur=t1_e,
                        conv=conv_m,
                    )
                    step_init = 2
                elif p_oggi_m >= t1_e:
                    sl_e = pmc_m
                    step_init = 1
                else:
                    sl_e = round(pmc_m * (1.0 - sl_pct_m), 2)
                    step_init = 0
                bivio_id_rst = f"{tk_m}_{oggi_rst}_START"
                # 1) Record Portafoglio Reale (allineato da oggi)
                nuova_sh.append({
                    'Ticker': tk_m,
                    'Segnale': '💼 PORTAFOGLIO REALE',
                    'Origine': 'Portafoglio Reale',
                    'Tipo_Posizione': tipo_pos_m,
                    'Quantita_Spot': round(q_spot_m, 6),
                    'Quantita_PAC': round(q_pac_m, 6),
                    'Bivio_ID': bivio_id_rst,
                    'Currency': cur_m,
                    'Taglia_EUR': taglia_spot_m,
                    'Entry': pmc_m,
                    'Stop_Loss': sl_e,
                    'T1': t1_e,
                    'Target': t2_e,
                    'Max_Price': mx_init,
                    'Step_Trailing': step_init,
                    'SL_Confermato_TR': 0.0,
                    'SL_Notificato_Telegram': 0.0,
                    'Gain_Notificato_Telegram': 0,
                    'Avviso_SL': '',
                    'Avviso_SL_Tipo': '',
                    'Data_Ingresso': oggi_rst,
                    'Data_Check_SL': oggi_rst,
                    'Fonti': 'Portafoglio Reale (Start Allineato)',
                    'Stato': 'Attivo',
                    'Esito_Reale': 'In Portafoglio',
                })
                # 2) Record gemello Metodo Sistema (stesso Bivio_ID, stessi livelli da oggi)
                nuova_sh.append({
                    'Ticker': tk_m,
                    'Segnale': '🤖 PORTAFOGLIO SISTEMA (PARI)',
                    'Tipo_Segnale': 'ALLINEAMENTO_START',
                    'Origine': 'Metodo Sistema',
                    'Tipo_Posizione': tipo_pos_m,
                    'Bivio_ID': bivio_id_rst,
                    'Currency': cur_m,
                    'Taglia_EUR': taglia_spot_m,
                    'Entry': pmc_m,
                    'Stop_Loss': sl_e,
                    'T1': t1_e,
                    'Target': t2_e,
                    'Max_Price': mx_init,
                    'Step_Trailing': step_init,
                    'Avviso_SL': '',
                    'Data_Ingresso': oggi_rst,
                    'Data_Check_SL': oggi_rst,
                    'Fonti': 'Allineamento Iniziale (Sistema = Reale)',
                    'Stato': 'Attivo',
                    'Esito_Reale': 'In Corso (Pari)',
                })
                n_coppie += 1
            _save_j(SHADOW_FILE, nuova_sh)
            nota_pac_r = f" (esclusi {len(pac_tickers)} PAC puri)" if pac_tickers else ""
            st.success(f'✅ Storico azzerato e allineato da oggi ({oggi_rst}): {n_coppie} coppie Sistema = Reale create{nota_pac_r}!')
            st.rerun()

        if sh_list:
            # 1) Aggiornamento prezzi live + Trailing Stop/SL su TUTTI i record (con cache per ticker)
            upd = False
            hist_cache = {}
            prezzi_live_tk = {}
            valutati = []
            nuovi_sys_chiusi = []
            for idx_s, r in enumerate(sh_list):
                tk_r = str(r.get('Ticker', '')).strip().upper()
                st_r = str(r.get('Stato', 'Attivo'))
                is_port_reale = _is_operazione_portafoglio_reale(r)
                en_r = float(r.get('Entry', 0) or 0)
                sl_r = float(r.get('Stop_Loss', 0) or 0)
                t1_r = float(r.get('T1', 0) or round(en_r * 1.12, 2))
                tg_r = float(r.get('Target', 0) or 0)
                mx_r = float(r.get('Max_Price', en_r) or en_r)
                step_tr = int(r.get('Step_Trailing', 0) or 0)
                tg_e = float(r.get('Taglia_EUR', 200.0) or 200.0)
                dt_r = str(r.get('Data_Ingresso', ''))[:10]
                dt_chk = str(r.get('Data_Check_SL') or dt_r)[:10]
                conv_r = _fattore_cambio_ticker(tk_r, rate, r.get('Currency'))
                p_cur = en_r

                # Aggiornamento prezzi e Trailing Stop / SL (mai applicato ai PAC puri del portafoglio reale)
                if st_r == 'Attivo' and tk_r and en_r > 0:
                    try:
                        if tk_r not in hist_cache:
                            hist_cache[tk_r] = yf.Ticker(tk_r).history(period='6mo', interval='1d')
                        hr = hist_cache[tk_r]
                        if hr is not None and not hr.empty:
                            p_cur = round(float(hr['Close'].dropna().iloc[-1]) / conv_r, 2)
                            prezzi_live_tk[tk_r] = p_cur
                            is_pac_no_sl = is_port_reale and (tk_r in pac_tickers or str(r.get('Tipo_Posizione') or '').upper() == 'PAC')
                            if not is_pac_no_sl:
                                sr = hr[hr.index.strftime('%Y-%m-%d') >= dt_chk] if dt_chk else hr.tail(1)
                                lo = float(sr['Low'].min()) / conv_r if not sr.empty else p_cur
                                hi = float(sr['High'].max()) / conv_r if not sr.empty else p_cur
                                if hi > mx_r:
                                    mx_r = round(hi, 2)
                                    sh_list[idx_s]['Max_Price'] = mx_r
                                    upd = True
                                if step_tr < 1 and t1_r > 0 and hi >= t1_r and sl_r < en_r:
                                    sl_r = round(en_r, 2)
                                    step_tr = 1
                                    sh_list[idx_s]['Stop_Loss'] = sl_r
                                    sh_list[idx_s]['Step_Trailing'] = 1
                                    if is_port_reale:
                                        if _sl_merita_nuovo_avviso(sl_r, sh_list[idx_s].get('SL_Confermato_TR')):
                                            sh_list[idx_s]['Avviso_SL_Tipo'] = 'PAREGGIO'
                                            sh_list[idx_s]['Avviso_SL'] = f"🛡️ {tk_r}: Metti al sicuro il capitale — imposta lo Stop Loss su Trade Republic a € {sl_r:.2f} (pareggio)."
                                    else:
                                        # Record virtuale 'Metodo Sistema': aggiornamento silenzioso senza banner manuale
                                        sh_list[idx_s]['SL_Confermato_TR'] = sl_r
                                        sh_list[idx_s]['Avviso_SL'] = ''
                                        sh_list[idx_s]['Avviso_SL_Tipo'] = ''
                                    upd = True
                                if tg_r > 0 and hi >= tg_r:
                                    nuovo_sl, dist_mx_tr, mot_tr = _calcola_trailing_stop_adattivo_grafico(
                                        df_ohlc=hr,
                                        mx_eur=mx_r,
                                        p_live_eur=p_cur,
                                        pmc_eur=en_r,
                                        t1_eur=t1_r,
                                        conv=conv_r,
                                        dist_prec_pct=sh_list[idx_s].get('Avviso_SL_Dist_Max_Pct'),
                                    )
                                    if nuovo_sl > sl_r:
                                        sl_r = nuovo_sl
                                        step_tr = 2
                                        sh_list[idx_s]['Stop_Loss'] = sl_r
                                        sh_list[idx_s]['Step_Trailing'] = 2
                                        sh_list[idx_s]['Avviso_SL_Motivo_Grafico'] = mot_tr
                                        sh_list[idx_s]['Avviso_SL_Dist_Max_Pct'] = dist_mx_tr
                                        if is_port_reale:
                                            if _sl_merita_nuovo_avviso(sl_r, sh_list[idx_s].get('SL_Confermato_TR')):
                                                sh_list[idx_s]['Avviso_SL_Tipo'] = 'TRAILING'
                                                sh_list[idx_s]['Avviso_SL'] = f"🏆 {tk_r}: Proteggi il profitto accumulato — sposta lo Stop Loss su Trade Republic a € {sl_r:.2f} ({mot_tr})."
                                        else:
                                            # Record virtuale 'Metodo Sistema': aggiornamento silenzioso senza banner manuale
                                            sh_list[idx_s]['SL_Confermato_TR'] = sl_r
                                            sh_list[idx_s]['Avviso_SL'] = ''
                                            sh_list[idx_s]['Avviso_SL_Tipo'] = ''
                                        upd = True
                                if sl_r > 0 and lo <= sl_r:
                                    # Unificazione regole Home vs Tracker:
                                    # - Pareggio / Trailing in profitto (step_tr >= 1): scatta SEMPRE su entrambi i portafogli.
                                    # - SL in perdita (step_tr == 0, sl_r < en_r): bloccato se il titolo ha protezione Anti-Panico / Scudo Tom Nash.
                                    chiudi_sl = True
                                    if step_tr == 0 and sl_r < en_r:
                                        prot_ap, mot_ap = _is_protetto_anti_panico_tracker(tk_r)
                                        if prot_ap:
                                            chiudi_sl = False
                                            if sh_list[idx_s].get('Protezione_Anti_Panico') != mot_ap:
                                                sh_list[idx_s]['Protezione_Anti_Panico'] = mot_ap
                                                upd = True
                                    if chiudi_sl:
                                        dt_uscita_oggi = _oggi_italia_str()
                                        st_r = 'Chiuso (Trailing)' if step_tr >= 1 else 'Chiuso (SL)'
                                        p_cur, upd = sl_r, True
                                        sh_list[idx_s]['Stato'] = st_r
                                        sh_list[idx_s]['Prezzo_Uscita'] = sl_r
                                        sh_list[idx_s]['Data_Uscita'] = dt_uscita_oggi
                                        sh_list[idx_s]['Esito_Reale'] = 'Da Gestire' if is_port_reale else 'Chiusura Automatica'
                                        sh_list[idx_s]['Avviso_SL'] = ''
                                        # Crea subito 1 copia congelata Origine='Metodo Sistema' (senza duplicati)
                                        if is_port_reale:
                                            tmp_chk = list(sh_list) + nuovi_sys_chiusi
                                            if _crea_copia_sistema_chiusura_sl(tmp_chk, sh_list[idx_s], st_r, sl_r, dt_uscita_oggi):
                                                nuovi_sys_chiusi.append(tmp_chk[-1])
                    except Exception:
                        pass
                else:
                    p_cur = float(r.get('Prezzo_Uscita') or en_r)

                pct_v, netto_v = _calcola_netto_eur_trade(en_r, p_cur, tg_e)
                valutati.append({
                    'idx': idx_s, 'rec': r, 'tk': tk_r, 'stato': st_r,
                    'is_port': is_port_reale, 'en': en_r, 'sl': sl_r,
                    't1': t1_r, 'tg': tg_r, 'p_cur': p_cur,
                    'dt': dt_r, 'pct': pct_v, 'netto': netto_v,
                })

            if nuovi_sys_chiusi:
                for rec_ns in nuovi_sys_chiusi:
                    idx_ns = len(sh_list)
                    sh_list.append(rec_ns)
                    en_ns = float(rec_ns.get('Entry') or 0)
                    pu_ns = float(rec_ns.get('Prezzo_Uscita') or en_ns)
                    tg_ns = float(rec_ns.get('Taglia_EUR') or 200.0)
                    pct_ns, netto_ns = _calcola_netto_eur_trade(en_ns, pu_ns, tg_ns)
                    valutati.append({
                        'idx': idx_ns, 'rec': rec_ns, 'tk': str(rec_ns.get('Ticker') or ''),
                        'stato': str(rec_ns.get('Stato') or 'Chiuso (SL)'),
                        'is_port': False, 'en': en_ns, 'sl': float(rec_ns.get('Stop_Loss') or pu_ns),
                        't1': float(rec_ns.get('T1') or en_ns), 'tg': float(rec_ns.get('Target') or en_ns),
                        'p_cur': pu_ns, 'dt': str(rec_ns.get('Data_Ingresso') or '')[:10],
                        'pct': pct_ns, 'netto': netto_ns,
                    })
                upd = True

            if upd:
                _save_j(SHADOW_FILE, sh_list)

            # 2) Box KPI Comparativo in testa al Tracker: 🤖 Metodo Sistema vs 💼 Portafoglio Reale + ⚖️ Delta Bivi
            sys_items = [v for v in valutati if not v['is_port']]
            real_items = [v for v in valutati if v['is_port']]
            netto_sys_tot = round(sum(v['netto'] for v in sys_items), 2)
            netto_real_tot = round(sum(v['netto'] for v in real_items), 2)
            wr_sys = (sum(1 for v in sys_items if v['pct'] > 0) / len(sys_items) * 100.0) if sys_items else 0.0
            wr_real = (sum(1 for v in real_items if v['pct'] > 0) / len(real_items) * 100.0) if real_items else 0.0
            att_sys = sum(1 for v in sys_items if v['stato'] == 'Attivo')
            att_real = sum(1 for v in real_items if v['stato'] == 'Attivo')

            # Calcolo Delta Bivi 1-a-1 (stessa Taglia_EUR del bivio: Ramo Reale vs Ramo Sistema congelato)
            real_by_bivio = {
                str(v['rec'].get('Bivio_ID') or ''): v
                for v in real_items if str(v['rec'].get('Bivio_ID') or '').strip()
            }
            real_by_tk = {}
            for v in real_items:
                if v['tk'] not in real_by_tk or v['stato'] == 'Attivo':
                    real_by_tk[v['tk']] = v

            n_bivi = 0
            tot_bivio_sys = 0.0
            tot_bivio_real = 0.0
            vince_utente = 0
            vince_sistema = 0
            for v_s in sys_items:
                if _inferisci_tipo_segnale_sistema(v_s['rec']) != 'BIVIO_VENDITA':
                    continue
                bid = str(v_s['rec'].get('Bivio_ID') or '')
                tk_b = v_s['tk']
                taglia_b = float(v_s['rec'].get('Taglia_EUR') or 200.0)
                en_b = v_s['en']
                # Prezzo corrente o chiuso del Ramo Reale per confronto mele-con-mele
                v_r = real_by_bivio.get(bid) or real_by_tk.get(tk_b)
                if v_r is not None:
                    p_real_cmp = v_r['p_cur']
                elif tk_b in prezzi_live_tk:
                    p_real_cmp = prezzi_live_tk[tk_b]
                elif tk_b in port_map_all and float(port_map_all[tk_b].get('Prezzo_Attuale_EUR') or 0) > 0:
                    p_real_cmp = float(port_map_all[tk_b].get('Prezzo_Attuale_EUR'))
                else:
                    p_real_cmp = v_s['p_cur']
                _, netto_b_real = _calcola_netto_eur_trade(en_b, p_real_cmp, taglia_b)
                tot_bivio_sys += v_s['netto']
                tot_bivio_real += netto_b_real
                n_bivi += 1
                if netto_b_real > v_s['netto'] + 0.01:
                    vince_utente += 1
                elif v_s['netto'] > netto_b_real + 0.01:
                    vince_sistema += 1

            delta_bivi = round(tot_bivio_real - tot_bivio_sys, 2)
            col_sys = '#4ADE80' if netto_sys_tot >= 0 else '#F87171'
            col_real = '#4ADE80' if netto_real_tot >= 0 else '#F87171'
            if n_bivi == 0:
                col_delta = '#94A3B8'
                val_delta_txt = 'Nessun bivio'
                sub_delta_txt = 'Clicca ⏭️ Tengo/Ignora su una vendita per attivare la sfida'
            else:
                col_delta = '#4ADE80' if delta_bivi > 0 else ('#F87171' if delta_bivi < 0 else '#E2E8F0')
                chi_vince = 'Vince Tengo io' if delta_bivi > 0 else ('Vince il Sistema' if delta_bivi < 0 else 'In pari')
                val_delta_txt = f'€ {delta_bivi:+,.2f} ({chi_vince})'
                sub_delta_txt = f'{n_bivi} bivi ({vince_utente} Tu / {vince_sistema} Sistema) • Sist. € {tot_bivio_sys:+,.2f} vs Reale € {tot_bivio_real:+,.2f}'

            _kpi_cmp_html = "".join([
                "<div style='display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:10px; margin:8px 0 12px 0;'>",
                "<div style='background:#131722; border:1px solid #334155; border-top:3px solid #38BDF8; border-radius:10px; padding:0.80rem 1.0rem;'>",
                "<div style='font-size:0.78rem; font-weight:700; color:#CBD5E1; text-transform:uppercase;'>🤖 Metodo Sistema (Pilota)</div>",
                f"<div style='font-family:JetBrains Mono, monospace; font-size:1.35rem; font-weight:800; color:{col_sys}; margin-top:4px;'>€ {netto_sys_tot:+,.2f}</div>",
                f"<div style='font-size:0.78rem; color:#94A3B8; margin-top:3px;'>Win Rate {wr_sys:.0f}% • {len(sys_items)} op. ({att_sys} attive / {len(sys_items)-att_sys} chiuse)</div>",
                "</div>",
                "<div style='background:#131722; border:1px solid #334155; border-top:3px solid #10B981; border-radius:10px; padding:0.80rem 1.0rem;'>",
                "<div style='font-size:0.78rem; font-weight:700; color:#CBD5E1; text-transform:uppercase;'>💼 Portafoglio Reale</div>",
                f"<div style='font-family:JetBrains Mono, monospace; font-size:1.35rem; font-weight:800; color:{col_real}; margin-top:4px;'>€ {netto_real_tot:+,.2f}</div>",
                f"<div style='font-size:0.78rem; color:#94A3B8; margin-top:3px;'>Win Rate {wr_real:.0f}% • {len(real_items)} op. ({att_real} attive / {len(real_items)-att_real} chiuse)</div>",
                "</div>",
                "<div style='background:#131722; border:1px solid #334155; border-top:3px solid #F59E0B; border-radius:10px; padding:0.80rem 1.0rem;'>",
                "<div style='font-size:0.78rem; font-weight:700; color:#CBD5E1; text-transform:uppercase;'>⚖️ Delta Bivi (Tengo io vs Sistema)</div>",
                f"<div style='font-family:JetBrains Mono, monospace; font-size:1.15rem; font-weight:800; color:{col_delta}; margin-top:6px;'>{val_delta_txt}</div>",
                f"<div style='font-size:0.76rem; color:#94A3B8; margin-top:3px;'>{sub_delta_txt}</div>",
                "</div>",
                "</div>",
            ])
            st.markdown(_kpi_cmp_html, unsafe_allow_html=True)

            # 3) Filtro vista e tabella dettagliata
            tot_all = len(valutati)
            tot_port = len(real_items)
            tot_sist = len(sys_items)
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

            pnls, netti, rows, da_gestire, avvisi_sl = [], [], [], [], []
            for v in valutati:
                if filtro_vista == '🤖 Solo Metodo Sistema' and v['is_port']:
                    continue
                if filtro_vista == '💼 Solo Portafoglio Reale' and not v['is_port']:
                    continue
                r = v['rec']
                # Mostra il banner/pulsante manuale '✅ SL Aggiornato' esclusivamente sui record reali (mai su 'Metodo Sistema')
                if v['is_port'] and v['stato'] == 'Attivo' and str(r.get('Avviso_SL', '')).strip():
                    avvisi_sl.append((v['idx'], v['tk'], str(r.get('Avviso_SL'))))
                pnls.append(v['pct'])
                netti.append(v['netto'])
                if v['stato'] != 'Attivo' and str(r.get('Esito_Reale', 'Da Gestire')) == 'Da Gestire':
                    da_gestire.append((v['idx'], v['tk'], v['stato'], v['p_cur'], v['pct'], v['netto']))
                rows.append({
                    'Data': v['dt'], 'Ticker': v['tk'],
                    'Origine': '💼 Portafoglio Reale' if v['is_port'] else '🤖 Metodo Sistema',
                    'Segnale': r.get('Segnale', ''),
                    'Entry €': v['en'], 'SL €': v['sl'], 'T1 €': v['t1'], 'T2 €': v['tg'], 'Attuale €': v['p_cur'],
                    'Stato': v['stato'], 'Reale': r.get('Esito_Reale', 'In Attesa'),
                    'P&L %': f"{v['pct']:+.1f}%", 'Netto €': f"€ {v['netto']:+.2f}"
                })

            if rows:
                if avvisi_sl:
                    for ix_a, tk_a, msg_a in avvisi_sl:
                        ca1, ca2 = st.columns([3.5, 1])
                        ca1.info(msg_a)
                        if ca2.button('✅ SL Aggiornato', key=f'btn_ack_sl_{ix_a}_{tk_a}', use_container_width=True):
                            conferma_avviso_sl(tk_a, sh_list[ix_a].get('Stop_Loss'))
                            st.rerun()
                if da_gestire:
                    st.warning('🔔 **Chiusure Automatiche del Sistema (Trailing / SL) da confermare nel reale:**')
                    for ix_g, tk_g, st_g, pr_g, pc_g, nt_g in da_gestire:
                        cg1, cg2, cg3 = st.columns([2.5, 1, 1])
                        cg1.markdown(f'**{tk_g}** — {st_g} @ **€ {pr_g:.2f}** ({pc_g:+.1f}% | Netto **€ {nt_g:+.2f}**)')
                        if cg2.button('✅ Replicata', key=f'btn_rep_{ix_g}_{tk_g}', use_container_width=True):
                            sh_list[ix_g]['Esito_Reale'] = 'Replicata'; _save_j(SHADOW_FILE, sh_list); st.rerun()
                        if cg3.button('⏭️ Tengo/Ignora', key=f'btn_ign_{ix_g}_{tk_g}', use_container_width=True):
                            if _is_operazione_portafoglio_reale(sh_list[ix_g]):
                                # Sdoppiamento in 2 rami: congela Ramo Sistema a pr_g e mantiene Ramo Reale con PMC intatto
                                registra_bivio_tengo_vs_sistema(
                                    ticker=tk_g,
                                    prezzo_attuale_eur=pr_g,
                                    portafoglio=port_ok,
                                    motivo=st_g,
                                    pct_vendita=100,
                                    eurusd_rate=rate,
                                    record_reale_idx=ix_g,
                                )
                            else:
                                sh_list[ix_g]['Esito_Reale'] = 'Ignorata (Tengo)'
                                _save_j(SHADOW_FILE, sh_list)
                            st.rerun()
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
            st.info('📭 Nessuna operazione registrata. I segnali del Pilota Automatico vengono registrati automaticamente all\'avvio della Home.')


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
    with st.spinner(f"Verifica 4 Regole (Tecnica & Tom Nash) in corso su {len(tks)} titoli..."):
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
                pre_tag = " | ⏳ PRE-IGN" if is_pre_ign else ""
                _tk_comp = f"{tk} ${p_cur:.2f} ({var_pct:+.1f}%)"
                det_ign_full = f"Score {s_score}{pre_tag} | {det_ign}"
                righe.append({"Titolo": _tk_comp, "Motore": "🚀 IGNITION", "Esito": "✅ PASSA" if ok_ign else "❌ NO", "Dettaglio Criteri (✅ Passa | ❌ Manca)": det_ign_full})
                righe.append({"Titolo": tk, "Motore": "🟢 BY FABIO", "Esito": "✅ PASSA" if ok_fab else "❌ NO", "Dettaglio Criteri (✅ Passa | ❌ Manca)": det_fab})
                righe.append({"Titolo": tk, "Motore": "🔵 BY Standard", "Esito": "✅ PASSA" if ok_std else "❌ NO", "Dettaglio Criteri (✅ Passa | ❌ Manca)": det_std})

                # 4a riga diagnostica SEMPRE presente (titoli in portafoglio e non): Scudo Tom Nash & Stato PAC/Spot
                inf_sal = salute_map_chk.get(tk) if isinstance(salute_map_chk, dict) else None
                in_port = tk in port_map_chk
                q_pac_p, q_spot_p, pac_sosp = 0.0, 0.0, False
                if in_port:
                    pos_p = port_map_chk[tk]
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
                sec_buys_p = int(inf_sal.get("sec_buys") or 0) if isinstance(inf_sal, dict) else 0

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

                if in_port:
                    # Motivo positivo chiaro per titoli posseduti in portafoglio
                    motivi_prot = []
                    if scudo_ok:
                        motivi_prot.append(f"Scudo Tom Nash ({nota_tn})")
                    if q_pac_p > 1e-6 and q_spot_p > 1e-6:
                        motivi_prot.append(f"{'PAC Sospeso Long' if pac_sosp else 'PAC Attivo'} + Spot ({q_pac_p:.2f} PAC + {q_spot_p:.2f} Spot)")
                    elif q_pac_p > 1e-6:
                        motivi_prot.append("PAC Sospeso Long" if pac_sosp else "PAC Attivo")
                    if sec_buys_p > 0:
                        motivi_prot.append(f"{sec_buys_p} acq. Insider SEC 90gg")

                    if motivi_prot:
                        esito_tn = "🛡️ PROTETTO"
                        det_tn_str = f"🛡️ Protetto da {' + '.join(motivi_prot)}"
                        if not scudo_ok and nota_tn and nota_tn != "Dati fondamentali N/D":
                            det_tn_str += f" | {nota_tn}"
                    else:
                        esito_tn = "⚪ MONITORA"
                        det_tn_str = f"📂 Posizione Spot ({nota_tn})"
                else:
                    # Titoli non ancora in portafoglio: mostra comunque la 4a riga (Scudo Tom Nash + Non in portafoglio)
                    if scudo_ok:
                        esito_tn = "🛡️ SANO"
                        det_tn_str = f"🛡️ Scudo Tom Nash ATTIVO ({nota_tn}) | Non in portafoglio"
                    else:
                        esito_tn = "⚪ NEUTRO"
                        det_tn_str = f"ℹ️ Fondamentali: {nota_tn} | Non in portafoglio"

                if badge_m:
                    det_tn_str += f" | {badge_m}"

                righe.append({
                    "Titolo": tk,
                    "Motore": "🛡️ Tom Nash & PAC",
                    "Esito": esito_tn,
                    "Dettaglio Criteri (✅ Passa | ❌ Manca)": det_tn_str,
                })
            except Exception as ex:
                righe.append({"Titolo": tk, "Motore": "Errore", "Esito": "❌", "Dettaglio Criteri (✅ Passa | ❌ Manca)": str(ex)[:50]})
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
            "Titolo": st.column_config.TextColumn("Titolo", width="small"),
            "Motore": st.column_config.TextColumn("Motore", width="medium"),
            "Esito": st.column_config.TextColumn("Esito", width="small"),
            "Dettaglio Criteri (✅ Passa | ❌ Manca)": st.column_config.TextColumn("Dettaglio Criteri (✅ Passa | ❌ Manca)", width="large"),
        },
    )
