import { useCallback, useState } from 'react'

import type { ApiClient, FetchLike } from '../../api/client'
import { isConsentDenied, toPageError } from '../../api/client'
import {
  createUploadSession,
  type DocTypeHint,
  finalizeUpload,
  uploadToSignedUrl,
} from '../../api/documents'

type Phase = 'idle' | 'uploading' | 'error'

export interface PickedAsset {
  uri: string
  mimeType: string
}

export interface AddDocumentState {
  phase: Phase
  errorMsg?: string
  /**
   * The failure was a fail-closed `documents` consent gate, not a transport or
   * server fault. The screen must offer a route to the consent settings — the
   * patient cannot otherwise discover why uploading is refused.
   */
  consentDenied: boolean
  submit: (asset: PickedAsset, docType: DocTypeHint) => Promise<string | null>
}

/**
 * Orchestrates the secure ingestion flow from a picked/captured image
 * (BRD §C/§D): upload-session → PUT bytes to the signed url → finalize →
 * returns the document id (or null on failure). `fetchImpl` reads the local
 * file uri into a Blob body and is injectable for tests.
 */
export function useAddDocument(client: ApiClient, fetchImpl: FetchLike = fetch): AddDocumentState {
  const [phase, setPhase] = useState<Phase>('idle')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  const [consentDenied, setConsentDenied] = useState(false)

  const submit = useCallback(
    async (asset: PickedAsset, docType: DocTypeHint): Promise<string | null> => {
      setPhase('uploading')
      setErrorMsg(undefined)
      setConsentDenied(false)
      try {
        const session = await createUploadSession(client, {
          declaredMime: asset.mimeType,
          docTypeHint: docType,
        })
        // Read the local file uri into bytes for the raw PUT.
        const fileResp = await fetchImpl(asset.uri)
        const body = (await fileResp.blob()) as unknown as BodyInit
        await uploadToSignedUrl(session.signed_put_url, body, asset.mimeType, { fetchImpl })
        const doc = await finalizeUpload(client, session.upload_id)
        setPhase('idle')
        return doc.id
      } catch (err) {
        setConsentDenied(isConsentDenied(err))
        setErrorMsg(toPageError(err).message)
        setPhase('error')
        return null
      }
    },
    [client, fetchImpl]
  )

  return { phase, errorMsg, consentDenied, submit }
}
