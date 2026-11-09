import 'package:http/browser_client.dart';
import 'package:http/http.dart' as http;

/// The browser build sends and accepts cookies for the API origin: the OAuth
/// connections flow binds to the API's session cookie on top-level navigations.
http.Client makeExampleHttpClient() => BrowserClient()..withCredentials = true;
