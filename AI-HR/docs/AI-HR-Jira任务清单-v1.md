# AI-HR Jira ä»»åŠ¡æ¸…å•ï¼ˆBOSS ä¼˜å…ˆï¼‰

## 1. æ–‡æ¡£è¯´æ˜
- ç›®æ ‡ï¼šå°† `docs/AI-HR-å¼€å‘è®¡åˆ’-BOSSä¼˜å…ˆ-v1.md` æ‹†è§£ä¸ºå¯æ‰§è¡Œ Jira ä»»åŠ¡ã€‚
- å½“å‰æŠ€æœ¯æ ˆï¼š
- åç«¯ï¼š`FastAPI + Python`
- å‰ç«¯ï¼š`Vue 3`
- æ•°æ®åº“ï¼š`MySQL`
- èŒƒå›´ï¼šä»…è¦†ç›–æ‹›è˜ç«¯ MVPï¼Œä¸å«è°ˆè–ªã€è§†é¢‘é¢è¯•ã€AI é¢è¯•å®˜ã€‚

## 2. Epic åˆ’åˆ†

| Epic ID | Epic åç§° | è¯´æ˜ |
|---|---|---|
| AHR-BE-EPIC-01 | åç«¯åŸºç¡€è®¾æ–½ä¸è¿æ¥å™¨æ¡†æ¶ | FastAPIã€MySQLã€ä»»åŠ¡é˜Ÿåˆ—ã€è¿æ¥å™¨æŠ½è±¡ |
| AHR-BE-EPIC-02 | æ‹›è˜æ ¸å¿ƒæµç¨‹ | å²—ä½ã€å€™é€‰äººã€ä¼šè¯ã€é¢è¯•ã€å®¡æ‰¹ã€å®¡è®¡ |
| AHR-AI-EPIC-01 | AI è§£æä¸è‡ªåŠ¨åŒ–æœåŠ¡ | ç®€å†è§£æã€è¯„åˆ†ã€å›å¤ã€çº¦é¢å»ºè®® |
| AHR-FE-EPIC-01 | æ‹›è˜è¿è¥å° | å²—ä½ç®¡ç†ã€å€™é€‰äººçœ‹æ¿ã€ä¼šè¯å°ã€çº¦é¢å° |
| AHR-QA-EPIC-01 | è´¨é‡ä¿éšœä¸ä¸Šçº¿éªŒè¯ | æµ‹è¯•ã€å›å½’ã€ç°åº¦ã€éªŒæ”¶ |

## 3. åç«¯ä»»åŠ¡æ¸…å•ï¼ˆFastAPI + Python + MySQLï¼‰

| Task ID | ä»»åŠ¡æ ‡é¢˜ | ç±»å‹ | ä¼˜å…ˆçº§ | ä¾èµ– | éªŒæ”¶æ ‡å‡† |
|---|---|---|---|---|---|
| AHR-BE-001 | åˆå§‹åŒ– FastAPI é¡¹ç›®éª¨æ¶ä¸ç¯å¢ƒé…ç½® | Task | P0 | æ—  | é¡¹ç›®å¯å¯åŠ¨ï¼ŒåŒ…å« dev/test/prod é…ç½® |
| AHR-BE-002 | å»ºç«‹ MySQL æ•°æ®åº“è¿æ¥ã€ä¼šè¯ç®¡ç†ä¸è¿ç§»æ¡†æ¶ | Task | P0 | AHR-BE-001 | æ”¯æŒæœ¬åœ°è¿æ¥ã€è¿ç§»æ‰§è¡ŒæˆåŠŸ |
| AHR-BE-003 | è®¾è®¡æ ¸å¿ƒè¡¨ç»“æ„ï¼šjobs/candidates/conversations/interviews/events | Story | P0 | AHR-BE-002 | è¡¨ç»“æ„å¯è¿ç§»ï¼Œå­—æ®µæ»¡è¶³ PRD |
| AHR-BE-004 | å»ºç«‹ç»Ÿä¸€å“åº”æ¨¡å‹ã€é”™è¯¯ç ä¸å¹‚ç­‰ä¸­é—´ä»¶ | Task | P0 | AHR-BE-001 | API è¿”å›ç»“æ„ç»Ÿä¸€ï¼Œæ”¯æŒå¹‚ç­‰é”® |
| AHR-BE-005 | å®ç° Connector æŠ½è±¡æ¥å£ä¸æ³¨å†Œæœºåˆ¶ | Story | P0 | AHR-BE-001 | æ”¯æŒæŒ‰ channel åŠ¨æ€åŠ è½½è¿æ¥å™¨ |
| AHR-BE-006 | å®ç° BOSSConnector éª¨æ¶ä¸è®¤è¯ç®¡ç† | Story | P0 | AHR-BE-005 | å¯å®Œæˆè®¤è¯åˆå§‹åŒ–ä¸åŸºç¡€è¿é€šæ€§æ ¡éªŒ |
| AHR-BE-007 | å¼€å‘å²—ä½åˆ›å»º API `POST /api/v1/jobs` | Story | P0 | AHR-BE-003, AHR-BE-004 | å¯åˆ›å»ºå²—ä½å¹¶æŒä¹…åŒ– |
| AHR-BE-008 | å¼€å‘å²—ä½å‘å¸ƒ API `POST /api/v1/jobs/{job_id}/publish` | Story | P0 | AHR-BE-006, AHR-BE-007 | å¯è°ƒç”¨ BOSSConnector å‘å¸ƒå²—ä½ |
| AHR-BE-009 | å¼€å‘å‘å¸ƒçŠ¶æ€æŸ¥è¯¢ API `GET /api/v1/jobs/{job_id}/publish-status` | Story | P0 | AHR-BE-008 | å¯å›æ”¶å¹¶å±•ç¤ºå‘å¸ƒçŠ¶æ€ |
| AHR-BE-010 | å¼€å‘å€™é€‰äººåŒæ­¥æ¥å£ä¸å¢é‡æ‹‰å–ä»»åŠ¡ | Story | P0 | AHR-BE-006, AHR-BE-003 | å¯æŒ‰å²—ä½åŒæ­¥å€™é€‰äººå…¥åº“ |
| AHR-BE-011 | å®ç°å€™é€‰äººå»é‡ä¸åˆå¹¶é€»è¾‘ | Story | P0 | AHR-BE-010 | é‡å¤å€™é€‰äººå¯è¯†åˆ«å¹¶ä¿ç•™ä¸»æ¡£æ¡ˆ |
| AHR-BE-012 | å¼€å‘å€™é€‰äººè¯„åˆ†è§¦å‘ API `POST /api/v1/candidates/{id}/score` | Story | P0 | AHR-BE-010 | å¯è§¦å‘ AI è¯„åˆ†å¹¶å†™å›ç»“æœ |
| AHR-BE-013 | å¼€å‘è‡ªåŠ¨æ‰“æ‹›å‘¼ API `POST /api/v1/conversations/greet` | Story | P0 | AHR-BE-006, AHR-BE-010 | å¯è§¦è¾¾å€™é€‰äººå¹¶è®°å½•å‘é€ç»“æœ |
| AHR-BE-014 | å¼€å‘ä¼šè¯åŒæ­¥ä»»åŠ¡ä¸æ¶ˆæ¯å…¥åº“é€»è¾‘ | Story | P0 | AHR-BE-006, AHR-BE-003 | å¯æ‹‰å–æ¶ˆæ¯å¹¶ç»´æŠ¤ä¼šè¯çŠ¶æ€ |
| AHR-BE-015 | å¼€å‘è‡ªåŠ¨å›å¤ API `POST /api/v1/conversations/reply` | Story | P0 | AHR-BE-014 | å¯è°ƒç”¨ AI æœåŠ¡ç”Ÿæˆå¹¶å‘é€å›å¤ |
| AHR-BE-016 | å¼€å‘é¢è¯•æ’æœŸ API `POST /api/v1/interviews/schedule` | Story | P0 | AHR-BE-003 | å¯åˆ›å»ºé¢è¯•è®°å½•å¹¶å†™å…¥çŠ¶æ€ |
| AHR-BE-017 | å¼€å‘ BOSS çº¦é¢æ‰§è¡Œèƒ½åŠ›ä¸çŠ¶æ€å›å†™ | Story | P0 | AHR-BE-016, AHR-BE-006 | å¯å°†é¢è¯•å®‰æ’åŒæ­¥åˆ°æ¸ é“æˆ–æ‰§è¡Œå…œåº•æµç¨‹ |
| AHR-BE-018 | å®ç°å®¡æ‰¹æµ API `POST /api/v1/approvals` | Story | P0 | AHR-BE-003 | é«˜é£é™©åŠ¨ä½œå¯è¿›å…¥å®¡æ‰¹æµ |
| AHR-BE-019 | å®ç°å®¡è®¡æ—¥å¿—è®°å½•ä¸æŸ¥è¯¢æ¥å£ | Story | P0 | AHR-BE-003 | æ‰€æœ‰å…³é”®åŠ¨ä½œå†™å…¥å®¡è®¡æ—¥å¿— |
| AHR-BE-020 | å®ç°æ¼æ–—æŠ¥è¡¨ API `GET /api/v1/metrics/funnel` | Story | P1 | AHR-BE-003 | å¯è¾“å‡ºé˜¶æ®µè½¬åŒ–ç‡ä¸æ—¶é•¿ |
| AHR-BE-021 | æ¥å…¥å¼‚æ­¥ä»»åŠ¡é˜Ÿåˆ—ä¸å¤±è´¥é‡è¯•æœºåˆ¶ | Story | P0 | AHR-BE-010, AHR-BE-014 | å‘å¸ƒ/åŒæ­¥/å›å¤ä»»åŠ¡æ”¯æŒé‡è¯•ä¸è¡¥å¿ |
| AHR-BE-022 | å»ºç«‹é¢‘æ§ã€é™æµã€å‘Šè­¦è§„åˆ™ | Task | P0 | AHR-BE-021 | æ¸ é“è°ƒç”¨å…·å¤‡é¢‘ç‡é™åˆ¶ä¸å¼‚å¸¸å‘Šè­¦ |
| AHR-BE-023 | å®ç°æƒé™æ¨¡å‹ä¸è§’è‰²æ ¡éªŒ | Story | P1 | AHR-BE-001 | HR/é¢è¯•å®˜/ç®¡ç†å‘˜æƒé™éš”ç¦» |
| AHR-BE-024 | ç¼–å†™ OpenAPI æ–‡æ¡£ä¸æ¥å£ç¤ºä¾‹ | Task | P1 | AHR-BE-007 è‡³ AHR-BE-020 | Swagger æ–‡æ¡£å¯ç›´æ¥è°ƒè¯• |

