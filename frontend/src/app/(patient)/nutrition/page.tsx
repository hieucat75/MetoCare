'use client'

import * as React from 'react'
import { Plus, Flame, Sunrise, Sun, Moon, Coffee, Bot } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import {
  Button,
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Alert,
  Modal,
  EmptyState,
  PageHeader,
  Spinner,
  ErrorState,
} from '@/design-system'
import { Select } from '@/design-system'
import { Textarea } from '@/design-system'
import { Input } from '@/design-system'
import { getNutritionLog, logNutrition } from '@/lib/api/patient'
import type { NutritionEntry } from '@/lib/api/patient'

// ── Constants ─────────────────────────────────────────────────────────────────

type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack'

const MEAL_TYPE_OPTIONS = [
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

function groupByDate(entries: NutritionEntry[]): Array<{ label: string; items: NutritionEntry[] }> {
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

// ── Entry card ────────────────────────────────────────────────────────────────

function EntryItem({ entry }: { entry: NutritionEntry }) {
  const mealType = entry.meal_type as MealType
  const Icon = MEAL_ICONS[mealType] ?? Coffee
  const label = MEAL_LABELS[mealType] ?? entry.meal_type

  return (
    <div className="py-3 border-b border-border last:border-0">
      <div className="flex items-start gap-3">
        <div className="shrink-0 mt-0.5 w-8 h-8 rounded-full bg-secondary-100 flex items-center justify-center">
          <Icon className="size-4 text-secondary-600" aria-hidden="true" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <span className="text-caption font-medium text-mint-600">{label}</span>
              <p className="text-body-sm text-text truncate">{entry.description}</p>
            </div>
            <div className="text-right shrink-0">
              {entry.calories_kcal != null && (
                <p className="text-body-sm font-semibold text-text">
                  {entry.calories_kcal} kcal
                </p>
              )}
              <p className="text-caption text-text-muted">{formatTime(entry.logged_at)}</p>
            </div>
          </div>

          {/* Macros */}
          {(entry.carbs_g != null || entry.protein_g != null || entry.fat_g != null) && (
            <p className="text-caption text-text-muted mt-0.5">
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
        <div className="mt-2 ml-11">
          <div className="flex items-start gap-2 rounded-md bg-amber-50 border border-amber-200 p-2.5">
            <Bot className="size-4 text-amber-600 shrink-0 mt-0.5" aria-hidden="true" />
            <p className="text-caption text-amber-800">
              <span className="font-medium">Gợi ý AI:</span> {entry.ai_coaching}
              <span className="block text-amber-600 mt-0.5">
                (AI - không thay thế tư vấn dinh dưỡng)
              </span>
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Add meal modal ────────────────────────────────────────────────────────────

interface AddMealModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onAdd: (entry: NutritionEntry) => void
  patientId: string
}

function AddMealModal({ open, onOpenChange, onAdd, patientId }: AddMealModalProps) {
  const [mealType, setMealType] = React.useState<string>('breakfast')
  const [description, setDescription] = React.useState('')
  const [calories, setCalories] = React.useState('')
  const [carbs, setCarbs] = React.useState('')
  const [protein, setProtein] = React.useState('')
  const [fat, setFat] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [submitError, setSubmitError] = React.useState<string | null>(null)
  const [descError, setDescError] = React.useState<string | null>(null)

  function reset() {
    setMealType('breakfast')
    setDescription('')
    setCalories('')
    setCarbs('')
    setProtein('')
    setFat('')
    setSubmitError(null)
    setDescError(null)
  }

  function handleClose(open: boolean) {
    if (!open) reset()
    onOpenChange(open)
  }

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
        meal_type: mealType as MealType,
        description: description.trim(),
        calories_kcal: calories ? Number(calories) : undefined,
        carbs_g: carbs ? Number(carbs) : undefined,
        protein_g: protein ? Number(protein) : undefined,
        fat_g: fat ? Number(fat) : undefined,
      })
      onAdd(entry)
      handleClose(false)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Không thể ghi nhật ký dinh dưỡng')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={handleClose}
      title="Thêm bữa ăn"
      footer={
        <>
          <Button
            variant="outline"
            size="sm"
            disabled={submitting}
            onClick={() => handleClose(false)}
          >
            Huỷ
          </Button>
          <Button
            variant="mint"
            size="sm"
            loading={submitting}
            onClick={handleSubmit}
          >
            Lưu
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Select
          label="Bữa ăn"
          value={mealType}
          onValueChange={setMealType}
          options={MEAL_TYPE_OPTIONS}
          fullWidth
        />

        <Textarea
          label="Mô tả bữa ăn *"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Mô tả bữa ăn: ví dụ cơm trắng 1 bát, rau luộc..."
          rows={3}
          error={descError ?? undefined}
          fullWidth
        />

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Calories (kcal)"
            type="number"
            min={0}
            value={calories}
            onChange={(e) => setCalories(e.target.value)}
            placeholder="0"
          />
          <Input
            label="Carbs (g)"
            type="number"
            min={0}
            value={carbs}
            onChange={(e) => setCarbs(e.target.value)}
            placeholder="0"
          />
          <Input
            label="Đạm / Protein (g)"
            type="number"
            min={0}
            value={protein}
            onChange={(e) => setProtein(e.target.value)}
            placeholder="0"
          />
          <Input
            label="Chất béo / Fat (g)"
            type="number"
            min={0}
            value={fat}
            onChange={(e) => setFat(e.target.value)}
            placeholder="0"
          />
        </div>

        {submitError && (
          <Alert variant="danger">{submitError}</Alert>
        )}
      </form>
    </Modal>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function NutritionPage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [entries, setEntries] = React.useState<NutritionEntry[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [addModalOpen, setAddModalOpen] = React.useState(false)

  // ── Load log ───────────────────────────────────────────────────────────────
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

  // ── Guard ──────────────────────────────────────────────────────────────────
  if (!patientId) {
    return (
      <div className="p-4 lg:p-6 max-w-2xl mx-auto">
        <Alert variant="warning">
          Không tìm thấy hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
        </Alert>
      </div>
    )
  }

  const todayKcal = todayCalories(entries)
  const groups = groupByDate(entries)
  const todayEntries = entries.filter((e) => isSameDay(new Date(e.logged_at), new Date()))

  return (
    <div className="p-4 lg:p-6 space-y-6 max-w-2xl mx-auto">
      <PageHeader
        title="Nhật ký dinh dưỡng"
        actions={
          <Button
            variant="mint"
            size="sm"
            leftIcon={<Plus className="size-4" />}
            onClick={() => setAddModalOpen(true)}
          >
            Thêm bữa ăn
          </Button>
        }
      />

      {/* Today's calorie summary */}
      <Card variant="glass" padding="md">
        <CardContent>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-orange-100 flex items-center justify-center shrink-0">
              <Flame className="size-5 text-orange-500" aria-hidden="true" />
            </div>
            <div>
              <p className="text-caption text-text-muted">Tổng calo hôm nay</p>
              <p className="text-heading-lg font-bold text-text">
                {todayKcal.toLocaleString('vi-VN')}{' '}
                <span className="text-body-sm font-normal text-text-muted">kcal</span>
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-10">
          <Spinner size="md" />
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <ErrorState
          variant="inline"
          title="Không tải được nhật ký"
          message={error}
          onRetry={loadLog}
        />
      )}

      {/* Empty today */}
      {!loading && !error && todayEntries.length === 0 && (
        <EmptyState
          title="Chưa có nhật ký hôm nay"
          description="Chưa có nhật ký dinh dưỡng hôm nay. Hãy ghi lại bữa ăn của bạn!"
          action={{
            label: 'Thêm bữa ăn',
            onClick: () => setAddModalOpen(true),
          }}
        />
      )}

      {/* Grouped log */}
      {!loading && !error && entries.length > 0 && (
        <div className="space-y-4">
          {groups.map(({ label, items }) => (
            <Card key={label} variant="glass" padding="none">
              <CardHeader className="px-5 pt-4 pb-0">
                <CardTitle className="text-body-sm font-semibold text-text-muted">
                  {label}
                </CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-4">
                {items.map((entry) => (
                  <EntryItem key={entry.id} entry={entry} />
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Add meal modal */}
      <AddMealModal
        open={addModalOpen}
        onOpenChange={setAddModalOpen}
        patientId={patientId}
        onAdd={(entry) => setEntries((prev) => [entry, ...prev])}
      />
    </div>
  )
}
