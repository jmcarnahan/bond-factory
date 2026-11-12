/// A tiny SQL engine for [FakeSyncDb] table mode with `applySql: true`.
///
/// It understands exactly the shapes the adapters write: `SELECT cols FROM t [WHERE e] [ORDER BY e [DESC], ...]
/// [LIMIT n]`, `INSERT [OR REPLACE] INTO t (cols) VALUES (...)`, `UPDATE t SET c = e, ... WHERE e` and
/// `DELETE FROM t WHERE e`. An expression is `AND` / `OR` / `NOT`, parentheses, `= != <> < <= > >=`,
/// `IS [NOT] NULL`, `[NOT] IN (...)`, columns, `?` parameters, numbers, `'strings'` and `NULL`. Anything else
/// throws [UnsupportedError], so a test fails loudly instead of passing on a statement nobody evaluated.
/// Comparison follows SQLite: NULL compares unknown (false), NULL sorts first, text compares by code unit.
library;

import '../sync_db.dart';

typedef Tables = Map<String, List<SyncRow>>;

/// Column names per table; when a table is listed here an unknown column in a statement throws.
typedef Columns = Map<String, Set<String>>;

final RegExp _token = RegExp(r"\s*(?:('(?:[^']|'')*')|([A-Za-z_][A-Za-z0-9_]*)|(-?\d+(?:\.\d+)?)|(<=|>=|<>|!=|[=<>?(),*]))");

List<String> _lex(String sql) {
  final out = <String>[];
  var i = 0;
  final s = sql.trim().replaceAll(RegExp(r';\s*$'), '');
  while (i < s.length) {
    final m = _token.matchAsPrefix(s, i);
    if (m == null || m.end == i) throw UnsupportedError('fake sql: cannot read "${s.substring(i)}" in $sql');
    out.add(m.group(0)!.trim());
    i = m.end;
  }
  return out;
}

class _P {
  _P(this.sql, this.params, this.columns) : t = _lex(sql);
  final String sql;
  final List<Object?> params;
  final Set<String>? columns;
  final List<String> t;
  int i = 0;
  int paramAt = 0;

  bool get done => i >= t.length;
  String get peek => done ? '' : t[i];
  bool at(String kw) => !done && t[i].toUpperCase() == kw;
  bool eat(String kw) {
    if (at(kw)) {
      i++;
      return true;
    }
    return false;
  }

  void need(String kw) {
    if (!eat(kw)) throw UnsupportedError('fake sql: expected $kw at "$peek" in $sql');
  }

  String ident() {
    final s = t[i++];
    if (!RegExp(r'^[A-Za-z_]').hasMatch(s)) throw UnsupportedError('fake sql: expected a name, got $s in $sql');
    return s;
  }

  void checkColumn(String c) {
    final known = columns;
    if (known != null && !known.contains(c)) throw StateError('fake sql: no such column $c in $sql');
  }

  /// Parses an expression into a function of one row.
  Object? Function(SyncRow) or() {
    var l = and();
    while (eat('OR')) {
      final a = l, b = and();
      l = (r) {
        final x = _truth(a(r)), y = _truth(b(r));
        return x == true || y == true ? true : (x == null || y == null ? null : false);
      };
    }
    return l;
  }

  Object? Function(SyncRow) and() {
    var l = not();
    while (eat('AND')) {
      final a = l, b = not();
      l = (r) {
        final x = _truth(a(r)), y = _truth(b(r));
        return x == false || y == false ? false : (x == null || y == null ? null : true);
      };
    }
    return l;
  }

  Object? Function(SyncRow) not() {
    if (eat('NOT')) {
      final a = not();
      return (r) {
        final x = _truth(a(r));
        return x == null ? null : !x;
      };
    }
    return cmp();
  }

  Object? Function(SyncRow) cmp() {
    final a = operand();
    if (eat('IS')) {
      final neg = eat('NOT');
      need('NULL');
      return (r) => (a(r) == null) != neg;
    }
    final neg = eat('NOT');
    if (eat('IN')) {
      need('(');
      final items = [operand()];
      while (eat(',')) {
        items.add(operand());
      }
      need(')');
      return (r) {
        final v = a(r);
        if (v == null) return null;
        final hit = items.any((f) => _cmp(v, f(r)) == 0);
        return hit != neg;
      };
    }
    if (neg) throw UnsupportedError('fake sql: NOT without IN in $sql');
    const ops = {'=', '!=', '<>', '<', '<=', '>', '>='};
    if (!ops.contains(peek)) return a;
    final op = t[i++];
    final b = operand();
    return (r) {
      final x = a(r), y = b(r);
      if (x == null || y == null) return null;
      final c = _cmp(x, y);
      return switch (op) {
        '=' => c == 0,
        '!=' || '<>' => c != 0,
        '<' => c < 0,
        '<=' => c <= 0,
        '>' => c > 0,
        _ => c >= 0,
      };
    };
  }

  Object? Function(SyncRow) operand() {
    final s = peek;
    if (s == '(') {
      i++;
      final e = or();
      need(')');
      return e;
    }
    i++;
    if (s == '?') {
      if (paramAt >= params.length) throw StateError('fake sql: too few parameters for $sql');
      final v = params[paramAt++];
      return (_) => v;
    }
    if (s.startsWith("'")) {
      final v = s.substring(1, s.length - 1).replaceAll("''", "'");
      return (_) => v;
    }
    final n = num.tryParse(s);
    if (n != null) return (_) => n;
    if (s.toUpperCase() == 'NULL') return (_) => null;
    if (s.toUpperCase() == 'TRUE' || s.toUpperCase() == 'FALSE') {
      final v = s.toUpperCase() == 'TRUE' ? 1 : 0;
      return (_) => v;
    }
    checkColumn(s);
    return (r) => r[s];
  }
}

