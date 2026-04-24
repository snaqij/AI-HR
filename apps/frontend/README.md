# AI-HR Frontend (Vue 3)

会议式面试间 Web UI（候选人端），采用 Vue 3 + Vite + TypeScript。

## 目录

- `src/App.vue`: 会议式面试间页面
- `src/styles.css`: 页面样式（会议风格）

## 本地运行

```bash
cd frontend
npm install
npm run dev
```

默认地址：`http://localhost:5173`

## 接口对接

- 默认后端地址读取 `VITE_API_BASE_URL`（见 `.env.example`）
- 页面支持两种进入方式：
  0. 无参数直接打开：自动创建演示岗位/候选人并启动会话（便于本地联调）
  1. 传 `session_id`：`/?session_id=<id>`
  2. 传 `candidate_id + job_id`：页面自动创建并启动会话  
     `/?candidate_id=<candidateId>&job_id=<jobId>`

## 已接后端能力

- 会话信息：`POST /ai/interviews/sessions`、`POST /ai/interviews/sessions/{id}/start`、`GET /ai/interviews/sessions/{id}/report`
- 问题加载：`POST /ai/interviews/sessions/{id}/question-set/generate`
- 字幕流：轮询 `GET /ai/interviews/sessions/{id}/replay`
- 退出面试：`POST /ai/interviews/sessions/{id}/finish`
- 语音上行：浏览器麦克风采集 PCM/WAV 分片，调用 `POST /ai/interviews/sessions/{id}/rtc/asr/stream`
- 追问回写：调用 `POST /ai/interviews/sessions/{id}/events` 触发追问
- 语音下行：调用 `POST /ai/interviews/sessions/{id}/rtc/tts/stream` 并自动播放 `audio_uris`

## 语音说明

- 首次进入页面会请求麦克风权限。
- 浏览器可能阻止自动播放音频；若听不到播报，请先与页面发生一次交互（点击页面任意位置）后重试。

## 页面说明

- 顶部：会议状态栏（品牌、时长、网络、布局、设置、退出）
- 中央：视频舞台区（候选人主画面 + 面试官小卡片）
- 右侧：当前问题、补充提问、实时字幕
- 底部：会议工具条（成员、聊天、面试纪要、应用）

说明：候选人端遵循“去 AI 暴露”策略，不展示模型或技术链路字段。
