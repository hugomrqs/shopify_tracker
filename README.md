# shopify_tracker

Crawler léger qui récupère le catalogue complet de marques mode vendues sur
Shopify, via leur endpoint public `domaine.com/products.json` — pas de
scraping HTML, pas de Playwright, pas de parsing JSON-LD. Les données sont
stockées dans **Firestore**, sur GCP, avec un run automatique quotidien.

C'est un projet séparé de [`fashion_crawler`](../fashion_crawler) (qui reste
en place pour les sites non-Shopify : SFCC, plateformes custom, etc.).

## Pourquoi cette approche

Shopify expose nativement le catalogue entier d'une boutique en JSON sur
`/products.json` (paginable, pas d'authentification). Quand un site tourne
sur du Shopify natif, c'est strictement plus fiable et plus simple qu'un
crawl HTML : pas de sélecteurs CSS à maintenir, pas de JS à exécuter, pas de
risque de casser au moindre changement de thème.

## Sites suivis

| Marque | Domaine |
|---|---|
| Rouje | rouje.com |
| Dries Van Noten | driesvannoten.com |
| Soeur | soeur.fr |
| A.P.C. | apc.fr |
| Isabel Marant | isabelmarant.com |
| Roseanna | roseanna.fr |

Liste définie dans [`crawler/shops.py`](crawler/shops.py). Chaque domaine a
été vérifié en direct (`curl .../products.json`) — pas seulement supposé
Shopify. Sessun avait été envisagé mais est en fait un backend PHP custom
(404 sur `/products.json`) : exclu.

## Architecture

```
Cloud Scheduler (cron quotidien, 06:00 UTC)
        │  déclenche
        ▼
Cloud Run Job "shopify-tracker"
        │  pour chaque shop :
        │    GET {domaine}/products.json  (pagination jusqu'à page vide)
        │    upsert -> products/ (bronze, brut)
        ▼
        │  normalize_categories.run() (voir "Catégorisation" plus bas)
        ▼
Firestore products_normalized/ (silver, catégorisé — c'est ce que lit le dashboard)
```

## Modèle de données (Firestore)

```
products/{brand-slug}_{shopify_product_id}            # bronze — tout produit crawlé
  brand, domain, shopify_id, handle, title, vendor, product_type, tags,
  min_price, max_price, images[], options[], variants[],
  source_url, first_seen_at, last_seen_at, last_crawl_date

  snapshots/{run_date}
    # un document par run : permet de reconstruire l'historique de prix
    # et de disponibilité sans avoir à re-crawler le passé.
    min_price, max_price, variants[], captured_at

products_normalized/{brand-slug}_{shopify_product_id}  # silver — sous-ensemble catégorisé
  # miroir complet du document products/ correspondant, plus :
  category: {fn4_code, fn4_label, fn5_code, fn5_label[, confidence]} | null
  category_mapping_status: mapped | mapped_from_name | low_confidence
    # (out_of_scope et unmapped ne sont jamais écrits ici — voir plus bas)
```

## Catégorisation (taxonomy)

`products` (bronze) contient tout ce qui a été crawlé, tel quel.
`normalize_categories.py` mappe chaque produit sur la taxonomie interne
Soeur (FN4 catégorie / FN5 sous-catégorie) et publie le résultat dans
`products_normalized` (silver) — **c'est cette collection que lit le
dashboard**, pas `products`. Un produit qui ne matche rien reste dans
`products` mais n'apparaît jamais dans `products_normalized`, donc jamais
sur le site.

Ordre de résolution, par produit :

1. **Lookup direct** : `taxonomy/mappings/<brand-slug>.json` mappe le
   `product_type` Shopify de la marque (ex. `"Jeans"`, `"Petite
   maroquinerie"`) vers `{"fn4": "JEA"}` / `{"fn4": "SEM", "fn5": "PMA"}`,
   ou `{"out_of_scope": true}` (ex. le maquillage Rouje, hors périmètre).
   Seul niveau propre à chaque marque — c'est la source de vérité quand
   elle existe. **Aujourd'hui seul `rouje.json` existe** ; les autres
   marques crawlées n'ont pas encore de dictionnaire.
2. **Fallback flou sur le titre** (quand `product_type` est vide, absent
   du dictionnaire, ou trop générique, ex. `"Manteaux & Vestes"` qui
   mélange 2 familles FN4) : comparaison des 1 à 3 premiers mots du titre
   (et de chaque segment après un `|`) au vocabulaire des libellés
   FN4/FN5 via `difflib`. Score ≥ 0.90 → `mapped_from_name` ; entre 0.55
   et 0.90 → `low_confidence` (inclus quand même, à revoir) ; en dessous
   → aucune proposition. Deux garde-fous avant le score : mots-clés
   hors-périmètre (bougie, rouge à lèvres...) et trous connus de la
   taxonomie (top, body, maillot de bain...) qui court-circuitent vers
   `unmapped` plutôt que de forcer un score bidon.
3. Rien ne matche → `category: null`, statut `unmapped` — jamais de
   devinette forcée sous le seuil.

Rejouable à volonté sans re-crawler (`--dry-run` pour juste voir le
rapport de couverture par marque), puisque `products` (bronze) garde les
champs bruts (`product_type`, `title`) comme source de vérité.

```bash
python3 normalize_categories.py --dry-run   # rapport de couverture, aucune écriture
python3 normalize_categories.py             # applique et publie products_normalized
```

**Pour ajouter/étendre un dictionnaire de marque** : déposer ou éditer
`taxonomy/mappings/<brand-slug>.json` (slug = marque en minuscules,
espaces/ponctuation → `-`, ex. `taxonomy/mappings/a-p-c.json` pour
"A.P.C."). Aucune modification de code nécessaire — auto-détecté au run
suivant. Pour mettre à jour le référentiel FN3/FN4/FN5 lui-même,
remplacer les CSV dans `taxonomy/` (colonnes `CC_TYPE, CC_CODE,
CC_LIBELLE, CC_ABREGE, CC_LIBRE`).

Logique portée depuis [`fashion_crawler`](../fashion_crawler)
(`normalize_categories.py`, `utils/category_matching.py`), qui applique
les mêmes règles à ses propres données (Mongo, marques non-Shopify) —
deux pipelines séparés, même référentiel FN4/FN5 et même logique de
scoring.

## Structure du projet

```
shopify_tracker/
  crawler/
    shops.py            # liste des marques/domaines à suivre
    fetch.py             # pagination sur /products.json
    firestore_store.py    # upsert produit + snapshot journalier
    taxonomy.py            # chargeur des codebooks FN4/FN5
    category_matching.py   # fallback flou (difflib) sur le titre
    main.py                # orchestration + appel à normalize_categories.run()
  taxonomy/
    FN3.csv, FN4.csv, FN5.csv, FN6.csv   # référentiel Soeur (codes/libellés)
    mappings/
      rouje.json           # dictionnaire product_type -> FN4/FN5 par marque
  normalize_categories.py  # bronze (products) -> silver (products_normalized)
  deploy/
    deploy.sh              # provisioning GCP complet (projet, Firestore, Cloud Run, Scheduler)
  Dockerfile
  requirements.txt
```

## Lancer en local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

gcloud auth application-default login   # credentials Firestore locales

GOOGLE_CLOUD_PROJECT=<project-id> python -m crawler.main
```

## Déployer sur GCP

Crée un nouveau projet GCP, active les APIs nécessaires, provisionne
Firestore, build+push l'image dans Artifact Registry, crée le Cloud Run Job
et le trigger Cloud Scheduler.

```bash
gcloud auth login   # une fois, interactif

PROJECT_ID=mon-projet-shopify-tracker \
BILLING_ACCOUNT_ID=$(gcloud billing accounts list --format='value(ACCOUNT_ID)' | head -1) \
./deploy/deploy.sh
```

Variables optionnelles : `REGION` (défaut `europe-west1`), `SCHEDULE`
(défaut `0 6 * * *`, cron quotidien 06:00 UTC).

Lancer un run manuel après déploiement :

```bash
gcloud run jobs execute shopify-tracker --region=europe-west1
```

Suivre les executions :

```bash
gcloud run jobs executions list --job=shopify-tracker --region=europe-west1
```

## Ajouter un site

1. Vérifier que le site est bien du Shopify natif : `curl https://<domaine>/products.json` doit renvoyer du JSON avec un tableau `products`.
2. Ajouter `{"brand": "...", "base_url": "https://..."}` dans `crawler/shops.py`.
3. Rebuild + redeploy le job (relancer `deploy/deploy.sh`, ou juste `gcloud builds submit` + `gcloud run jobs update`).

Certains sites Shopify bloquent cet endpoint ou sont protégés par de
l'anti-bot (ex. Sezane, protégé DataDome — voir l'audit dans
`fashion_crawler/README.md`) : dans ce cas, ce projet n'est pas la bonne
approche, il faut repasser par un crawl HTML classique.
