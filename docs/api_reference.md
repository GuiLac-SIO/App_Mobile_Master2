# Référence API — Secure Votes Backend

Base URL: `http://localhost:8080`

---

## Santé

### `GET /health`

Vérifie la disponibilité de l'API et de la base de données.

```bash
curl http://localhost:8080/health
```

**Réponse 200 :**
```json
{"status": "ok", "database": "ok"}
```

---

## Votes

### `POST /votes/send`

Soumet un vote chiffré (Paillier) associé à une question et un participant.

```bash
curl -X POST http://localhost:8080/votes/send \
  -H "Content-Type: application/json" \
  -d '{
    "question_id": "Q-001",
    "participant_id": "P-042",
    "agent_id": "agent-terrain-1",
    "ciphertext": "123456789012345678901234567890",
    "key_id": "key-v1"
  }'
```

**Réponse 201 :**
```json
{
  "status": "stored",
  "vote_id": 1,
  "question_id": "Q-001",
  "key_id": "key-v1"
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `question_id` | string (1-64) | ID unique de la question |
| `participant_id` | string (1-256) | ID du participant (hashé avant stockage) |
| `agent_id` | string (1-256) | ID de l'agent (hashé avant stockage) |
| `ciphertext` | string | Vote chiffré Paillier (entier décimal) |
| `key_id` | string (1-64) | ID de la clé utilisée |

---

### `GET /votes/aggregate`

Agrégation homomorphe des votes pour une question donnée.

```bash
curl "http://localhost:8080/votes/aggregate?question_id=Q-001&key_id=key-v1"
```

**Réponse 200 :**
```json
{
  "question_id": "Q-001",
  "key_id": "key-v1",
  "count": 5,
  "aggregate_ciphertext": "987654321...",
  "total": 3
}
```

| Paramètre | Type | Description |
|-----------|------|-------------|
| `question_id` | query string | ID de la question |
| `key_id` | query string | ID de la clé (défaut: `key-v1`) |

---

## Photos

### `POST /uploads/photo`

Upload d'une photo chiffrée (AES-256-GCM) vers MinIO.

```bash
curl -X POST http://localhost:8080/uploads/photo \
  -H "Content-Type: application/json" \
  -d '{
    "object_name": "Q-001_P-042_1708800000",
    "nonce_b64": "bm9uY2UxMjM0NTY=",
    "tag_b64": "dGFnMTIzNDU2Nzg5MDEyMzQ1Ng==",
    "ciphertext_b64": "Y2lwaGVydGV4dA==",
    "content_type": "image/jpeg",
    "key_id": "aes-demo",
    "alg": "AES-256-GCM"
  }'
```

**Réponse 201 :**
```json
{
  "status": "stored",
  "bucket": "photos",
  "object_name": "Q-001_P-042_1708800000",
  "photo_id": 1
}
```

---

## Audit

### `GET /audit/verify`

Vérifie l'intégrité de la chaîne d'audit (hash chain).

```bash
curl http://localhost:8080/audit/verify
```

**Réponse 200 :**
```json
{"ok": true, "length": 12, "broken_id": null}
```

### `GET /audit/logs`

Retourne les dernières entrées d'audit.

```bash
curl "http://localhost:8080/audit/logs?limit=10"
```

**Réponse 200 :** Liste d'objets avec `id`, `event_type`, `payload_hash`, `prev_hash`, `created_at`.

---

## IAM

### `GET /iam/verify`

Vérifie que le rôle DB respecte le moindre privilège.

```bash
curl http://localhost:8080/iam/verify
```

**Réponse 200 :**
```json
{
  "rolsuper": false,
  "rolcreatedb": false,
  "rolcreaterole": false,
  "rolreplication": false,
  "can_insert_votes": true,
  "can_select_votes": true,
  "can_select_identities": true
}
```

---

## Cryptographie

### `GET /crypto/pubkey`

Retourne la clé publique Paillier de démo pour le chiffrement client-side.

```bash
curl http://localhost:8080/crypto/pubkey
```

**Réponse 200 :**
```json
{
  "key_id": "key-v1",
  "n": "123456789...",
  "g": "123456790..."
}
```

### `POST /crypto/encrypt`

Chiffre un vote binaire avec Paillier côté serveur (fallback).

```bash
curl -X POST http://localhost:8080/crypto/encrypt \
  -H "Content-Type: application/json" \
  -d '{"plaintext": 1}'
```

**Réponse 200 :**
```json
{
  "key_id": "key-v1",
  "plaintext": 1,
  "ciphertext": "987654321..."
}
```
