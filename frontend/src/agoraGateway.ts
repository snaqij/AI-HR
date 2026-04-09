export interface AgoraJoinParams {
  appId: string;
  channel: string;
  token: string;
  uid: number;
}

interface IAgoraRTCRemoteAudioTrack {
  play(): void | Promise<void>;
  stop(): void;
  getVolumeLevel?(): number;
  getCurrentLevel?(): number;
}

interface AgoraCameraTrackInitConfig {
  encoderConfig?:
    | string
    | {
        width?: number;
        height?: number;
        frameRate?: number;
        bitrateMin?: number;
        bitrateMax?: number;
      };
  optimizationMode?: "detail" | "motion" | string;
}

interface IAgoraRTCLocalAudioTrack {
  setEnabled(enabled: boolean): Promise<void>;
  close(): void;
}

interface IAgoraRTCLocalVideoTrack {
  play(element: string | HTMLElement): void;
  stop(): void;
  setEnabled(enabled: boolean): Promise<void>;
  close(): void;
}

interface IAgoraRTCRemoteUser {
  uid: string | number;
  audioTrack?: IAgoraRTCRemoteAudioTrack;
}

interface IAgoraRTCClient {
  on(event: "user-published", listener: (user: IAgoraRTCRemoteUser, mediaType: "audio" | "video") => void): void;
  on(event: "user-unpublished", listener: (user: IAgoraRTCRemoteUser, mediaType: "audio" | "video") => void): void;
  on(event: "connection-state-change", listener: (curState: string, revState: string, reason?: string) => void): void;
  join(appId: string, channel: string, token: string | null, uid: number | null): Promise<number>;
  leave(): Promise<void>;
  publish(tracks: Array<IAgoraRTCLocalAudioTrack | IAgoraRTCLocalVideoTrack>): Promise<void>;
  subscribe(user: IAgoraRTCRemoteUser, mediaType: "audio" | "video"): Promise<void>;
}

interface AgoraRTCSDK {
  createClient(config: { mode: "rtc"; codec: "vp8" | "h264" }): IAgoraRTCClient;
  createMicrophoneAudioTrack(): Promise<IAgoraRTCLocalAudioTrack>;
  createCameraVideoTrack(config?: AgoraCameraTrackInitConfig): Promise<IAgoraRTCLocalVideoTrack>;
}

declare global {
  interface Window {
    AgoraRTC?: AgoraRTCSDK;
  }
}

export interface AgoraGatewayCallbacks {
  onRemoteAudioSubscribed?: (uid: string) => void;
  onRemoteAudioUnsubscribed?: (uid: string) => void;
  onConnectionStateChanged?: (state: string, reason?: string) => void;
  onRemoteAudioSpeakingChanged?: (speaking: boolean) => void;
  onRemoteAudioPlaybackError?: (message: string) => void;
}

const AGORA_WEB_SDK_URL =
  (import.meta.env.VITE_AGORA_WEB_SDK_URL as string | undefined)?.trim() ||
  "https://download.agora.io/sdk/release/AgoraRTC_N.js";

const DEFAULT_CAMERA_TRACK_CONFIG: AgoraCameraTrackInitConfig = {
  encoderConfig: {
    width: 1280,
    height: 720,
    frameRate: 24,
    bitrateMin: 1200,
    bitrateMax: 2200
  },
  optimizationMode: "detail"
};

function toNumericUid(value: string | number | null | undefined): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  const parsed = Number(value);
  if (Number.isFinite(parsed) && parsed > 0) {
    return parsed;
  }
  throw new Error(`Invalid Agora uid: ${String(value)}`);
}

async function ensureAgoraSdkLoaded(): Promise<AgoraRTCSDK> {
  if (window.AgoraRTC) {
    return window.AgoraRTC;
  }
  await new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>("script[data-agora-sdk='true']");
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error("Failed to load Agora Web SDK")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.src = AGORA_WEB_SDK_URL;
    script.async = true;
    script.dataset.agoraSdk = "true";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Agora Web SDK"));
    document.head.appendChild(script);
  });

  if (!window.AgoraRTC) {
    throw new Error("Agora Web SDK loaded but window.AgoraRTC is unavailable");
  }
  return window.AgoraRTC;
}

export class AgoraRTCGateway {
  private client: IAgoraRTCClient | null = null;
  private localAudioTrack: IAgoraRTCLocalAudioTrack | null = null;
  private localVideoTrack: IAgoraRTCLocalVideoTrack | null = null;
  private remoteAudioTrack: IAgoraRTCRemoteAudioTrack | null = null;
  private remoteAudioLevelTimer: number | null = null;
  private remoteSpeaking = false;
  private callbacks: AgoraGatewayCallbacks;

