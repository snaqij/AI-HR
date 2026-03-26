<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  appendCandidateEvent,
  bootstrapDemoSession,
  buildInterviewDuplexWsUrl,
  buildInterviewEventsWsUrl,
  createInterviewSession,
  finishInterviewSession,
  generateQuestionSet,
  loadInterviewReport,
  loadReplayItems,
  startInterviewSession,
  streamASR,
  streamTTS,
  type InterviewSession,
  type ReplayItem,
  type InterviewRealtimeEvent
} from "./api";

const loading = ref(true);
const errorText = ref("");
const exiting = ref(false);
const session = ref<InterviewSession | null>(null);
const reportSummary = ref("");
const currentQuestion = ref("请稍候，正在加载面试问题...");
const followupQuestion = ref("面试官会根据你的回答进行补充提问。");
const transcriptItems = ref<ReplayItem[]>([]);
const liveTranscriptItems = ref<ReplayItem[]>([]);
const elapsedSeconds = ref(0);
const micStatus = ref("待启动");
const ttsStatus = ref("待播报");
const partialHint = ref("");

let replayTimer: number | null = null;
let tickerTimer: number | null = null;
let analyzeTimer: number | null = null;
let wsReconnectTimer: number | null = null;
let duplexReconnectTimer: number | null = null;
let heartbeatTimer: number | null = null;

let audioContext: AudioContext | null = null;
let mediaStream: MediaStream | null = null;
let sourceNode: MediaStreamAudioSourceNode | null = null;
let workletNode: AudioWorkletNode | null = null;
let audioPlayer: HTMLAudioElement | null = null;
let sessionSocket: WebSocket | null = null;
let duplexSocket: WebSocket | null = null;

const frameWindow: Float32Array[] = [];
let frameWindowSamples = 0;
let frameWindowEnergy = 0;

const sentenceChunks: Int16Array[] = [];
let sentenceSamples = 0;
let silenceWindows = 0;
let asrSeq = 1;
let eventSeq = 1;
let lastFollowupAt = 0;
let lastFollowupNormalized = "";
let busySubmitting = false;
let wsConnected = false;
let duplexConnected = false;
let duplexChunkIndex = 1;
let duplexHasAudioInSeq = false;
const offlineBuffer: Int16Array[] = [];
const fallbackSubmittedSeq = new Set<number>();

const SAMPLE_RATE = 16000;
const FRAME_MS = 30;
const SAMPLES_PER_FRAME = Math.floor((SAMPLE_RATE * FRAME_MS) / 1000);
const ACK_TIMEOUT_MS = 180;
const MAX_RETRY = 2;
const ENERGY_THRESHOLD = 0.0022;
const PAUSE_WINDOWS_TO_COMMIT = 3; // 3 * 150ms = 450ms
const ANALYZE_INTERVAL_MS = 150;
const MAX_SENTENCE_SECONDS = 12;
const MAX_SENTENCE_SAMPLES = SAMPLE_RATE * MAX_SENTENCE_SECONDS;
const MIN_SENTENCE_SAMPLES = SAMPLE_RATE * 0.4;
const FAILSAFE_SILENCE_WINDOWS = 6; // 6 * 150ms = 900ms (Failsafe for very short words)
const FOLLOWUP_COOLDOWN_MS = 2200;
const TTS_CAPTURE_BLOCK_MS = 900;
const ADAPTIVE_SPEECH_FACTOR = 3.4;
const NOISE_ALPHA = 0.08;
const ADAPTIVE_MIN_THRESHOLD = 0.0012;
const ADAPTIVE_MAX_THRESHOLD = 0.012;
let noiseFloor = 0.0018;
let adaptiveThreshold = ENERGY_THRESHOLD;
let lastTtsEndedAt = 0;
const ttsQueue: string[] = [];
let ttsPlaying = false;
const rawTtsQueue: AudioBuffer[] = [];
let rawTtsPlaying = false;
let nextStartTime = 0;
const pendingFrames = new Map<string, { payload: string; retry: number; timer: number }>();

const meetingTimeText = computed(() => {
  const mins = Math.floor(elapsedSeconds.value / 60)
    .toString()
    .padStart(2, "0");
  const secs = Math.floor(elapsedSeconds.value % 60)
    .toString()
    .padStart(2, "0");
  return `${mins}:${secs}`;
});

function normalizeForCompare(text: string): string {
  return text.replace(/[，。！？、,.!?;；:\s]/g, "").trim();
}

