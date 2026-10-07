// Playback: queue of PCM16 chunks played at the context rate (24 kHz).
// {type: "flush"} drops everything instantly, which is what makes barge-in feel immediate.
// Chunks are tagged with the transcript item they belong to, and the processor reports how many
// samples of each item have actually been heard so the transcript can follow the voice.
const IDLE_STOP_SAMPLES = Math.round(sampleRate * 0.4);
const PROGRESS_EVERY_SAMPLES = Math.round(sampleRate * 0.1);

class PlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.idleSamples = 0;
    this.queue = [];
    this.current = null;
    this.offset = 0;
    this.playing = false;
    this.played = new Map();
    this.dirty = new Set();
    this.sinceReport = 0;
    this.port.onmessage = (event) => {
      const data = event.data;
      if (data && data.type === "chunk") {
        const samples = new Int16Array(data.buffer, 0, data.buffer.byteLength >> 1);
        const floats = new Float32Array(samples.length);
        for (let i = 0; i < samples.length; i++) floats[i] = samples[i] / 0x8000;
        this.queue.push({ floats, item: data.item || null });
      } else if (data && data.type === "flush") {
        this.queue = [];
        this.current = null;
        this.offset = 0;
        this.report();
        this.setPlaying(false);
      }
    };
  }

  setPlaying(playing) {
    if (playing !== this.playing) {
      this.playing = playing;
      this.port.postMessage({ type: playing ? "started" : "stopped" });
    }
  }

  report() {
    for (const item of this.dirty) {
      this.port.postMessage({ type: "progress", item, played: this.played.get(item) });
    }
    this.dirty.clear();
    this.sinceReport = 0;
  }

  process(_inputs, outputs) {
    const out = outputs[0][0];
    let written = 0;
    while (written < out.length) {
      if (!this.current) {
        this.current = this.queue.shift() || null;
        this.offset = 0;
        if (!this.current) break;
      }
      const { floats, item } = this.current;
      const n = Math.min(out.length - written, floats.length - this.offset);
      out.set(floats.subarray(this.offset, this.offset + n), written);
      written += n;
      this.offset += n;
      if (item) {
        this.played.set(item, (this.played.get(item) || 0) + n);
        this.dirty.add(item);
      }
      if (this.offset >= floats.length) this.current = null;
    }
    if (written < out.length) out.fill(0, written);
    for (let c = 1; c < outputs[0].length; c++) outputs[0][c].set(out);
    this.sinceReport += written;
    if (this.sinceReport >= PROGRESS_EVERY_SAMPLES || (written < out.length && this.dirty.size)) {
      this.report();
    }
    if (written > 0) {
      this.idleSamples = 0;
      this.setPlaying(true);
    } else if (this.playing) {
      // Bridge short network gaps so the "speaking" state doesn't flicker between chunks.
      this.idleSamples += out.length;
      if (this.idleSamples >= IDLE_STOP_SAMPLES) this.setPlaying(false);
    }
    return true;
  }
}

registerProcessor("playback-processor", PlaybackProcessor);
