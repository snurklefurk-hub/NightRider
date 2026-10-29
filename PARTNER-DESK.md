# Partner offers — software demo

NightRider does not currently provision partner accounts or offer real
transportation services. The public **Partner Hub** (`/partner-portal`) has a
request-account form that intentionally records and sends nothing, plus a
login path for any existing simulation credential.

Partner proposals are simulations. They never create rides, reserve drivers,
collect payment, or send external notifications. An existing partner may submit
or withdraw its own simulated proposal through `/affiliate-hub`. All
NightRider-side review, acceptance, decline, and audit activity is on the
existing `/dispatch.html#partner-offers` workspace and remains restricted to a
non-demo Dispatch administrator.

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

Run `node --test tests/*.test.cjs` and
`NIGHTRIDER_REQUIRE_DATABASE=false python -m unittest discover -s tests -p
'test_*.py' -v`. Confirm the Partner Hub does not submit the request form and
that a Dispatch administrator can review a fixture offer without creating a
ride.