function isPlaceholderTranscript(text: string): boolean {
  return /ASR_TRANSCRIPT_SEQ_\d+/i.test((text || "").trim());
}

function isLikelyPromptEcho(text: string): boolean {
  const normalized = normalizeForCompare(text);
  if (!normalized || normalized.length < 6) {
    return false;
  }
  const q = normalizeForCompare(currentQuestion.value || "");
  const f = normalizeForCompare(followupQuestion.value || "");
  const similar = (target: string): boolean => {
    if (!target || target.length < 6) {
      return false;
    }
    return target.includes(normalized) || normalized.includes(target.slice(0, Math.min(target.length, normalized.length)));
  };
  return similar(q) || similar(f);
}

function mergeTranscriptLines(items: ReplayItem[]): string[] {
  const source = items
    .filter((item) => item.speaker === "candidate" || item.speaker === "candidate_partial")
    .map((item) => (item.transcript || "").trim())
    .filter((text) => !!text && !isPlaceholderTranscript(text));
  // Keep subtitle lines readable: do not aggressively merge short chunks.
  // Only drop exact consecutive duplicates.
  const lines: string[] = [];
  for (const text of source) {
    const latest = lines[lines.length - 1] || "";
    if (latest === text) {
      continue;
    }
    lines.push(text);
  }
  return lines.slice(-14).reverse();
}

const transcriptView = computed(() => mergeTranscriptLines([...liveTranscriptItems.value, ...transcriptItems.value]));

