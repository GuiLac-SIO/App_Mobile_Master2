import hashlib
import os

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Boolean,
    Table,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool


def get_database_url() -> str:
    """
    Retrieve the database URL from environment.
    Defaults to the docker-compose network host.
    """
    return os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://app_user:app_pass@db:5432/votes_db",
    )


def get_engine() -> AsyncEngine:
    """Return a new async engine using NullPool to avoid pool/loop issues."""
    return create_async_engine(
        get_database_url(), pool_pre_ping=True, future=True, poolclass=NullPool
    )


async def check_db_connection(engine: AsyncEngine) -> bool:
    """
    Perform a lightweight health probe against the database.
    Raises on failure; returns True on success.
    """
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True



IDENTITY_SCHEMA = "identity"
VOTES_SCHEMA = "votes"
AUDIT_SCHEMA = "audit"
PHOTOS_SCHEMA = "photos"
USERS_SCHEMA = "identity"  # users live in identity silo

metadata = MetaData()

users_table = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String(64), nullable=False, unique=True),
    Column("password_hash", String(128), nullable=False),
    Column("password_salt", String(64), nullable=False),
    Column("role", String(20), nullable=False, server_default="agent"),
    Column("full_name", String(128), nullable=False, server_default=""),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    schema=USERS_SCHEMA,
)

questions_table = Table(
    "questions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("question_id", String(64), nullable=False, unique=True),
    Column("label", String(512), nullable=False),
    Column("created_by", String(64), nullable=False),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    schema=VOTES_SCHEMA,
)

