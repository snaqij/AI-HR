export interface Envelope<T> {
  ok: boolean;
  schema_version?: string;
  data: T;
  error?: {
    code: string;
    message: string;
  } | null;
}

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
  publications?: JobPublication[];
}

export interface JobPublication {
  id: string;
  channel: string;
  status: string;
  external_job_id?: string | null;
}

export interface JobsQuery {
  limit?: number;
  offset?: number;
  platform?: string;
  name?: string;
  job_type?: "intern" | "social";
  salary?: string;
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
  evaluation?: CandidateEvaluation | null;
  latest_delivery?: CandidateEmailDelivery | null;
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

export interface ResumeRiskItem {
  risk_code: string;
  risk_level: string;
  detail: string;
}

export interface ResumeProfilePayload {
  candidate_id: string;
  raw_text: string;
  parse_status: string;
  parser_version: string;
  confidence: number;
  parsed_profile: Record<string, any>;
  normalized_profile: Record<string, any>;
  risks: ResumeRiskItem[];
  created_at: string;
  updated_at: string;
}

export interface CandidateResumeProfileResult {
  profile: ResumeProfilePayload;
}

export interface ResumeAttachmentPayload {
  candidate_id: string;
  source_channel: string;
  external_candidate_id: string;
  file_name: string;
  content_type?: string | null;
  source_url?: string | null;
  file_size_bytes: number;
  file_sha256: string;
  object_storage_provider?: string | null;
  object_storage_bucket?: string | null;
  object_storage_key?: string | null;
  object_storage_url?: string | null;
  last_synced_at: string;
  created_at: string;
  updated_at: string;
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

export interface InterviewInvitationHistoryItem {
  id: string;
  workspace_id?: string | null;
  created_by_user_id?: string | null;
  candidate_id: string;
  candidate_name: string;
  candidate_email?: string | null;
  job_id: string;
  job_title: string;
  delivery_status: string;
  scene: string;
  sent_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface InterviewInvitationHistoryResult {
  total: number;
  items: InterviewInvitationHistoryItem[];
}

export interface InterviewQuestionAnswerItem {
  question_id: string;
  question: string;
  followup_questions?: string[];
  candidate_answer?: string | null;
  answer_turn_no?: number | null;
}

export interface InterviewOpeningSegmentItem {
  title: string;
  followup_questions?: string[];
  candidate_answer?: string | null;
  answer_turn_no?: number | null;
}

export interface InterviewAIAnalysis {
  summary?: string | null;
  recommendation?: string | null;
  dimension_scores: Record<string, number>;
  risk_tags: string[];
}

export interface InterviewInvitationRecordDetailResult {
  delivery_id: string;
  workspace_id?: string | null;
  created_by_user_id?: string | null;
  candidate_id: string;
  candidate_name: string;
  candidate_email?: string | null;
  job_id: string;
  job_title: string;
  delivery_status: string;
  invitation_id?: string | null;
  session_id?: string | null;
  has_record: boolean;
  record_message?: string | null;
  opening_segments: InterviewOpeningSegmentItem[];
  questions: InterviewQuestionAnswerItem[];
  analysis: InterviewAIAnalysis;
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
  daily_deltas: {
    open_jobs: number;
    total_candidates: number;
    pending_interviews: number;
    pending_invitations: number;
    monthly_hires: number;
  };
}

export interface HiringCenterEvaluationItem {
  candidate_id: string;
  candidate_name: string;
  avatar_url?: string | null;
  candidate_stage: string;
  candidate_expected_salary?: string | null;
  candidate_score_explanation?: string | null;
  job_id: string;
  job_title: string;
  job_salary_range?: string | null;
  evaluation_status: string;
  resume_score?: number | null;
  interview_score?: number | null;
  final_score: number;
  recommendation: string;
  summary?: string | null;
  highlights: string[];
  invited_flag: boolean;
  updated_at: string;
  created_at: string;
}

export interface HiringCenterOverviewResult {
  total: number;
  review_count: number;
  invited_count: number;
  recommended_count: number;
  conversion_rate: number;
  top_items: HiringCenterEvaluationItem[];
  queue_items: HiringCenterEvaluationItem[];
}

export interface HiringDecisionDimensionItem {
  key: string;
  label: string;
  score: number;
  max_score: number;
}

export interface HiringDecisionCandidateProfile {
  candidate_id: string;
  candidate_name: string;
  avatar_url?: string | null;
  phone?: string | null;
  email?: string | null;
  city?: string | null;
  degree?: string | null;
  work_experience?: string | null;
  current_role?: string | null;
  current_stage: string;
  expected_salary?: string | null;
  applied_at?: string | null;
  updated_at?: string | null;
  job_id: string;
  job_title: string;
  department?: string | null;
  job_city?: string | null;
  job_salary_range?: string | null;
}

export interface HiringDecisionOverview {
  resume_score: number;
  interview_score: number;
  composite_score: number;
  grade: string;
  recommendation: string;
  recommended_salary?: string | null;
  updated_at?: string | null;
}

export interface HiringDecisionAssessmentPanel {
  score: number;
  summary?: string | null;
  dimensions: HiringDecisionDimensionItem[];
  strengths: string[];
  weaknesses: string[];
  risk_tags: string[];
}

export interface HiringDecisionTimelineItem {
  step: string;
  time?: string | null;
  status?: string | null;
}

export interface HiringDecisionInterviewerReviewItem {
  reviewer: string;
  stage?: string | null;
  score?: number | null;
  time?: string | null;
  comment?: string | null;
}

export interface HiringDecisionQAItem {
  question: string;
  answer?: string | null;
  turn_no?: number | null;
  occurred_at?: string | null;
}

export interface HiringDecisionOperationLogItem {
  type: string;
  title: string;
  status?: string | null;
  time?: string | null;
  detail?: string | null;
}

export interface HiringDecisionDetailResult {
  profile: HiringDecisionCandidateProfile;
  overview: HiringDecisionOverview;
  resume_assessment: HiringDecisionAssessmentPanel;
  interview_assessment: HiringDecisionAssessmentPanel;
  composite_assessment: HiringDecisionAssessmentPanel;
  timeline: HiringDecisionTimelineItem[];
  interviewer_reviews: HiringDecisionInterviewerReviewItem[];
  qa_items: HiringDecisionQAItem[];
  operation_logs: HiringDecisionOperationLogItem[];
}

export interface CredentialStatus {
  id: string;
  channel: string;
  account_name: string;
  status: string;
  is_active: boolean;
  last_validated_at?: string | null;
  last_failure_at?: string | null;
  failure_count: number;
}

export interface AuthWorkspaceSummary {
  id: string;
  workspace_code: string;
  name: string;
  role: string;
  status: string;
}

export interface AuthSessionPayload {
  access_token: string;
  token_type: string;
  expires_in: number;
  workspace_id: string;
  workspaces: AuthWorkspaceSummary[];
}

export interface AuthRegisterRequest {
  email: string;
  verification_code: string;
  password: string;
  display_name: string;
  workspace_name?: string;
}

export interface AuthSendRegisterEmailCodeRequest {
  email: string;
}

export interface AuthSendRegisterEmailCodeResponse {
  email: string;
  expires_in: number;
  resend_cooldown_seconds: number;
  sent: boolean;
}

export interface AuthRegisterResponse {
  user_id: string;
  email: string;
  display_name: string;
  workspace: AuthWorkspaceSummary;
  session: AuthSessionPayload;
}

export interface AuthLoginRequest {
  email: string;
  password: string;
}

export interface AuthLoginResponse {
  user_id: string;
  email: string;
  display_name: string;
  session: AuthSessionPayload;
}

export interface AuthRefreshResponse {
  session: AuthSessionPayload;
}

export interface AuthLogoutResponse {
  logged_out: boolean;
}

export interface AuthMeResponse {
  user_id: string;
  email: string;
  display_name: string;
  status: string;
  current_workspace_id: string;
  workspaces: AuthWorkspaceSummary[];
}

export interface WorkspaceCreateRequest {
  name: string;
}

export interface WorkspaceCreateResponse {
  workspace: AuthWorkspaceSummary;
  created_at: string;
}

export interface WorkspaceDetail {
  id: string;
  workspace_code: string;
  name: string;
  role: string;
  status: string;
  plan_code: string;
  owner_user_id: string;
  owner_display_name?: string | null;
  owner_email?: string | null;
  member_count: number;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceUpdateRequest {
  name: string;
}

export interface WorkspaceMember {
  id: string;
  user_id: string;
  display_name: string;
  email: string;
  avatar_url?: string | null;
  role: string;
  status: string;
  is_current_user: boolean;
  joined_at?: string | null;
  last_active_at?: string | null;
}

export interface WorkspaceMemberListResult {
  workspace_id: string;
  total: number;
  items: WorkspaceMember[];
}

export interface WorkspaceMemberInviteRequest {
  email: string;
  role: string;
}

export interface WorkspaceMemberUpdateRequest {
  role: string;
}

export interface WorkspaceMemberRemoveResponse {
  member_id: string;
  removed: boolean;
}

function resolveDefaultApiBaseUrl(): string {
  if (typeof window === "undefined") {
    return "http://127.0.0.1:8000/api/v1";
  }
  const protocol = window.location.protocol || "http:";
  const hostname = window.location.hostname || "127.0.0.1";
  return `${protocol}//${hostname}:8000/api/v1`;
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || resolveDefaultApiBaseUrl();
const WORKSPACE_STORAGE_KEY = "ai_hr_workspace_id";
const ACCESS_TOKEN_SKEW_MS = 10_000;

let accessToken: string | null = null;
let accessTokenExpiresAtMs: number | null = null;
let activeWorkspaceId: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;

if (typeof window !== "undefined") {
  const storedWorkspace = window.localStorage.getItem(WORKSPACE_STORAGE_KEY);
  activeWorkspaceId = storedWorkspace ? storedWorkspace.trim() || null : null;
}

interface RequestOptions {
  auth?: boolean;
  retryOnUnauthorized?: boolean;
}

function updateWorkspaceSelection(workspaceId: string | null): void {
  const normalized = String(workspaceId || "").trim() || null;
  activeWorkspaceId = normalized;
  if (typeof window !== "undefined") {
    if (normalized) {
      window.localStorage.setItem(WORKSPACE_STORAGE_KEY, normalized);
    } else {
      window.localStorage.removeItem(WORKSPACE_STORAGE_KEY);
    }
  }
}

function applyAuthSession(session: AuthSessionPayload | null): void {
  if (!session?.access_token) {
    accessToken = null;
    accessTokenExpiresAtMs = null;
    return;
  }
  accessToken = session.access_token;
  accessTokenExpiresAtMs = Date.now() + Math.max(1, Number(session.expires_in || 0)) * 1000;
  const preferredWorkspaceId = String(session.workspace_id || "").trim();
  if (preferredWorkspaceId) {
    updateWorkspaceSelection(preferredWorkspaceId);
    return;
  }
  const firstWorkspaceId = String(session.workspaces?.[0]?.id || "").trim();
  if (firstWorkspaceId) {
    updateWorkspaceSelection(firstWorkspaceId);
  }
}

function clearAuthSession(): void {
  accessToken = null;
  accessTokenExpiresAtMs = null;
}

async function extractErrorText(res: Response): Promise<string> {
  let rawText = "";
  try {
    rawText = await res.text();
  } catch {
    return `HTTP ${res.status}`;
  }
  if (!rawText) {
    return `HTTP ${res.status}`;
  }
  try {
    const parsed = JSON.parse(rawText) as Envelope<unknown>;
    const message = parsed?.error?.message;
    if (message && String(message).trim()) {
      return String(message).trim();
    }
    return `HTTP ${res.status}`;
  } catch {
    return `HTTP ${res.status}: ${rawText}`;
  }
}

function parseEnvelope<T>(payload: Envelope<T>): T {
  if (payload.ok !== true) {
    const message = payload.error?.message || "Request failed";
    throw new Error(message);
  }
  return payload.data as T;
}

async function executeRefreshFlow(): Promise<boolean> {
  if (refreshInFlight) {
    return refreshInFlight;
  }
  refreshInFlight = (async () => {
    try {
      const data = await request<AuthRefreshResponse>(
        "/auth/refresh",
        {
          method: "POST",
          body: JSON.stringify({}),
        },
        { auth: false, retryOnUnauthorized: false },
      );
      applyAuthSession(data.session);
      return true;
    } catch {
      clearAuthSession();
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

async function request<T>(path: string, init?: RequestInit, options: RequestOptions = {}): Promise<T> {
  const authRequired = options.auth ?? true;
  const retryOnUnauthorized = options.retryOnUnauthorized ?? authRequired;

  const doFetch = async (): Promise<Response> => {
    const headers = new Headers(init?.headers || {});
    const hasBinaryBody = typeof FormData !== "undefined" && init?.body instanceof FormData;
    if (!headers.has("Content-Type") && init?.body != null && !hasBinaryBody) {
      headers.set("Content-Type", "application/json");
    }
    if (authRequired && accessToken) {
      headers.set("Authorization", `Bearer ${accessToken}`);
    }
    if (authRequired && activeWorkspaceId) {
      headers.set("X-Workspace-Id", activeWorkspaceId);
    }
    return fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: "include",
      headers,
    });
  };

  if (authRequired && accessToken && accessTokenExpiresAtMs && accessTokenExpiresAtMs - Date.now() <= ACCESS_TOKEN_SKEW_MS) {
    await executeRefreshFlow();
  }

  let res = await doFetch();
  if (res.status === 401 && authRequired && retryOnUnauthorized) {
    const refreshed = await executeRefreshFlow();
    if (refreshed) {
      res = await doFetch();
    }
  }

  if (!res.ok) {
    throw new Error(await extractErrorText(res));
  }

  const payload = (await res.json()) as Envelope<T>;
  return parseEnvelope(payload);
}

export function hasActiveAccessToken(): boolean {
  return Boolean(accessToken);
}

export function getActiveWorkspaceId(): string | null {
  return activeWorkspaceId;
}

export function selectWorkspace(workspaceId: string): void {
  updateWorkspaceSelection(workspaceId);
}

export function clearWorkspaceSelection(): void {
  updateWorkspaceSelection(null);
}

export function clearClientAuthState(): void {
  clearAuthSession();
  clearWorkspaceSelection();
}

export async function login(payload: AuthLoginRequest): Promise<AuthLoginResponse> {
  const data = await request<AuthLoginResponse>(
    "/auth/login",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    { auth: false, retryOnUnauthorized: false },
  );
  applyAuthSession(data.session);
  return data;
}

export async function register(payload: AuthRegisterRequest): Promise<AuthRegisterResponse> {
  const data = await request<AuthRegisterResponse>(
    "/auth/register",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    { auth: false, retryOnUnauthorized: false },
  );
  applyAuthSession(data.session);
  return data;
}

export async function sendRegisterEmailCode(
  payload: AuthSendRegisterEmailCodeRequest
): Promise<AuthSendRegisterEmailCodeResponse> {
  return request<AuthSendRegisterEmailCodeResponse>(
    "/auth/register/email-code",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    { auth: false, retryOnUnauthorized: false },
  );
}

export async function refreshSession(): Promise<AuthRefreshResponse> {
  const data = await request<AuthRefreshResponse>(
    "/auth/refresh",
    {
      method: "POST",
      body: JSON.stringify({}),
    },
    { auth: false, retryOnUnauthorized: false },
  );
  applyAuthSession(data.session);
  return data;
}

export async function fetchCurrentUser(): Promise<AuthMeResponse> {
  return request<AuthMeResponse>("/auth/me");
}

export async function logout(): Promise<AuthLogoutResponse> {
  try {
    return await request<AuthLogoutResponse>("/auth/logout", { method: "POST", body: JSON.stringify({}) });
  } finally {
    clearAuthSession();
    clearWorkspaceSelection();
  }
}

export async function listWorkspaces(): Promise<AuthWorkspaceSummary[]> {
  return request<AuthWorkspaceSummary[]>("/workspaces");
}

export async function createWorkspace(payload: WorkspaceCreateRequest): Promise<WorkspaceCreateResponse> {
  return request<WorkspaceCreateResponse>("/workspaces", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getWorkspaceDetail(workspaceId: string): Promise<WorkspaceDetail> {
  return request<WorkspaceDetail>(`/workspaces/${encodeURIComponent(workspaceId)}`);
}

export async function updateWorkspace(workspaceId: string, payload: WorkspaceUpdateRequest): Promise<WorkspaceDetail> {
  return request<WorkspaceDetail>(`/workspaces/${encodeURIComponent(workspaceId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function listWorkspaceMembers(workspaceId: string): Promise<WorkspaceMemberListResult> {
  return request<WorkspaceMemberListResult>(`/workspaces/${encodeURIComponent(workspaceId)}/members`);
}

export async function inviteWorkspaceMember(
  workspaceId: string,
  payload: WorkspaceMemberInviteRequest,
): Promise<WorkspaceMember> {
  return request<WorkspaceMember>(`/workspaces/${encodeURIComponent(workspaceId)}/members`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateWorkspaceMember(
  workspaceId: string,
  memberId: string,
  payload: WorkspaceMemberUpdateRequest,
): Promise<WorkspaceMember> {
  return request<WorkspaceMember>(
    `/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(memberId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export async function removeWorkspaceMember(
  workspaceId: string,
  memberId: string,
): Promise<WorkspaceMemberRemoveResponse> {
  return request<WorkspaceMemberRemoveResponse>(
    `/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(memberId)}`,
    {
      method: "DELETE",
    },
  );
}

// Credentials
export async function fetchBossCredential(): Promise<CredentialStatus> {
  return request<CredentialStatus>("/credentials/boss");
}

export async function validateBossCredential(): Promise<CredentialStatus> {
  return request<CredentialStatus>("/credentials/boss/validate", {
    method: "POST",
    body: JSON.stringify({}),
  });
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

export async function fetchHiringCenterOverview(
  payload: { top_n?: number; queue_limit?: number; max_scan?: number } = {}
): Promise<HiringCenterOverviewResult> {
  const params = new URLSearchParams();
  params.set("top_n", String(payload.top_n ?? 3));
  params.set("queue_limit", String(payload.queue_limit ?? 20));
  params.set("max_scan", String(payload.max_scan ?? 3000));
  return request<HiringCenterOverviewResult>(`/analytics/hiring-center?${params.toString()}`);
}

export async function fetchHiringDecisionDetail(jobId: string, candidateId: string): Promise<HiringDecisionDetailResult> {
  const params = new URLSearchParams();
  params.set("job_id", jobId);
  params.set("candidate_id", candidateId);
  return request<HiringDecisionDetailResult>(`/analytics/hiring-decision-detail?${params.toString()}`);
}

// Jobs
export async function listJobs(query: number | JobsQuery = 100): Promise<Job[]> {
  const params = new URLSearchParams();
  if (typeof query === "number") {
    params.set("limit", String(query));
  } else {
    params.set("limit", String(query.limit ?? 100));
    if (typeof query.offset === "number") {
      params.set("offset", String(query.offset));
    }
    if (query.platform) {
      params.set("platform", query.platform);
    }
    if (query.name) {
      params.set("name", query.name);
    }
    if (query.job_type) {
      params.set("job_type", query.job_type);
    }
    if (query.salary) {
      params.set("salary", query.salary);
    }
  }
  const res = await request<{ items: Job[] }>(`/jobs?${params.toString()}`);
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

export async function syncJobCandidates(
  jobId: string,
  payload: {
    max_pages?: number;
    auto_request_resume?: boolean;
    auto_sync_resume_attachment?: boolean;
    reset_cursor?: boolean;
  } = {}
): Promise<any> {
  return request(`/jobs/${jobId}/candidates/sync`, {
    method: "POST",
    body: JSON.stringify({
      max_pages: payload.max_pages ?? 5,
      auto_request_resume: Boolean(payload.auto_request_resume),
      auto_sync_resume_attachment: Boolean(payload.auto_sync_resume_attachment),
      reset_cursor: Boolean(payload.reset_cursor),
    })
  });
}

export async function deleteJob(jobId: string): Promise<void> {
  await request(`/jobs/${jobId}`, {
    method: "DELETE",
  });
}

export async function batchDeleteJobs(jobIds: string[]): Promise<{ deleted_count: number }> {
  return request<{ deleted_count: number }>(`/jobs/batch-delete`, {
    method: "POST",
    body: JSON.stringify({ job_ids: jobIds }),
  });
}

// Candidates
export async function listJobCandidates(
  jobId: string,
  payload: { limit?: number; cursor?: string; keyword?: string; stage?: string; resume_status?: string; segment?: "all" | "recommended" | "invited" | "failed" } = {}
): Promise<JobCandidateListResult> {
  const params = new URLSearchParams();
  if (payload.limit) {
    params.set("limit", String(payload.limit));
  }
  if (payload.cursor) {
    params.set("cursor", payload.cursor);
  }
  if (payload.keyword) {
    params.set("keyword", payload.keyword);
  }
  if (payload.stage && payload.stage !== "all") {
    params.set("stage", payload.stage);
  }
  if (payload.resume_status && payload.resume_status !== "all") {
    params.set("resume_status", payload.resume_status);
  }
  if (payload.segment && payload.segment !== "all") {
    params.set("segment", payload.segment);
  }
  const qs = params.toString();
  return request<JobCandidateListResult>(`/jobs/${jobId}/candidates${qs ? `?${qs}` : ""}`);
}

export async function getJobCandidate(jobId: string, candidateId: string): Promise<JobCandidate> {
  return request<JobCandidate>(`/jobs/${jobId}/candidates/${candidateId}`);
}

export async function fetchCandidateResumeProfile(candidateId: string): Promise<CandidateResumeProfileResult> {
  return request<CandidateResumeProfileResult>(`/candidates/${candidateId}/resume-profile`);
}

export async function fetchCandidateResumeAttachment(candidateId: string): Promise<ResumeAttachmentPayload> {
  return request<ResumeAttachmentPayload>(`/candidates/${candidateId}/resume-attachment`);
}

export async function syncCandidateResumeAttachment(candidateId: string): Promise<{ attachment: ResumeAttachmentPayload }> {
  return request<{ attachment: ResumeAttachmentPayload }>(`/candidates/${candidateId}/resume-attachment/sync`, {
    method: "POST",
    body: JSON.stringify({}),
  });
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

export async function fetchInterviewInvitationHistory(
  payload: { limit?: number; keyword?: string; status?: string; stage?: string } = {}
): Promise<InterviewInvitationHistoryResult> {
  const params = new URLSearchParams();
  params.set("limit", String(payload.limit ?? 200));
  if (payload.keyword) {
    params.set("keyword", payload.keyword);
  }
  if (payload.stage && payload.stage !== "all") {
    params.set("stage", payload.stage);
  }
  if (payload.status && payload.status !== "all") {
    params.set("status", payload.status);
  }
  return request<InterviewInvitationHistoryResult>(`/interviews/invitations/history?${params.toString()}`);
}

export async function fetchInterviewInvitationRecord(deliveryId: string): Promise<InterviewInvitationRecordDetailResult> {
  return request<InterviewInvitationRecordDetailResult>(`/interviews/invitations/${encodeURIComponent(deliveryId)}/record`);
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
  const data = await request<{ items: any[] }>(
    `/ai/interviews/sessions/${sessionId}/replay?limit=200&offset=0`,
    undefined,
    { auth: false, retryOnUnauthorized: false },
  );
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
  return request<InterviewSession>(
    `/ai-interviews/invitations/token/${encodeURIComponent(token)}/activate`,
    {
      method: "POST",
      body: JSON.stringify({}),
    },
    { auth: false, retryOnUnauthorized: false },
  );
}

export async function getInterviewSession(sessionId: string): Promise<InterviewSession> {
  return request<InterviewSession>(
    `/ai/interviews/sessions/${encodeURIComponent(sessionId)}`,
    undefined,
    { auth: false, retryOnUnauthorized: false },
  );
}

export async function startInterviewSession(sessionId: string, operator = "system"): Promise<InterviewSession> {
  return request<InterviewSession>(
    `/ai/interviews/sessions/${encodeURIComponent(sessionId)}/start`,
    {
      method: "POST",
      body: JSON.stringify({ operator }),
    },
    { auth: false, retryOnUnauthorized: false },
  );
}

export async function finishInterviewSession(
  sessionId: string,
  payload: { result_status?: "completed" | "failed"; operator?: string; note?: string } = {}
): Promise<InterviewSession> {
  return request<InterviewSession>(
    `/ai/interviews/sessions/${encodeURIComponent(sessionId)}/finish`,
    {
      method: "POST",
      body: JSON.stringify({
        result_status: payload.result_status || "completed",
      }),
    },
    { auth: false, retryOnUnauthorized: false },
  );
}

export async function joinInterviewRTC(
  sessionId: string,
  candidateId: string,
  clientId = "web"
): Promise<InterviewRTCJoinInfo> {
  return request<InterviewRTCJoinInfo>(
    `/ai/interviews/sessions/${encodeURIComponent(sessionId)}/rtc/join`,
    {
      method: "POST",
      body: JSON.stringify({
        candidate_id: candidateId,
        client_id: clientId,
      }),
    },
    { auth: false, retryOnUnauthorized: false },
  );
}

export async function renewInterviewRTCToken(
  sessionId: string,
  candidateId: string,
  clientId = "web"
): Promise<InterviewRTCJoinInfo> {
  return joinInterviewRTC(sessionId, candidateId, clientId);
}

export async function joinInterviewRTCPreflight(
  sessionId: string,
  candidateId: string,
  clientId = "web"
): Promise<InterviewRTCJoinInfo> {
  return joinInterviewRTC(sessionId, candidateId, clientId);
}

export async function getTenRuntimeConfig(sessionId: string): Promise<InterviewTENRuntimeConfig> {
  return request<InterviewTENRuntimeConfig>(
    `/ai/interviews/sessions/${encodeURIComponent(sessionId)}/ten/runtime-config`,
    undefined,
    { auth: false, retryOnUnauthorized: false },
  );
}

export async function launchTenSession(sessionId: string): Promise<InterviewTENRuntimeConfig> {
  return request<InterviewTENRuntimeConfig>(
    `/ai/interviews/sessions/${encodeURIComponent(sessionId)}/ten/launch`,
    {
      method: "POST",
      body: JSON.stringify({}),
    },
    { auth: false, retryOnUnauthorized: false },
  );
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
