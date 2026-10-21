# Critique — code et stack GCP

Périmètre : `shopify_tracker/` (POC déployé sur Firestore) et `quiet-luxury-pricing/` (projet cible, BigQuery).
Revue statique du code et des fichiers de config. Je n'ai pas interrogé le projet GCP réel : tout ce qui concerne l'état déployé reste à vérifier.

## Verdict

- **shopify_tracker** : le principe est bon (endpoint `products.json`, pagination, multi-marchés, snapshot quotidien). Mais le déploiement tel qu'écrit ne peut pas démarrer, et le job peut échouer en silence.
- **quiet-luxury-pricing** : la fondation est sérieuse (contrat pydantic, règle d'ajout seul, décisions datées). Il n'y a que l'étape 0 : aucun adaptateur, aucun job, aucune table créée.
- **Deux stacks, pas une.** shopify_tracker écrit dans Firestore ; quiet-luxury décide explicitement d'abandonner Firestore pour les données produit (décision 12 de `docs/decisions.md`) au profit de GCS + BigQuery + Dataform. Il faut acter que shopify_tracker est un prototype et que la cible est quiet-luxury.

## 1. Bugs bloquants (shopify_tracker)

**1.1 Le conteneur ne démarre pas.** `Dockerfile` ne copie que `crawler/`. Or :
- `crawler/main.py:13` fait `import normalize_categories` (fichier à la racine, absent de l'image) ;
- `crawler/taxonomy.py:16` lit `taxonomy/` (dossier absent de l'image).

Le job échoue à l'import avant même de crawler. Correctif : `COPY normalize_categories.py ./` et `COPY taxonomy ./taxonomy`.

**1.2 Le contexte de build est le mauvais dossier.** `deploy/deploy.sh` fait `gcloud builds submit --tag "$IMAGE" ..`. Le `..` est relatif au répertoire courant, pas au script. Le README lance `./deploy/deploy.sh` depuis la racine : le contexte devient alors le dossier parent (`Bureau/`), qui n'a pas de Dockerfile. Correctif : résoudre le chemin depuis le script (`ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"`).

**1.3 Échecs silencieux.** `crawler/main.py` attrape toutes les exceptions par marché et continue, puis sort avec le code 0. Conséquences : le job apparaît en succès même si tout a échoué, `--max-retries=1` ne se déclenche jamais, et aucune alerte ne part. Correctif : compter les marchés en échec, sortir en code non nul si un échec survient, et ajouter une alerte (log-based metric ou notification).

## 2. Risques sur les données

**2.1 Collision d'identifiants entre boutiques distinctes** (Isabel Marant, Polène, The Frankie Shop). Dans `crawler/main.py`, `doc_shopify_id = handle_to_home_id.get(handle, product.get("id"))` : si un produit n'existe que sur un marché secondaire, son id (issu d'une *autre* instance Shopify) sert de clé de document. Il peut coïncider avec l'id d'un produit sans rapport de la boutique principale, et ses prix sont alors écrits dans la fiche d'un autre produit.

Variante du même problème : si le marché principal échoue un jour, les produits des marchés secondaires créent des documents avec leurs propres ids. Quand le marché principal revient, les ids ne correspondent plus et on obtient des doublons.

**2.2 Pas de détection de disparition.** Un produit retiré du catalogue garde un `last_seen_at` figé et reste dans `products_normalized` indéfiniment, car la normalisation incrémentale ne supprime jamais rien. Pour une pyramide de prix, il faut savoir ce qui est en vente aujourd'hui.

**2.3 Devises mélangées.** `min_price` / `max_price` au niveau racine correspondent au marché principal, dans la devise de ce marché. Or certaines boutiques principales ne sont pas en EUR : Totême en SEK, The Frankie Shop et Khaite en USD, Nanushka en GBP. Un agrégat sur `min_price` sans filtrer sur la devise est faux. La devise n'est stockée que dans `markets.*`, pas au niveau racine.

**2.4 Prix barrés ignorés.** `compare_at_price` est stocké dans les variants mais jamais exploité. Suffisant pour un prix pratiqué, insuffisant pour mesurer la démarque.

**2.5 Taille des documents.** `variants` est dupliqué (racine + `markets.<clé>`) et chaque snapshot embarque les variants de chaque marché. La limite Firestore est de 1 MiB par document : à mesurer sur les produits à nombreuses variantes et plusieurs marchés.

**2.6 Coût Firestore.** Pour chaque produit et chaque marché : 1 lecture + 2 écritures (document + snapshot). Ordre de grandeur : 19 marques × 2 à 4 marchés × quelques centaines de produits, soit plusieurs dizaines de milliers d'écritures par jour. Le quota gratuit est de 20 000 écritures par jour. Chiffrage à faire avec le nombre réel de produits (non mesuré ici).

**2.8 Marchés `?country=` cassés (corrigé).** `fetch.py` construisait l'URL par concaténation : `https://staud.clothing/?country=GB` + `/products.json` donnait `/?country=GB/products.json`, qui renvoie la page d'accueil HTML. Le `resp.json()` échouait donc, et chaque marché de ce type était en `FAILED` sans alerte. Ça touchait Staud, Cult Gaia, Khaite, Nanushka, Officine Générale, Musier Paris, By Far et The Frankie Shop (14 marchés au total, d'après `shops.py`). Corrigé dans `fetch.py` (`_products_url`), vérifié en direct sur 16 marchés.

Second problème du même type, qui serait apparu après la correction : `_market_key` ignorait la query string. Les marchés `base`, `?country=GB` et `?country=CH` d'un même domaine auraient écrasé la même entrée `markets.<clé>`. Corrigé dans `firestore_store.py` (la clé inclut désormais la query). Les clés des marchés sans query ne changent pas.

**2.7 Lectures complètes à chaque run.** `normalize_categories.run()` lit toute la collection `products` et tous les ids de `products_normalized`, même en `--new-only`. Acceptable à cette échelle, mais coûteux en lectures à mesure que le catalogue grossit.

## 3. Qualité du mapping catégorie (le cœur métier)

**3.1 Un seul dictionnaire de marque.** Seul `taxonomy/mappings/rouje.json` existe. Les 18 autres marques passent par le fuzzy matching sur le titre (`difflib`).

**3.2 Le fuzzy matching est fragile.** Le code lui-même documente des faux positifs (« Top » → « Tote bag » à 0,57, « Bougie » → « CHE » à 0,67). Le seuil de 0,90 ne protège pas contre les coïncidences.

**3.3 Les `low_confidence` sont publiés.** Ils entrent dans `products_normalized`, donc dans le dashboard, sans distinction visuelle. Une pyramide construite dessus mélange des catégories fiables et des devinettes.

**3.4 Pas de tests.** Aucun fichier de test n'est suivi par git dans shopify_tracker. Le mapping n'a aucun test de non-régression.

## 4. Qualité du code et des dépendances

- `requirements.txt` n'épingle pas les versions (`requests>=2.31`, `google-cloud-firestore>=2.16`) : builds non reproductibles. Pas de lockfile.
- Pas de `.dockerignore` : le contexte embarque `.git`, les caches, etc.
- Le README renvoie à `../fashion_crawler`, qui n'est pas dans le workspace. La logique de `category_matching` y est *copiée* : deux pipelines à maintenir en parallèle.
- Le User-Agent contient un email de contact envoyé à chaque site crawlé. C'est une bonne pratique de politesse, à garder en tête.

## 5. Stack GCP

**Ce qui est bien**
- Cloud Run Job + Cloud Scheduler, avec un service account par rôle et des droits minimaux (`datastore.user`, `run.invoker`).
- Pas de clé JSON : authentification par ADC.
- `set -euo pipefail` dans le script de déploiement.

**Ce qui manque ou pose question**
- **Régions incohérentes** : `europe-west1` dans shopify_tracker, `europe-west9` dans quiet-luxury-pricing (projet `pyramidale`). À aligner, ou à assumer explicitement.
- **Pas de monitoring ni d'alerte** sur le job, pas de budget alert sur la facturation.
- **Déploiement partiellement idempotent** : `gcloud projects create` et le lien de facturation ne sont pas protégés contre une relance.
- **Deux projets GCP potentiellement distincts** pour une même idée : à clarifier avant de provisionner quoi que ce soit de plus.

## 6. quiet-luxury-pricing (cible)

**Points forts**
- Contrat formel (`src/qlp/models.py`, pydantic, montants en `Decimal`), avec règles métier écrites.
- Règle d'or : aucune écriture par-dessus une ligne raw, historique en ajout seul.
- Prix brut stocké, conversion de devise et de TVA reportée à BigQuery : c'est le bon choix pour une pyramide.
- Juridique noté (descriptions et images = contenus protégés, avis de juriste requis).

**Points faibles**
- **Étape 0 seulement** : `src/qlp/` contient le contrat et la config, aucun adaptateur, `dataform/` et `infra/` n'existent pas encore.
- **18 marchés sur 29 marques ont `verified: false`** dans `config/brands.yaml`. La couverture réelle n'est pas confirmée.
- **Tests verts** : `pytest` passe (8/8), mais il met 80 s pour des tests de fondations, ce qui mérite une vérification (import lent, réseau ?).
- **Lint en échec** : `ruff check .` remonte 29 erreurs (imports non utilisés, `E401`, lignes trop longues), dont 16 corrigeables automatiquement.
- **Périmètre à trancher** (voir section 7).

## 7. Périmètre : « luxe français » ou « quiet luxury » ?

La plupart des maisons françaises de luxe (Chanel, Hermès, Louis Vuitton, Dior, Saint Laurent…) ne sont **pas** sur Shopify : elles tournent sur des plateformes custom ou SFCC, souvent protégées contre le scraping. L'approche `products.json` ne les atteint pas.

Le projet a donc choisi le segment « quiet luxury » (Soeur + 28 marques, dont beaucoup sont Shopify). C'est réaliste, mais ça s'éloigne de l'idée de départ. Trois options : (a) assumer le segment quiet luxury ; (b) ajouter les maisons inaccessibles via des données manuelles ou un partenaire ; (c) passer par un service de déblocage, ce que la décision 11 n'autorise qu'à l'usage.

## 8. Méthodologie de la pyramide

- **Unité** : prix TTC en EUR, taux BCE du jour du relevé (décision 6). Déjà acté.
- **Grain** : couleur × marché (décision 5). La pyramide se calcule par catégorie FN4/FN5, par marque et par tier.
- **Statistique** : médiane et quartiles plutôt que moyenne, qui est sensible aux valeurs extrêmes.
- **Prix pris en compte** : à définir. Prix pratiqué (prix affiché, promos incluses) ou prix de référence (hors démarque). Les prix barrés Soeur sont des démarques réelles (décision 14).
- **Couverture** : une marque absente d'un marché fausse la comparaison. Il faut un indicateur de couverture dans chaque vue (décision 3).
- **Produits disponibles** : une pyramide ne doit compter que les produits en stock (cf. 2.2).
- **Périmètre** : femme + unisexe par défaut (décision 8).
