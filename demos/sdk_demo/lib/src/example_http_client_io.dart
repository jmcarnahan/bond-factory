import 'package:http/http.dart' as http;

/// Outside the browser (the io build and the tests) a plain client is enough.
http.Client makeExampleHttpClient() => http.Client();
