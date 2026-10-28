# NightRider messaging — recipients and driver safety

This document is the shared contract for the website, Dispatch, browser Driver and Android Driver.

## Who receives what

| Sender | Recipient tab | Who can read the message |
| --- | --- | --- |
| Rider | Driver + Dispatch (the only option) | Rider, Dispatch and the currently assigned driver; future assigned drivers inherit shared ride history |
| Driver | Rider | Rider, Dispatch, current driver; future assigned drivers inherit shared ride history |
| Driver | Dispatch | That driver and Dispatch only, not the rider or other drivers |
| Driver | Team | Dispatch and all drivers, not riders |
| Dispatch | Rider | Rider and Dispatch only, not the assigned driver |
| Dispatch | Driver | Dispatch and the selected driver only |
| Dispatch | Team | Dispatch and all drivers, not riders |

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

## Testing before publishing

- Run the isolated Python suite, including `tests/test_chat.py`.
- Run `node --check public/nr-chat.js` and `node tests/client_notify_check.js`.
- Compile the Android project using the Build driver app APK workflow.
- Verify on real devices: new ride, rider before assignment, reassignment with previous-driver messages, private messages, lost network/retry, typing while new text arrives, and switching themes.
- These automated checks are not substitutes for testing while the vehicle is stationary and for real-world connection handling.
