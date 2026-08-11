import streamlit as st
import pandas as pd
import requests
from io import StringIO
import re

st.set_page_config(page_title="FantaScout 26/27", page_icon="⚽", layout="centered")

st.markdown("""
<style>
.block-container {padding:1rem .75rem 4rem;max-width:920px}
h1 {font-size:1.75rem!important}
.card {padding:.85rem;border:1px solid rgba(128,128,128,.25);border-radius:14px;margin-bottom:.7rem}
</style>
""", unsafe_allow_html=True)

st.title("⚽ FantaScout 26/27")
st.caption("Database storico • versione mobile")

SEASONS = {
    "2025/26":"https://www.fantacalcio.it/statistiche-serie-a/2025-26/statistico/riepilogo",
    "2024/25":"https://www.fantacalcio.it/statistiche-serie-a/2024-25/statistico/riepilogo",
    "2023/24":"https://www.fantacalcio.it/statistiche-serie-a/2023-24/statistico/riepilogo",
}
HEADERS={"User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"}

def clean(v):
    return re.sub(r"\s+"," ",str(v)).strip() if pd.notna(v) else ""

def num(v):
    if pd.isna(v): return None
    s=str(v).strip().replace(",",".")
    s=re.sub(r"[^0-9.\-]","",s)
    try: return float(s)
    except: return None

def col(df, names):
    for n in names:
        for c in df.columns:
            if c == n.lower() or n.lower() in c:
                return c
    return None

@st.cache_data(ttl=21600, show_spinner=False)
def get_tables(url):
    r=requests.get(url,headers=HEADERS,timeout=(10,25))
    r.raise_for_status()
    return pd.read_html(StringIO(r.text))

def parse(season,url):
    tables=get_tables(url)
    best=None; score=-1
    for t in tables:
        if t.empty: continue
        t=t.copy()
        t.columns=[re.sub(r"\s+"," ",str(c)).strip().lower() for c in t.columns]
        s=0
        if col(t,["nome","giocatore","player"]): s+=5
        if col(t,["mv","media voto"]): s+=3
        if col(t,["fm","fantamedia"]): s+=3
        if col(t,["pv","presenze","partite"]): s+=2
        if len(t)>=10: s+=2
        if s>score: best,score=t,s
    if best is None or score<4:
        raise RuntimeError(f"Tabella statistiche non riconosciuta per {season}.")
    nc=col(best,["nome","giocatore","player"])
    rc=col(best,["ruolo","role"])
    tc=col(best,["squadra","team","club"])
    mvc=col(best,["mv","media voto","media"])
    fmc=col(best,["fm","fantamedia"])
    pvc=col(best,["pv","presenze","partite"])
    gc=col(best,["gol","reti"])
    ac=col(best,["assist"])
    rows=[]
    for _,r in best.iterrows():
        name=clean(r.get(nc,""))
        if not name or name.lower() in ("nome","giocatore","player"): continue
        rows.append({
            "giocatore":name,
            "ruolo":clean(r.get(rc,"")) if rc else "",
            "squadra":clean(r.get(tc,"")) if tc else "",
            f"mv_{season}":num(r.get(mvc)) if mvc else None,
            f"fm_{season}":num(r.get(fmc)) if fmc else None,
            f"pv_{season}":num(r.get(pvc)) if pvc else None,
            f"gol_{season}":num(r.get(gc)) if gc else None,
            f"assist_{season}":num(r.get(ac)) if ac else None,
        })
    df=pd.DataFrame(rows)
    if df.empty: raise RuntimeError(f"Nessun giocatore estratto per {season}.")
    df["key"]=(df["giocatore"].str.lower()
               .str.replace(r"[^a-zàèéìòù0-9 ]","",regex=True)
               .str.replace(r"\s+"," ",regex=True).str.strip())
    return df

