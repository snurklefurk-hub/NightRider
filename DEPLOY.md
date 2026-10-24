# NightRider: put it online (GitHub + Render)

No coding is needed. You will copy the files to GitHub, then connect GitHub to Render.

## Part 1: Put the files on GitHub

1. Go to https://github.com and sign in (or create a free account).
2. Click the **+** at the top right, then **New repository**.
3. Name it `nightrider`. Keep it **Public** or **Private** (either works with Render). Do **not** tick any "add README" boxes. Click **Create repository**.
4. On the next screen, click **uploading an existing file**.
5. Unzip `nightrider.zip` on your computer. Open the folder it creates.
6. Drag **everything inside** that folder into the GitHub upload box. You should see `server.py`, `render.yaml`, `public`, `tests`, and `README.md`.
7. Click **Commit changes**.

## Part 2: Start the site on Render

1. Go to https://render.com and sign up, choosing **Sign in with GitHub**.
2. Click **New +** then **Blueprint**.
3. Find your `nightrider` repository and click **Connect**. Render reads `render.yaml` automatically.
4. Click **Apply** (or **Deploy Blueprint**). Wait 2 to 5 minutes until the status says **Live**.
5. Click the link at the top of the page (it looks like `https://nightrider-xxxx.onrender.com`). That is your live site.

Your pages:
- `/` is the customer ride request page.
- `/driver.html` is the driver page.
- `/dispatch.html` is the dispatch page.

## Good to know

- **Free plan sleeps.** After about 15 minutes with no visitors, the site goes to sleep. The first visit afterward can take ~30 seconds to load.
- **Ride data resets.** Rides are saved to a file on the server. Render's free plan can erase that file on restarts and redeploys. This is fine for testing. Real ride storage needs a database, which we can add later.
- **Updating the site.** Change files on GitHub (or upload new ones), and Render redeploys automatically.
- **Not for real riders yet.** There is no login, payment, or maps. Anyone with the link can see the dispatch page.

## Running it on your own computer (optional)

You need Python 3 installed. In the folder, run `python3 server.py`, then open http://localhost:8000.
