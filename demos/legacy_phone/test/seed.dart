import 'package:powersync/powersync.dart';

/// Rows an old build wrote, by raw SQL, before the SDK store existed (the stage-one columns only):
/// no `due_at`, no `priority`; `''` in `assigned_user_id` and `client_ref`; the flag NULL on one row; a timed row, a
/// date-only row and an undated row; one done row; one row with no `mirror_status`. "Now" is 2026-03-11 13:00 local.
///
/// open for u-owner, in the app's order: o-timed (09:00, overdue), o-pm (17:00), o-dated, o-next (assigned to me),
/// o-later, o-none (undated). Not mine: o-theirs. Done: o-done.
Future<void> seedLegacy(PowerSyncDatabase db) async {
  for (final u in const [
    ['u-owner', 'Olive Owner', 'owner@example.com'],
    ['u-editor', null, 'editor@example.com'],
    ['u-other', 'Otto Other', 'other@example.com'],
  ]) {
    await db.execute('INSERT INTO users (id, name, email) VALUES (?, ?, ?)', u);
  }
  await db.execute('INSERT INTO clients (id, first_name, last_name) VALUES (?, ?, ?)', ['cl-1', 'Ada', 'Lovelace']);
  await db.execute('INSERT INTO clients (id, first_name, last_name) VALUES (?, ?, ?)', ['cl-2', 'Grace', null]);
  for (final c in const [
    ['ca-1', 'cl-1', 'Contract review', 101],
    ['ca-2', 'cl-2', 'Estate', 202],
    ['ca-3', 'cl-1', 'Appeal', 303],
  ]) {
    await db.execute('INSERT INTO cases (id, client_id, label, file_no) VALUES (?, ?, ?, ?)', c);
  }
  const cols = 'id, owner_user_id, created_by, assigned_user_id, client_ref, case_ref, case_file_no, title, due_date, due_time, '
      'status, completed_at, completed_by, mirror_status, sync_to_calendar, source, created_at, updated_at';
  final rows = <List<Object?>>[
    ['o-timed', 'u-owner', '', 'cl-1', 'ca-1', 101, 'Old timed', '2026-03-11', '09:00', 'open', null, null, 'mirrored', 1, '2026-03-01'],
    ['o-pm', 'u-owner', 'u-editor', null, null, null, 'Old afternoon', '2026-03-11', '17:00', 'open', null, null, 'pending', null, '2026-03-02'],
    ['o-dated', 'u-owner', null, '', null, null, 'Old dated', '2026-03-11', null, 'open', null, null, 'skipped', 0, '2026-03-03'],
    ['o-next', 'u-other', 'u-owner', 'cl-2', 'ca-2', 202, 'Assigned to me', '2026-03-12', null, 'open', null, null, 'pending', 1, '2026-03-04'],
    ['o-later', 'u-owner', null, null, null, null, 'Old later', '2026-03-20', '08:30', 'open', null, null, 'pending', 1, '2026-03-05'],
    ['o-none', 'u-owner', null, 'cl-1', null, null, 'Old undated', null, null, 'open', null, null, null, 1, '2026-03-06'],
    ['o-done', 'u-owner', null, 'cl-1', null, null, 'Old done', '2026-03-10', null, 'done', '2026-03-11T15:00:00.000Z', 'u-owner', 'skipped', 1, '2026-03-01'],
    ['o-theirs', 'u-other', 'u-editor', 'cl-1', null, null, 'Not mine', '2026-03-11', null, 'open', null, null, 'pending', 1, '2026-03-07'],
  ];
  for (final r in rows) {
    final [id, owner, assigned, client, kase, fileNo, title, date, time, status, doneAt, doneBy, mirror, flag, created] = r;
    await db.execute('INSERT INTO tasks ($cols) VALUES (${List.filled(18, '?').join(', ')})', [
      id, owner, owner, assigned, client, kase, fileNo, title, date, time, status, doneAt, doneBy, mirror, flag, 'app',
      '${created}T10:00:00.000Z', '${created}T10:00:00.000Z', //
    ]);
  }
}
