"""The link filter on a real PostgreSQL: same page and total as the JSON text match, and the index is used."""
import random

import pytest
from conftest import LinkIndex, Task
from sqlalchemy import text
from sqlalchemy.orm import Session
from support_read import mk

from bond_tasks_py import TaskFilters, list_tasks

pytestmark = pytest.mark.postgres

CONTACTS = [f"contact-{n:03d}" for n in range(200)]


def test_index_filter_matches_the_text_match_and_uses_the_index(pg_engine):
    rng = random.Random(7)
    with Session(pg_engine) as session:
        for n in range(2000):
            picks = rng.sample(CONTACTS, rng.randint(1, 3))
            mk(session, Task, f"t{n:05d}", links=[{"kind": "contact", "id": c, "label": c} for c in picks],
               index_model=LinkIndex)
        session.commit()
        session.execute(text("ANALYZE"))
        for contact in ("contact-007", "contact-123"):
            filters = TaskFilters(link_kind="contact", link_id=contact)
            old, old_total = list_tasks(session, task_model=Task, user_id="u1", filters=filters, limit=10)
            new, new_total = list_tasks(session, task_model=Task, user_id="u1", filters=filters, limit=10,
                                        link_index_model=LinkIndex)
            assert new_total == old_total > 0
            assert [t.id for t in new] == [t.id for t in old]
        plan = "\n".join(row[0] for row in session.execute(text(
            "EXPLAIN SELECT t.id FROM tasks t WHERE t.id IN (SELECT task_id FROM task_link_index "
            "WHERE kind = 'contact' AND ref_id = 'contact-007') ORDER BY t.created_at DESC LIMIT 25")))
        assert "ix_task_link_ref" in plan, plan
