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
    "2025/26": "https://www.fantacalcio.it/statistiche-serie-a/2025-26/statistico/riepilogo",
    "2024/25": "https://www.fantacalcio.it/statistiche-serie-a/2024-25/statistico/riepilogo",
    "2023/24": "https://www.fantacalcio.it/statistiche-serie-a/2023-24/statistico/riepilogo",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
        "Mobile/15E148 Safari/604.1"
    )
}


def clean(value):
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def num(value):
    if pd.isna(value):
        return None
    text = str(value).strip().replace(",", ".")
    text = re.sub(r"[^0-9.\-]", "", text)
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def find_col(df, names):
    for name in names:
        name = name.lower()
        for column in df.columns:
            if column == name or name in column:
                return column
    return None


@st.cache_data(ttl=21600, show_spinner=False)
def get_tables(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=(10, 25),
        allow_redirects=True,
    )
    response.raise_for_status()
    return pd.read_html(StringIO(response.text))


def parse_season(season, url):
    tables = get_tables(url)
    best = None
    best_score = -1

    for table in tables:
        if table.empty:
            continue

        table = table.copy()
        table.columns = [
            re.sub(r"\s+", " ", str(column)).strip().lower()
            for column in table.columns
        ]

        score = 0
        if find_col(table, ["nome", "giocatore", "player"]):
            score += 5
        if find_col(table, ["mv", "media voto"]):
            score += 3
        if find_col(table, ["fm", "fantamedia"]):
            score += 3
        if find_col(table, ["pv", "presenze", "partite"]):
            score += 2
        if len(table) >= 10:
            score += 2

        if score > best_score:
            best = table
            best_score = score

    if best is None or best_score < 4:
        raise RuntimeError(
            f"Tabella statistiche non riconosciuta per {season}."
        )

    name_col = find_col(best, ["nome", "giocatore", "player"])
    role_col = find_col(best, ["ruolo", "role"])
    team_col = find_col(best, ["squadra", "team", "club"])
    mv_col = find_col(best, ["mv", "media voto", "media"])
    fm_col = find_col(best, ["fm", "fantamedia"])
    pv_col = find_col(best, ["pv", "presenze", "partite"])
    goals_col = find_col(best, ["gol", "reti"])
    assists_col = find_col(best, ["assist"])

    rows = []

    for _, row in best.iterrows():
        name = clean(row.get(name_col, ""))

        if not name or name.lower() in {"nome", "giocatore", "player"}:
            continue

        rows.append(
            {
                "giocatore": name,
                "ruolo": clean(row.get(role_col, "")) if role_col else "",
                "squadra": clean(row.get(team_col, "")) if team_col else "",
                f"mv_{season}": num(row.get(mv_col)) if mv_col else None,
                f"fm_{season}": num(row.get(fm_col)) if fm_col else None,
                f"pv_{season}": num(row.get(pv_col)) if pv_col else None,
                f"gol_{season}": num(row.get(goals_col)) if goals_col else None,
                f"assist_{season}": num(row.get(assists_col)) if assists_col else None,
            }
        )

    result = pd.DataFrame(rows)

    if result.empty:
        raise RuntimeError(f"Nessun giocatore estratto per {season}.")

    result["key"] = (
        result["giocatore"]
        .astype(str)
        .str.lower()
        .str.replace(r"[^a-zàèéìòù0-9 ]", "", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    return result


@st.cache_data(ttl=21600, show_spinner=False)
def build_database():
    datasets = {}
    errors = {}

    for season, url in SEASONS.items():
        try:
            datasets[season] = parse_season(season, url)
        except Exception as exc:
            errors[season] = str(exc)

    if not datasets:
        details = " | ".join(
            f"{season}: {error}" for season, error in errors.items()
        )
        raise RuntimeError(
            "Nessuna stagione è stata recuperata. " + details
        )

    latest = datasets.get("2025/26", next(iter(datasets)))
    database = datasets[latest].copy()

    for season, dataset in datasets.items():
        if season == latest:
            continue

        extra = dataset.drop(
            columns=["giocatore", "ruolo", "squadra"],
            errors="ignore",
        )

        database = database.merge(extra, on="key", how="left")

    fm_columns = [
        column for column in database.columns if column.startswith("fm_")
    ]
    mv_columns = [
        column for column in database.columns if column.startswith("mv_")
    ]

    if fm_columns:
        database["fm_media_3anni"] = (
            database[fm_columns]
            .apply(pd.to_numeric, errors="coerce")
            .mean(axis=1)
        )
    else:
        database["fm_media_3anni"] = float("nan")

    if mv_columns:
        database["mv_media_3anni"] = (
            database[mv_columns]
            .apply(pd.to_numeric, errors="coerce")
            .mean(axis=1)
        )
    else:
        database["mv_media_3anni"] = float("nan")

    database["score"] = (
        database["fm_media_3anni"].fillna(0) * 0.70
        + database["mv_media_3anni"].fillna(0) * 0.30
    )

    return database, datasets, errors


with st.expander("⚙️ Stato database", expanded=True):
    try:
        with st.spinner("Recupero e preparo le tre stagioni…"):
            database, datasets, errors = build_database()

        st.success(
            f"Database pronto • {len(database)} giocatori • "
            f"{len(datasets)} stagioni"
        )

        for season, error in errors.items():
            st.warning(f"{season}: {error}")

        if st.button("🔄 Aggiorna database"):
            build_database.clear()
            st.rerun()

    except Exception as exc:
        st.error("Il database non è stato costruito.")
        st.code(str(exc))
        st.stop()


roles = ["Tutti"] + [
    role
    for role in ["P", "D", "C", "A"]
    if role in set(database["ruolo"].astype(str))
]

selected_role = st.segmented_control(
    "Ruolo",
    roles,
    default="Tutti",
)

if selected_role and selected_role != "Tutti":
    database = database[
        database["ruolo"].astype(str) == selected_role
    ]

query = st.text_input(
    "🔎 Cerca giocatore",
    placeholder="Lautaro, Barella, Dimarco…",
)

if query:
    database = database[
        database["giocatore"].str.contains(
            query,
            case=False,
            na=False,
        )
    ]

sorts = {
    "Indice FantaScout": "score",
    "FM media 3 anni": "fm_media_3anni",
    "MV media 3 anni": "mv_media_3anni",
    "FM 2025/26": "fm_2025/26",
    "MV 2025/26": "mv_2025/26",
}

available_sorts = {
    label: column
    for label, column in sorts.items()
    if column in database.columns
}

sort_label = st.selectbox(
    "Ordina per",
    list(available_sorts.keys()),
)

database = database.sort_values(
    available_sorts[sort_label],
    ascending=False,
    na_position="last",
)

st.caption(f"{len(database)} giocatori")

for _, player in database.iterrows():
    score = player.get("score")
    score_text = (
        f"{float(score):.2f}"
        if pd.notna(score)
        else "—"
    )

    with st.container():
        st.markdown(
            '<div class="card">',
            unsafe_allow_html=True,
        )

        player_name = player.get("giocatore", "—")
        player_role = player.get("ruolo", "—")
        player_team = player.get("squadra", "—")

        st.markdown(
            f"### {player_name}\n"
            f"`{player_role}` · **{player_team}** · "
            f"Indice **{score_text}**"
        )

        c1, c2, c3, c4 = st.columns(4)

        metrics = [
            (c1, "FM 3a", "fm_media_3anni"),
            (c2, "MV 3a", "mv_media_3anni"),
            (c3, "FM 25/26", "fm_2025/26"),
            (c4, "MV 25/26", "mv_2025/26"),
        ]

        for column, label, key in metrics:
            value = player.get(key)

            if pd.isna(value):
                text = "—"
            else:
                text = f"{float(value):.2f}"

            column.metric(label, text)

        with st.expander("📊 Storico"):
            history = []

            for season in ["2025/26", "2024/25", "2023/24"]:
                history.append(
                    {
                        "Stagione": season,
                        "Club": player.get(
                            f"squadra_{season}",
                            "—",
                        ),
                        "FM": player.get(
                            f"fm_{season}",
                            "—",
                        ),
                        "MV": player.get(
                            f"mv_{season}",
                            "—",
                        ),
                        "Presenze": player.get(
                            f"pv_{season}",
                            "—",
                        ),
                        "Gol": player.get(
                            f"gol_{season}",
                            "—",
                        ),
                        "Assist": player.get(
                            f"assist_{season}",
                            "—",
                        ),
                    }
                )

            st.dataframe(
                pd.DataFrame(history),
                hide_index=True,
                use_container_width=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)

st.divider()
st.caption(
    "FantaScout • dati recuperati online; "
    "verifica sempre le fonti prima dell'asta."
)