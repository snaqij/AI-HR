export interface InterviewRTCInfo {
  provider: string;
  transport: string;
  room_id: string;
  channel_name: string;
  token: string;
  app_id: string | null;
  uid: string | null;
  expire_at: string | null;
}

export interface InterviewTENInfo {
  enabled: boolean;
  room_id: string;
  agent_user_id: string | null;
  remote_user_id: string | null;
  property_file: string | null;
  launch_status: string;
  launch_command: string | null;
}

export interface InterviewSession {
  id: string;
  candidate_id: string;
  job_id: string;
  status: string;
  channel: string;
  language: string;
  rtc_room_id: string;
  join_token: string;
  join_url: string;
  rtc: InterviewRTCInfo;
  ten: InterviewTENInfo;
  payload: Record<string, unknown>;
}

export interface InterviewRTCJoinResponse {
  session_id: string;
  provider: string;
  room_id: string;
  channel_name: string;
  join_token: string;
  app_id: string | null;
  uid: string | null;
  expire_at: string | null;
  reconnectable: boolean;
  transport: string;
}

export interface InterviewTENRuntimeResponse {
  session_id: string;
  enabled: boolean;
  room_id: string;
  provider: string;
  app_id: string | null;
  channel_name: string | null;
  agent_user_id: string | null;
  remote_user_id: string | null;
  property_file: string | null;
  launch_status: string;
  launch_command: string | null;
  process_pid: number | null;
}

export interface ReplayItem {
  turn_id: string;
  turn_no: number;
  speaker: string;
  transcript: string | null;
  occurred_at: string;
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

export async function createInterviewSession(candidateId: string, jobId: string): Promise<InterviewSession> {
  const data = await request<{ session: InterviewSession }>("/ai/interviews/sessions", {
    method: "POST",
    body: JSON.stringify({
      candidate_id: candidateId,
      job_id: jobId,
      channel: "agora_web",
      language: "zh-CN",
      payload: {
        source: "web_frontend",
        rtc_strategy: "agora_ten"
      }
    })
  });
  return data.session;
}

export async function getInterviewSession(sessionId: string): Promise<InterviewSession> {
  return request<InterviewSession>(`/ai/interviews/sessions/${sessionId}`);
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
  return createInterviewSession(candidateId, jobId);
}

export async function startInterviewSession(sessionId: string): Promise<InterviewSession> {
  return request<InterviewSession>(`/ai/interviews/sessions/${sessionId}/start`, {
    method: "POST",
    body: JSON.stringify({ operator: "candidate_web" })
  });
}

export async function joinInterviewRTC(sessionId: string, candidateId: string, clientId = "agora-web"): Promise<InterviewRTCJoinResponse> {
  return request<InterviewRTCJoinResponse>(`/ai/interviews/sessions/${sessionId}/rtc/join`, {
    method: "POST",
    body: JSON.stringify({
      candidate_id: candidateId,
      client_id: clientId
    })
  });
}

export async function getTenRuntimeConfig(sessionId: string): Promise<InterviewTENRuntimeResponse> {
  return request<InterviewTENRuntimeResponse>(`/ai/interviews/sessions/${sessionId}/ten/runtime-config`);
}

export async function launchTenSession(sessionId: string): Promise<InterviewTENRuntimeResponse> {
  return request<InterviewTENRuntimeResponse>(`/ai/interviews/sessions/${sessionId}/ten/launch`, {
    method: "POST",
    body: JSON.stringify({})
  });
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
