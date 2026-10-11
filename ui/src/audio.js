// Microphone capture inside the MCP App.
// The server declares `_meta.ui.permissions.microphone` on the card resource (MCP Apps 2026-01-26).
// The spec says apps SHOULD NOT assume the permission is granted, so everything here feature-detects
// and degrades to "say it to Alexa" (transcript-only) instead of failing.

export const TARGET_RATE = 16000;

export function micSupport() {
  const md = typeof navigator !== "undefined" ? navigator.mediaDevices : undefined;
  if (!md || typeof md.getUserMedia !== "function") return { ok: false, reason: "unsupported" };
  if (typeof window !== "undefined" && window.isSecureContext === false) return { ok: false, reason: "insecure" };
  return { ok: true };
}

/** Explain a getUserMedia failure in learner language. */
export function micErrorReason(err) {
  const n = err?.name || "";
  if (n === "NotAllowedError" || n === "SecurityError") return "blocked";
  if (n === "NotFoundError" || n === "OverconstrainedError") return "no-device";
  return "unsupported";
}

/** Downmix + resample Float32 PCM to 16 kHz mono (linear interpolation; fine for speech scoring). */
export function resample(input, fromRate, toRate = TARGET_RATE) {
  if (fromRate === toRate) return input;
  const ratio = fromRate / toRate;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const x = i * ratio, i0 = Math.floor(x), t = x - i0;
    out[i] = (input[i0] ?? 0) * (1 - t) + (input[i0 + 1] ?? input[i0] ?? 0) * t;
  }
  return out;
}

/** Encode mono Float32 PCM as a 16-bit WAV (RIFF) ArrayBuffer. */
export function encodeWav(samples, rate = TARGET_RATE) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); w(8, "WAVE");
  w(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  w(36, "data"); v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buf;
}

export function toBase64(buf) {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

/**
 * Start recording. Returns { stop(): Promise<{wavBase64, url, seconds}>, cancel(), level(): 0..1 }.
 * Uses MediaRecorder when present, decodes with WebAudio, and ships 16 kHz mono WAV.
 */
export async function startRecording({ maxSeconds = 15 } = {}) {
  const sup = micSupport();
  if (!sup.ok) throw Object.assign(new Error(sup.reason), { reason: sup.reason });
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
  } catch (e) {
    throw Object.assign(new Error(e?.message || "mic error"), { reason: micErrorReason(e) });
  }
  const AC = window.AudioContext || window.webkitAudioContext;
  const ctx = new AC();
  const src = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  src.connect(analyser);
  const data = new Uint8Array(analyser.fftSize);
  const chunks = [];
  const rec = typeof MediaRecorder !== "undefined" ? new MediaRecorder(stream) : null;
  rec?.addEventListener("dataavailable", (e) => e.data.size && chunks.push(e.data));
  rec?.start();
  const t0 = performance.now();
  const timer = setTimeout(() => api.stop(), maxSeconds * 1000);

  const cleanup = () => { clearTimeout(timer); stream.getTracks().forEach((t) => t.stop()); };
  let stopping = null;
  const api = {
    level() {
      analyser.getByteTimeDomainData(data);
      let peak = 0;
      for (let i = 0; i < data.length; i++) peak = Math.max(peak, Math.abs(data[i] - 128));
      return Math.min(1, peak / 64);
    },
    cancel() { try { rec?.stop(); } catch { /* ignore */ } cleanup(); ctx.close(); },
    stop() {
      if (stopping) return stopping;
      stopping = new Promise((resolve, reject) => {
        if (!rec) { cleanup(); ctx.close(); return reject(Object.assign(new Error("MediaRecorder unavailable"), { reason: "unsupported" })); }
        rec.addEventListener("stop", async () => {
          cleanup();
          try {
            const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
            const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
            const mono = resample(decoded.getChannelData(0), decoded.sampleRate);
            const wav = encodeWav(mono);
            const url = URL.createObjectURL(new Blob([wav], { type: "audio/wav" }));
            resolve({ wavBase64: toBase64(wav), url, seconds: (performance.now() - t0) / 1000, sampleRate: TARGET_RATE });
          } catch (e) { reject(e); } finally { ctx.close(); }
        }, { once: true });
        rec.stop();
      });
      return stopping;
    },
  };
  return api;
}
