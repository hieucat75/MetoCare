import * as LocalAuthentication from 'expo-local-authentication'

/**
 * Optional biometric unlock over expo-local-authentication (Face ID / Touch ID
 * / fingerprint). ALWAYS degrades safely: if hardware is missing, no biometric
 * is enrolled, or the user cancels, the caller falls back to password.
 *
 * Native hardware paths are logic-tested via a mock; real device biometrics
 * are native-runtime pending.
 */

export interface BiometricCapability {
  hasHardware: boolean
  isEnrolled: boolean
  available: boolean
}

export async function getBiometricCapability(): Promise<BiometricCapability> {
  try {
    const [hasHardware, isEnrolled] = await Promise.all([
      LocalAuthentication.hasHardwareAsync(),
      LocalAuthentication.isEnrolledAsync(),
    ])
    return { hasHardware, isEnrolled, available: hasHardware && isEnrolled }
  } catch {
    return { hasHardware: false, isEnrolled: false, available: false }
  }
}

export interface BiometricResult {
  success: boolean
  /** True when the failure is a fallback-to-password (declined / unavailable). */
  fallback: boolean
  error?: string
}

export async function authenticateBiometric(promptMessage: string): Promise<BiometricResult> {
  const cap = await getBiometricCapability()
  if (!cap.available) {
    return { success: false, fallback: true, error: 'unavailable' }
  }
  try {
    const result = await LocalAuthentication.authenticateAsync({
      promptMessage,
      disableDeviceFallback: false,
      cancelLabel: 'Huỷ',
    })
    if (result.success) return { success: true, fallback: false }
    // User cancelled or auth failed → let caller fall back to password.
    return { success: false, fallback: true, error: 'error' in result ? result.error : undefined }
  } catch {
    return { success: false, fallback: true, error: 'exception' }
  }
}
