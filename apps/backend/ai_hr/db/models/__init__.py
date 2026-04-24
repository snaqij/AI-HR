"""数据库模型模块集合。"""

from .ai_decision_log import AIDecisionLog
from .agent_event import AgentEvent
from .agent_run import AgentRun
from .ai_eval_run import AIEvalRun
from .ai_feature_flag import AIFeatureFlag
from .ai_interview_handoff import AIInterviewHandoff
from .ai_interview_invitation import AIInterviewInvitation
from .ai_interview_question_set import AIInterviewQuestionSet
from .ai_interview_report import AIInterviewReport
from .ai_interview_session import AIInterviewSession
from .ai_interview_turn import AIInterviewTurn
from .ai_model_config import AIModelConfig
from .ai_prompt_version import AIPromptVersion
from .ai_request_trace import AIRequestTrace
from .approval import Approval
from .automation_task_log import AutomationTaskLog
from .candidate import Candidate
from .candidate_email_delivery import CandidateEmailDelivery
from .candidate_identity import CandidateIdentity
from .candidate_job_evaluation import CandidateJobEvaluation
from .candidate_composite_assessment import CandidateCompositeAssessment
from .candidate_job_pipeline import CandidateJobPipeline
from .candidate_resume_access_retry import CandidateResumeAccessRetry
from .candidate_resume_attachment import CandidateResumeAttachment
from .candidate_job_score import CandidateJobScore
from .candidate_resume_profile import CandidateResumeProfile
from .candidate_resume_risk import CandidateResumeRisk
from .decision_event import DecisionEvent
from .decision_policy_version import DecisionPolicyVersion
from .conversation import Conversation
from .email_template import EmailTemplate
from .event import Event
from .interview import Interview
from .job_market_snapshot import JobMarketSnapshot
from .ai_interview_assessment import AIInterviewAssessment
from .ai_interview_answer_record import AIInterviewAnswerRecord
from .ai_interview_answer_score import AIInterviewAnswerScore
from .ai_interview_question_attempt import AIInterviewQuestionAttempt
from .job import Job
from .job_candidate import JobCandidate
from .job_publication import JobPublication
from .review_queue_task import ReviewQueueTask
from .platform_user import PlatformUser
from .platform_email_verification_code import PlatformEmailVerificationCode
from .platform_user_session import PlatformUserSession
from .team_workspace import TeamWorkspace
from .team_workspace_member import TeamWorkspaceMember
from .job_sync_run import JobSyncRun
from .job_sync_task import JobSyncTask
from .job_shortlist import JobShortlist
from .credential import ChannelCredential

__all__ = [
    "AIDecisionLog",
    "AgentEvent",
    "AgentRun",
    "AIEvalRun",
    "AIFeatureFlag",
    "AIInterviewHandoff",
    "AIInterviewInvitation",
    "AIInterviewQuestionSet",
    "AIInterviewReport",
    "AIInterviewSession",
    "AIInterviewTurn",
    "AIModelConfig",
    "AIPromptVersion",
    "AIRequestTrace",
    "Approval",
    "AutomationTaskLog",
    "Candidate",
    "CandidateEmailDelivery",
    "CandidateIdentity",
    "CandidateJobEvaluation",
    "CandidateCompositeAssessment",
    "CandidateJobPipeline",
    "CandidateResumeAccessRetry",
    "CandidateResumeAttachment",
    "CandidateJobScore",
    "CandidateResumeProfile",
    "CandidateResumeRisk",
    "DecisionEvent",
    "DecisionPolicyVersion",
    "Conversation",
    "EmailTemplate",
    "Event",
    "Interview",
    "JobMarketSnapshot",
    "AIInterviewAssessment",
    "AIInterviewAnswerRecord",
    "AIInterviewAnswerScore",
    "AIInterviewQuestionAttempt",
    "Job",
    "JobCandidate",
    "JobPublication",
    "ReviewQueueTask",
    "PlatformUser",
    "PlatformEmailVerificationCode",
    "PlatformUserSession",
    "TeamWorkspace",
    "TeamWorkspaceMember",
    "JobSyncRun",
    "JobSyncTask",
    "JobShortlist",
    "ChannelCredential",
]
