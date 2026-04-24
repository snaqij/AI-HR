<template>
  <div class="candidate-board">
    <section v-if="!jobId" class="candidate-empty candidate-panel">
      <h2>缺少岗位信息</h2>
      <p>请从职位管理页进入候选人管理页面。</p>
    </section>

    <section v-else-if="isBoardLoading" class="candidate-empty candidate-panel">
      <div class="loading-spinner"></div>
      <p>正在加载候选人数据...</p>
    </section>

    <section v-else-if="boardError" class="candidate-empty candidate-panel">
      <h2>加载失败</h2>
      <p>{{ boardError }}</p>
      <button type="button" class="ghost-btn" @click="loadBoard">重试</button>
    </section>

    <section v-else class="candidate-layout">
      <aside class="roster-panel candidate-panel">
        <div class="roster-header">
          <div>
            <p class="eyebrow">Candidates</p>
            <h2>候选人管理</h2>
          </div>
          <button
            type="button"
            class="sync-btn"
            :disabled="isSyncing"
            @click="handleSyncCandidates"
            title="从 BOSS 同步候选人数据"
          >
            <span v-if="isSyncing">同步中...</span>
            <span v-else>Sync</span>
          </button>
          <p class="roster-job">{{ job?.title || "当前岗位" }}</p>
        </div>

        <label class="search-box">
          <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <circle cx="9" cy="9" r="5.75" stroke="currentColor" stroke-width="1.6" />
            <path d="M13.5 13.5L17 17" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
          </svg>
          <input
            v-model.trim="searchKeyword"
            type="text"
            placeholder="搜索候选人姓名、学校、公司"
          />
        </label>

        <div class="filter-row">
          <select v-model="jobFilter">
            <option value="all">全部职位</option>
            <option value="current">{{ job?.title || "当前岗位" }}</option>
          </select>
          <select v-model="stageFilter">
            <option value="all">全部状态</option>
            <option
              v-for="item in stageOptions"
              :key="item.value"
              :value="item.value"
            >
              {{ item.label }}
            </option>
          </select>
          <button type="button" class="filter-trigger">
            <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M2 4H14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
              <path d="M4.5 8H11.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
              <path d="M6.5 12H9.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
            筛选
          </button>
        </div>

        <div class="roster-meta">
          <span>共 {{ totalCandidates }} 位候选人</span>
          <span v-if="job?.city">{{ job.city }}</span>
        </div>

        <div class="roster-list" :class="{ 'opacity-50 pointer-events-none': isListLoading }">
          <button
            v-for="candidate in pagedCandidates"
            v-memo="[candidate.candidate.id, candidate.candidate.id === selectedCandidateId, candidate.stage, candidate.last_synced_at]"
            :key="candidate.candidate.id"
            type="button"
            class="candidate-card"
            :class="{ active: candidate.candidate.id === selectedCandidateId }"
            @click="handleSelectCandidate(candidate.candidate.id)"
          >
            <div 
              v-if="getCandidateAvatar(candidate.candidate)" 
              class="candidate-avatar"
              :style="{ backgroundImage: `url(${getCandidateAvatar(candidate.candidate)})`, backgroundSize: 'cover', backgroundPosition: 'center' }"
            ></div>
            <div 
              v-else
              class="candidate-avatar" 
              :style="avatarStyle(candidate.candidate.name)"
            >
              {{ initials(candidate.candidate.name) }}
            </div>
            <div class="candidate-copy">
              <div class="candidate-name-row">
                <span class="candidate-name">{{ candidate.candidate.name || "未命名候选人" }}</span>
                <span class="status-pill" :class="stageTone(candidate.stage)">
                  {{ getStageText(candidate.stage) }}
                </span>
              </div>
              <p class="candidate-role">{{ candidateTitle(candidate) }}</p>
              <p class="candidate-updated">更新于 {{ formatShortDate(candidate.last_synced_at || candidate.first_synced_at) }}</p>
            </div>
          </button>

          <div v-if="!pagedCandidates.length" class="roster-empty">
            没有匹配到候选人
          </div>
        </div>

        <div class="pagination-bar" v-if="totalPages > 1">
          <button
            type="button"
            class="page-arrow"
            :disabled="currentPage === 1"
            @click="currentPage -= 1"
          >
            <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M10 4L6 8L10 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
          </button>

          <button
            v-for="page in visiblePages"
            :key="page"
            type="button"
            class="page-btn"
            :class="{ active: page === currentPage }"
            @click="currentPage = page"
          >
            {{ page }}
          </button>

          <span v-if="totalPages > lastVisiblePage">...</span>

          <button
            type="button"
            class="page-arrow"
            :disabled="currentPage === totalPages"
            @click="currentPage += 1"
          >
            <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M6 4L10 8L6 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
          </button>
        </div>
      </aside>

      <main class="detail-area" v-if="selectedCandidate">
        <div v-if="isCandidateLoading" class="detail-loading">正在同步候选人详情...</div>
        <section class="hero-card candidate-panel">
          <div class="hero-main">
            <div 
              v-if="getCandidateAvatar(selectedCandidate.candidate)" 
              class="hero-avatar"
              :style="{ backgroundImage: `url(${getCandidateAvatar(selectedCandidate.candidate)})`, backgroundSize: 'cover', backgroundPosition: 'center' }"
            ></div>
            <div 
              v-else
              class="hero-avatar" 
              :style="avatarStyle(selectedCandidate.candidate.name)"
            >
              {{ initials(selectedCandidate.candidate.name) }}
            </div>

            <div class="hero-copy">
              <div class="hero-name-row">
                <h1>{{ selectedCandidate.candidate.name || "--" }}</h1>
                <span class="verified-chip">
                  <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
                    <circle cx="10" cy="10" r="10" fill="currentColor" />
                    <path d="M6.4 10.2L8.6 12.5L13.7 7.4" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                </span>
                <span class="hero-stage" :class="stageTone(selectedCandidate.stage)">
                  {{ getStageText(selectedCandidate.stage) }}
                </span>
              </div>

              <div class="hero-subline">
                <span>{{ candidateTitle(selectedCandidate) }}</span>
                <span>来自 {{ selectedCandidate.channel || "--" }}</span>
              </div>

              <div class="hero-contact">
                <div class="hero-contact-item">
                  <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path d="M3.5 2C3.2 2 3 2.2 3 2.5V4.5C3 9.2 6.8 13 11.5 13H13.5C13.8 13 14 12.8 14 12.5V10.5C14 10.2 13.8 10 13.5 10H11.5C11.2 10 11 10.2 11 10.5V11.5C8.5 11.2 6.8 9.5 6.5 7H7.5C7.8 7 8 6.8 8 6.5V4.5C8 4.2 7.8 4 7.5 4H5.5C5.2 4 5 4.2 5 4.5V5.5C5 5.8 4.8 6 4.5 6H3.5C3.2 6 3 5.8 3 5.5V2.5C3 2.2 3.2 2 3.5 2Z" stroke="currentColor" stroke-width="1.2" fill="none" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                  <span>{{ candidatePhone }}</span>
                </div>
                <div class="hero-contact-item">
                  <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <rect x="2.2" y="3.4" width="11.6" height="9.2" rx="2" stroke="currentColor" stroke-width="1.3" />
                    <path d="M2.8 4.4L8 8.2L13.2 4.4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                  <span>{{ selectedCandidate.candidate.email || "--" }}</span>
                </div>
                <div class="hero-contact-item">
                  <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path d="M8 14C10.8 11.3 12.2 9.1 12.2 7.2C12.2 4.9 10.3 3 8 3C5.7 3 3.8 4.9 3.8 7.2C3.8 9.1 5.2 11.3 8 14Z" stroke="currentColor" stroke-width="1.3" />
                    <circle cx="8" cy="7.2" r="1.6" stroke="currentColor" stroke-width="1.3" />
                  </svg>
                  <span>{{ candidateLocation }}</span>
                </div>
                <div class="hero-contact-item">
                  <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <rect x="2.4" y="3.2" width="11.2" height="10.4" rx="2" stroke="currentColor" stroke-width="1.3" />
                    <path d="M5.1 2V4.4M10.9 2V4.4M2.4 6.2H13.6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" />
                  </svg>
                  <span>{{ candidateExperience }}</span>
                </div>
              </div>
            </div>
            <div class="hero-actions">
            <button type="button" class="ghost-btn" @click="openDetailPage">
              操作
              <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M4 6L8 10L12 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
              </svg>
            </button>
            <button type="button" class="ghost-btn">加入人才库</button>
            <button type="button" class="primary-btn" @click="showInviteDialog">
              面试邀请
            </button>
          </div>
        </div>

          <div class="hero-tabs">
            <button
              v-for="tab in tabs"
              :key="tab.value"
              type="button"
              class="hero-tab"
              :class="{ active: activeTab === tab.value }"
              @click="activeTab = tab.value"
            >
              {{ tab.label }}
            </button>
          </div>
        </section>

        <section class="content-grid">
          <div class="content-main">
            <template v-if="activeTab === 'resume'">
              <article class="candidate-panel detail-card wide-card">
                <div class="detail-card-head">
                  <h3>简历预览</h3>
                  <div style="display: flex; gap: 8px;">
                    <button
                      v-if="!resumeAttachment && selectedCandidateId"
                      type="button"
                      class="primary-btn compact"
                      :disabled="isLoadingAttachment"
                      @click="handleSyncResume"
                    >
                      {{ isLoadingAttachment ? "同步中..." : "同步PDF简历" }}
                    </button>
                    <a
                      v-if="resumeAttachment"
                      :href="resumeDownloadUrl || '#'"
                      target="_blank"
                      class="inline-link"
                      download
                    >
                      <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
                        <path d="M8 2.5V11.5M8 11.5L4.8 8.4M8 11.5L11.2 8.4M2.5 13.5H13.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
                      </svg>
                      下载PDF
                    </a>
                  </div>
                </div>

                <div v-if="isLoadingAttachment" class="resume-preview" style="display: flex; align-items: center; justify-content: center; min-height: 800px;">
                  <div style="width: 48px; height: 48px; border: 4px solid rgba(99, 102, 241, 0.2); border-top-color: rgb(99, 102, 241); border-radius: 50%; animation: spin 1s linear infinite;"></div>
                </div>

                <div v-else-if="resumeAttachment" class="resume-preview">
                  <iframe
                    v-if="resumeDownloadUrl"
                    :src="resumeDownloadUrl"
                    style="width: 100%; height: 900px; border: 1px solid #e5e7eb; border-radius: 8px;"
                    title="简历预览"
                  />
                </div>

                <div v-else-if="selectedCandidate?.candidate.resume_text" class="resume-preview" style="padding: 32px; background: white; border: 1px solid #e5e7eb; border-radius: 8px; min-height: 800px;">
                  <div style="max-width: 800px; margin: 0 auto;">
                    <div style="margin-bottom: 24px; padding-bottom: 16px; border-bottom: 2px solid #e5e7eb;">
                      <h2 style="font-size: 24px; font-weight: 600; margin-bottom: 8px;">{{ selectedCandidate.candidate.name }}</h2>
                      <div style="display: flex; gap: 16px; flex-wrap: wrap; font-size: 14px; color: #6b7280;">
                        <span v-if="selectedCandidate.candidate.email">📧 {{ selectedCandidate.candidate.email }}</span>
                        <span v-if="selectedCandidate.candidate.school">🎓 {{ selectedCandidate.candidate.school }}</span>
                        <span v-if="selectedCandidate.candidate.degree">📚 {{ selectedCandidate.candidate.degree }}</span>
                      </div>
                    </div>
                    <div style="white-space: pre-wrap; line-height: 1.8; font-size: 14px; color: #374151;">{{ selectedCandidate.candidate.resume_text }}</div>
                  </div>
                </div>

                <div v-else class="resume-preview" style="display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 800px; gap: 16px;">
                  <svg viewBox="0 0 24 24" fill="none" style="width: 80px; height: 80px; opacity: 0.3;">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <polyline points="14 2 14 8 20 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                  <p style="font-size: 14px; color: #6b7280;">暂无简历信息</p>
                  <p style="font-size: 12px; color: #9ca3af;">点击上方"同步PDF简历"按钮从BOSS直聘获取简历文件</p>
                </div>
              </article>
            </template>

            <article v-else-if="activeTab === 'basic'" class="candidate-panel detail-card wide-card">
              <div class="detail-card-head">
                <h3>候选人档案</h3>
              </div>
              <div class="profile-grid">
                <div v-for="item in profileItems" :key="item.label" class="profile-chip">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                </div>
              </div>
            </article>

            <article v-else-if="activeTab === 'evaluation'" class="candidate-panel detail-card wide-card">
              <div class="detail-card-head">
                <h3>评估结论</h3>
                <button type="button" class="primary-btn compact" :disabled="isAnalyzing" @click="refreshEvaluation">
                  {{ isAnalyzing ? "分析中..." : "重新评估" }}
                </button>
              </div>
              <div class="eval-stack">
                <section class="eval-section">
                  <span class="eval-label">总结</span>
                  <p>{{ evaluationSummary }}</p>
                </section>
                <section class="eval-section">
                  <span class="eval-label">核心优势</span>
                  <ul v-if="evaluationStrengths.length">
                    <li v-for="item in evaluationStrengths" :key="item">{{ item }}</li>
                  </ul>
                  <p v-else>暂无优势分析</p>
                </section>
                <section class="eval-section">
                  <span class="eval-label">改进建议</span>
                  <ul v-if="evaluationWeaknesses.length">
                    <li v-for="item in evaluationWeaknesses" :key="item">{{ item }}</li>
                  </ul>
                  <p v-else>暂无改进建议</p>
                </section>
                <section class="eval-section">
                  <span class="eval-label">风险提示</span>
                  <ul v-if="evaluationRisks.length">
                    <li v-for="item in evaluationRisks" :key="item">{{ item }}</li>
                  </ul>
                  <p v-else>暂无风险提示</p>
                </section>
              </div>
            </article>

            <article v-else-if="activeTab === 'history'" class="candidate-panel detail-card wide-card">
              <div class="detail-card-head">
                <h3>面试记录</h3>
              </div>
              <div class="log-list">
                <div class="log-item">
                  <span>首次同步</span>
                  <strong>{{ formatDateTime(selectedCandidate.first_synced_at) }}</strong>
                </div>
                <div class="log-item">
                  <span>最近更新</span>
                  <strong>{{ formatDateTime(selectedCandidate.last_synced_at) }}</strong>
                </div>
                <div class="log-item">
                  <span>当前阶段</span>
                  <strong>{{ getStageText(selectedCandidate.stage) }}</strong>
                </div>
                <div class="log-item">
                  <span>状态来源</span>
                  <strong>{{ selectedCandidate.source_status || "系统同步" }}</strong>
                </div>
              </div>
            </article>

            <article v-else-if="activeTab === 'communication'" class="candidate-panel detail-card wide-card">
              <div class="detail-card-head">
                <h3>沟通记录</h3>
              </div>
              <div v-if="deliveries.length" class="delivery-list">
                <article v-for="item in deliveries" :key="item.id" class="delivery-item">
                  <div class="delivery-top">
                    <span class="delivery-status">{{ item.status }}</span>
                    <span>{{ formatDateTime(item.sent_at || item.created_at) }}</span>
                  </div>
                  <strong>{{ item.subject || "未命名邮件" }}</strong>
                  <p>{{ item.to_email }}</p>
                </article>
              </div>
              <div v-else class="blank-card">暂无沟通记录</div>
            </article>

            <article v-else-if="activeTab === 'offer'" class="candidate-panel detail-card wide-card">
              <div class="detail-card-head">
                <h3>Offer / 入职</h3>
              </div>
              <div class="offer-panel">
                <div class="offer-stage">{{ getStageText(selectedCandidate.stage) }}</div>
                <p>{{ offerDescription }}</p>
              </div>
            </article>

            <article v-else class="candidate-panel detail-card wide-card">
              <div class="detail-card-head">
                <h3>备注</h3>
              </div>
              <div class="blank-card">暂无备注内容</div>
            </article>
          </div>

          <aside class="content-side">
            <article class="candidate-panel side-card">
              <div class="side-card-head">
                <h3>评估结果</h3>
              </div>

              <div class="score-panel">
                <div class="score-ring">
                  <svg viewBox="0 0 120 120" aria-hidden="true">
                    <circle class="ring-base" cx="60" cy="60" r="49" />
                    <circle
                      class="ring-value"
                      cx="60"
                      cy="60"
                      r="49"
                      :stroke-dasharray="scoreStroke"
                    />
                  </svg>
                  <div class="score-inner">
                    <strong>{{ finalScore }}</strong>
                    <span>综合评分</span>
                  </div>
                </div>

                <div class="score-copy">
                  <div class="score-recommend">
                    <span>推荐等级：</span>
                    <strong>{{ recommendationText }}</strong>
                  </div>
                  <p>{{ evaluationSummary }}</p>
                </div>

                <div class="score-meta">
                  <span>评估时间：{{ evaluationTime }}</span>
                  <span>评估人：AI 评估</span>
                </div>

                <button type="button" class="ghost-btn full" @click="activeTab = 'evaluation'">
                  查看评估详情
                </button>
              </div>
            </article>

            <article class="candidate-panel side-card">
              <div class="side-card-head">
                <h3>评估维度</h3>
              </div>

              <div v-if="dimensionRatings.length" class="dimension-list">
                <div v-for="item in dimensionRatings" :key="item.label" class="dimension-row">
                  <span>{{ item.label }}</span>
                  <div class="stars">
                    <svg
                      v-for="star in 5"
                      :key="`${item.label}-${star}`"
                      viewBox="0 0 16 16"
                      class="star"
                      :class="{ active: star <= item.stars }"
                    >
                      <path d="M8 1.2L10.1 5.5L14.8 6.1L11.4 9.4L12.2 14L8 11.7L3.8 14L4.6 9.4L1.2 6.1L5.9 5.5L8 1.2Z" />
                    </svg>
                  </div>
                </div>
              </div>
              <div v-else class="blank-card">暂无维度评分</div>

              <button type="button" class="inline-expand" @click="activeTab = 'evaluation'">
                展开全部
                <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path d="M4 6L8 10L12 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
                </svg>
              </button>
            </article>
          </aside>
        </section>
      </main>

      <section v-else class="candidate-empty candidate-panel">
        <h2>暂无候选人</h2>
        <p>当前岗位还没有同步到候选人数据。</p>
      </section>
    </section>

    <!-- Interview invitation modal -->
    <div v-if="showInviteModal" class="modal-overlay" @click.self="showInviteModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>发送面试邀请</h3>
          <button type="button" class="modal-close" @click="showInviteModal = false">
            <svg viewBox="0 0 16 16" fill="none">
              <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <div class="form-field">
            <label>候选人</label>
            <div class="form-value">{{ selectedCandidate?.candidate.name }}</div>
          </div>
          <div class="form-field">
            <label>邮箱</label>
            <div class="form-value">{{ selectedCandidate?.candidate.email || '未填写' }}</div>
          </div>
          <div class="form-field">
            <label>岗位</label>
            <div class="form-value">{{ job?.title }}</div>
          </div>
          <p class="form-hint">确认后将向候选人发送面试邀请邮件，邮件中包含面试链接。</p>
        </div>
        <div class="modal-footer">
          <button type="button" class="ghost-btn" @click="showInviteModal = false">取消</button>
          <button type="button" class="primary-btn" :disabled="isSendingInvite" @click="handleSendInvite">
            {{ isSendingInvite ? '发送中...' : '确认发送' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  evaluateJobCandidate,
  fetchCandidateResumeAttachment,
  fetchCandidateResumeProfile,
  fetchJobEmailDeliveries,
  fetchLatestJobCandidateEvaluation,
  getJob,
  listJobCandidates,
  sendCandidateInvitationEmail,
  syncCandidateResumeAttachment,
  syncJobCandidates,
  updateCandidateStage,
  type CandidateEvaluation,
  type CandidateEmailDelivery,
  type CandidateResumeProfileResult,
  type Job,
  type JobCandidate,
  type ResumeAttachmentPayload,
} from "../../api";

type TabKey = "resume" | "basic" | "evaluation" | "history" | "communication" | "offer" | "notes";

const route = useRoute();
const router = useRouter();

const tabs: Array<{ label: string; value: TabKey }> = [
  { label: "简历信息", value: "resume" },
  { label: "基本信息", value: "basic" },
  { label: "评估", value: "evaluation" },
  { label: "面试记录", value: "history" },
  { label: "沟通记录", value: "communication" },
  { label: "Offer / 入职", value: "offer" },
  { label: "备注", value: "notes" },
];

const stageOptions = [
  { value: "new", label: "新申请" },
  { value: "parsed", label: "待初筛" },
  { value: "screen_pass", label: "初筛通过" },
  { value: "interview", label: "面试中" },
  { value: "offer", label: "录用" },
  { value: "rejected", label: "不合适" },
];

const pageSize = 7;

const job = ref<Job | null>(null);
const allCandidates = ref<JobCandidate[]>([]);
const selectedCandidateId = ref("");
const selectedCandidateDetail = ref<JobCandidate | null>(null);
const evaluation = ref<CandidateEvaluation | null>(null);
const deliveries = ref<CandidateEmailDelivery[]>([]);
const resumeProfile = ref<CandidateResumeProfileResult["profile"] | null>(null);
const resumeAttachment = ref<ResumeAttachmentPayload | null>(null);
const resumeProfileCache = new Map<string, CandidateResumeProfileResult["profile"] | null>();
const resumeAttachmentCache = new Map<string, ResumeAttachmentPayload | null>();
const deliveriesCache = new Map<string, CandidateEmailDelivery[]>();
const evaluationCache = new Map<string, CandidateEvaluation | null>();

const isBoardLoading = ref(false);
const isListLoading = ref(false);
const isCandidateLoading = ref(false);
const isAnalyzing = ref(false);
const isAdvancingStage = ref(false);
const isSyncing = ref(false);
const isLoadingAttachment = ref(false);
const showInviteModal = ref(false);
const isSendingInvite = ref(false);
const boardError = ref("");

const searchKeyword = ref("");
const debouncedKeyword = ref("");
let searchTimer: any = null;

watch(searchKeyword, (val) => {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    debouncedKeyword.value = val;
  }, 300);
});
const jobFilter = ref("all");
const stageFilter = ref("all");
const currentPage = ref(1);
const totalCandidates = ref(0);  // Total count from backend
const activeTab = ref<TabKey>("resume");

