<template>
  <div class="decision-detail-page">
    <section class="decision-detail-toolbar">
      <button class="ghost-btn" @click="$router.push('/admin/hiring')">
        <span class="material-symbols-outlined">arrow_back</span>
        返回列表
      </button>
      <button class="primary-btn">
        <span class="material-symbols-outlined">ios_share</span>
        导出评估报告
      </button>
    </section>

    <section v-if="isLoading" class="state-panel">
      <div class="loader"></div>
      <p>正在加载录用决策详情...</p>
    </section>

    <section v-else-if="loadError" class="state-panel">
      <p>{{ loadError }}</p>
      <button class="primary-btn" @click="loadData">重试</button>
    </section>

    <template v-else-if="detail">
      <section class="summary-grid">
        <article class="candidate-card">
          <div class="avatar-wrap">
            <img v-if="profile.avatar_url" :src="profile.avatar_url" :alt="profile.candidate_name">
            <span v-else>{{ initials }}</span>
          </div>
          <div class="candidate-main">
            <div class="name-line">
              <h2>{{ profile.candidate_name }}</h2>
              <span class="recommend-pill">{{ recommendationText }}</span>
            </div>
            <p class="role">{{ profile.job_title || "--" }}</p>
            <p class="meta">{{ profile.city || "--" }} · {{ profile.work_experience || "--" }}</p>
            <p class="meta">{{ profile.current_role || "--" }}</p>
            <p class="meta">{{ profile.department || "--" }}</p>
          </div>
        </article>

        <article class="overview-card">
          <h3>综合评估总览</h3>
          <div class="overview-metrics">
            <div class="metric-block">
              <p>简历评分</p>
              <strong class="blue">{{ overview.resume_score.toFixed(1) }}</strong>
              <div class="stars">
                <span v-for="i in 5" :key="`r-${i}`" class="material-symbols-outlined" :class="{ active: i <= toStars(overview.resume_score) }">star</span>
              </div>
            </div>
            <div class="metric-block">
              <p>面试评分</p>
              <strong class="green">{{ overview.interview_score.toFixed(1) }}</strong>
              <div class="stars green">
                <span v-for="i in 5" :key="`i-${i}`" class="material-symbols-outlined" :class="{ active: i <= toStars(overview.interview_score) }">star</span>
              </div>
            </div>
            <div class="ring" :style="ringStyle(overview.composite_score)">
              <span>{{ overview.composite_score.toFixed(1) }}</span>
            </div>
            <div class="right-metrics">
              <div class="metric-kv">
                <label>综合评级</label>
                <strong>{{ overview.grade || "--" }}</strong>
              </div>
              <div class="metric-kv">
                <label>推荐结果</label>
                <strong class="green">{{ recommendationResult }}</strong>
              </div>
              <div class="metric-kv">
                <label>推荐薪资</label>
                <strong>{{ overview.recommended_salary || profile.expected_salary || profile.job_salary_range || "--" }}</strong>
              </div>
              <div class="metric-kv">
                <label>更新时间</label>
                <strong>{{ formatDateTime(overview.updated_at) }}</strong>
              </div>
            </div>
          </div>
        </article>
      </section>

      <section class="content-grid">
        <aside class="left-stack">
          <article class="card">
            <h4 class="section-title-bold">基本信息</h4>
            <div class="kv-list">
              <p><label>应聘职位</label><span>{{ profile.job_title || "--" }}</span></p>
              <p><label>所属部门</label><span>{{ profile.department || "--" }}</span></p>
              <p><label>所在城市</label><span>{{ profile.city || "--" }}</span></p>
              <p><label>学历</label><span>{{ profile.degree || "--" }}</span></p>
              <p><label>工作经验</label><span>{{ profile.work_experience || "--" }}</span></p>
              <p><label>手机号</label><span>{{ maskPhone(profile.phone) }}</span></p>
              <p><label>邮箱</label><span>{{ profile.email || "--" }}</span></p>
              <p><label>投递时间</label><span>{{ formatDateTime(profile.applied_at) }}</span></p>
              <p><label>当前流程</label><span class="status-green">{{ stageText(profile.current_stage) }}</span></p>
              <p><label>Offer 薪资</label><span>{{ profile.expected_salary || profile.job_salary_range || "--" }}</span></p>
            </div>
          </article>

          <article class="card">
            <h4>招聘流程</h4>
            <div class="timeline">
              <div v-for="(item, idx) in detail.timeline" :key="`${item.step}-${idx}`" class="timeline-item">
                <div class="dot"></div>
                <div class="timeline-main">
                  <p>{{ item.step }}</p>
                  <span>{{ formatDateTime(item.time) }}</span>
                </div>
                <span class="timeline-tag">{{ item.status || "--" }}</span>
              </div>
            </div>
          </article>
        </aside>

        <section class="main-content">
          <section class="tabs-row">
            <button v-for="tab in tabs" :key="tab.key" class="tab-btn" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">{{ tab.label }}</button>
          </section>

          <template v-if="activeTab === 'detail'">
            <div class="detail-grid">
              <main class="center-stack">
                <section class="assessment-row">
                  <article class="card">
                    <div class="panel-head">
                      <h4 class="section-title-bold">简历评估</h4>
                      <strong>{{ resumePanel.score.toFixed(1) }}/100</strong>
                    </div>
                    <div class="bars">
                      <div v-for="(item, idx) in resumeRawDimensions" :key="`resume-${item.key}-${idx}`" class="bar-line">
                        <label>{{ item.label }}</label>
                        <div class="bar-track"><div class="bar-fill blue" :style="{ width: `${Math.max(0, Math.min(100, item.score))}%` }"></div></div>
                        <span>{{ item.score.toFixed(0) }}/{{ item.max_score.toFixed(0) }}</span>
                      </div>
                    </div>
                    <div class="panel-conclusion">
                      <h5>评估总结</h5>
                      <p>{{ resumePanel.summary || "暂无总结" }}</p>
                    </div>
                  </article>

                  <article class="card">
                    <div class="panel-head">
                      <h4 class="section-title-bold">面试评估</h4>
                      <strong class="green">{{ interviewPanel.score.toFixed(1) }}/100</strong>
                    </div>
                    <div class="bars">
                      <div v-for="(item, idx) in interviewRawDimensions" :key="`interview-${item.key}-${idx}`" class="bar-line">
                        <label>{{ item.label }}</label>
                        <div class="bar-track"><div class="bar-fill green" :style="{ width: `${Math.max(0, Math.min(100, item.score))}%` }"></div></div>
                        <span>{{ item.score.toFixed(0) }}/{{ item.max_score.toFixed(0) }}</span>
                      </div>
                    </div>
                    <div class="panel-conclusion green-bg">
                      <h5>评估总结</h5>
                      <p>{{ interviewPanel.summary || "暂无总结" }}</p>
                    </div>
                  </article>
                </section>

                <section class="bottom-dual">
                  <article class="card">
                    <h4>评估维度对比</h4>
                    <div class="compare-legend">
                      <span><i class="candidate"></i>候选人得分</span>
                      <span><i class="benchmark"></i>岗位标准</span>
                    </div>
                    <div class="compare-list">
                      <div v-for="item in dimensionCompareRows" :key="`compare-${item.label}`" class="compare-row">
                        <label>{{ item.label }}</label>
                        <div class="compare-line">
                          <div class="candidate-line" :style="{ width: `${item.candidate}%` }"></div>
                          <div class="benchmark-mark" :style="{ left: `${item.benchmark}%` }"></div>
                        </div>
                        <span>| {{ item.benchmarkScore.toFixed(0) }}</span>
                      </div>
                    </div>
                  </article>

                  <article class="card">
                    <h4>能力雷达图</h4>
                    <div class="radar-wrap">
                      <svg class="radar-svg" viewBox="0 0 260 230" aria-label="能力雷达图">
                        <polygon
                          v-for="(ring, idx) in radarRings"
                          :key="`ring-${idx}`"
                          :points="ring"
                          class="radar-ring"
                        />
                        <line
                          v-for="(point, idx) in radarVertices"
                          :key="`axis-${idx}`"
                          :x1="radarCenter.x"
                          :y1="radarCenter.y"
                          :x2="point.x"
                          :y2="point.y"
                          class="radar-axis"
                        />
                        <polygon :points="radarPolygonPoints" class="radar-data-fill" />
                        <polyline :points="radarPolygonPoints" class="radar-data-line" />
                        <circle
                          v-for="(point, idx) in radarDataVertices"
                          :key="`dot-${idx}`"
                          :cx="point.x"
                          :cy="point.y"
                          r="3"
                          class="radar-data-dot"
                        />
                        <text
                          v-for="(point, idx) in radarLabelPoints"
                          :key="`label-${idx}`"
                          :x="point.x"
                          :y="point.y"
                          class="radar-label"
                        >
                          {{ point.label }}
                        </text>
                      </svg>
                      <div class="radar-legend">
                        <span><i class="legend-dot"></i>候选人得分</span>
                        <span><i class="legend-box"></i>岗位标准</span>
                      </div>
                    </div>
                  </article>
                </section>
              </main>

              <aside class="right-stack">
                <article class="card compact">
                  <h4 class="section-title-bold">综合评估结果</h4>
                  <div class="compact-ring" :style="ringStyle(compositePanel.score)">
                    <span>{{ compositePanel.score.toFixed(1) }}</span>
                  </div>
                  <div class="compact-kv">
                    <p><label>综合评级</label><span>{{ overview.grade || "--" }}</span></p>
                    <p><label>推荐结果</label><span class="status-green">{{ recommendationResult }}</span></p>
                    <p><label>推荐薪资</label><span>{{ overview.recommended_salary || "--" }}</span></p>
                    <p><label>入职建议</label><span>{{ recommendationHireAdvice }}</span></p>
                  </div>
                  <p class="remark">{{ compositePanel.summary || "暂无综合评估结论" }}</p>
                </article>

                <article class="card">
                  <h4>面试官评价汇总</h4>
                  <div v-if="detail.interviewer_reviews.length === 0" class="empty-tip">暂无面试官评价</div>
                  <div v-for="(item, idx) in detail.interviewer_reviews" :key="`review-${idx}-${item.reviewer}`" class="review-item">
                    <p class="review-title">{{ item.reviewer }}<span>{{ item.stage || "" }}</span></p>
                    <p class="review-comment">{{ item.comment || "--" }}</p>
                    <p class="review-time">{{ formatDateTime(item.time) }}<span v-if="item.score != null"> · {{ item.score.toFixed(1) }}</span></p>
                  </div>
                </article>
              </aside>
            </div>
          </template>

          <section v-else-if="activeTab === 'record'" class="record-card card">
            <h4>面试记录</h4>
            <div v-if="detail.qa_items.length === 0" class="empty-tip">暂无面试问答记录</div>
            <div v-for="(item, idx) in detail.qa_items" :key="`${idx}-${item.question}`" class="qa-item">
              <p class="question">{{ idx + 1 }}. {{ item.question }}</p>
              <p class="answer">{{ item.answer || "候选人尚未作答" }}</p>
              <p class="qa-time">{{ formatDateTime(item.occurred_at) }}</p>
            </div>
          </section>

          <section v-else-if="activeTab === 'report'" class="record-card card">
            <h4>评估报告</h4>
            <p class="report-text">{{ compositePanel.summary || resumePanel.summary || interviewPanel.summary || "暂无评估报告内容" }}</p>
            <ul class="report-list">
              <li v-for="item in mergedReportBullets" :key="item">{{ item }}</li>
            </ul>
          </section>

          <section v-else class="record-card card">
            <h4>操作记录</h4>
            <div v-if="detail.operation_logs.length === 0" class="empty-tip">暂无操作记录</div>
            <div v-for="(item, idx) in detail.operation_logs" :key="`${idx}-${item.type}-${item.title}`" class="log-item">
              <p>{{ item.title }}</p>
              <span>{{ formatDateTime(item.time) }} · {{ item.status || "--" }}</span>
              <em v-if="item.detail">{{ item.detail }}</em>
            </div>
          </section>
        </section>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import {
  fetchHiringDecisionDetail,
  type HiringDecisionAssessmentPanel,
  type HiringDecisionDetailResult,
} from "../../api";

const route = useRoute();
const jobId = ref(String(route.query.jobId || ""));
const candidateId = ref(String(route.query.candidateId || ""));

const isLoading = ref(false);
const loadError = ref("");
const detail = ref<HiringDecisionDetailResult | null>(null);
const activeTab = ref("detail");

const tabs = [
  { key: "detail", label: "评估详情" },
  { key: "record", label: "面试记录" },
  { key: "report", label: "评估报告" },
  { key: "operate", label: "操作记录" },
];

const profile = computed(() => detail.value!.profile);
const overview = computed(() => detail.value!.overview);
const resumePanel = computed<HiringDecisionAssessmentPanel>(() => detail.value!.resume_assessment);
const interviewPanel = computed<HiringDecisionAssessmentPanel>(() => detail.value!.interview_assessment);
const compositePanel = computed<HiringDecisionAssessmentPanel>(() => detail.value!.composite_assessment);

const initials = computed(() => String(profile.value?.candidate_name || "NA").slice(0, 2).toUpperCase());
const recommendationText = computed(() => recommendationLabel(overview.value?.recommendation || ""));
const recommendationResult = computed(() => recommendationResultLabel(overview.value?.recommendation || ""));
const recommendationHireAdvice = computed(() => {
  const rec = String(overview.value?.recommendation || "").toLowerCase();
  if (rec.includes("reject")) return "建议淘汰";
  if (rec.includes("review")) return "建议复核";
  return "建议录用";
});

