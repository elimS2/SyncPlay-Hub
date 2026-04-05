/**
 * Optional mic vs local playback correlation for "Listen here" — auto one-shot only.
 * Manual DJ-style sync is deck pitch buttons in remote-control.js (no microphone).
 */

(function (global) {
  const SAMPLE_MS = 50;
  const AUTO_CAPTURE_MS = 2000;
  const MAX_LAG_SAMPLES = 28;
  const AUTO_MIN_SCORE = 0.12;

  function rmsTimeDomain(analyser) {
    const buf = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(buf);
    let s = 0;
    for (let i = 0; i < buf.length; i++) {
      const v = (buf[i] - 128) / 128;
      s += v * v;
    }
    return Math.sqrt(s / buf.length);
  }

  function normalizeZeroMeanUnit(arr) {
    const n = arr.length;
    if (!n) return [];
    let sum = 0;
    for (let i = 0; i < n; i++) sum += arr[i];
    const m = sum / n;
    let v = 0;
    const out = new Array(n);
    for (let i = 0; i < n; i++) {
      const x = arr[i] - m;
      out[i] = x;
      v += x * x;
    }
    const norm = Math.sqrt(v) || 1;
    for (let i = 0; i < n; i++) out[i] /= norm;
    return out;
  }

  function bestLagNorm(ref, mic, maxLag) {
    const len = Math.min(ref.length, mic.length);
    if (len < 8) return { lag: 0, score: 0 };
    const r = normalizeZeroMeanUnit(ref.slice(0, len));
    const m = normalizeZeroMeanUnit(mic.slice(0, len));
    let bestL = 0;
    let bestScore = -Infinity;
    for (let L = -maxLag; L <= maxLag; L++) {
      let c = 0;
      let cnt = 0;
      for (let i = 0; i < len; i++) {
        const j = i + L;
        if (j >= 0 && j < len) {
          c += r[i] * m[j];
          cnt++;
        }
      }
      const score = cnt > 0 ? c / cnt : -Infinity;
      if (score > bestScore) {
        bestScore = score;
        bestL = L;
      }
    }
    return { lag: bestL, score: bestScore };
  }

  class RemoteMicSyncController {
    /** @param {*} remoteControl RemoteControl instance */
    constructor(remoteControl) {
      this.rc = remoteControl;
      this._audioContext = null;
      this._micStream = null;
      this._elementSource = null;
      this._refAnalyser = null;
      this._micAnalyser = null;
      this._boundElement = null;
      this._autoRunning = false;
    }

    isAutoRunning() {
      return !!this._autoRunning;
    }

    _toast(msg, isError) {
      const t = global.ToastNotifications && global.ToastNotifications.showToast;
      if (t) {
        t(msg, isError
          ? { id: 'micSyncToast', backgroundColor: 'rgba(139, 0, 0, 0.92)', duration: 4000 }
          : { id: 'micSyncToast', duration: 3200 });
      } else {
        console.log(msg);
      }
    }

    /**
     * @param {HTMLMediaElement} mediaEl
     * @param {MediaStream} micStream from getUserMedia (must be obtained in the same user gesture as the Mic sync click)
     */
    async _buildGraph(mediaEl, micStream) {
      if (!micStream) {
        throw new Error('Microphone stream missing');
      }
      await this.dispose();
      const AC = global.AudioContext || global.webkitAudioContext;
      if (!AC) {
        throw new Error('Web Audio not supported');
      }
      const ctx = new AC();
      await ctx.resume();
      const elSrc = ctx.createMediaElementSource(mediaEl);
      elSrc.connect(ctx.destination);
      const refA = ctx.createAnalyser();
      const micA = ctx.createAnalyser();
      refA.fftSize = 2048;
      micA.fftSize = 2048;
      elSrc.connect(refA);
      const micSrc = ctx.createMediaStreamSource(micStream);
      micSrc.connect(micA);
      this._audioContext = ctx;
      this._micStream = micStream;
      this._elementSource = elSrc;
      this._refAnalyser = refA;
      this._micAnalyser = micA;
      this._boundElement = mediaEl;
    }

    async dispose() {
      try {
        if (this._elementSource) {
          this._elementSource.disconnect();
        }
      } catch (e) {
        /* ignore */
      }
      this._elementSource = null;
      this._refAnalyser = null;
      this._micAnalyser = null;
      this._boundElement = null;
      if (this._micStream) {
        this._micStream.getTracks().forEach((t) => t.stop());
        this._micStream = null;
      }
      if (this._audioContext) {
        try {
          await this._audioContext.close();
        } catch (e) {
          /* ignore */
        }
        this._audioContext = null;
      }
    }

    async stopAll() {
      await this.dispose();
    }

    /**
     * Run correlation using an already-granted mic stream. Call getUserMedia from the button click
     * handler (sync .then chain) — not after await inside this method — or the browser may block mic.
     * @param {HTMLMediaElement} mediaEl
     * @param {MediaStream} micStream
     */
    async runAutoWithMicStream(mediaEl, micStream) {
      this._autoRunning = true;
      try {
        try {
          await this._buildGraph(mediaEl, micStream);
        } catch (e) {
          console.warn('Mic sync auto failed:', e);
          this._toast('Mic permission or audio setup failed.', true);
          try {
            micStream.getTracks().forEach((t) => t.stop());
          } catch (e2) {
            /* ignore */
          }
          return;
        }
        const refA = this._refAnalyser;
        const micA = this._micAnalyser;
        const refBuf = [];
        const micBuf = [];
        const t0 = performance.now();
        while (performance.now() - t0 < AUTO_CAPTURE_MS) {
          refBuf.push(rmsTimeDomain(refA));
          micBuf.push(rmsTimeDomain(micA));
          await new Promise((r) => setTimeout(r, SAMPLE_MS));
        }
        const { lag, score } = bestLagNorm(refBuf, micBuf, MAX_LAG_SAMPLES);
        if (score < AUTO_MIN_SCORE) {
          this._toast(
            'Could not lock (mic too quiet or no match). Move closer to speakers.',
            true,
          );
        } else {
          const correction = -lag * (SAMPLE_MS / 1000);
          const clamped = Math.max(-0.45, Math.min(0.45, correction * 0.95));
          try {
            mediaEl.currentTime = Math.max(0, mediaEl.currentTime + clamped);
          } catch (e) {
            console.warn('Mic auto seek failed:', e);
          }
          this._toast(`Mic sync applied (~${(clamped * 1000).toFixed(0)} ms).`, false);
        }
      } finally {
        this._autoRunning = false;
        await this.dispose();
      }
    }
  }

  global.RemoteMicSyncController = RemoteMicSyncController;
})(typeof window !== 'undefined' ? window : globalThis);
