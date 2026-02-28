/**
 * AES-256-GCM photo encryption using the Web Crypto API.
 * Photos are encrypted client-side before transmission.
 */

const PhotoCrypto = (() => {
    /**
     * @param {Blob} blob - The photo data
     * @returns {Promise<{ciphertext: Uint8Array, nonce: Uint8Array, tag: Uint8Array, key: CryptoKey, keyB64: string}>}
     */
    async function encryptPhoto(blob) {
        const plaintext = new Uint8Array(await blob.arrayBuffer());

        const key = await crypto.subtle.generateKey(
            { name: 'AES-GCM', length: 256 },
            true,
            ['encrypt', 'decrypt']
        );

        const nonce = crypto.getRandomValues(new Uint8Array(12));

        const encryptedBuffer = await crypto.subtle.encrypt(
            { name: 'AES-GCM', iv: nonce, tagLength: 128 },
            key,
            plaintext
        );

        const encrypted = new Uint8Array(encryptedBuffer);
        const ciphertext = encrypted.slice(0, encrypted.length - 16);
        const tag = encrypted.slice(encrypted.length - 16);

        const rawKey = await crypto.subtle.exportKey('raw', key);
        const keyB64 = btoa(String.fromCharCode(...new Uint8Array(rawKey)));

        return { ciphertext, nonce, tag, key, keyB64 };
    }

    function toBase64(arr) {
        return btoa(String.fromCharCode(...arr));
    }

    return { encryptPhoto, toBase64 };
})();