type DimensionRow = {
  key: string;
  label: string;
  score: number;
  max_score: number;
};

const resumeRawDimensions = computed<DimensionRow[]>(() => mapRawDimensions(resumePanel.value.dimensions || []));
const interviewRawDimensions = computed<DimensionRow[]>(() => mapRawDimensions(interviewPanel.value.dimensions || []));

const radarCenter = { x: 120, y: 108 };
const radarRadius = 74;
const radarAngles = [0, 1, 2, 3, 4, 5].map((idx) => (Math.PI * 2 * idx) / 6 - Math.PI / 2);

const mergedDimensionRows = computed<DimensionRow[]>(() => {
  const merged = new Map<string, { key: string; label: string; scoreSum: number; maxSum: number; count: number }>();
  const addRows = (rows: DimensionRow[]) => {
    rows.forEach((item) => {
      if (!item.key) return;
      const bucket = merged.get(item.key) || {
        key: item.key,
        label: item.label,
        scoreSum: 0,
        maxSum: 0,
        count: 0,
      };
      bucket.scoreSum += Number(item.score || 0);
      bucket.maxSum += Number(item.max_score || 100);
      bucket.count += 1;
      if (!bucket.label && item.label) bucket.label = item.label;
      merged.set(item.key, bucket);
    });
  };
  addRows(resumeRawDimensions.value);
  addRows(interviewRawDimensions.value);
  return Array.from(merged.values())
    .map((item) => ({
      key: item.key,
      label: item.label,
      score: item.count ? item.scoreSum / item.count : 0,
      max_score: item.count ? item.maxSum / item.count : 100,
    }))
    .sort((a, b) => b.score - a.score);
});

