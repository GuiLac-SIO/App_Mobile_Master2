/**
 * Paillier homomorphic encryption – client-side (BigInt).
 * Pedagogical implementation matching the backend Python version.
 */

const Paillier = (() => {
    /** Modular exponentiation: base^exp mod mod */
    function modPow(base, exp, mod) {
        base = BigInt(base); exp = BigInt(exp); mod = BigInt(mod);
        let result = 1n;
        base = base % mod;
        while (exp > 0n) {
            if (exp % 2n === 1n) result = (result * base) % mod;
            exp = exp >> 1n;
            base = (base * base) % mod;
        }
        return result;
    }

    /** Generate a cryptographically random BigInt in [1, max-1] coprime with max */
    function randomCoprime(max) {
        max = BigInt(max);
        const bytes = new Uint8Array(Math.ceil(Number(max).toString(2).length / 8) + 4);
        while (true) {
            crypto.getRandomValues(bytes);
            let r = 0n;
            for (const b of bytes) r = (r << 8n) | BigInt(b);
            r = (r % (max - 2n)) + 2n;
            if (gcd(r, max) === 1n) return r;
        }
    }

    function gcd(a, b) {
        a = a < 0n ? -a : a;
        b = b < 0n ? -b : b;
        while (b > 0n) { [a, b] = [b, a % b]; }
        return a;
    }

    /**
     * Encrypt a plaintext integer m ∈ {0, 1} using the public key (n, g).
     * @param {string|BigInt} n - Public key n
     * @param {string|BigInt} g - Public key g (usually n+1)
     * @param {number} m - Plaintext (0 or 1)
     * @returns {string} Ciphertext as decimal string
     */
    function encrypt(n, g, m) {
        n = BigInt(n);
        g = BigInt(g);
        const nSq = n * n;
        const r = randomCoprime(n);
        const c1 = modPow(g, BigInt(m), nSq);
        const c2 = modPow(r, n, nSq);
        return ((c1 * c2) % nSq).toString();
    }

    /**
     * Homomorphic addition of two ciphertexts.
     */
    function add(n, c1, c2) {
        n = BigInt(n);
        const nSq = n * n;
        return ((BigInt(c1) * BigInt(c2)) % nSq).toString();
    }

    return { encrypt, add, modPow, gcd };
})();
