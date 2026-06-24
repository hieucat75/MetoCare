'use client'

import * as React from 'react'
import { Plus, Flame, Sunrise, Sun, Moon, Coffee, Bot, Utensils } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { NeuCard, NeuButton, NeuIconButton } from '@/components/patient/neu'
import { PatientEmptyState } from '@/components/patient'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { getNutritionLog, logNutrition } from '@/lib/api/patient'
import type { NutritionEntry } from '@/lib/api/patient'

// ── Constants ─────────────────────────────────────────────────────────────────

type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack'

const MEAL_TYPE_OPTIONS: { value: MealType; label: string }[] = [
  { value: 'breakfast', label: 'Sáng' },
  { value: 'lunch', label: 'Trưa' },
  { value: 'dinner', label: 'Tối' },
  { value: 'snack', label: 'Bữa phụ' },
]

const MEAL_LABELS: Record<MealType, string> = {
  breakfast: 'Sáng',
  lunch: 'Trưa',
  dinner: 'Tối',
  snack: 'Bữa phụ',
}

const MEAL_ICONS: Record<MealType, React.ElementType> = {
  breakfast: Sunrise,
  lunch: Sun,
  dinner: Moon,
  snack: Coffee,
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

function groupByDate(
  entries: NutritionEntry[]
): Array<{ label: string; items: NutritionEntry[] }> {
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)

  const map = new Map<string, NutritionEntry[]>()

  for (const entry of entries) {
    const d = new Date(entry.logged_at)
    let key: string
    if (isSameDay(d, today)) {
      key = 'Hôm nay'
    } else if (isSameDay(d, yesterday)) {
      key = 'Hôm qua'
    } else {
      key = d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' })
    }
    const arr = map.get(key) ?? []
    arr.push(entry)
    map.set(key, arr)
  }

  return Array.from(map.entries()).map(([label, items]) => ({ label, items }))
}

function todayCalories(entries: NutritionEntry[]): number {
  const today = new Date()
  return entries
    .filter((e) => isSameDay(new Date(e.logged_at), today))
    .reduce((sum, e) => sum + (e.calories_kcal ?? 0), 0)
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
}

// ── Entry item ────────────────────────────────────────────────────────────────

