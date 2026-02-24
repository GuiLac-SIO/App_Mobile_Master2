# 🛡️ Secure Votes — Système de collecte et d'agrégation homomorphe de votes

Système sécurisé permettant la collecte terrain de votes binaires (Oui/Non) avec chiffrement homomorphe (Paillier), stockage chiffré des photos (AES-256-GCM), et journalisation immuable (hash-chain).

---

## 📐 Architecture

```
┌─────────────────┐     HTTPS      ┌──────────────┐     ┌──────────────┐
│  Application    │◄──────────────►│   Nginx      │────►│  FastAPI     │
│  Agent Terrain  │  (port 3000)   │  Reverse     │     │  Backend     │
│  (PWA)          │                │  Proxy       │     │  (port 8000) │
└─────────────────┘                └──────────────┘     └──────┬───────┘
                                                               │
                                          ┌────────────────────┼────────────────────┐
                                          ▼                    ▼                    ▼
                                   ┌──────────┐         ┌──────────┐         ┌──────────┐
                                   │ PostgreSQL│         │  MinIO   │         │  Paillier│
                                   │ 4 silos  │         │  Photos  │         │  Crypto  │
                                   │ chiffrés │         │ chiffrées│         │  Module  │
                                   └──────────┘         └──────────┘         └──────────┘
```

### Silos de données (PostgreSQL)

| Schéma     | Table          | Contenu                              |
|------------|----------------|--------------------------------------|
| `identity` | `participants` | Hachés SHA-256 (participant + agent) |
| `votes`    | `votes`        | Chiffrés Paillier (ciphertext)       |
| `audit`    | `logs`         | Hash-chain (payload_hash + prev_hash)|
| `photos`   | `photos`       | Métadonnées AES-GCM (nonce, tag)     |

---

## 🚀 Démarrage rapide

### Prérequis
- Docker & Docker Compose

### Lancer le projet

```bash
# Copier la configuration
cp .env.example .env

# Lancer tous les services
docker compose up -d --build
```

### Accès

| Service              | URL                          |
|----------------------|------------------------------|
| **App Agent Terrain**| http://localhost:3000         |
| **Admin Dashboard**  | http://localhost:3000/dashboard.html |
| **API Backend**      | http://localhost:8080         |
| **Swagger / OpenAPI**| http://localhost:8080/docs    |
| **Page démo API**    | http://localhost:8080/demo    |
| **MinIO Console**    | http://localhost:9001         |

---

## 🧪 Tests

```bash
# Exécuter les tests (8 fichiers, ~20 tests)
docker compose run --rm api pytest tests/ -v
```

### Fichiers de tests

| Fichier                  | Couverture                          |
|--------------------------|-------------------------------------|
| `test_health.py`         | Endpoint health + connectivité DB   |
| `test_votes_send.py`     | Soumission vote + audit + hashage   |
| `test_votes_aggregate.py`| Agrégation homomorphe Paillier      |
| `test_upload_photo.py`   | Upload photo AES-GCM + MinIO       |
| `test_audit_chain.py`    | Hash-chain intégrité + corruption   |
| `test_db_models.py`      | Insertion/lecture silos séparés      |
| `test_paillier.py`       | Encrypt/decrypt + addition homomorphe|
| `test_iam.py`            | Vérification moindre privilège DB   |

---

## 🔍 Scripts d'audit de sécurité

```bash
# Lancer tous les audits
docker compose run --rm api python -m audit.run_all_audits
```

| Script                     | Vérification                         |
|----------------------------|--------------------------------------|
| `check_votes_encrypted.py` | Votes jamais stockés en clair (0/1)  |
| `check_photos_encrypted.py`| Photos avec nonce, tag, key_id       |
| `check_iam.py`             | Rôle DB non-superuser, grants OK     |
| `check_hash_chain.py`      | Intégrité chaîne d'audit             |
| `check_network.py`         | Ports exposés conformes              |

Les audits produisent un fichier `audit_report.json`.

---

## 🔐 Sécurité

### Chiffrement homomorphe (Paillier)
- Clé 256 bits (pédagogique)
- Chiffrement côté client (BigInt JS) ou serveur
- Agrégation sans déchiffrement individuel