const radarAxes = computed(() => mergedDimensionRows.value.slice(0, 6));

function radarVertex(ratio: number, angle: number) {
  const r = radarRadius * ratio;
  return {
    x: radarCenter.x + Math.cos(angle) * r,
    y: radarCenter.y + Math.sin(angle) * r,
  };
}

const radarVertices = computed(() => radarAngles.map((angle) => radarVertex(1, angle)));

const radarRings = computed(() => {
  const levels = [0.25, 0.5, 0.75, 1];
  return levels.map((ratio) =>
    radarAngles
      .map((angle) => radarVertex(ratio, angle))
      .map((point) => `${point.x},${point.y}`)
      .join(" "),
  );
});

const radarDataVertices = computed(() =>
  radarAxes.value.map((axis, idx) => radarVertex(Math.max(0, Math.min(1, axis.score / Math.max(1, axis.max_score))), radarAngles[idx])),
);

const radarPolygonPoints = computed(() => radarDataVertices.value.map((point) => `${point.x},${point.y}`).join(" "));

const radarLabelPoints = computed(() =>
  radarAxes.value.map((axis, idx) => {
    const point = radarVertex(1.17, radarAngles[idx]);
    return { ...point, label: axis.label };
  }),
);

const dimensionCompareRows = computed(() =>
  radarAxes.value.map((axis) => {
    const maxScore = Math.max(1, Number(axis.max_score || 100));
    return {
      label: axis.label,
      candidate: Math.max(0, Math.min(100, (Number(axis.score || 0) / maxScore) * 100)),
      benchmark: 100,
      benchmarkScore: maxScore,
    };
  }),
);

