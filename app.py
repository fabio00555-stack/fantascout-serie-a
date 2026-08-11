import re, time
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import urljoin

st.set_page_config(page_title="FantaScout 26/27", page_icon="⚽", layout="centered")

st.markdown("""
<style>
.block-container{padding:.8rem .7rem 4rem;max-width:900px}
h1{font-size:1.75rem!important}
.player{padding:.75rem;border:1px solid rgba(128,128,128,.25);border-radius:14px;margin:.55rem 0}
.small{opacity:.7;font-size:.8rem}
</style>
""", unsafe_allow_html=True)

BASE="https://www.fantacalcio.it"
HEAD={"User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"}
SEASONS=["2025-26","2024-25","2023-24"]

@st.cache_data(ttl=12*3600)
def get(url):
    r=requests.get(url,headers=HEAD,timeout=30)
    r.raise_for_status()
    return r.text

def num(x):
    if pd.isna(x): return None
    m=re.search(r"-?\d+(?:[.,]\d+)?",str(x))
    return float(m.group().replace(",",".")) if m else None

def clean_name(x):
    return re.sub(r"\s+"," ",str(x)).strip()

@st.cache_data(ttl=12*3600)
def season_table(season):
    urls=[
        f"{BASE}/statistiche-serie-a/{season}/italia/riepilogo",
        f"{BASE}/statistiche-serie-a/{season}/italia",
        f"{BASE}/statistiche-serie-a/{season}",
    ]
    html=None
    for u in urls:
        try:
            html=get(u); break
        except Exception: pass
    if not html: raise RuntimeError(f"Statistiche {season} non raggiungibili")
    tables=pd.read_html(html)
    candidates=[]
    for t in tables:
        cols=[str(c).strip() for c in t.columns]
        if "MV" in cols and "FM" in cols and "PV" in cols:
            t=t.copy(); t.columns=cols
            candidates.append(t)
    if not candidates: raise RuntimeError(f"Tabella statistiche {season} non trovata")
    df=candidates[0]
    # normalizza nomi
    name_col=next((c for c in df.columns if "Calciatore" in c), df.columns[0])
    df=df.rename(columns={name_col:"giocatore"})
    for c in ["PV","MV","FM","Gf","Ass","RP"]:
        if c not in df.columns: df[c]=0
    for c in ["PV","MV","FM","Gf","Ass","RP"]:
        df[c]=df[c].map(num)
    df["giocatore"]=df["giocatore"].map(clean_name)
    df["bonus_gara"]=((df["Gf"].fillna(0)*3)+(df["Ass"].fillna(0))+(df["RP"].fillna(0)*3))/df["PV"].replace(0,pd.NA)
    return df[["giocatore","PV","MV","FM","Gf","Ass","RP","bonus_gara"]].dropna(subset=["giocatore"])

@st.cache_data(ttl=12*3600)
def current_list():
    urls=[
        f"{BASE}/quotazioni-fantacalcio/2026-27",
        f"{BASE}/quotazioni-fantacalcio",
    ]
    html=None
    for u in urls:
        try: html=get(u); break
        except Exception: pass
    if not html: raise RuntimeError("Listone 2026/27 non raggiungibile")
    tables=pd.read_html(html)
    for t in tables:
        t=t.copy(); t.columns=[str(c).strip() for c in t.columns]
        cols=" ".join(t.columns).lower()
        if any(x in cols for x in ["fvm","quot","calciatore","ruolo"]):
            # best effort: map likely columns
            name=next((c for c in t.columns if c.lower() in ["calciatore","nome","giocatore"]),None)
            role=next((c for c in t.columns if c.lower() in ["r","ruolo","role"]),None)
            team=next((c for c in t.columns if c.lower() in ["squadra","sq","team"]),None)
            if name:
                out=pd.DataFrame({"giocatore":t[name].map(clean_name)})
                out["ruolo"]=t[role].astype(str) if role else "?"
                out["squadra"]=t[team].astype(str) if team else "?"
                for src,dst in [("FVM","fvm"),("Quotazione","quotazione"),("Q","quotazione")]:
                    c=next((x for x in t.columns if x.lower()==src.lower()),None)
                    if c: out[dst]=t[c].map(num)
                return out.drop_duplicates("giocatore")
    raise RuntimeError("Formato listone non riconosciuto")

