import React, { useState } from 'react'
import { ScrollView, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router } from 'expo-router'
import * as ImagePicker from 'expo-image-picker'

import { useAuth } from '../../src/auth/AuthContext'
import { GlassCard } from '../../src/components/GlassCard'
import { PrimaryButton } from '../../src/components/PrimaryButton'
import { LoadingView, OfflineBanner } from '../../src/components/StateViews'
import type { DocTypeHint } from '../../src/api/documents'
import { useAddDocument } from '../../src/features/documents/useAddDocument'
import { useNetworkStatus } from '../../src/hooks/useNetworkStatus'
import { vi } from '../../src/i18n/vi'
import { colors, spacing, typography } from '../../src/theme/tokens'

const DOC_TYPES: Array<{ key: DocTypeHint; label: string }> = [
  { key: 'prescription', label: vi.documents.typePrescription },
  { key: 'lab_report', label: vi.documents.typeLab },
  { key: 'general', label: vi.documents.typeGeneral },
]

function assetFrom(result: ImagePicker.ImagePickerResult) {
  if (result.canceled || result.assets.length === 0) return null
  const a = result.assets[0]!
  return { uri: a.uri, mimeType: a.mimeType ?? 'image/jpeg' }
}

export default function AddDocumentScreen() {
  const { client } = useAuth()
  const { isOffline } = useNetworkStatus()
  const { phase, errorMsg, submit } = useAddDocument(client)
  const [docType, setDocType] = useState<DocTypeHint>('prescription')

  async function handleAsset(result: ImagePicker.ImagePickerResult) {
    const asset = assetFrom(result)
    if (!asset) return
    const documentId = await submit(asset, docType)
    if (documentId) router.push(`/review/${documentId}`)
  }

  async function takePhoto() {
    const perm = await ImagePicker.requestCameraPermissionsAsync()
    if (!perm.granted) return
    await handleAsset(await ImagePicker.launchCameraAsync({ quality: 0.7 }))
  }

  async function chooseImage() {
    await handleAsset(await ImagePicker.launchImageLibraryAsync({ quality: 0.7 }))
  }

  if (phase === 'uploading') return <LoadingView label={vi.documents.uploading} />

  return (
    <SafeAreaView style={styles.safe}>
      <OfflineBanner visible={isOffline} />
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>{vi.documents.addTitle}</Text>
        <Text style={styles.subtitle}>{vi.documents.addSubtitle}</Text>

        <View style={styles.types}>
          {DOC_TYPES.map((t) => {
            const active = t.key === docType
            return (
              <PrimaryButton
                key={t.key}
                label={t.label}
                variant={active ? 'primary' : 'ghost'}
                onPress={() => setDocType(t.key)}
                style={styles.typeBtn}
                testID={`doctype-${t.key}`}
              />
            )
          })}
        </View>

        <GlassCard style={styles.card}>
          <PrimaryButton
            label={vi.documents.takePhoto}
            onPress={() => void takePhoto()}
            style={styles.action}
            testID="add-take-photo"
          />
          <PrimaryButton
            label={vi.documents.chooseImage}
            variant="ghost"
            onPress={() => void chooseImage()}
            style={styles.action}
            testID="add-choose-image"
          />
        </GlassCard>

        {phase === 'error' && errorMsg && (
          <Text style={styles.error} testID="add-error">
            {errorMsg}
          </Text>
        )}

        <PrimaryButton
          label={vi.common.back}
          variant="ghost"
          onPress={() => router.back()}
          style={styles.back}
          testID="add-back"
        />
      </ScrollView>
    </SafeAreaView>
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
    marginBottom: spacing.xl,
  },
  types: { flexDirection: 'row', marginBottom: spacing.xl },
  typeBtn: { flex: 1, marginHorizontal: spacing.xs },
  card: { marginBottom: spacing.lg },
  action: { marginBottom: spacing.md },
  error: { ...typography.body, color: colors.danger, marginBottom: spacing.lg },
  back: { marginTop: spacing.md },
})