identities_table = Table(
    "participants",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("participant_hash", String(128), nullable=False, unique=True),
    Column("agent_hash", String(128), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    schema=IDENTITY_SCHEMA,
)

votes_table = Table(
    "votes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("question_id", String(64), nullable=False),
    Column("participant_hash", String(128), nullable=False),
    Column("ciphertext", String, nullable=False),
    Column("key_id", String(64), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    schema=VOTES_SCHEMA,
)

audit_logs_table = Table(
    "logs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("event_type", String(64), nullable=False),
    Column("payload_hash", String(128), nullable=False),
    Column("prev_hash", String(128), nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    schema=AUDIT_SCHEMA,
)

photos_table = Table(
    "photos",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("object_name", String(256), nullable=False, unique=True),
    Column("nonce", String(64), nullable=False),
    Column("tag", String(64), nullable=False),
    Column("alg", String(32), nullable=False),
    Column("content_type", String(128), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("key_id", String(64), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    schema=PHOTOS_SCHEMA,
)


async def init_db(engine: AsyncEngine) -> None:
    """Create schemas and tables if they do not exist (idempotent)."""
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {IDENTITY_SCHEMA}"))
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {VOTES_SCHEMA}"))
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {AUDIT_SCHEMA}"))
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {PHOTOS_SCHEMA}"))
        await conn.run_sync(metadata.create_all)

        result = await conn.execute(select(users_table.c.id).limit(1))
        if result.first() is None:
            from app.auth import hash_password
            pw_hash, salt = hash_password("admin")
            await conn.execute(
                users_table.insert().values(
                    username="admin",
                    password_hash=pw_hash,
                    password_salt=salt,
                    role="admin",
                    full_name="Administrateur",
                )
            )
            pw_hash2, salt2 = hash_password("agent")
            await conn.execute(
                users_table.insert().values(
                    username="agent",
                    password_hash=pw_hash2,
                    password_salt=salt2,
                    role="agent",
                    full_name="Agent Terrain",
                )
            )


async def reset_db(engine: AsyncEngine) -> None:
    """Truncate all domain tables between tests to keep state isolated."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                f"TRUNCATE TABLE {AUDIT_SCHEMA}.logs, {VOTES_SCHEMA}.questions, {VOTES_SCHEMA}.votes, {IDENTITY_SCHEMA}.participants, {PHOTOS_SCHEMA}.photos RESTART IDENTITY CASCADE"
            )
        )
        await conn.commit()


def hash_identifier(value: str) -> str:
    """Deterministic hash (SHA-256 hex) for identities and audit payloads."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def record_vote(
    engine: AsyncEngine,
    *,
    question_id: str,
    participant_id: str,
    agent_id: str,
    ciphertext: str,
    key_id: str,
) -> dict:
    """
    Store a vote in the dedicated silo and append an audit entry (hash-chain style).
    - participant_id and agent_id are hashed before storage
    - ciphertext is stored as-is (already encrypted client-side)
    - audit log is chained via prev_hash
    Returns inserted vote metadata.
    """

    participant_hash = hash_identifier(participant_id)
    agent_hash = hash_identifier(agent_id)
    payload_hash = hash_identifier(f"{question_id}:{ciphertext}:{key_id}")

    async with engine.begin() as conn:
        q_check = await conn.execute(
            select(questions_table.c.id)
            .where(questions_table.c.question_id == question_id)
            .where(questions_table.c.is_active == True)
        )
        if q_check.first() is None:
            raise ValueError("Question invalide ou inactive")

        stmt_identity = (
            insert(identities_table)
            .values(participant_hash=participant_hash, agent_hash=agent_hash)
            .on_conflict_do_nothing(index_elements=[identities_table.c.participant_hash])
        )
        await conn.execute(stmt_identity)

        vote_result = await conn.execute(
            votes_table.insert()
            .values(
                question_id=question_id,
                participant_hash=participant_hash,
                ciphertext=ciphertext,
                key_id=key_id,
            )
            .returning(
                votes_table.c.id,
                votes_table.c.created_at,
                votes_table.c.participant_hash,
                votes_table.c.question_id,
            )
        )
        vote_row = vote_result.mappings().first()

        prev_hash_row = (
            await conn.execute(
                select(audit_logs_table.c.payload_hash)
                .order_by(audit_logs_table.c.id.desc())
                .limit(1)
            )
        ).first()
        prev_hash = prev_hash_row[0] if prev_hash_row else None

        await conn.execute(
            audit_logs_table.insert().values(
                event_type="vote_received",
                payload_hash=payload_hash,
                prev_hash=prev_hash,
            )
        )

    return {
        "vote_id": vote_row["id"],
        "question_id": vote_row["question_id"],
        "participant_hash": vote_row["participant_hash"],
        "created_at": vote_row["created_at"],
        "key_id": key_id,
    }


async def fetch_votes_by_question(
    engine: AsyncEngine, *, question_id: str, key_id: str
) -> list[dict]:
    """Retrieve votes for a given question/key pair."""
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                select(votes_table.c.ciphertext).where(
                    votes_table.c.question_id == question_id,
                    votes_table.c.key_id == key_id,
                )
            )
        ).mappings().all()
    return rows


async def verify_db_permissions(engine: AsyncEngine) -> dict:
    """Check that the current DB role is non-privileged and has minimal rights."""
    async with engine.connect() as conn:
        perms = (
            await conn.execute(
                text(
                    """
                    SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication
                    FROM pg_roles WHERE rolname = current_user
                    """
                )
            )
        ).mappings().first()

        privileges = (
            await conn.execute(
                text(
                    """
                    SELECT
                        has_table_privilege(current_user, 'votes.votes', 'INSERT') AS can_insert_votes,
                        has_table_privilege(current_user, 'votes.votes', 'SELECT') AS can_select_votes,
                        has_table_privilege(current_user, 'identity.participants', 'SELECT') AS can_select_identities
                    """
                )
            )
        ).mappings().first()

    return {
        "rolsuper": bool(perms["rolsuper"]),
        "rolcreatedb": bool(perms["rolcreatedb"]),
        "rolcreaterole": bool(perms["rolcreaterole"]),
        "rolreplication": bool(perms["rolreplication"]),
        "can_insert_votes": bool(privileges["can_insert_votes"]),
        "can_select_votes": bool(privileges["can_select_votes"]),
        "can_select_identities": bool(privileges["can_select_identities"]),
    }


async def verify_hash_chain(engine: AsyncEngine) -> dict:
    """Verify audit chain linkage (prev_hash matches previous payload_hash).

    Returns {"ok": bool, "length": int, "broken_id": Optional[int]}.
    """
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                select(
                    audit_logs_table.c.id,
                    audit_logs_table.c.payload_hash,
                    audit_logs_table.c.prev_hash,
                ).order_by(audit_logs_table.c.id.asc())
            )
        ).mappings().all()

    prev_payload = None
    for row in rows:
        if prev_payload is None:
            prev_payload = row["payload_hash"]
            continue
        if row["prev_hash"] != prev_payload:
            return {"ok": False, "length": len(rows), "broken_id": row["id"]}
        prev_payload = row["payload_hash"]

    return {"ok": True, "length": len(rows), "broken_id": None}


async def fetch_audit_logs(engine: AsyncEngine, *, limit: int = 50) -> list[dict]:
    """Return latest audit entries (id, event_type, payload_hash, prev_hash, created_at)."""
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                select(
                    audit_logs_table.c.id,
                    audit_logs_table.c.event_type,
                    audit_logs_table.c.payload_hash,
                    audit_logs_table.c.prev_hash,
                    audit_logs_table.c.created_at,
                ).order_by(audit_logs_table.c.id.desc()).limit(limit)
            )
        ).mappings().all()
    return rows


