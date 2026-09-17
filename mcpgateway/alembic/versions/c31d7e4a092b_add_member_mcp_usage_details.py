"""Add MCP metadata to token usage records.

Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

# Third-Party
from alembic import op
import sqlalchemy as sa

revision = "c31d7e4a092b"
down_revision = "5e211ec89cad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable metadata without changing historical request records."""
    inspector = sa.inspect(op.get_bind())
    if "token_usage_logs" in inspector.get_table_names() and "mcp_details" not in {c["name"] for c in inspector.get_columns("token_usage_logs")}:
        op.add_column("token_usage_logs", sa.Column("mcp_details", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Remove the optional MCP metadata column."""
    inspector = sa.inspect(op.get_bind())
    if "token_usage_logs" in inspector.get_table_names() and "mcp_details" in {c["name"] for c in inspector.get_columns("token_usage_logs")}:
        op.drop_column("token_usage_logs", "mcp_details")
