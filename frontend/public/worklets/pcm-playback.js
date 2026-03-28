class PcmPlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.readIndex = 0;
    this.current = null;
    this.port.onmessage = (event) => {
      const data = event.data;
      if (!data) return;
      if (data.type === "reset") {
        this.queue = [];
        this.readIndex = 0;
        this.current = null;
        return;
      }
      if (data.type === "push" && data.samples) {
        this.queue.push(data.samples);
      }
    };
  }

  process(_inputs, outputs) {
    const out = outputs[0];
    if (!out || !out[0]) return true;
    const channel = out[0];
    for (let i = 0; i < channel.length; i += 1) {
      if (!this.current || this.readIndex >= this.current.length) {
        this.current = this.queue.length > 0 ? this.queue.shift() : null;
        this.readIndex = 0;
      }
      if (!this.current) {
        channel[i] = 0;
        continue;
      }
      channel[i] = this.current[this.readIndex++];
    }
    return true;
  }
}

registerProcessor("pcm-playback-processor", PcmPlaybackProcessor);

