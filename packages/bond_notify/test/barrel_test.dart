import 'package:bond_api/bond_api.dart';
import 'package:bond_notify/bond_notify.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

void main() {
  test('the barrel exports every public name', () {
    // One reference per exported file: removing an export stops this compiling.
    const Notice notice = Notice(id: 'n');
    const NoticePage page = NoticePage(items: [notice]);
    final api = NoticesApi(ApiClient(baseUrl: Uri.parse('https://api.test'), http: MockClient((_) async => http.Response('{}', 200))));
    final NoticeFeed feed = PollingNoticeFeed(api);
    final controller = NoticeController(feed);
    const NoticeState state = NoticeState();
    final NoticeAlert alert = browserNoticeAlert();
    const NoticeLabels labels = NoticeLabels();
    expect(page.items.single, notice);
    expect(controller.feed, feed);
    expect(state.unreadCount, 0);
    expect(alert, isNotNull);
    expect(labels.inboxTitle, isNotEmpty);
    controller.dispose();
    feed.dispose();
  });
}