const mergedReportBullets = computed(() => {
  const source = [
    ...resumePanel.value.strengths,
    ...interviewPanel.value.strengths,
    ...compositePanel.value.risk_tags.map((item) => `风险提示：${item}`),
  ].filter((item) => String(item || "").trim());
  return source.slice(0, 8);
});

function toStars(score: number): number {
  if (score >= 90) return 5;
  if (score >= 80) return 4;
  if (score >= 70) return 3;
  if (score >= 60) return 2;
  return 1;
}

function ringStyle(score: number): Record<string, string> {
  const pct = Math.max(0, Math.min(100, Number(score || 0)));
  return { background: `conic-gradient(#377dff ${pct}%, #dce9ff ${pct}% 100%)` };
}

function mapRawDimensions(dimensions: HiringDecisionAssessmentPanel["dimensions"]): DimensionRow[] {
  return dimensions.map((item) => ({
    key: dimensionKey(item.key, item.label),
    label: String(item.label || item.key || "--"),
    score: Number(item.score || 0),
    max_score: Number(item.max_score || 100),
  }));
}

function dimensionKey(key?: string | null, label?: string | null): string {
  const source = String(key || label || "").trim().toLowerCase();
  return source.replace(/[\s_-]+/g, " ").trim();
}

function recommendationLabel(value: string): string {
  const rec = String(value || "").toLowerCase();
  if (rec === "strong_recommend") return "优先推荐";
  if (rec === "recommend" || rec === "advance") return "推荐";
  if (rec === "reject") return "不推荐";
  return "待审批";
}

function recommendationResultLabel(value: string): string {
  const rec = String(value || "").toLowerCase();
  if (rec === "strong_recommend" || rec === "recommend" || rec === "advance") return "通过";
  if (rec === "reject") return "拒绝";
  return "待复核";
}

function stageText(stage: string): string {
  const val = String(stage || "").toLowerCase();
  if (val === "offer" || val === "offered" || val === "hired") return "已通过";
  if (val === "rejected") return "已拒绝";
  if (val === "interview") return "面试中";
  return "待审批";
}

function maskPhone(phone?: string | null): string {
  const text = String(phone || "").trim();
  if (!text) return "--";
  if (text.length < 7) return text;
  return `${text.slice(0, 3)}******${text.slice(-4)}`;
}

function formatDateTime(value?: string | null): string {
  if (!value) return "--";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
}

