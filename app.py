import streamlit as st
import pandas as pd

st.set_page_config(page_title="FantaScout 26/27", page_icon="⚽", layout="centered")

st.markdown("""
<style>
.block-container {padding: 1rem .8rem 4rem; max-width: 900px;}
h1 {font-size: 1.8rem !important;}
.player-card {padding:.8rem;border:1px solid rgba(128,128,128,.25);border-radius:14px;margin-bottom:.7rem}
</style>
""", unsafe_allow_html=True)

st.title("⚽ FantaScout 26/27")
st.caption("Ranking mobile per l'asta")

@st.cache_data
def load_data():
    return pd.read_csv("data.csv")

try:
    df = load_data()
except Exception:
    st.warning("Database non ancora presente.")
    st.info("Carica `data.csv` nel repository GitHub e poi riavvia l'app.")
    st.stop()

required = ["giocatore", "ruolo", "squadra"]
missing = [c for c in required if c not in df.columns]
if missing:
    st.error("Colonne mancanti: " + ", ".join(missing))
    st.stop()

ruoli = ["Tutti"] + [r for r in ["P","D","C","A"] if r in df["ruolo"].astype(str).unique()]
ruolo = st.segmented_control("Ruolo", ruoli, default="Tutti")
if ruolo and ruolo != "Tutti":
    df = df[df["ruolo"].astype(str) == ruolo]

q = st.text_input("🔎 Cerca giocatore", placeholder="es. Lautaro, Barella...")
if q:
    df = df[df["giocatore"].astype(str).str.contains(q, case=False, na=False)]

sorts = {
    "Indice FantaScout": "score",
    "Fantamedia 25/26": "fm_25_26",
    "Media voto 25/26": "mv_25_26",
    "Bonus medi 25/26": "bonus_25_26",
}
sort_label = st.selectbox("Ordina per", list(sorts))
if sorts[sort_label] in df.columns:
    df = df.sort_values(sorts[sort_label], ascending=False, na_position="last")

st.caption(f"{len(df)} giocatori")

for _, r in df.iterrows():
    with st.container():
        st.markdown('<div class="player-card">', unsafe_allow_html=True)
        score = r.get("score", "—")
        score = f"{float(score):.2f}" if pd.notna(score) and score != "—" else "—"
        st.markdown(f"**{r['giocatore']}** · {r['ruolo']} · {r['squadra']} · **{score}**")

        c1,c2,c3,c4 = st.columns(4)
        for c, label, key in [
            (c1,"FM","fm_25_26"),(c2,"MV","mv_25_26"),
            (c3,"Bonus","bonus_25_26"),(c4,"Infortuni","inj_25_26")]:
            v = r.get(key, "—")
            if pd.notna(v) and v != "—":
                v = f"{float(v):.2f}" if label != "Infortuni" else str(int(float(v)))
            c.metric(label, v)

        with st.expander("📊 Storico 3 stagioni"):
            rows=[]
            for season,suf in [("2025/26","25_26"),("2024/25","24_25"),("2023/24","23_24")]:
                rows.append({
                    "Stagione":season,
                    "Club":r.get(f"club_{suf}","—"),
                    "FM":r.get(f"fm_{suf}","—"),
                    "MV":r.get(f"mv_{suf}","—"),
                    "Bonus":r.get(f"bonus_{suf}","—"),
                    "Infortuni":r.get(f"inj_{suf}","—")
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        if str(r.get("nuovo_arrivo","")).lower() in ("si","sì","yes","true","1"):
            st.info(f"🆕 Nuovo arrivo · provenienza: {r.get('club_precedente','da verificare')}")
        st.markdown("</div>", unsafe_allow_html=True)

st.divider()
st.caption("Verifica sempre dati, rose e indisponibili sulle fonti ufficiali prima dell'asta.")
