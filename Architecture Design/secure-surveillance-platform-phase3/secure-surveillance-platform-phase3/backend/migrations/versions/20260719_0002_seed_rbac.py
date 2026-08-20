"""Seed system roles and OpenAPI permissions.

Revision ID: 20260719_0002
Revises: 20260719_0001
Create Date: 2026-07-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260719_0002"
down_revision: Union[str, None] = "20260719_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERMISSIONS = [
    "audit.read", "cameras.ai.configure", "cameras.create", "cameras.read",
    "cameras.test", "cameras.update", "custody.create", "custody.read",
    "custody.transfer", "custody.transfer.accept", "custody.transfer.reject",
    "evidence.content.read", "evidence.export", "evidence.ingest",
    "evidence.quarantine", "evidence.read", "evidence.verify",
    "incidents.assign", "incidents.close", "incidents.confirm",
    "incidents.create", "incidents.false_positive", "incidents.notes.create",
    "incidents.read", "incidents.update", "notifications.read",
    "reports.export", "reports.generate", "reports.read", "users.create",
    "users.credentials.reset", "users.deactivate", "users.read",
    "users.roles.assign", "users.roles.remove", "users.update",
]

ROLE_PERMISSIONS = {
    "ADMINISTRATOR": set(PERMISSIONS),
    "SECURITY_OFFICER": {
        "cameras.read", "cameras.test", "incidents.create", "incidents.read",
        "incidents.update", "incidents.confirm", "incidents.false_positive",
        "incidents.assign", "incidents.notes.create", "evidence.read",
        "evidence.content.read", "custody.read", "custody.create",
        "reports.read", "reports.generate", "notifications.read",
    },
    "INVESTIGATOR": {
        "incidents.read", "incidents.update", "incidents.notes.create",
        "incidents.close", "evidence.read", "evidence.content.read",
        "evidence.export", "evidence.verify", "custody.read", "custody.create",
        "custody.transfer", "custody.transfer.accept", "custody.transfer.reject",
        "reports.read", "reports.generate", "reports.export", "notifications.read",
    },
    "SECURITY_MANAGER": {
        "users.read", "cameras.read", "incidents.create", "incidents.read",
        "incidents.update", "incidents.assign", "incidents.confirm",
        "incidents.false_positive", "incidents.close", "evidence.read",
        "evidence.content.read", "evidence.verify", "custody.read",
        "reports.read", "reports.generate", "reports.export", "audit.read",
        "notifications.read",
    },
}


def _quote(value: str) -> str:
    return value.replace("'", "''")


def upgrade() -> None:
    for role_name in ROLE_PERMISSIONS:
        role = _quote(role_name)
        op.execute(
            sa.text(
                f"INSERT INTO roles (name, description, is_system_role) "
                f"VALUES ('{role}', 'System role: {role}', true) "
                "ON CONFLICT (name) DO NOTHING"
            )
        )

    for code in PERMISSIONS:
        resource, action = code.split(".", 1)
        permission = _quote(code)
        resource_value = _quote(resource)
        action_value = _quote(action)
        op.execute(
            sa.text(
                f"INSERT INTO permissions (code, resource, action, description) "
                f"VALUES ('{permission}', '{resource_value}', '{action_value}', "
                f"'Allows {permission}') ON CONFLICT (code) DO NOTHING"
            )
        )

    for role_name, permissions in ROLE_PERMISSIONS.items():
        role = _quote(role_name)
        for permission_code in permissions:
            permission = _quote(permission_code)
            op.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "SELECT r.id, p.id FROM roles r CROSS JOIN permissions p "
                    f"WHERE r.name = '{role}' AND p.code = '{permission}' "
                    "ON CONFLICT DO NOTHING"
                )
            )


def downgrade() -> None:
    permission_values = ", ".join(f"'{_quote(code)}'" for code in PERMISSIONS)
    role_values = ", ".join(f"'{_quote(role)}'" for role in ROLE_PERMISSIONS)
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE role_id IN "
            f"(SELECT id FROM roles WHERE name IN ({role_values}))"
        )
    )
    op.execute(sa.text(f"DELETE FROM permissions WHERE code IN ({permission_values})"))
    op.execute(sa.text(f"DELETE FROM roles WHERE name IN ({role_values})"))
