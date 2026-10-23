# Kagi Custom Bang

GroundRecall's first Kagi integration is a navigation shortcut. It opens the
GroundRecall browser search page; it does not inject private records into
Kagi's result list or send a query to a GroundRecall server without the user's
browser session.

In Kagi, create a Custom Bang with:

- **Name:** GroundRecall
- **Bang:** `!gr`
- **URL:** `http://127.0.0.1:8765/search?q=%s`

The `%s` placeholder is replaced by Kagi with the full search query. The
GroundRecall HTTP service must be running on that address, and the browser
must have an authenticated session if the service requires one. For a service
reachable from another device, replace `127.0.0.1:8765` with the intentionally
configured HTTPS address; `localhost` on a phone or another computer refers
to that device, not the GroundRecall host.

The query is sent to Kagi as part of the bang invocation before the redirect.
Do not put bearer tokens, store paths, or other credentials in the Custom Bang
URL. Use the direct GroundRecall page for queries that must remain local to
the GroundRecall host.

The browser target is `/search?q=...`; `/` remains an equivalent bookmarked
search page. Record links use `/records/{url-encoded-stable-id}` and remain
stable across service restarts while the record is available to the session.
