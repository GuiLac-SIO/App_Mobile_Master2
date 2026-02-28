import math
import secrets
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class PublicKey:
    n: int
    g: int

    @property
    def n_sq(self) -> int:
        return self.n * self.n


@dataclass(frozen=True)
class PrivateKey:
    lam: int
    mu: int
    n: int

    @property
    def n_sq(self) -> int:
        return self.n * self.n



def _lcm(a: int, b: int) -> int:
    return abs(a * b) // math.gcd(a, b)


def _is_probable_prime(n: int, rounds: int = 16) -> bool:
    if n < 2:
        return False
    small_primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
    if n in small_primes:
        return True
    if any((n % p) == 0 for p in small_primes):
        return False

    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1

    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _generate_prime(bits: int) -> int:
    while True:
        candidate = secrets.randbits(bits) | 1 | (1 << (bits - 1))
        if _is_probable_prime(candidate):
            return candidate



def generate_keypair(bits: int = 256) -> Tuple[PublicKey, PrivateKey]:
    p = _generate_prime(bits // 2)
    q = _generate_prime(bits // 2)
    n = p * q
    lam = _lcm(p - 1, q - 1)
    g = n + 1
    n_sq = n * n
    x = pow(g, lam, n_sq)
    l_val = (x - 1) // n
    mu = pow(l_val, -1, n)
    return PublicKey(n=n, g=g), PrivateKey(lam=lam, mu=mu, n=n)



def encrypt(pub: PublicKey, m: int, r: int | None = None) -> int:
    if not 0 <= m < pub.n:
        raise ValueError("message out of range")
    if r is None:
        while True:
            r_candidate = secrets.randbelow(pub.n)
            if 1 <= r_candidate < pub.n and math.gcd(r_candidate, pub.n) == 1:
                r = r_candidate
                break
    c1 = pow(pub.g, m, pub.n_sq)
    c2 = pow(r, pub.n, pub.n_sq)
    return (c1 * c2) % pub.n_sq


def decrypt(priv: PrivateKey, c: int) -> int:
    x = pow(c, priv.lam, priv.n_sq)
    l_val = (x - 1) // priv.n
    return (l_val * priv.mu) % priv.n


def add(pub: PublicKey, c1: int, c2: int) -> int:
    return (c1 * c2) % pub.n_sq


def add_plain(pub: PublicKey, c: int, m: int) -> int:
    return (c * pow(pub.g, m, pub.n_sq)) % pub.n_sq
