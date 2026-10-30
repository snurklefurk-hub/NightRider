# NightRider messaging: recipients and driver safety

This document is the shared contract for the website, Dispatch, browser Driver and Android Driver.

## Who receives what

| Sender | Recipient tab | Who can read the message |
| --- | --- | --- |
| Rider | Ride messages: Driver + Dispatch | Rider, Dispatch and the currently assigned driver; future assigned drivers inherit shared ride history |
| Rider | Account messages: Dispatch | The rider account and Dispatch only, including between rides |
| Driver | Rider | Rider, Dispatch, current driver; future assigned drivers inherit shared ride history |
| Driver | Dispatch | That driver and Dispatch only, not the rider or other drivers |
| Driver | Team | Dispatch and all drivers, not riders |
| Dispatch | Rider account | Rider and Dispatch only while the server is running; never visible to drivers |
| Dispatch | Ride thread | Rider and Dispatch only, not the assigned driver |
| Dispatch | Driver | Dispatch and the selected driver only |
| Dispatch | Team | Dispatch and all drivers, not riders |

### Temporary messages across every account

**All NightRider chat is ephemeral.** Team, private Driver/Dispatch, ride and rider-account messages are kept only in server-process memory, never in PostgreSQL, rides.json or browser storage. A restart clears conversations and rotates the in-memory chat epoch so already-open browser tabs clear old bubbles. Startup also removes previously stored chat collections from the current state record. This does not erase earlier database backups or operator-saved archives.

While a server remains running, account chats are indexed by rider-account ID; riders and Dispatch can reply between rides. Recipient permissions are unchanged: drivers never see private rider/Dispatch account conversations. There is no SMS, email, push notification or off-browser delivery. Do not treat any chat as reliable long-term correspondence.

### Ride reassignment

Shared ride messages belong to the **ride**, not a particular driver. An assigned replacement driver receives prior shared rider, Dispatch and previous-driver messages. Older rider-originated Dispatch-only messages also follow the new rider-sharing rule. A Dispatch-to-rider-only message and a driver-to-Dispatch-only private message must **not** become visible to future drivers.

Backend authorization, not the selected tab label, decides which messages may be read and sent.

### Driver interaction rules (No Surprises)

1. Recipient buttons remain in the same locations and sizes.
2. Incoming messages must never steal focus, open the keyboard, overlay navigation, switch tabs, or change the selected recipient.
3. Incoming messages must never automatically scroll the chat log or the containing screen.
4. Newly arrived messages may be appended inside a fixed-height log. Use a quiet unread counter, not flashing or pulsing effects.
5. Drivers can change conversations and scroll intentionally, and typed drafts remain intact when networking fails.
6. Do not interrupt navigation with chat alerts. Voice or driver-safe notification design requires separate testing and explicit opt-in.
7. Keep the established NightRider dark and Aero themes; avoid a new visual language.

## Operator history deletion (software demo)

A **non-demo Dispatch administrator only** can use the buttons at the bottom of
the **Messages** and **Recent rides** cards. The controls are never shown to
shared DEMO Dispatch logins or ordinary Dispatch staff. The server enforces
the same restrictions; UI visibility is not authorization.

- **Export summary & clear temporary chats:** exports message counts only
  (never text) and clears the in-memory team, private, ride and account chat
  collections. Rider/driver accounts and ride records are preserved. The
  separate account archive also deliberately omits all chat text.
- **Export & delete ride history:** archives and clears *all* currently
  retained completed/cancelled rides, plus rider history references and
  ratings. It clears their in-memory ride messages but never archives chat
  bodies. Account conversations, team chat, and user logins remain.
- **Fail closed:** both actions are blocked while **any** ride is still active
  or requested. The admin must close or cancel every trip first.
- Each deletion requires the desktop browser File System Access Save As picker,
  server archive content and SHA-256 verification, successful local file
  write/close, a separate irreversible-action confirmation, and an expiring,
  one-time server grant. If data changes between export and deletion, the
  backend rejects deletion and requires a fresh archive.
- The backend cannot inspect a user's disk. It can validate a grant and
  unchanged snapshot, but only the web client can attest successful local save.
  There is deliberately no silent/download-only destructive fallback.
- The archive contains sensitive data from multiple participants. Store it
  securely. These features are for **simulated records only** until legal
  retention, litigation hold, audit and transport-data requirements are
  explicitly evaluated for a future licensed transportation operation.
- The current JSONB app-state implementation has a **per-process** lock and
  ephemeral grants. Do not enable production deletion across multiple workers
  without transactional database protection.
- After clearing chat or rides, the chat history epoch invalidates cached
  message bubbles in other connected web clients. No focus/scroll/tab change
  is triggered in the driver UI.

## Testing before publishing

- Run the isolated Python suite, including `tests/test_chat.py`.
- Run `node --check public/nr-chat.js` and `node tests/client_notify_check.js`.
- Compile the Android project using the Build driver app APK workflow.
- Verify on real devices: new ride, rider before assignment, reassignment with previous-driver messages, private messages, lost network/retry, typing while new text arrives, and switching themes.
- These automated checks are not substitutes for testing while the vehicle is stationary and for real-world connection handling.
