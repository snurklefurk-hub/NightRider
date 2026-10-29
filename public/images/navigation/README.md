# Simulated Driver navigation screenshots

These static previews illustrate the current custom LIGHT and DARK Android
navigation styles. The scene, route, position, speed and guidance are fictional.
They are not device captures, GPS fixes or directions for actual travel.

Reference: `snurklefurk-hub/nightrider-driver-android` at `a063c9f`, specifically
`VelaNavigationActivity.kt`, `NavigationRoadStyle.kt`, `NavigationMarker.kt`
and the existing LIGHT/DARK UI colors. Both previews share the same scene.
They preserve the flat map, current top/bottom panels, blue route and driver
marker; no lane or audio guidance is implied.

`scripts/render-driver-navigation.cjs` renders the SVG scenes to the committed
PNG files using Sharp (`node scripts/render-driver-navigation.cjs`). Sharp is
only an authoring tool; the deployed website serves static PNGs and needs no
additional runtime dependency.