## 4. AI ä»»åŠ¡æ¸…å•

| Task ID | ä»»åŠ¡æ ‡é¢˜ | ç±»å‹ | ä¼˜å…ˆçº§ | ä¾èµ– | éªŒæ”¶æ ‡å‡† |
|---|---|---|---|---|---|
| AHR-AI-001 | å®šä¹‰ç®€å†ç»“æ„åŒ–è¾“å‡º Schema | Task | P0 | æ—  | è¾“å‡ºå­—æ®µè¦†ç›–æ•™è‚²ã€ç»å†ã€æŠ€èƒ½ã€é¡¹ç›® |
| AHR-AI-002 | å®ç°ç®€å†è§£ææœåŠ¡æ¥å£ | Story | P0 | AHR-AI-001 | æ”¯æŒ PDF/Word ç®€å†è§£æ |
| AHR-AI-003 | å®ç°ç®€å†æ¸…æ´—ä¸å­—æ®µæ ‡å‡†åŒ– | Story | P0 | AHR-AI-002 | å­¦å†ã€å¹´é™ã€æŠ€èƒ½åç§°å¯æ ‡å‡†åŒ– |
| AHR-AI-004 | å®ç°å²—ä½åŒ¹é…è¯„åˆ†è§„åˆ™å¼•æ“ | Story | P0 | AHR-AI-003 | å¯è¾“å‡ºæ€»åˆ†ã€ç»´åº¦åˆ†ã€è§£é‡Š |
| AHR-AI-005 | å®ç°é£é™©æ ‡ç­¾è¯†åˆ« | Story | P1 | AHR-AI-003 | å¯è¯†åˆ«è·³æ§½é¢‘ç‡ã€ä¿¡æ¯ç¼ºå¤±ç­‰æ ‡ç­¾ |
| AHR-AI-006 | å®šä¹‰è‡ªåŠ¨æ‰“æ‹›å‘¼æ¨¡æ¿å˜é‡ä¸ç”Ÿæˆç­–ç•¥ | Task | P0 | æ—  | æ”¯æŒæŒ‰å²—ä½/å€™é€‰äººå˜é‡æ¸²æŸ“ |
| AHR-AI-007 | å®ç°è‡ªåŠ¨å›å¤æ„å›¾åˆ†ç±»å™¨ | Story | P0 | æ—  | è‡³å°‘æ”¯æŒ FAQã€æ„å‘ç¡®è®¤ã€è–ªèµ„æ•æ„Ÿã€äººå·¥è½¬æ¥ |
| AHR-AI-008 | å®ç°è‡ªåŠ¨å›å¤ç”ŸæˆæœåŠ¡ | Story | P0 | AHR-AI-007 | å¯è¾“å‡ºå›å¤æ–‡æœ¬ä¸ç½®ä¿¡åº¦ |
| AHR-AI-009 | å®ç°ä½ç½®ä¿¡åº¦è½¬äººå·¥ç­–ç•¥ | Story | P0 | AHR-AI-008 | ä½äºé˜ˆå€¼æ—¶ä¸è‡ªåŠ¨å‘é€ |
| AHR-AI-010 | å®ç°çº¦é¢æ—¶é—´æ¨èæœåŠ¡ | Story | P0 | æ—  | è¾“å…¥å€™é€‰äººåå¥½å’Œé¢è¯•å®˜æ—¶é—´åå¯è¾“å‡ºå€™é€‰æ—¶æ®µ |
| AHR-AI-011 | å®ç°æ•æ„Ÿå†…å®¹ä¸åˆè§„å®¡æŸ¥ç­–ç•¥ | Story | P0 | AHR-AI-008 | æ•æ„Ÿæ„å›¾è‡ªåŠ¨æ‹¦æˆª |
| AHR-AI-012 | å»ºç«‹ AI æœåŠ¡è¯„ä¼°é›†ä¸ç¦»çº¿è¯„ä¼°è„šæœ¬ | Task | P1 | AHR-AI-002, AHR-AI-008 | å¯è¯„ä¼°è§£ææˆåŠŸç‡ä¸å›å¤å‡†ç¡®ç‡ |

