# TODO — pyramide de prix

Voir [CRITIQUE.md](CRITIQUE.md) pour le détail de chaque point (numéros entre parenthèses).

## Fait (session courante)

- [x] Corriger les marchés `?country=` : URL du `products.json` sur le chemin, pas en fin de query (2.8)
- [x] Inclure la query dans la clé de marché pour éviter l'écrasement entre marchés d'un même domaine (2.8)
- [x] Ajouter Lemaire (FR, US, GB, CH), Margaux Lonnberg (FR, US, GB), Laurence Bras (FR, GB, CH) dans `crawler/shops.py`, endpoints vérifiés en direct
- [x] Corriger le `Dockerfile` : copier `normalize_categories.py` et `taxonomy/` (1.1), commit `c6e7082`
- [x] Corriger `deploy/deploy.sh` : contexte de build relatif au script, pas à `..` (1.2), commit `c6e7082`
- [x] Vérifier l'état du job déployé : les exécutions quotidiennes sont `COMPLETE 1/1` et les logs montrent des crawls réussis (l'image déployée est plus ancienne que la branche)

## En attente (branche `feat/add-brands-fix-country-markets`)

- [ ] Pousser la branche : `gh auth login` puis `git push -u origin feat/add-brands-fix-country-markets`
- [ ] Reconstruire l'image (`gcloud builds submit`), puis lancer une exécution et contrôler les logs

## P0 — Bloquant : le job ne tourne pas

- [ ] Faire échouer le job si un marché échoue, et ajouter une alerte (1.3)
- [ ] Faire échouer le job si un marché échoue, et ajouter une alerte (1.3)

## P1 — Intégrité des données

- [ ] Ne plus utiliser l'id d'un marché secondaire comme clé de document (2.1)
- [ ] Gérer les doublons existants dans `products` après correction (2.1)
- [ ] Marquer les produits disparus du catalogue (`last_seen_at` ancien → `available: false` ou `removed_at`) (2.2)
- [ ] Ajouter la devise au niveau racine du document et filtrer par devise dans toute agrégation (2.3)
- [ ] Mesurer la taille max d'un document Firestore sur les produits les plus lourds (2.5)
- [ ] Chiffrer le nombre d'écritures Firestore par jour sur le catalogue réel (2.6)

## P2 — Qualité de la classification

- [ ] Écrire des tests de non-régression sur `category_matching` et `resolve()` (3.4)
- [ ] Ajouter un dictionnaire `taxonomy/mappings/<marque>.json` pour les marques les plus importantes (3.1)
- [ ] Exclure les `low_confidence` de la pyramide, ou les marquer visuellement (3.3)
- [ ] Revoir les seuils du fuzzy matching sur un échantillon annoté à la main (3.2)

## P3 — Hygiène du code et du déploiement

- [ ] Épingler les versions dans `requirements.txt` (ou ajouter un lockfile) (4)
- [ ] Ajouter un `.dockerignore` (4)
- [ ] Documenter ou supprimer la référence à `../fashion_crawler` dans le README (4)
- [ ] Ajouter un budget alert sur le projet GCP (5)
- [ ] Rendre `deploy.sh` idempotent sur la création du projet et de la facturation (5)

## Décisions à prendre (avant de construire la suite)

- [ ] **Quel projet GCP et quelle région ?** `shopify_tracker` (europe-west1, Firestore) ou `pyramidale` (europe-west9, BigQuery) (5)
- [ ] **Shopify_tracker : prototype à archiver, ou socle à migrer ?** Recommandation : le garder comme prototype, reprendre la logique Shopify comme adaptateur dans `quiet-luxury-pricing` (6)
- [ ] **Périmètre : quiet luxury ou maisons de luxe françaises ?** Les maisons françaises majeures ne sont pas sur Shopify (7)
- [ ] **Quel prix pour la pyramide ?** Prix pratiqué ou prix de référence ; promos incluses ou non (8)
- [ ] **Shopify_tracker inclut des marques non françaises** (Khaite, Staud, Cult Gaia, Totême…) : les garder pour le benchmark, ou les retirer ? (7)

## quiet-luxury-pricing — étape 1 (adaptateurs)

- [ ] Corriger le lint : `ruff check . --fix` puis traiter les 13 restantes (E501, E702)
- [ ] Expliquer les 80 s de `pytest` sur les tests de fondations
- [ ] Vérifier les 18 marchés `verified: false` dans `config/brands.yaml` (6)
- [ ] Adaptateur Shopify (reprendre la logique de `shopify_tracker/crawler/fetch.py`)
- [ ] Adaptateur SFCC (Sandro, Maje, Ba&sh)
- [ ] Adaptateur WShop / Global-e (Vanessa Bruno)
- [ ] Adaptateur Sessun, puis Gérard Darel (Storefront API)
- [ ] Sauver chaque réponse brute dans GCS avant parsing (règle du `CLAUDE.md`)
- [ ] Fixtures enregistrées + tests de contrat pour chaque adaptateur
- [ ] Créer `sql/bigquery/001_raw_and_ref.sql` dans le projet `pyramidale` et valider le schéma
- [ ] Référentiels : charger `taxonomy/erp_soeur/` et `scope.csv` en `qlp_ref`

## quiet-luxury-pricing — étapes 2 à 4

- [ ] Dataform : `qlp_core` puis `qlp_mart` (conversion BCE, TTC, quartiles)
- [ ] Terraform : `infra/` (aujourd'hui « à venir »)
- [ ] Run en parallèle pendant 1 à 2 semaines, comparaison avec shopify_tracker
- [ ] Looker Studio : vue pyramide par catégorie, marque, marché, avec indicateur de couverture
- [ ] Classification : dictionnaire par marque → fuzzy → LLM (Vertex) → validation humaine (décision 7)
- [ ] Images (phase 4) : packshots, similarité « même coupe » ; avis juriste avant commercialisation (décisions 10 et 15)
