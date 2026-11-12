"""``InboxNotifier``: the transactional notifier that writes the stored inbox inside the sweep's claim."""

from collections.abc import Sequence
from typing import Any


class InboxNotifier:
    """Satisfies the tasks lib's ``TransactionalNotifier`` by shape: ``write(session, notices)``.

    Intended behaviour: one executemany insert of ``NoticeLike`` rows (target-less ON CONFLICT DO NOTHING, so a replayed
    claim is harmless), ``id = notice.notice_id``, ``source_id = notice.task_id``, ``data`` as in
    ``serialize.DATA_KEYS``. Flushes, never commits; raises to cancel the batch.
    """

    def __init__(self, notice_model: Any) -> None:
        self.notice_model = notice_model

    def write(self, session: Any, notices: Sequence[Any]) -> None:
        raise NotImplementedError("notifier.InboxNotifier.write is not implemented yet")