function pushLiveTranscript(text: string, speaker: "candidate" | "candidate_partial" = "candidate_partial"): void {
  const normalized = text.trim();
  if (!normalized) {
    return;
  }
  if (isPlaceholderTranscript(normalized)) {
    return;
  }
  if (isLikelyPromptEcho(normalized)) {
    return;
  }
  const latestIndex = liveTranscriptItems.value.length - 1;
  const latest = latestIndex >= 0 ? liveTranscriptItems.value[latestIndex] : null;

  if (latest && latest.speaker === "candidate_partial" && speaker === "candidate_partial") {
    // Continuous partial update: just overwrite.
    latest.transcript = normalized;
    latest.occurred_at = new Date().toISOString();
    return;
  }

  if (latest && latest.speaker === "candidate_partial" && speaker === "candidate") {
    // Final result replaces the active partial line.
    latest.transcript = normalized;
    latest.speaker = "candidate";
    latest.occurred_at = new Date().toISOString();
    return;
  }

  // Push new line for speaker switch or a fresh turn.
  liveTranscriptItems.value.push({
    turn_id: `live-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    turn_no: 0,
    speaker,
    transcript: normalized,
    occurred_at: new Date().toISOString()
  });
  if (liveTranscriptItems.value.length > 24) {
    liveTranscriptItems.value = liveTranscriptItems.value.slice(-24);
  }
}

function floatToInt16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i += 1) {
    const s = Math.max(-1, Math.min(1, input[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

function mergeInt16(chunks: Int16Array[]): Int16Array {
  const total = chunks.reduce((sum, arr) => sum + arr.length, 0);
  const out = new Int16Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
}

function encodeWavBase64(samples: Int16Array, sampleRate: number): string {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i += 1) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };
  writeString(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, samples.length * 2, true);
  let idx = 44;
  for (let i = 0; i < samples.length; i += 1) {
    view.setInt16(idx, samples[i], true);
    idx += 2;
  }
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function encodePcmBase64(samples: Int16Array): string {
  const bytes = new Uint8Array(samples.length * 2);
  const view = new DataView(bytes.buffer);
  for (let i = 0; i < samples.length; i += 1) {
    view.setInt16(i * 2, samples[i], true);
  }
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

async function playAudioDataUris(uris: string[]): Promise<void> {
  if (!uris.length) {
    return;
  }
  if (!audioPlayer) {
    audioPlayer = new Audio();
  }
  for (const uri of uris) {
    await new Promise<void>((resolve) => {
      if (!audioPlayer) {
        resolve();
        return;
      }
      audioPlayer.src = uri;
      audioPlayer.onended = () => resolve();
      audioPlayer.onerror = () => resolve();
      audioPlayer.play().then(() => undefined).catch(() => resolve());
    });
  }
}

function playRawPcm(buffer: ArrayBuffer): void {
  if (!audioContext) {
    audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });
  }
  if (audioContext.state === "suspended") {
    void audioContext.resume();
  }

  // Convert Int16 PCM to Float32
  const int16 = new Int16Array(buffer);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32768.0;
  }

  const audioBuffer = audioContext.createBuffer(1, float32.length, SAMPLE_RATE);
  audioBuffer.getChannelData(0).set(float32);

  const source = audioContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(audioContext.destination);

  // Stitching logic for seamless playback
  const currentTime = audioContext.currentTime;
  if (nextStartTime < currentTime) {
    nextStartTime = currentTime + 0.01;
  }
  source.start(nextStartTime);
  nextStartTime += audioBuffer.duration;
  
  source.onended = () => {
    lastTtsEndedAt = Date.now();
  };
  rawTtsPlaying = true;
}

async function pumpTtsQueue(): Promise<void> {
  if (ttsPlaying) {
    return;
  }
  ttsPlaying = true;
  try {
    while (ttsQueue.length > 0) {
      const uri = ttsQueue.shift();
      if (!uri) {
        continue;
      }
      await playAudioDataUris([uri]);
      lastTtsEndedAt = Date.now();
    }
  } finally {
    ttsPlaying = false;
    if (ttsQueue.length === 0) {
      ttsStatus.value = "已播报";
    }
  }
}

function shouldBlockCaptureByTts(): boolean {
  if (ttsPlaying || rawTtsPlaying) {
    // Check if rawTts is still "effectively" playing based on nextStartTime
    const now = audioContext?.currentTime || 0;
    if (nextStartTime > now + 0.05) {
      return true;
    }
    rawTtsPlaying = false;
  }
  if (ttsPlaying) return true;
  return Date.now() - lastTtsEndedAt < TTS_CAPTURE_BLOCK_MS;
}

function enqueueTtsUris(uris: string[]): void {
  for (const uri of uris) {
    if (uri) {
      ttsQueue.push(uri);
    }
  }
  void pumpTtsQueue();
}

function resetSentenceBuffer(): void {
  sentenceChunks.length = 0;
  sentenceSamples = 0;
  silenceWindows = 0;
}

function splitFrames(samples: Int16Array): Int16Array[] {
  if (!samples.length) {
    return [];
  }
  const result: Int16Array[] = [];
  for (let idx = 0; idx < samples.length; idx += SAMPLES_PER_FRAME) {
    result.push(samples.slice(idx, Math.min(samples.length, idx + SAMPLES_PER_FRAME)));
  }
  return result;
}

function makeFrameId(seq: number, chunkIndex: number): string {
  return `${seq}-${chunkIndex}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

function clearPendingFrame(frameId: string): void {
  const pending = pendingFrames.get(frameId);
  if (!pending) {
    return;
  }
  window.clearTimeout(pending.timer);
  pendingFrames.delete(frameId);
}

function armFrameTimeout(frameId: string): void {
  const pending = pendingFrames.get(frameId);
  if (!pending || !duplexSocket || duplexSocket.readyState !== WebSocket.OPEN) {
    return;
  }
  pending.timer = window.setTimeout(() => {
    const current = pendingFrames.get(frameId);
    if (!current || !duplexSocket || duplexSocket.readyState !== WebSocket.OPEN) {
      return;
    }
    if (current.retry >= MAX_RETRY || current.payload.includes('"type":"audio_chunk"')) {
      pendingFrames.delete(frameId);
      return;
    }
    current.retry += 1;
    duplexSocket.send(current.payload);
    armFrameTimeout(frameId);
  }, ACK_TIMEOUT_MS);
}

function applyRealtimeEvent(event: InterviewRealtimeEvent): void {
  if (event.event_type === "session.event") {
    const payload = (event.payload || {}) as Record<string, unknown>;
    const followupText = String(payload.followup_question || "").trim();
    if (followupText) {
      followupQuestion.value = followupText;
    }
  }
  if (event.event_type === "asr.turn") {
    const payload = (event.payload || {}) as Record<string, unknown>;
    const text = String(payload.transcript || "").trim();
    if (text && !isPlaceholderTranscript(text)) {
      partialHint.value = text;
      pushLiveTranscript(text, "candidate_partial");
    }
  }
}

async function applyFollowupFromEventResult(eventResult: Record<string, unknown>): Promise<void> {
  const now = Date.now();
  const followupText = String(eventResult.followup_question || "").trim();
  const normalizedFollowup = normalizeForCompare(followupText);
  const isDifferentFollowup = !!normalizedFollowup && normalizedFollowup !== lastFollowupNormalized;
  if (!followupText || !isDifferentFollowup || now - lastFollowupAt <= FOLLOWUP_COOLDOWN_MS) {
    return;
  }
  lastFollowupAt = now;
  lastFollowupNormalized = normalizedFollowup;
  followupQuestion.value = followupText;
  const audioUris = Array.isArray(eventResult.followup_audio_uris) ? (eventResult.followup_audio_uris as string[]) : [];
  if (audioUris.length > 0) {
    ttsStatus.value = "播报中...";
    enqueueTtsUris(audioUris);
    return;
  }
  try {
    ttsStatus.value = "播报中...";
    const tts = await streamTTS(session.value!.id, followupText);
    enqueueTtsUris(tts.audio_uris || []);
  } catch {
    ttsStatus.value = "待播报";
  }
}

async function fallbackFollowupFromTranscript(seq: number, transcript: string): Promise<void> {
  if (!session.value || !transcript.trim()) {
    return;
  }
  if (isPlaceholderTranscript(transcript)) {
    return;
  }
  if (fallbackSubmittedSeq.has(seq)) {
    return;
  }
  fallbackSubmittedSeq.add(seq);
  try {
    const event = await appendCandidateEvent(session.value.id, {
      seq: eventSeq++,
      transcript: transcript.trim(),
      eventId: `duplex-fallback-${seq}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
    });
    await applyFollowupFromEventResult(event as unknown as Record<string, unknown>);
    void refreshReplay();
  } catch {
    return;
  }
}

function connectRealtimeBus(sessionId: string): void {
  if (sessionSocket) {
    sessionSocket.close();
    sessionSocket = null;
  }
  const wsUrl = buildInterviewEventsWsUrl(sessionId);
  const ws = new WebSocket(wsUrl);
  sessionSocket = ws;

  ws.onopen = () => {
    wsConnected = true;
  };
  ws.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data) as InterviewRealtimeEvent;
      applyRealtimeEvent(payload);
    } catch {
      return;
    }
  };
  ws.onerror = () => {
    wsConnected = false;
  };
  ws.onclose = () => {
    wsConnected = false;
    if (wsReconnectTimer != null) {
      window.clearTimeout(wsReconnectTimer);
    }
    wsReconnectTimer = window.setTimeout(() => {
      if (session.value) {
        connectRealtimeBus(session.value.id);
      }
    }, 2000);
  };
}

function connectDuplexSocket(sessionId: string): void {
  if (duplexSocket) {
    duplexSocket.close();
    duplexSocket = null;
  }
  const wsUrl = buildInterviewDuplexWsUrl(sessionId);
  const ws = new WebSocket(wsUrl);
  duplexSocket = ws;

  ws.onopen = () => {
    duplexConnected = true;
    ws.binaryType = "arraybuffer"; // 启用二进制支持
    ws.send(JSON.stringify({ type: "ping" }));
    
    // Flush buffered chunks after reconnection
    while (offlineBuffer.length > 0) {
      const chunk = offlineBuffer.shift();
      if (chunk) sendDuplexChunk(chunk, false);
    }
    
    // Heartbeat to prevent gateway timeout
    if (heartbeatTimer != null) window.clearInterval(heartbeatTimer);
    heartbeatTimer = window.setInterval(() => {
      if (duplexSocket?.readyState === WebSocket.OPEN) {
        duplexSocket.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);
  };
  ws.onmessage = (event) => {
    if (event.data instanceof ArrayBuffer) {
      // 收到 TTS 二进制音频帧
      playRawPcm(event.data);
      return;
    }
    try {
      const payload = JSON.parse(event.data) as Record<string, unknown>;
      const type = String(payload.type || "");
      if (type === "duplex.ack") {
        const frameId = String(payload.frame_id || "").trim();
        const status = String(payload.status || "").trim().toLowerCase();
        if (frameId && (status === "accepted" || status === "duplicate")) {
          clearPendingFrame(frameId);
        }
        return;
      }
      if (type === "duplex.tts.packet") {
        const uri = String(payload.audio_uri || "").trim();
        const transport = String(payload.transport || "");
        if (transport === "binary") {
          ttsStatus.value = "播报中...";
          // 下一条消息将是二进制帧，由 ArrayBuffer 分支处理
          return;
        }
        if (uri) {
          ttsStatus.value = "播报中...";
          enqueueTtsUris([uri]);
        }
        return;
      }
      if (type !== "duplex.turn") {
        return;
      }
      const data = (payload.data || {}) as Record<string, unknown>;
      const asr = (data.asr || {}) as Record<string, unknown>;
      const eventResult = (data.event || null) as Record<string, unknown> | null;
      const seq = Number(data.seq || 0);
      const isFinal = Boolean(data.is_final);
      const transcript = String(asr.transcript || "").trim();
      const validTranscript = transcript && !isPlaceholderTranscript(transcript);
      if (validTranscript && !isLikelyPromptEcho(transcript)) {
        partialHint.value = transcript;
        pushLiveTranscript(transcript, isFinal ? "candidate" : "candidate_partial");
      }

      if (eventResult) {
        void refreshReplay();
        partialHint.value = "";
        void applyFollowupFromEventResult(eventResult);
      } else if (isFinal && seq > 0 && validTranscript) {
        // Fallback path: if final turn misses event payload, call events API to trigger followup.
        void fallbackFollowupFromTranscript(seq, transcript);
      }
    } catch {
      return;
    }
  };
  ws.onerror = () => {
    duplexConnected = false;
  };
  ws.onclose = () => {
    duplexConnected = false;
    duplexChunkIndex = 1;
    duplexHasAudioInSeq = false;
    if (heartbeatTimer != null) {
      window.clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
    for (const frameId of Array.from(pendingFrames.keys())) {
      clearPendingFrame(frameId);
    }
    if (duplexReconnectTimer != null) {
      window.clearTimeout(duplexReconnectTimer);
    }
    duplexReconnectTimer = window.setTimeout(() => {
      if (session.value) {
        connectDuplexSocket(session.value.id);
      }
    }, 1800);
  };
}

function sendDuplexChunk(samples: Int16Array, isFinal: boolean): boolean {
  if (!session.value || !duplexSocket) {
    return false;
  }
  if (duplexSocket.readyState !== WebSocket.OPEN) {
    if (duplexSocket.readyState === WebSocket.CLOSED || duplexSocket.readyState === WebSocket.CLOSING) {
      // Force reconnect if we have speech but no socket
      console.warn("Duplex socket closed during speech, re-initiating...");
      connectDuplexSocket(session.value.id);
      
      // Buffer the chunk to avoid losing initial words
      if (offlineBuffer.length < 50) { // Limit buffer size to 7.5s (50 * 150ms)
        offlineBuffer.push(samples);
      }
    }
    return false;
  }
  const frameId = makeFrameId(asrSeq, duplexChunkIndex);
  const metadata = {
    type: "audio_chunk",
    frame_id: frameId,
    seq: asrSeq,
    chunk_index: duplexChunkIndex,
    chunk_total: isFinal ? duplexChunkIndex : 9999,
    is_final: isFinal,
    input_format: "pcm",
    target_latency_ms: 700
  };

  const metaStr = JSON.stringify(metadata);
  const metaBytes = new TextEncoder().encode(metaStr);
  const pcmBytes = new Uint8Array(samples.buffer, samples.byteOffset, samples.byteLength);
  
  // Format: [2 bytes Big-Endian JSON size][JSON Metadata][Raw PCM]
  const totalLen = 2 + metaBytes.byteLength + pcmBytes.byteLength;
  const buffer = new ArrayBuffer(totalLen);
  const view = new DataView(buffer);
  view.setUint16(0, metaBytes.byteLength, false); // Big-Endian
  
  const uint8 = new Uint8Array(buffer);
  uint8.set(metaBytes, 2);
  uint8.set(pcmBytes, 2 + metaBytes.byteLength);

  duplexSocket.send(buffer);
  
  // For ACK tracking, we still use the JSON metadata as payload reference
  pendingFrames.set(frameId, { payload: metaStr, retry: 0, timer: 0 });
  armFrameTimeout(frameId);
  
  duplexChunkIndex += 1;
  duplexHasAudioInSeq = true;
  if (isFinal) {
    asrSeq += 1;
    duplexChunkIndex = 1;
    duplexHasAudioInSeq = false;
  }
  return true;
}

async function submitSentenceAudio(merged: Int16Array): Promise<void> {
  if (!session.value || busySubmitting) {
    return;
  }
  if (duplexConnected) {
    partialHint.value = "识别中...";
    // Use actual sentence audio as final chunk; avoid silent final marker that causes placeholder transcripts.
    sendDuplexChunk(merged, true);
    return;
  }
  busySubmitting = true;
  partialHint.value = "识别中...";
  try {
    const audioBase64 = encodeWavBase64(merged, SAMPLE_RATE);
    const asr = await streamASR(session.value.id, { seq: asrSeq++, audioBase64, textHint: "" });
    const transcript = (asr.transcript || "").trim();
    if (!transcript || isPlaceholderTranscript(transcript)) {
      partialHint.value = "";
      return;
    }
    partialHint.value = transcript;
    const event = await appendCandidateEvent(session.value.id, {
      seq: eventSeq++,
      transcript,
      eventId: `web-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
    });
    await refreshReplay();
    partialHint.value = "";

    const now = Date.now();
    const followupText = (event.followup_question || "").trim();
    const normalizedFollowup = normalizeForCompare(followupText);
    const isDifferentFollowup = !!normalizedFollowup && normalizedFollowup !== lastFollowupNormalized;
    if (followupText && isDifferentFollowup && now - lastFollowupAt > FOLLOWUP_COOLDOWN_MS) {
      lastFollowupAt = now;
      lastFollowupNormalized = normalizedFollowup;
      followupQuestion.value = followupText;
      ttsStatus.value = "播报中...";
      const tts = await streamTTS(session.value.id, followupText);
      await playAudioDataUris(tts.audio_uris || []);
      ttsStatus.value = "已播报";
    }
  } catch (err) {
    errorText.value = err instanceof Error ? err.message : "语音链路调用失败";
    micStatus.value = "异常";
    partialHint.value = "";
  } finally {
    busySubmitting = false;
  }
}

async function analyzeSpeechWindow(): Promise<void> {
  if (!session.value || !frameWindow.length) {
    return;
  }

  const chunks = frameWindow.splice(0, frameWindow.length);
  const samples = frameWindowSamples;
  const energy = frameWindowEnergy / Math.max(1, chunks.length);
  frameWindowSamples = 0;
  frameWindowEnergy = 0;

  const pcmChunks = chunks.map((item) => floatToInt16(item));
  const mergedWindow = mergeInt16(pcmChunks);
  if (shouldBlockCaptureByTts()) {
    resetSentenceBuffer();
    return;
  }
  const candidateSpeech = energy >= adaptiveThreshold;

  if (!candidateSpeech) {
    noiseFloor = noiseFloor * (1 - NOISE_ALPHA) + energy * NOISE_ALPHA;
    adaptiveThreshold = Math.min(
      ADAPTIVE_MAX_THRESHOLD,
      Math.max(ADAPTIVE_MIN_THRESHOLD, noiseFloor * ADAPTIVE_SPEECH_FACTOR)
    );
  }

  const isSpeech = energy >= adaptiveThreshold;

  if (isSpeech) {
    sentenceChunks.push(mergedWindow);
    sentenceSamples += samples;
    silenceWindows = 0;
    partialHint.value = "正在听你说话...";
    if (duplexConnected) {
      const frames = splitFrames(mergedWindow);
      for (const frame of frames) {
        sendDuplexChunk(frame, false);
      }
    }
  } else if (sentenceSamples > 0) {
    silenceWindows += 1;
  }

  const shouldCommitByPause = sentenceSamples >= MIN_SENTENCE_SAMPLES && silenceWindows >= PAUSE_WINDOWS_TO_COMMIT;
  const shouldCommitByFailsafe = sentenceSamples > 0 && silenceWindows >= FAILSAFE_SILENCE_WINDOWS;
  const shouldCommitByLength = sentenceSamples >= MAX_SENTENCE_SAMPLES;
  
  if (!shouldCommitByPause && !shouldCommitByLength && !shouldCommitByFailsafe) {
    return;
  }
  const sentence = mergeInt16(sentenceChunks);
  resetSentenceBuffer();
  await submitSentenceAudio(sentence);
}

async function startMicPipeline(): Promise<void> {
  if (!session.value) {
    return;
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    });
    audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });
    await audioContext.audioWorklet.addModule("/worklets/pcm-capture.js");
    sourceNode = audioContext.createMediaStreamSource(mediaStream);
    workletNode = new AudioWorkletNode(audioContext, "pcm-capture-processor", {
      numberOfInputs: 1,
      numberOfOutputs: 0,
      channelCount: 1
    });
    workletNode.port.onmessage = (event) => {
      const samples = event.data as Float32Array;
      if (!samples || !samples.length) {
        return;
      }
      frameWindow.push(samples);
      frameWindowSamples += samples.length;
      let e = 0;
      for (let i = 0; i < samples.length; i += 1) {
        e += samples[i] * samples[i];
      }
      frameWindowEnergy += e / samples.length;
    };
    sourceNode.connect(workletNode);
    analyzeTimer = window.setInterval(() => {
      void analyzeSpeechWindow();
    }, ANALYZE_INTERVAL_MS);
    micStatus.value = "采集中";
  } catch (err) {
    micStatus.value = "未授权";
    errorText.value = err instanceof Error ? err.message : "麦克风权限获取失败";
  }
}

