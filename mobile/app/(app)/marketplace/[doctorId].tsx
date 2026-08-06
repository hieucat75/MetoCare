import React from 'react'
import { ScrollView, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router, useLocalSearchParams } from 'expo-router'

import { useAuth } from '../../../src/auth/AuthContext'
import { GlassCard } from '../../../src/components/GlassCard'
import { PrimaryButton } from '../../../src/components/PrimaryButton'
import { ErrorView, LoadingView } from '../../../src/components/StateViews'
import { useDoctorDetail } from '../../../src/features/marketplace/useDoctorDetail'
import { formatVnd } from '../../../src/lib/format'
import { firstParam } from '../../../src/lib/params'
import { vi } from '../../../src/i18n/vi'
import { colors, spacing, typography } from '../../../src/theme/tokens'

export default function DoctorDetailScreen() {
  const { client } = useAuth()
  const params = useLocalSearchParams<{ doctorId: string | string[] }>()
  const doctorId = firstParam(params.doctorId)
  const { phase, errorMsg, doctor, reload } = useDoctorDetail(client, doctorId)

  if (phase === 'loading') return <LoadingView />
  if (phase === 'error' || !doctor) {
    return <ErrorView title={vi.errors.generic} message={errorMsg} onRetry={() => void reload()} />
  }

  const ratingText =
    doctor.rating_count > 0
      ? `★ ${doctor.rating_avg.toFixed(1)} · ${vi.marketplace.ratingCount(doctor.rating_count)}`
      : vi.marketplace.noRating

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.name} testID="doctor-detail-name">
          {doctor.full_name}
        </Text>
        {doctor.specialty && <Text style={styles.subtitle}>{doctor.specialty}</Text>}

        <GlassCard style={styles.card}>
          <View style={styles.row}>
            <Text style={styles.fee}>{formatVnd(doctor.consultation_fee)}</Text>
            <Text style={styles.perSession}>{vi.marketplace.perSession}</Text>
          </View>
          <Text style={styles.rating}>{ratingText}</Text>
          {doctor.hospital_name && (
            <Text style={styles.meta}>
              {vi.marketplace.hospital}: {doctor.hospital_name}
            </Text>
          )}
          {doctor.years_experience != null && (
            <Text style={styles.meta}>{vi.marketplace.experience(doctor.years_experience)}</Text>
          )}
          {doctor.languages && (
            <Text style={styles.meta}>
              {vi.marketplace.languages}: {doctor.languages}
            </Text>
          )}
          {doctor.consultation_methods && (
            <Text style={styles.meta}>
              {vi.marketplace.methods}: {doctor.consultation_methods}
            </Text>
          )}
        </GlassCard>

        <GlassCard style={styles.card}>
          <Text style={styles.section}>{vi.marketplace.bio}</Text>
          <Text style={styles.body}>{doctor.bio?.trim() || vi.marketplace.noBio}</Text>
        </GlassCard>

        <Text style={styles.disclaimer} testID="doctor-disclaimer">
          {doctor.disclaimer?.trim() || vi.marketplace.disclaimerFallback}
        </Text>

        <PrimaryButton
          label={vi.marketplace.bookCta}
          onPress={() => router.push(`/marketplace/${doctor.id}/book`)}
          style={styles.cta}
          testID="doctor-book-cta"
        />
        <PrimaryButton
          label={vi.common.back}
          variant="ghost"
          onPress={() => router.back()}
          style={styles.back}
          testID="doctor-back"
        />
      </ScrollView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl },
  name: { ...typography.title, color: colors.ink },
  subtitle: {
    ...typography.body,
    color: colors.inkMuted,
    marginTop: spacing.xs,
    marginBottom: spacing.xl,
  },
  card: { marginBottom: spacing.lg },
  row: { flexDirection: 'row', alignItems: 'baseline' },
  fee: { ...typography.title, color: colors.mint },
  perSession: { ...typography.caption, color: colors.inkMuted, marginLeft: spacing.sm },
  rating: { ...typography.body, color: colors.inkMuted, marginTop: spacing.sm },
  section: { ...typography.heading, color: colors.ink, marginBottom: spacing.xs },
  meta: { ...typography.body, color: colors.inkMuted, marginTop: spacing.xs },
  body: { ...typography.body, color: colors.inkMuted },
  disclaimer: {
    ...typography.caption,
    color: colors.inkMuted,
    fontStyle: 'italic',
    marginBottom: spacing.xl,
  },
  cta: { marginBottom: spacing.md },
  back: { marginTop: spacing.xs },
})
