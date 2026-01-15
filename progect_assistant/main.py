from progect_assistant.assistant.app import AppConfig, create_runtime


def main() -> None:
    config = AppConfig.from_env()
    runtime = create_runtime(config)
    runtime.run()


if __name__ == "__main__":
    main()
