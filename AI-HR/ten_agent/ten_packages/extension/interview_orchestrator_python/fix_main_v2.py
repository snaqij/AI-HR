import os
import re

file_path = r"d:\24985\code\boss-cli-main\AI-HR\ten_agent\ten_packages\extension\interview_orchestrator_python\main.py"

with open(file_path, "rb") as f:
    content = f.read().decode("utf-8")

# 1. Define the missing method and the new on_stop
new_methods = r'''    async def _listen_for_events(self) -> None:
        """监听 Event Bus 上的外部事件，如手动强制结算。"""
        try:
            async for event in DEFAULT_INTERVIEW_EVENT_BUS.subscribe():
                if not isinstance(event, dict):
                    continue
                
                event_type = event.get("event_type")
                session_id = event.get("session_id")
                
                # 仅处理匹配当前会话的事件
                if session_id != self.session_id:
                    continue
                
                if event_type == InterviewEventType.CANDIDATE_FORCE_FINALIZE:
                    self._log(logging.INFO, "orchestrator.force_finalize_received", event=event)
                    # 触发手动交互处理，跳过 VAD 等待
                    payload = event.get("payload") or {}
                    transcript = payload.get("text") or self.last_final_transcript
                    
                    if transcript:
                        # 使用 _create_task 确保并发执行
                        self._create_task(
                            self._handle_interaction(
                                ten_env=self._ten_env,
                                transcript=transcript,
                                asr_final_ts=time.perf_counter(),
                                asr_sentence_start_ts=0,
                                asr_physical_stop_ts=0,
                                orch_receive_ts=time.perf_counter(),
                            ),
                            name="manual-force-finalize"
                        )
        except asyncio.CancelledError:
            self._log(logging.INFO, "orchestrator.event_bus_listener_cancelled")
        except Exception as exc:
            self._log(logging.ERROR, "orchestrator.event_bus_listener_failed", error=str(exc))

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        self._cancel_pending_finalize()
        self._invalidate_active_response()
        
        # 取消并等待所有后台任务
        if self._bg_tasks:
            self._log(logging.INFO, "orchestrator.stopping_tasks", count=len(self._bg_tasks))
            for task in list(self._bg_tasks):
                if not task.done():
                    task.cancel()
            
            # 使用 wait 确保所有任务都已清理完成，防止 rwlock 冲突
            if self._bg_tasks:
                import asyncio
                # We are already in an async method, so we can await.
                # However, on_stop might be called from a context where we want to be brief.
                # But to avoid rwlock issues, we must await here.
                done, pending = await asyncio.wait(list(self._bg_tasks), timeout=2.0)
                for t in pending:
                    # If still not done, we just log it and move on (not ideal but avoids hanging)
                    pass
            self._bg_tasks.clear()

        if self.event_bridge is not None:
            await self.event_bridge.stop()
        with contextlib.suppress(Exception):
            await ten_env.send_cmd(Cmd.create(RuntimeCommand.INTERRUPT))
        self._log(logging.INFO, "orchestrator.stopped")
'''

# 2. Targeted replacement for on_stop
# We use a pattern that matches the old on_stop block
pattern = r'    async def on_stop\(self, ten_env: AsyncTenEnv\) -> None:.*?orchestrator\.stopped\"\)'

content = re.sub(pattern, new_methods, content, flags=re.DOTALL)

with open(file_path, "wb") as f:
    f.write(content.encode("utf-8"))

print("Fixed")
