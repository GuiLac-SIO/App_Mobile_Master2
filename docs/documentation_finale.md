# 🛡️ Secure Votes — Documentation Finale du Projet

---

## 📝 Introduction

Ce document présente la conception, l'architecture et les fonctionnalités du projet **Secure Votes**, réalisé dans le cadre de nos attentes académiques. Le projet répond à une problématique complexe : comment concevoir un système de consultation citoyenne sur le terrain qui garantit à la fois la **confidentialité absolue des votes** individuels, la **transparence des résultats** et l'**intégrité totale des données** face aux risques de falsification ou de compromission des serveurs.

Dans cette documentation, nous aborderons en détail les fonctionnalités de nos interfaces graphiques (GUI) ainsi que les règles de sécurité strictes implémentées à chaque couche de l'application pour répondre scrupuleusement aux exigences du cahier des charges.

---

## 💻 1. Fonctionnalités des Interfaces Graphiques (GUI)

Le projet propose deux interfaces distinctes, pensées pour deux cas d'usage radicalement différents : l'agent sur le terrain (mobile-first) et l'administrateur système (desktop).

### 1.1 L'Application "Agent Terrain" (Frontend PWA)

L'application de l'agent terrain a été conçue comme une **Progressive Web App (PWA)**, permettant une utilisation fluide sur smartphone en conditions réelles (hors connexion, accès aux composants matériels du téléphone).

* **Scan de QR Codes (Questions & Participants) :** L'application accède à la caméra du smartphone de l'agent pour scanner les identifiants. Pour des raisons pragmatiques, une saisie manuelle est aussi disponible.
* **Sécurité à la source (Vote et Photo) :** 
  * Le vote binaire (Oui/Non) est **chiffré localement sur le téléphone** de l'agent en utilisant la clé publique (Chiffrement Homomorphe de Paillier) avant même de transiter sur le réseau.
  * La photo justificative prise par l'agent est chiffrée localement en **AES-256-GCM** via la Web Crypto API du navigateur. Le serveur ne reçoit que des données illisibles.
* **Mode Hors-Ligne (Offline Sync) :** Si l'agent perd sa connexion internet (ex: zone blanche), l'application stocke les votes chiffrés de manière sécurisée dans le navigateur (`localStorage`) et les transmet automatiquement en arrière-plan dès que la connexion est rétablie.

