from ten_runtime import App, LogLevel, TenEnv


class AiHrApp(App):
    def on_init(self, ten_env: TenEnv) -> None:
        print("[main.py] on_init invoked", flush=True)
        ten_env.log(LogLevel.INFO, "AI-HR Python app initialized")
        ten_env.on_init_done()

    def on_deinit(self, ten_env: TenEnv) -> None:
        print("[main.py] on_deinit invoked", flush=True)
        ten_env.log(LogLevel.INFO, "AI-HR Python app deinitialized")
        ten_env.on_deinit_done()


if __name__ == "__main__":
    print("[main.py] creating AI-HR app", flush=True)
    app = AiHrApp()
    print("[main.py] starting app.run(False)", flush=True)
    app.run(False)
    print("[main.py] app.run(False) returned", flush=True)
