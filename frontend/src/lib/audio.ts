// Web Audio plumbing: 24 kHz AudioContext, mic capture worklet, and a flushable player.

export const SAMPLE_RATE = 24000;

const CAPTURE_URL = "/worklets/capture-processor.js";
const PLAYBACK_URL = "/worklets/playback-processor.js";

export interface AudioEngine {
  /** Queue a PCM16 chunk for playback, tagged with the transcript item it voices. */
  play(chunk: ArrayBuffer, itemId: string | null): void;
  /** Drop all queued audio immediately (barge-in). */
  flush(): void;
  setMuted(muted: boolean): void;
  close(): Promise<void>;
}

export interface AudioEngineOptions {
  /** Called with each 40 ms PCM16 mic frame. */
  onMicFrame: (frame: ArrayBuffer) => void;
  /** Called when the player starts or stops producing sound. */
  onPlaybackChange: (playing: boolean) => void;
  /** Called with the total samples of `itemId` that have actually been played so far. */
  onPlaybackProgress: (itemId: string, playedSamples: number) => void;
}

type PlayerMessage =
  | { type: "started" | "stopped" }
  | { type: "progress"; item: string; played: number };

export async function createAudioEngine(opts: AudioEngineOptions): Promise<AudioEngine> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Microphone access requires a secure context (https or localhost).");
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
    },
  });

  const ctx = new AudioContext({ sampleRate: SAMPLE_RATE, latencyHint: "interactive" });
  let captureCtx = ctx;
  try {
    await ctx.audioWorklet.addModule(PLAYBACK_URL);
    await ctx.audioWorklet.addModule(CAPTURE_URL);

    let source: MediaStreamAudioSourceNode;
    try {
      source = ctx.createMediaStreamSource(stream);
    } catch {
      // Firefox cannot connect a mic to a context whose rate differs from the device rate.
      // Capture in a native-rate context instead; the worklet resamples to 24 kHz.
      captureCtx = new AudioContext({ latencyHint: "interactive" });
      await captureCtx.audioWorklet.addModule(CAPTURE_URL);
      source = captureCtx.createMediaStreamSource(stream);
    }

    const capture = new AudioWorkletNode(captureCtx, "capture-processor", {
      numberOfInputs: 1,
      numberOfOutputs: 0,
      channelCount: 1,
    });
    capture.port.onmessage = (e: MessageEvent<ArrayBuffer>) => opts.onMicFrame(e.data);
    source.connect(capture);

    const player = new AudioWorkletNode(ctx, "playback-processor", {
      numberOfInputs: 0,
      numberOfOutputs: 1,
      outputChannelCount: [1],
    });
    player.port.onmessage = (e: MessageEvent<PlayerMessage>) => {
      const msg = e.data;
      if (msg.type === "progress") opts.onPlaybackProgress(msg.item, msg.played);
      else opts.onPlaybackChange(msg.type === "started");
    };
    player.connect(ctx.destination);

    await ctx.resume();
    if (captureCtx !== ctx) await captureCtx.resume();

    return {
      play(chunk, itemId) {
        player.port.postMessage({ type: "chunk", buffer: chunk, item: itemId }, [chunk]);
      },
      flush() {
        player.port.postMessage({ type: "flush" });
      },
      setMuted(muted) {
        // A disabled track yields silence, so server-side VAD still sees the turn end.
        stream.getAudioTracks().forEach((t) => (t.enabled = !muted));
      },
      async close() {
        stream.getTracks().forEach((t) => t.stop());
        source.disconnect();
        capture.port.onmessage = null;
        player.port.onmessage = null;
        await Promise.allSettled([
          ctx.close(),
          captureCtx !== ctx ? captureCtx.close() : Promise.resolve(),
        ]);
      },
    };
  } catch (err) {
    stream.getTracks().forEach((t) => t.stop());
    await Promise.allSettled([ctx.close(), captureCtx !== ctx ? captureCtx.close() : null]);
    throw err;
  }
}
