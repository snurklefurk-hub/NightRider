# NightRider visual style

Applies to Rider, Dispatch, browser Driver, Accounts, Map Lab, and the Android driver app (including Settings, map HUD, simulation and Field Test).

## Shared appearance

Keep the existing LIGHT/DARK choice. DARK uses forest green surfaces, emerald actions and cream text. LIGHT uses sky blue glass surfaces, blue primary actions, green secondary actions and dark blue text. Appearance changes include the map and preserve account/session state.

| Role | DARK | LIGHT |
| --- | --- | --- |
| Page / top bar | #071B12 | #E8F8FF |
| Panel | #0E2B1E | #E4F6FD |
| Primary action | #19D47B | #0876B8 |
| Secondary action | #5AE6A5 | #168957 |
| Main text | #F2F0DF | #103D58 |
| Muted text | #9BB7A5 | #3E6075 |
| Danger | #D95C4F | #B83B45 |

Use system sans-serif in DARK; rounded humanist sans-serif in LIGHT (Nunito Sans with local fallbacks on web, Android sans-serif-rounded). Use rounded cards, pill-shaped web actions, clear keyboard focus and readable secondary text. Keep native Android controls usable and recognizable.

## Implementation

Web: nightrider.css owns the main dark shell; map-lab.css uses the same interface colors with a dedicated map workspace layout. aero-theme.css supplies LIGHT and shared appearance corrections to all five entrypoints. Bump its query version on every entrypoint when changing it.

Android: colors.xml, aero_colors.xml and themes.xml own semantic roles. Dynamic map panels resolve nrText, nrMuted, nrAccent and nrTopbar from the active theme using appearanceColor. Programmatic buttons inherit NrButton through android:buttonStyle.

Do not recolor map roads, navigation routes, role markers, sender colors or raw/accepted GPS traces merely to match interface accents. These encode information or preserve navigation contrast.

## Review checklist

Review both appearances at desktop and narrow widths. Include welcome dialog, account form, empty/populated ride cards, private chat, map popups, fullscreen maps, Settings, navigation HUD and test controls. Verify LIGHT text on every nested panel and DARK focus rings. Preserve reduced-motion behavior, map attribution, test isolation, no-audio behavior and existing signing secrets.
