const MIMES = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4", "audio/webm"];
const MAX_SECONDS = 120;

export const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
export const extFromMime = (m = "") => (m.includes("ogg") ? "ogg" : m.includes("mp4") ? "m4a" : "webm");

export class Recorder {
  async start(onTick, onLimit) {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.mime = MIMES.find((m) => window.MediaRecorder?.isTypeSupported(m)) || "";
    this.chunks = [];
    this.mr = new MediaRecorder(this.stream, this.mime ? { mimeType: this.mime } : undefined);
    this.mr.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
    this.mr.start();
    this.t0 = performance.now();
    this.limited = false;
    this.timer = setInterval(() => {
      const s = this.elapsed();
      onTick(s);
      if (s >= MAX_SECONDS && !this.limited) { this.limited = true; onLimit(); }
    }, 250);
  }

  elapsed() { return (performance.now() - this.t0) / 1000; }

  #release() {
    clearInterval(this.timer);
    this.stream?.getTracks().forEach((t) => t.stop());
  }

  stop() {
    return new Promise((resolve) => {
      const secs = this.elapsed();
      this.mr.onstop = () => {
        this.#release();
        const mime = this.mr.mimeType || this.mime;
        resolve({ blob: new Blob(this.chunks, { type: mime }), secs, mime });
      };
      this.mr.stop();
    });
  }

  cancel() {
    this.mr.onstop = () => this.#release();
    if (this.mr.state !== "inactive") this.mr.stop(); else this.#release();
  }
}

const PLAY = '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>';
const PAUSE = '<svg viewBox="0 0 24 24"><path d="M8 5v14M16 5v14"/></svg>';

export function audioBubble(url, secs) {
  const box = document.createElement("div");
  box.className = "audio";
  const btn = document.createElement("button");
  btn.type = "button"; btn.className = "play"; btn.innerHTML = PLAY; btn.setAttribute("aria-label", "Ouvir áudio");
  const wave = document.createElement("div");
  wave.className = "wave";
  const bars = Array.from({ length: 28 }, (_, i) => {
    const b = document.createElement("i");
    b.style.height = `${25 + Math.abs(Math.sin(i * 1.7 + secs)) * 75}%`;
    wave.append(b);
    return b;
  });
  const dur = document.createElement("span");
  dur.className = "dur"; dur.textContent = fmt(secs);
  const audio = new Audio(url);
  btn.addEventListener("click", () => (audio.paused ? audio.play() : audio.pause()));
  audio.addEventListener("play", () => { btn.innerHTML = PAUSE; });
  audio.addEventListener("pause", () => { btn.innerHTML = PLAY; });
  audio.addEventListener("ended", () => { bars.forEach((b) => b.classList.remove("on")); dur.textContent = fmt(secs); });
  audio.addEventListener("timeupdate", () => {
    const p = Math.min(1, audio.currentTime / secs);
    bars.forEach((b, i) => b.classList.toggle("on", i / bars.length < p));
    dur.textContent = fmt(audio.currentTime);
  });
  box.append(btn, wave, dur);
  return box;
}
