from __future__ import annotations

import logging
import logging.config

from pythonjsonlogger.json import JsonFormatter


class PlatformJsonFormatter(JsonFormatter):
    def add_fields(
        self,
        log_record: dict[str, object],
        record: logging.LogRecord,
        message_dict: dict[str, object],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record.setdefault("level", record.levelname)
        log_record.setdefault("logger", record.name)


def configure_logging(level: str) -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": "app.core.logging.PlatformJsonFormatter",
                    "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "level": level.upper(),
                }
            },
            "root": {"handlers": ["default"], "level": level.upper()},
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": level.upper(), "propagate": False},
                "uvicorn.access": {
                    "handlers": ["default"],
                    "level": level.upper(),
                    "propagate": False,
                },
            },
        }
    )
