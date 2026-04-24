from ten_runtime import Addon, TenEnv, register_addon_as_extension

from .main import AliyunNlsASRExtension


@register_addon_as_extension("aliyun_nls_asr_python")
class AliyunNlsASRExtensionAddon(Addon):
    def on_create_instance(self, ten_env: TenEnv, name: str, context) -> None:
        print(f"[aliyun_nls_asr] create instance: {name}", flush=True)
        ten_env.on_create_instance_done(AliyunNlsASRExtension(name), context)