const jobId = computed(() => String(route.query.jobId || ""));
const routeCandidateId = computed(() => String(route.query.candidateId || ""));

const filteredCandidates = computed(() => {
  const query = debouncedKeyword.value.trim().toLowerCase();
  return allCandidates.value.filter((item) => {
    if (jobFilter.value !== "all" && jobFilter.value !== "current") {
      return false;
    }
    if (!query) {
      return true;
    }
    const source = [
      item.candidate.name,
      item.candidate.school,
      item.candidate.latest_company,
      item.candidate.email,
      candidateTitle(item),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return source.includes(query);
  });
});

// Use frontend-filtered data for pagination calculation
const totalPages = computed(() => Math.max(1, Math.ceil(filteredCandidates.value.length / pageSize)));
const lastVisiblePage = computed(() => visiblePages.value[visiblePages.value.length - 1] || 1);

const visiblePages = computed(() => {
  const max = Math.min(totalPages.value, 5);
  const start = Math.min(Math.max(1, currentPage.value - 2), Math.max(1, totalPages.value - 4));
  return Array.from({ length: max }, (_, index) => start + index);
});

// Frontend pagination: get current page from filtered data
const pagedCandidates = computed(() => {
  const start = (currentPage.value - 1) * pageSize;
  return filteredCandidates.value.slice(start, start + pageSize);
});

const selectedCandidate = computed(() => {
  if (selectedCandidateDetail.value?.candidate.id === selectedCandidateId.value) {
    return selectedCandidateDetail.value;
  }
  return allCandidates.value.find((item) => item.candidate.id === selectedCandidateId.value) || null;
});

const parsedProfile = computed<Record<string, any>>(() => resumeProfile.value?.parsed_profile || {});
const normalizedProfile = computed<Record<string, any>>(() => resumeProfile.value?.normalized_profile || {});
const candidatePhone = computed(() => maskPhone(selectedCandidate.value?.source_payload));
const candidateLocation = computed(() => {
  return firstText(
    normalizedProfile.value.location,
    normalizedProfile.value.city,
    parsedProfile.value.location,
    parsedProfile.value.city,
    selectedCandidate.value?.source_payload?.location,
    selectedCandidate.value?.source_payload?.city,
    job.value?.city,
  ) || "--";
});
const candidateExperience = computed(() => {
  return firstText(
    selectedCandidate.value?.candidate.work_experience,
    normalizedProfile.value.work_experience,
    parsedProfile.value.work_experience,
  ) || "--";
});

const profileItems = computed(() => {
  const item = selectedCandidate.value?.candidate;
  return [
    { label: "姓名", value: item?.name || "--" },
    { label: "性别", value: pickProfileValue(item?.raw_profile, ["gender", "sex"], normalizedProfile.value.gender, parsedProfile.value.gender) },
    { label: "出生年月", value: pickProfileValue(item?.raw_profile, ["birthday", "birth_date"], normalizedProfile.value.birthday, parsedProfile.value.birthday, parsedProfile.value.birth_date) },
    { label: "手机号", value: candidatePhone.value },
    { label: "邮箱", value: item?.email || "--" },
    { label: "现居地", value: candidateLocation.value || "--" },
    { label: "工作年限", value: item?.work_experience || candidateExperience.value || "--" },
    { label: "最高学历", value: item?.degree || firstText(normalizedProfile.value.education_level, parsedProfile.value.education_level) || "--" },
    { label: "毕业院校", value: item?.school || "--" },
    { label: "专业", value: pickProfileValue(item?.raw_profile, ["major"], normalizedProfile.value.major, parsedProfile.value.major) },
    { label: "期望职位", value: candidateTitle(selectedCandidate.value) },
    { label: "期望薪资", value: item?.expected_salary || job.value?.salary_range || "--" },
    { label: "到岗时间", value: pickProfileValue(item?.raw_profile, ["available_in", "arrival_time"], normalizedProfile.value.available_in, parsedProfile.value.available_in, parsedProfile.value.arrival_time) },
  ];
});

const finalScore = computed(() => {
  const score = evaluation.value?.final_score ?? selectedCandidate.value?.candidate.score_total;
  if (typeof score !== "number" || Number.isNaN(score)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(score)));
});

