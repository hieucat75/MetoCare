import React from 'react'
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router } from 'expo-router'

import { useAuth } from '../../src/auth/AuthContext'
import { GlassCard } from '../../src/components/GlassCard'
import { PrimaryButton } from '../../src/components/PrimaryButton'
import { ErrorView, LoadingView } from '../../src/components/StateViews'
import { useDoctorList } from '../../src/features/marketplace/useDoctorList'
import { formatVnd } from '../../src/lib/format'
import { vi } from '../../src/i18n/vi'
import { colors, radius, spacing, typography } from '../../src/theme/tokens'

export default function MarketplaceScreen() {
  const { client } = useAuth()
  const {
    phase,
    errorMsg,
    visible,
    specialties,
    search,
    specialty,
    setSearch,
    setSpecialty,
    reload,
  } = useDoctorList(client)

  if (phase === 'loading') return <LoadingView />
  if (phase === 'error') {
    return <ErrorView title={vi.errors.generic} message={errorMsg} onRetry={() => void reload()} />
  }

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>{vi.marketplace.title}</Text>
        <Text style={styles.subtitle}>{vi.marketplace.subtitle}</Text>

        <TextInput
          style={styles.search}
          placeholder={vi.marketplace.searchPlaceholder}
          placeholderTextColor={colors.slate}
          value={search}
          onChangeText={setSearch}
          autoCapitalize="none"
          testID="marketplace-search"
        />

        {specialties.length > 0 && (
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.chips}
          >
            <FilterChip
              label={vi.marketplace.allSpecialties}
              active={specialty === null}
              onPress={() => setSpecialty(null)}
              testID="specialty-all"
            />
            {specialties.map((s) => (
              <FilterChip
                key={s}
                label={s}
                active={specialty === s}
                onPress={() => setSpecialty(s)}
                testID={`specialty-${s}`}
              />
            ))}
          </ScrollView>
        )}

        {visible.length === 0 && (
          <GlassCard style={styles.card} testID="marketplace-empty">
            <Text style={styles.body}>{vi.marketplace.empty}</Text>
          </GlassCard>
        )}

        {visible.map((d) => (
          <Pressable
            key={d.id}
            onPress={() => router.push(`/marketplace/${d.id}`)}
            accessibilityRole="button"
            accessibilityLabel={d.full_name}
            testID={`doctor-${d.id}`}
          >
            <GlassCard style={styles.card}>
              <Text style={styles.name}>{d.full_name}</Text>
              {d.specialty && <Text style={styles.meta}>{d.specialty}</Text>}
              {d.hospital_name && <Text style={styles.meta}>{d.hospital_name}</Text>}
              <View style={styles.row}>
                <Text style={styles.fee}>{formatVnd(d.consultation_fee)}</Text>
                <Text style={styles.rating}>
                  {d.rating_count > 0
                    ? `★ ${d.rating_avg.toFixed(1)} · ${vi.marketplace.ratingCount(d.rating_count)}`
                    : vi.marketplace.noRating}
                </Text>
              </View>
            </GlassCard>
          </Pressable>
        ))}

        <PrimaryButton
          label={vi.common.back}
          variant="ghost"
          onPress={() => router.back()}
          style={styles.back}
          testID="marketplace-back"
        />
      </ScrollView>
    </SafeAreaView>
  )
}

interface FilterChipProps {
  label: string
  active: boolean
  onPress: () => void
  testID?: string
}

function FilterChip({ label, active, onPress, testID }: FilterChipProps) {
  return (
    <Pressable
      onPress={onPress}
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      style={[styles.chip, active ? styles.chipActive : null]}
    >
      <Text style={[styles.chipText, active ? styles.chipTextActive : null]}>{label}</Text>
    </Pressable>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl },
  title: { ...typography.title, color: colors.ink },
  subtitle: {
    ...typography.body,
    color: colors.inkMuted,
    marginTop: spacing.xs,
    marginBottom: spacing.lg,
  },
  search: {
    ...typography.body,
    color: colors.ink,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    marginBottom: spacing.lg,
  },
  chips: { paddingBottom: spacing.lg },
  chip: {
    borderWidth: 1,
    borderColor: colors.mint,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    marginRight: spacing.sm,
  },
  chipActive: { backgroundColor: colors.mint },
  chipText: { ...typography.label, color: colors.mint },
  chipTextActive: { color: colors.white },
  card: { marginBottom: spacing.lg },
  body: { ...typography.body, color: colors.inkMuted },
  name: { ...typography.heading, color: colors.ink, marginBottom: spacing.xs },
  meta: { ...typography.body, color: colors.inkMuted },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.md,
  },
  fee: { ...typography.label, color: colors.mint },
  rating: { ...typography.caption, color: colors.inkMuted },
  back: { marginTop: spacing.md },
})
