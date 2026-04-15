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

export interface InterviewRTCJoinInfo {
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

export interface InterviewTENRuntimeConfig {
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
  transcript?: string | null;
  audio_uri?: string | null;
  confidence?: number | null;
  latency_ms?: number | null;
  policy_flags?: string[];
  occurred_at?: string | null;
}

export interface InterviewRealtimeEvent {
  event_type: string;
  session_id?: string;
  payload?: Record<string, any>;
}

export interface Job {
  id: string;
  title: string;
  department: string | null;
  city: string;
  salary_range: string | null;
  requirements: string;
  status: string;
  created_at: string;
  published_at: string | null;
  candidate_count?: number;
  
  // Automation Settings
  auto_request_resume?: boolean;
  min_degree?: string | null;
  min_experience_years?: number | null;
  max_daily_resume_requests?: number;
}

export interface Candidate {
  id: string;
  name: string;
  email?: string | null;
  email_hash?: string;
  current_stage: string;
  school?: string | null;
  degree?: string | null;
  work_experience?: string | null;
  latest_company?: string | null;
  expected_salary?: string | null;
  score_total?: number | null;
  score_explanation?: string | null;
  raw_profile?: Record<string, unknown>;
  created_at: string;
}

export interface JobCandidate {
  candidate: Candidate;
  channel: string;
  stage: string;
  applied_at?: string | null;
  first_synced_at: string;
  last_synced_at: string;
  source_payload: any;

  // Pipeline Status
  resume_request_status?: string | null;
  resume_download_status?: string | null;
  last_resume_requested_at?: string | null;
  
