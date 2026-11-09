/// What the connector needs to know about the app's tables and rules.
library;

import 'package:bond_sync/bond_sync.dart';
import 'package:powersync/powersync.dart';

/// The two local-only tables the adapter keeps: `sync_rejections` (refused
/// writes, shown inline) and `sync_meta` (key/value bookkeeping). Add them to
/// the app's [Schema]: `Schema([...appTables, ...syncSupportTables()])`.
List<Table> syncSupportTables() => [
      Table.localOnly('sync_rejections', [
        for (final c in const ['table_name', 'row_id', 'action', 'code', 'message', 'payload', 'created_at', 'op'])
          Column.text(c),
      ]),
      const Table.localOnly('sync_meta', [Column.text('key'), Column.text('value')]),
    ];

/// The app builds one; the adapter has no table names of its own.
class SyncPolicy {
  const SyncPolicy({
    required this.schema,
    this.notUploadedTables = const {},
    this.createPuts = const {},
    this.silentWrites = const {},
    this.rekeyChildren = const {},
    this.sendCaps = const {},
    this.endpointOverride,
    this.chunkSize = kChunkSize,
    this.chunkBytes = kChunkBytes,
    this.transientMaxCount = kTransientMaxCount,
    this.transientMaxSpan = kTransientMaxSpan,
    this.transientStale = kTransientStale,
  });

  final Schema schema;

  /// Tables whose writes never go through the upload route.
  final Set<String> notUploadedTables;

  /// Puts that CREATE a row the server may not have; a refusal removes the
  /// optimistic local row. The value is the set of actions, or null for any.
  final Map<String, Set<String>?> createPuts;

  /// Writes whose refusal leaves nothing for the person to do, so no note is
  /// kept: table -> actions (null = every action).
  final Map<String, Set<String>?> silentWrites;

  /// When the server re-keys a row, the child columns that name it:
  /// table -> [(childTable, column)].
  final Map<String, List<(String, String)>> rekeyChildren;

  /// The most ops of one kind (`table:action`) one request takes.
  final Map<String, int> sendCaps;

  /// Overrides the endpoint the token answer carries (a local sync URL).
  final String? endpointOverride;

  final int chunkSize;

  /// Upper bound on the JSON bytes of one request.
  final int chunkBytes;
  final int transientMaxCount;
  final Duration transientMaxSpan;
  final Duration transientStale;

  /// Every synced (not local-only) table.
  Set<String> get schemaTables => {
        for (final t in schema.tables)
          if (!t.localOnly) t.name,
      };

  /// Synced tables whose writes go through the upload route.
  Set<String> get sendableTables => schemaTables.difference(notUploadedTables);

  bool isSilentWrite({required String table, String? action}) => rules.isSilentWrite(table: table, action: action);

  OutcomeRules get rules => OutcomeRules(createPuts: createPuts, silentWrites: silentWrites, rekeyChildren: rekeyChildren);

  UploadLimits get limits => UploadLimits(
        chunkSize: chunkSize,
        chunkBytes: chunkBytes,
        sendCaps: sendCaps,
        transientMaxCount: transientMaxCount,
        transientMaxSpan: transientMaxSpan,
        transientStale: transientStale,
      );
}