const scoreStroke = computed(() => {
  const circumference = 2 * Math.PI * 49;
  const filled = (finalScore.value / 100) * circumference;
  return `${filled} ${circumference}`;
});

const recommendationText = computed(() => (evaluation.value?.recommendation ? getRecommendationText(evaluation.value.recommendation) : "--"));
const evaluationTime = computed(() => formatDateTime(evaluation.value?.evaluated_at || evaluation.value?.updated_at || selectedCandidate.value?.last_synced_at));
const evaluationSummary = computed(() => {
  return localizeEvaluationText(evaluation.value?.summary) || selectedCandidate.value?.candidate.score_explanation || "暂无评估结果";
});
const evaluationStrengths = computed(() => {
  return (evaluation.value?.strengths || []).map(localizeEvaluationText).filter(Boolean).slice(0, 4);
});
const evaluationWeaknesses = computed(() => {
  return (evaluation.value?.weaknesses || []).map(localizeEvaluationText).filter(Boolean).slice(0, 4);
});
const evaluationRisks = computed(() => {
  const fromEvaluation = (evaluation.value?.risk_flags || []).map(localizeEvaluationText).filter(Boolean).slice(0, 3);
  if (fromEvaluation.length) {
    return fromEvaluation;
  }
  return (resumeProfile.value?.risks || []).map((item) => item.detail).filter(Boolean).slice(0, 3);
});

