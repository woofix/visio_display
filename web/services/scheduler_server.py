"""Run Visio's background schedulers without forking web workers."""
import logging
import threading


def main():
    from app import create_app

    create_app(start_scheduler=True)
    logging.getLogger(__name__).info("Visio background schedulers started in a dedicated process")
    threading.Event().wait()


if __name__ == '__main__':
    main()
