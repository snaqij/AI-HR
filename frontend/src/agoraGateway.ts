export interface AgoraJoinParams {
  appId: string;
  channel: string;
  token: string;
  uid: number;
}

interface IAgoraRTCRemoteAudioTrack {
  play(): void;
  stop(): void;
}

interface IAgoraRTCLocalAudioTrack {
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
  publish(tracks: IAgoraRTCLocalAudioTrack[]): Promise<void>;
  subscribe(user: IAgoraRTCRemoteUser, mediaType: "audio" | "video"): Promise<void>;
}

interface AgoraRTCSDK {
  createClient(config: { mode: "rtc"; codec: "vp8" | "h264" }): IAgoraRTCClient;
  createMicrophoneAudioTrack(): Promise<IAgoraRTCLocalAudioTrack>;
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
}

const AGORA_WEB_SDK_URL =
  (import.meta.env.VITE_AGORA_WEB_SDK_URL as string | undefined)?.trim() ||
  "https://download.agora.io/sdk/release/AgoraRTC_N.js";

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
      user.audioTrack?.play();
      this.callbacks.onRemoteAudioSubscribed?.(String(user.uid));
    });

    client.on("user-unpublished", (user, mediaType) => {
      if (mediaType !== "audio") {
        return;
      }
      user.audioTrack?.stop();
      this.callbacks.onRemoteAudioUnsubscribed?.(String(user.uid));
    });

    client.on("connection-state-change", (state, _prevState, reason) => {
      this.callbacks.onConnectionStateChanged?.(state, reason);
    });

    const uid = toNumericUid(params.uid);
    await client.join(params.appId, params.channel, params.token || null, uid);
    const localAudioTrack = await AgoraRTC.createMicrophoneAudioTrack();
    await client.publish([localAudioTrack]);

    this.client = client;
    this.localAudioTrack = localAudioTrack;
  }

  async setMicrophoneEnabled(enabled: boolean): Promise<void> {
    if (!this.localAudioTrack) {
      return;
    }
    await this.localAudioTrack.setEnabled(enabled);
  }

  async disconnect(): Promise<void> {
    try {
      this.localAudioTrack?.close();
      this.localAudioTrack = null;
      if (this.client) {
        await this.client.leave();
      }
    } finally {
      this.client = null;
    }
  }
}
