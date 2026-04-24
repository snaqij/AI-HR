#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from ten_runtime import (
    Addon,
    register_addon_as_extension,
    TenEnv,
)
from .main import TENVADPythonExtension


@register_addon_as_extension("ten_vad_python")
class TENVADPythonExtensionAddon(Addon):
    def on_create_instance(self, ten_env: TenEnv, name: str, context) -> None:
        print(f"[ten_vad] create instance: {name}", flush=True)
        ten_env.log_info("on_create_instance")
        ten_env.on_create_instance_done(TENVADPythonExtension(name), context)
