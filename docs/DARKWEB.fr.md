# Connexion directe aux sites onion publics

## Ce qui fonctionne

Le preset `config/sources.darkweb.json` combine la source HTTPS RansomLook et un adaptateur direct pour la page publique de publications Endzone. L'adresse onion provient de [l'annuaire RansomLook](https://www.ransomlook.io/api/group/endzone) ; sa disponibilité a été vérifiée séparément via Tor.

Vérification réalisée : Tor a atteint `Bootstrapped 100%`, le diagnostic officiel a confirmé une route Tor, et la page onion a répondu. Le parsing des cartes `.glow-card` a observé **3 revendications**, dont **1 nouvelle identité locale** et **2 déjà connues**. Les observations directes sont conservées à côté de celles provenant de l'API. Ce résultat est ponctuel et ne garantit pas la disponibilité future du site ni la véracité des revendications.

## Démarrer

Depuis la racine du dépôt, Docker et son plugin Compose étant disponibles :

```sh
# Construire et lancer uniquement le client Tor
# Docker utilise les paquets Tor officiels de Debian, sans image Tor tierce.
docker compose -p sentinel-tor -f deployment/tor/compose.yml up --build -d

# Attendre « Bootstrapped 100% » dans les journaux
docker compose -p sentinel-tor -f deployment/tor/compose.yml logs --tail 20

source .venv/bin/activate
python -m sentinel tor-check
python -m sentinel monitor --config config/sources.darkweb.json
```

Ouvrir **http://127.0.0.1:8000/?mode=live**. Dans Collection health, la source directe porte la mention **DIRECT ONION · Tor SOCKS transport**. Ouvrir une organisation pour examiner ses observations et distinguer la source API de la source onion.

Le preset interroge la page onion environ une fois par heure. La source HTTPS conserve son intervalle de 15 minutes. Une relance respecte les échéances persistantes ; `waiting` indique un délai restant, pas une panne. Ne pas lancer plusieurs workers pour la même base.

Pour ne faire qu'une passe :

```sh
python -m sentinel collect --config config/sources.darkweb.json
```

Pour arrêter : Ctrl+C dans le terminal du monitor, puis :

```sh
docker compose -p sentinel-tor -f deployment/tor/compose.yml stop
```

Le conteneur n'a pas de redémarrage automatique. Après un arrêt ou redémarrage de Docker, relancer `up -d`. La configuration n'installe aucun service système Tor sur l'hôte.

## Chemin réseau

```text
Collecteur Python
    -> SOCKS5 avec résolution distante, 127.0.0.1:9050
    -> client Tor dans un conteneur Debian
    -> réseau Tor
    -> service onion public
    -> parsing HTML local
    -> métadonnées et provenance SQLite
```

Le proxy est publié sur la boucle locale uniquement. Le conteneur est exécuté avec un utilisateur non privilégié, sans capabilities Linux, avec système de fichiers en lecture seule et stockage Tor temporaire. Aucun ControlPort n'est exposé. Tor n'est pas utilisé comme relais public.

Les modes `onion_html` et `onion_status` exigent une adresse onion v3 valide, y compris sa somme de contrôle, et un proxy local `socks5h` avec un port explicite. Une erreur de proxy ne déclenche jamais de connexion directe de secours. Les redirections sont refusées ; si un site déménage, mettre à jour sa source après vérification.

Le comportement SOCKS/DNS s'appuie sur les [recommandations du projet Tor](https://support.torproject.org/little-t-tor/troubleshooting/check-for-leaks/). Le diagnostic utilise `https://check.torproject.org/api/ip` via le proxy et ne conserve pas l'adresse IP de sortie. Un diagnostic réussi confirme une route de sortie Tor, pas l'accessibilité de chaque service onion. Le dashboard indique son horodatage ; il ne s'agit pas d'un indicateur de connexion instantané.

## Périmètre de collecte

L'adaptateur Endzone lit seulement `h2.company-name` à l'intérieur de `.glow-card`. Les avertissements hors cartes et les fenêtres présentant des échantillons ne sont pas interprétés comme des victimes.

Le corps HTML est nécessairement reçu temporairement en mémoire pour le parser. Il n'est pas enregistré en base. Les scripts ne sont pas exécutés ; les images, liens de téléchargement, archives, échantillons, boutons de contact et endpoints de discussion ne sont pas suivis. Seuls le nom revendiqué, le groupe configuré, l'URL source et les dates locales d'observation sont persistés. Aucun pays, secteur ou horodatage fournisseur n'est inventé.

Si les cartes disparaissent, le parsing échoue et la source est signalée en erreur. Si le HTML change tout en conservant les mêmes classes, un contrôle manuel reste nécessaire : les sélecteurs ne garantissent pas une extraction correcte pour toujours.

`onion_status` permet aussi de surveiller uniquement la disponibilité HTTP d'une page. Un HTTP 200 ne prouve ni qu'une page est authentique ni qu'elle contient des publications valides. Ce mode ne crée aucune victime.

## Ajouter un autre site

Ajouter une source `onion_html` avec une adresse de page publique vérifiée, un acteur, un `item_selector` et des sélecteurs de champs précis. Tester le parseur sur une fixture fictive avant activation. Ne pas réutiliser les sélecteurs Endzone sur un autre site sans les vérifier. Aucun mécanisme ne contourne les CAPTCHA, pages de connexion ou restrictions d'accès.

Ne pas présenter ce projet comme couvrant tout le dark web : il surveille une page configurée par source, sans pagination ni exploration récursive. L'attribution des domaines repose sur l'annuaire et l'examen du site ; elle n'est pas une preuve cryptographique de l'identité d'un groupe.
