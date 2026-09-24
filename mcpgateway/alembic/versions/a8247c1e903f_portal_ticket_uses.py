"""Track single-use parent application login tickets.

Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

from alembic import op
import sqlalchemy as sa

revision = "a8247c1e903f"
down_revision = "d72f8a1c903e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the ticket-use table when it is absent."""
    inspector = sa.inspect(op.get_bind())
    if "portal_ticket_uses" in inspector.get_table_names():
        return
    op.create_table(
        "portal_ticket_uses",
        sa.Column("jti", sa.String(36), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_portal_ticket_uses_expires_at", "portal_ticket_uses", ["expires_at"])


def downgrade() -> None:
    """Remove the ticket-use table when it exists."""
    if "portal_ticket_uses" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("portal_ticket_uses")