async function bootstrap(): Promise<void> {
  loading.value = true;
  errorText.value = "";
  const params = new URLSearchParams(window.location.search);
  const qSessionId = params.get("session_id") || "";
  const qCandidateId = params.get("candidate_id") || "";
  const qJobId = params.get("job_id") || "";

  try {
    let activeSessionId = qSessionId;
    if (!activeSessionId) {
      if (!qCandidateId || !qJobId) {
        const demo = await bootstrapDemoSession();
        session.value = demo;
        activeSessionId = demo.id;
        const target = new URL(window.location.href);
        target.searchParams.set("session_id", demo.id);
        target.searchParams.set("candidate_id", demo.candidate_id);
        target.searchParams.set("job_id", demo.job_id);
        window.history.replaceState(null, "", target.toString());
      } else {
        const created = await createInterviewSession(qCandidateId, qJobId);
        const started = await startInterviewSession(created.id);
        session.value = started;
        activeSessionId = started.id;
        const target = new URL(window.location.href);
        target.searchParams.set("session_id", activeSessionId);
        target.searchParams.set("candidate_id", started.candidate_id);
        target.searchParams.set("job_id", started.job_id);
        window.history.replaceState(null, "", target.toString());
      }
    }

    if (!session.value && activeSessionId) {
      const report = await loadInterviewReport(activeSessionId);
      reportSummary.value = report.summary || "";
      session.value = {
        id: report.session_id,
        candidate_id: qCandidateId || "candidate",
        job_id: qJobId || "job",
        status: "in_progress",
        rtc_room_id: "",
        join_token: "",
        join_url: "",
        payload: {}
      };
    }

    if (session.value) {
      connectRealtimeBus(session.value.id);
      connectDuplexSocket(session.value.id);
      // UI should be interactive once session and sockets are ready.
      loading.value = false;
      // Run question generation / initial TTS in background to avoid blocking first paint.
      void (async () => {
        try {
          const questions = await generateQuestionSet(session.value!.id);
          if (questions[0]?.question) {
            currentQuestion.value = questions[0].question;
          }
          if (questions[1]?.question) {
            followupQuestion.value = questions[1].question;
          }
          await refreshReplay();
          ttsStatus.value = "播报中...";
          const firstTts = await streamTTS(session.value!.id, currentQuestion.value);
          await playAudioDataUris(firstTts.audio_uris || []);
          ttsStatus.value = "已播报";
        } catch (err) {
          errorText.value = err instanceof Error ? err.message : "初始化问答失败";
          ttsStatus.value = "待播报";
        }
      })();
    }
  } catch (err) {
    errorText.value = err instanceof Error ? err.message : "页面初始化失败";
  } finally {
    loading.value = false;
  }
}

