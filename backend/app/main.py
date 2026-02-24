from contextlib import asynccontextmanager

import base64
from fastapi import Depends, FastAPI, HTTPException, Header, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncEngine
from typing import Optional

from app.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    create_token,
    decode_token,
    hash_password,
    verify_password,
    JWT_EXPIRE_MINUTES,
)
from app.crypto.paillier import PrivateKey, PublicKey, add, decrypt, encrypt, generate_keypair
from app.db import (
    check_db_connection,
    create_question,
    create_user,
    fetch_audit_logs,
    fetch_votes_by_question,
    get_engine,
    get_user_by_username,
    get_vote_stats,
    init_db,
    list_questions,
    list_users,
    record_photo_metadata,
    record_vote,
    verify_db_permissions,
    verify_hash_chain,
)
from app.storage import ensure_bucket, get_bucket_name, get_s3_client, put_object


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create engine at startup, dispose on shutdown
    engine = get_engine()
    await init_db(engine)
    ensure_bucket(get_s3_client())
    yield
    # Do not dispose the cached engine here to avoid event-loop-closed errors in tests


app = FastAPI(
    title="Secure Votes API",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Security: CORS ───────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=False,
)


# ── Security: HTTP headers ───────────────────────────────────
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store"
    return response


DEMO_KEY_ID = "key-v1"
_DEMO_PUB, _DEMO_PRIV = generate_keypair(bits=256)


def get_demo_keypair() -> tuple[PublicKey, PrivateKey]:
    return _DEMO_PUB, _DEMO_PRIV


class VoteRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=64)
    participant_id: str = Field(min_length=1, max_length=256)
    agent_id: str = Field(min_length=1, max_length=256)
    ciphertext: str = Field(min_length=1)
    key_id: str = Field(min_length=1, max_length=64)


class PhotoUploadRequest(BaseModel):
    object_name: str = Field(min_length=1, max_length=256)
    nonce_b64: str = Field(min_length=1)
    tag_b64: str = Field(min_length=1)
    ciphertext_b64: str = Field(min_length=1)
    content_type: str = Field(min_length=1, max_length=128)
    key_id: str = Field(min_length=1, max_length=64)
    alg: str = Field(default="AES-256-GCM", min_length=5, max_length=32)


async def verify_database(engine: AsyncEngine = Depends(get_engine)) -> dict:
    try:
        await check_db_connection(engine)
        return {"db": "ok"}
    except Exception as exc:  # pragma: no cover - handled in tests via status code
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.get("/health")
async def health(database=Depends(verify_database)) -> dict:
    """Simple liveness/readiness probe that also checks database connectivity."""
    return {"status": "ok", "database": database["db"]}


# ── JWT Auth dependency ─────────────────────────────────

async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Extract and verify JWT token from Authorization header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Token manquant")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Format: Bearer <token>")
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")
    return payload


def require_role(*roles):
    """Dependency factory: require the current user to have one of the given roles."""
    async def checker(user: dict = Depends(get_current_user)):
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Accès interdit pour ce rôle")
        return user
    return checker


# ── Auth endpoints ───────────────────────────────────

@app.post("/auth/login")
async def login(payload: LoginRequest, engine: AsyncEngine = Depends(get_engine)):
    """Authenticate a user and return a JWT token."""
    user = await get_user_by_username(engine, payload.username)
    if not user or not verify_password(payload.password, user["password_hash"], user["password_salt"]):
        raise HTTPException(status_code=401, detail="Identifiants incorrects")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Compte désactivé")
    token = create_token(user["id"], user["username"], user["role"])
    return TokenResponse(
        access_token=token,
        role=user["role"],
        username=user["username"],
        expires_in=JWT_EXPIRE_MINUTES * 60,
    )


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    engine: AsyncEngine = Depends(get_engine),
    admin: dict = Depends(require_role("admin")),
):
    """Register a new user (admin only)."""
    existing = await get_user_by_username(engine, payload.username)
    if existing:
        raise HTTPException(status_code=409, detail="Nom d'utilisateur déjà pris")
    pw_hash, salt = hash_password(payload.password)
    user = await create_user(
        engine,
        username=payload.username,
        password_hash=pw_hash,
        password_salt=salt,
        role=payload.role,
        full_name=payload.full_name,
    )
    return {"status": "created", "user_id": user["id"], "username": user["username"], "role": user["role"]}


