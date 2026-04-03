from ten_runtime import Addon, TenEnv, register_addon_as_extension

from .main import InterviewOrchestratorExtension


@register_addon_as_extension("interview_orchestrator_python")
class InterviewOrchestratorExtensionAddon(Addon):
    def on_create_instance(self, ten_env: TenEnv, name: str, context) -> None:
        print(f"[orchestrator] create instance: {name}", flush=True)
        ten_env.on_create_instance_done(InterviewOrchestratorExtension(name), context)