async function refreshReplay(): Promise<void> {
  if (!session.value) {
    return;
  }
  transcriptItems.value = await loadReplayItems(session.value.id);
}

async function exitMeeting(): Promise<void> {
  if (!session.value || exiting.value) {
    return;
  }
  try {
    exiting.value = true;
    await finishInterviewSession(session.value.id);
    window.location.href = "/?left=1";
  } catch (err) {
    errorText.value = err instanceof Error ? err.message : "退出失败";
    exiting.value = false;
  }
}

function stopAudioPipeline(): void {
  if (analyzeTimer != null) {
    window.clearInterval(analyzeTimer);
    analyzeTimer = null;
  }
  if (workletNode) {
    workletNode.disconnect();
    workletNode.port.onmessage = null;
    workletNode = null;
  }
  if (sourceNode) {
    sourceNode.disconnect();
    sourceNode = null;
  }
  if (audioContext) {
    void audioContext.close();
    audioContext = null;
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }
  frameWindow.length = 0;
  frameWindowSamples = 0;
  frameWindowEnergy = 0;
  noiseFloor = 0.0018;
  adaptiveThreshold = ENERGY_THRESHOLD;
  ttsQueue.length = 0;
  ttsPlaying = false;
  for (const frameId of Array.from(pendingFrames.keys())) {
    clearPendingFrame(frameId);
  }
  resetSentenceBuffer();
}

