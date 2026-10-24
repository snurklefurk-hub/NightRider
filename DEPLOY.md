# NightRider: put it online (GitHub + Render)

No coding is needed. You will copy the files to GitHub, then connect GitHub to Render.

## Part 1: Put the files on GitHub

1. Go to https://github.com and sign in (or create a free account).
2. Click the **+** at the top right, then **New repository**.
3. Name it `nightrider`. Keep it **Public** or **Private** (either works with Render). Do **not** tick any "add README" boxes. Click **Create repository**.
4. On the next screen, click **uploading an existing file**.
5. Unzip `nightrider.zip` on your computer. Open the folder it creates.
6. Drag **everything inside** that folder into the GitHub upload box. You should see `server.py`, `render.yaml`, `public`, `tests`, and `README.md`.
7. Click **Commit changes**. If GitHub asks about replacing existing files, say yes — the new files must replace the old ones.

> Updating an existing site? Upload the whole folder again the same way. The new `public/index.html` must overwrite the old one, or the site keeps showing the old map.

## Part 2: Start the site on Render

1. Go to https://render.com and sign up, choosing **Sign in with GitHub**.
2. Click **New +** then **Blueprint**.
3. Find your `nightrider` repository and click **Connect**. Render reads `render.yaml` automatically.
4. Click **Apply** (or **Deploy Blueprint**). Wait 2 to 5 minutes until the status says **Live**.
5. Click the link at the top of the page (it looks like `https://nightrider-xxxx.onrender.com`). That is your live site.

Your pages:
- `/` is the rider page (map, address search, ride tiers, live status).
- `/driver.html` is the driver page.
- `/dispatch.html` is the dispatch page.

## If Render shows "Failed to launch" or a Python error

Upload the newest `render.yaml` (from the newest nightrider.zip) to GitHub, replacing the old one. Older versions pinned Python 3.11.2, which Render no longer has. Render redeploys automatically after the upload.

## Good to know

- **Free plan sleeps.** After about 15 minutes with no visitors, the site goes to sleep. The first visit afterward can take ~30 seconds to load.
- **Ride data resets.** Rides are saved to a file on the server. Render's free plan can erase that file on restarts and redeploys. This is fine for testing. Real ride storage needs a database, which we can add later.
- **Updating the site.** Change files on GitHub (or upload new ones), and Render redeploys automatically.
- **Map key — works out of the box.** The map uses CARTO's clean "Voyager" tiles. A working basemap key is already built into the code, so you do **not** need to do anything: deploy and the map works. It is a public client-side basemap key (it is visible in any tile request the browser makes), not an account secret.
- **Optional: rotate the key.** If you ever get a new key and want to use it without editing code, open your Render service → **Environment** → **Add Environment Variable** → name `CARTO_API_KEY`, value = your new key → save. Render redeploys automatically and the server hands the new key to the page. If an old copy of your site ever asks for a Google key, that page is out of date — re-upload the current files from `nightrider.zip` and redeploy.
- **Not for real riders yet.** There is no login or payment. Anyone with the link can see the dispatch and driver pages.

## Running it on your own computer (optional)

You need Python 3 installed. In the folder, run `python3 server.py`, then open http://localhost:8000.

