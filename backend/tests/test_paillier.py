import pytest

from app.crypto.paillier import add, add_plain, decrypt, encrypt, generate_keypair


@pytest.mark.anyio
async def test_encrypt_decrypt_roundtrip():
    pub, priv = generate_keypair(bits=256)
    for msg in [0, 1, 5, 42]:
        c = encrypt(pub, msg)
        m_out = decrypt(priv, c)
        assert m_out == msg


@pytest.mark.anyio
async def test_homomorphic_addition():
    pub, priv = generate_keypair(bits=256)
    m1, m2 = 1, 1
    c1 = encrypt(pub, m1)
    c2 = encrypt(pub, m2)
    agg = add(pub, c1, c2)
    assert decrypt(priv, agg) == m1 + m2


@pytest.mark.anyio
async def test_add_plaintext_optimization():
    pub, priv = generate_keypair(bits=256)
    base = encrypt(pub, 3)
    agg = add_plain(pub, base, 4)
    assert decrypt(priv, agg) == 7
