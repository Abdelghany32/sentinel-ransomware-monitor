# Surveillance périodique avec des API réelles

## Démarrer en une commande

Depuis le dépôt, après activation de l'environnement virtuel :

```sh
source .venv/bin/activate
python -m sentinel monitor
```

Ouvrir **http://127.0.0.1:8000/?mode=live**. La commande lance le serveur local et un collecteur en arrière-plan dans le même processus. Laisser ce terminal ouvert ; Ctrl+C arrête le service. Une requête déjà en cours peut durer jusqu'aux limites réseau ; après cinq secondes de fermeture, le processus peut terminer son thread daemon. Les transactions SQLite protègent les écritures en cours.

Le worker vérifie les sources toutes les 60 secondes. La configuration intégrée interroge RansomLook toutes les 15 minutes environ. Le dashboard relit la base toutes les 60 secondes. Ce mécanisme n'est pas un flux temps réel garanti.

Ne lancer qu'un worker par base : le calendrier persiste, mais il n'existe pas de verrou de planification distribué entre plusieurs processus. Le nom d'une source doit rester stable pour conserver son historique et ses délais.

## Sources intégrées

| Source | Activation | Données conservées |
| --- | --- | --- |
| RansomLook `/api/recent` | Activée dans `config/sources.live.json`, sans clé lors de la vérification | Organisation, groupe et date d'observation fournisseur |
| Ransomware.live PRO `/victims/recent` | Optionnelle, désactivée tant que vous n'avez pas configuré votre clé | Organisation, groupe, pays, secteur et date d'observation fournisseur |

Les données sont attribuées à leur fournisseur dans les observations. Ces fournisseurs surveillent des publications de groupes ransomware ; Sentinel interroge leurs API HTTPS publiques. Il ne contacte pas directement les sites onion avec cette configuration et ne vérifie pas les revendications indépendamment.

La documentation officielle : [RansomLook](https://www.ransomlook.io/doc/) et [Ransomware.live PRO](https://api-pro.ransomware.live/docs). Consulter leurs conditions et limites avant de redistribuer des données ou d'augmenter le volume. L'accès à une API publique n'implique pas des droits de redistribution illimités.

## Activer Ransomware.live PRO

La documentation PRO demande l'en-tête `X-API-KEY` et indique [où obtenir une clé](https://www.ransomware.live/my). Ne partagez pas la clé dans le chat, dans un fichier suivi par Git ou dans une capture d'écran.

Dans un terminal Bash, saisir la clé sans l'inscrire dans l'historique :

```bash
read -r -s -p 'Ransomware.live API key: ' RANSOMWARE_LIVE_API_KEY
export RANSOMWARE_LIVE_API_KEY
printf '\n'
```

Dans `config/sources.live.json`, mettre `enabled` à `true` pour Ransomware.live PRO, puis lancer `python -m sentinel monitor`. Le programme lit la variable d'environnement ; il ne charge pas automatiquement `.env`. L'en-tête secret n'est envoyé qu'à l'URL HTTPS exacte du fournisseur, jamais à une URL arbitraire et jamais après redirection.

Cette intégration a été validée contre la documentation et des fixtures fictives. Aucun appel authentifié n'a été réalisé sans votre clé. L'ancien endpoint Ransomware.live v2 n'est pas utilisé ; sa vérification TLS échouait dans cet environnement. Aucune vérification TLS n'a été désactivée.

## Trois horloges différentes

- **First seen** : première observation locale par Sentinel. Un import initial fait apparaître les publications historiques comme nouvellement ingérées.
- **Provider first observed** : date `discovered` déclarée par le fournisseur, conservée dans chaque observation de source.
- **Last successful sync** : date du dernier téléchargement et traitement réussis de cette source.

Les dates sans fuseau sont interprétées comme UTC. La date estimée d'attaque de PRO n'est pas confondue avec une date de publication : elle n'est pas ingérée. Les graphiques restent basés sur la première observation locale. Le champ pays/secteur reste `Unknown` quand RansomLook ne le fournit pas.

## État des sources

Le panneau Collection health présente : dernier succès, dernière observation fournisseur, prochain instant d'éligibilité, nombre d'échecs et état de synchronisation.

- `fresh` : synchronisation réussie depuis moins de deux intervalles, avec un seuil minimal de 30 minutes ; ce n'est pas une preuve de fraîcheur de chaque publication.
- `stale` : dernier succès trop ancien, y compris lorsque le worker a été arrêté.
- `error` : dernière tentative échouée ; les données existantes restent consultables.
- `never synced` / `disabled` : aucune synchronisation réussie / source inactive.

`Eligible to poll after` indique un délai enregistré en base, pas une garantie que le worker est en cours d'exécution. Après un échec, le délai double progressivement jusqu'à 24 heures. Un `Retry-After` plus long est respecté. Une réponse 429 n'entraîne pas de boucle de tentatives immédiates. Les délais persistent après redémarrage et s'appliquent aussi aux collectes manuelles.

```sh
# Une seule tentative, si le délai l'autorise
python -m sentinel collect --config config/sources.live.json

# Collecteur séparé, sans dashboard
python -m sentinel collect --config config/sources.live.json --interval 900
```

Le fichier de configuration d'une collecte devient l'inventaire actif des sources pour cette base. Les anciennes sources absentes sont marquées désactivées. Pour isoler plusieurs configurations, utiliser des bases distinctes avec `--db`.

## Limites de couverture

Les deux endpoints portent sur les 100 dernières publications : une longue interruption ou un volume élevé peut créer des trous de couverture. Aucun rattrapage historique automatique n'est implémenté. Les variantes de noms entre fournisseurs peuvent créer des doublons ; les rapprochements utilisent toujours acteur + organisation.

Les identités restent des revendications non vérifiées. Les descriptions, captures d'écran, liens de téléchargement, archives volées et enrichissements infostealer ne sont pas stockés. Une réponse dont le schéma change fait échouer la source plutôt que d'inventer des champs.

## Vérification réalisée

Une collecte réelle de RansomLook a retourné HTTP 200, observé 100 publications et ajouté 100 identités locales. Cette vérification ponctuelle prouve le fonctionnement du connecteur à cet instant ; elle ne garantit pas la disponibilité future du fournisseur. Les données sont uniquement dans la base locale ignorée par Git.

Pour un portfolio public, démontrer le fonctionnement avec des données fictives et expliquer les différences entre première ingestion, date fournisseur et date réelle d'un incident.
