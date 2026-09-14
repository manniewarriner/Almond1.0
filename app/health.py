"""Local readiness checks: config, directories, audit storage, provider syntax.

No network calls. Every check is isolated so one failure doesn't hide the
others (except an unreadable config, which blocks everything downstream).
"""

from __future__ import annotations

import sqlite3

from app.audit.log import init_audit_db
from app.config import AppConfig, load_config
from app.errors import ConfigError
from app.models import CheckStatus, HealthCheckItem, HealthReport


def check_data_dir(config: AppConfig) -> HealthCheckItem:
    try:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        return HealthCheckItem(name="data_dir", status=CheckStatus.OK, detail=str(config.data_dir))
    except OSError as exc:
        return HealthCheckItem(name="data_dir", status=CheckStatus.FAIL, detail=str(exc))


def check_audit_db(config: AppConfig) -> HealthCheckItem:
    try:
        init_audit_db(config.audit_db_path)
        return HealthCheckItem(
            name="audit_db", status=CheckStatus.OK, detail=str(config.audit_db_path)
        )
    except (OSError, sqlite3.Error) as exc:
        return HealthCheckItem(name="audit_db", status=CheckStatus.FAIL, detail=str(exc))


def check_provider_config(config: AppConfig) -> HealthCheckItem:
    needs_key = config.provider_name not in {"fake", "local"}
    if needs_key and not config.provider_api_key:
        return HealthCheckItem(
            name="provider_config",
            status=CheckStatus.FAIL,
            detail=f"provider {config.provider_name!r} requires provider_api_key",
        )
    return HealthCheckItem(
        name="provider_config",
        status=CheckStatus.OK,
        detail=f"provider={config.provider_name}",
    )


def run_health_check(env_file: str | None = None) -> HealthReport:
    try:
        config = load_config(env_file)
    except ConfigError as exc:
        return HealthReport(
            items=[HealthCheckItem(name="config", status=CheckStatus.FAIL, detail=str(exc))]
        )

    items = [
        HealthCheckItem(
            name="config", status=CheckStatus.OK, detail=f"provider={config.provider_name}"
        ),
        check_data_dir(config),
        check_audit_db(config),
        check_provider_config(config),
    ]
    return HealthReport(items=items)
