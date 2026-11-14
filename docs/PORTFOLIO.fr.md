# Présenter Sentinel pour une candidature

## Positionnement

**Sentinel — plateforme locale de veille sur les revendications ransomware et d'investigation analyste.**

Ce projet permet de montrer du développement Python, du traitement de données, de la compréhension des besoins SOC/CTI, des tests automatisés et une démarche de sécurité. Il s'agit d'un projet personnel de laboratoire, pas d'un service ayant détecté des incidents réels en production.

## Démonstration de cinq minutes

1. **Problème — 30 secondes.** « Un analyste doit centraliser les métadonnées de plusieurs sources et distinguer une nouvelle observation d'un incident confirmé. »
2. **Vue d'ensemble — 45 secondes.** Montrer les données fictives, les filtres, les graphiques et la différence entre date de publication et première observation.
3. **Cas analyste — 90 secondes.** Ajouter `Healthcare` à la watchlist, ouvrir une organisation, passer le statut à `investigating`, sélectionner une priorité et écrire une note. Sauvegarder puis rouvrir pour montrer la persistance et l'historique.
4. **Fiabilité — 60 secondes.** Expliquer la déduplication, les observations par source et la réponse HTTP 409 lorsqu'un onglet tente d'enregistrer une version périmée. Montrer le test correspondant.
5. **Ingénierie — 45 secondes.** Lancer la suite de tests. Présenter la configuration CI, la migration additive et le paquet Python.
6. **Limites — 30 secondes.** Pas de confirmation automatique d'incident, pas de données volées téléchargées, pas d'authentification multi-utilisateur ni de validation réelle des sources Tor.

Exemple de note de démonstration :

> Revendication observée dans le jeu fictif. Vérifier l'identité de l'organisation et rechercher une confirmation indépendante. Priorité élevée choisie par l'analyste pour l'exercice ; aucune compromission confirmée.

## Texte pour le CV

À utiliser uniquement après avoir exécuté et compris les fonctionnalités décrites :

**Sentinel — projet personnel Python / SQLite / JavaScript**

- Développé un outil local de veille sur des métadonnées de revendications ransomware, avec collecteurs JSON/HTML, déduplication et suivi de provenance.
- Implémenté un workflow d'investigation avec notes, priorités, historique transactionnel et contrôle de concurrence optimiste.
- Ajouté des tests automatisés de persistance, migration, API et contrôles de sécurité, ainsi qu'une configuration CI GitHub Actions multi-version Python.

Ne pas ajouter de nombre de victimes réelles détectées, de pourcentage de réduction du temps analyste, de disponibilité ou de couverture sans mesure reproductible. La configuration CI n'est pas une preuve d'exécution réussie sur GitHub : attendre un vrai run avant de l'affirmer.

## Questions d'entretien à préparer

| Question | Réponse à construire à partir du code |
| --- | --- |
| Pourquoi SQLite ? | Simplicité d'exploitation locale, transactions, WAL ; limites de concurrence et de volumétrie à expliciter. |
| Comment évites-tu les doublons ? | Identité déterministe acteur + organisation normalisés en minuscules Unicode ; expliquer les limites des variantes et incidents répétés. |
| Comment gères-tu deux modifications simultanées ? | Numéro de version, transaction `BEGIN IMMEDIATE`, comparaison avant écriture, conflit 409 sans perte de notes. |
| Que prouve ton historique ? | L'application garde les changements ; ce n'est pas un journal inviolable et il n'y a pas d'identité utilisateur authentifiée. |
| Pourquoi `socks5h` ? | Résolution DNS via le proxy pour les adresses onion ; Tor reste un service externe. |
| Comment évites-tu le XSS ? | Texte inséré via `textContent`, pas de HTML issu des sources, CSP ; montrer le code et distinguer cela d'un audit exhaustif. |
| Comment sais-tu qu'un incident est réel ? | Le collecteur ne le sait pas : une revendication doit être vérifiée indépendamment. |
| Que changerais-tu pour la production ? | Serveur applicatif adapté, authentification, rôles, rétention, pagination SQL, orchestration et supervision. |
| Que testent réellement tes tests ? | Cas reproductibles, fixtures et serveur loopback ; aucune preuve de disponibilité des sources réelles. |

## Préparer le dépôt public

- Choisir une licence avant diffusion ; aucune licence n'a été choisie à votre place.
- Relire les fichiers suivis : pas de base SQLite, de notes privées, d'adresses de sources privées ou de secrets.
- Exécuter les commandes du README dans un environnement neuf.
- Ajouter deux captures réelles : tableau de bord et investigation avec historique. Les captures doivent montrer des données fictives.
- Enregistrer une courte démonstration et ajouter son lien au README.
- Publier le dépôt, vérifier le résultat du workflow CI et épingler le projet sur le profil GitHub.
- Adapter le résumé du projet au poste visé : SOC/CTI (analyse et limites), backend Python (transactions/API/tests), sécurité applicative (frontières de confiance).

## Travail personnel pour maîtriser le projet

1. Lire `store.py` et expliquer chaque transaction sans assistance.
2. Écrire une fixture HTML fictive avec une structure différente et ajouter son adaptateur testé.
3. Provoquer un échec de parsing et expliquer ce qui apparaît dans Collection health.
4. Ouvrir la même investigation dans deux onglets et expliquer le conflit de sauvegarde.
5. Mesurer une latence d'import ou un temps de réponse sur un jeu synthétique dont la taille est connue ; publier la méthode avec le résultat.

Un portfolio convaincant repose sur une démonstration reproductible et la capacité à défendre les choix techniques. Ce projet peut soutenir une candidature ; il ne garantit pas une embauche.
