"""
app.py — Interface Streamlit du scraper CDE.

Lancement :
    streamlit run app.py
"""

import os
import queue
import threading
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from utils.categories import (
    STUDENT_JOB_CATEGORIES,
    CATEGORY_NAMES,
    classify_offer,
    get_category_icon,
)
from utils.qualifier import qualify_prospects
from utils.dedup import DedupManager
from utils.exporter import (
    CSV_COLUMNS,
    DOUBLONS_FILE,
    PROSPECTS_FILE,
    ensure_data_dir,
    generate_summary_stats,
    list_sessions,
    read_prospects_df,
    read_session_df,
)

st.set_page_config(
    page_title="CDE Jobs Étudiants",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

ensure_data_dir()

# ─── Données de localisation ─────────────────────────────────────────────────

ALL_REGIONS = {
    "Île-de-France": [
        "Paris", "Boulogne-Billancourt", "Saint-Denis", "Argenteuil", "Montreuil",
    ],
    "Auvergne-Rhône-Alpes": [
        "Lyon", "Grenoble", "Saint-Étienne", "Clermont-Ferrand", "Annecy",
    ],
    "Bourgogne-Franche-Comté": [
        "Dijon", "Besançon", "Chalon-sur-Saône", "Auxerre",
    ],
    "Bretagne": [
        "Rennes", "Brest", "Quimper", "Saint-Malo",
    ],
    "Centre-Val de Loire": [
        "Orléans", "Tours", "Bourges", "Blois",
    ],
    "Corse": [
        "Ajaccio", "Bastia",
    ],
    "Grand Est": [
        "Strasbourg", "Reims", "Metz", "Nancy",
    ],
    "Hauts-de-France": [
        "Lille", "Amiens", "Roubaix", "Dunkerque",
    ],
    "Normandie": [
        "Rouen", "Caen", "Le Havre",
    ],
    "Nouvelle-Aquitaine": [
        "Bordeaux", "Limoges", "Poitiers", "La Rochelle",
    ],
    "Occitanie": [
        "Toulouse", "Montpellier", "Nîmes", "Perpignan",
    ],
    "Pays de la Loire": [
        "Nantes", "Angers", "Le Mans", "Saint-Nazaire",
    ],
    "Provence-Alpes-Côte d'Azur": [
        "Marseille", "Nice", "Toulon", "Cannes",
    ],
}


# ─── Sidebar ─────────────────────────────────────────────────────────────────

def render_sidebar() -> dict:
    st.sidebar.title("Configuration")

    # ── Sources ──
    st.sidebar.subheader("Sources de données")
    use_pj = st.sidebar.checkbox("Pages Jaunes", value=True,
        help="Scraping HTML de pagesjaunes.fr — noms, adresses, téléphones.")

    ft_client_id = os.getenv("FT_CLIENT_ID", "").strip()
    ft_client_secret = os.getenv("FT_CLIENT_SECRET", "").strip()
    ft_key_ok = bool(ft_client_id and ft_client_secret
                     and ft_client_id != "votre_client_id_ici")

    if ft_key_ok:
        use_ft = st.sidebar.checkbox(
            "France Travail (Pôle Emploi)",
            value=True,
            help="API officielle — entreprises qui recrutent ACTIVEMENT.",
        )
    else:
        st.sidebar.checkbox("France Travail (Pôle Emploi)", value=False, disabled=True,
            help="Clé API requise. Voir onglet Guide.")
        use_ft = False
        st.sidebar.caption(
            "**France Travail non configuré.**  \n"
            "Inscription gratuite : francetravail.io  \n"
            "→ Voir onglet **Guide de lancement**"
        )

    use_linkedin = st.sidebar.checkbox("LinkedIn Jobs", value=True,
        help="Offres publiques LinkedIn — ~60 résultats/requête, fraîcheur 7 jours.")

    # ── Paramètres ──
    st.sidebar.subheader("Paramètres")
    max_prospects = st.sidebar.number_input(
        "Prospects max à collecter",
        min_value=10, max_value=1000, value=100, step=10,
        help="Arrêt automatique quand ce nombre est atteint.",
    )
    max_pages = st.sidebar.slider("Pages max par localisation", 1, 20, 3)
    delay = st.sidebar.slider("Délai entre requêtes (s)", 1.0, 5.0, 2.0, step=0.5)
    fetch_phones = st.sidebar.checkbox(
        "Récupérer les téléphones (plus lent)", value=True,
        help="Visite chaque page détail pour extraire le numéro.",
    )

    # ── Stats base ──
    st.sidebar.divider()
    st.sidebar.subheader("Base de données")
    df_existing = read_prospects_df()
    df_dupes = read_prospects_df(DOUBLONS_FILE)

    col1, col2 = st.sidebar.columns(2)
    col1.metric("Prospects", len(df_existing))
    col2.metric("Doublons évités", len(df_dupes))

    st.sidebar.caption(
        "Déduplication **cross-session** — aucun prospect ajouté deux fois."
    )

    if not df_existing.empty:
        csv_bytes = df_existing.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.sidebar.download_button(
            label="Télécharger prospects CSV",
            data=csv_bytes,
            file_name=f"prospects_CDE_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    sources = []
    if use_pj:
        sources.append("pagesjaunes")
    if use_ft:
        sources.append("francetravail")
    if use_linkedin:
        sources.append("linkedin")

    return {
        "sources": sources,
        "max_pages": max_pages,
        "max_prospects": int(max_prospects),
        "delay": delay,
        "fetch_phones": fetch_phones,
        "ft_client_id": ft_client_id,
        "ft_client_secret": ft_client_secret,
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
        dedup = DedupManager()
        log_queue.put(f"Base chargée : {len(dedup.known_keys)} prospects connus")

        all_raw = []

        def cb(msg):
            log_queue.put(msg)

        max_prospects = config.get("max_prospects", 0)
        total_combos = len(selected_queries) * len(selected_locations) * max(len(config["sources"]), 1)
        combo_num = 0
        limit_reached = False

        for label, query_str in selected_queries:
            if limit_reached:
                break
            for location in selected_locations:
                if limit_reached:
                    break
                for source in config["sources"]:
                    combo_num += 1
                    log_queue.put({"progress_pct": max(1, int(combo_num / total_combos * 85))})

                    if source == "pagesjaunes":
                        log_queue.put(f"\n[{combo_num}/{total_combos}] Pages Jaunes — {label} @ {location}")
                        from scrapers.pages_jaunes import PagesJaunesScraper
                        scraper = PagesJaunesScraper(delay=config["delay"])
                        results = scraper.scrape(
                            query=query_str, location=location,
                            max_pages=config["max_pages"],
                            fetch_phones=config["fetch_phones"],
                            progress_callback=cb,
                        )
                        all_raw.extend(results)

                    elif source == "linkedin":
                        log_queue.put(f"\n[{combo_num}/{total_combos}] LinkedIn Jobs — {label} @ {location}")
                        from scrapers.linkedin_jobs import LinkedInJobsScraper
                        li = LinkedInJobsScraper(delay=config["delay"])
                        results = li.scrape(
                            query=query_str, location=location,
                            progress_callback=cb,
                        )
                        all_raw.extend(results)

                    elif source == "francetravail":
                        log_queue.put(f"\n[{combo_num}/{total_combos}] France Travail — {label} @ {location}")
                        from scrapers.france_travail import FranceTravailScraper
                        ft = FranceTravailScraper(
                            client_id=config["ft_client_id"],
                            client_secret=config["ft_client_secret"],
                            delay=0.3,
                        )
                        results = ft.scrape(
                            query=query_str, location=location,
                            max_pages=min(config["max_pages"], 6),
                            progress_callback=cb,
                        )
                        all_raw.extend(results)

                    # Vérification limite
                    if max_prospects > 0:
                        current_with_link = sum(1 for p in all_raw if p.get("Lien", "").strip())
                        if current_with_link >= max_prospects:
                            log_queue.put(f"Limite de {max_prospects} prospects atteinte — arrêt.")
                            limit_reached = True
                            break

        log_queue.put(f"\nTotal brut : {len(all_raw)} fiches")
        log_queue.put({"progress_pct": 90})

        # ── Score /10 + filtrage + tri ──────────────────────────────────────
        log_queue.put("Scoring /10 et qualification...")
        qualified = qualify_prospects(all_raw, min_score=5)
        rejected = len(all_raw) - len(qualified)
        if rejected > 0:
            log_queue.put(f"{rejected} prospects éliminés (score < 5/10)")
        log_queue.put(f"{len(qualified)} prospects qualifiés (score >= 5/10)")
        log_queue.put({"progress_pct": 93})

        # ── Déduplication ──────────────────────────────────────────────────
        log_queue.put("Déduplication cross-sessions...")
        for prospect in qualified:
            dedup.check_and_register(prospect)

        log_queue.put({"progress_pct": 95})
        new_count, dupe_count = dedup.flush_to_disk()
        log_queue.put(
            f"Terminé — {new_count} nouveaux prospects | {dupe_count} doublons évités"
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
    st.header("Lancer un scraping")

    # ════════════════════════════════════════════════
    # BLOC 1 : Catégories de jobs étudiants
    # ════════════════════════════════════════════════
    st.subheader("1. Catégories de jobs étudiants")
    st.caption("Sélectionne les types de jobs à rechercher. Chaque catégorie lance des requêtes ciblées.")

    selected_queries = []

    # Affichage en grille 3 colonnes avec icônes
    cols = st.columns(3)
    for i, cat_name in enumerate(CATEGORY_NAMES):
        cat_info = STUDENT_JOB_CATEGORIES[cat_name]
        icon = cat_info["icon"]
        # Les 4 premières catégories cochées par défaut
        default = i < 4
        checked = cols[i % 3].checkbox(
            f"{icon} {cat_name}",
            value=default,
            key=f"cat_{i}",
        )
        if checked:
            # Ajouter toutes les requêtes de cette catégorie
            for query in cat_info["queries"]:
                selected_queries.append((cat_name, query))

    # ════════════════════════════════════════════════
    # BLOC 2 : Zone géographique
    # ════════════════════════════════════════════════
    st.subheader("2. Zone géographique")
    st.caption("Clique sur une région pour voir ses villes.")

    selected_locations = []

    for region_name, cities in ALL_REGIONS.items():
        expanded = region_name == "Île-de-France"
        with st.expander(f"{region_name} ({len(cities)} villes)", expanded=expanded):
            col_all, col_none, _ = st.columns([1, 1, 4])
            if col_all.button("Tout cocher", key=f"sel_all_{region_name}"):
                for city in cities:
                    st.session_state[f"city_{city}"] = True
            if col_none.button("Tout décocher", key=f"desel_all_{region_name}"):
                for city in cities:
                    st.session_state[f"city_{city}"] = False

            city_cols = st.columns(4)
            for i, city in enumerate(cities):
                key = f"city_{city}"
                default_city = region_name == "Île-de-France" and city == "Paris"
                checked = city_cols[i % 4].checkbox(
                    city,
                    value=st.session_state.get(key, default_city),
                    key=key,
                )
                if checked:
                    selected_locations.append(city)

    # ════════════════════════════════════════════════
    # BLOC 3 : Résumé + lancement
    # ════════════════════════════════════════════════
    st.divider()

    n_queries = len(selected_queries)
    n_locs = len(selected_locations)
    n_combos = n_queries * n_locs
    est_minutes = round(n_combos * config["max_pages"] * 2.5 / 60, 1)

    if n_queries == 0 or n_locs == 0:
        st.warning("Sélectionne au moins **une catégorie** et **une ville** pour lancer.")
        return

    source_labels = {
        "pagesjaunes": "Pages Jaunes",
        "francetravail": "France Travail",
        "linkedin": "LinkedIn Jobs",
    }
    sources_str = ", ".join(source_labels.get(s, s) for s in config["sources"]) or "Aucune"

    with st.expander("Résumé avant lancement", expanded=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("Requêtes", n_queries)
        c2.metric("Villes", n_locs)
        c3.metric("Durée estimée", f"~{est_minutes} min")
        st.caption(f"Sources : {sources_str} | Max : {config['max_prospects']} prospects")

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
                            f"**{msg['new_count']} nouveaux prospects** | "
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
            r1.metric("Nouveaux ajoutés", result.get("new_count", 0))
            r2.metric("Doublons évités", result.get("dupe_count", 0))
            r3.metric("Total en base", result.get("total", 0))


# ─── Onglet "Résultats" ──────────────────────────────────────────────────────

def _delete_session(session_path):
    """Supprime un fichier de session et reconstruit le fichier consolidé."""
    from pathlib import Path
    try:
        session_path = Path(session_path)
        if session_path.exists():
            session_path.unlink()
        # Reconstruire le fichier consolidé à partir des sessions restantes
        from utils.exporter import PROSPECTS_FILE, SESSIONS_DIR, CSV_COLUMNS
        all_dfs = []
        for f in SESSIONS_DIR.glob("session_*.csv"):
            try:
                df = pd.read_csv(f, encoding="utf-8-sig", dtype=str)
                all_dfs.append(df)
            except Exception:
                continue
        if all_dfs:
            combined = pd.concat(all_dfs, ignore_index=True)
            for col in CSV_COLUMNS:
                if col not in combined.columns:
                    combined[col] = ""
            combined[CSV_COLUMNS].to_csv(PROSPECTS_FILE, index=False, encoding="utf-8-sig")
        elif PROSPECTS_FILE.exists():
            PROSPECTS_FILE.unlink()
    except Exception:
        pass


def render_results_tab():
    st.header("Résultats")

    sessions = list_sessions()
    df_all = read_prospects_df()
    df_dupes = read_prospects_df(DOUBLONS_FILE)

    # ── Métriques globales ──
    stats_all = generate_summary_stats(df_all)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total prospects", len(df_all))
    m2.metric("Sessions", len(sessions))
    m3.metric("Score moyen", f"{stats_all.get('avg_score', 0)}/10")
    m4.metric("Doublons évités", len(df_dupes))

    st.divider()

    # ── Aucune session ? ──
    if not sessions and df_all.empty:
        st.info("Aucune session de scraping. Lance un scraping pour commencer !")
        return

    # ── Vue par session ──
    st.subheader("Sessions de scraping")

    # Choix de la vue
    view_mode = st.radio(
        "Affichage",
        options=["Par session", "Tout combiné"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if view_mode == "Par session":
        if not sessions:
            # Pas de fichiers session mais des données dans le consolidé (ancien format)
            st.info("Les anciens prospects sont dans le fichier consolidé. Choisis 'Tout combiné' pour les voir.")
        else:
            for idx, sess in enumerate(sessions):
                session_num = len(sessions) - idx
                with st.expander(
                    f"Session {session_num} — {sess['date']} ({sess['count']} prospects)",
                    expanded=(idx == 0),
                ):
                    df_sess = read_session_df(sess["path"])
                    if df_sess.empty:
                        st.caption("Aucun prospect dans cette session.")
                        continue

                    # Filtres pour cette session
                    fc = st.columns(3)
                    villes = sorted(df_sess["Localisation"].dropna().unique())
                    canaux = sorted(df_sess["Canal de contact"].dropna().unique())

                    sel_v = fc[0].multiselect("Ville", villes, placeholder="Toutes", key=f"sv_{idx}")
                    sel_c = fc[1].multiselect("Canal", canaux, placeholder="Tous", key=f"sc_{idx}")

                    filtered = df_sess.copy()
                    if sel_v:
                        filtered = filtered[filtered["Localisation"].isin(sel_v)]
                    if sel_c:
                        filtered = filtered[filtered["Canal de contact"].isin(sel_c)]

                    st.caption(f"{len(filtered)} prospects affichés")

                    st.dataframe(
                        filtered,
                        use_container_width=True,
                        height=min(400, 40 + len(filtered) * 35),
                        column_config={
                            "Lien": st.column_config.LinkColumn("Lien"),
                        },
                    )

                    # Boutons télécharger / supprimer cette session
                    btn_cols = st.columns([3, 1])
                    csv_sess = df_sess.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                    btn_cols[0].download_button(
                        f"Télécharger ({sess['count']} prospects)",
                        data=csv_sess,
                        file_name=sess["filename"],
                        mime="text/csv",
                        key=f"dl_{idx}",
                    )
                    if btn_cols[1].button("Supprimer", key=f"del_{idx}", type="secondary"):
                        _delete_session(sess["path"])
                        st.rerun()

    else:
        # Vue combinée (toutes sessions)
        if df_all.empty:
            st.info("Aucun prospect en base.")
            return

        # Filtres
        fc = st.columns(4)
        villes = sorted(df_all["Localisation"].dropna().unique()) if "Localisation" in df_all.columns else []
        canaux = sorted(df_all["Canal de contact"].dropna().unique()) if "Canal de contact" in df_all.columns else []
        offres = sorted(df_all["Type de partenariat(Leads)"].dropna().unique()) if "Type de partenariat(Leads)" in df_all.columns else []
        tri_options = ["Date (récent)", "Entreprise (A-Z)"]

        sel_villes = fc[0].multiselect("Ville", villes, placeholder="Toutes", key="all_v")
        sel_canaux = fc[1].multiselect("Canal", canaux, placeholder="Tous", key="all_c")
        sel_offres = fc[2].multiselect("Type", offres, placeholder="Tous", key="all_t")
        tri = fc[3].selectbox("Trier par", tri_options, index=0, key="all_tri")

        filtered = df_all.copy()
        if sel_canaux:
            filtered = filtered[filtered["Canal de contact"].isin(sel_canaux)]
        if sel_villes:
            filtered = filtered[filtered["Localisation"].isin(sel_villes)]
        if sel_offres:
            filtered = filtered[filtered["Type de partenariat(Leads)"].isin(sel_offres)]
        if tri == "Entreprise (A-Z)" and "Entreprise" in filtered.columns:
            filtered = filtered.sort_values("Entreprise", ascending=True, na_position="last")

        st.caption(f"**{len(filtered)}** prospects sur **{len(df_all)}** total")

        st.dataframe(
            filtered,
            use_container_width=True,
            height=500,
            column_config={
                "Lien": st.column_config.LinkColumn("Lien"),
            },
        )

    st.divider()

    # ── Export global ──
    st.subheader("Export CSV")
    ec1, ec2 = st.columns(2)
    if not df_all.empty:
        csv_all = df_all.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        ec1.download_button(
            "Télécharger TOUS les prospects",
            data=csv_all,
            file_name=f"prospects_CDE_complet_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.divider()

    # ── Graphiques ──
    if not df_all.empty:
        st.subheader("Répartitions")
        gc1, gc2 = st.columns(2)
        with gc1:
            if stats_all["by_canal"]:
                st.markdown("**Par canal de contact**")
                st.bar_chart(pd.DataFrame(
                    list(stats_all["by_canal"].items()), columns=["Canal", "Nombre"]
                ).set_index("Canal"))
        with gc2:
            if stats_all["by_type_offre"]:
                st.markdown("**Par type de partenariat**")
                st.bar_chart(pd.DataFrame(
                    list(stats_all["by_type_offre"].items()), columns=["Type", "Nombre"]
                ).set_index("Type"))
        if stats_all["by_ville"]:
            st.markdown("**Top 10 localisations**")
            st.bar_chart(pd.DataFrame(
                list(stats_all["by_ville"].items()), columns=["Localisation", "Nombre"]
            ).set_index("Localisation"))

    st.divider()

    # ── Supprimer les données ──
    st.subheader("Supprimer les données")
    st.warning("Supprime tous les prospects et toutes les sessions. Une sauvegarde est créée.")
    confirm = st.checkbox("Je confirme vouloir supprimer toutes les données")
    if confirm:
        if st.button("Supprimer toutes les données", type="primary"):
            from utils.exporter import clear_prospects
            ok = clear_prospects(backup=True)
            if ok:
                st.success("Base vidée. Sauvegarde créée dans data/backups/.")
                if "last_scrape_result" in st.session_state:
                    del st.session_state["last_scrape_result"]
                st.rerun()
            else:
                st.error("Erreur lors de la suppression.")


# ─── Onglet "Catégories" ─────────────────────────────────────────────────────

def render_categories_tab():
    st.header("Catégories de jobs étudiants")
    st.caption("Voici les 13 catégories de jobs étudiants les plus courants en France.")

    for cat_name in CATEGORY_NAMES:
        cat_info = STUDENT_JOB_CATEGORIES[cat_name]
        icon = cat_info["icon"]
        queries = cat_info["queries"]
        keywords = cat_info["keywords"][:8]

        with st.expander(f"{icon} {cat_name}", expanded=False):
            st.markdown(f"**Requêtes de recherche :** {', '.join(queries)}")
            st.markdown(f"**Mots-clés :** {', '.join(keywords)}")


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

### Activer France Travail (source prioritaire)

France Travail liste uniquement des entreprises qui **recrutent activement**. C'est gratuit.

1. Va sur **francetravail.io** → crée un compte
2. **Mes applications** → **Créer une application**
3. Coche **"Offres d'emploi v2"** → récupère Client ID + Secret
4. Ouvre `.env` et ajoute :
```
FT_CLIENT_ID=ton_id
FT_CLIENT_SECRET=ton_secret
```
5. Relance l'app

---

### Où sont les données ?

- `data/prospects_CDE.csv` → prospects (import dans Google Sheets)
- `data/doublons_CDE.csv` → doublons évités

**Import Google Sheets :** Fichier → Importer → CSV → Virgule → UTF-8

---

### Déduplication

Cross-session automatique : **Nom + Ville + Téléphone**. Aucun prospect ajouté deux fois.
    """)


# ─── Point d'entrée ──────────────────────────────────────────────────────────

def main():
    st.title("CDE — Jobs Étudiants France")
    st.caption("Coin des Étudiants — Trouve les meilleurs jobs étudiants partout en France")

    if "scraping_running" not in st.session_state:
        st.session_state["scraping_running"] = False

    config = render_sidebar()

    tab_scrape, tab_results, tab_cats, tab_guide = st.tabs([
        "Scraping", "Résultats", "Catégories", "Guide",
    ])

    with tab_scrape:
        render_scrape_tab(config)
    with tab_results:
        render_results_tab()
    with tab_cats:
        render_categories_tab()
    with tab_guide:
        render_guide_tab()


if __name__ == "__main__":
    main()