### Chiffrement photos (AES-256-GCM)
- Chiffrement côté client (Web Crypto API)
- Nonce + tag stockés séparément
- Photos stockées dans MinIO (silo isolé)

### Intégrité (Hash Chain)
- Chaque entrée d'audit liée à la précédente via `prev_hash`
- Détection automatique de corruption

### IAM
- Rôle `app_user` non-superuser (NOSUPERUSER NOCREATEDB NOCREATEROLE)
- Permissions limitées par schéma (SELECT, INSERT uniquement)
- Endpoint `/iam/verify` pour audit programmatique

### Headers de sécurité
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Strict-Transport-Security`
- CORS restreint aux origines autorisées

---

## 📡 API Endpoints

| Méthode | Endpoint            | Description                      |
|---------|---------------------|----------------------------------|
| GET     | `/health`           | Health check (API + DB)          |
| POST    | `/votes/send`       | Soumettre un vote chiffré        |
| GET     | `/votes/aggregate`  | Agrégation homomorphe            |
| POST    | `/uploads/photo`    | Upload photo chiffrée            |
| GET     | `/audit/verify`     | Vérifier intégrité hash-chain    |
| GET     | `/audit/logs`       | Consulter les logs d'audit       |
| GET     | `/iam/verify`       | Vérifier permissions DB          |
| GET     | `/crypto/pubkey`    | Clé publique Paillier (démo)     |
| POST    | `/crypto/encrypt`   | Chiffrer un vote (fallback)      |
| PUT/DEL | `/admin/users/{id}` | Gérer les utilisateurs (Admin)   |

---

## 📑 Documentation Finale

Le rapport exhaustif validant les choix techniques demandés par vos professeurs (Justification de l'Architecture, Séparation en Silos, CI/CD, RBAC, etc.) est disponible dans le fichier Word suivant :
- `docs/Documentation_Finale_V2.docx`

---

## 🏗️ CI/CD

Pipeline GitHub Actions (`.github/workflows/ci.yml`) avec 4 jobs :

1. **Lint** — Ruff (qualité de code + règles sécurité)
2. **Tests** — pytest avec PostgreSQL + MinIO en services
3. **Dependency Scan** — pip-audit (vulnérabilités)
4. **Secret Scan** — detect-secrets (secrets dans le code)

---

## 📁 Structure du projet

```
Sujet_cnam/
├── docker-compose.yml          # Orchestration 4 services
├── .env.example                # Variables d'environnement
├── .github/workflows/ci.yml   # Pipeline CI/CD
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml          # Config lint + pytest
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py             # FastAPI (10 endpoints)
│   │   ├── db.py               # 4 silos PostgreSQL + hash-chain
│   │   ├── storage.py          # MinIO S3 client
│   │   └── crypto/
│   │       └── paillier.py     # Chiffrement homomorphe
│   ├── audit/
│   │   ├── run_all_audits.py   # Script d'audit principal
│   │   ├── check_*.py          # 5 vérifications de sécurité
│   ├── db_init/
│   │   └── init.sql            # Rôles IAM + permissions
│   └── tests/                  # 8 fichiers de tests
├── frontend/
│   ├── index.html              # App agent terrain (PWA)
│   ├── dashboard.html          # Tableau de bord Administrateur (Gestion & Résultats)
│   ├── nginx.conf              # Config reverse proxy
│   ├── css/style.css           # UI mobile-first dark
│   └── js/
│       ├── app.js              # Workflow 5 étapes (Avec validation de question)
│       ├── paillier.js         # Paillier côté client (BigInt)
│       ├── crypto.js           # AES-256-GCM (Web Crypto)
│       ├── api.js              # Client API backend
│       └── qr-scanner.js       # Scanner QR (html5-qrcode)
└── docs/
    ├── Documentation_Finale_V2.docx # Rapport écrit complet
    ├── rapport_conception.md   # Rapport Phase 1
    └── api_reference.md        # Documentation API
```

---

## ⚠️ Avertissement

> Ce projet est un **prototype pédagogique**. Le chiffrement Paillier utilise des clés de 256 bits (non adapté à la production). En production, utiliser une bibliothèque auditée (python-phe, SEAL) avec des clés ≥ 2048 bits.
