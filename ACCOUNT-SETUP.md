# NightRider accounts and first deployment

NightRider provides its own sign-in. It does not use Google, Apple, Facebook,
or another identity provider.

## Before deploying

The account system requires PostgreSQL. The Blueprint adds a free Render
Postgres database named `nightrider-db` in the same region as the web service.
This is for development only: Render's free databases have 1 GB of storage,
expire after 30 days, have no backups, and are not suitable for production.
After expiration, there is a 14-day grace period to upgrade before Render
deletes the database and its data. Export anything you want to keep before
that deadline.

For an existing Render Blueprint service, add this secret in the service's
**Environment** page before deploying the account-enabled revision:

- `NIGHTRIDER_SETUP_TOKEN`: a long, random, one-time code used to create the
  first dispatch account. Generate it in a password manager. Do not commit or
  send the code in chat. Remove the variable after the first dispatch account
  has been created.

The Blueprint defines `DATABASE_URL` from the database's private connection,
sets `NIGHTRIDER_REQUIRE_DATABASE=true`, and sets `NIGHTRIDER_COOKIE_SECURE=true`.
If this is an existing service, confirm those values appear on its Environment
page after syncing the Blueprint. Never deploy the account-enabled server
without a working database URL: it deliberately refuses to start.

## Create the first dispatch account

After the database and account-enabled service are running:

1. Open `https://nightrider.onrender.com/account.html?setup=1`.
2. Enter the one-time setup code, a dispatch name, username, and password of at
   least 8 characters.
3. Sign in, then remove `NIGHTRIDER_SETUP_TOKEN` from the Render service and
   save the environment change.
4. From the Dispatch page, create a username, display name, and initial
   password for each driver. Give each driver their details privately.

The initial dispatcher setup is disabled once a dispatch account exists.
Riders create their own accounts from the sign-in page. Driver accounts are
created by dispatch. Dispatch can disable driver accounts and reset passwords.
If a rider forgets a password, dispatch can reset it after confirming the
rider's identity separately.

## Sign-in behavior

- Rider, driver, and dispatch accounts use NightRider usernames and passwords.
- Passwords are stored as salted scrypt hashes. The server never stores a
  readable password.
- Website sessions use secure, HTTP-only cookies. The Android driver app uses
  the same account service and stores its session token encrypted with Android
  Keystore.
- A rider's account is the rider identity. NightRider no longer creates an
  identity from browser or device signals. Older ride history is preserved when
  found in `rides.json`, but its old device-derived rider IDs and signal records
  are removed because they cannot be reliably matched to an account.
- No email, SMS, or third-party account is required. There is no self-service
  email recovery; dispatch can reset a rider's password after identity checks.
- Passwords must be at least 8 characters. Sign-in attempts are throttled.

## Data storage and migration

Rides, rider profiles, ratings, messages, and driver status are stored in a
single JSON state record in Postgres. Account and session records are stored in
separate Postgres tables. The service currently runs one web instance and uses
an in-process lock while updating the shared state record; keep the Render web
service at one instance until storage is moved to normalized tables or a
database transaction strategy is added for multiple app instances.

On first database startup, NightRider imports the local `rides.json` file if it
is present on the service. Render's local filesystem is temporary, so existing
ride data may not be present when the new revision starts. Download the current
dispatch ride log before deployment if you need an offline reference. The
account rollout does not infer or recreate accounts for historic riders.

For local development without Postgres, set `NIGHTRIDER_REQUIRE_DATABASE=false`
explicitly. This is a development-only mode and does not provide login or
protected API access. Do not use it on Render or another public service.

