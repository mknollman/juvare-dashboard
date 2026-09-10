import os.path

from config import Config


def main():
    cfg = Config()
    os.makedirs(cfg.DATA_DIR, exist_ok=True)
    import server
    server.start_server(cfg)


if __name__ == "__main__":
    main()