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
        ▼
Firestore (native mode, europe-west1)
```

## Modèle de données (Firestore)

```
products/{brand-slug}_{shopify_product_id}
  brand, domain, shopify_id, handle, title, vendor, product_type, tags,
  min_price, max_price, images[], options[], variants[],
  source_url, first_seen_at, last_seen_at, last_crawl_date

  snapshots/{run_date}
    # un document par run : permet de reconstruire l'historique de prix
    # et de disponibilité sans avoir à re-crawler le passé.
    min_price, max_price, variants[], captured_at
```

## Structure du projet

```
shopify_tracker/
  crawler/
    shops.py            # liste des marques/domaines à suivre
    fetch.py             # pagination sur /products.json
    firestore_store.py    # upsert produit + snapshot journalier
    main.py                # orchestration, un site en échec ne bloque pas les autres
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
