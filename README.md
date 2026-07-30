# Scraper CDE — Outil de prospection Île-de-France

Outil de scraping automatisé pour générer des listes de prospects (entreprises) en Île-de-France, prêtes à importer dans Google Sheets.

## Fonctionnalités

- Scraping depuis **Pages Jaunes**, **Google Maps** et **Indeed**
- Zone géographique : **Île-de-France** (Paris + petite et grande couronne)
- **Détection de doublons persistante** entre les sessions (clé : Nom + Ville + Téléphone)
- **Classification automatique** : canal recommandé (Appel / Email) et type d'offre (Job étudiant / Stage / Alternance / Tous)
- **Export CSV** compatible Google Sheets (encodage UTF-8 avec BOM)
- Interface web Streamlit + CLI Python

---

## Installation

### Prérequis

- Python 3.9 ou supérieur
- pip

### Étapes

```bash
# 1. Cloner ou copier le répertoire scraper_CDE
cd scraper_CDE

# 2. (Recommandé) Créer un environnement virtuel
python -m venv venv
# Windows :
venv\Scripts\activate
# Mac/Linux :
source venv/bin/activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer les variables d'environnement
# Éditer le fichier .env (déjà présent) :
# - Ajouter votre clé Google Places API
# - Optionnel : cookie Pages Jaunes si bloqué
```

---

## Configuration

### Fichier `.env`

```env
# Obligatoire pour la source Google Maps
# Obtenir une clé : https://console.cloud.google.com/
# Activer l'API : "Places API" dans votre projet GCP
GOOGLE_PLACES_API_KEY=votre_cle_ici

# Optionnel : si Pages Jaunes retourne des erreurs 403
# Comment copier le cookie :
# 1. Ouvrir pagesjaunes.fr dans Chrome
# 2. F12 → Onglet Network
# 3. Actualiser la page → cliquer sur la première requête
# 4. Headers → copier la valeur complète du champ "Cookie:"
PJ_COOKIE_HEADER=
```

### Obtenir une clé Google Places API

