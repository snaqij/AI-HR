export interface InterviewSession {
  id: string;
  candidate_id: string;
  job_id: string;
  status: string;
  rtc_room_id: string;
  join_token: string;
  join_url: string;
  payload: Record<string, unknown>;
}

export interface ReplayItem {
  turn_id: string;
  turn_no: number;
  speaker: string;
  transcript: string | null;
  occurred_at: string;
}

export interface ASRStreamResponse {
  transcript: string;
  confidence: number;
  latency_ms: number;
  turn_id: string | null;
  event_id: string | null;
  realtime_target_met: boolean;
}

export interface EventAppendResponse {
  followup_question: string | null;
  followup_audio_uris: string[];
  accepted: boolean;
  deduplicated: boolean;
}

export interface TTSStreamResponse {
  chunks: string[];
  audio_uris: string[];
  published: boolean;
}

export interface InterviewRealtimeEvent {
  event_type: string;
  session_id: string;
  ts?: number;
  payload?: Record<string, unknown>;
}

interface Envelope<T> {
  data: T;
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || "http://127.0.0.1:8000/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {})
    }
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  const payload = (await res.json()) as Envelope<T>;
  return payload.data;
}

export function buildInterviewEventsWsUrl(sessionId: string): string {
  const asUrl = new URL(API_BASE_URL);
  asUrl.protocol = asUrl.protocol === "https:" ? "wss:" : "ws:";
  const basePath = asUrl.pathname.replace(/\/$/, "");
  asUrl.pathname = `${basePath}/ai/interviews/sessions/${sessionId}/events/ws`;
  return asUrl.toString();
}

export function buildInterviewDuplexWsUrl(sessionId: string): string {
  const asUrl = new URL(API_BASE_URL);
  asUrl.protocol = asUrl.protocol === "https:" ? "wss:" : "ws:";
  const basePath = asUrl.pathname.replace(/\/$/, "");
  asUrl.pathname = `${basePath}/ai/interviews/sessions/${sessionId}/rtc/duplex/ws`;
  return asUrl.toString();
}

export function buildRtcAsrIngestWsUrl(): string {
  const asUrl = new URL(API_BASE_URL);
  asUrl.protocol = asUrl.protocol === "https:" ? "wss:" : "ws:";
  const basePath = asUrl.pathname.replace(/\/$/, "");
  asUrl.pathname = `${basePath}/ai/interviews/rtc/asr/ingest/ws`;
  return asUrl.toString();
}

export async function createInterviewSession(candidateId: string, jobId: string): Promise<InterviewSession> {
  const data = await request<{ session: InterviewSession }>("/ai/interviews/sessions", {
    method: "POST",
    body: JSON.stringify({ candidate_id: candidateId, job_id: jobId })
  });
  return data.session;
}

async function createDemoJob(): Promise<string> {
  const data = await request<{ id: string }>("/jobs", {
    method: "POST",
    body: JSON.stringify({
      title: "后端开发工程师（演示）",
      department: "研发中心",
      city: "上海",
      salary_range: "30k-45k",
      requirements: "熟悉 Python、FastAPI、MySQL、分布式系统。"
    })
  });
  return data.id;
}

async function createDemoCandidate(): Promise<string> {
  const extId = `fe-demo-${Date.now()}`;
  const data = await request<{ candidates: Array<{ id: string }> }>("/candidates/import", {
    method: "POST",
    body: JSON.stringify({
      candidates: [
        {
          name: "候选人",
          source_channel: "self_hosted",
          external_candidate_id: extId,
          resume_text: "5年后端开发经验，负责过高并发服务治理和性能优化。",
          raw_profile: { skills: ["Python", "FastAPI", "MySQL", "Redis"] }
        }
      ]
    })
  });
  return data.candidates[0].id;
}

export async function bootstrapDemoSession(): Promise<InterviewSession> {
  const jobId = await createDemoJob();
  const candidateId = await createDemoCandidate();
  const created = await createInterviewSession(candidateId, jobId);
  return startInterviewSession(created.id);
}

export async function startInterviewSession(sessionId: string): Promise<InterviewSession> {
  return request<InterviewSession>(`/ai/interviews/sessions/${sessionId}/start`, {
    method: "POST",
    body: JSON.stringify({ operator: "candidate_web" })
  });
}

export async function loadInterviewReport(sessionId: string): Promise<{
  session_id: string;
  summary: string;
  runtime_mode: string;
  recommendation: string;
}> {
  return request(`/ai/interviews/sessions/${sessionId}/report`);
}

export async function generateQuestionSet(sessionId: string): Promise<Array<{ question: string }>> {
  const data = await request<{ questions: Array<{ question: string }> }>(
    `/ai/interviews/sessions/${sessionId}/question-set/generate`,
    {
      method: "POST",
      body: JSON.stringify({
        question_count: 6,
        source: "resume+jd",
        force_regenerate: false
      })
    }
  );
  return data.questions || [];
}

export async function loadReplayItems(sessionId: string): Promise<ReplayItem[]> {
  const data = await request<{ items: ReplayItem[] }>(`/ai/interviews/sessions/${sessionId}/replay?limit=200&offset=0`);
  return data.items || [];
}

export async function finishInterviewSession(sessionId: string): Promise<InterviewSession> {
  return request<InterviewSession>(`/ai/interviews/sessions/${sessionId}/finish`, {
    method: "POST",
    body: JSON.stringify({
      result_status: "completed",
      operator: "candidate_web",
      note: "candidate_exit"
    })
  });
}

export async function streamASR(
  sessionId: string,
  payload: { seq: number; audioBase64: string; textHint?: string; chunkIndex?: number; chunkTotal?: number; isFinal?: boolean }
): Promise<ASRStreamResponse> {
  return request<ASRStreamResponse>(`/ai/interviews/sessions/${sessionId}/rtc/asr/stream`, {
    method: "POST",
    body: JSON.stringify({
      seq: payload.seq,
      text_hint: payload.textHint || "",
      audio_base64: payload.audioBase64,
      confidence: 0.9,
      latency_ms: 320,
      chunk_index: payload.chunkIndex || 1,
      chunk_total: payload.chunkTotal || 1,
      is_final: payload.isFinal ?? true,
      input_format: "wav",
      target_latency_ms: 700
    })
  });
}

export async function appendCandidateEvent(
  sessionId: string,
  payload: { seq: number; transcript: string; eventId: string }
): Promise<EventAppendResponse> {
  return request<EventAppendResponse>(`/ai/interviews/sessions/${sessionId}/events`, {
    method: "POST",
    body: JSON.stringify({
      event_id: payload.eventId,
      seq: payload.seq,
      speaker: "candidate",
      transcript: payload.transcript,
      confidence: 0.9,
      latency_ms: 320,
      policy_flags: []
    })
  });
}

export async function streamTTS(sessionId: string, text: string): Promise<TTSStreamResponse> {
  return request<TTSStreamResponse>(`/ai/interviews/sessions/${sessionId}/rtc/tts/stream`, {
    method: "POST",
    body: JSON.stringify({
      text,
      voice: "default",
      chunk_size: 24,
      publish_to_rtc: false,
      target_latency_ms: 1200
    })
  });
}
