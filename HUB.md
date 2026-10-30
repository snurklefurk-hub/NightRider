# Hub destination contract

The public Hub gives visitors a dependable way to find the software demo and
understand its intended standards. All transportation and payments remain simulated.

On desktop, preserve two rows of four approved tiles in this reading order, followed by one compact full-width ninth destination:

| First row | | | |
| --- | --- | --- | --- |
| Info for Riders | Info for Drivers | Affiliates and Partners | Our Ethos |
| Rider Demo | Driver Demo | Dispatch Demo | Partner Hub |

The ninth tile, **For Insurers, Investors, and Clients**, spans the full grid
width with a shallow horizontal layout. It links to `/for-insurers.html`, whose
three sections describe proposed Driver requirements, Vehicle requirements and
Roadmap. The new page keeps software-demo notices, never asserts existing
licensing/insurance or active transport, and conditions eligibility on inspection,
underwriting and state requirements. The owner-provided Georgia code reference
(`46-1-1` through `46-1-8`) was not the TNC section range; the public page
instead cites `40-1-190` through `40-1-201` and `33-1-24`.
Regulatory review must verify audit obligations prior to launch.

Keep the same source and keyboard order as the grid becomes two columns on
normal phone widths and one column only on very narrow screens (340px or less).
On phones, the Hub tightens its header, intro, text sizes and tile spacing
without hiding or rewriting the nine descriptions, removing demo access, or
changing desktop's four-column layout. The ninth tile stays full-width at every
breakpoint. Verify both LIGHT and DARK appearance, links, focus order,
text enlargement and lack of horizontal overflow. Affiliates and Partners now links to a **public
future-plans information page** at `/for-affiliates.html`. It describes intended
hospitality/referral and third-party booking capabilities, but offers no active
transportation or payment services. Account sign-in remains in the header.

The Affiliates and Partners tile retains its public future-plans information
page. The separate Partner Hub tile is the single entry point for account-request
preview, an existing-login path, and an interactive browser-local sample offer
workspace. It does not accept, transmit, or provision account requests.
NightRider-side offer decisions happen on Dispatch, including the browser-only
sample offer workflow for the shared DEMO Dispatch role.

Retire the standalone map preview and its public links. Preserve Rider and
Dispatch maps, their shared Midnight palette, LIGHT/DARK behavior, ride markers,
and the independent Android navigation workflow. Old preview bookmarks should
return visitors to the Hub. Existing rider information bookmarks remain valid.

## Public contact and prelaunch inquiries

Public email: `carson.nightrider@gmail.com`. Show it on the Hub, informational Rider,
Driver and Affiliate/Partner pages, insurer standards, and Partner Hub.
The three information pages contain prefilled, audience-specific forms for
expressing interest or asking a question. The form opens an email-client draft
with the visitor's reply address and message; they must press Send from their
own email app. Never claim the browser action sent, stored or accepted an
inquiry. Always show the direct email link as a fallback. No public storage
endpoint, ride request, account creation or driver application is involved.
The Partner Hub account-request form remains simulation-only; its real
interest link points to the Affiliates and Partners information form.

## Value gate

1. Professional ride safety: preserve operational map behavior and access gates;
   this navigation change does not claim a new driving-safety capability.
2. Rider trust (primary): distinguish information, fictional demos and private
   partner access, with working destinations and no misleading placeholder link.
3. Industry improvement: preserve direct access to driver information and partner
   plans that support professional local operators without claiming active service.

This replaces the existing directory structure instead of adding an unrelated
feature. The portal consolidates existing access rather than duplicating it.

## Acceptance and release

Verify the exact tile order, four desktop columns, smaller-screen reading order,
LIGHT/DARK and keyboard focus. Verify the Affiliates and Partners page and its
working Partner Hub links, future-only wording, and honest ADA goals. Check all public links, legacy information links,
demo session preservation and Dispatch-only partner-offer access with isolated fixtures.
Run the existing frontend and backend suites and inspect GitHub checks before
merging. A web merge can redeploy Render; verify the deployed commit, health and
public pages before reporting it live. No migrations or Android release are
required. Revert the PR to roll back the directory and route changes.