async function loadData() {
  if (!jobId.value || !candidateId.value) {
    loadError.value = "缺少 jobId 或 candidateId 参数。";
    return;
  }
  isLoading.value = true;
  loadError.value = "";
  try {
    detail.value = await fetchHiringDecisionDetail(jobId.value, candidateId.value);
  } catch (error) {
    console.error(error);
    detail.value = null;
    loadError.value = "加载录用决策详情失败，请稍后重试。";
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadData);
</script>

<style scoped>
.decision-detail-page { display: flex; flex-direction: column; gap: 14px; }
.decision-detail-toolbar { display: flex; justify-content: flex-end; gap: 10px; }
.ghost-btn,.primary-btn { height: 36px; border-radius: 10px; font-size: 14px; font-weight: 600; padding: 0 14px; display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
.ghost-btn { border: 1px solid #e4ebf5; background: #fff; color: #5f7089; }
.primary-btn { border: 0; background: #2f74ff; color: #fff; }
.state-panel { border: 1px solid #e8eef7; border-radius: 14px; background: #fff; min-height: 320px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: #7d8da3; }
.loader { width: 34px; height: 34px; border-radius: 999px; border: 3px solid #cfdcf6; border-top-color: #2f74ff; animation: spin 0.9s linear infinite; }

.summary-grid { display: grid; grid-template-columns: 280px 1fr; gap: 12px; }
.candidate-card,.overview-card,.card { border: 1px solid #e8eef7; border-radius: 14px; background: #fff; }
.candidate-card { padding: 16px; display: flex; align-items: flex-start; gap: 12px; margin-top: -44px; }
.avatar-wrap { width: 72px; height: 72px; border-radius: 999px; overflow: hidden; background: #eef3fa; color: #607189; font-size: 26px; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.avatar-wrap img { width: 100%; height: 100%; object-fit: cover; }
.avatar-wrap { flex-shrink: 0; }
.candidate-main { margin-top: 0; min-width: 0; }
.name-line { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.name-line h2 { margin: 0; font-size: 24px; line-height: 32px; color: #223145; }
.recommend-pill { padding: 4px 10px; border-radius: 999px; background: #eaf2ff; color: #3a7eff; font-size: 12px; font-weight: 700; }
.candidate-main .role { margin: 6px 0 4px; font-size: 19px; line-height: 26px; color: #1f2d3f; font-weight: 700; }
.candidate-main .meta { margin: 4px 0 0; font-size: 14px; color: #7e8ea5; }

.overview-card { padding: 16px 20px; }
.overview-card h3 { margin: 0; font-size: 18px; color: #33465d; }
.overview-metrics { margin-top: 14px; display: grid; grid-template-columns: 170px 170px 110px 1fr; align-items: center; gap: 14px; }
.metric-block p { margin: 0; font-size: 14px; color: #7a899e; }
.metric-block strong { display: block; margin-top: 4px; font-size: 30px; line-height: 34px; }
.metric-block strong.blue { color: #3378ff; }
.metric-block strong.green { color: #2cb371; }
.stars { margin-top: 2px; display: flex; gap: 1px; }
.stars .material-symbols-outlined { font-size: 13px; color: #d2ddef; font-variation-settings: "FILL" 1; }
.stars .material-symbols-outlined.active { color: #3b7fff; }
.stars.green .material-symbols-outlined.active { color: #2cb371; }
.ring,.compact-ring { width: 76px; height: 76px; border-radius: 999px; display: grid; place-items: center; position: relative; }
.ring::before,.compact-ring::before { content: ""; position: absolute; width: 62px; height: 62px; border-radius: 999px; background: #fff; }
.ring span,.compact-ring span { position: relative; font-size: 24px; line-height: 28px; color: #3378ff; font-weight: 700; }
.right-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; align-items: center; }
.metric-kv { min-width: 0; }
.right-metrics label { display: block; font-size: 13px; color: #7f8ea2; line-height: 18px; }
.right-metrics strong { display: block; margin-top: 6px; font-size: 16px; color: #3d4f66; line-height: 22px; white-space: nowrap; }
.right-metrics strong.green { color: #2cb371; }

.tabs-row { border-bottom: 1px solid #e7edf7; display: flex; gap: 30px; margin-top: 8px; }
.tab-btn { border: 0; background: transparent; color: #7b8aa1; font-size: 18px; line-height: 26px; font-weight: 400; padding: 0 0 10px; border-bottom: 3px solid transparent; cursor: pointer; }
.tab-btn.active { color: #2f74ff; border-bottom-color: #2f74ff; }

.content-grid { display: grid; grid-template-columns: 280px 1fr; gap: 12px; align-items: start; }
.main-content { min-width: 0; }
.detail-grid { display: grid; grid-template-columns: 1fr 300px; gap: 12px; align-items: start; }
.left-stack,.center-stack,.right-stack { display: flex; flex-direction: column; gap: 12px; }
.assessment-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.card { padding: 16px; }
.card h4 { margin: 0; font-size: 18px; line-height: 26px; color: #32455c; }
.left-stack .card h4 { font-size: 18px; line-height: 26px; }
.section-title-bold { font-weight: 700; }
.compact > .section-title-bold { text-align: right; }

.kv-list { margin-top: 10px; }
.kv-list p,.compact-kv p { margin: 0 0 9px; display: flex; justify-content: space-between; gap: 8px; }
.kv-list label,.compact-kv label { color: #7f8ea4; font-size: 14px; }
.kv-list span,.compact-kv span { color: #3c4f66; font-size: 16px; font-weight: 600; }
.status-green { color: #2cb371 !important; }

.timeline { margin-top: 12px; }
.timeline-item { display: grid; grid-template-columns: 16px 1fr auto; align-items: center; gap: 8px; margin-bottom: 14px; }
.dot { width: 10px; height: 10px; border-radius: 999px; background: #4d85ff; }
.timeline-main p { margin: 0; font-size: 16px; color: #364a61; font-weight: 600; }
.timeline-main span { font-size: 13px; color: #8594a8; }
.timeline-tag { font-size: 12px; color: #2cb371; background: #e7f8ef; padding: 2px 8px; border-radius: 999px; }

.panel-head { display: flex; justify-content: space-between; align-items: center; }
.panel-head strong { font-size: 22px; line-height: 28px; color: #3378ff; }
.panel-head strong.green { color: #2cb371; }
.panel-head + .bars { margin-top: 8px; }
.panel-desc { margin: 8px 0 12px; font-size: 14px; color: #7d8ca2; }
.bars { display: flex; flex-direction: column; gap: 9px; }
.bars.small { margin-top: 12px; }
.bar-line { display: grid; grid-template-columns: 110px 1fr 90px; align-items: center; gap: 8px; }
.assessment-row .bar-line { grid-template-columns: 132px minmax(110px, 188px) 72px; justify-content: space-between; column-gap: 14px; }
.bar-line label { font-size: 14px; color: #60738d; }
.assessment-row .bar-line label { display: block; white-space: nowrap; overflow: hidden; text-overflow: clip; }
.bar-line span { text-align: right; font-size: 13px; color: #6f8098; }
.compare-legend { margin-top: 10px; display: flex; align-items: center; gap: 18px; color: #8a99ae; font-size: 12px; }
.compare-legend span { display: inline-flex; align-items: center; gap: 6px; }
.compare-legend i { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
.compare-legend i.candidate { background: #3a7eff; }
.compare-legend i.benchmark { background: #d5deec; }
.compare-list { margin-top: 10px; display: flex; flex-direction: column; gap: 9px; }
.compare-row { display: grid; grid-template-columns: 96px minmax(120px, 1fr) 32px; align-items: center; column-gap: 10px; }
.compare-row label { font-size: 13px; color: #6f8098; white-space: nowrap; }
.compare-line { position: relative; height: 2px; background: #dce5f3; border-radius: 999px; }
.compare-line .candidate-line { position: absolute; inset: 0 auto 0 0; height: 100%; border-radius: 999px; background: #3a7eff; }
.compare-line .benchmark-mark { position: absolute; top: -4px; width: 1px; height: 10px; background: #c7d2e6; transform: translateX(-0.5px); }
.compare-row span { color: #8a99ae; font-size: 12px; text-align: right; }
.bar-track { height: 4px; border-radius: 999px; background: #e2ebf9; overflow: hidden; position: relative; }
.bar-track.dual { height: 6px; }
.bar-fill { height: 100%; }
.bar-fill.blue { background: #3a7eff; }
.bar-fill.green { background: #2cb371; }
.bar-fill.overlay { position: absolute; inset: 0 auto 0 0; opacity: .55; }
.panel-conclusion { margin-top: 12px; background: #f7fbff; border-radius: 10px; padding: 10px; }
.panel-conclusion h5 { margin: 0; font-size: 14px; color: #4e83f8; }
.panel-conclusion p { margin: 6px 0 0; font-size: 14px; line-height: 22px; color: #5f728c; }
.panel-conclusion.green-bg h5 { color: #2cb371; }
.bottom-dual { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

.radar-wrap { margin-top: 8px; display: flex; flex-direction: column; align-items: center; gap: 8px; }
.radar-svg { width: 100%; max-width: 260px; height: 220px; overflow: visible; }
.radar-ring { fill: none; stroke: #dfe7f5; stroke-width: 1; }
.radar-axis { stroke: #e8edf8; stroke-width: 1; }
.radar-data-fill { fill: rgba(58, 126, 255, 0.2); }
.radar-data-line { fill: none; stroke: #3a7eff; stroke-width: 2; }
.radar-data-dot { fill: #3a7eff; }
.radar-label { fill: #8a99ae; font-size: 12px; text-anchor: middle; dominant-baseline: middle; }
.radar-legend { display: flex; gap: 18px; font-size: 12px; color: #7e8ea4; align-items: center; }
.radar-legend span { display: inline-flex; gap: 6px; align-items: center; }
.legend-dot,.legend-box { width: 10px; height: 10px; display: inline-block; }
.legend-dot { border-radius: 999px; background: #3a7eff; }
.legend-box { border-radius: 2px; background: #dfe7f5; }

.compact { text-align: center; }
.compact-ring { margin: 14px auto 12px; }
.remark { margin: 8px 0 0; font-size: 13px; line-height: 20px; color: #7c8ca2; text-align: left; }
.review-item { margin-top: 10px; border-top: 1px solid #eef3fa; padding-top: 10px; }
.review-title { margin: 0; color: #33465e; font-weight: 700; display: flex; justify-content: space-between; }
.review-title span { color: #7f8fa4; font-size: 12px; font-weight: 500; }
.review-comment { margin: 4px 0 0; color: #546981; font-size: 13px; line-height: 20px; }
.review-time { margin: 4px 0 0; color: #8ca0b5; font-size: 12px; }

.record-card { min-height: 240px; }
.empty-tip { margin-top: 16px; color: #8796ab; }
.qa-item { margin-top: 12px; padding: 12px; border-radius: 10px; border: 1px solid #e8eef7; background: #fbfdff; }
.qa-item .question { margin: 0 0 8px; color: #32475f; font-size: 15px; font-weight: 600; }
.qa-item .answer { margin: 0; color: #5f728a; line-height: 22px; }
.qa-time { margin-top: 6px; font-size: 12px; color: #8ba0b4; }
.report-text { margin-top: 12px; color: #61748c; line-height: 24px; }
.report-list { margin: 10px 0 0; padding-left: 18px; color: #51647d; line-height: 22px; }
.log-item { margin-top: 10px; padding: 10px; border: 1px solid #e8eef7; border-radius: 10px; background: #fbfdff; }
.log-item p { margin: 0; color: #32475f; font-size: 14px; font-weight: 600; }
.log-item span { display: block; margin-top: 4px; color: #8090a6; font-size: 12px; }
.log-item em { display: block; margin-top: 4px; color: #7e8ea4; font-style: normal; font-size: 12px; }

@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 1600px) {
  .summary-grid,.content-grid,.detail-grid { grid-template-columns: 1fr; }
  .candidate-card { margin-top: 0; }
  .overview-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .assessment-row { grid-template-columns: 1fr; }
  .bottom-dual { grid-template-columns: 1fr; }
  .name-line h2 { font-size: 24px; }
  .candidate-main .role { font-size: 20px; }
}
</style>
