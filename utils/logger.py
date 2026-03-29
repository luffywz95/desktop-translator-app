from datetime import datetime
import logging
import os
import logging.handlers


class Logger:
    _logger = None

    def __init__(self, file_name: str = "app"):
        self.file_name = file_name
        self.setup()

    def setup(self):
        if not self._logger:
            self._logger = logging.getLogger()
            self._logger.setLevel(logging.INFO)
            os.makedirs("logs", exist_ok=True)
            handler = logging.handlers.RotatingFileHandler(
                f"logs/{self.file_name}_{datetime.now().strftime('%Y-%m-%d')}.log",
                maxBytes=1024 * 1024,
                backupCount=5,
            )
            handler.setFormatter(
                logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            )
            self._logger.addHandler(handler)

    def get(self):
        if not self._logger:
            self.setup()
        return self._logger
