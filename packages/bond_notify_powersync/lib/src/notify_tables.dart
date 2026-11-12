/// PowerSync table definitions for notices and push devices.
library;

import 'package:powersync/powersync.dart';

const kNoticesTable = 'notices';
const kPushDevicesTable = 'push_devices';

/// The synced notices table; add it to the app schema.
List<Table> noticesTables() => throw UnimplementedError('noticesTables is not implemented yet');

/// The upload-only push devices table; add it to the app schema.
List<Table> pushDevicesTables() => throw UnimplementedError('pushDevicesTables is not implemented yet');
