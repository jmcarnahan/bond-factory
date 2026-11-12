/// PowerSync table definitions for notices and push devices.
library;

import 'package:powersync/powersync.dart';

const kNoticesTable = 'notices';
const kPushDevicesTable = 'push_devices';

/// The stored columns of a notice (besides the implicit `id`); `data` is JSON text.
const List<String> kNoticeColumns = [
  'user_id',
  'kind',
  'title',
  'body',
  'data',
  'created_at',
  'read_at',
  'dismissed_at',
];

/// The stored columns of a push device row (besides the implicit `id`).
const List<String> kPushDeviceColumns = [
  'user_id',
  'device_id',
  'token',
  'platform',
  'environment',
  'topic',
  'last_seen_at',
  'disabled_at',
  'created_at',
];

/// The synced notices table; add it to the app schema.
List<Table> noticesTables() => [
      Table(
        kNoticesTable,
        [for (final c in kNoticeColumns) Column.text(c)],
        indexes: [
          const Index('user_created', [IndexedColumn('user_id'), IndexedColumn('created_at')]),
        ],
      ),
    ];

/// The synced push devices table (the device writes its own row); add it to the app schema.
List<Table> pushDevicesTables() => [
      Table(
        kPushDevicesTable,
        [for (final c in kPushDeviceColumns) Column.text(c)],
        indexes: [
          const Index('user_device', [IndexedColumn('user_id'), IndexedColumn('device_id')]),
        ],
      ),
    ];
