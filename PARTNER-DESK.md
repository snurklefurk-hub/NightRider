# Partner Desk and Affiliate Hub — pilot preview

This is a **SOFTWARE DEMO**, not a live transportation service.
No affiliate offer creates a ride, reserves a driver, collects payment, or sends
an external notification. Do not use this workflow for customer commitments.

**Two distinct demonstration experiences**:
- A PUBLIC SANDBOX for anyone opening Partner Portal from `/hub` and choosing
  Partner Desk demo or Affiliate Hub demo. All partner records and sample offers are fictitious, live **only in
  that browser's local storage**, and never touch the server's affiliate database.
- The original PRIVATE OPERATOR / AFFILIATE preview behind administrator
  sessions and administrator-issued partner keys. These server-backed simulated
  offers remain restricted and are **not** displayed in public demos.

## Entry points

- `/hub`: clicking a Rider, Driver or Dispatch tile signs into that existing
  role's shared DEMO account automatically and opens its appropriate workspace.
  The Accounts tile is removed; existing account sign-in remains accessible in
  the header and from the introduction.
- `/partner-desk-demo`: PUBLIC browser-only Partner Desk sandbox, no login.
- `/partner-portal`: public directory grouping both demos and the separate
  protected operator and verified affiliate entry points. It never signs in
  visitors automatically or grants access to private records.
- `/affiliate-hub?demo=1`: PUBLIC browser-only Affiliate Hub sandbox, no key.
  Select a sample company to simulate different partner views.
- `/partner-desk`: authenticated **non-demo Dispatch administrator** only.
- `/affiliate-hub` (without the demo query): private affiliate key login,
  issued by a verified administrator, as before.

The database must be configured for these API endpoints. The pages intentionally
show an access-denied state when the current user isn't authorized.

## Public sandbox walkthrough

1. Open **Partner Portal** from the Hub and choose **Partner Desk demo** or **Affiliate Hub demo**.
2. The operator sandbox can add fictitious sample partners, accept or decline
   sample offers and view sample audit events.
3. The affiliate sandbox automatically selects a fictitious partner. Submit
   sample offers, acknowledge accepted terms, or withdraw them.
4. Switch between the sample operator and affiliate pages using the demo links.
   Both share local browser demo state, not any backend partner records.
5. Use **Reset sample data** to restore the initial example. Browser storage
   can be cleared by the browser; no passenger or partner data should be entered.

## Private operator walkthrough (test records only)

1. Sign in to the existing Dispatch administrator account. The shared public
   DEMO Dispatch login cannot approve partners or review partner records.
2. Open `/partner-desk` and approve an already-verified transportation company.
   **Operational verification takes place outside this preview**; clicking
   Approve is an administrator decision, not automated vetting.
3. Copy the newly issued **one-time** secret access key and pass it securely to
   the specific company's authorized contact. The server stores its SHA-256
   digest, not the plaintext key. Rotate the key immediately if compromised.
4. The affiliate enters that key at `/affiliate-hub`, attests passenger
   authorization, and submits a simulated offer with a unique reservation
   reference, route, time, capacity and proposed payout.
5. The Dispatch administrator reviews and accepts or declines. Acceptance
   means **awaiting affiliate acknowledgment**, never a booked ride.
6. The affiliate can acknowledge or withdraw. Acknowledgment results in
   `agreed_preview` (terms agreed **in a simulation**, no ride created).
   Acknowledgment must happen before the five-minute deadline.
7. Access can be disabled or rotated from Partner Desk at any time.
   Offers and audit events remain available to the operator.

## Boundaries

- Ordinary rides are still created only by authenticated riders.
- Only verified, enabled, administrator-approved partners with a valid key may
  submit B2B offers. Each can read and change **only its own** offers.
- The public sandbox has no server-side affiliate credentials, private partner
  records, or access to Dispatch's rider/driver conversations. Private affiliate
  authorization is unchanged, and the public demo must never call operational
  `/api/partner-desk` or `/api/affiliate-hub` endpoints.
- A company submitting an offer must attest that it has authority to do so on
  behalf of the passenger. Do not include sensitive passenger data in notes.
- NightRider advertises **one** everyday service: four doors, up to four
  passengers plus the driver, no sedan/SUV/luxury choice and no vehicle-class
  upgrade prices. A 0–4 bag count in this pilot is **not** a luggage capacity
  guarantee; real vehicle fit would need checking before dispatch.
- Driver interface and Vela/navigation are intentionally unchanged.

## API preview

Authenticated admin, using existing Dispatch session:

- `GET /api/partner-desk`
- `POST /api/partner-desk/partners`
- `POST /api/partner-desk/partners/{id}/enabled`
- `POST /api/partner-desk/partners/{id}/rotate`
- `POST /api/partner-desk/offers/{id}/accept` (with `revision`)
- `POST /api/partner-desk/offers/{id}/decline` (with `revision`)

Affiliate calls use `X-NR-Partner-Token` (a secret transmitted in an HTTP
request header, never URL parameters):

- `GET /api/affiliate-hub`
- `POST /api/affiliate-hub/offers`
- `POST /api/affiliate-hub/offers/{id}/confirm` (with `revision`)
- `POST /api/affiliate-hub/offers/{id}/withdraw` (with `revision`)

The Partner key stays in **page memory only** and must be reentered after reload.
Offer versions protect against stale accept/decline/confirmation decisions.
Partner reservation references are deduplicated per partner.

## Not ready for operational bookings

**Do not remove the demo labels or wire these offers directly to confirmed rides
without another implementation/review.** Known next work:

- Dedicated transactional PostgreSQL data structures with cross-process-safe
  constraints, locking, schedule validation, idempotency keys and auditable
  immutable revisions (the demo uses the existing JSONB app state and a
  *single-process* lock).
- Full partner employee identities, account recovery/MFA, login rate limiting,
  session expiration and secure notification preferences.
- Explicit compatible-trip checks, real passenger authorization records,
  transport/regulatory requirements and payment agreements.
- Driver scheduling, reconciliation, external/email/SMS notifications, messages,
  cancellation handling and real ride lifecycle integration.
- End-to-end manual testing against **isolated** accounts and devices.

## Tests

The `backend-check` PR workflow compiles the Python modules, runs
`unittest discover -s tests -p 'test_*.py'`, and checks both Partner Desk
JavaScript entrypoints with `node --check`. The frontend, agent coordination
and commit-value gate workflows also run on pull requests.

Merging this web PR can trigger a Render redeployment. Review it and its checks
before merging; rollback by reverting the PR. It does not require Android changes.