  external_candidate_id: string;
  external_job_id?: string | null;
  source_status?: string;
}

export interface JobCandidateListResult {
  job_id: string;
  total: number;
  evaluated_count: number;
  sent_count: number;
  limit: number;
  next_cursor?: string | null;
  has_more: boolean;
  candidates: JobCandidate[];
}

export interface CandidateEvaluation {
  id: string;
  candidate_id: string;
  job_id: string;
  resume_attachment_id?: string | null;
  evaluation_version: string;
  source: string;
  status: string;
  match_score: number;
  competitiveness_score: number;
  final_score: number;
  confidence_score?: number | null;
  recommendation: string;
  summary?: string | null;
  dimension_scores: Record<string, number>;
  strengths: string[];
  weaknesses: string[];
  highlights: string[];
  risk_flags: string[];
  job_requirement_coverage: Record<string, string>;
  raw_llm_output?: Record<string, unknown> | null;
  invited_flag: boolean;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  evaluated_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CandidateEvaluationListItem {
  candidate: Candidate;
  evaluation: CandidateEvaluation;
}

export interface JobEvaluationListResult {
  job_id: string;
  total: number;
  items: CandidateEvaluationListItem[];
}

export interface CandidateEvaluationDetailResult {
  candidate: Candidate;
  evaluation: CandidateEvaluation;
  pipeline_status: Record<string, unknown>;
}

export interface CandidateEvaluationUpdatePayload {
  recommendation?: string;
  summary?: string;
  strengths?: string[];
  weaknesses?: string[];
  highlights?: string[];
  risk_flags?: string[];
  reviewed_by?: string;
}

export interface CandidateEmailDelivery {
  id: string;
  candidate_id: string;
  job_id: string;
  evaluation_id?: string | null;
  invitation_id?: string | null;
  template_code: string;
  scene: string;
  to_email: string;
  subject: string;
  provider?: string | null;
  provider_message_id?: string | null;
  status: string;
  retry_count: number;
  max_retry_count: number;
  last_error?: string | null;
  sent_at?: string | null;
  delivered_at?: string | null;
  opened_at?: string | null;
  clicked_at?: string | null;
  payload?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface CandidateEmailDeliveryListResult {
  job_id: string;
  total: number;
  items: CandidateEmailDelivery[];
}

export interface InterviewInvitationEmailSendPayload {
  evaluation_id?: string | null;
  template_code?: string | null;
  note?: string | null;
}

export interface InterviewInvitationEmailSendResult {
  candidate_id: string;
  job_id: string;
  evaluation_id: string;
  delivery_id: string;
  invitation_id: string;
  to_email: string;
  status: string;
  invitation_link: string;
}

export interface DashboardAnalytics {
  funnel: Array<{
    label: string,
    value: number,
    growth: number,
    height: string,
    opacity: number,
    conversion?: string
  }>;
  efficiency: Array<{
    label: string,
    value: string,
    unit: string,
    progress: number
  }>;
  total_synced: number;
}

export interface CredentialStatus {
  id: string;
  channel: string;
  account_name: string;
  status: string;
  is_active: boolean;
  last_failure_at?: string | null;
  failure_count: number;
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

// Credentials
export async function fetchBossCredential(): Promise<CredentialStatus> {
  return request<CredentialStatus>("/credentials/boss");
}

export async function updateBossCredential(cookie: string): Promise<any> {
  return request("/credentials/boss", {
    method: "POST",
    body: JSON.stringify({ cookie_header: cookie })
  });
}

// Analytics
export async function fetchDashboardAnalytics(): Promise<DashboardAnalytics> {
  return request<DashboardAnalytics>("/analytics/dashboard");
}

// Jobs
export async function listJobs(limit = 100): Promise<Job[]> {
  const res = await request<{ items: Job[] }>(`/jobs?limit=${limit}`);
  return res.items;
}

export async function getJob(jobId: string): Promise<Job> {
  return request<Job>(`/jobs/${jobId}`);
}

export async function updateJobSettings(jobId: string, settings: Partial<Job>): Promise<Job> {
  return request<Job>(`/jobs/${jobId}/settings`, {
    method: "PATCH",
    body: JSON.stringify(settings)
  });
}

export async function syncJobCandidates(jobId: string): Promise<any> {
  return request(`/jobs/${jobId}/candidates/sync`, {
    method: "POST",
    body: JSON.stringify({ max_pages: 5 })
  });
}

// Candidates
export async function listJobCandidates(
  jobId: string,
  payload: { limit?: number; cursor?: string } = {}
): Promise<JobCandidateListResult> {
  const params = new URLSearchParams();
  if (payload.limit) {
    params.set("limit", String(payload.limit));
  }
  if (payload.cursor) {
    params.set("cursor", payload.cursor);
  }
  const qs = params.toString();
  return request<JobCandidateListResult>(`/jobs/${jobId}/candidates${qs ? `?${qs}` : ""}`);
}

export async function getJobCandidate(jobId: string, candidateId: string): Promise<JobCandidate> {
  return request<JobCandidate>(`/jobs/${jobId}/candidates/${candidateId}`);
}

export async function fetchJobEvaluations(
  jobId: string,
  payload: { limit?: number; candidateIds?: string[] } = {}
): Promise<JobEvaluationListResult> {
  const params = new URLSearchParams();
  params.set("limit", String(payload.limit ?? 200));
  params.set("offset", "0");
  if (payload.candidateIds?.length) {
    params.set("candidate_ids", payload.candidateIds.join(","));
  }
  return request<JobEvaluationListResult>(`/jobs/${jobId}/evaluations?${params.toString()}`);
}

export async function evaluateJobCandidate(
  jobId: string,
  candidateId: string,
  payload: { evaluation_version?: string; force_refresh?: boolean } = {}
): Promise<CandidateEvaluationDetailResult> {
  return request<CandidateEvaluationDetailResult>(`/jobs/${jobId}/candidates/${candidateId}/evaluate`, {
    method: "POST",
    body: JSON.stringify({
      evaluation_version: payload.evaluation_version || "v1",
      force_refresh: Boolean(payload.force_refresh),
    })
  });
}

export async function fetchLatestJobCandidateEvaluation(
  jobId: string,
  candidateId: string
): Promise<CandidateEvaluationDetailResult> {
  return request<CandidateEvaluationDetailResult>(`/jobs/${jobId}/candidates/${candidateId}/evaluation-latest`);
}

export async function updateLatestJobCandidateEvaluation(
  jobId: string,
  candidateId: string,
  payload: CandidateEvaluationUpdatePayload
): Promise<CandidateEvaluationDetailResult> {
  return request<CandidateEvaluationDetailResult>(`/jobs/${jobId}/candidates/${candidateId}/evaluation-latest`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function sendCandidateInvitationEmail(
  jobId: string,
  candidateId: string,
  payload: InterviewInvitationEmailSendPayload = {}
): Promise<InterviewInvitationEmailSendResult> {
  return request<InterviewInvitationEmailSendResult>(`/jobs/${jobId}/candidates/${candidateId}/invite-email`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function fetchJobEmailDeliveries(
  jobId: string,
  candidateId?: string,
  limit = 200
): Promise<CandidateEmailDeliveryListResult> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (candidateId) {
    params.set("candidate_id", candidateId);
  }
  return request<CandidateEmailDeliveryListResult>(`/jobs/${jobId}/email-deliveries?${params.toString()}`);
}

export async function updateCandidateStage(jobId: string, candidateId: string, stage: string): Promise<JobCandidate> {
  return request<JobCandidate>(`/jobs/${jobId}/candidates/${candidateId}`, {
    method: "PATCH",
    body: JSON.stringify({ stage })
  });
}

export async function importRemoteJobs(channel = "boss", page = 1, pageSize = 20): Promise<any> {
  return request("/jobs/remote/import", {
    method: "POST",
    body: JSON.stringify({ channel, page, page_size: pageSize })
  });
}

export async function fetchJobShortlist(jobId: string): Promise<any> {
    return request(`/jobs/${jobId}/shortlist`);
}

// Interviews & Replay
export async function loadReplayItems(sessionId: string): Promise<any[]> {
  const data = await request<{ items: any[] }>(`/ai/interviews/sessions/${sessionId}/replay?limit=200&offset=0`);
  return data.items || [];
}

export async function createInterviewSession(candidateId: string, jobId: string): Promise<InterviewSession> {
  const data = await request<{ session: InterviewSession }>("/ai/interviews/sessions", {
    method: "POST",
    body: JSON.stringify({
      candidate_id: candidateId,
      job_id: jobId,
      channel: "agora_web",
      language: "zh-CN"
    })
  });
  return data.session;
}

export async function activateInterviewInvitation(token: string): Promise<InterviewSession> {
  return request<InterviewSession>(`/ai-interviews/invitations/token/${encodeURIComponent(token)}/activate`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export async function getInterviewSession(sessionId: string): Promise<InterviewSession> {
  return request<InterviewSession>(`/ai/interviews/sessions/${encodeURIComponent(sessionId)}`);
}

export async function startInterviewSession(sessionId: string, operator = "system"): Promise<InterviewSession> {
  return request<InterviewSession>(`/ai/interviews/sessions/${encodeURIComponent(sessionId)}/start`, {
    method: "POST",
    body: JSON.stringify({ operator })
  });
}

export async function finishInterviewSession(
  sessionId: string,
  payload: { result_status?: "completed" | "failed"; operator?: string; note?: string } = {}
): Promise<InterviewSession> {
  return request<InterviewSession>(`/ai/interviews/sessions/${encodeURIComponent(sessionId)}/finish`, {
    method: "POST",
    body: JSON.stringify({
      result_status: payload.result_status || "completed",
      operator: payload.operator || "system",
      note: payload.note || null,
    })
  });
}

export async function joinInterviewRTC(
  sessionId: string,
  candidateId: string,
  clientId = "web"
): Promise<InterviewRTCJoinInfo> {
  return request<InterviewRTCJoinInfo>(`/ai/interviews/sessions/${encodeURIComponent(sessionId)}/rtc/join`, {
    method: "POST",
    body: JSON.stringify({
      candidate_id: candidateId,
      client_id: clientId,
    }),
  });
}

export async function joinInterviewRTCPreflight(
  sessionId: string,
  candidateId: string,
  clientId = "web"
): Promise<InterviewRTCJoinInfo> {
  return joinInterviewRTC(sessionId, candidateId, clientId);
}

export async function getTenRuntimeConfig(sessionId: string): Promise<InterviewTENRuntimeConfig> {
  return request<InterviewTENRuntimeConfig>(`/ai/interviews/sessions/${encodeURIComponent(sessionId)}/ten/runtime-config`);
}

export async function launchTenSession(sessionId: string): Promise<InterviewTENRuntimeConfig> {
  return request<InterviewTENRuntimeConfig>(`/ai/interviews/sessions/${encodeURIComponent(sessionId)}/ten/launch`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function buildInterviewEventsWsUrl(sessionId: string): string {
  const apiUrl = new URL(API_BASE_URL);
  const protocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
  const wsPath = `${apiUrl.pathname.replace(/\/$/, "")}/ai/interviews/sessions/${encodeURIComponent(sessionId)}/events/ws`;
  return `${protocol}//${apiUrl.host}${wsPath}`;
}

export async function bootstrapDemoSession(): Promise<InterviewSession> {
  const jobs = await listJobs(20);
  if (!jobs.length) {
    throw new Error("No jobs found. Please create a job first.");
  }

  const targetJob = jobs[0];
  const candidateList = await listJobCandidates(targetJob.id, { limit: 20 });
  const targetCandidate = candidateList.candidates?.[0]?.candidate;
  if (!targetCandidate?.id) {
    throw new Error(`No candidates found for job ${targetJob.id}.`);
  }

  const session = await createInterviewSession(targetCandidate.id, targetJob.id);
  try {
    await startInterviewSession(session.id);
  } catch {
    // Session might already be started by invitation/runtime path.
  }
  return getInterviewSession(session.id);
}
