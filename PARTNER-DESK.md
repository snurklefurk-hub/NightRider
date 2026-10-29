# Partner offers: software demo

NightRider does not currently provision partner accounts or offer real
transportation services. The public **Partner Hub** (`/partner-portal`) has a
request-account preview that sends or stores nothing, a login path for existing
simulation credentials, and an interactive browser-local offer demo at
`/partner-portal?demo=1`.

Partner proposals are simulations. They never create rides, reserve drivers,
collect payment, or send external notifications. An existing partner may submit
or withdraw its own simulated proposal through `/affiliate-hub`. All
NightRider-side review, acceptance, decline, and audit activity for existing
partner records is on `/dispatch.html#partner-offers` and stays restricted to a
non-demo Dispatch administrator. Separately, the shared DEMO Dispatch role can
review the public browser-local sample offers on that same Dispatch page. It
never calls the real partner-offer API to change those examples.

Legacy `/partner-desk` links redirect to that Dispatch section; the old public
Partner Desk sandbox redirects to Partner Hub. The server keeps the role checks
and offer revision checks for the existing simulated API. No migration or
Android change is required.

## Boundaries

- Riders remain the only source of ordinary simulated ride requests.
- An accepted proposal is not a confirmed ride and does not reach Driver.
- Public visitors must not enter passenger, payment, or sensitive information.
- Do not advertise protected, verified, or real-account access while account
  provisioning is paused.

## Verification

Use Partner Hub's interactive demo to propose a sample offer, then open the
shared Dispatch demo and accept or decline it under Partner offers. Return to
the Partner Hub demo to acknowledge accepted terms. These stages share local
browser storage only, so a different browser or device will not see them.

Run `node --test tests/*.test.cjs` and
`NIGHTRIDER_REQUIRE_DATABASE=false python -m unittest discover -s tests -p
'test_*.py' -v`. Confirm the Partner Hub does not submit the request form and
that a Dispatch administrator can review a fixture offer without creating a
ride.