const dimensionRatings = computed(() => {
  const scores = evaluation.value?.dimension_scores || {};
  const fromEvaluation = Object.entries(scores)
    .slice(0, 5)
    .map(([key, value]) => ({
      label: localizeDimensionKey(key),
      stars: toStarScore(value),
    }));
  return fromEvaluation;
});

const resumeTags = computed(() => {
  const skills = normalizeStringArray(normalizedProfile.value.skills).slice(0, 6);
  const base = [
    candidateTitle(selectedCandidate.value),
    selectedCandidate.value?.candidate.degree,
    selectedCandidate.value?.candidate.school,
    selectedCandidate.value?.channel,
    ...skills,
  ].filter(Boolean) as string[];
  return Array.from(new Set(base)).slice(0, 6);
});

const resumeDownloadUrl = computed(() => {
  if (!selectedCandidateId.value || !resumeAttachment.value) {
    return null;
  }
  // Use MinIO URL directly
  return resumeAttachment.value.object_storage_url;
});

const workTimeline = computed(() => {
  const workItems = firstArray(
    normalizedProfile.value.work_experiences,
    parsedProfile.value.work_experiences,
    normalizedProfile.value.work_history,
    parsedProfile.value.work_history,
    parsedProfile.value.experiences,
  );
  return workItems
    .map((item: any) => ({
      period: firstText(item.period, item.duration, joinPeriod(item.start_date, item.end_date), item.start, item.end),
      company: firstText(item.company, item.company_name, item.employer),
      title: firstText(item.title, item.role, item.position),
      points: normalizeStringArray(item.responsibilities || item.highlights || item.achievements || item.summary || item.description),
    }))
    .filter((item: any) => item.period || item.company || item.title || item.points.length);
});

const projectCard = computed(() => {
  const projects = firstArray(
    normalizedProfile.value.projects,
    parsedProfile.value.projects,
    normalizedProfile.value.project_experiences,
    parsedProfile.value.project_experiences,
  );
  const first = projects[0] || {};
  return {
    title: firstText(first.name, first.title),
    period: firstText(first.period, joinPeriod(first.start_date, first.end_date)),
    role: firstText(first.role, first.position),
    description: firstText(first.summary, first.description),
  };
});

const offerDescription = computed(() => {
  return firstText(selectedCandidate.value?.source_status, selectedCandidate.value?.latest_delivery?.status) || "暂无 Offer / 入职数据";
});

watch(
  jobId,
  async () => {
    await loadBoard();
  },
  { immediate: true }
);

watch(routeCandidateId, (nextCandidateId) => {
  if (!nextCandidateId || nextCandidateId === selectedCandidateId.value || !allCandidates.value.length) {
    return;
  }
  if (allCandidates.value.some((item) => item.candidate.id === nextCandidateId)) {
    void handleSelectCandidate(nextCandidateId, false);
  }
});

watch(filteredCandidates, (list) => {
  if (currentPage.value > totalPages.value) {
    currentPage.value = totalPages.value;
  }
  if (!list.length) {
    selectedCandidateId.value = "";
    selectedCandidateDetail.value = null;
    evaluation.value = null;
    deliveries.value = [];
    resumeProfile.value = null;
    resumeAttachment.value = null;
    return;
  }
  if (!list.some((item) => item.candidate.id === selectedCandidateId.value)) {
    void handleSelectCandidate(list[0].candidate.id);
  }
});

watch([debouncedKeyword, stageFilter, jobFilter], async () => {
  currentPage.value = 1;
  await refreshCandidates();
});

watch(
  () => [selectedCandidateId.value, activeTab.value] as const,
  ([candidateId, tab]) => {
    if (!candidateId) {
      return;
    }
    if (tab === "resume" || tab === "basic") {
      void ensureResumeProfileLoaded(candidateId);
    }
    if (tab === "communication") {
      void ensureDeliveriesLoaded(candidateId);
    }
    if (tab === "evaluation" && !evaluation.value) {
      void ensureEvaluationLoaded(candidateId);
    }
  },
  { immediate: true }
);

async function loadBoard(): Promise<void> {
  if (!jobId.value) {
    job.value = null;
    allCandidates.value = [];
    selectedCandidateId.value = "";
    selectedCandidateDetail.value = null;
    evaluation.value = null;
    deliveries.value = [];
    resumeProfile.value = null;
    resumeAttachment.value = null;
    resumeProfileCache.clear();
    resumeAttachmentCache.clear();
    deliveriesCache.clear();
    evaluationCache.clear();
    return;
  }

  isBoardLoading.value = true;
  boardError.value = "";

  try {
    const jobRes = await getJob(jobId.value);
    job.value = jobRes;
    await refreshCandidates();
  } catch (error) {
    boardError.value = error instanceof Error ? error.message : "加载数据失败";
  } finally {
    isBoardLoading.value = false;
  }
}