@st.cache_data(ttl=21600, show_spinner=False)
def build():
    data={}; errors={}
    for season,url in SEASONS.items():
        try: data[season]=parse(season,url)
        except Exception as e: errors[season]=str(e)
    if not data:
        raise RuntimeError("Nessuna stagione è stata recuperata. "+" | ".join(f"{s}: {e}" for s,e in errors.items()))
    latest=data.get("2025/26",next(iter(data)))
    db=data[latest].copy()
    for season,d in data.items():
        if season==latest: continue
        add=d.drop(columns=["giocatore","ruolo","squadra"],errors="ignore")
        db=db.merge(add,on="key",how="left")
    fm=[c for c in db if c.startswith("fm_")]
    mv=[c for c in db if c.startswith("mv_")]
    db["fm_media_3anni"]=db[fm].apply(pd.to_numeric,errors="coerce").mean(axis=1) if fm else float("nan")
    db["mv_media_3anni"]=db[mv].apply(pd.to_numeric,errors="coerce").mean(axis=1) if mv else float("nan")
    db["score"]=db["fm_media_3anni"].fillna(0)*.7+db["mv_media_3anni"].fillna(0)*.3
    return db,data,errors

with st.expander("⚙️ Stato database",expanded=True):
    try:
        with st.spinner("Recupero e preparo le tre stagioni…"):
            db,data,errors=build()
        st.success(f"Database pronto • {len(db)} giocatori • {len(data)} stagioni")
        for s,e in errors.items(): st.warning(f"{s}: {e}")
        if st.button("🔄 Aggiorna database"):
            build.clear(); st.rerun()
    except Exception as e:
        st.error("Il database non è stato costruito.")
        st.code(str(e))
        st.stop()

roles=["Tutti"]+[r for r in ["P","D","C","A"] if r in set(db["ruolo"].astype(str))]
role=st.segmented_control("Ruolo",roles,default="Tutti")
if role and role!="Tutti": db=db[db["ruolo"].astype(str)==role]

q=st.text_input("🔎 Cerca giocatore",placeholder="Lautaro, Barella, Dimarco…")
if q: db=db[db["giocatore"].str.contains(q,case=False,na=False)]

sorts={"Indice FantaScout":"score","FM media 3 anni":"fm_media_3anni","MV media 3 anni":"mv_media_3anni","FM 2025/26":"fm_2025/26","MV 2025/26":"mv_2025/26"}
sort_label=st.selectbox("Ordina per",[x for x,c in sorts.items() if c in db.columns])
db=db.sort_values(sorts[sort_label],ascending=False,na_position="last")
st.caption(f"{len(db)} giocatori")

for _,p in db.iterrows():
    score=p.get("score")
    score=f"{float(score):.2f}" if pd.notna(score) else "—"
    with st.container():
        st.markdown('<div class="card">',unsafe_allow_html=True)
        st.markdown(f"### {p.get('giocatore','—')}  
`{p.get('ruolo','—')}` · **{p.get('squadra','—')}** · Indice **{score}**")
        c1,c2,c3,c4=st.columns(4)
        for c,label,key in [(c1,"FM 3a","fm_media_3anni"),(c2,"MV 3a","mv_media_3anni"),(c3,"FM 25/26","fm_2025/26"),(c4,"MV 25/26","mv_2025/26")]:
            v=p.get(key)
            c.metric(label,"—" if pd.isna(v) else f"{float(v):.2f}")
        with st.expander("📊 Storico"):
            hist=[]
            for season in ["2025/26","2024/25","2023/24"]:
                hist.append({"Stagione":season,"Club":p.get(f"squadra_{season}","—"),"FM":p.get(f"fm_{season}","—"),"MV":p.get(f"mv_{season}","—"),"Presenze":p.get(f"pv_{season}","—"),"Gol":p.get(f"gol_{season}","—"),"Assist":p.get(f"assist_{season}","—")})
            st.dataframe(pd.DataFrame(hist),hide_index=True,use_container_width=True)
        st.markdown("</div>",unsafe_allow_html=True)

st.divider()
st.caption("FantaScout • dati recuperati online; verifica sempre le fonti prima dell'asta.")