> **[Insérer Screenshot de l'Application Agent Terrain (ex: Écran de Scan QR ou Écran de Vote) ici]**

### 1.2 Le Tableau de Bord Administrateur (Admin Dashboard)

Le tableau de bord permet aux superviseurs de gérer le système, de suivre les statistiques en temps réel et, surtout, de procéder au dépouillement en garantissant le secret des votes.

* **Statistiques en Temps Réel :** Vue d'ensemble sur le nombre de votes collectés, le nombre de questions actives, de participants et les journaux d'audit.
* **Gestion des Utilisateurs & RBAC :** Interface pour créer, éditer et supprimer des agents terrain et d'autres administrateurs. Seuls les administrateurs ont accès à cette interface via vérification de jeton JWT (Role-Based Access Control).
* **Générateur de QR Codes :** Un outil intégré permettant de générer à la volée des QR codes pour les identifiants de questions (ex: `Q-001`) ou de participants pour faciliter le vote sur le terrain.
* **Agrégation Homomorphe (Le Dépouillement) :** C'est le cœur du système. L'administrateur peut demander au serveur de calculer la somme des votes pour une question donnée. Le serveur additionne **tous les votes chiffrés entre eux** mathématiquement sans jamais les déchiffrer. L'interface reçoit la "somme chiffrée" et seul le détenteur de la clé privée finale peut révéler le résultat (ex: "45 Oui, 55 Non"), sans jamais savoir "qui a voté quoi".
* **Vérification de l'Intégrité (Audit) :** Un onglet dédié permet de déclencher une validation cryptographique de l'ensemble de la base de données pour s'assurer qu'aucun vote n'a été altéré.

> **[Insérer Screenshot du Dashboard Administrateur (ex: Vue Statistiques ou Générateur QR) ici]**
> **[Insérer Screenshot du Résultat de l'Agrégation Homomorphe ici]**

---

## 🔒 2. Mesures & Règles de Sécurité Implémentées

Pour répondre aux attentes strictes du professeur et aux standards de l'industrie (protection de la vie privée, RGPD, ISO 27001), l'architecture a été conçue autour du principe du *"Zero Trust"* (Confiance Zéro) et de la défense en profondeur.

### 2.1 Anonymat et Confidentialité (Chiffrement Homomorphe)
La règle d'or du système est que **le backend ne doit jamais connaitre le choix de l'électeur en clair**.  
* **Implémentation :** Nous avons implémenté le cryptosystème de **Paillier** (homomorphe additif). Le vote (0 ou 1) est transformé en un grand nombre aléatoire (Ciphertext) sur le téléphone de l'agent.
* **Résultat :** Le serveur de base de données stocke des nombres inintelligibles. Cependant, la magie de Paillier permet d'additionner ces données chiffrées. Si un attaquant pirate la base de données, il ne verra qu'une suite de chiffres aléatoires. L'anonymat est mathématiquement garanti.

### 2.2 Ségrégation des Données (Silos Isolés)
Afin d'éviter la corrélation (relier un électeur à son vote ou à sa photo en cas de fuite de données), la base de données PostgreSQL a été cloisonnée.
* **Implémentation :** La base est divisée en plusieurs "schémas" logiques et physiques :
  * `identity` : Ne contient que des HASH (SHA-256) irréversibles des QR codes scannés.
  * `votes` : Ne contient que le vote chiffré mathématiquement.
  * `photos` : Contient les métadonnées de déchiffrement (Nonce), la donnée brute étant sur un serveur de stockage S3 séparé (MinIO).
* **Résultat :** Même en cas de fuite d'un des silos, aucune information liant formellement une identité en clair à un vote n'existe.

### 2.3 Traçabilité Infaillible (Hash-Chain & Audit)
Comment s'assurer qu'un administrateur corrompu n'a pas supprimé ou falsifié un vote directment dans la base de données Postgres ?
* **Implémentation :** Dès qu'un vote ou une photo arrive sur le serveur, une ligne de "Log" est créée dans le silo d'Audit. Cette ligne est scellée par un **HASH cryptographique** qui inclut les informations de l'action ET le hash de l'action précédente (`prev_hash`).
* **Résultat :** C'est le principe d'une Blockchain privée. Si quelqu'un modifie une ligne au milieu de la base de données, la chaîne est brisée mathématiquement. Le système d'audit (bouton "Vérifier hash-chain" sur le Dashboard) clignotera en rouge immédiatement.

### 2.4 Le Principe du Moindre Privilège (IAM)
* **Implémentation :** L'API Python FastAPI qui se connecte à la base de données utilise un utilisateur restreint (`app_user`). Ce rôle n'est **pas super-utilisateur**. De plus, les droits (`GRANT`) sont limités : l'API a le droit d'insérer des données (`INSERT`) et de les lire (`SELECT`), mais elle n'a **strictement pas le droit d'effacer ou de mettre à jour** (`REVOKE DELETE, UPDATE`) des votes !
* **Résultat :** Même si toute l'application FastAPI ou le code Python est compromis et qu'un pirate prend le contrôle du serveur API, il lui est impossible d'effacer les votes dans la base de données, limitant considérablement l'impact d'une attaque.

### 2.5 Validation Dure des Entrées (Frontend & Backend)
* **API REST :** Toute donnée entrante côté serveur est validée drastiquement par la biliothèque `Pydantic` (Vérification des longueurs, caractères autorisés). Si un agent terrain bidouille la requête HTTP, elle est rejetée (Erreur 422). 
* **Vérification croisée :** Lorsqu'un vote est soumis, le backend vérifie que l'ID de la question existe *réellement* et est "active". De même pour l'interface frontend (GUI) qui interroge l'API avant d'autoriser l'agent à scanner un participant si la question initiale est introuvable.

### 2.6 Sécurité des Échanges et de l'Hébergement Web
* **Headers de sécurité :** Le serveur renvoie des entêtes stricts pour le navigateur (`Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`) empêchant toute tentative d'injection script (XSS) via la PWA.
* **CORS :** Le partage des ressources multiorigine est verrouillé pour n'accepter des requêtes API que depuis le port d'hébergement original de l'application cliente.

---

## Conclusion
Ce projet démontre qu'il est possible de concilier la praticité d'une application mobile moderne (PWA, mode hors-ligne, scan caméra) avec des concepts algorithmiques de pointe (chiffrement homomorphe, signature AES-GCM client-side, chaînage par Hash block). Les attentes globales de sécurité de la donnée, du transit jusqu'au repos, ont été traitées à travers une modélisation défensive à chaque étape réseau.

> **[Insérer tout autre Screenshot pertinent ou Diagramme de l'architecture ici]**
