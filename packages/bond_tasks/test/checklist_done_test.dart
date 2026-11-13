import 'package:bond_tasks/bond_tasks.dart';
import 'package:test/test.dart';

void main() {
  const never = ChecklistItem(id: 'a', text: 'one');
  final ticked = ChecklistItem(id: 'b', text: 'two', doneAt: DateTime.utc(2026, 11, 8, 12));

  test('an item never ticked here sends no done; a ticked item sends done_at and no done', () {
    expect(never.toJson(), {'id': 'a', 'text': 'one', 'done_at': null});
    final j = ticked.toJson();
    expect(j.containsKey('done'), isFalse);
    expect(j['done_at'], isNotNull);
  });

  test('clearDone marks the item unticked and sends done false', () {
    final u = ticked.copyWith(clearDone: true);
    expect(u.unticked, isTrue);
    expect(u.doneAt, isNull);
    expect(u.toJson(), {'id': 'b', 'text': 'two', 'done': false, 'done_at': null});
  });

  test('the flag survives a rename, ends on a new tick and is not part of equality', () {
    final u = ticked.copyWith(clearDone: true);
    expect(u.copyWith(text: 'x').unticked, isTrue);
    final again = u.copyWith(doneAt: DateTime.utc(2026, 11, 9));
    expect(again.unticked, isFalse);
    expect(again.toJson().containsKey('done'), isFalse);
    expect(u, const ChecklistItem(id: 'b', text: 'two'));
    expect(never.copyWith(text: 'y').unticked, isFalse);
  });

  test('a patch and a draft carry the unticked item only', () {
    final items = [never, ticked.copyWith(clearDone: true), ticked];
    final patch = TaskPatch(checklist: items).toJson();
    expect([for (final c in patch['checklist'] as List) (c as Map)['done']], [null, false, null]);
    final draft = TaskDraft(title: 't', checklist: items).toJson();
    expect([for (final c in draft['checklist'] as List) (c as Map)['done']], [null, false, null]);
  });

  test('fromJson ignores done and never sets the flag', () {
    expect(ChecklistItem.fromJson({'id': 'a', 'text': 'x', 'done': false, 'done_at': null}).unticked, isFalse);
    expect(ChecklistItem.fromJson({'id': 'a', 'text': 'x', 'done': true}).doneAt, isNull);
    expect(ChecklistItem.fromJson(ticked.toJson()), ticked);
  });

  test('toStoredJson never carries done, even for an unticked item', () {
    expect(ticked.copyWith(clearDone: true).toStoredJson(), {'id': 'b', 'text': 'two', 'done_at': null});
    expect(ticked.toStoredJson().keys, ['id', 'text', 'done_at']);
  });
}