async function refreshCandidates(): Promise<void> {
  if (!jobId.value) return;

  isListLoading.value = true;
  try {
    // Load first 50 for quick display, frontend pagination
    const listRes = await listJobCandidates(jobId.value, {
      limit: 50,
      keyword: debouncedKeyword.value,
      stage: stageFilter.value === "all" ? undefined : stageFilter.value,
    });

    allCandidates.value = listRes.candidates || [];
    
    // Save total count for display
    totalCandidates.value = listRes.total || 0;
    
    resumeProfileCache.clear();
    resumeAttachmentCache.clear();
    deliveriesCache.clear();
    evaluationCache.clear();
    for (const item of listRes.candidates || []) {
      evaluationCache.set(item.candidate.id, item.evaluation || null);
    }

    const nextId =
      (routeCandidateId.value && listRes.candidates.some((item) => item.candidate.id === routeCandidateId.value) && routeCandidateId.value) ||
      listRes.candidates[0]?.candidate.id ||
      "";

    if (!nextId) {
      selectedCandidateId.value = "";
      selectedCandidateDetail.value = null;
      evaluation.value = null;
      deliveries.value = [];
      resumeProfile.value = null;
      resumeAttachment.value = null;
      return;
    }

    void handleSelectCandidate(nextId, true);
  } catch (error) {
    console.error("加载候选人失败", error);
    boardError.value = error instanceof Error ? error.message : "加载候选人失败";
  } finally {
    isListLoading.value = false;
  }
}

async function handleSyncCandidates(): Promise<void> {
  if (!jobId.value || isSyncing.value) {
    return;
  }

  isSyncing.value = true;
  try {
    await syncJobCandidates(jobId.value, {
      max_pages: 5,
      auto_request_resume: true,
      auto_sync_resume_attachment: true,
      reset_cursor: false,
    });
    await loadBoard();
  } catch (error) {
    console.error("同步候选人失败", error);
    boardError.value = error instanceof Error ? error.message : "同步候选人失败";
  } finally {
    isSyncing.value = false;
  }
}

async function handleSyncResume(): Promise<void> {
  if (!selectedCandidateId.value || isLoadingAttachment.value) {
    return;
  }

  isLoadingAttachment.value = true;
  try {
    const result = await syncCandidateResumeAttachment(selectedCandidateId.value);
    resumeAttachment.value = result.attachment;
    resumeAttachmentCache.set(selectedCandidateId.value, result.attachment);
  } catch (error) {
    console.error("同步简历失败", error);
    alert(error instanceof Error ? error.message : "同步简历失败");
  } finally {
    isLoadingAttachment.value = false;
  }
}

async function handleSelectCandidate(candidateId: string, syncRoute = true): Promise<void> {
  if (!jobId.value || !candidateId) {
    return;
  }

  selectedCandidateId.value = candidateId;
  activeTab.value = activeTab.value || "resume";

  if (syncRoute && routeCandidateId.value !== candidateId) {
    router.replace({
      query: {
        ...route.query,
        candidateId,
      },
    });
  }

  selectedCandidateDetail.value = allCandidates.value.find((item) => item.candidate.id === candidateId) || null;
  evaluation.value = evaluationCache.get(candidateId) ?? selectedCandidateDetail.value?.evaluation ?? null;
  deliveries.value = deliveriesCache.get(candidateId) || [];
  resumeProfile.value = resumeProfileCache.get(candidateId) ?? null;
  resumeAttachment.value = resumeAttachmentCache.get(candidateId) ?? null;

  if (activeTab.value === "resume" || activeTab.value === "basic") {
    void ensureResumeProfileLoaded(candidateId);
    void ensureResumeAttachmentLoaded(candidateId);
  }
  if (activeTab.value === "communication") {
    void ensureDeliveriesLoaded(candidateId);
  }
  if (activeTab.value === "evaluation" && !evaluation.value) {
    void ensureEvaluationLoaded(candidateId);
  }
}

async function refreshEvaluation(): Promise<void> {
  if (!jobId.value || !selectedCandidateId.value || isAnalyzing.value) {
    return;
  }

  isAnalyzing.value = true;
  try {
    const result = await evaluateJobCandidate(jobId.value, selectedCandidateId.value, {
      force_refresh: true,
      evaluation_version: "v1",
    });
    evaluation.value = result.evaluation;
    evaluationCache.set(selectedCandidateId.value, result.evaluation);
    patchCandidateCaches(selectedCandidateId.value, { evaluation: result.evaluation });
  } finally {
    isAnalyzing.value = false;
  }
}

async function advanceStage(): Promise<void> {
  if (!jobId.value || !selectedCandidate.value || isAdvancingStage.value) {
    return;
  }

  const next = nextStage(selectedCandidate.value.stage);
  if (!next || next === selectedCandidate.value.stage) {
    return;
  }

  isAdvancingStage.value = true;
  try {
    const updated = await updateCandidateStage(jobId.value, selectedCandidate.value.candidate.id, next);
    selectedCandidateDetail.value = updated;
    patchCandidateCaches(updated.candidate.id, updated);
  } finally {
    isAdvancingStage.value = false;
  }
}

function showInviteDialog(): void {
  if (!selectedCandidate.value?.candidate.email) {
    alert('候选人没有邮箱，无法发送面试邀请');
    return;
  }
  showInviteModal.value = true;
}

async function handleSendInvite(): Promise<void> {
  if (!jobId.value || !selectedCandidateId.value || isSendingInvite.value) {
    return;
  }

  isSendingInvite.value = true;
  try {
    const result = await sendCandidateInvitationEmail(jobId.value, selectedCandidateId.value, {
      evaluation_id: evaluation.value?.id || undefined,
    });
    
    showInviteModal.value = false;
    alert(`面试邀请已发送至 ${result.to_email}`);
    
    // Refresh candidate data
    await refreshCandidates();
  } catch (error) {
    console.error('发送面试邀请失败', error);
    alert(error instanceof Error ? error.message : '发送面试邀请失败');
  } finally {
    isSendingInvite.value = false;
  }
}

async function ensureResumeProfileLoaded(candidateId: string): Promise<void> {
  if (resumeProfileCache.has(candidateId)) {
    if (candidateId === selectedCandidateId.value) {
      resumeProfile.value = resumeProfileCache.get(candidateId) ?? null;
    }
    return;
  }

  isCandidateLoading.value = true;
  try {
    const result = await fetchCandidateResumeProfile(candidateId);
    resumeProfileCache.set(candidateId, result.profile);
    if (candidateId === selectedCandidateId.value) {
      resumeProfile.value = result.profile;
    }
  } catch {
    resumeProfileCache.set(candidateId, null);
    if (candidateId === selectedCandidateId.value) {
      resumeProfile.value = null;
    }
  } finally {
    isCandidateLoading.value = false;
  }
}

async function ensureResumeAttachmentLoaded(candidateId: string): Promise<void> {
  if (resumeAttachmentCache.has(candidateId)) {
    if (candidateId === selectedCandidateId.value) {
      resumeAttachment.value = resumeAttachmentCache.get(candidateId) ?? null;
    }
    return;
  }

  isLoadingAttachment.value = true;
  try {
    const attachment = await fetchCandidateResumeAttachment(candidateId);
    resumeAttachmentCache.set(candidateId, attachment);
    if (candidateId === selectedCandidateId.value) {
      resumeAttachment.value = attachment;
    }
  } catch {
    resumeAttachmentCache.set(candidateId, null);
    if (candidateId === selectedCandidateId.value) {
      resumeAttachment.value = null;
    }
  } finally {
    isLoadingAttachment.value = false;
  }
}

async function ensureDeliveriesLoaded(candidateId: string): Promise<void> {
  if (!jobId.value) {
    return;
  }
  if (deliveriesCache.has(candidateId)) {
    if (candidateId === selectedCandidateId.value) {
      deliveries.value = deliveriesCache.get(candidateId) || [];
    }
    return;
  }

  isCandidateLoading.value = true;
  try {
    const result = await fetchJobEmailDeliveries(jobId.value, candidateId, 20);
    deliveriesCache.set(candidateId, result.items || []);
    if (candidateId === selectedCandidateId.value) {
      deliveries.value = result.items || [];
    }
  } catch {
    deliveriesCache.set(candidateId, []);
    if (candidateId === selectedCandidateId.value) {
      deliveries.value = [];
    }
  } finally {
    isCandidateLoading.value = false;
  }
}

async function ensureEvaluationLoaded(candidateId: string): Promise<void> {
  if (!jobId.value) {
    return;
  }
  if (evaluationCache.has(candidateId) && evaluationCache.get(candidateId)) {
    if (candidateId === selectedCandidateId.value) {
      evaluation.value = evaluationCache.get(candidateId) || null;
    }
    return;
  }

  isCandidateLoading.value = true;
  try {
    const result = await fetchLatestJobCandidateEvaluation(jobId.value, candidateId);
    evaluationCache.set(candidateId, result.evaluation);
    patchCandidateCaches(candidateId, { evaluation: result.evaluation });
    if (candidateId === selectedCandidateId.value) {
      evaluation.value = result.evaluation;
    }
  } catch {
    evaluationCache.set(candidateId, null);
    if (candidateId === selectedCandidateId.value) {
      evaluation.value = null;
    }
  } finally {
    isCandidateLoading.value = false;
  }
}