def score(df):
    # 55% FM, 30% MV, 15% bonus medio. Minimo 10 PV totali per evitare micro-campioni.
    p=df["PV"].sum()
    if p<=0: return None
    fm=(df["FM"]*df["PV"]).sum()/p
    mv=(df["MV"]*df["PV"]).sum()/p
    bm=(df["bonus_gara"].fillna(0)*df["PV"]).sum()/p
    return .55*fm+.30*mv+.15*bm

st.title("⚽ FantaScout 26/27")
st.caption("Database dinamico • Fantacalcio® storico 3 stagioni")

if st.button("🔄 Aggiorna database"):
    st.cache_data.clear(); st.rerun()

try:
    current=current_list()
    stats={s:season_table(s) for s in SEASONS}
except Exception as e:
    st.error("Non riesco a recuperare il database automatico.")
    st.code(str(e))
    st.stop()

# join names; use current list as universe
result=current.copy()
for s in SEASONS:
    x=stats[s].copy()
    x=x.rename(columns={c:f"{c}_{s}" for c in x.columns if c!="giocatore"})
    result=result.merge(x,on="giocatore",how="left")

result["pv_3anni"]=result[[f"PV_{s}" for s in SEASONS]].fillna(0).sum(axis=1)

def row_score(r):
    d=[]
    for s in SEASONS:
        if pd.notna(r.get(f"PV_{s}")):
            d.append(pd.Series({
                "PV":r[f"PV_{s}"],"FM":r[f"FM_{s}"],"MV":r[f"MV_{s}"],
                "bonus_gara":r[f"bonus_gara_{s}"]
            }))
    return score(pd.DataFrame(d)) if d else None
result["score"]=result.apply(row_score,axis=1)
result["nuovo_arrivo"]=result["pv_3anni"].eq(0)

role_opts=["Tutti"]+[x for x in ["P","D","C","A"] if x in result["ruolo"].astype(str).unique()]
role=st.segmented_control("Ruolo",role_opts,default="Tutti")
if role and role!="Tutti": result=result[result["ruolo"].astype(str)==role]

q=st.text_input("🔎 Cerca",placeholder="Nome giocatore")
if q: result=result[result["giocatore"].str.contains(q,case=False,na=False)]

sort=st.selectbox("Ordina",["Indice FantaScout","FM 25/26","MV 25/26","Bonus/gara 25/26","PV 3 anni"])
sortmap={"Indice FantaScout":"score","FM 25/26":"FM_2025-26","MV 25/26":"MV_2025-26","Bonus/gara 25/26":"bonus_gara_2025-26","PV 3 anni":"pv_3anni"}
result=result.sort_values(sortmap[sort],ascending=False,na_position="last")

st.caption(f"{len(result)} giocatori • aggiornamento automatico")

for _,r in result.iterrows():
    with st.container():
        st.markdown('<div class="player">',unsafe_allow_html=True)
        sc="—" if pd.isna(r["score"]) else f"{r['score']:.2f}"
        st.markdown(f"**{r['giocatore']}** · {r['ruolo']} · {r['squadra']} · **{sc}**")
        c=st.columns(4)
        for col,label,key in [(c[0],"FM","FM_2025-26"),(c[1],"MV","MV_2025-26"),(c[2],"Bonus/g","bonus_gara_2025-26"),(c[3],"PV 3a","pv_3anni")]:
            v=r.get(key)
            col.metric(label,"—" if pd.isna(v) else (f"{v:.2f}" if label!="PV 3a" else str(int(v))))
        with st.expander("📊 Storico"):
            rows=[]
            for s in SEASONS:
                rows.append({"Stagione":s,"PV":r.get(f"PV_{s}"),"MV":r.get(f"MV_{s}"),"FM":r.get(f"FM_{s}"),"Bonus/gara":r.get(f"bonus_gara_{s}")})
            st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
        if bool(r["nuovo_arrivo"]):
            st.info("🆕 Nessuna presenza a voto nelle tre stagioni di Serie A analizzate.")
        st.markdown("</div>",unsafe_allow_html=True)

st.divider()
st.caption("Fonti statistiche: Fantacalcio® Serie A. Il bonus medio è calcolato da gol, assist e rigori parati per partita a voto. Le giornate di infortunio richiedono il dettaglio dei profili individuali e verranno aggiunte come modulo separato per evitare stime.")
