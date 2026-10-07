// Mic capture: Float32 at the context rate -> PCM16 at 24 kHz, posted in 960-sample (40 ms) frames.
const TARGET_RATE = 24000;
const FRAME_SAMPLES = 960;

class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / TARGET_RATE;
    this.frame = new Int16Array(FRAME_SAMPLES);
    this.filled = 0;
    // Fractional read position carried across render quanta when resampling.
    this.pos = 0;
  }

  push(sample) {
    const s = Math.max(-1, Math.min(1, sample));
    this.frame[this.filled++] = s < 0 ? s * 0x8000 : s * 0x7fff;
    if (this.filled === FRAME_SAMPLES) {
      const out = this.frame;
      this.port.postMessage(out.buffer, [out.buffer]);
      this.frame = new Int16Array(FRAME_SAMPLES);
      this.filled = 0;
    }
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    if (this.ratio === 1) {
      for (let i = 0; i < channel.length; i++) this.push(channel[i]);
      return true;
    }
    // Linear-interpolation resampler for browsers that ignore the requested 24 kHz rate.
    while (this.pos < channel.length - 1) {
      const i = Math.floor(this.pos);
      const frac = this.pos - i;
      this.push(channel[i] * (1 - frac) + channel[i + 1] * frac);
      this.pos += this.ratio;
    }
    this.pos -= channel.length;
    if (this.pos < 0) this.pos = 0;
    return true;
  }
}

registerProcessor("capture-processor", CaptureProcessor);
