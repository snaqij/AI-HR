from ten_runtime import Addon, TenEnv, register_addon_as_extension

from .main import TencentTTSExtension


@register_addon_as_extension("tencent_tts_python")
class TencentTTSExtensionAddon(Addon):
    def on_create_instance(self, ten_env: TenEnv, name: str, context) -> None:
        print(f"[tencent_tts] create instance: {name}", flush=True)
        ten_env.on_create_instance_done(TencentTTSExtension(name), context)
