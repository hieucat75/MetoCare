'use client'

import * as React from 'react'
import { suggestMedications, type DrugSuggestItem } from '@/lib/api/patient'

/**
 * MedicationNameAutocomplete
 *
 * A controlled medication-name input that surfaces matches from the backend
 * drug reference catalog (GET /medications/suggest). NAME LOOKUP ONLY — it
 * never shows dosing, prescribing, or treatment advice.
 *
 * Behaviour:
 *  - Fetches after the user types >= 2 characters, debounced ~300ms.
 *  - Latest-request-wins via AbortController so stale responses never clobber.
 *  - Free-text entry is always preserved: the dropdown only assists.
 *  - Selecting a suggestion fills the field with `display_name` and reports the
 *    full item up via `onSelect` (so the parent can persist the generic name).
 */

const DEBOUNCE_MS = 300
const MIN_CHARS = 2
const DEFAULT_LIMIT = 10

export const MEDICATION_SAFETY_NOTICE =
  'Thông tin thuốc chỉ để nhận diện tên thuốc. ' +
  'Không tự ý dùng, ngừng hoặc đổi liều nếu chưa có chỉ định của bác sĩ.'

interface MedicationNameAutocompleteProps {
  value: string
  onChange: (name: string) => void
  /** Fired when the user picks a catalog suggestion (not on free-text typing). */
  onSelect?: (item: DrugSuggestItem) => void
  inputClassName?: string
  placeholder?: string
  id?: string
  /** Optional metric group key to bias results (e.g. 'diabetes', 'lipid'). */
  metricGroup?: string
  required?: boolean
}

export function MedicationNameAutocomplete({
  value,
  onChange,
  onSelect,
  inputClassName,
  placeholder,
  id,
  metricGroup,
  required,
}: MedicationNameAutocompleteProps) {
  const [suggestions, setSuggestions] = React.useState<DrugSuggestItem[]>([])
  const [open, setOpen] = React.useState(false)
  const [loading, setLoading] = React.useState(false)
  const [errored, setErrored] = React.useState(false)
  const [activeIndex, setActiveIndex] = React.useState(-1)

  // Suppress the next fetch when the value change came from selecting a suggestion.
  const skipNextFetch = React.useRef(false)
  const rootRef = React.useRef<HTMLDivElement>(null)

  const query = value.trim()

  // Debounced catalog lookup. Latest request wins via AbortController.
  React.useEffect(() => {
    if (skipNextFetch.current) {
      skipNextFetch.current = false
      return
    }
    if (query.length < MIN_CHARS) {
      setSuggestions([])
      setOpen(false)
      setLoading(false)
      setErrored(false)
      return
    }

    const controller = new AbortController()
    setLoading(true)
    setErrored(false)

    const timer = setTimeout(() => {
      suggestMedications(query, {
        metricGroup,
        limit: DEFAULT_LIMIT,
        signal: controller.signal,
      })
        .then((resp) => {
          setSuggestions(resp.results)
          setActiveIndex(-1)
          setOpen(true)
          setLoading(false)
        })
        .catch((err: unknown) => {
          // Aborted requests are expected on each keystroke — ignore them.
          if (err instanceof DOMException && err.name === 'AbortError') return
          setSuggestions([])
          setErrored(true)
          setOpen(true)
          setLoading(false)
        })
    }, DEBOUNCE_MS)

    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query, metricGroup])

  // Close the dropdown on outside click.
  React.useEffect(() => {
    if (!open) return
    function onDocClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [open])

  function handleSelect(item: DrugSuggestItem) {
    skipNextFetch.current = true
    onChange(item.display_name)
    onSelect?.(item)
    setOpen(false)
    setSuggestions([])
    setActiveIndex(-1)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || suggestions.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => Math.min(i + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      e.preventDefault()
      handleSelect(suggestions[activeIndex])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const showDropdown = open && query.length >= MIN_CHARS
  const showEmpty = showDropdown && !loading && !errored && suggestions.length === 0
  const listboxId = id ? `${id}-listbox` : 'medication-suggest-listbox'

  return (
    <div ref={rootRef} className="relative">
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => {
          if (suggestions.length > 0) setOpen(true)
        }}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        className={inputClassName}
        required={required}
        autoComplete="off"
        role="combobox"
        aria-expanded={showDropdown}
        aria-controls={listboxId}
        aria-autocomplete="list"
      />

      {showDropdown && (
        <ul
          id={listboxId}
          role="listbox"
          className="absolute z-50 mt-1 max-h-72 w-full overflow-auto rounded-[14px] border-2 border-[#C8D8D4] bg-white shadow-lg"
        >
          {loading && (
            <li className="px-4 py-3 text-[15px] text-neu-muted" aria-live="polite">
              Đang tìm…
            </li>
          )}

          {errored && (
            <li className="px-4 py-3 text-[15px] text-neu-muted">
              Không tải được gợi ý. Bạn vẫn có thể tự nhập tên thuốc.
            </li>
          )}

          {showEmpty && (
            <li className="px-4 py-3 text-[15px] text-neu-muted">
              Không tìm thấy thuốc phù hợp. Bạn vẫn có thể tự nhập tên.
            </li>
          )}

          {!loading &&
            !errored &&
            suggestions.map((item, idx) => {
              const secondary = [item.generic_name, item.drug_class.replace(/_/g, ' ')]
                .filter(Boolean)
                .join(' · ')
              const isActive = idx === activeIndex
              return (
                <li key={item.id} role="option" aria-selected={isActive}>
                  <button
                    type="button"
                    // Use onMouseDown so selection fires before the input blur closes the list.
                    onMouseDown={(e) => {
                      e.preventDefault()
                      handleSelect(item)
                    }}
                    className={`flex min-h-[44px] w-full flex-col items-start gap-0.5 px-4 py-2.5 text-left transition-colors ${
                      isActive ? 'bg-[#E8F5F0]' : 'hover:bg-[#F2F8F6]'
                    }`}
                  >
                    <span className="flex w-full items-center gap-2">
                      <span className="text-[16px] font-semibold text-neu-text">
                        {item.display_name}
                      </span>
                      {item.prescription_required && (
                        <span className="rounded-full bg-[#FEF0E7] px-2 py-0.5 text-[11px] font-semibold text-[#C2410C]">
                          Thuốc kê đơn
                        </span>
                      )}
                    </span>
                    {secondary && <span className="text-[13px] text-neu-muted">{secondary}</span>}
                  </button>
                </li>
              )
            })}
        </ul>
      )}
    </div>
  )
}
