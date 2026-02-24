/**
 * API client – communicates with the Secure Votes backend.
 */

const API = (() => {
    const BASE_URL = window.location.port === '3000'
        ? 'http://localhost:8080'
        : window.location.origin;

    /** Get auth headers with JWT token */
    function authHeaders() {
        const token = localStorage.getItem('sv_token');
        const headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = `Bearer ${token}`;
        return headers;
    }

    /**
     * Fetch the Paillier demo public key from the backend.
     * @returns {Promise<{key_id: string, n: string, g: string}>}
     */
    async function fetchPublicKey() {
        const resp = await fetch(`${BASE_URL}/crypto/pubkey`, { headers: authHeaders() });
        if (!resp.ok) throw new Error(`Failed to fetch public key: ${resp.status}`);
        return resp.json();
    }

    /**
     * Submit an encrypted vote to the backend.
     * @param {{question_id, participant_id, agent_id, ciphertext, key_id}} payload
     * @returns {Promise<object>}
     */
    async function sendVote(payload) {
        const resp = await fetch(`${BASE_URL}/votes/send`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify(payload),
        });
        if (!resp.ok) throw new Error(`Vote submission failed: ${resp.status}`);
        return resp.json();
    }

    /**
     * Upload encrypted photo metadata + blob.
     * @param {{object_name, nonce_b64, tag_b64, ciphertext_b64, content_type, key_id}} payload
     * @returns {Promise<object>}
     */
    async function uploadPhoto(payload) {
        const resp = await fetch(`${BASE_URL}/uploads/photo`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify(payload),
        });
        if (!resp.ok) throw new Error(`Photo upload failed: ${resp.status}`);
        return resp.json();
    }

    /**
     * Check backend health.
     * @returns {Promise<boolean>}
     */
    async function healthCheck() {
        try {
            const resp = await fetch(`${BASE_URL}/health`, { signal: AbortSignal.timeout(3000) });
            return resp.ok;
        } catch {
            return false;
        }
    }

    /**
     * Fetch active questions from the backend.
     * @returns {Promise<Array>}
     */
    async function fetchQuestions() {
        const resp = await fetch(`${BASE_URL}/questions`, { headers: authHeaders() });
        if (!resp.ok) throw new Error(`Failed to fetch questions: ${resp.status}`);
        return resp.json();
    }

    return { fetchPublicKey, fetchQuestions, sendVote, uploadPhoto, healthCheck, authHeaders, BASE_URL };
})();