### 4.1 AI æ¨¡å—å¯æ‰§è¡Œæ‹†è§£ï¼ˆæ¥å£ + æ•°æ®è¡¨ + éªŒæ”¶æŒ‡æ ‡ï¼‰

#### 4.1.1 ç®€å†è§£æä¸æ ‡å‡†åŒ–ï¼ˆå¯¹åº” AHR-AI-001 ~ AHR-AI-003ï¼‰

| ç»´åº¦ | æ¸…å• |
|---|---|
| æ¥å£ | `POST /api/v1/ai/resume/parse`ï¼ˆç®€å†è§£æï¼‰ |
| æ¥å£ | `POST /api/v1/ai/resume/normalize`ï¼ˆå­—æ®µæ ‡å‡†åŒ–ï¼‰ |
| æ¥å£ | `GET /api/v1/candidates/{id}/resume-profile`ï¼ˆç»“æ„åŒ–ç”»åƒæŸ¥è¯¢ï¼‰ |
| æ•°æ®è¡¨ | `candidate_resume_profiles`ï¼š`id,candidate_id,raw_text,parsed_json,normalized_json,parse_status,parser_version,confidence,created_at,updated_at` |
| æ•°æ®è¡¨ | `candidate_resume_risks`ï¼š`id,candidate_id,risk_code,risk_level,detail,created_at` |
| éªŒæ”¶æŒ‡æ ‡ | è§£ææˆåŠŸç‡ `>= 92%` |
| éªŒæ”¶æŒ‡æ ‡ | å…³é”®å­—æ®µå®Œæ•´ç‡ï¼ˆæ•™è‚²/ç»å†/æŠ€èƒ½/å¹´é™ï¼‰`>= 90%` |
| éªŒæ”¶æŒ‡æ ‡ | æ ‡å‡†åŒ–å‡†ç¡®ç‡ï¼ˆæŠ½æ£€ï¼‰`>= 85%` |

#### 4.1.2 åŒ¹é…æ‰“åˆ†ä¸ç­›é€‰æ’åºï¼ˆå¯¹åº” AHR-AI-004 ~ AHR-AI-005ï¼‰

| ç»´åº¦ | æ¸…å• |
|---|---|
| æ¥å£ | `POST /api/v1/ai/candidates/score`ï¼ˆæŒ‰ `job_id` æ‰¹é‡æ‰“åˆ†ï¼‰ |
| æ¥å£ | `POST /api/v1/ai/candidates/rank`ï¼ˆç­›é€‰å¹¶æ’åºï¼‰ |
| æ¥å£ | `GET /api/v1/jobs/{job_id}/shortlist`ï¼ˆå…¥å›´åå•ï¼‰ |
| æ•°æ®è¡¨ | `candidate_job_scores`ï¼š`id,candidate_id,job_id,total_score,dimension_scores,explanation,risk_tags,score_version,scored_at` |
| æ•°æ®è¡¨ | `job_shortlists`ï¼š`id,job_id,candidate_id,rank,status,created_at` |
| éªŒæ”¶æŒ‡æ ‡ | æ‰“åˆ†æ¥å£ P95 å“åº”æ—¶é—´ `< 1.5s`ï¼ˆå•å€™é€‰äººï¼‰ |
| éªŒæ”¶æŒ‡æ ‡ | æ’åºç¨³å®šæ€§ï¼ˆåŒè¾“å…¥åŒç‰ˆæœ¬ï¼‰`100%` |
| éªŒæ”¶æŒ‡æ ‡ | Top-N å‘½ä¸­ç‡ï¼ˆäººå·¥è¯„å®¡å¯¹é½ï¼‰`>= 80%` |

#### 4.1.3 è‡ªåŠ¨å›å¤ï¼ˆå¯¹åº” AHR-AI-007 ~ AHR-AI-009, AHR-AI-011ï¼‰

| ç»´åº¦ | æ¸…å• |
|---|---|
| æ¥å£ | `POST /api/v1/ai/reply/classify-intent`ï¼ˆæ„å›¾åˆ†ç±»ï¼‰ |
| æ¥å£ | `POST /api/v1/ai/reply/generate`ï¼ˆå›å¤ç”Ÿæˆ + ç½®ä¿¡åº¦ï¼‰ |
| æ¥å£ | `POST /api/v1/conversations/reply/auto`ï¼ˆè‡ªåŠ¨å›å¤æ‰§è¡Œ + è½¬äººå·¥ï¼‰ |
| æ•°æ®è¡¨ | `conversation_ai_replies`ï¼š`id,conversation_id,message_id,intent,reply_text,confidence,action,policy_flags,model_version,created_at` |
| æ•°æ®è¡¨ | `conversation_handoffs`ï¼š`id,conversation_id,reason,confidence,status,created_at` |
| éªŒæ”¶æŒ‡æ ‡ | æ„å›¾åˆ†ç±»å‡†ç¡®ç‡ `>= 85%` |
| éªŒæ”¶æŒ‡æ ‡ | è‡ªåŠ¨å›å¤å¯ç›´æ¥å‘é€æ¯”ä¾‹ `>= 70%` |
| éªŒæ”¶æŒ‡æ ‡ | ä½ç½®ä¿¡åº¦è½¬äººå·¥å¬å›ç‡ `>= 95%` |
| éªŒæ”¶æŒ‡æ ‡ | æ•æ„Ÿå†…å®¹æ¼å‘ç‡ `<= 1%` |

#### 4.1.4 æŒ‰å²—ä½äººæ•°è‡ªåŠ¨å‘é¢è¯•ï¼ˆå¯¹åº” AHR-AI-010 + æ‹›è˜æµç¨‹è”åŠ¨ï¼‰

