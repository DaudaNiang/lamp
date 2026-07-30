"""
app.py — Interface Streamlit du scraper CDE : Résidences Étudiantes Privées.

Lancement :
    streamlit run app.py
"""

import queue
import threading
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from utils.geo import ALL_REGIONS
from utils.residence_dedup import ResidenceDedupManager
from utils.residence_exporter import (
    RESIDENCE_CSV_COLUMNS,
    RESIDENCE_DOUBLONS_FILE,
    RESIDENCE_PROSPECTS_FILE,
    RESIDENCE_SESSIONS_DIR,
    ensure_data_dir,
    generate_summary_stats,
    list_sessions,
    read_prospects_df,
    read_session_df,
)
from utils.residence_taxonomy import KNOWN_CHAIN_DOMAINS
from scrapers.residences_pj import RESIDENCE_QUERIES

st.set_page_config(
    page_title="CDE Résidences Étudiantes",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

ensure_data_dir()


# ─── Sidebar ─────────────────────────────────────────────────────────────────

def render_sidebar() -> dict:
    st.sidebar.title("Configuration")

    st.sidebar.subheader("Paramètres")
    max_pages = st.sidebar.slider("Pages max par ville (Pages Jaunes)", 1, 10, 2)
    delay = st.sidebar.slider("Délai entre requêtes (s)", 1.0, 5.0, 2.0, step=0.5)
    fetch_details = st.sidebar.checkbox(
        "Récupérer Email + Instagram (plus lent)", value=True,
        help="Visite le site officiel de chaque résidence pour extraire email et Instagram.",
    )

    st.sidebar.divider()
    st.sidebar.subheader("Base de données")
    df_existing = read_prospects_df()
    df_dupes = read_prospects_df(RESIDENCE_DOUBLONS_FILE)

    col1, col2 = st.sidebar.columns(2)
    col1.metric("Résidences", len(df_existing))
    col2.metric("Doublons évités", len(df_dupes))

    st.sidebar.caption(
        "Déduplication **cross-session** — aucune résidence ajoutée deux fois."
    )

    if not df_existing.empty:
        csv_bytes = df_existing.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.sidebar.download_button(
            label="Télécharger résidences CSV",
            data=csv_bytes,
            file_name=f"residences_CDE_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    return {
        "max_pages": max_pages,
        "delay": delay,
        "fetch_details": fetch_details,
    }


# ─── Thread de scraping ──────────────────────────────────────────────────────

def run_scraping_thread(
    config: dict,
    selected_queries: list,
    selected_locations: list,
    log_queue: queue.Queue,
):
    """Exécuté dans un thread séparé."""
    try:
        from scrapers.residences_pj import ResidencePagesJaunesScraper

        dedup = ResidenceDedupManager()
        log_queue.put(f"Base chargée : {len(dedup.known_keys)} résidences connues")

        scraper = ResidencePagesJaunesScraper(delay=config["delay"])
        all_raw = []

        def cb(msg):
            log_queue.put(msg)

        total_combos = max(len(selected_locations), 1)
        combo_num = 0

        for location in selected_locations:
            combo_num += 1
            log_queue.put({"progress_pct": max(1, int(combo_num / total_combos * 90))})
            log_queue.put(f"\n[{combo_num}/{total_combos}] Résidences @ {location}")

            results = scraper.scrape(
                location=location,
                queries=selected_queries,
                max_pages=config["max_pages"],
                fetch_details=config["fetch_details"],
                progress_callback=cb,
            )
            all_raw.extend(results)

        log_queue.put(f"\nTotal brut : {len(all_raw)} résidences privées trouvées")
        log_queue.put({"progress_pct": 91})

        # ── Regroupement des chaînes nationales ──────────────────────────────
        # Studéa/UXCO/etc. partagent le même Instagram/site pour toutes leurs
        # résidences : on regroupe en UNE ligne de contact par gestionnaire.
        from utils.residence_exporter import group_chain_residences
        n_before = len(all_raw)
        all_raw = group_chain_residences(all_raw)
        n_chains = sum(1 for r in all_raw if r.get("Gestionnaire"))
        log_queue.put(
            f"Regroupement chaînes : {n_before} résidences → {len(all_raw)} contacts "
            f"({n_chains} gestionnaires nationaux)"
        )
        log_queue.put({"progress_pct": 92})

        # ── Déduplication ──────────────────────────────────────────────────
        log_queue.put("Déduplication cross-sessions...")
        for residence in all_raw:
            dedup.check_and_register(residence)

        log_queue.put({"progress_pct": 96})
        new_count, dupe_count = dedup.flush_to_disk()
        log_queue.put(
            f"Terminé — {new_count} nouvelles résidences | {dupe_count} doublons évités"
        )
        log_queue.put({
            "done": True,
            "new_count": new_count,
            "dupe_count": dupe_count,
            "total": len(dedup.known_keys),
        })

    except Exception as e:
        import traceback
        log_queue.put(f"Erreur : {e}\n{traceback.format_exc()}")
        log_queue.put({"done": True, "error": str(e), "new_count": 0, "dupe_count": 0, "total": 0})


# ─── Onglet "Lancer" ─────────────────────────────────────────────────────────

def render_scrape_tab(config: dict):
    st.header("Lancer un scraping de résidences")

    st.subheader("1. Types de recherche")
    st.caption("Requêtes utilisées pour découvrir les résidences privées (via Pages Jaunes).")

    selected_queries = []
    cols = st.columns(4)
    for i, q in enumerate(RESIDENCE_QUERIES):
        checked = cols[i % 4].checkbox(q, value=True, key=f"query_{i}")
        if checked:
            selected_queries.append(q)

    st.subheader("2. Zone géographique")
    st.caption("Clique sur une région pour voir ses villes.")

    selected_locations = []

    for region_name, cities in ALL_REGIONS.items():
        expanded = region_name == "Île-de-France"
        with st.expander(f"{region_name} ({len(cities)} villes)", expanded=expanded):
            col_all, col_none, _ = st.columns([1, 1, 4])
            if col_all.button("Tout cocher", key=f"sel_all_{region_name}"):
                for city in cities:
                    st.session_state[f"rcity_{city}"] = True
            if col_none.button("Tout décocher", key=f"desel_all_{region_name}"):
                for city in cities:
                    st.session_state[f"rcity_{city}"] = False

            city_cols = st.columns(4)
            for i, city in enumerate(cities):
                key = f"rcity_{city}"
                default_city = region_name == "Île-de-France" and city == "Paris"
                checked = city_cols[i % 4].checkbox(
                    city, value=st.session_state.get(key, default_city), key=key,
                )
                if checked:
                    selected_locations.append(city)

    st.divider()

    n_queries = len(selected_queries)
    n_locs = len(selected_locations)
    n_combos = n_queries * n_locs
    est_minutes = round(n_combos * config["max_pages"] * 3 / 60, 1)

    if n_queries == 0 or n_locs == 0:
        st.warning("Sélectionne au moins **un type de recherche** et **une ville** pour lancer.")
        return

    with st.expander("Résumé avant lancement", expanded=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("Requêtes", n_queries)
        c2.metric("Villes", n_locs)
        c3.metric("Durée estimée", f"~{est_minutes} min")

    if st.button("Lancer le scraping", type="primary", use_container_width=True):
        log_queue = queue.Queue()
        thread = threading.Thread(
            target=run_scraping_thread,
            args=(config, selected_queries, selected_locations, log_queue),
            daemon=True,
        )
        thread.start()

        log_placeholder = st.empty()
        progress_bar = st.progress(1, text="Démarrage...")
        status_text = st.empty()
        logs = []

        while True:
            try:
                msg = log_queue.get(timeout=0.4)
            except queue.Empty:
                if not thread.is_alive():
                    progress_bar.progress(100, text="Terminé")
                    status_text.warning("Le scraping s'est terminé de manière inattendue.")
                    break
                continue

            if isinstance(msg, dict):
                if msg.get("done"):
                    st.session_state["last_scrape_result"] = msg
                    progress_bar.progress(100, text="Terminé !")
                    if msg.get("error"):
                        status_text.error(f"Erreur : {msg['error']}")
                    else:
                        status_text.success(
                            f"**{msg['new_count']} nouvelles résidences** | "
                            f"{msg['dupe_count']} doublons évités"
                        )
                    break
                elif "progress_pct" in msg:
                    pct = max(1, min(99, int(msg["progress_pct"])))
                    progress_bar.progress(pct, text=f"En cours… {pct} %")
                continue

            logs.append(str(msg))
            log_placeholder.code("\n".join(logs[-40:]), language=None)

        thread.join(timeout=5)
        st.rerun()

    if "last_scrape_result" in st.session_state:
        result = st.session_state["last_scrape_result"]
        if not result.get("error"):
            r1, r2, r3 = st.columns(3)
            r1.metric("Nouvelles résidences", result.get("new_count", 0))
            r2.metric("Doublons évités", result.get("dupe_count", 0))
            r3.metric("Total en base", result.get("total", 0))


# ─── Onglet "Résultats" ──────────────────────────────────────────────────────

def _delete_session(session_path):
    """Supprime un fichier de session et reconstruit le fichier consolidé."""
    try:
        session_path = Path(session_path)
        if session_path.exists():
            session_path.unlink()
        all_dfs = []
        for f in RESIDENCE_SESSIONS_DIR.glob("session_*.csv"):
            try:
                df = pd.read_csv(f, encoding="utf-8-sig", dtype=str)
                all_dfs.append(df)
            except Exception:
                continue
        if all_dfs:
            combined = pd.concat(all_dfs, ignore_index=True)
            for col in RESIDENCE_CSV_COLUMNS:
                if col not in combined.columns:
                    combined[col] = ""
            combined[RESIDENCE_CSV_COLUMNS].to_csv(
                RESIDENCE_PROSPECTS_FILE, index=False, encoding="utf-8-sig"
            )
        elif RESIDENCE_PROSPECTS_FILE.exists():
            RESIDENCE_PROSPECTS_FILE.unlink()
    except Exception:
        pass


def render_results_tab():
    st.header("Résultats")

    sessions = list_sessions()
    df_all = read_prospects_df()
    df_dupes = read_prospects_df(RESIDENCE_DOUBLONS_FILE)

    stats_all = generate_summary_stats(df_all)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total résidences", len(df_all))
    m2.metric("Sessions", len(sessions))
    m3.metric("Avec email", stats_all.get("with_email", 0))
    m4.metric("Avec Instagram", stats_all.get("with_instagram", 0))

    st.divider()

    if not sessions and df_all.empty:
        st.info("Aucune session de scraping. Lance un scraping pour commencer !")
        return

    st.subheader("Sessions de scraping")

    view_mode = st.radio(
        "Affichage", options=["Par session", "Tout combiné"],
        horizontal=True, label_visibility="collapsed",
    )

    if view_mode == "Par session":
        if not sessions:
            st.info("Les anciennes résidences sont dans le fichier consolidé. Choisis 'Tout combiné'.")
        else:
            for idx, sess in enumerate(sessions):
                session_num = len(sessions) - idx
                with st.expander(
                    f"Session {session_num} — {sess['date']} ({sess['count']} résidences)",
                    expanded=(idx == 0),
                ):
                    df_sess = read_session_df(sess["path"])
                    if df_sess.empty:
                        st.caption("Aucune résidence dans cette session.")
                        continue

                    fc = st.columns(3)
                    villes = sorted(df_sess["Ville"].dropna().unique())
                    gestionnaires = sorted(
                        g for g in df_sess["Gestionnaire"].dropna().unique() if g
                    )

                    sel_v = fc[0].multiselect("Ville", villes, placeholder="Toutes", key=f"sv_{idx}")
                    sel_g = fc[1].multiselect("Gestionnaire", gestionnaires, placeholder="Tous", key=f"sg_{idx}")

                    filtered = df_sess.copy()
                    if sel_v:
                        filtered = filtered[filtered["Ville"].isin(sel_v)]
                    if sel_g:
                        filtered = filtered[filtered["Gestionnaire"].isin(sel_g)]

                    st.caption(f"{len(filtered)} résidences affichées")

                    st.dataframe(
                        filtered,
                        use_container_width=True,
                        height=min(400, 40 + len(filtered) * 35),
                        column_config={
                            "Lien": st.column_config.LinkColumn("Lien"),
                            "Instagram": st.column_config.LinkColumn("Instagram"),
                        },
                    )

                    btn_cols = st.columns([3, 1])
                    csv_sess = df_sess.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                    btn_cols[0].download_button(
                        f"Télécharger ({sess['count']} résidences)",
                        data=csv_sess,
                        file_name=sess["filename"],
                        mime="text/csv",
                        key=f"dl_{idx}",
                    )
                    if btn_cols[1].button("Supprimer", key=f"del_{idx}", type="secondary"):
                        _delete_session(sess["path"])
                        st.rerun()

    else:
        if df_all.empty:
            st.info("Aucune résidence en base.")
            return

        fc = st.columns(3)
        villes = sorted(df_all["Ville"].dropna().unique()) if "Ville" in df_all.columns else []
        gestionnaires = sorted(
            g for g in df_all["Gestionnaire"].dropna().unique() if g
        ) if "Gestionnaire" in df_all.columns else []

        sel_villes = fc[0].multiselect("Ville", villes, placeholder="Toutes", key="all_v")
        sel_gest = fc[1].multiselect("Gestionnaire", gestionnaires, placeholder="Tous", key="all_g")
        tri = fc[2].selectbox("Trier par", ["Nom (A-Z)", "Ville (A-Z)"], index=0, key="all_tri")

        filtered = df_all.copy()
        if sel_villes:
            filtered = filtered[filtered["Ville"].isin(sel_villes)]
        if sel_gest:
            filtered = filtered[filtered["Gestionnaire"].isin(sel_gest)]
        if tri == "Nom (A-Z)":
            filtered = filtered.sort_values("Nom résidence", ascending=True, na_position="last")
        else:
            filtered = filtered.sort_values("Ville", ascending=True, na_position="last")

        st.caption(f"**{len(filtered)}** résidences sur **{len(df_all)}** total")

        st.dataframe(
            filtered,
            use_container_width=True,
            height=500,
            column_config={
                "Lien": st.column_config.LinkColumn("Lien"),
                "Instagram": st.column_config.LinkColumn("Instagram"),
            },
        )

    st.divider()

    st.subheader("Export CSV")
    if not df_all.empty:
        csv_all = df_all.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            "Télécharger TOUTES les résidences",
            data=csv_all,
            file_name=f"residences_CDE_complet_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.divider()

    if not df_all.empty:
        st.subheader("Répartitions")
        gc1, gc2 = st.columns(2)
        with gc1:
            if stats_all["by_gestionnaire"]:
                st.markdown("**Par gestionnaire**")
                st.bar_chart(pd.DataFrame(
                    list(stats_all["by_gestionnaire"].items()), columns=["Gestionnaire", "Nombre"]
                ).set_index("Gestionnaire"))
        with gc2:
            if stats_all["by_region"]:
                st.markdown("**Par région**")
                st.bar_chart(pd.DataFrame(
                    list(stats_all["by_region"].items()), columns=["Région", "Nombre"]
                ).set_index("Région"))

    st.divider()

    st.subheader("Supprimer les données")
    st.warning("Supprime toutes les résidences et toutes les sessions. Une sauvegarde est créée.")
    confirm = st.checkbox("Je confirme vouloir supprimer toutes les données")
    if confirm:
        if st.button("Supprimer toutes les données", type="primary"):
            from utils.residence_exporter import clear_residences
            ok = clear_residences(backup=True)
            if ok:
                st.success("Base vidée. Sauvegarde créée dans data/backups/.")
                if "last_scrape_result" in st.session_state:
                    del st.session_state["last_scrape_result"]
                st.rerun()
            else:
                st.error("Erreur lors de la suppression.")


# ─── Onglet "Gestionnaires connus" ───────────────────────────────────────────

def render_gestionnaires_tab():
    st.header("Gestionnaires nationaux connus")
    st.caption(
        "Ces réseaux de résidences étudiantes privées sont automatiquement "
        "détectés et étiquetés dans la colonne Gestionnaire lors du scraping."
    )

    for name, domain in KNOWN_CHAIN_DOMAINS.items():
        st.markdown(f"**{name}** — `{domain}`")


# ─── Onglet "Guide de lancement" ─────────────────────────────────────────────

def render_guide_tab():
    st.header("Comment lancer l'application")

    st.markdown("""
### Option 1 — Double-clic

1. Va dans le dossier **`scrap CDE`**
2. Double-clique sur **`Démarrer l'app.bat`**
3. Le navigateur s'ouvre sur `http://localhost:8502`
4. Pour arrêter : ferme la fenêtre noire

---

### Option 2 — Terminal

```
cd "C:\\Users\\niang\\Downloads\\scrap CDE"
python -m streamlit run app.py --server.port 8502
```

---

### Comment ça marche

Le scraper cherche sur **Pages Jaunes** des résidences étudiantes privées
(Studéa, UXCO, Cardinal Campus, etc.) via des requêtes ciblées
("résidence étudiante", "logement étudiant"...).

Pour chaque résidence trouvée :
- Le **site officiel** est identifié (pas la fiche Pages Jaunes générique)
- Le site est visité pour extraire l'**email** et le compte **Instagram**
- Les résidences **CROUS / logement social** sont automatiquement exclues
- Les gestionnaires nationaux connus sont étiquetés automatiquement

---

### Où sont les données ?

- `data/residences_CDE.csv` → résidences (import dans Google Sheets)
- `data/residences_doublons_CDE.csv` → doublons évités
- `data/residences_sessions/` → une session par lancement

**Import Google Sheets :** Fichier → Importer → CSV → Virgule → UTF-8

---

### Déduplication

Cross-session automatique : **Nom résidence + Ville**. Aucune résidence
ajoutée deux fois, même entre plusieurs lancements.
    """)


# ─── Point d'entrée ──────────────────────────────────────────────────────────

def main():
    st.title("CDE — Résidences Étudiantes Privées France")
    st.caption("Coin des Étudiants — Base de prospection pour partenariats avec les résidences privées")

    config = render_sidebar()

    tab_scrape, tab_results, tab_gest, tab_guide = st.tabs([
        "Scraping", "Résultats", "Gestionnaires connus", "Guide",
    ])

    with tab_scrape:
        render_scrape_tab(config)
    with tab_results:
        render_results_tab()
    with tab_gest:
        render_gestionnaires_tab()
    with tab_guide:
        render_guide_tab()


if __name__ == "__main__":
    main()
