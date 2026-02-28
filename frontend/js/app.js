/**
 * Main application logic – Agent Terrain workflow.
 * Orchestrates the 5-step vote collection process.
 */

(function () {
    'use strict';

    const state = {
        questionId: null,
        participantId: null,
        vote: null,            // 0 or 1
        photoBlob: null,
        photoEncrypted: null,  // { ciphertext, nonce, tag, keyB64 }
        voteCiphertext: null,
        paillierKey: null,     // { key_id, n, g }
        agentId: localStorage.getItem('sv_username') || 'agent-' + Math.random().toString(36).slice(2, 8),
        timestamp: null,
        geo: null,
    };

    const OFFLINE_QUEUE_KEY = 'secureVotes_offlineQueue';
    let currentStep = 1;

    const $ = (sel) => document.querySelector(sel);
    const steps = [null, $('#step1'), $('#step2'), $('#step3'), $('#step4'), $('#step5')];
    const stepDone = $('#stepDone');

    init();

    async function init() {
        setupEventListeners();
        monitorOnlineStatus();
        await loadPaillierKey();
        getGeolocation();
        showStep(1);
    }

    async function loadPaillierKey() {
        try {
            state.paillierKey = await API.fetchPublicKey();
            console.log('🔑 Paillier public key loaded:', state.paillierKey.key_id);
        } catch (err) {
            console.warn('⚠️ Could not load Paillier key from server, will use server-side encryption fallback');
        }
    }

    function getGeolocation() {
        if ('geolocation' in navigator) {
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    state.geo = `${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)}`;
                },
                () => { state.geo = 'Non disponible'; }
            );
        } else {
            state.geo = 'Non supporté';
        }
    }

    function showStep(n) {
        currentStep = n;
        steps.forEach((el, i) => {
            if (el) el.classList.toggle('visible', i === n);
        });
        stepDone.classList.remove('visible');

        document.querySelectorAll('.steps-nav .step').forEach((el) => {
            const s = parseInt(el.dataset.step);
            el.classList.remove('active', 'done');
            if (s === n) el.classList.add('active');
            else if (s < n) el.classList.add('done');
        });

        if (n === 1) startQuestionScanner();
        else QRScanner.stop('qr-reader-question');

        if (n === 2) startParticipantScanner();
        else QRScanner.stop('qr-reader-participant');

        if (n === 4) startCamera();
        else stopCamera();

        if (n === 5) populateSummary();
    }

    function setupEventListeners() {
        $('#manualQuestionId').addEventListener('input', (e) => {
            const val = e.target.value.trim();
            if (val) setQuestion(val);
        });
        $('#btnStep1Next').addEventListener('click', () => showStep(2));

        $('#manualParticipantId').addEventListener('input', (e) => {
            const val = e.target.value.trim();
            if (val) setParticipant(val);
        });
        $('#btnStep2Back').addEventListener('click', () => showStep(1));
        $('#btnStep2Next').addEventListener('click', () => showStep(3));

        $('#voteYes').addEventListener('click', () => setVote(1));
        $('#voteNo').addEventListener('click', () => setVote(0));
        $('#btnStep3Back').addEventListener('click', () => showStep(2));
        $('#btnStep3Next').addEventListener('click', () => showStep(4));

        $('#btnCapture').addEventListener('click', capturePhoto);
        $('#btnRetake').addEventListener('click', retakePhoto);
        $('#btnStep4Back').addEventListener('click', () => showStep(3));
        $('#btnStep4Next').addEventListener('click', () => showStep(5));

        $('#btnStep5Back').addEventListener('click', () => showStep(4));
        $('#btnSubmit').addEventListener('click', submitData);

        $('#btnNewCollect').addEventListener('click', resetWorkflow);
    }

    function startQuestionScanner() {
        QRScanner.start('qr-reader-question', (text) => {
            setQuestion(text);
            QRScanner.stop('qr-reader-question');
        });
    }

    async function setQuestion(id) {
        $('#btnStep1Next').disabled = true;
        $('#questionResult').style.display = 'flex';
        $('#questionIdDisplay').textContent = 'Vérification...';
        $('#questionIdDisplay').style.color = 'var(--muted)';

        try {
            const questions = await API.fetchQuestions();
            const q = questions.find(q => q.question_id === id);

            if (q) {
                state.questionId = id;
                $('#questionIdDisplay').textContent = id + ' - ' + q.label;
                $('#questionIdDisplay').style.color = 'var(--accent)';
                $('#manualQuestionId').value = id;
                $('#btnStep1Next').disabled = false;
            } else {
                state.questionId = null;
                $('#questionIdDisplay').textContent = 'ID invalide ou inactif';
                $('#questionIdDisplay').style.color = '#ef4444';
            }
        } catch (err) {
            state.questionId = null;
            $('#questionIdDisplay').textContent = 'Erreur réseau';
            $('#questionIdDisplay').style.color = '#ef4444';
        }
    }

    function startParticipantScanner() {
        QRScanner.start('qr-reader-participant', (text) => {
            setParticipant(text);
            QRScanner.stop('qr-reader-participant');
        });
    }

    function setParticipant(id) {
        state.participantId = id;
        $('#participantIdDisplay').textContent = id;
        $('#participantResult').style.display = 'flex';
        $('#manualParticipantId').value = id;
        $('#btnStep2Next').disabled = false;
    }

    function setVote(value) {
        state.vote = value;
        $('#voteYes').classList.toggle('selected', value === 1);
        $('#voteNo').classList.toggle('selected', value === 0);
        $('#voteValueDisplay').textContent = value === 1 ? '👍 Oui (1)' : '👎 Non (0)';
        $('#voteResult').style.display = 'flex';
        $('#btnStep3Next').disabled = false;
    }

    let cameraStream = null;

    async function startCamera() {
        const video = $('#cameraPreview');
        const preview = $('#photoPreview');
        video.style.display = 'block';
        preview.style.display = 'none';
        $('#btnCapture').style.display = 'block';
        $('#btnRetake').style.display = 'none';

        try {
            cameraStream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'environment', width: { ideal: 640 }, height: { ideal: 480 } }
            });
            video.srcObject = cameraStream;
        } catch (err) {
            console.warn('Camera not available:', err);
        }
    }

    function stopCamera() {
        if (cameraStream) {
            cameraStream.getTracks().forEach(t => t.stop());
            cameraStream = null;
        }
    }

    function capturePhoto() {
        const video = $('#cameraPreview');
        const canvas = $('#cameraCanvas');
        const preview = $('#photoPreview');

        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        canvas.getContext('2d').drawImage(video, 0, 0);

        canvas.toBlob((blob) => {
            state.photoBlob = blob;
            preview.src = URL.createObjectURL(blob);
            preview.style.display = 'block';
            video.style.display = 'none';
            $('#btnCapture').style.display = 'none';
            $('#btnRetake').style.display = 'block';
            $('#btnStep4Next').disabled = false;
            stopCamera();
        }, 'image/jpeg', 0.8);
    }

    function retakePhoto() {
        state.photoBlob = null;
        state.photoEncrypted = null;
        $('#btnStep4Next').disabled = true;
        startCamera();
    }

    async function populateSummary() {
        state.timestamp = new Date().toISOString();

        $('#sumQuestion').textContent = state.questionId;
        $('#sumParticipant').textContent = state.participantId;
        $('#sumVote').textContent = state.vote === 1 ? '👍 Oui' : '👎 Non';
        $('#sumPhoto').textContent = state.photoBlob ? `${(state.photoBlob.size / 1024).toFixed(1)} KB` : 'Aucune';
        $('#sumTimestamp').textContent = state.timestamp;
        $('#sumGeo').textContent = state.geo || 'Non disponible';
        $('#sumAgent').textContent = state.agentId;

        try {
            if (state.paillierKey) {
                state.voteCiphertext = Paillier.encrypt(
                    state.paillierKey.n,
                    state.paillierKey.g,
                    state.vote
                );
                $('#sumCiphertext').textContent = state.voteCiphertext.slice(0, 40) + '…';
            } else {
                $('#sumCiphertext').textContent = '(chiffrement côté serveur)';
            }
        } catch (err) {
            console.error('Paillier encryption error:', err);
            $('#sumCiphertext').textContent = '(erreur)';
        }

        if (state.photoBlob) {
            try {
                state.photoEncrypted = await PhotoCrypto.encryptPhoto(state.photoBlob);
                $('#sumPhotoEnc').textContent = `AES-256-GCM, ${state.photoEncrypted.ciphertext.length} octets`;
            } catch (err) {
                console.error('Photo encryption error:', err);
                $('#sumPhotoEnc').textContent = '(erreur)';
            }
        } else {
            $('#sumPhotoEnc').textContent = 'Aucune photo';
        }

        $('#cryptoInfo').style.display = 'block';
    }

    async function submitData() {
        const $btn = $('#btnSubmit');
        const $result = $('#submitResult');
        $btn.disabled = true;
        $btn.textContent = '⏳ Chiffrement et envoi…';
        $result.style.display = 'none';

        try {
            const ciphertext = state.voteCiphertext || state.vote.toString();
            const voteResp = await API.sendVote({
                question_id: state.questionId,
                participant_id: state.participantId,
                agent_id: state.agentId,
                ciphertext: ciphertext,
                key_id: state.paillierKey ? state.paillierKey.key_id : 'key-v1',
            });

            let photoResp = null;
            if (state.photoEncrypted) {
                const enc = state.photoEncrypted;
                photoResp = await API.uploadPhoto({
                    object_name: `${state.questionId}_${state.participantId}_${Date.now()}`,
                    nonce_b64: PhotoCrypto.toBase64(enc.nonce),
                    tag_b64: PhotoCrypto.toBase64(enc.tag),
                    ciphertext_b64: PhotoCrypto.toBase64(enc.ciphertext),
                    content_type: 'image/jpeg',
                    key_id: 'aes-demo',
                });
            }

            $result.style.display = 'flex';
            $result.innerHTML = `<span style="color:#22c55e">✅ Vote #${voteResp.vote_id} enregistré${photoResp ? ' + photo transmise' : ''}</span>`;

            setTimeout(() => {
                steps[5].classList.remove('visible');
                stepDone.classList.add('visible');
            }, 1500);

        } catch (err) {
            console.error('Submit error:', err);

            if (!navigator.onLine) {
                saveToOfflineQueue();
                $result.style.display = 'flex';
                $result.innerHTML = '<span style="color:#f59e0b">📴 Hors ligne — données sauvegardées localement</span>';
            } else {
                $result.style.display = 'flex';
                $result.innerHTML = `<span style="color:#ef4444">❌ Erreur : ${err.message}</span>`;
            }
        }

        $btn.disabled = false;
        $btn.textContent = '🚀 Transmettre au serveur';
    }

    function saveToOfflineQueue() {
        const queue = JSON.parse(localStorage.getItem(OFFLINE_QUEUE_KEY) || '[]');
        queue.push({
            questionId: state.questionId,
            participantId: state.participantId,
            vote: state.vote,
            ciphertext: state.voteCiphertext,
            agentId: state.agentId,
            timestamp: state.timestamp,
            geo: state.geo,
        });
        localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(queue));
        updatePendingBadge();
    }

    async function syncOfflineQueue() {
        const queue = JSON.parse(localStorage.getItem(OFFLINE_QUEUE_KEY) || '[]');
        if (queue.length === 0) return;

        const remaining = [];
        for (const item of queue) {
            try {
                await API.sendVote({
                    question_id: item.questionId,
                    participant_id: item.participantId,
                    agent_id: item.agentId,
                    ciphertext: item.ciphertext || item.vote.toString(),
                    key_id: state.paillierKey ? state.paillierKey.key_id : 'key-v1',
                });
            } catch {
                remaining.push(item);
            }
        }
        localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(remaining));
        updatePendingBadge();
    }

    function updatePendingBadge() {
        const queue = JSON.parse(localStorage.getItem(OFFLINE_QUEUE_KEY) || '[]');
        const badge = $('#pendingCount');
        if (queue.length > 0) {
            badge.textContent = queue.length;
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    }

    function monitorOnlineStatus() {
        const badge = $('#onlineStatus');

        function update() {
            if (navigator.onLine) {
                badge.textContent = 'En ligne';
                badge.className = 'status-badge online';
                syncOfflineQueue();
            } else {
                badge.textContent = 'Hors ligne';
                badge.className = 'status-badge offline';
            }
        }

        window.addEventListener('online', update);
        window.addEventListener('offline', update);
        update();
        updatePendingBadge();
    }

    function resetWorkflow() {
        state.questionId = null;
        state.participantId = null;
        state.vote = null;
        state.photoBlob = null;
        state.photoEncrypted = null;
        state.voteCiphertext = null;
        state.timestamp = null;

        $('#questionResult').style.display = 'none';
        $('#participantResult').style.display = 'none';
        $('#voteResult').style.display = 'none';
        $('#cryptoInfo').style.display = 'none';
        $('#submitResult').style.display = 'none';
        $('#manualQuestionId').value = '';
        $('#manualParticipantId').value = '';
        $('#voteYes').classList.remove('selected');
        $('#voteNo').classList.remove('selected');
        $('#btnStep1Next').disabled = true;
        $('#btnStep2Next').disabled = true;
        $('#btnStep3Next').disabled = true;
        $('#btnStep4Next').disabled = true;

        stepDone.classList.remove('visible');
        showStep(1);
    }

})();