function EntryItem({ entry }: { entry: NutritionEntry }) {
  const mealType = entry.meal_type as MealType
  const Icon = MEAL_ICONS[mealType] ?? Coffee
  const label = MEAL_LABELS[mealType] ?? entry.meal_type

  return (
    <div className="py-3 border-b border-[#C8D8D4] last:border-0">
      <div className="flex items-start gap-3">
        {/* Meal type icon in a circular neu-pressed well */}
        <div className="shrink-0 mt-0.5 neu-pressed size-9 rounded-full flex items-center justify-center">
          <Icon className="size-4 text-neu-green" aria-hidden="true" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <span className="text-[13px] font-semibold text-neu-green">{label}</span>
              <p className="text-[15px] font-medium text-neu-text truncate">{entry.description}</p>
            </div>
            <div className="text-right shrink-0">
              {entry.calories_kcal != null && (
                <p className="text-[16px] font-bold text-neu-text">
                  {entry.calories_kcal}{' '}
                  <span className="text-[12px] font-normal text-neu-muted">kcal</span>
                </p>
              )}
              <p className="text-[12px] text-neu-muted">{formatTime(entry.logged_at)}</p>
            </div>
          </div>

          {/* Macros */}
          {(entry.carbs_g != null || entry.protein_g != null || entry.fat_g != null) && (
            <p className="text-[13px] text-neu-muted mt-0.5">
              {[
                entry.carbs_g != null && `Carb ${entry.carbs_g}g`,
                entry.protein_g != null && `Đạm ${entry.protein_g}g`,
                entry.fat_g != null && `Béo ${entry.fat_g}g`,
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
          )}
        </div>
      </div>

      {/* AI coaching tip */}
      {entry.ai_coaching && (
        <div className="mt-2 ml-12">
          <div className="flex items-start gap-2 rounded-[12px] bg-[rgba(245,230,195,0.7)] border border-[rgba(196,136,24,0.25)] p-2.5">
            <Bot className="size-4 text-[#C77A06] shrink-0 mt-0.5" aria-hidden="true" />
            <p className="text-[13px] text-[#7a4f06]">
              <span className="font-semibold">Gợi ý AI:</span> {entry.ai_coaching}
              <span className="block text-[#a0680a] mt-0.5">(AI - không thay thế tư vấn dinh dưỡng)</span>
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Inline add-meal form ───────────────────────────────────────────────────────

interface AddMealFormProps {
  patientId: string
  onAdd: (entry: NutritionEntry) => void
  onClose: () => void
}

function AddMealForm({ patientId, onAdd, onClose }: AddMealFormProps) {
  const [mealType, setMealType] = React.useState<MealType>('breakfast')
  const [description, setDescription] = React.useState('')
  const [calories, setCalories] = React.useState('')
  const [carbs, setCarbs] = React.useState('')
  const [protein, setProtein] = React.useState('')
  const [fat, setFat] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [submitError, setSubmitError] = React.useState<string | null>(null)
  const [descError, setDescError] = React.useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setDescError(null)
    setSubmitError(null)

    if (!description.trim()) {
      setDescError('Vui lòng nhập mô tả bữa ăn')
      return
    }

    setSubmitting(true)
    try {
      const entry = await logNutrition(patientId, {
        meal_type: mealType,
        description: description.trim(),
        calories_kcal: calories ? Number(calories) : undefined,
        carbs_g: carbs ? Number(carbs) : undefined,
        protein_g: protein ? Number(protein) : undefined,
        fat_g: fat ? Number(fat) : undefined,
      })
      onAdd(entry)
      onClose()
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Không thể ghi nhật ký dinh dưỡng')
    } finally {
      setSubmitting(false)
    }
  }

  const inputClass =
    'w-full border-2 border-[#C8D8D4] rounded-[14px] px-4 py-3 bg-white/60 text-[15px] text-neu-text placeholder:text-neu-muted focus:outline-none focus:border-[#0F9C6E] transition-colors'

  return (
    <NeuCard className="mt-3">
      <h2 className="text-[16px] font-bold text-neu-text mb-4">Thêm bữa ăn</h2>
      <form onSubmit={handleSubmit} className="space-y-3">
        {/* Meal type selector */}
        <div>
          <label className="block text-[13px] font-semibold text-neu-muted mb-1.5">Bữa ăn</label>
          <div className="flex gap-2 flex-wrap">
            {MEAL_TYPE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setMealType(opt.value)}
                className={
                  mealType === opt.value
                    ? 'flex-1 min-w-[60px] rounded-[12px] py-2 text-[13px] font-bold text-white bg-gradient-to-b from-[#13b37e] to-[#0F9C6E] shadow-[0_4px_12px_-4px_rgba(15,156,110,0.5)]'
                    : 'flex-1 min-w-[60px] rounded-[12px] py-2 text-[13px] font-semibold text-neu-muted neu-pressed'
                }
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Description */}
        <div>
          <label className="block text-[13px] font-semibold text-neu-muted mb-1.5">
            Mô tả bữa ăn <span className="text-[#D92D20]">*</span>
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Ví dụ: cơm trắng 1 bát, rau luộc..."
            rows={3}
            className={inputClass}
          />
          {descError && <p className="mt-1 text-[13px] text-[#D92D20]">{descError}</p>}
        </div>

        {/* Macros grid */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[13px] font-semibold text-neu-muted mb-1.5">
              Calories (kcal)
            </label>
            <input
              type="number"
              min={0}
              value={calories}
              onChange={(e) => setCalories(e.target.value)}
              placeholder="0"
              className={inputClass}
            />
          </div>
          <div>
            <label className="block text-[13px] font-semibold text-neu-muted mb-1.5">Carbs (g)</label>
            <input
              type="number"
              min={0}
              value={carbs}
              onChange={(e) => setCarbs(e.target.value)}
              placeholder="0"
              className={inputClass}
            />
          </div>
          <div>
            <label className="block text-[13px] font-semibold text-neu-muted mb-1.5">Đạm / Protein (g)</label>
            <input
              type="number"
              min={0}
              value={protein}
              onChange={(e) => setProtein(e.target.value)}
              placeholder="0"
              className={inputClass}
            />
          </div>
          <div>
            <label className="block text-[13px] font-semibold text-neu-muted mb-1.5">Chất béo / Fat (g)</label>
            <input
              type="number"
              min={0}
              value={fat}
              onChange={(e) => setFat(e.target.value)}
              placeholder="0"
              className={inputClass}
            />
          </div>
        </div>

        {/* Submit error */}
        {submitError && (
          <div className="rounded-[12px] bg-[rgba(251,231,229,0.93)] border border-[rgba(217,45,32,0.2)] px-4 py-3">
            <p className="text-[13px] text-[#D92D20]">{submitError}</p>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3 pt-1">
          <NeuButton
            variant="secondary"
            className="flex-1"
            onClick={onClose}
            disabled={submitting}
          >
            Huỷ
          </NeuButton>
          <NeuButton
            type="submit"
            variant="primary"
            className="flex-1"
            disabled={submitting}
          >
            {submitting ? 'Đang lưu...' : 'Lưu'}
          </NeuButton>
        </div>
      </form>
    </NeuCard>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function NutritionPage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [entries, setEntries] = React.useState<NutritionEntry[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [showAddForm, setShowAddForm] = React.useState(false)

  const loadLog = React.useCallback(async () => {
    if (!patientId) return
    setLoading(true)
    setError(null)
    try {
      const res = await getNutritionLog(patientId, { limit: 20 })
      setEntries(res.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được nhật ký dinh dưỡng')
    } finally {
      setLoading(false)
    }
  }, [patientId])

  React.useEffect(() => {
    loadLog()
  }, [loadLog])

  if (!patientId) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <NeuCard>
          <p className="text-[15px] text-neu-muted text-center">
            Không tìm thấy hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </NeuCard>
      </div>
    )
  }

  const todayKcal = todayCalories(entries)
  const groups = groupByDate(entries)
  const todayEntries = entries.filter((e) => isSameDay(new Date(e.logged_at), new Date()))

  return (
    <div className="p-4 max-w-md mx-auto pb-28 space-y-4">
      {/* Header */}
      <header className="flex items-center justify-between">
        <h1 className="text-[22px] font-extrabold tracking-[-0.02em] text-neu-text">
          Nhật ký dinh dưỡng
        </h1>
        <NeuIconButton
          aria-label="Thêm bữa ăn"
          onClick={() => setShowAddForm((v) => !v)}
          className="!w-11 !h-11 !rounded-full text-neu-green"
        >
          <Plus className="size-5" />
        </NeuIconButton>
      </header>

      {/* Today calorie hero card */}
      <NeuCard>
        <div className="flex items-center gap-3">
          <div className="shrink-0 size-12 rounded-full bg-[rgba(254,215,170,0.7)] flex items-center justify-center"
            style={{ boxShadow: 'inset 2px 2px 5px rgba(180,90,20,0.12), inset -1px -1px 3px rgba(255,255,255,0.9)' }}
          >
            <Flame className="size-6 text-[#EA580C]" aria-hidden="true" />
          </div>
          <div>
            <p className="text-[13px] text-neu-muted">Tổng calo hôm nay</p>
            <p className="text-[28px] font-extrabold text-neu-text leading-none">
              {todayKcal.toLocaleString('vi-VN')}
              <span className="text-[15px] font-normal text-neu-muted ml-1">kcal</span>
            </p>
          </div>
        </div>
      </NeuCard>

      {/* Inline add-meal form */}
      {showAddForm && (
        <AddMealForm
          patientId={patientId}
          onAdd={(entry) => setEntries((prev) => [entry, ...prev])}
          onClose={() => setShowAddForm(false)}
        />
      )}

      {/* Loading */}
      {loading && (
        <div className="space-y-3">
          <PatientSkeleton />
          <PatientSkeleton />
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <PatientErrorState
          title="Không tải được nhật ký"
          message={error}
          onRetry={loadLog}
        />
      )}

      {/* Empty today */}
      {!loading && !error && todayEntries.length === 0 && (
        <PatientEmptyState
          icon={<Utensils />}
          title="Chưa có nhật ký hôm nay"
          description="Hãy ghi lại bữa ăn của bạn!"
          action={{
            label: 'Thêm bữa ăn',
            onClick: () => setShowAddForm(true),
          }}
        />
      )}

      {/* Grouped log */}
      {!loading && !error && entries.length > 0 && (
        <div className="space-y-4">
          {groups.map(({ label, items }) => (
            <NeuCard key={label} className="!p-0">
              <div className="px-5 pt-4 pb-1">
                <p className="text-[13px] font-semibold uppercase tracking-[0.05em] text-neu-muted">
                  {label}
                </p>
              </div>
              <div className="px-5 pb-4">
                {items.map((entry) => (
                  <EntryItem key={entry.id} entry={entry} />
                ))}
              </div>
            </NeuCard>
          ))}
        </div>
      )}
    </div>
  )
}