onMounted(async () => {
  await bootstrap();
  if (!errorText.value) {
    await startMicPipeline();
  }
  replayTimer = window.setInterval(() => {
    if (!wsConnected) {
      void refreshReplay();
    }
  }, 8000);
  tickerTimer = window.setInterval(() => {
    elapsedSeconds.value += 1;
  }, 1000);
});

onBeforeUnmount(() => {
  if (replayTimer != null) {
    window.clearInterval(replayTimer);
  }
  if (tickerTimer != null) {
    window.clearInterval(tickerTimer);
  }
  if (wsReconnectTimer != null) {
    window.clearTimeout(wsReconnectTimer);
  }
  if (duplexReconnectTimer != null) {
    window.clearTimeout(duplexReconnectTimer);
  }
  if (sessionSocket) {
    sessionSocket.close();
    sessionSocket = null;
  }
  if (duplexSocket) {
    duplexSocket.close();
    duplexSocket = null;
  }
  stopAudioPipeline();
});
</script>

<template>
  <div class="meeting-shell">
    <header class="meeting-topbar">
      <div class="topbar-left">
        <div class="brand">
          <span class="brand-mark"></span>
          <span class="brand-text">面试会议</span>
        </div>
        <span class="meeting-time">{{ meetingTimeText }}</span>
        <div class="signal-bars" aria-label="网络良好">
          <span v-for="n in 4" :key="n" :class="['bar', `h${n}`]"></span>
        </div>
      </div>
      <div class="topbar-center">
        <div class="notice">
          <span>面试官正在提问，请直接作答</span>
        </div>
      </div>
      <div class="topbar-right">
        <button class="ghost-btn">宫格布局</button>
        <button class="ghost-btn">设置</button>
        <button class="exit-btn" :disabled="exiting" @click="exitMeeting">
          {{ exiting ? "正在退出..." : "退出面试" }}
        </button>
      </div>
    </header>

    <main class="meeting-main">
      <section v-if="loading" class="loading-view">正在连接面试会话...</section>
      <section v-else-if="errorText" class="loading-view error">{{ errorText }}</section>
      <template v-else>
        <section class="stage-area">
          <div class="stage-overlay-card">
            <div class="avatar-ring">
              <div class="avatar"></div>
            </div>
            <p class="candidate-name">候选人</p>
            <p class="candidate-state">请自然作答，系统将自动记录面试内容。</p>
            <p class="candidate-status-line">麦克风：{{ micStatus }} | 播报：{{ ttsStatus }}</p>
          </div>
          <div class="interviewer-mini-card">
            <div class="interviewer-avatar"></div>
            <div>
              <p class="interviewer-title">面试官</p>
              <p class="interviewer-status">正在聆听</p>
            </div>
          </div>
        </section>

        <aside class="session-sidebar">
          <div class="sidebar-block">
            <p class="block-title">当前问题</p>
            <p class="block-content">{{ currentQuestion }}</p>
          </div>
          <div class="sidebar-block">
            <p class="block-title">补充提问</p>
            <p class="block-content">{{ followupQuestion }}</p>
          </div>
          <div class="sidebar-block transcript">
            <div class="block-header-inline">
              <p class="block-title">实时字幕</p>
              <span class="live-dot">实时</span>
            </div>
            <ul class="transcript-list">
              <li v-if="partialHint">
                <span class="who">系统</span>
                <span>{{ partialHint }}</span>
              </li>
              <li v-for="(line, idx) in transcriptView" :key="`${idx}-${line}`">
                <span class="who">你</span>
                <span>{{ line }}</span>
              </li>
              <li v-if="!partialHint && transcriptView.length === 0">
                <span class="who">系统</span>
                <span>正在等待你的回答...</span>
              </li>
            </ul>
          </div>
          <div class="sidebar-block" v-if="reportSummary">
            <p class="block-title">会话摘要</p>
            <p class="block-content">{{ reportSummary }}</p>
          </div>
        </aside>
      </template>
    </main>

    <footer class="meeting-footer">
      <div class="footer-tip">实时链路：AudioWorklet + 句级提交 + WebSocket 事件总线</div>
      <nav class="footer-actions">
        <button class="footer-action">成员(1)</button>
        <button class="footer-action">聊天</button>
        <button class="footer-action">纪要</button>
        <button class="footer-action">应用</button>
      </nav>
    </footer>
  </div>
</template>