| ç»´åº¦ | æ¸…å• |
|---|---|
| æ¥å£ | `POST /api/v1/jobs/{job_id}/interview/plan`ï¼ˆæŒ‰ `headcount` ç”Ÿæˆé‚€çº¦è®¡åˆ’ï¼‰ |
| æ¥å£ | `POST /api/v1/jobs/{job_id}/interview/send`ï¼ˆæ‰¹é‡å‘é€é¢è¯•é‚€çº¦ï¼‰ |
| æ¥å£ | `GET /api/v1/jobs/{job_id}/interview/progress`ï¼ˆå‘é€ä¸ç¡®è®¤è¿›åº¦ï¼‰ |
| æ•°æ®è¡¨ | `job_hiring_plans`ï¼š`id,job_id,target_headcount,shortlist_size,strategy,created_at` |
| æ•°æ®è¡¨ | `interview_campaigns`ï¼š`id,job_id,batch_no,total_targets,sent_count,failed_count,status,created_at` |
| æ•°æ®è¡¨ | `interview_invitations`ï¼š`id,campaign_id,candidate_id,channel,send_status,confirm_status,sent_at,confirmed_at,fail_reason` |
| éªŒæ”¶æŒ‡æ ‡ | è®¡åˆ’ä¸è¶…è¿‡å²—ä½äººæ•°ç­–ç•¥è¾¹ç•Œ `100%` |
| éªŒæ”¶æŒ‡æ ‡ | é‚€çº¦å‘é€æˆåŠŸç‡ `>= 95%` |
| éªŒæ”¶æŒ‡æ ‡ | å‘é€åˆ°ç¡®è®¤è½¬åŒ–ç‡ï¼ˆç›®æ ‡äººç¾¤ï¼‰`>= 70%` |
| éªŒæ”¶æŒ‡æ ‡ | å¤±è´¥é‡è¯•åæ¢å¤ç‡ `>= 90%` |

#### 4.1.5 è¯„ä¼°ä¸æ²»ç†ï¼ˆå¯¹åº” AHR-AI-012ï¼‰

| ç»´åº¦ | æ¸…å• |
|---|---|
| æ¥å£ | `POST /api/v1/ai/eval/run`ï¼ˆè§¦å‘è¯„ä¼°ä»»åŠ¡ï¼‰ |
| æ¥å£ | `GET /api/v1/ai/eval/report`ï¼ˆè¯„ä¼°æŠ¥å‘ŠæŸ¥è¯¢ï¼‰ |
| æ•°æ®è¡¨ | `ai_eval_runs`ï¼š`id,eval_type,dataset_version,model_version,metrics,status,created_at,finished_at` |
| æ•°æ®è¡¨ | `ai_decision_logs`ï¼š`id,module,input_hash,output_summary,confidence,policy_result,created_at` |
| éªŒæ”¶æŒ‡æ ‡ | æ¯å‘¨è‡³å°‘ 1 æ¬¡ç¦»çº¿è¯„ä¼° |
| éªŒæ”¶æŒ‡æ ‡ | AI å†³ç­–å¯è¿½æº¯ç‡ `100%` |
| éªŒæ”¶æŒ‡æ ‡ | æ¨¡å‹/è§„åˆ™ç‰ˆæœ¬å¯å›æ»šèƒ½åŠ› `100%` |

### 4.2 AI å¼€å‘é¡ºåºï¼ˆæ‰§è¡Œå»ºè®®ï¼‰

1. é˜¶æ®µä¸€ï¼ˆå…ˆå½¢æˆå¯ç”¨ AI èƒ½åŠ›ï¼‰
- ç®€å†è§£æä¸æ ‡å‡†åŒ–ï¼ˆ4.1.1ï¼‰
- åŒ¹é…æ‰“åˆ†ä¸ç­›é€‰æ’åºï¼ˆ4.1.2ï¼‰
- è‡ªåŠ¨å›å¤ï¼ˆ4.1.3ï¼‰

2. é˜¶æ®µäºŒï¼ˆå½¢æˆç«¯åˆ°ç«¯é—­ç¯ï¼‰
- æŒ‰å²—ä½äººæ•°è‡ªåŠ¨å‘é¢è¯•ï¼ˆ4.1.4ï¼‰
- è¯„ä¼°ä¸æ²»ç†èƒ½åŠ›ï¼ˆ4.1.5ï¼‰

## 5. å‰ç«¯ä»»åŠ¡æ¸…å•ï¼ˆVue 3ï¼‰

| Task ID | ä»»åŠ¡æ ‡é¢˜ | ç±»å‹ | ä¼˜å…ˆçº§ | ä¾èµ– | éªŒæ”¶æ ‡å‡† |
|---|---|---|---|---|---|
| AHR-FE-001 | åˆå§‹åŒ– Vue 3 é¡¹ç›®éª¨æ¶ä¸è·¯ç”±çŠ¶æ€ç®¡ç† | Task | P0 | æ—  | é¡¹ç›®å¯å¯åŠ¨ï¼Œå…·å¤‡åŸºç¡€å¸ƒå±€ |
| AHR-FE-002 | å»ºç«‹é€šç”¨è¯·æ±‚å±‚ã€é‰´æƒä¸é”™è¯¯æç¤ºæœºåˆ¶ | Task | P0 | AHR-FE-001 | å¯ç»Ÿä¸€å¤„ç† API è°ƒç”¨å’Œå¼‚å¸¸ |
| AHR-FE-003 | å¼€å‘å²—ä½åˆ—è¡¨é¡µä¸å²—ä½åˆ›å»ºé¡µ | Story | P0 | AHR-BE-007 | å¯åˆ›å»ºå¹¶æŸ¥çœ‹å²—ä½ |
| AHR-FE-004 | å¼€å‘å²—ä½å‘å¸ƒçŠ¶æ€é¡µ | Story | P0 | AHR-BE-008, AHR-BE-009 | å¯æŸ¥çœ‹å„æ¸ é“å‘å¸ƒçŠ¶æ€ |
| AHR-FE-005 | å¼€å‘å€™é€‰äººåˆ—è¡¨é¡µä¸è¯¦æƒ…é¡µ | Story | P0 | AHR-BE-010, AHR-BE-012 | å¯æŸ¥çœ‹å€™é€‰äººä¿¡æ¯å’Œè¯„åˆ†ç»“æœ |
| AHR-FE-006 | å¼€å‘ä¼šè¯å·¥ä½œå° | Story | P0 | AHR-BE-014, AHR-BE-015 | å¯æŸ¥çœ‹ä¼šè¯ã€æ‰‹åŠ¨å›å¤ã€çŠ¶æ€åˆ‡æ¢ |
| AHR-FE-007 | å¼€å‘äººå·¥æ¥ç®¡ä¸å®¡æ‰¹å° | Story | P0 | AHR-BE-018 | å¯å®¡æ‰¹é«˜é£é™©åŠ¨ä½œå’Œæ¥ç®¡ä½ç½®ä¿¡åº¦ä¼šè¯ |
| AHR-FE-008 | å¼€å‘é¢è¯•æ’æœŸå° | Story | P0 | AHR-BE-016, AHR-BE-017 | å¯æŸ¥çœ‹å€™é€‰æ—¶é—´ã€å‘èµ·çº¦é¢ã€ç¡®è®¤çŠ¶æ€ |
| AHR-FE-009 | å¼€å‘æ¼æ–—æŠ¥è¡¨é¡µ | Story | P1 | AHR-BE-020 | å¯å±•ç¤ºé˜¶æ®µè½¬åŒ–ç‡ä¸æ—¶é•¿ |
| AHR-FE-010 | å¼€å‘å®¡è®¡æ—¥å¿—æŸ¥è¯¢é¡µ | Story | P1 | AHR-BE-019 | å¯æŒ‰åŠ¨ä½œã€äººã€æ—¶é—´ç­›é€‰æ—¥å¿— |
| AHR-FE-011 | å»ºç«‹ç»„ä»¶åº“è§„èŒƒä¸é¡µé¢æƒé™æ§åˆ¶ | Task | P1 | AHR-FE-001, AHR-BE-023 | é¡µé¢æŒ‰è§’è‰²å±•ç¤ºä¸åŒæ“ä½œ |

## 6. QA ä»»åŠ¡æ¸…å•

| Task ID | ä»»åŠ¡æ ‡é¢˜ | ç±»å‹ | ä¼˜å…ˆçº§ | ä¾èµ– | éªŒæ”¶æ ‡å‡† |
|---|---|---|---|---|---|
| AHR-QA-001 | ç¼–å†™æµ‹è¯•è®¡åˆ’ä¸æµ‹è¯•èŒƒå›´è¯´æ˜ | Task | P0 | æ—  | è¦†ç›–åç«¯ã€AIã€å‰ç«¯ã€é›†æˆæµ‹è¯• |
| AHR-QA-002 | å»ºç«‹ FastAPI æ¥å£è‡ªåŠ¨åŒ–æµ‹è¯• | Story | P0 | AHR-BE-007 è‡³ AHR-BE-020 | æ ¸å¿ƒæ¥å£å…·å¤‡è‡ªåŠ¨åŒ–å›å½’ |
| AHR-QA-003 | ç¼–å†™ BOSSConnector å¥‘çº¦æµ‹è¯• | Story | P0 | AHR-BE-006 | å…³é”®è¿æ¥å™¨æ¥å£æœ‰ç¨³å®šå¥‘çº¦æµ‹è¯• |
| AHR-QA-004 | å»ºç«‹ç®€å†è§£æä¸å›å¤æ•ˆæœè¯„æµ‹æµç¨‹ | Story | P0 | AHR-AI-002, AHR-AI-008 | å¯è¾“å‡ºå‡†ç¡®ç‡/å¬å›ç‡/äººå·¥æŠ½æ£€ç»“æœ |
| AHR-QA-005 | å»ºç«‹å‰ç«¯å…³é”®é¡µé¢ E2E æµ‹è¯• | Story | P1 | AHR-FE-003 è‡³ AHR-FE-008 | å²—ä½/å€™é€‰äºº/ä¼šè¯/çº¦é¢æ ¸å¿ƒæµç¨‹å¯å›å½’ |
| AHR-QA-006 | æ‰§è¡Œé™æµã€å¤±è´¥é‡è¯•ã€è¡¥å¿åœºæ™¯æµ‹è¯• | Story | P0 | AHR-BE-021, AHR-BE-022 | å¤±è´¥åœºæ™¯å¯æ¢å¤ä¸”ç»“æœå¯è¿½è¸ª |
| AHR-QA-007 | ç¼–å†™ç°åº¦ä¸Šçº¿ä¸å›æ»šéªŒæ”¶æ¸…å• | Task | P0 | Week 4 ç›¸å…³ä»»åŠ¡ | å¯æ”¯æŒä¸Šçº¿å‰ Go/No-Go å®¡æ ¸ |
| AHR-QA-008 | ç»„ç»‡ UAT å¹¶è¾“å‡ºé—®é¢˜æ¸…å• | Task | P0 | æ‰€æœ‰ P0 ä»»åŠ¡ | UAT å®Œæˆå¹¶æœ‰é—®é¢˜é—­ç¯è®°å½• |

## 7. å»ºè®® Sprint åˆ’åˆ†

### Sprint 1
- AHR-BE-001 ~ AHR-BE-007
- AHR-AI-001 ~ AHR-AI-004
- AHR-FE-001 ~ AHR-FE-003
- AHR-QA-001 ~ AHR-QA-003

### Sprint 2
- AHR-BE-008 ~ AHR-BE-014
- AHR-AI-006 ~ AHR-AI-009
- AHR-FE-004 ~ AHR-FE-006
- AHR-QA-004 ~ AHR-QA-006

### Sprint 3
- AHR-BE-015 ~ AHR-BE-019
- AHR-AI-010 ~ AHR-AI-011
- AHR-FE-007 ~ AHR-FE-008
- AHR-QA-007

### Sprint 4
- AHR-BE-020 ~ AHR-BE-024
- AHR-AI-012
- AHR-FE-009 ~ AHR-FE-011
- AHR-QA-008

## 8. Jira å­—æ®µå»ºè®®

| å­—æ®µ | å»ºè®®å€¼ |
|---|---|
| Issue Type | Epic / Story / Task / Bug |
| Priority | P0 / P1 / P2 |
| Component | Backend / AI / Frontend / QA / Connector |
| Labels | `ai-hr`, `boss`, `mvp`, `fastapi`, `vue3`, `mysql` |
| Sprint | Sprint 1 ~ Sprint 4 |
| Assignee | æŒ‰èŒèƒ½åˆ†é… |

## 9. ä¸Šçº¿å‰å¿…é¡»å®Œæˆçš„ P0 ä»»åŠ¡
- AHR-BE-001 è‡³ AHR-BE-022
- AHR-AI-001 è‡³ AHR-AI-011
- AHR-FE-001 è‡³ AHR-FE-008
- AHR-QA-001 è‡³ AHR-QA-008

## 10. AI Ö´ĞĞ×´Ì¬£¨´úÂëÂäµØ¿Ú¾¶£¬³ÖĞø¸üĞÂ£©

> ¸üĞÂÈÕÆÚ£º2026-03-20  
> ¿Ú¾¶£º½ö±ê¼Ç¡°´úÂë¿ÉÖ´ĞĞ + ÓĞ½Ó¿Ú + ÓĞ²âÊÔ¸²¸Ç¡±µÄÈÎÎñ¡£

### ÒÑÍê³É

