"""actionable alerts and query migrations

Revision ID: 96b784074d1c
Revises: ff32e2dd3106
Create Date: 2025-04-23 18:39:07.626918

"""

import json
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import yaml

# revision identifiers, used by Alembic.
revision: str = '96b784074d1c'
down_revision: Union[str, None] = 'ff32e2dd3106'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    query_dir = os.environ.get('SIGNAL_QUERY_DIR', 'default')
    base_dir = os.path.dirname(__file__)

    directory = os.path.join(base_dir, '../../queries', query_dir)
    directory = os.path.normpath(directory)

    for filename in os.listdir(directory):
        if filename.endswith('.yaml') or filename.endswith('.yml'):
            file_path = os.path.join(directory, filename)
            with open(file_path, 'r') as f:
                yaml_data = yaml.safe_load(f)
                conn = op.get_bind()
                conn.execute(
                    sa.text(
                        """
                            INSERT INTO actionable_insight_queries (
                                id, version, type, title, name, description, enabled,
                                periodicity, goal_lines, projections, query, plots,
                                created_at, updated_at
                            )
                            VALUES (
                                :id, :version, :type, :title, :name, :description, :enabled,
                                CAST(:periodicity AS jsonb), CAST(:goal_lines AS jsonb),
                                CAST(:projections AS jsonb), CAST(:query AS jsonb),
                                CAST(:plots AS jsonb), now(), now()
                            )
                        """
                    ),
                    {
                        'id': yaml_data['id'],
                        'version': yaml_data['version'],
                        'type': yaml_data['type'],
                        'title': yaml_data['title'],
                        'name': yaml_data['name'],
                        'description': yaml_data.get('description', ''),
                        'enabled': yaml_data.get('enabled', True),
                        'periodicity': json.dumps(yaml_data['periodicity']),
                        'goal_lines': json.dumps(yaml_data['goal_lines']),
                        'projections': json.dumps(yaml_data['projections']),
                        'query': json.dumps(yaml_data['query']),
                        'plots': json.dumps(yaml_data['plots']),
                    },
                )
    op.create_foreign_key(
        'fk_insight_query',
        'actionable_alerts',
        'actionable_insight_queries',
        ['signal_id'],
        ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_insight_query', 'actionable_alerts', type_='foreignkey')
    op.execute('TRUNCATE TABLE actionable_insight_queries RESTART IDENTITY CASCADE')
