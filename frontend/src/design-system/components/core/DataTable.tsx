'use client'

import { type ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Card } from './Card'
import { Table, type Column } from './Table'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DataColumn<T> {
  /** Unique column key (used for React keys and default value lookup). */
  key: string
  /** Header label — also used as the field label on the mobile card. */
  header: ReactNode
  /** Custom cell renderer. Falls back to `row[key]` when omitted. */
  render?: (row: T) => ReactNode
  /**
   * Mobile emphasis. Lower number = more important. The most important column
   * becomes the mobile card's header; the rest render as label:value rows in
   * ascending priority order. Columns without a priority keep source order
   * after prioritised ones.
   */
  priority?: number
  align?: 'left' | 'center' | 'right'
}

export interface DataTableProps<T> {
  columns: DataColumn<T>[]
  rows: T[]
  /** Field on each row that yields a stable unique key. */
  keyField: keyof T
  /** Optional per-row action cluster (buttons, links). */
  rowActions?: (row: T) => ReactNode
  onRowClick?: (row: T) => void
  loading?: boolean
  emptyMessage?: string
  className?: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderCell<T>(col: DataColumn<T>, row: T): ReactNode {
  if (col.render) return col.render(row)
  return (row as Record<string, ReactNode>)[col.key]
}

/**
 * Order columns for the mobile card: prioritised columns first (ascending),
 * then the remaining columns in their original order. The first entry is used
 * as the card header, the rest become label:value rows.
 */
function orderForMobile<T>(columns: DataColumn<T>[]): DataColumn<T>[] {
  const withPriority = columns
    .filter((c) => c.priority !== undefined)
    .sort((a, b) => (a.priority as number) - (b.priority as number))
  const withoutPriority = columns.filter((c) => c.priority === undefined)
  return [...withPriority, ...withoutPriority]
}

// ---------------------------------------------------------------------------
// Mobile stacked-card view (< md)
// ---------------------------------------------------------------------------

function MobileCards<T>({
  columns,
  rows,
  keyField,
  rowActions,
  onRowClick,
  loading,
  emptyMessage,
}: Required<Pick<DataTableProps<T>, 'columns' | 'rows' | 'keyField'>> &
  Pick<DataTableProps<T>, 'rowActions' | 'onRowClick'> & {
    loading: boolean
    emptyMessage: string
  }) {
  if (loading) {
    return (
      <div className="space-y-3" aria-busy="true">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i} padding="md">
            <div className="space-y-2">
              <div className="h-5 w-1/2 animate-pulse rounded bg-secondary-200" />
              <div className="h-4 w-full animate-pulse rounded bg-secondary-200" />
              <div className="h-4 w-2/3 animate-pulse rounded bg-secondary-200" />
            </div>
          </Card>
        ))}
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <Card padding="lg">
        <p className="text-center text-base text-text-muted">{emptyMessage}</p>
      </Card>
    )
  }

  const ordered = orderForMobile(columns)
  const [headerCol, ...bodyCols] = ordered

  return (
    <div className="space-y-3">
      {rows.map((row) => (
        <Card
          key={String(row[keyField])}
          padding="md"
          interactive={!!onRowClick}
          className={onRowClick ? 'min-h-[44px]' : undefined}
        >
          <div
            role={onRowClick ? 'button' : undefined}
            tabIndex={onRowClick ? 0 : undefined}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
            onKeyDown={
              onRowClick
                ? (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onRowClick(row)
                    }
                  }
                : undefined
            }
          >
            {/* Card header — most important field */}
            {headerCol && (
              <div className="mb-2 text-base font-semibold text-text">
                {renderCell(headerCol, row)}
              </div>
            )}

            {/* Remaining fields as label : value rows */}
            <dl className="divide-y divide-border">
              {bodyCols.map((col) => (
                <div key={col.key} className="flex items-start justify-between gap-3 py-2">
                  <dt className="text-base text-text-muted">{col.header}</dt>
                  <dd className="text-right text-base text-text">{renderCell(col, row)}</dd>
                </div>
              ))}
            </dl>
          </div>

          {/* Actions footer — tap targets forced to >= 44px */}
          {rowActions && (
            <div className="mt-3 flex flex-wrap gap-2 border-t border-border pt-3 [&_a]:min-h-[44px] [&_button]:min-h-[44px]">
              {rowActions(row)}
            </div>
          )}
        </Card>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// DataTable — responsive generic table
// ---------------------------------------------------------------------------

/**
 * Responsive data table.
 *
 * - `>= md`: renders a real semantic `<table>` (delegates to the design-system
 *   `Table`), appending a trailing actions column when `rowActions` is set.
 * - `< md`: renders each row as a stacked `Card` with label:value pairs and an
 *   actions footer.
 *
 * Both views are always rendered and toggled with Tailwind `hidden`/`md:*`
 * classes so there is no hydration flash and no client-only gating.
 */
export function DataTable<T extends object>({
  columns,
  rows,
  keyField,
  rowActions,
  onRowClick,
  loading = false,
  emptyMessage = 'Không có dữ liệu',
  className,
}: DataTableProps<T>) {
  // Map to the desktop Table's column shape, appending an actions column.
  const tableColumns: Column<T>[] = columns.map((col) => ({
    key: col.key,
    header: col.header,
    align: col.align,
    cell: col.render ? (row: T) => col.render!(row) : undefined,
  }))

  if (rowActions) {
    tableColumns.push({
      key: '__actions',
      header: 'Thao tác',
      align: 'right',
      cell: (row: T) => (
        <div className="flex flex-wrap items-center justify-end gap-2">{rowActions(row)}</div>
      ),
    })
  }

  return (
    <div className={className}>
      {/* Desktop / tablet — real table */}
      <div className={cn('hidden md:block')}>
        <Table
          columns={tableColumns}
          data={rows}
          rowKey={keyField}
          loading={loading}
          emptyMessage={emptyMessage}
          onRowClick={onRowClick}
        />
      </div>

      {/* Mobile — stacked cards */}
      <div className="md:hidden">
        <MobileCards
          columns={columns}
          rows={rows}
          keyField={keyField}
          rowActions={rowActions}
          onRowClick={onRowClick}
          loading={loading}
          emptyMessage={emptyMessage}
        />
      </div>
    </div>
  )
}

export default DataTable
