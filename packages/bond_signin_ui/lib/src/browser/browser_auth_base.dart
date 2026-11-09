/// The system browser, as the sign-in flow needs it.
///
/// [run] opens [url] in the system's authentication browser and completes with
/// the address the browser was sent back to ([callback] says which return
/// address to wait for). Embedded web views are never used: the identity
/// providers refuse them. On web [run] navigates the whole window and never
/// completes, because the page reloads; read the return on the next load with
/// `SignInReturn.parse`.
///
/// The system sign-in sheet that appears is an operating-system requirement,
/// not an app dialog.
abstract class BrowserAuth {
  Future<Uri> run(Uri url, {required Uri callback, bool ephemeral = false});
}
