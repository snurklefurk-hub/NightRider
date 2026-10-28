# NightRider: instructions for every coding agent

**Read this file before making ANY code or deployment change.** NightRider is developed by multiple independent ChatGPT/frontier-model instances. They do not share live chat state or an automatic coordination channel. **GitHub is the source of truth.**

## First five minutes — required

1. Read this file, `README.md`, and the applicable feature policy (for example, `CHAT-POLICY.md`). Check the companion [Android repository](https://github.com/snurklefurk-hub/nightrider-driver-android), too.
2. Fetch current `main`, **all open pull requests in both repos**, and recent commits. Never assume the branch from a prior conversation is current. Live work queues: [Web/API PRs](https://github.com/snurklefurk-hub/NightRider/pulls) · [Android PRs](https://github.com/snurklefurk-hub/nightrider-driver-android/pulls).
3. Work from current `main` on a uniquely named task branch. **Open a DRAFT PR early**, with a task summary and expected files, so other agents can discover your work. Update the draft as scope changes. A branch alone is not an announcement.
4. If another PR touches the same files or public API, read its diff and coordinate using PR comments / dependencies. Do not overwrite, cherry-pick, duplicate, or silently supersede another agent's work.
5. When implementation is ready, update the PR with tests, deployment effects and risks. Mark ready only after automated checks and review. Don't merge unless explicitly assigned integration responsibility.

## Integration and release rules

- **No direct commits or force pushes to `main`.** No unattended auto-merges. One designated integration owner reviews and merges one PR at a time, rebasing or refreshing other PRs against the new `main` when necessary.
- **Web `main` can deploy to Render; Android `main` can publish a signed APK.** Treat merging as a production action, not routine housekeeping. Check service health, workflows and rollback options.
- Cross-repository API changes require a linked PR in the other repository when necessary. Explicitly document rollout order and backward compatibility.
- GitHub Actions provides automated tests and an **agent coordination report** on PRs. Its overlap report finds identical filenames and lists active work across both repos; it is **not** semantic conflict detection, live messaging, or an approval to merge.
- If an automated tool says a merge is blocked, stop and report what it said. Never work around a safety block using an alternate write path.
- If two agents both want `server.py`, `public/nr-chat.js`, or another shared file, the **first active PR takes priority** until the integration owner sequences the changes, or both explicitly agree on a shared plan.

## NightRider invariants

- Driver attention and muscle memory are top priority: no unsolicited navigation, scrolling, jumping buttons, focus theft, keyboard popups, or distracting chat animations.
- Only riders submit ride requests. Riders use a browser, no app download required.
- Ride-specific rider messages reach Dispatch and the assigned driver; private account-level rider/Dispatch messages persist between rides and remain inaccessible to drivers. Read `CHAT-POLICY.md` before changing message access.
- Keep styling consistent across rider website, Dispatch, browser Driver, Android and map pages; preserve existing LIGHT/DARK choices.
- Navigation is a separate workstream: do not change it incidentally while working on chat.
- No credentials in git, PR descriptions, or logs. Never test against the production database unless explicitly directed. Use isolated fixtures.
- Provide plain-language reports; the product owner should not need to debug code, mediate parallel agents or manually relay work between conversations.

## PR handoff format

Write the PR description using the template at `.github/PULL_REQUEST_TEMPLATE.md`. At minimum record:

- Goal and roles affected
- Files / systems changed and any overlapping or dependent PRs
- Automated tests **actually run** and results, plus untested edge cases
- Database migrations, production implications, and merge/deploy order
- Acceptance criteria and verification steps for the integrator
- Status: **draft / ready / blocked** (do not write “deployed” without verifying deployment)

## Current work status

**Do not keep a manually edited “active agents” roster in README:** it goes stale and creates conflicts. The two live PR pages above are the shared status board. Draft PRs are how agents announce work; the bot refreshes summaries and overlap notices. A pull request in progress is not proof of a deployed feature.

As of 2026-10-28, [web PR #21](https://github.com/snurklefurk-hub/NightRider/pull/21) implements Dispatch text shortcuts and persistent rider-account chat, and **was open at the time this file was authored**. Recheck GitHub before acting.