- AHR-AI-001£º¶¨Òå¼òÀú½á¹¹»¯Êä³ö Schema  
  - ´úÂëÒÀ¾İ£º`ai_hr/schemas/ai_resume.py`
- AHR-AI-002£ºÊµÏÖ¼òÀú½âÎö·şÎñ½Ó¿Ú  
  - ´úÂëÒÀ¾İ£º`POST /api/v1/ai/resume/parse`¡¢`ai_hr/services/ai_resume.py`
- AHR-AI-003£ºÊµÏÖ¼òÀúÇåÏ´Óë×Ö¶Î±ê×¼»¯  
  - ´úÂëÒÀ¾İ£º`POST /api/v1/ai/resume/normalize`¡¢`ai_hr/services/ai_resume.py`

### ÅäÌ×ÊµÏÖ£¨Ö§³Å AHR-AI-001~003£©

- Êı¾İ±íÄ£ĞÍ£º`candidate_resume_profiles`¡¢`candidate_resume_risks`  
  - ´úÂëÒÀ¾İ£º`ai_hr/db/models/candidate_resume_profile.py`¡¢`ai_hr/db/models/candidate_resume_risk.py`
- ²éÑ¯½Ó¿Ú£º`GET /api/v1/candidates/{candidate_id}/resume-profile`
- ²âÊÔ¸²¸Ç£º`tests/test_ai_hr_ai_resume.py`

### ´ıÖ´ĞĞ£¨ÏÂÒ»Ë³Î»£©

- AHR-AI-004£º¸ÚÎ»Æ¥ÅäÆÀ·Ö¹æÔòÒıÇæ£¨AI ×¨ÊôÅúÁ¿ÆÀ·Ö½Ó¿Ú£©
- AHR-AI-005£º·çÏÕ±êÇ©ÔöÇ¿£¨¹æÔòÀ©Õ¹ + ¿É½âÊÍÊä³ö£©
- AHR-AI-007/008/009/011£ºÒâÍ¼·ÖÀà¡¢×Ô¶¯»Ø¸´Éú³É¡¢µÍÖÃĞÅ¶È×ªÈË¹¤¡¢ºÏ¹æÀ¹½Ø£¨AI ×¨Êô½Ó¿Ú»¯£©
- AHR-AI-010£º°´¸ÚÎ»ÈËÊıµÄ×Ô¶¯ÑûÔ¼¼Æ»®Óë·¢ËÍ
- AHR-AI-012£ºÀëÏßÆÀ¹ÀÓë¾ö²ß×·×Ù

## 11. AI Ö´ĞĞ×´Ì¬£¨2026-03-20 µÚ¶şÅú£©

### ±¾´ÎÍê³É£¨AHR-AI-004/005£©

- AHR-AI-004£º¸ÚÎ»Æ¥ÅäÆÀ·Ö¹æÔòÒıÇæ£¨ÅúÁ¿ÆÀ·Ö½Ó¿Ú»¯£©
  - ½Ó¿Ú£º`POST /api/v1/ai/candidates/score`
  - Âä¿â£º`candidate_job_scores`
  - Êä³ö£º×Ü·Ö¡¢Î¬¶È·Ö¡¢½âÊÍ¡¢·çÏÕ±êÇ©¡¢ÆÀ·Ö°æ±¾

- AHR-AI-005£º·çÏÕ±êÇ©Ê¶±ğÔöÇ¿£¨ÆÀ·Ö½×¶Î£©
  - ÔÚÆÀ·ÖÁ´Â·Êä³ö `risk_tags`£¨Èç `skills_missing`¡¢`resume_too_short`¡¢`job_hops_high`¡¢`skills_match_low`£©
  - ÅÅĞòÓë shortlist ½á¹ûÍ¸´«·çÏÕ±êÇ©

### ÅäÌ×½Ó¿ÚÓëÊı¾İ

- ÅÅĞò½Ó¿Ú£º`POST /api/v1/ai/candidates/rank`
- ÈëÎ§²éÑ¯£º`GET /api/v1/jobs/{job_id}/shortlist`
- Êı¾İ±í£º`candidate_job_scores`¡¢`job_shortlists`

### ÑéÖ¤½á¹û

- ²âÊÔÎÄ¼ş£º`tests/test_ai_hr_ai_scoring.py`
- È«Á¿»Ø¹é£º`26 passed`

### ÏÂÒ»Åú½¨ÒéË³Ğò

- AHR-AI-007£ºÒâÍ¼·ÖÀà½Ó¿Ú»¯
- AHR-AI-008£º×Ô¶¯»Ø¸´Éú³É½Ó¿Ú»¯
- AHR-AI-009£ºµÍÖÃĞÅ¶È×ªÈË¹¤²ßÂÔ¹Ì»¯
- AHR-AI-011£ºÃô¸ĞÄÚÈİÓëºÏ¹æÀ¹½Ø

## 12. LLM Éú²ú»¯ÈÎÎñÇåµ¥£¨°´Éè¼Æ¸å²ğ½â£¬Ö´ĞĞÖĞ£©

> Ä¿±ê£ºÔÚ²»ÆÆ»µÏÖÓĞ API µÄÇ°ÌáÏÂ£¬Öğ²½ÒıÈë´óÄ£ĞÍÄÜÁ¦²¢±£Áô¹æÔò¶µµ×¡£  
> ×´Ì¬¶¨Òå£º`TODO` / `DOING` / `DONE`¡£

### ½×¶Î A£ºÆ½Ì¨»ù´¡²ã£¨±¾ÂÖÓÅÏÈ£©

- [ ] A-01£¨DOING£©ĞÂÔö LLM Æ½Ì¨Ä¿Â¼ÓëºËĞÄÄ£¿é£º`client/router/prompts/contracts/guardrails/fallback`
- [ ] A-02£¨DOING£©ĞÂÔö²ßÂÔ²ã£º`policy/decision.py`¡¢`policy/thresholds.py`
- [ ] A-03£¨DOING£©ĞÂÔöÔËĞĞÊ±Êı¾İ±íÄ£ĞÍ£º`ai_model_configs/ai_prompt_versions/ai_feature_flags/ai_request_traces/ai_decision_logs`
- [ ] A-04£¨TODO£©ĞÂÔöÔËĞĞÊ±²Ö´¢£ºÄ£ĞÍÂ·ÓÉÅäÖÃ¶ÁÈ¡¡¢trace/decision Âä¿â
- [ ] A-05£¨TODO£©ĞÂÔöÍ¨ÓÃ schema£º`schemas/ai_llm.py`¡¢`schemas/ai_policy.py`

### ½×¶Î B£ºÒµÎñ±àÅÅ½ÓÈë£¨µÚ¶ş²½£©

