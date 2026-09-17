"""Store encrypted API tokens for authorized retrieval.

Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

from alembic import op
import sqlalchemy as sa

revision = "d72f8a1c903e"
down_revision = "c31d7e4a092b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add encrypted storage without attempting to recover historical hashes."""
    inspector = sa.inspect(op.get_bind())
    if "email_api_tokens" in inspector.get_table_names() and "encrypted_token" not in {column["name"] for column in inspector.get_columns("email_api_tokens")}:
        op.add_column("email_api_tokens", sa.Column("encrypted_token", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove encrypted storage while retaining token hashes."""
    inspector = sa.inspect(op.get_bind())
    if "email_api_tokens" in inspector.get_table_names() and "encrypted_token" in {column["name"] for column in inspector.get_columns("email_api_tokens")}:
        op.drop_column("email_api_tokens", "encrypted_token")
