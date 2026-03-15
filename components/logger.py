import logging
import os
import logging.handlers


class Logger:
    def __init__(self):
        self.logger = None

    def setup(self):
        if not self.logger:
            self.logger = logging.getLogger("Translator (by Sam·D·Leung)")
            self.logger.setLevel(logging.INFO)
            os.makedirs("logs", exist_ok=True)
            handler = logging.handlers.RotatingFileHandler(
                "logs/ocr_tool.log", maxBytes=1024 * 1024, backupCount=5
            )
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
            )
            self.logger.addHandler(handler)

    def get(self):
        if not self.logger:
            self.setup()
        return self.logger