- [ ] B-01£¨TODO£©`AIResume` ½ÓÈë LLM ±àÅÅ£¨LLM first + heuristic fallback£©
- [ ] B-02£¨TODO£©`AIScoring` ½ÓÈë LLM Î¬¶ÈÀ©Õ¹£¨ÏîÄ¿/¾­Àú£©+ Ë«¹ìÈÚºÏ
- [ ] B-03£¨TODO£©`Conversation` ½ÓÈëÒâÍ¼·ÖÀàÓë»Ø¸´Éú³É£¨²ßÂÔÃÅ¿Ø£©
- [ ] B-04£¨TODO£©ĞÂÔöÄÚ²¿ÔËĞĞÊ± API£¨Ä£ĞÍÅäÖÃ/»Ò¶È¿ª¹Ø/Prompt °æ±¾¹ÜÀí£©

### ½×¶Î C£ºÖÎÀíÓëÉÏÏß£¨µÚÈı²½£©

- [ ] C-01£¨TODO£©ĞÂÔöÀëÏßÆÀ²â½Å±¾¹Ç¼ÜÓëÖ¸±ê½á¹¹
- [ ] C-02£¨TODO£©ĞÂÔö»Ò¶È²ßÂÔ£¨°´×â»§/¸ÚÎ»£©Óë»Ø¹ö¿ª¹Ø
- [ ] C-03£¨TODO£©ÍêÉÆÉó¼Æ×·×ÙÓë¸æ¾¯Ö¸±ê

### ÑéÊÕ»ùÏß

- [ ] T-01 ÏÖÓĞ¹¦ÄÜ»Ø¹é²âÊÔÈ«²¿Í¨¹ı
- [ ] T-02 ĞÂÔö LLM »ù´¡²ãµ¥²âÍ¨¹ı
- [ ] T-03 ÎÄµµ£¨ÒÑÊµÏÖ¹¦ÄÜÇåµ¥£©Íê³É¸üĞÂ

## 13. LLM ÈÎÎñÖ´ĞĞ½øÕ¹£¨2026-03-20£©

### ÒÑÍê³É£¨½×¶Î A£©

- A-01£¨DONE£©LLM Æ½Ì¨Ä¿Â¼ÓëºËĞÄÄ£¿é£º`client/router/prompts/contracts/guardrails/fallback`
- A-02£¨DONE£©²ßÂÔ²ã£º`policy/decision.py`¡¢`policy/thresholds.py`
- A-03£¨DONE£©ÔËĞĞÊ±Êı¾İ±íÄ£ĞÍ£º
  - `ai_model_configs`
  - `ai_prompt_versions`
  - `ai_feature_flags`
  - `ai_request_traces`
  - `ai_decision_logs`
- A-04£¨DONE£©ÔËĞĞÊ±²Ö´¢£º`repositories/ai_runtime.py`¡¢`repositories/ai_observability.py`
- A-05£¨DONE£©Í¨ÓÃ schema£º`schemas/ai_llm.py`¡¢`schemas/ai_policy.py`

### ÒÑ¿ªÊ¼£¨½×¶Î B£©

- B-01£¨DONE£©`AIResume` ÒÑ½ÓÈë LLM ¿ª¹ØÂ·¾¶£¨Ä¬ÈÏ¹Ø±Õ£¬±£Áô heuristic fallback£©
- B-02£¨DONE£©`AIScoring` ÒÑ½ÓÈë LLM ÈÚºÏÆÀ·Ö¿ª¹Ø£¨Ä¬ÈÏ¹Ø±Õ£¬±£Áô¹æÔò·Ö£©
- B-03£¨DONE£©`Conversation` ÒÑ½ÓÈë LLM ×Ô¶¯»Ø¸´Â·¾¶¿ª¹Ø£¨Ä¬ÈÏ¹Ø±Õ£©

### ´ı¼ÌĞø

- B-04£¨TODO£©ĞÂÔöÄÚ²¿ÔËĞĞÊ± API£¨Ä£ĞÍÅäÖÃ/»Ò¶È¿ª¹Ø/Prompt °æ±¾¹ÜÀí£©
- C-01£¨TODO£©ÀëÏßÆÀ²â½Å±¾¹Ç¼Ü
- C-02£¨TODO£©»Ò¶ÈÓë»Ø¹ö²ßÂÔÍêÉÆ
- C-03£¨TODO£©¸æ¾¯ÓëÖ¸±ê¿´°å

### ÑéÖ¤

- ĞÂÔö²âÊÔ£º`tests/test_ai_hr_llm_platform.py`
- »Ø¹é½á¹û£º`28 passed`

## 14. ÔËĞĞÊ±¹ÜÀí API Ö´ĞĞ½á¹û£¨2026-03-20£©

- B-04£¨DONE£©ÄÚ²¿ÔËĞĞÊ±¹ÜÀí API ÒÑÍê³É£º
  - `PUT/GET /api/v1/ai/runtime/feature-flags/{feature_key}`
  - `POST /api/v1/ai/runtime/feature-flags/{feature_key}/rollback`
  - `PUT/GET /api/v1/ai/runtime/model-configs/{task_key}`
  - `PUT/GET /api/v1/ai/runtime/prompts/{task_key}`
- »Ø¹ö¿ª¹ØÉúĞ§£º`rule_only` ¿É¼´Ê±¹Ø±Õ LLM Â·¾¶²¢»ØÍË¹æÔòÁ´Â·¡£
- ¸²¸Ç²âÊÔ£º`tests/test_ai_hr_ai_runtime.py`
- »Ø¹é½á¹û£º`30 passed`

## 15. AHR-AI-007/008 Ö´ĞĞ½á¹û£¨2026-03-20£©

### ÒÑÍê³É

- AHR-AI-007£¨DONE£©ÒâÍ¼·ÖÀà½Ó¿Ú»¯
  - `POST /api/v1/ai/reply/classify-intent`
- AHR-AI-008£¨DONE£©×Ô¶¯»Ø¸´Éú³É½Ó¿Ú»¯£¨º¬¿É½âÊÍÊä³ö£©
  - `POST /api/v1/ai/reply/generate`

### ´úÂëÂäµØ

- `ai_hr/schemas/ai_reply.py`
- `ai_hr/services/ai_reply_llm.py`
- `ai_hr/api/routes/ai.py`
- `tests/test_ai_hr_ai_reply.py`

### ÑéÖ¤½á¹û

- ĞÂÔö²âÊÔ£º`tests/test_ai_hr_ai_reply.py`
- È«Á¿»Ø¹é£º`32 passed`

## 16. AHR-BE-016/017 Ö´ĞĞ½á¹û£¨2026-03-20£©

### ÒÑÍê³É

- AHR-BE-016£¨DONE£©ÃæÊÔÅÅÆÚ API
  - `POST /api/v1/interviews/schedule`
  - `GET /api/v1/interviews/{interview_id}`
