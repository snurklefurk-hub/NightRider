# NightRider deployment

The software demo is served by the existing Render service from this GitHub repository. No transportation services are offered. Review
**ACCOUNT-SETUP.md** before deploying the account-enabled revision.

## Render Blueprint resources

The Blueprint configures the Python service and links it to a free Render
Postgres database named `nightrider-db`. This is for development only. Render's
free databases have 1 GB of storage, expire after 30 days, and have no backups.
There is a 14-day grace period to upgrade after expiration; after that Render
deletes the database and its data. Export anything you want to keep before
that deadline. Keep the web service and database in the same region.

The Blueprint sets `DATABASE_URL` from the database's private connection and
requires the database at startup. It enables secure cookies for the HTTPS
service. `NIGHTRIDER_SETUP_TOKEN` is a secret and is not stored in Git. When
updating an existing Blueprint, add that variable manually in the Render
service's **Environment** page; Render does not prompt for `sync: false` values
again during later Blueprint syncs.

Use a password manager to generate a long, random setup token. Do not put it in
GitHub, a URL, or a chat message. The token is used once to create the first
dispatch account; remove it from Render after setup.

## First account setup

1. Confirm the database and required environment variables are available to the
   service before its account-enabled revision starts. The server refuses to
   start if the required database is missing.
2. After the service is live, open
   `https://nightrider.onrender.com/account.html?setup=1`.
3. Create the initial dispatch account using `NIGHTRIDER_SETUP_TOKEN`.
4. Remove the setup token from Render and save the environment change.
5. On the Dispatch page, create driver accounts and give each driver their
   username and initial password privately.
6. Visitors choose Rider, Driver, or Dispatch on the sign-in page and use the public `DEMO` / `PASSWORD` credentials. Rider registration is paused and trips are always simulated. The startup migration adds `nr_users.is_demo` and seeds three demo accounts; it does not replace private accounts or create a separate service/database.

See **ACCOUNT-SETUP.md** for role behavior, account recovery, and the one-time
ride-data migration details.

## Other settings

- `ADDRESS_COUNTRY` selects the country used for local address lookup (default
  `us`).
- `CARTO_API_KEY` optionally overrides the public browser-visible map key. It
  is not a secret.
- `NIGHTRIDER_ENABLE_DEMO_DRIVER` is off by default. Enable it only for internal
  testing.

## Running locally

For the development-only no-database mode, install the Python dependency and
run:

```text
pip install -r requirements.txt
NIGHTRIDER_REQUIRE_DATABASE=false python3 server.py
```

That mode does not provide accounts or protected API routes. Keep it on a local
machine only. Public deployments must set `DATABASE_URL` and keep
`NIGHTRIDER_REQUIRE_DATABASE=true`.

