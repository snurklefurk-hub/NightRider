# Hub destination contract

The public Hub gives visitors a dependable way to find the software demo and
understand its intended standards. All transportation and payments remain simulated.

On desktop, show exactly two rows of four tiles in this reading order:

| First row | | | |
| --- | --- | --- | --- |
| Info for Riders | Info for Drivers | Affiliates and Partners | Our Ethos |
| Rider Demo | Driver Demo | Dispatch Demo | Partner Portal |

Keep the same source and keyboard order as the grid becomes two columns or one
column on smaller screens. Affiliates and Partners is an empty, non-interactive
placeholder; never give it a fake link. Account sign-in remains in the header.

Partner Portal groups the existing public Partner Desk and Affiliate Hub demos
and clearly labels the separate protected administrator and verified affiliate
entry points. It does not authenticate visitors or grant partner privileges.

Retire the standalone map preview and its public links. Preserve Rider and
Dispatch maps, their shared Midnight palette, LIGHT/DARK behavior, ride markers,
and the independent Android navigation workflow. Old preview bookmarks should
return visitors to the Hub. Existing rider information bookmarks remain valid.

## Value gate

1. Professional ride safety: preserve operational map behavior and access gates;
   this navigation change does not claim a new driving-safety capability.
2. Driver business: the driver information page stays directly discoverable;
   this change does not claim increased earnings.
3. Customer trust (primary): distinguish information, fictional demos and private
   partner access, with working destinations and no misleading placeholder link.

This replaces the existing directory structure instead of adding an unrelated
feature. The portal consolidates existing access rather than duplicating it.

## Acceptance and release

Verify the exact tile order, four desktop columns, smaller-screen reading order,
LIGHT/DARK and keyboard focus. Check all public links, legacy information links,
demo session preservation and protected partner access with isolated fixtures.
Run the existing frontend and backend suites and inspect GitHub checks before
merging. A web merge can redeploy Render; verify the deployed commit, health and
public pages before reporting it live. No migrations or Android release are
required. Revert the PR to roll back the directory and route changes.