function patchCandidateCaches(candidateId: string, patch: Partial<JobCandidate>): void {
  allCandidates.value = allCandidates.value.map((item) => (item.candidate.id === candidateId ? { ...item, ...patch } : item));
  if (selectedCandidateDetail.value?.candidate.id === candidateId) {
    selectedCandidateDetail.value = { ...selectedCandidateDetail.value, ...patch };
  }
}

function openDetailPage(): void {
  if (!jobId.value || !selectedCandidateId.value) {
    return;
  }
  router.push(`/admin/candidate-detail?jobId=${jobId.value}&candidateId=${selectedCandidateId.value}`);
}

function getStageText(stage?: string | null): string {
  const match = stageOptions.find((item) => item.value === stage);
  return match?.label || stage || "待处理";
}

function getRecommendationText(value: string): string {
  switch (value) {
    case "strong_recommend":
      return "强烈推荐";
    case "recommend":
      return "推荐";
    case "review":
      return "待复核";
    case "reject":
      return "不推荐";
    default:
      return "--";
  }
}

function candidateTitle(item?: JobCandidate | null): string {
  return firstText(
    item?.source_payload?.desired_position,
    item?.source_payload?.position,
    item?.source_payload?.title,
    item?.candidate.latest_company,
    item?.candidate.school,
    job.value?.title,
  ) || "--";
}

function initials(value?: string | null): string {
  const raw = String(value || "候选人").trim();
  return raw.slice(0, Math.min(2, raw.length)).toUpperCase();
}

function getCandidateAvatar(candidate: any): string | null {
  if (!candidate) return null;
  const rawProfile = candidate.raw_profile || {};
  const avatarUrl = rawProfile.avatar;
  
  // Debug log
  if (avatarUrl) {
    console.log('候选人头像URL:', candidate.name, avatarUrl);
  }
  
  if (avatarUrl && typeof avatarUrl === 'string' && avatarUrl.startsWith('http')) {
    return avatarUrl;
  }
  return null;
}

function avatarStyle(seed?: string | null): Record<string, string> {
  const value = Array.from(String(seed || "AI")).reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const hue = value % 360;
  return {
    background: `linear-gradient(135deg, hsl(${hue} 78% 62%), hsl(${(hue + 36) % 360} 72% 78%))`,
  };
}

function stageTone(stage?: string | null): string {
  switch (stage) {
    case "offer":
      return "tone-green";
    case "rejected":
      return "tone-gray";
    case "screen_pass":
      return "tone-lime";
    case "interview":
      return "tone-blue";
    default:
      return "tone-amber";
  }
}

function pickProfileValue(raw: Record<string, unknown> | undefined, keys: string[], ...extra: unknown[]): string {
  if (raw) {
    for (const key of keys) {
      const value = raw[key];
      const text = firstText(value);
      if (text) {
        return text;
      }
    }
  }
  const text = firstText(...extra);
  return text || "--";
}

function firstText(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      return String(value);
    }
  }
  return "";
}

function firstArray(...values: unknown[]): any[] {
  for (const value of values) {
    if (Array.isArray(value) && value.length) {
      return value;
    }
  }
  return [];
}

function normalizeStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === "string") {
          return item.trim();
        }
        if (item && typeof item === "object") {
          return firstText((item as any).name, (item as any).title, (item as any).summary, (item as any).description);
        }
        return "";
      })
      .filter(Boolean);
  }
  const text = firstText(value);
  return text ? [text] : [];
}

function joinPeriod(start?: unknown, end?: unknown): string {
  const startText = firstText(start);
  const endText = firstText(end) || "至今";
  if (!startText && !endText) {
    return "";
  }
  if (!startText) {
    return endText === "至今" ? "" : endText;
  }
  return `${startText} - ${endText}`;
}

function formatShortDate(value?: string | null): string {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function formatDateTime(value?: string | null): string {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function localizeDimensionKey(key: string): string {
  const map: Record<string, string> = {
    domain_knowledge: "专业能力",
    role_fit: "岗位匹配度",
    communication: "沟通表达",
    learning_agility: "学习能力",
    culture_fit: "综合素质",
  };
  return map[key] || key.replace(/_/g, " ");
}

function toStarScore(value: unknown): number {
  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(numeric)) {
    return 4;
  }
  if (numeric <= 5) {
    return Math.max(1, Math.round(numeric));
  }
  return Math.max(1, Math.min(5, Math.round(numeric / 20)));
}

function localizeEvaluationText(value?: string | null): string {
  if (!value) {
    return "";
  }
  const map: Record<string, string> = {
    candidate_shows_direct_stack_overlap: "候选人与岗位技术栈高度重合",
  };
  return map[value] || value;
}

function maskPhone(payload: any): string {
  const values = [
    payload?.mobile,
    payload?.phone,
    payload?.phone_number,
    payload?.contact_phone,
  ].filter((item) => typeof item === "string" && item.trim()) as string[];

  const value = values[0];
  if (!value) {
    return "--";
  }
  const digits = value.replace(/\D/g, "");
  if (digits.length < 7) {
    return value;
  }
  return `${digits.slice(0, 3)}****${digits.slice(-4)}`;
}

function nextStage(current: string): string {
  const order = ["new", "parsed", "screen_pass", "interview", "offer"];
  const index = order.indexOf(current);
  if (index === -1 || index === order.length - 1) {
    return current;
  }
  return order[index + 1];
}
</script>

<style scoped>
.candidate-board {
  min-height: calc(100vh - 104px);
}

.candidate-layout {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

.candidate-panel {
  border: 1px solid #edf2fa;
  background: #ffffff;
  border-radius: 16px;
  box-shadow: 0 12px 40px rgba(34, 54, 88, 0.05);
}

.candidate-empty {
  min-height: 420px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 12px;
  color: #6f7c90;
  text-align: center;
}

.candidate-empty h2 {
  margin: 0;
  color: #1a2332;
  font-size: 24px;
  font-weight: 700;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border-radius: 999px;
  border: 3px solid #d7e3fb;
  border-top-color: #2b6ff6;
  animation: spin 0.9s linear infinite;
}

.roster-panel {
  padding: 14px;
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 104px);
}

.roster-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: start;
  margin-bottom: 16px;
  position: relative;
}

.sync-btn {
  position: absolute;
  top: 0;
  right: 0;
  padding: 6px 14px;
  background: #ef4444;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 1px 3px rgba(239, 68, 68, 0.2);
}

.sync-btn:hover:not(:disabled) {
  background: #dc2626;
  box-shadow: 0 2px 6px rgba(239, 68, 68, 0.3);
  transform: translateY(-1px);
}

.sync-btn:active:not(:disabled) {
  transform: translateY(0);
  box-shadow: 0 1px 2px rgba(239, 68, 68, 0.2);
}

.sync-btn:disabled {
  background: #fca5a5;
  cursor: not-allowed;
  opacity: 0.7;
}

.eyebrow {
  margin: 0 0 6px;
  color: #2b6ff6;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.roster-header h2 {
  margin: 0;
  font-size: 16px;
  line-height: 24px;
  font-weight: 700;
  color: #1a2332;
}

.roster-job {
  margin: 5px 0 0;
  color: #93a0b2;
  font-size: 12px;
  text-align: right;
}

.search-box {
  position: relative;
  display: block;
  margin-bottom: 12px;
}

.search-box svg {
  position: absolute;
  left: 12px;
  top: 50%;
  width: 16px;
  height: 16px;
  transform: translateY(-50%);
  color: #a9b4c4;
}

.search-box input,
.filter-row select {
  width: 100%;
  height: 36px;
  border: 1px solid #e6edf7;
  border-radius: 8px;
  background: #ffffff;
  color: #1a2332;
  font-size: 13px;
}

.search-box input {
  padding: 0 14px 0 38px;
}

.filter-row {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 8px;
  margin-bottom: 14px;
}

.filter-row select {
  padding: 0 10px;
}

.filter-trigger {
  min-width: 64px;
  height: 36px;
  border: 1px solid #e6edf7;
  border-radius: 8px;
  background: #fff;
  color: #526178;
  font-size: 13px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.filter-trigger svg {
  width: 14px;
  height: 14px;
}

.roster-meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
  color: #8d98aa;
  font-size: 13px;
}

