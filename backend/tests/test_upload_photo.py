import base64
import uuid

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from httpx import AsyncClient
from sqlalchemy import select

from app.db import get_engine, init_db, photos_table, reset_db
from app.main import app
from app.storage import get_object_bytes


@pytest.mark.anyio
async def test_upload_photo_stores_object_and_metadata():
    engine = get_engine()
    await init_db(engine)
    await reset_db(engine)

    key = AESGCM.generate_key(bit_length=256)
    aesgcm = AESGCM(key)
    nonce = b"123456789012"  # 12 bytes
    plaintext = b"hello-photo"
    ct_with_tag = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    tag = ct_with_tag[-16:]
    ciphertext = ct_with_tag[:-16]

    object_name = f"photo-{uuid.uuid4()}"
    payload = {
        "object_name": object_name,
        "nonce_b64": base64.b64encode(nonce).decode(),
        "tag_b64": base64.b64encode(tag).decode(),
        "ciphertext_b64": base64.b64encode(ciphertext).decode(),
        "content_type": "image/jpeg",
        "key_id": "aes-demo",
    }

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post("/uploads/photo", json=payload)

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "stored"
    assert body["object_name"] == object_name

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                select(photos_table).where(photos_table.c.object_name == object_name)
            )
        ).mappings().first()

    assert row is not None
    assert row["nonce"] == payload["nonce_b64"]
    assert row["tag"] == payload["tag_b64"]
    assert row["content_type"] == payload["content_type"]
    assert row["size_bytes"] == len(ciphertext + tag)

    stored_bytes = get_object_bytes(object_name=object_name)
    assert stored_bytes == ciphertext + tag

    decrypted = aesgcm.decrypt(nonce, ciphertext + tag, associated_data=None)
    assert decrypted == plaintext
