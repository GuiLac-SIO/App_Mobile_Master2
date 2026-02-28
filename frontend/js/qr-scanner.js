/**
 * QR code scanner wrapper using html5-qrcode library.
 */

const QRScanner = (() => {
    const scanners = {};

    /**
     * Start scanning QR codes with the device camera.
     * @param {string} elementId - ID of the container element
     * @param {function} onSuccess - Callback with decoded text
     * @returns {Promise<void>}
     */
    async function start(elementId, onSuccess) {
        await stop(elementId);

        const scanner = new Html5Qrcode(elementId);
        scanners[elementId] = scanner;

        try {
            await scanner.start(
                { facingMode: 'environment' },
                {
                    fps: 10,
                    qrbox: { width: 220, height: 220 },
                    aspectRatio: 1.0,
                },
                (decodedText) => {
                    onSuccess(decodedText);
                },
                () => { } // ignore errors (no QR in frame)
            );
        } catch (err) {
            console.warn(`QR scanner couldn't start on ${elementId}:`, err);
        }
    }

    /**
     * Stop the scanner on a given element.
     * @param {string} elementId
     */
    async function stop(elementId) {
        const scanner = scanners[elementId];
        if (scanner) {
            try {
                const state = scanner.getState();
                if (state === Html5QrcodeScannerState.SCANNING) {
                    await scanner.stop();
                }
            } catch {
            }
            try { scanner.clear(); } catch { }
            delete scanners[elementId];
        }
    }

    /** Stop all active scanners */
    async function stopAll() {
        for (const id of Object.keys(scanners)) {
            await stop(id);
        }
    }

    return { start, stop, stopAll };
})();