.roster-list {
  flex: 1;
  overflow: auto;
  padding-right: 4px;
}

.candidate-card {
  width: 100%;
  display: flex;
  gap: 12px;
  padding: 14px 12px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: #fff;
  text-align: left;
  transition: 0.2s ease;
  margin-bottom: 8px;
}

.candidate-card:hover {
  background: #f9fbff;
  border-color: #e0ebfd;
}

.candidate-card.active {
  background: #edf3fb;
  border-color: #d9e7ff;
  box-shadow: inset 0 0 0 1px rgba(43, 111, 246, 0.04);
}

.candidate-avatar,
.hero-avatar,
.resume-mini-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.candidate-avatar {
  width: 48px;
  height: 48px;
  border-radius: 999px;
  font-size: 15px;
  flex-shrink: 0;
}

.candidate-copy {
  min-width: 0;
  flex: 1;
}

.candidate-name-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: start;
  margin-bottom: 4px;
}

.candidate-name {
  color: #1a2332;
  font-size: 14px;
  font-weight: 700;
}

.status-pill,
.hero-stage {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 20px;
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.tone-blue {
  color: #2b6ff6;
  background: rgba(43, 111, 246, 0.1);
}

.tone-green {
  color: #12a868;
  background: rgba(18, 168, 104, 0.12);
}

.tone-lime {
  color: #45ad60;
  background: rgba(69, 173, 96, 0.12);
}

.tone-amber {
  color: #f59f26;
  background: rgba(245, 159, 38, 0.12);
}

.tone-gray {
  color: #7f8c9f;
  background: #f1f4f8;
}

.candidate-role,
.candidate-updated {
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.candidate-role {
  color: #526178;
  font-size: 13px;
  margin-bottom: 6px;
}

.candidate-updated {
  color: #99a5b5;
  font-size: 12px;
}

.roster-empty {
  min-height: 180px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #99a5b5;
  font-size: 13px;
}

.pagination-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  justify-content: center;
  padding-top: 10px;
  border-top: 1px solid #f0f3f9;
  color: #8e9aac;
  font-size: 12px;
}

.page-btn,
.page-arrow,
.mini-icon-btn {
  border: 1px solid #e5eaf2;
  background: #fff;
  color: #738196;
}

.page-btn,
.page-arrow {
  height: 28px;
  min-width: 28px;
  border-radius: 8px;
  font-size: 12px;
}

.page-btn.active {
  background: #2b6ff6;
  border-color: #2b6ff6;
  color: #fff;
}

.detail-area {
  min-width: 0;
  position: relative;
}

.detail-loading {
  position: sticky;
  top: 0;
  z-index: 3;
  margin-bottom: 12px;
  padding: 10px 14px;
  border: 1px solid rgba(43, 111, 246, 0.12);
  border-radius: 12px;
  background: rgba(247, 250, 255, 0.96);
  color: #2b6ff6;
  font-size: 13px;
  font-weight: 600;
  backdrop-filter: blur(8px);
}

.hero-card {
  padding: 24px 26px 0;
  margin-bottom: 14px;
}

.hero-card,
.hero-main,
.hero-actions,
.detail-card-head,
.side-card-head,
.score-meta,
.delivery-top,
.project-head,
.project-page {
  display: flex;
  align-items: center;
}

.hero-card {
  flex-direction: column;
  align-items: stretch;
}

.hero-main {
  justify-content: space-between;
  gap: 24px;
  align-items: flex-start;
}

.hero-avatar {
  width: 78px;
  height: 78px;
  border-radius: 999px;
  font-size: 24px;
  box-shadow: 0 14px 28px rgba(43, 111, 246, 0.18);
}

.hero-copy {
  min-width: 0;
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  column-gap: 24px;
  row-gap: 10px;
  align-items: start;
}

.hero-name-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.hero-name-row h1 {
  margin: 0;
  color: #1a2332;
  font-size: 24px;
  line-height: 1.2;
  font-weight: 700;
}

.verified-chip {
  color: #2b6ff6;
  width: 20px;
  height: 20px;
}

.verified-chip svg {
  display: block;
  width: 20px;
  height: 20px;
}

.hero-stage {
  min-height: 28px;
  padding: 4px 12px;
  font-size: 13px;
}

.hero-subline {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  color: #5e6d85;
  font-size: 14px;
  margin-bottom: 16px;
  grid-column: 1;
}

.hero-contact {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px 14px;
  grid-column: 1 / -1;
}

.hero-contact-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: #61708c;
  font-size: 14px;
}

.hero-contact-item svg {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.hero-contact-item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hero-actions {
  gap: 12px;
  align-self: start;
  justify-self: end;
  grid-column: 2;
  grid-row: 1 / span 2;
}

.ghost-btn,
.primary-btn,
.inline-link,
.inline-expand {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  transition: 0.2s ease;
}

.ghost-btn {
  height: 40px;
  padding: 0 16px;
  background: #fff;
  border: 1px solid #dfe7f4;
  color: #44546d;
}

.ghost-btn:hover,
.filter-trigger:hover,
.page-btn:hover,
.page-arrow:hover,
.mini-icon-btn:hover {
  border-color: #2b6ff6;
  color: #2b6ff6;
}

.primary-btn {
  height: 40px;
  padding: 0 18px;
  border: 1px solid #2b6ff6;
  background: #2b6ff6;
  color: #fff;
}

.primary-btn:hover {
  background: #1f61e7;
}

.primary-btn.compact {
  height: 34px;
  padding: 0 14px;
  font-size: 13px;
}

.ghost-btn:disabled,
.primary-btn:disabled,
.page-arrow:disabled,
.mini-icon-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.ghost-btn.full {
  width: 100%;
}

.hero-tabs {
  display: flex;
  gap: 32px;
  margin-top: 22px;
  border-top: 1px solid #eef2f7;
  overflow-x: auto;
}

.hero-tab {
  position: relative;
  height: 52px;
  border: 0;
  background: transparent;
  color: #6f7c90;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
}

.hero-tab.active {
  color: #2b6ff6;
  font-weight: 600;
}

.hero-tab.active::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 2px;
  border-radius: 999px;
  background: #2b6ff6;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 328px;
  gap: 14px;
}

.content-main,
.content-side {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.resume-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(280px, 0.92fr);
  gap: 14px;
}

.detail-card,
.side-card {
  padding: 18px 20px;
}