bool? _truth(Object? v) {
  if (v == null) return null;
  if (v is bool) return v;
  if (v is num) return v != 0;
  return false;
}

Object? _norm(Object? v) => v is bool ? (v ? 1 : 0) : v;

int _cmp(Object? x, Object? y) {
  final a = _norm(x), b = _norm(y);
  if (a is num && b is num) return a.compareTo(b);
  if (a is String && b is String) return a.compareTo(b);
  if (a is num) return -1; // SQLite: numbers sort before text
  if (b is num) return 1;
  return a.toString().compareTo(b.toString());
}

int _sortCmp(Object? x, Object? y) {
  final a = _norm(x), b = _norm(y);
  if (a == null || b == null) return a == null ? (b == null ? 0 : -1) : 1;
  return _cmp(a, b);
}

String _tableOf(List<String> t, String after) {
  final k = t.indexWhere((s) => s.toUpperCase() == after);
  if (k < 0 || k + 1 >= t.length) throw UnsupportedError('fake sql: no $after in ${t.join(' ')}');
  return t[k + 1];
}

/// The statement's table name, or null for a statement this engine does not read.
String? tableOfWrite(String sql) {
  final t = _lex(sql);
  if (t.isEmpty) return null;
  switch (t.first.toUpperCase()) {
    case 'INSERT':
      return _tableOf(t, 'INTO');
    case 'UPDATE':
      return t[1];
    case 'DELETE':
      return _tableOf(t, 'FROM');
  }
  return null;
}

/// Applies one INSERT / UPDATE / DELETE to [tables]. Returns false for any other statement.
bool applyWrite(Tables tables, Columns columns, String sql, List<Object?> params) {
  final table = tableOfWrite(sql);
  if (table == null) return false;
  final p = _P(sql, params, columns[table]);
  final rows = tables.putIfAbsent(table, () => []);
  switch (p.t.first.toUpperCase()) {
    case 'INSERT':
      p.i = 1;
      final replace = p.eat('OR') && (p.eat('REPLACE') || (throw UnsupportedError('fake sql: only OR REPLACE')));
      p.need('INTO');
      p.ident();
      p.need('(');
      final names = [p.ident()];
      while (p.eat(',')) {
        names.add(p.ident());
      }
      p.need(')');
      p.need('VALUES');
      p.need('(');
      final values = [p.operand()(const {})];
      while (p.eat(',')) {
        values.add(p.operand()(const {}));
      }
      p.need(')');
      if (names.length != values.length) throw StateError('fake sql: ${names.length} columns, ${values.length} values');
      for (final n in names) {
        p.checkColumn(n);
      }
      final row = <String, Object?>{for (final c in columns[table] ?? const <String>{}) c: null};
      for (var k = 0; k < names.length; k++) {
        row[names[k]] = values[k];
      }
      final at = rows.indexWhere((r) => r['id'] == row['id']);
      if (at >= 0) {
        if (!replace) throw StateError('fake sql: UNIQUE constraint failed: $table.id');
        rows[at] = row;
      } else {
        rows.add(row);
      }
    case 'UPDATE':
      p.i = 2;
      p.need('SET');
      final sets = <String, Object?>{};
      do {
        final c = p.ident();
        p.checkColumn(c);
        p.need('=');
        sets[c] = p.operand()(const {});
      } while (p.eat(','));
      final where = p.eat('WHERE') ? p.or() : null;
      if (!p.done) throw UnsupportedError('fake sql: trailing "${p.peek}" in $sql');
      for (final r in rows) {
        if (where == null || _truth(where(r)) == true) r.addAll(sets);
      }
    default:
      p.i = 1;
      p.need('FROM');
      p.ident();
      final where = p.eat('WHERE') ? p.or() : null;
      if (!p.done) throw UnsupportedError('fake sql: trailing "${p.peek}" in $sql');
      rows.removeWhere((r) => where == null || _truth(where(r)) == true);
  }
  return true;
}

/// Answers a SELECT over [rows] (already copies): WHERE, ORDER BY, LIMIT, and a column list.
List<SyncRow> select(String sql, List<Object?> params, List<SyncRow> rows, Set<String>? columns) {
  final p = _P(sql, params, columns);
  if (!p.eat('SELECT')) return rows;
  final names = <String>[];
  do {
    names.add(p.t[p.i++]);
  } while (p.eat(','));
  p.need('FROM');
  p.ident();
  var out = rows;
  if (p.eat('WHERE')) {
    final w = p.or();
    out = [for (final r in out) if (_truth(w(r)) == true) r];
  }
  if (p.eat('ORDER')) {
    p.need('BY');
    final keys = <(Object? Function(SyncRow), bool)>[];
    do {
      final e = p.cmp();
      keys.add((e, p.eat('DESC')));
      p.eat('ASC');
    } while (p.eat(','));
    out = [...out]..sort((a, b) {
        for (final (e, desc) in keys) {
          final c = _sortCmp(e(a), e(b));
          if (c != 0) return desc ? -c : c;
        }
        return 0;
      });
  }
  if (p.eat('LIMIT')) {
    final n = p.operand()(const {});
    if (n is num) out = out.take(n.toInt()).toList();
  }
  if (!p.done) throw UnsupportedError('fake sql: trailing "${p.peek}" in $sql');
  if (names.length == 1 && names.first == '*') return out;
  for (final n in names) {
    p.checkColumn(n);
  }
  return [for (final r in out) {for (final n in names) n: r[n]}];
}