1. Aller sur [Google Cloud Console](https://console.cloud.google.com/)
2. Créer un projet (ou utiliser un existant)
3. Activer l'API **Places API**
4. Créer une clé API (Identifiants → Créer des identifiants → Clé API)
5. Coller la clé dans le fichier `.env`

**Coût estimé :**
- Nearby Search : ~$0.032 par requête
- Place Details : ~$0.017 par requête
- Avec `--no-details` : économise les appels Place Details (perd téléphone/site web)
- Google offre $200 de crédit gratuit par mois

---

## Utilisation

### Interface web (recommandée)

```bash
streamlit run app.py
```

Ouvrir le navigateur sur `http://localhost:8501`

**Interface :**
- Sidebar : choisir les sources (Pages Jaunes, Google Maps, Indeed), paramètres
- Onglet "Lancer" : entrer la requête et la zone, cliquer sur "Lancer le scraping"
- Onglet "Résultats" : voir les métriques, filtrer le tableau, télécharger le CSV

### CLI (ligne de commande)

```bash
# Scraper les restaurants à Paris via Pages Jaunes
python main.py --source pagesjaunes --query "restaurant" --location "Paris"

# Scraper les cabinets RH en IDF (5 pages max)
python main.py --source pagesjaunes --query "cabinet recrutement" --location "Île-de-France" --max-pages 5

# Scraper Google Maps (sans appels Place Details pour économiser)
python main.py --source google --no-details

# Tout scraper (toutes sources)
python main.py --source all --query "restaurant" --location "Paris"

# Test sans sauvegarder (dry run)
python main.py --source pagesjaunes --query "boulangerie" --location "Paris" --dry-run
```

**Options CLI :**

| Option | Description | Défaut |
|--------|-------------|--------|
| `--source` | google / pagesjaunes / indeed / all | all |
| `--query` | Terme de recherche | restaurant |
| `--location` | Zone géographique | Île-de-France |
| `--max-pages` | Nombre max de pages par source | 10 |
| `--no-details` | Ignorer Place Details Google | False |
| `--dry-run` | Tester sans sauvegarder | False |

---

## Requêtes recommandées

| Cible | Requête | Canal | Type offre |
|-------|---------|-------|------------|
| Restaurants | `restaurant` | Appel | Job étudiant |
| Boulangeries | `boulangerie patisserie` | Appel | Job étudiant |
| Bars / cafés | `bar cafe brasserie` | Appel | Job étudiant |
| Supermarchés | `supermarche epicerie` | Appel | Job étudiant |
| Grandes enseignes | `grande surface` | Email | Job étudiant |
| Agences RH | `agence recrutement ressources humaines` | Email | Tous |
| Startups / PME | `startup agence conseil` | Email | Stage / Alternance |
| Cabinets comptables | `cabinet comptable expertise` | Email | Stage / Alternance |

---

## Structure des fichiers de données

### `data/prospects_CDE.csv` — Fichier principal

| Colonne | Description |
|---------|-------------|
| Entreprise | Nom de l'entreprise |
| Secteur | Secteur d'activité |
| Ville | Ville / Arrondissement |
| Adresse | Adresse complète |
| Téléphone | Numéro de téléphone |
| Email | Email (si disponible) |
| Site web | URL du site web |
| LinkedIn | URL LinkedIn (si disponible) |
| Type offre visée | Job étudiant / Stage / Alternance / Tous |
| Canal recommandé | Appel ou Email |
| Assigné à | Membre de l'équipe CDE |
| Statut | À contacter (par défaut) |
| Date ajout | Date de scraping |
| Notes | Commentaires libres |

### `data/doublons_CDE.csv` — Doublons évités

Même format que prospects_CDE.csv. Conservé pour audit et éviter les re-doublons entre sessions.

---

## Import dans Google Sheets

1. Ouvrir Google Sheets → Fichier → Importer
2. Choisir le fichier CSV téléchargé
3. Séparateur : **Virgule**
4. Encodage : **UTF-8** (le BOM est inclus, les accents seront corrects)
5. Cliquer sur "Importer les données"

---

## Détection des doublons

La clé de déduplication est : **Nom normalisé + Ville normalisée + 10 derniers chiffres du téléphone**

- Les doublons sont détectés **entre les sessions** (les CSV existants sont chargés au démarrage)
- Un prospect sans téléphone est considéré comme doublon d'un autre sans téléphone s'ils ont le même nom et la même ville
- Les doublons sont sauvegardés dans `data/doublons_CDE.csv` pour audit

---

## Dépannage

### Pages Jaunes retourne 403

1. Ouvrir `https://www.pagesjaunes.fr` dans Chrome
2. F12 → Onglet Network → Actualiser la page
3. Cliquer sur la première requête (pagesjaunes.fr)
4. Headers → Request Headers → copier la valeur de `Cookie:`
5. Coller dans `.env` : `PJ_COOKIE_HEADER=<valeur copiée>`

### Google Maps ne retourne rien

- Vérifier que `GOOGLE_PLACES_API_KEY` est bien définie dans `.env`
- Vérifier que l'API "Places API" est activée dans Google Cloud Console
- Vérifier que la clé n'est pas restreinte à des domaines/IPs spécifiques

### Indeed retourne des résultats vides

Indeed a une protection anti-bot forte. C'est normal — les résultats seront vides ou partiels. La source Indeed est fournie en "best-effort".

---

## Structure du projet

```
scraper_CDE/
├── main.py              # Point d'entrée CLI
├── app.py               # Interface Streamlit
├── scrapers/
│   ├── __init__.py
│   ├── google_maps.py   # Scraper Google Places API
│   ├── pages_jaunes.py  # Scraper Pages Jaunes HTML
│   └── indeed.py        # Scraper Indeed (best-effort)
├── utils/
│   ├── __init__.py
│   ├── dedup.py         # Détection et gestion des doublons
│   ├── classifier.py    # Règles canal + type offre
│   └── exporter.py      # Export CSV et lecture données
├── data/
│   ├── prospects_CDE.csv
│   └── doublons_CDE.csv
├── .env                 # Variables d'environnement (ne pas commiter)
├── requirements.txt
└── README.md
```