async def record_photo_metadata(
    engine: AsyncEngine,
    *,
    object_name: str,
    nonce_b64: str,
    tag_b64: str,
    alg: str,
    content_type: str,
    size_bytes: int,
    key_id: str,
) -> dict:
    """Persist photo metadata in the dedicated silo and append an audit entry."""
    payload_hash = hash_identifier(f"photo:{object_name}:{size_bytes}:{key_id}")

    async with engine.begin() as conn:
        photo_res = await conn.execute(
            photos_table.insert()
            .values(
                object_name=object_name,
                nonce=nonce_b64,
                tag=tag_b64,
                alg=alg,
                content_type=content_type,
                size_bytes=size_bytes,
                key_id=key_id,
            )
            .returning(photos_table.c.id, photos_table.c.created_at)
        )
        photo_row = photo_res.mappings().first()

        prev_hash_row = (
            await conn.execute(
                select(audit_logs_table.c.payload_hash)
                .order_by(audit_logs_table.c.id.desc())
                .limit(1)
            )
        ).first()
        prev_hash = prev_hash_row[0] if prev_hash_row else None

        await conn.execute(
            audit_logs_table.insert().values(
                event_type="photo_uploaded",
                payload_hash=payload_hash,
                prev_hash=prev_hash,
            )
        )

    return {
        "photo_id": photo_row["id"],
        "object_name": object_name,
        "created_at": photo_row["created_at"],
    }



async def get_user_by_username(engine: AsyncEngine, username: str) -> dict | None:
    """Fetch a user by username. Returns dict or None."""
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                select(users_table).where(users_table.c.username == username)
            )
        ).mappings().first()
    return dict(row) if row else None


async def create_user(engine: AsyncEngine, *, username: str, password_hash: str, password_salt: str, role: str, full_name: str) -> dict:
    """Insert a new user. Returns the created user dict."""
    async with engine.begin() as conn:
        result = await conn.execute(
            users_table.insert().values(
                username=username,
                password_hash=password_hash,
                password_salt=password_salt,
                role=role,
                full_name=full_name,
            ).returning(users_table.c.id, users_table.c.username, users_table.c.role, users_table.c.created_at)
        )
        row = result.mappings().first()
    return dict(row)


async def list_users(engine: AsyncEngine) -> list[dict]:
    """List all users (id, username, role, full_name, is_active, created_at)."""
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                select(
                    users_table.c.id,
                    users_table.c.username,
                    users_table.c.role,
                    users_table.c.full_name,
                    users_table.c.is_active,
                    users_table.c.created_at,
                ).order_by(users_table.c.id)
            )
        ).mappings().all()
    return [dict(r) for r in rows]


async def update_user(engine: AsyncEngine, user_id: int, **kwargs) -> dict | None:
    """Update user fields (role, full_name, is_active, password_hash, password_salt)."""
    allowed = {"role", "full_name", "is_active", "password_hash", "password_salt"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return None
    async with engine.begin() as conn:
        await conn.execute(
            users_table.update().where(users_table.c.id == user_id).values(**updates)
        )
        row = (
            await conn.execute(
                select(
                    users_table.c.id,
                    users_table.c.username,
                    users_table.c.role,
                    users_table.c.full_name,
                    users_table.c.is_active,
                ).where(users_table.c.id == user_id)
            )
        ).mappings().first()
    return dict(row) if row else None


async def delete_user(engine: AsyncEngine, user_id: int) -> bool:
    """Delete a user by ID. Returns True if deleted."""
    async with engine.begin() as conn:
        result = await conn.execute(
            users_table.delete().where(users_table.c.id == user_id)
        )
        return result.rowcount > 0



async def create_question(engine: AsyncEngine, *, question_id: str, label: str, created_by: str) -> dict:
    """Insert a new question. Returns the created question dict."""
    async with engine.begin() as conn:
        result = await conn.execute(
            questions_table.insert().values(
                question_id=question_id,
                label=label,
                created_by=created_by,
            ).returning(questions_table.c.id, questions_table.c.question_id, questions_table.c.label, questions_table.c.created_at)
        )
        row = result.mappings().first()
    return dict(row)


async def list_questions(engine: AsyncEngine) -> list[dict]:
    """List all active questions."""
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                select(questions_table).where(questions_table.c.is_active == True).order_by(questions_table.c.id)
            )
        ).mappings().all()
    return [dict(r) for r in rows]


async def get_vote_stats(engine: AsyncEngine) -> dict:
    """Get vote statistics: total votes, unique questions, unique participants."""
    async with engine.connect() as conn:
        total = (await conn.execute(text("SELECT COUNT(*) FROM votes.votes"))).scalar() or 0
        questions = (await conn.execute(text("SELECT COUNT(DISTINCT question_id) FROM votes.votes"))).scalar() or 0
        participants = (await conn.execute(text("SELECT COUNT(DISTINCT participant_hash) FROM votes.votes"))).scalar() or 0
        photos = (await conn.execute(text("SELECT COUNT(*) FROM photos.photos"))).scalar() or 0
        audit_count = (await conn.execute(text("SELECT COUNT(*) FROM audit.logs"))).scalar() or 0
    return {
        "total_votes": total,
        "unique_questions": questions,
        "unique_participants": participants,
        "total_photos": photos,
        "total_audit_entries": audit_count,
    }
