# NightRider next steps

Reviewed 2026-10-29 against web main 9c857b2 and Android main 2a3e8a7.
This is a proposed implementation sequence, not a claim that the work is shipped.
Open issues track planned work; draft PRs track active work. Recheck both before starting.

## Where the project stands

NightRider is a software demo with no real transportation or payments. The web
Hub now has the approved eight destinations and public descriptions. Partner
Hub is the single partner entry point; NightRider-side decisions belong inside
Dispatch. The public partner demonstration shares browser-local storage only,
so it does not demonstrate cross-device coordination. Real account provisioning
remains paused. Ordinary ride requests still originate with riders.

Android's latest signed release at review is v10028. It embeds Vela's navigation
engine with the approved custom appearance. It does not include the full Vela
camera/location-service pipeline, background navigation, offline routing or
live traffic. Keep guidance silent and preserve the unified LIGHT/DARK choices.

## First milestone: one dependable trip

### A. Keep the driver connected through navigation

Evidence: MainActivity.onPause stops polling, location updates and driver pings;
VelaNavigationActivity reads assignments but does not send replacement pings.
The server uses a 90-second activity window. Vela's GPS listener also stops when
its Activity pauses. These are code findings, not a reproduced road test.

- Give an explicitly started driving session ownership of location and presence
  across the board and navigation screens. Use Android's appropriate visible
  foreground-service lifecycle for continued navigation; preserve permission
  and location-sharing choices. Test mode must remain isolated from ride APIs.
- Handle return from Settings, screen lock, app switching, revoked permissions,
  stale GPS, logout, force-stop and process recreation with honest state labels.
- Keep controls fixed and silent. Restore the selected ride and destination
  when possible; never claim navigation survived if its session was lost.
- Acceptance: an isolated driver remains visible to Dispatch during a five-minute
  navigation session; stopping/logging out stops sharing; the location age is
  truthful. Phone checks cover stationary and moving use, not just an emulator.

### B. Make trip actions safe to repeat

Evidence: /advance uses the server's current NEXT state and the Android/browser
clients send no expected stage or request identity. Repeated requests can advance
more than once. Booking creates a new identifier for each accepted POST.

- Add expected-state/revision checks and request identifiers for booking and trip
  transitions. Repeating an accepted request must return the same outcome.
- Disable pending buttons and reconcile after uncertain responses. Do not queue
  blind stage changes while offline. Show pending, confirmed and failed states.
- Plan a backward-compatible rollout for existing v10028 installations. Deploy
  server support, update both driver clients, then enforce the new contract only
  with an explicit compatibility policy for older versions.
- Acceptance: double taps, dropped responses, retries after restart, two drivers
  accepting one ride, and Dispatch reassignment cannot duplicate a booking or
  skip a stage. Test competing requests against a real isolated PostgreSQL DB.

### C. Protect the trip record and release process

- Enable repository rulesets requiring relevant checks. At review, both branches
  report unprotected and both repository ruleset lists are empty. CI alone does
  not prevent a failed merge. Keep a documented owner recovery path.
- Add an authenticated browser-to-API journey and Android contract checks using
  isolated accounts. Existing SQLite/account fixtures and mocked state writes
  are useful, but do not prove PostgreSQL durability or a complete device flow.
- Test backup and restore in an isolated database. The existing per-account and
  history exports are not a full database recovery mechanism.
- Move critical rides, transitions and messages from the shared JSON state record
  into transactional records in small migrations. Keep one web process until
  cross-process writes are safe. Test failures between mutation and persistence.
- Document a free development hosting/data-retention plan with an export and
  restore drill. Verify actual provider limits before relying on them. No paid
  upgrades or hosting moves are part of this housekeeping request.
- Acceptance: a service restart preserves an acknowledged trip/message; a failed
  write is not displayed as confirmed; restore recovers isolated account and
  trip history; release checks cannot be silently skipped by path filters.

## Second milestone: trustworthy navigation and prices

Use recorded traces and controlled routes to improve Vela integration. Cover a
stationary phone, ordinary turns, missed turns, roundabouts, parallel roads,
weak signal and lost connectivity. Record reroute events, accepted/rejected GPS
and the displayed instruction with timing. Improve turn artwork and turn-aware
camera behavior only after the evidence identifies the need. Preserve the
approved colors and flat map. No audio or additional platform port is required.

Validate supported geography, pickup distance and route plausibility. Distances
and authoritative fares must be checked by the server before real use. Label
estimates and confirmed amounts consistently, and explain any change before a
commitment. A supplied browser distance is not an authoritative fare input.
NightRider has one service and one pricing structure, with no vehicle-class
upsells. Actual passenger/luggage capacity must be checked rather than assumed.

Acceptance: a replay pack produces explainable turn timing and stable stationary
behavior; lost GPS/network never masquerades as a fresh route or live ETA;
out-of-area or implausible requests cannot silently produce a normal quote.

## Third milestone: make repeat local business easier

The initial competitive focus is a dependable local service that riders can
return to and independent drivers can operate without juggling messages.
Evaluate success through completed journeys and repeat use, not the number of
pages or how closely the app resembles a national marketplace.

- Add a clear sooner/later booking model, timezone-aware pickup windows,
  availability/conflict checks, and honest confirmation status.
- Make repeat booking simple while keeping the rider in control of submission.
  Preserve useful pickup instructions and the private rider/Dispatch conversation.
- Consolidate the current trip, next action, connection status and unread
  messages in predictable positions. Put completed trips in history. Keep demo
  galleries secondary to driver tasks, preserving approved copy and branding.
- Show driver-relevant trip economics: paid trip, pickup distance, expected time
  and recorded waiting time. Estimates should state their assumptions.
- Keep partner offer review on Dispatch. Before making partner demos operational,
  design the explicit conversion into an authorized rider booking, capacity and
  scheduling checks, duplicate protection and a shared server-backed record.
  Do not provision real partner accounts or imply a proposal reserves a driver.

Acceptance: family testers can request, confirm, complete and rebook a fictional
trip without coaching; Dispatch can handle the partner proposal on one page;
missed requests and ambiguous confirmations are visible rather than silent.

## Pilot evidence and later work

Suggested first gate: 20 complete isolated simulated journeys across at least
three devices, including competing actions, reloads and dropped connections.
Then run controlled navigation drives with logs and stationary/passenger-led
interaction. Record completion rate, stage errors, recovery time, navigation
failures, missed messages and repeat-booking effort. Targets should be set before
expanding the pilot, and failures should become reproducible fixtures.

Broader operations, payments, an iPhone app and a white-label setup wizard follow
these gates. Build brand configuration and tenant separation when a second
operator is actually being tested. Retain the option for other operators to
configure service classes later; do not add those options to NightRider now.

## Housekeeping in this review

- Web backend verification covers all root Python modules, including account
  archives, history deletion, showroom data and partner logic, on PRs and main.
- Android native-screen verification covers shared source/resources and build
  configuration, not only files named Vela.
- Windows without a POSIX shell reports the shell-only hook test as skipped;
  Linux CI still executes the hook assertions. Other source checks still run.
- Stale test-coverage and historical work-status documentation is corrected.

These maintenance changes do not implement the milestones above or claim field
readiness. Runtime behavior and the signed Android application are unchanged.