  constructor(callbacks: AgoraGatewayCallbacks = {}) {
    this.callbacks = callbacks;
  }

  async connect(params: AgoraJoinParams): Promise<void> {
    const AgoraRTC = await ensureAgoraSdkLoaded();
    const client = AgoraRTC.createClient({ mode: "rtc", codec: "vp8" });

    client.on("user-published", async (user, mediaType) => {
      if (mediaType !== "audio") {
        return;
      }
      await client.subscribe(user, "audio");
      this.remoteAudioTrack = user.audioTrack || null;
      await this.playRemoteAudio();
      this.startRemoteAudioLevelMonitor();
      this.callbacks.onRemoteAudioSubscribed?.(String(user.uid));
    });

    client.on("user-unpublished", (user, mediaType) => {
      if (mediaType !== "audio") {
        return;
      }
      user.audioTrack?.stop();
      this.remoteAudioTrack = null;
      this.stopRemoteAudioLevelMonitor();
      this.callbacks.onRemoteAudioUnsubscribed?.(String(user.uid));
    });

    client.on("connection-state-change", (state, _prevState, reason) => {
      this.callbacks.onConnectionStateChanged?.(state, reason);
    });

    const uid = toNumericUid(params.uid);
    await client.join(params.appId, params.channel, params.token || null, uid);
    const localAudioTrack = await AgoraRTC.createMicrophoneAudioTrack();
    const localVideoTrack = await AgoraRTC.createCameraVideoTrack(DEFAULT_CAMERA_TRACK_CONFIG);
    await client.publish([localAudioTrack, localVideoTrack]);

    this.client = client;
    this.localAudioTrack = localAudioTrack;
    this.localVideoTrack = localVideoTrack;
  }

  async setMicrophoneEnabled(enabled: boolean): Promise<void> {
    if (!this.localAudioTrack) {
      return;
    }
    await this.localAudioTrack.setEnabled(enabled);
  }

  async setCameraEnabled(enabled: boolean): Promise<void> {
    if (!this.localVideoTrack) {
      return;
    }
    await this.localVideoTrack.setEnabled(enabled);
  }

  playLocalVideo(element: HTMLElement): void {
    if (!this.localVideoTrack) {
      return;
    }
    this.localVideoTrack.play(element);
  }

  stopLocalVideo(): void {
    this.localVideoTrack?.stop();
  }

  async resumeRemoteAudioPlayback(): Promise<void> {
    await this.playRemoteAudio();
  }

  private readRemoteAudioLevel(): number {
    if (!this.remoteAudioTrack) {
      return 0;
    }
    if (typeof this.remoteAudioTrack.getVolumeLevel === "function") {
      return Number(this.remoteAudioTrack.getVolumeLevel()) || 0;
    }
    if (typeof this.remoteAudioTrack.getCurrentLevel === "function") {
      return Number(this.remoteAudioTrack.getCurrentLevel()) || 0;
    }
    return 0;
  }

  private async playRemoteAudio(): Promise<void> {
    if (!this.remoteAudioTrack) {
      return;
    }
    try {
      await Promise.resolve(this.remoteAudioTrack.play());
    } catch (error) {
      const message = error instanceof Error ? error.message : "浏览器阻止了远端音频自动播放";
      this.callbacks.onRemoteAudioPlaybackError?.(message);
    }
  }

  private startRemoteAudioLevelMonitor(): void {
    this.stopRemoteAudioLevelMonitor();
    this.remoteAudioLevelTimer = window.setInterval(() => {
      const speaking = this.readRemoteAudioLevel() > 0.05;
      if (speaking === this.remoteSpeaking) {
        return;
      }
      this.remoteSpeaking = speaking;
      this.callbacks.onRemoteAudioSpeakingChanged?.(speaking);
    }, 180);
  }

  private stopRemoteAudioLevelMonitor(): void {
    if (this.remoteAudioLevelTimer != null) {
      window.clearInterval(this.remoteAudioLevelTimer);
      this.remoteAudioLevelTimer = null;
    }
    if (this.remoteSpeaking) {
      this.remoteSpeaking = false;
      this.callbacks.onRemoteAudioSpeakingChanged?.(false);
    }
  }

  async disconnect(): Promise<void> {
    try {
      this.stopRemoteAudioLevelMonitor();
      this.localAudioTrack?.close();
      this.localVideoTrack?.stop();
      this.localVideoTrack?.close();
      this.remoteAudioTrack = null;
      this.localAudioTrack = null;
      this.localVideoTrack = null;
      if (this.client) {
        await this.client.leave();
      }
    } finally {
      this.client = null;
    }
  }
}