@app.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Return current authenticated user info."""
    return {"user_id": user["sub"], "username": user["username"], "role": user["role"]}


# ── Admin endpoints ──────────────────────────────────

@app.get("/admin/stats")
async def admin_stats(
    engine: AsyncEngine = Depends(get_engine),
    admin: dict = Depends(require_role("admin", "auditor")),
):
    """Get vote/photo/audit statistics (admin/auditor only)."""
    return await get_vote_stats(engine)


@app.get("/admin/users")
async def admin_list_users(
    engine: AsyncEngine = Depends(get_engine),
    admin: dict = Depends(require_role("admin")),
):
    """List all users (admin only)."""
    users = await list_users(engine)
    # Convert datetimes to strings for JSON
    for u in users:
        if u.get("created_at"):
            u["created_at"] = str(u["created_at"])
    return users


class UpdateUserRequest(BaseModel):
    role: str | None = Field(default=None, pattern="^(agent|admin|auditor)$")
    full_name: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=4, max_length=128)


@app.put("/admin/users/{user_id}")
async def admin_update_user(
    user_id: int,
    payload: UpdateUserRequest,
    engine: AsyncEngine = Depends(get_engine),
    admin: dict = Depends(require_role("admin")),
):
    """Update a user (admin only)."""
    from app.db import update_user as db_update_user
    kwargs = {}
    if payload.role is not None:
        kwargs["role"] = payload.role
    if payload.full_name is not None:
        kwargs["full_name"] = payload.full_name
    if payload.is_active is not None:
        kwargs["is_active"] = payload.is_active
    if payload.password is not None:
        pw_hash, salt = hash_password(payload.password)
        kwargs["password_hash"] = pw_hash
        kwargs["password_salt"] = salt
    if not kwargs:
        raise HTTPException(status_code=400, detail="Aucun champ à modifier")
    result = await db_update_user(engine, user_id, **kwargs)
    if not result:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return {"status": "updated", **result}


@app.delete("/admin/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    engine: AsyncEngine = Depends(get_engine),
    admin: dict = Depends(require_role("admin")),
):
    """Delete a user (admin only). Cannot delete yourself."""
    if str(user_id) == admin.get("sub"):
        raise HTTPException(status_code=400, detail="Impossible de supprimer votre propre compte")
    from app.db import delete_user as db_delete_user
    deleted = await db_delete_user(engine, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return {"status": "deleted", "user_id": user_id}

# ── Questions endpoints ───────────────────────────────

class QuestionRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=512)


@app.post("/questions", status_code=status.HTTP_201_CREATED)
async def add_question(
    payload: QuestionRequest,
    engine: AsyncEngine = Depends(get_engine),
    user: dict = Depends(require_role("admin")),
):
    """Create a new question (admin only)."""
    q = await create_question(engine, question_id=payload.question_id, label=payload.label, created_by=user["username"])
    return {"status": "created", "question_id": q["question_id"], "label": q["label"]}


@app.get("/questions")
async def get_questions(engine: AsyncEngine = Depends(get_engine)):
    """List all active questions."""
    questions = await list_questions(engine)
    for q in questions:
        if q.get("created_at"):
            q["created_at"] = str(q["created_at"])
    return questions


@app.post("/votes/send", status_code=status.HTTP_201_CREATED)
async def send_vote(payload: VoteRequest, engine: AsyncEngine = Depends(get_engine)):
    """Store a ciphertext vote and append an audit log entry (hash-chain)."""
    try:
        vote_meta = await record_vote(
            engine,
            question_id=payload.question_id,
            participant_id=payload.participant_id,
            agent_id=payload.agent_id,
            ciphertext=payload.ciphertext,
            key_id=payload.key_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    return {
        "status": "stored",
        "vote_id": vote_meta["vote_id"],
        "question_id": vote_meta["question_id"],
        "key_id": vote_meta["key_id"],
    }


@app.post("/uploads/photo", status_code=status.HTTP_201_CREATED)
async def upload_photo(payload: PhotoUploadRequest, engine: AsyncEngine = Depends(get_engine)):
    """Store an AES-GCM encrypted photo blob into MinIO and persist metadata."""
    try:
        nonce = base64.b64decode(payload.nonce_b64)
        tag = base64.b64decode(payload.tag_b64)
        ciphertext = base64.b64decode(payload.ciphertext_b64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid base64 fields") from exc

    data = ciphertext + tag  # tag kept separately; stored together in object body
    client = get_s3_client()
    bucket = get_bucket_name()
    put_object(object_name=payload.object_name, data=data, content_type=payload.content_type, client=client, bucket=bucket)

    meta = await record_photo_metadata(
        engine,
        object_name=payload.object_name,
        nonce_b64=payload.nonce_b64,
        tag_b64=payload.tag_b64,
        alg=payload.alg,
        content_type=payload.content_type,
        size_bytes=len(data),
        key_id=payload.key_id,
    )

    return {
        "status": "stored",
        "bucket": bucket,
        "object_name": meta["object_name"],
        "photo_id": meta["photo_id"],
    }


@app.get("/votes/aggregate")
async def aggregate_votes(
    question_id: str = Query(..., min_length=1, max_length=64),
    key_id: str = Query(default=DEMO_KEY_ID, min_length=1, max_length=64),
    engine: AsyncEngine = Depends(get_engine),
):
    """Homomorphic aggregation of votes for a question/key pair (demo)."""

    pub, priv = get_demo_keypair()
    rows = await fetch_votes_by_question(engine, question_id=question_id, key_id=key_id)

    if not rows:
        return {
            "question_id": question_id,
            "key_id": key_id,
            "count": 0,
            "aggregate_ciphertext": None,
            "total": 0,
        }

    from app.crypto.paillier import encrypt as paillier_encrypt
    agg = paillier_encrypt(pub, 0)
    for row in rows:
        c_int = int(row["ciphertext"])
        agg = add(pub, agg, c_int)

    total_plain = decrypt(priv, agg)

    return {
        "question_id": question_id,
        "key_id": key_id,
        "count": len(rows),
        "aggregate_ciphertext": str(agg),
        "total": int(total_plain),
    }


@app.get("/audit/verify")
async def audit_verify(engine: AsyncEngine = Depends(get_engine)):
    """Verify audit hash-chain linkage (prev_hash consistency)."""
    result = await verify_hash_chain(engine)
    return result


@app.get("/iam/verify")
async def iam_verify(engine: AsyncEngine = Depends(get_engine)):
    """Report DB role privileges and required table grants (simulation IAM check)."""
    return await verify_db_permissions(engine)


@app.get("/audit/logs")
async def audit_logs(limit: int = Query(default=50, ge=1, le=200), engine: AsyncEngine = Depends(get_engine)):
    """Return the latest audit entries (for demo/debug)."""
    return await fetch_audit_logs(engine, limit=limit)


# ── Crypto endpoints (for client-side integration) ───────────


class EncryptRequest(BaseModel):
    plaintext: int = Field(ge=0, le=1, description="Vote binaire: 0 ou 1")


@app.get("/crypto/pubkey")
async def get_public_key():
    """Return the demo Paillier public key for client-side encryption."""
    pub, _ = get_demo_keypair()
    return {
        "key_id": DEMO_KEY_ID,
        "n": str(pub.n),
        "g": str(pub.g),
    }


@app.post("/crypto/encrypt")
async def encrypt_vote(payload: EncryptRequest):
    """Encrypt a binary vote with the demo Paillier public key (server-side fallback)."""
    pub, _ = get_demo_keypair()
    ciphertext = encrypt(pub, payload.plaintext)
    return {
        "key_id": DEMO_KEY_ID,
        "plaintext": payload.plaintext,
        "ciphertext": str(ciphertext),
    }


@app.get("/demo", response_class=HTMLResponse)
async def demo_page() -> HTMLResponse:
        """Lightweight HTML page to exercise the API endpoints from a browser."""
        html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <title>Secure Votes API Demo</title>
            <style>
                :root { --bg: #0f172a; --panel: #111827; --accent: #22c55e; --text: #e5e7eb; --muted: #94a3b8; }
                * { box-sizing: border-box; }
                body { margin: 0; padding: 32px; font-family: "Segoe UI", system-ui, -apple-system, sans-serif; background: radial-gradient(circle at 10% 20%, #111827 0, #0b1224 35%, #0f172a 100%); color: var(--text); }
                h1 { margin: 0 0 24px; font-size: 26px; }
                .grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
                .card { background: var(--panel); border: 1px solid #1f2937; border-radius: 12px; padding: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.25); }
                .card h2 { margin: 0 0 8px; font-size: 18px; }
                .card p { margin: 0 0 12px; color: var(--muted); font-size: 14px; }
                label { display: block; margin: 8px 0 4px; font-size: 13px; color: var(--muted); }
                input, textarea, select, button { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #1f2937; background: #0b1324; color: var(--text); font-size: 14px; }
                textarea { min-height: 70px; resize: vertical; }
                button { cursor: pointer; border: none; background: linear-gradient(120deg, #22c55e, #16a34a); color: #0b1324; font-weight: 700; box-shadow: 0 8px 20px rgba(34,197,94,0.25); }
                button:active { transform: translateY(1px); }
                pre { background: #0b1324; border: 1px solid #1f2937; border-radius: 8px; padding: 10px; color: #d1d5db; font-size: 13px; overflow-x: auto; }
                .row { display: flex; gap: 8px; }
                .row > * { flex: 1; }
            </style>
        </head>
        <body>
            <h1>Secure Votes API Demo</h1>
            <div class="grid">
                <div class="card">
                    <h2>Health</h2>
                    <p>Ping /health to verify API and DB availability.</p>
                    <button onclick="callEndpoint('GET', '/health')">Run</button>
                </div>
                <div class="card">
                    <h2>IAM</h2>
                    <p>Check DB role privileges.</p>
                    <button onclick="callEndpoint('GET', '/iam/verify')">Run</button>
                </div>
                <div class="card">
                    <h2>Audit verify</h2>
                    <p>Validate hash-chain consistency.</p>
                    <button onclick="callEndpoint('GET', '/audit/verify')">Run</button>
                </div>
                <div class="card">
                    <h2>Audit logs</h2>
                    <p>Fetch last entries (id, type, hashes).</p>
                    <label>limit</label>
                    <input id="audit_limit" value="20" type="number" min="1" max="200" />
                    <button onclick="loadAuditLogs()">Load</button>
                </div>
                <div class="card">
                    <h2>Send vote</h2>
                    <p>Submit an already-encrypted vote payload.</p>
                    <label>question_id</label>
                    <input id="question_id" value="q-demo" />
                    <label>participant_id</label>
                    <input id="participant_id" value="alice" />
                    <label>agent_id</label>
                    <input id="agent_id" value="agent-1" />
                    <label>ciphertext</label>
                    <input id="ciphertext" value="123456789" />
                    <label>key_id</label>
                    <input id="key_id" value="key-v1" />
                    <button onclick="sendVote()">Send</button>
                </div>
                <div class="card">
                    <h2>Aggregate</h2>
                    <p>Homomorphic sum for a question/key pair.</p>
                    <label>question_id</label>
                    <input id="agg_question" value="q-demo" />
                    <label>key_id</label>
                    <input id="agg_key" value="key-v1" />
                    <button onclick="aggregate()">Aggregate</button>
                </div>
                <div class="card">
                    <h2>Seed votes</h2>
                    <p>Insert three demo votes then aggregate.</p>
                    <button onclick="seedVotes()">Seed + aggregate</button>
                </div>
                <div class="card">
                    <h2>Upload photo</h2>
                    <p>Push encrypted blob metadata to MinIO.</p>
                    <label>object_name</label>
                    <input id="photo_object" value="demo-photo" />
                    <label>nonce_b64</label>
                    <input id="photo_nonce" value="bm9uY2U=" />
                    <label>tag_b64</label>
                    <input id="photo_tag" value="dGFn" />
                    <label>ciphertext_b64</label>
                    <textarea id="photo_cipher" spellcheck="false">Y2lwaGVydGV4dA==</textarea>
                    <label>content_type</label>
                    <input id="photo_ct" value="application/octet-stream" />
                    <label>key_id</label>
                    <input id="photo_key" value="key-v1" />
                    <label>alg</label>
                    <input id="photo_alg" value="AES-256-GCM" />
                    <button onclick="uploadPhoto()">Upload</button>
                </div>
                <div class="card">
                    <h2>Custom request</h2>
                    <p>Call any endpoint with method/path/body.</p>
                    <label>method</label>
                    <select id="custom_method">
                        <option>GET</option>
                        <option>POST</option>
                        <option>PUT</option>
                        <option>DELETE</option>
                    </select>
                    <label>path</label>
                    <input id="custom_path" value="/health" />
                    <label>body (JSON)</label>
                    <textarea id="custom_body" spellcheck="false">{}</textarea>
                    <button onclick="customCall()">Send</button>
                </div>
            </div>
            <div class="card" style="margin-top:16px;">
                <h2>Response</h2>
                <pre id="output">Ready.</pre>
            </div>

            <script>
                const base = window.location.origin;
                const output = document.getElementById('output');

                async function callEndpoint(method, path, body) {
                    try {
                        const res = await fetch(base + path, {
                            method,
                            headers: body ? { 'Content-Type': 'application/json' } : undefined,
                            body: body ? JSON.stringify(body) : undefined,
                        });
                        const text = await res.text();
                        let parsed;
                        try { parsed = JSON.parse(text); } catch (_) { parsed = text; }
                        output.textContent = JSON.stringify(parsed, null, 2);
                    } catch (err) {
                        output.textContent = 'Error: ' + err;
                    }
                }

                function sendVote() {
                    callEndpoint('POST', '/votes/send', {
                        question_id: document.getElementById('question_id').value,
                        participant_id: document.getElementById('participant_id').value,
                        agent_id: document.getElementById('agent_id').value,
                        ciphertext: document.getElementById('ciphertext').value,
                        key_id: document.getElementById('key_id').value,
                    });
                }

                function aggregate() {
                    const q = encodeURIComponent(document.getElementById('agg_question').value);
                    const k = encodeURIComponent(document.getElementById('agg_key').value);
                    callEndpoint('GET', `/votes/aggregate?question_id=${q}&key_id=${k}`);
                }

                function loadAuditLogs() {
                    const limit = document.getElementById('audit_limit').value || 20;
                    callEndpoint('GET', `/audit/logs?limit=${limit}`);
                }

                function uploadPhoto() {
                    callEndpoint('POST', '/uploads/photo', {
                        object_name: document.getElementById('photo_object').value,
                        nonce_b64: document.getElementById('photo_nonce').value,
                        tag_b64: document.getElementById('photo_tag').value,
                        ciphertext_b64: document.getElementById('photo_cipher').value,
                        content_type: document.getElementById('photo_ct').value,
                        key_id: document.getElementById('photo_key').value,
                        alg: document.getElementById('photo_alg').value,
                    });
                }

                async function seedVotes() {
                    const votes = [
                        { question_id: 'q-demo', participant_id: 'alice', agent_id: 'agent-1', ciphertext: '2', key_id: 'key-v1' },
                        { question_id: 'q-demo', participant_id: 'bob', agent_id: 'agent-1', ciphertext: '3', key_id: 'key-v1' },
                        { question_id: 'q-demo', participant_id: 'carol', agent_id: 'agent-2', ciphertext: '5', key_id: 'key-v1' },
                    ];
                    for (const v of votes) {
                        await callEndpoint('POST', '/votes/send', v);
                    }
                    aggregate();
                }

                function customCall() {
                    const method = document.getElementById('custom_method').value;
                    const path = document.getElementById('custom_path').value;
                    const bodyText = document.getElementById('custom_body').value.trim();
                    let payload = undefined;
                    if (bodyText && method !== 'GET') {
                        try { payload = JSON.parse(bodyText); } catch (e) { output.textContent = 'Invalid JSON body'; return; }
                    }
                    callEndpoint(method, path, payload);
                }
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html)
