# Migrating to bond_tasks_py

Task table, due instant, per-user settings, link index, three-stage notice ledger and sweep, calendar mirror
(`libs/bond_tasks_py`). The wire is `docs/contracts/tasks.md` and `docs/contracts/notices.md`. Wired in
`services/sdk_example` (`tasks_wiring.py`, `routes/tasks.py`, `routes/jobs.py`). Legend: `docs/migration/README.md`.
Dart side: `bond_tasks.md`. Adoption order: `todo-checklist.md`.

## 1. What it replaces

| App | Goes away | Stays app-side |
|---|---|---|
| S | `TaskRecord` body, `task_service.py` (CRUD, roles, list, summary, `to_item`), `task_outlook_mirror.py`, the `/tasks` router except parse, `handlers_tasks.py` | contact and loan columns, `relink_loan_ids`, parse (LLM), loan-actor rule, admin override |
| A | `PersonalEventRecord`, `personal_events.py` reminder code, the `/me/events` router | the interpret route, the Today day grouping, the reminder job body |

Column renames from S: `mirror_to_outlook` is `mirror_enabled`. `outlook_event_id`, `outlook_event_user_id` are
`external_event_id`, `external_account_user_id` (new `external_provider`, `external_etag`). Contact and loan ids become
`links` `[{kind, id, label}]` (keep your FK columns on your subclass and list them in `host_columns`). Error codes are
lower case (`task_not_found`) in `{"detail": {code, message}}`. A: checklist items (no start) become date-only tasks, timed
entries keep `due_time`, `done_at` becomes `status = done`, `removed_at` has no equivalent (cancel instead).

## 2. What the app adds
Six new tables in the SAME database as `tasks`, and two new columns on it. The lib ships no migration: write one
revision and assert each `*_COLUMNS` constant in a test (`schema_contract` from `bond_service_kit`).

| Mixin | Table |
|---|---|
| `TasksMixin` | `tasks`: new `priority`, `due_at`, index `(status, due_at)` |
| `TaskUserSettingsMixin`, `TaskLinkIndexMixin` | `task_user_settings`, `task_link_index` |
| `NoticeLedgerMixin`, `NoticeOutboxMixin` | `task_notice_ledger`, `task_notice_outbox` |
| `NoticesMixin`, `PushDevicesMixin` (sibling libs) | `notices`, `push_devices` |

Routes: copy `routes/tasks.py` and `routes/task_today.py`. `bond_tasks_py_host.md` lists every route, its service call, the
signatures and the models block. Notice and device routes: `bond_notify_py.md`, `bond_push_py.md`. `now` is required in `task_item`, `list_tasks` and `summary` (no `today`). Pass the link index model to `delete`.
Wire `after_write=make_link_hook(LinkIndex)`. `sync_routes(on_deleted=)` is called `(ctx, session, task_id, owner_user_id)`: dismiss notices there.

## 3. The reminder is removed
Old queued reminder: `reminders.py`, the `Scheduler` protocol, `schedule_reminder`, `fire_reminder`, `cancel_reminder`, `compute_remind_at`, `refresh_remind_at`, `dedupe_key`, `JOB_TYPE`, the `scheduler=` parameter of `sync_routes`,
the columns `remind_at` and `reminded_at`, the wire keys of the same names (TaskItem has 24 keys). Drop both columns in
your revision and delete your `task_reminder` job type, its `Scheduler` and its `cancel_reminder` calls. A pending
reminder job does nothing useful after the upgrade: let it drain or delete it.
`remind_minutes_before` stays, with `-3` use my default now the default for new rows. Existing rows keep their value
(`-2` stays "no close notice"). The due and past notices still go out for every open dated task, so pass `since=` on
the first sweep. The sweep reads the value and no job is queued.

## 4. SQLite savepoint setup
On SQLite call `sqlite_savepoint_setup(engine)` once, before the engine's first connection. Without it `sweep_due` and
`deliver_pending` raise `RuntimeError`, because a released savepoint would commit the outer transaction. SQLite 3.35 or
later is needed (`RETURNING`). PostgreSQL needs nothing.

## 5. Running the sweep
From a `bond_jobs` tick, as the `before` hook, throttled with `before_every`:
```python
# models are in bond_tasks_py_host.md; push = PushNotifier(PushDevice, ApnsSender(key_pem, key_id, team_id))
KW = dict(task_model=Task, ledger_model=TaskNoticeLedger, outbox_model=TaskNoticeOutbox)
def sweep(session, now):  # bond_jobs.tick(..., before=sweep, before_every=60); tick commits after the hook
    sweep_due(session, now=now, prefs=StoredPreferences(TaskUserSettings), tz="UTC",
              transactional=[InboxNotifier(Notice)], channels=["push"], **KW)
```

Run `deliver_pending` as a job (it needs a `commit` callable). Or a plain script, every minute:

```python
with Session(engine) as s:   # engine = sqlite_savepoint_setup(create_engine(url)) on SQLite
    sweep(s, now)            # pass since=activation_time on the first run
    s.commit()
    deliver_pending(s, ledger_model=TaskNoticeLedger, outbox_model=TaskNoticeOutbox, task_model=Task,
                    notifiers={"push": push}, now=now, commit=s.commit)
    prune_ledger(s, now=now, **KW)  # daily, then bond_notify_py.prune_notices(s, Notice, now)
    s.commit()
```

Pass `since=` on first activation (old stage times are then skipped). List `"push"` only when a real sender is configured.

## 6. A chat-tool Notifier in 15 lines

A `Notifier` runs after commit and must be idempotent on `notice_id`. Return one of four strings.

```python
class ChatNotifier:
    def __init__(self, post, seen): self.post, self.seen = post, seen  # post(text, key) -> bool
    def send(self, session, notice):
        if notice.notice_id in self.seen: return "ok"
        try: sent = self.post(f"{notice.title}: {notice.body}", notice.notice_id)
        except TimeoutError: return "retryable"
        if not sent: return "failed"
        self.seen.add(notice.notice_id)
        return "ok"
# sweep_due(..., channels=["chat"]); deliver_pending(..., notifiers={"chat": ChatNotifier(post, seen)})
```

## 7. Call-site changes and checks

- On done, cancel and delete call `dismiss_for_source`, and when `due_date`, `due_time` or the assignee changes call
  `dismiss_stale` (both are in `bond_notify_py`, not this lib). `apply_notice_action` is the one handler (done or cancel on a closed task does nothing). After a reassign use `notice_recipients(task)` and `bond_notify_py.dismiss_for_source(..., user_ids=)`.
- Settings: `update_settings(..., on_recomputed=)` returns `(prefs, warnings)`; in the hook call `bond_notify_py.dismiss_stale`. Pass `time_zone` with client writes.
- Order: revision, backfill, wire the sweep, swap the router. Assert every `*_COLUMNS`, round-trip
  `fixtures/tasks/task.json` through `task_item`, run `make -C libs/bond_tasks_py test`.
- Test: a fake clock sweep over close, due and past with an `InboxNotifier`, and one `sweep_due` twice (second claims 0).
- Known limits: with both a Google and a Microsoft connection the example mirrors to Google only. A multi-process
  SQLite app must retry on a busy error.