.detail-card-head,
.side-card-head {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.detail-card-head h3,
.side-card-head h3 {
  margin: 0;
  color: #1a2332;
  font-size: 16px;
  font-weight: 700;
}

.inline-link,
.inline-expand {
  border: 0;
  background: transparent;
  padding: 0;
  color: #2b6ff6;
  font-size: 14px;
}

.inline-link svg,
.inline-expand svg {
  width: 16px;
  height: 16px;
}

.resume-preview {
  border: 1px solid #e8edf6;
  border-radius: 12px;
  background: #f6f9fd;
  overflow: hidden;
}

.resume-paper {
  min-height: 380px;
  margin: 18px;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 14px 32px rgba(38, 52, 77, 0.08);
  overflow: hidden;
}

.resume-sheet-head {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 16px 18px;
  background: linear-gradient(180deg, #f7fbff, #ffffff);
  border-bottom: 1px solid #edf2fa;
}

.resume-mini-avatar {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  font-size: 14px;
}

.resume-sheet-head strong {
  display: block;
  color: #1a2332;
  font-size: 18px;
  margin-bottom: 4px;
}

.resume-sheet-head p {
  margin: 0;
  color: #8996a9;
  font-size: 12px;
}

.resume-body-scroll {
  padding: 16px 18px;
  max-height: 280px;
  overflow-y: auto;
  scrollbar-width: none;
}

.resume-body-scroll::-webkit-scrollbar {
  display: none;
}

.resume-mini-section {
  margin-bottom: 20px;
}

.resume-mini-item {
  margin-bottom: 12px;
}

.resume-mini-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 3px;
}

.resume-mini-head strong {
  font-size: 13px;
  color: #1a2332;
  font-weight: 700;
}

.resume-mini-head span {
  font-size: 11px;
  color: #93a0b2;
}

.resume-mini-item p {
  margin: 0;
  font-size: 12px;
  color: #5e6d85;
  line-height: 1.5;
}

.resume-mini-desc {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}

.resume-lines-placeholder {
  padding: 18px;
}

.resume-line-item {
  height: 8px;
  width: 72%;
  border-radius: 999px;
  background: #edf2f9;
  margin-bottom: 9px;
}

.resume-line-item.wide {
  width: 92%;
}

.resume-line-item.short {
  width: 46%;
}

.resume-tag-row {
  padding: 0 18px 18px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.resume-tag-row span {
  padding: 4px 8px;
  border-radius: 999px;
  background: #f1f5fb;
  color: #66768d;
  font-size: 11px;
}

.resume-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  border-top: 1px solid #edf2fa;
  background: #fff;
  color: #7e8ca0;
  font-size: 13px;
}

.toolbar-icons,
.project-page {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.mini-icon-btn {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.mini-icon-btn svg {
  width: 15px;
  height: 15px;
}

.info-table {
  display: grid;
  gap: 14px;
}

.info-row {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 12px;
  font-size: 14px;
}

.info-row span {
  color: #8d9aad;
}

.info-row strong {
  color: #253146;
  font-weight: 600;
}

.wide-card {
  min-width: 0;
}

.timeline-list {
  position: relative;
  padding-left: 4px;
}

.timeline-item {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 14px;
}

.timeline-item + .timeline-item {
  margin-top: 18px;
}

.timeline-rail {
  position: relative;
}

.timeline-rail::after {
  content: "";
  position: absolute;
  left: 11px;
  top: 10px;
  bottom: -18px;
  width: 2px;
  background: #e4e9f1;
}

.timeline-item:last-child .timeline-rail::after {
  display: none;
}

.timeline-dot {
  display: block;
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: #2b6ff6;
  box-shadow: 0 0 0 4px rgba(43, 111, 246, 0.08);
  margin-top: 8px;
}

.timeline-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.timeline-period {
  color: #2b6ff6;
  font-size: 13px;
  font-weight: 700;
}

.timeline-head strong {
  color: #1f2b3b;
  font-size: 14px;
  font-weight: 700;
}

.timeline-role {
  margin: 0 0 10px;
  color: #60708a;
  font-size: 14px;
  font-weight: 600;
}

.timeline-body ul,
.eval-section ul {
  margin: 0;
  padding-left: 18px;
  color: #5c6b83;
}

.timeline-body li,
.eval-section li {
  margin-bottom: 8px;
  line-height: 1.65;
  font-size: 13px;
}

.project-head {
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.project-head strong {
  color: #1a2332;
  font-size: 18px;
}

.project-head span {
  color: #8c99ac;
  font-size: 13px;
}

.project-role {
  margin: 0 0 10px;
  color: #2b6ff6;
  font-size: 14px;
  font-weight: 700;
}

.project-desc {
  margin: 0;
  color: #5d6b81;
  line-height: 1.8;
  font-size: 14px;
}

.profile-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.profile-chip,
.log-item,
.delivery-item,
.offer-panel,
.blank-card,
.eval-section {
  border: 1px solid #edf2fa;
  border-radius: 12px;
  background: #fafcff;
}

.profile-chip {
  padding: 14px 16px;
}

.profile-chip span,
.log-item span,
.delivery-item p {
  display: block;
  color: #8a97ab;
  font-size: 12px;
}

.profile-chip strong,
.log-item strong,
.delivery-item strong,
.offer-stage {
  display: block;
  color: #1f2b3b;
  font-size: 14px;
  font-weight: 700;
  margin-top: 6px;
}

.eval-stack {
  display: grid;
  gap: 14px;
}

.eval-section {
  padding: 16px;
}

.eval-label {
  display: block;
  margin-bottom: 8px;
  color: #2b6ff6;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.eval-section p {
  margin: 0;
  color: #5b6b83;
  font-size: 14px;
  line-height: 1.8;
}

.log-list,
.delivery-list {
  display: grid;
  gap: 12px;
}

.log-item,
.delivery-item,
.offer-panel,
.blank-card {
  padding: 16px;
}

.delivery-top {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  color: #8a97ab;
  font-size: 12px;
}

.delivery-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  background: #eef4ff;
  color: #2b6ff6;
  font-weight: 700;
}

.offer-panel p,
.blank-card {
  margin: 0;
  color: #5f6f87;
  line-height: 1.8;
  font-size: 14px;
}

.score-panel {
  display: grid;
  justify-items: center;
}

.score-ring {
  position: relative;
  width: 120px;
  height: 120px;
  margin: 6px 0 18px;
}

.score-ring svg {
  width: 120px;
  height: 120px;
  transform: rotate(-90deg);
}

.ring-base {
  fill: none;
  stroke: #edf1f7;
  stroke-width: 8;
}

.ring-value {
  fill: none;
  stroke: #2b6ff6;
  stroke-width: 8;
  stroke-linecap: round;
}

.score-inner {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.score-inner strong {
  color: #2b6ff6;
  font-size: 22px;
  line-height: 1;
}

.score-inner span {
  margin-top: 6px;
  color: #7b899d;
  font-size: 13px;
}

.score-copy {
  width: 100%;
  text-align: left;
  margin-bottom: 14px;
}

.score-recommend {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
  color: #60708a;
  font-size: 14px;
}

.score-recommend strong {
  color: #44ad63;
  font-size: 15px;
}

.score-copy p {
  margin: 0;
  color: #5d6b81;
  line-height: 1.8;
  font-size: 14px;
}

.score-meta {
  width: 100%;
  flex-direction: column;
  align-items: start;
  gap: 8px;
  padding: 14px 0 16px;
  color: #8d98aa;
  font-size: 12px;
}

.dimension-list {
  display: grid;
  gap: 14px;
}

.dimension-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  color: #344154;
  font-size: 14px;
}

.stars {
  display: inline-flex;
  gap: 4px;
}

.star {
  width: 16px;
  height: 16px;
  fill: #e7ebf2;
}

.star.active {
  fill: #ffb020;
}

.inline-expand {
  width: 100%;
  justify-content: center;
  margin-top: 18px;
}

.search-box input:focus,
.filter-row select:focus {
  outline: none;
  border-color: #2b6ff6;
  box-shadow: 0 0 0 4px rgba(43, 111, 246, 0.08);
}

.roster-list::-webkit-scrollbar,
.hero-tabs::-webkit-scrollbar {
  height: 6px;
  width: 6px;
}

.roster-list::-webkit-scrollbar-thumb,
.hero-tabs::-webkit-scrollbar-thumb {
  background: #d7deea;
  border-radius: 999px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 1380px) {
  .hero-main {
    flex-direction: column;
    align-items: stretch;
  }

  .hero-copy {
    grid-template-columns: minmax(0, 1fr);
  }

  .hero-actions {
    grid-column: 1;
    grid-row: auto;
    justify-self: start;
    align-self: stretch;
    flex-wrap: wrap;
  }

  .hero-contact {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .content-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .content-side {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 1120px) {
  .candidate-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .roster-panel {
    min-height: auto;
  }

  .resume-grid,
  .profile-grid,
  .content-side {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 768px) {
  .hero-card {
    padding: 18px 18px 0;
  }

  .hero-contact {
    grid-template-columns: minmax(0, 1fr);
  }

  .filter-row {
    grid-template-columns: minmax(0, 1fr);
  }

  .candidate-name-row,
  .timeline-head,
  .project-head {
    flex-direction: column;
    align-items: start;
  }
}

/* Interview invitation modal styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 12px;
  width: 90%;
  max-width: 480px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid #e5e7eb;
}

.modal-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: #111827;
  margin: 0;
}

.modal-close {
  background: none;
  border: none;
  padding: 4px;
  cursor: pointer;
  color: #6b7280;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-close:hover {
  color: #111827;
}

.modal-close svg {
  width: 20px;
  height: 20px;
}

.modal-body {
  padding: 24px;
}

.form-field {
  margin-bottom: 16px;
}

.form-field label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: #374151;
  margin-bottom: 6px;
}

.form-value {
  font-size: 14px;
  color: #111827;
  padding: 8px 12px;
  background: #f9fafb;
  border-radius: 6px;
}

.form-hint {
  font-size: 13px;
  color: #6b7280;
  margin: 16px 0 0 0;
  padding: 12px;
  background: #f0f9ff;
  border-radius: 6px;
  border-left: 3px solid #3b82f6;
}

.modal-footer {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding: 16px 24px;
  border-top: 1px solid #e5e7eb;
}
</style>
