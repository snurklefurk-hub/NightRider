## Three-test value gate (required)

**Before each commit, ask all three questions and answer at least one concretely:**

1. Does it make delivering a professional ride easier or safer?
2. Does it improve the driver's profitability, independence, or ability to retain customers?
3. Does it make a customer's experience more dependable, transparent, or trustworthy?

- **Primary test passed (1 / 2 / 3):**
- **Specific outcome for professional rides, drivers, or customers:**
- **Why this is worth maintaining rather than feature bloat:**
- **Every commit includes an `NR-Value:` justification or an owner-approved `NR-Override: MAKE IT SO` declaration:** yes / no
- **Would anything be better if we did NOT ship this?** explain

## Manual owner override (if used)

- Did the product owner directly say **MAKE IT SO** for this exact change?
- Record the authorized scope and where the owner's instruction can be verified:
- Integration owner has verified the authorization: yes / no
- Safety, privacy, testing and release checks remain in force.

## Mission
What user-facing outcome is this PR delivering? Which role(s) does it affect?

## Workstream and ownership
- Agent / workstream:
- State: draft / ready / blocked
- Files and systems expected to change:
- Companion repo PR / dependency (URL or “none”):
- Overlapping open PRs reviewed (URLs or “none”):

## Implementation
What changed, including API contract/data/permission changes? What did not change?

## Safety and compatibility
- Driver No-Surprises Rule checked:
- Existing LIGHT / DARK styles preserved:
- Rider/driver/Dispatch privacy and roles checked:
- Backward compatibility, migrations and data retention:
- Production secrets or services touched: none / explain

## Testing evidence
- Automated commands or GitHub Actions URL **that actually ran**:
- Verified behavior:
- What is not yet tested:

## Integration handoff
- Safe merge/deploy order:
- Expected backend, Render or signed-APK side effects:
- Rollback plan:
- Human/device acceptance steps:
