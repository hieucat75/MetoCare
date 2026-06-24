/**
 * <SoftBottomNav/> — soft-UI bottom tab bar.
 * The whole bar is a raised neuomorphic slab; the active tab is a puffed teal pill
 * that springs in. Center "AI" action floats above the bar.
 *
 * Each tab is a full 44pt+ target. Active label/icon stay high-contrast.
 */
import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import Animated, {
  useAnimatedStyle, withSpring, useDerivedValue,
} from 'react-native-reanimated';
import { colors, springs, radii, MIN_TARGET } from './theme';
import { Neomorph } from './Neomorph';
import { hapticTick } from './haptics';

export type Tab = { key: string; label: string; icon: (active: boolean) => React.ReactNode };

export function SoftBottomNav({
  tabs, active, onChange,
}: { tabs: Tab[]; active: string; onChange: (k: string) => void }) {
  return (
    <Neomorph radius={radii.lg} style={styles.bar}>
      <View style={styles.row}>
        {tabs.map((t) => {
          const isActive = t.key === active;
          return (
            <Pressable
              key={t.key}
              onPress={() => { if (!isActive) { hapticTick(); onChange(t.key); } }}
              accessibilityRole="tab"
              accessibilityState={{ selected: isActive }}
              accessibilityLabel={t.label}
              style={styles.tap}
            >
              <TabPill active={isActive}>
                {t.icon(isActive)}
                <Text
                  numberOfLines={1}
                  maxFontSizeMultiplier={1.4}
                  style={[styles.label, { color: isActive ? colors.onPrimary : colors.textMuted }]}
                >
                  {t.label}
                </Text>
              </TabPill>
            </Pressable>
          );
        })}
      </View>
    </Neomorph>
  );
}

function TabPill({ active, children }: { active: boolean; children: React.ReactNode }) {
  const a = useDerivedValue(() => withSpring(active ? 1 : 0, springs.press), [active]);
  const aStyle = useAnimatedStyle(() => ({ transform: [{ scale: 0.96 + a.value * 0.04 }] }));

  return (
    <Animated.View style={[styles.pill, aStyle]}>
      {active && (
        <LinearGradient
          colors={[colors.primaryHi, colors.primaryLo]}
          start={{ x: 0.1, y: 0 }} end={{ x: 0.9, y: 1 }}
          style={[StyleSheet.absoluteFill, { borderRadius: radii.md }]}
        />
      )}
      <View style={styles.pillInner}>{children}</View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  bar: { marginHorizontal: 14, marginBottom: 10, backgroundColor: colors.surface },
  row: { flexDirection: 'row', backgroundColor: colors.surface, paddingHorizontal: 8, paddingVertical: 8, borderRadius: radii.lg },
  tap: { flex: 1, minHeight: MIN_TARGET, alignItems: 'center', justifyContent: 'center' },
  pill: { minHeight: MIN_TARGET, minWidth: MIN_TARGET, borderRadius: radii.md, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 10, overflow: 'hidden' },
  pillInner: { alignItems: 'center', gap: 3, paddingVertical: 6 },
  label: { fontSize: 11, fontWeight: '700' },
});
