# MetoCare — Soft-UI kit (React Native + Reanimated 3)

Premium "modern skeuomorphism" components tuned for metabolic patients
(middle-aged / low-vision / reduced dexterity).

## Install
```bash
npx expo install react-native-reanimated react-native-gesture-handler \
  expo-linear-gradient expo-haptics
```
- Add `react-native-reanimated/plugin` as the **last** item in `babel.config.js`.
- Wrap the app root in `<GestureHandlerRootView style={{flex:1}}>`.

## Files
| File | What |
|---|---|
| `theme.ts` | colors, **spring presets** (mass/damping/stiffness), radii, 44pt target consts |
| `haptics.ts` | `hapticTick` / `hapticSnap` / `hapticEdge` (call via `runOnJS`) |
| `Neomorph.tsx` | cross-platform soft surface (dual light/dark shadow, raised ↔ sunk) |
| `SoftButton.tsx` | puffed button, sinks on press; `primary` (filled teal) / `soft` |
| `SoftBottomNav.tsx` | soft tab bar with puffed active pill |
| `DraggableCard.tsx` | spring drag + rubber-band + dismiss threshold |
| `MenuDrawer.tsx` | edge-drag drawer, 3D background recede, rubber-band, snap |

## Usage
```tsx
const ref = useRef<DrawerRef>(null);

<MenuDrawer ref={ref} drawer={<Menu/>}>
  <Screen>
    <SoftButton label="Đã uống thuốc" variant="primary" onPress={...} />
    <SoftButton label="Bỏ qua" variant="soft" onPress={...} />
    <DraggableCard onDismiss={...}><MetricCard/></DraggableCard>
    <SoftBottomNav tabs={TABS} active={tab} onChange={setTab} />
  </Screen>
</MenuDrawer>
// open from a hamburger: ref.current?.open()
```

## Apple "fluid" motion
All movement is **spring physics**, never easing curves. Tune in `theme.ts`:
- `press` — snappy micro-interaction
- `card` — settle/reorder
- `drawer` — crisp organic bounce (`overshootClamping:false`)
- `snapBack` — smooth, no bounce (`overshootClamping:true`)

Gestures run entirely on the **UI thread** (Reanimated worklets); JS only receives
haptic callbacks through `runOnJS`, so it stays 120 Hz / ProMotion smooth with zero
input latency. No `setState` during a drag.

## Accessibility (built in — keep it)
- **Hit target ≥ 44×44 pt** on every control, plus `hitSlop`.
- **Contrast held at WCAG AA** even on the soft surface: text `#10241F` (≈13:1),
  muted `#3C534D` (≈7:1), white-on-teal primary (≈5:1). The puffed look never
  relies on shadow alone to separate a control from the background — primaries are
  filled and high-contrast.
- `maxFontSizeMultiplier` lets Dynamic Type scale up without breaking layout.
- `accessibilityRole` / `accessibilityState` wired for VoiceOver.
- Honour `Reduce Motion`: gate the spring/scale with
  `AccessibilityInfo.isReduceMotionEnabled()` and shorten travel when true.