- AHR-BE-017£¨DONE£©BOSS Ô¼ÃæÖ´ĞĞÓë×´Ì¬»ØĞ´
  - `POST /api/v1/interviews/{interview_id}/dispatch`
  - `POST /api/v1/interviews/{interview_id}/sync-status`

### ´úÂëÂäµØ

- `ai_hr/schemas/interviews.py`
- `ai_hr/repositories/interviews.py`
- `ai_hr/services/interviews.py`
- `ai_hr/api/routes/interviews.py`
- `ai_hr/connectors/boss.py`£¨ĞÂÔö `schedule_interview`¡¢`sync_interview_status`£©

### ÑéÖ¤½á¹û

- ĞÂÔö²âÊÔ£º`tests/test_ai_hr_interviews.py`
- È«Á¿»Ø¹é£º`pytest -q` -> `36 passed`

## 17. 3-Agent Ö´ĞĞ½øÕ¹£¨2026-03-20 µÚ1ÂÖ£©

### Ö÷Agent½áÂÛ

- µ±Ç°Ä£Ê½£º1 Ö÷ Agent + 2 ×Ó Agent Ñ­»·ÍÆ½ø¡£
- ±¾ÂÖÓÅÏÈ¼¶£ºÏÈÍê³É `AHR-AI-010`£¬²¢ĞĞÍÆ½ø `AHR-AI-012`¡£

### ±¾ÂÖÒÑÍê³É

- AHR-AI-010£¨DONE£©£º°´¸ÚÎ»ÈËÊı×Ô¶¯ÑûÔ¼¼Æ»®Óë·¢ËÍ±àÅÅ
  - ĞÂÔö½Ó¿Ú£º
    - `POST /api/v1/jobs/{job_id}/interview/plan`
    - `POST /api/v1/jobs/{job_id}/interview/send`
    - `GET /api/v1/jobs/{job_id}/interview/progress`
  - ´úÂëÂäµØ£º
    - `ai_hr/api/routes/interviews.py`
    - `ai_hr/schemas/interviews.py`
    - `ai_hr/services/interviews.py`
    - `ai_hr/repositories/interviews.py`
    - `ai_hr/db/models/interview.py`£¨ĞÂÔö `target_headcount`£©
    - `tests/test_ai_hr_interviews.py`
  - ÑéÖ¤½á¹û£º
    - `tests/test_ai_hr_interviews.py` -> `7 passed`
  - ÄÜÁ¦ËµÃ÷£º
    - °´ `headcount` ´Ó shortlist Éú³ÉÑûÔ¼¼Æ»®
    - ·¢ËÍ½×¶Î¾ß±¸²»³¬·¢¿ØÖÆÓëÍ¬¸ÚÎ»ºòÑ¡ÈËÃİµÈ±£»¤
    - Ìá¹©¸ÚÎ»Î¬¶ÈµÄÑûÔ¼½ø¶È¾ÛºÏÍ³¼Æ

### ±¾ÂÖ½øĞĞÖĞ

- AHR-AI-012£¨DOING£©£ºÀëÏßÆÀ²âÔËĞĞÓë±¨¸æ½Ó¿Ú×îĞ¡¿ÉÖ´ĞĞ°æ±¾
  - ×Ó Agent ÒÑÖØÅÉ£¬Ä¿±êÎª `POST /api/v1/ai/eval/run` Óë `GET /api/v1/ai/eval/report`
  - Íê³Éºó½«¼ÌĞø¸üĞÂ±¾Çåµ¥Îª DONE/TODO ½áÂÛ

## 18. 3-Agent Ö´ĞĞ½øÕ¹£¨2026-03-20 µÚ1ÂÖÊÕ¿Ú£©

### ±¾ÂÖĞÂÔöÍê³É

- AHR-AI-012£¨DONE£©£ºÀëÏßÆÀ²âÔËĞĞÓë±¨¸æ½Ó¿Ú£¨×îĞ¡¿ÉÖ´ĞĞ£©
  - ĞÂÔö½Ó¿Ú£º
    - `POST /api/v1/ai/eval/run`
    - `GET /api/v1/ai/eval/report`
  - ´úÂëÂäµØ£º
    - `ai_hr/schemas/ai_eval.py`
    - `ai_hr/services/ai_eval.py`
    - `ai_hr/repositories/ai_eval.py`
    - `ai_hr/db/models/ai_eval_run.py`
    - `ai_hr/api/routes/ai.py`
    - `tests/test_ai_hr_ai_eval.py`
  - ÑéÖ¤½á¹û£º
    - `tests/test_ai_hr_interviews.py + tests/test_ai_hr_ai_eval.py` -> `10 passed`

### µÚ1ÂÖ½áÊø×´Ì¬

- ÒÑÍê³É£º`AHR-AI-010`¡¢`AHR-AI-012`
- ÏÂÒ»ÂÖÓÅÏÈ½¨Òé£º`AHR-AI-009`£¨µÍÖÃĞÅ¶È×ªÈË¹¤²ßÂÔ¹Ì»¯£©+ `AHR-AI-011`£¨Ãô¸ĞÄÚÈİºÏ¹æÀ¹½ØÔöÇ¿£©

## 19. ÖÎÀíÂ·ÓÉ½ÓÈëÖ´ĞĞ½á¹û£¨2026-03-20£©

### ÒÑÍê³É

- ÖÎÀíÂ·ÓÉÒÑ½ÓÈëÖ÷Â·ÓÉ£º
  - `POST /api/v1/approvals`
  - `POST /api/v1/approvals/{approval_id}/decision`
  - `GET /api/v1/audit/events`
  - `GET /api/v1/metrics/funnel`

### ´úÂëÂäµØ

- `ai_hr/api/router.py`£¨×¢²á `governance.router`£©
- `tests/test_ai_hr_governance.py`£¨ĞÂÔöÖÎÀí½Ó¿Ú²âÊÔ£©

### ÑéÖ¤½á¹û

- `tests/test_ai_hr_governance.py` -> `2 passed`
- È«Á¿»Ø¹é£º`pytest -q` -> `44 passed`

## 20. AI ÃæÊÔ¹ÙÈÎÎñ°üAÖ´ĞĞ½á¹û£¨2026-03-20£©

### ÒÑÍê³É

- AHR-AIINT-BE-001£¨DONE£©£ºAI ÃæÊÔ¹Ù 5 ÕÅºËĞÄÄ£ĞÍ±í
- AHR-AIINT-DB-001£¨DONE£©£ººËĞÄÊı¾İÄ£ĞÍÄÉÈë×Ô¶¯½¨±í
- AHR-AIINT-BE-002£¨DONE£©£º`POST /api/v1/ai/interviews/sessions`

### ÑéÖ¤

- ×¨Ïî²âÊÔ£º`tests/test_ai_hr_ai_interviews.py` -> `2 passed`
- È«Á¿»Ø¹é£º`pytest -q` -> `46 passed`
