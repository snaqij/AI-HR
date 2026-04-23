# Bugfix Requirements Document

## Introduction

岗位的每日简历请求配额（max_daily_resume_requests）被超出，系统允许发送的请求数量超过了设定的限制。这导致实际消耗的请求点数超出了预期的配额控制。

根本原因是 `count_requests_today()` 方法使用 `last_resume_requested_at` 时间戳来统计当天的请求数，但该字段也会在 `mark_resume_visible()` 方法中被设置（当字段为 None 时）。这导致某些从未真正发送请求的记录也被计入统计，使得配额检查失效。

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN 统计某个岗位当天的简历请求数时 THEN 系统使用 `last_resume_requested_at >= start_of_day` 条件统计记录数

1.2 WHEN 简历状态从其他状态变为 "visible" 且 `last_resume_requested_at` 为 None 时 THEN 系统会设置 `last_resume_requested_at` 为当前时间

1.3 WHEN 上述情况发生时 THEN 该记录会被错误地计入当天的请求统计中，即使该记录并未真正发送简历请求

1.4 WHEN 配额检查基于错误的统计数据时 THEN 系统允许发送超出 `max_daily_resume_requests` 限制的请求

### Expected Behavior (Correct)

2.1 WHEN 统计某个岗位当天的简历请求数时 THEN 系统 SHALL 使用 `resume_request_count` 字段的总和来统计实际发送的请求数

2.2 WHEN 简历状态变为 "visible" 时 THEN 系统 SHALL 不影响当天请求数的统计结果

2.3 WHEN 配额检查执行时 THEN 系统 SHALL 准确反映实际发送的请求数量

2.4 WHEN 当天请求数达到 `max_daily_resume_requests` 限制时 THEN 系统 SHALL 阻止发送更多请求

### Unchanged Behavior (Regression Prevention)

3.1 WHEN 调用 `mark_resume_requested()` 方法时 THEN 系统 SHALL CONTINUE TO 增加 `resume_request_count` 计数器

3.2 WHEN 调用 `mark_resume_requested()` 方法时 THEN 系统 SHALL CONTINUE TO 设置 `last_resume_requested_at` 为当前时间

3.3 WHEN 调用 `mark_resume_visible()` 方法时 THEN 系统 SHALL CONTINUE TO 将 `resume_request_status` 设置为 "visible"

3.4 WHEN 简历请求重试逻辑执行时 THEN 系统 SHALL CONTINUE TO 正常工作

3.5 WHEN 查询单个 pipeline 记录的请求历史时 THEN 系统 SHALL CONTINUE TO 能够访问 `last_resume_requested_at` 和 `resume_request_count` 字段
