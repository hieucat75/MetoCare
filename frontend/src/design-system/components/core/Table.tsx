'use client'

import React, { ReactNode, useCallback } from 'react'
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Column<T> {
  key: keyof T | string
  header: ReactNode
  cell?: (row: T, index: number) => ReactNode
  width?: string
  align?: 'left' | 'center' | 'right'
  sortable?: boolean
}

export interface TableProps<T> {
  columns: Column<T>[]
  data: T[]
  loading?: boolean
  onSort?: (key: string, dir: 'asc' | 'desc') => void
  sortKey?: string
  sortDir?: 'asc' | 'desc'
  rowKey: keyof T
  onRowClick?: (row: T) => void
  emptyMessage?: string
  stickyHeader?: boolean
  striped?: boolean
  compact?: boolean
  className?: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ALIGN_CLASSES: Record<'left' | 'center' | 'right', string> = {
  left: 'text-left',
  center: 'text-center',
  right: 'text-right',
}

function getCellValue<T>(row: T, key: keyof T | string): ReactNode {
  return row[key as keyof T] as ReactNode
}

// ---------------------------------------------------------------------------
// Skeleton loading rows
// ---------------------------------------------------------------------------

function SkeletonRows({ columns, compact }: { columns: number; compact: boolean }) {
  return (
    <>
      {Array.from({ length: 3 }).map((_, rowIdx) => (
        <tr key={rowIdx} className="border-b border-border last:border-none">
          {Array.from({ length: columns }).map((_, colIdx) => (
            <td key={colIdx} className={cn('px-4', compact ? 'py-2' : 'py-3')}>
              <div
                className={cn(
                  'animate-pulse rounded bg-secondary-200',
                  colIdx === 0 ? 'h-4 w-3/4' : 'h-4 w-full',
                )}
              />
            </td>
          ))}
        </tr>
      ))}
    </>
  )
}

// ---------------------------------------------------------------------------
// Sort indicator icon
// ---------------------------------------------------------------------------

function SortIcon({
  colKey,
  sortKey,
  sortDir,
}: {
  colKey: string
  sortKey?: string
  sortDir?: 'asc' | 'desc'
}) {
  const isActive = sortKey === colKey

  if (!isActive) {
    return <ChevronsUpDown className="ml-1 inline h-3.5 w-3.5 text-text-subtle" aria-hidden />
  }
  return sortDir === 'asc' ? (
    <ChevronUp className="ml-1 inline h-3.5 w-3.5 text-primary" aria-hidden />
  ) : (
    <ChevronDown className="ml-1 inline h-3.5 w-3.5 text-primary" aria-hidden />
  )
}

// ---------------------------------------------------------------------------
// Table component
// ---------------------------------------------------------------------------

function TableInner<T extends object>(
  {
    columns,
    data,
    loading = false,
    onSort,
    sortKey,
    sortDir,
    rowKey,
    onRowClick,
    emptyMessage = 'Không có dữ liệu',
    stickyHeader = false,
    striped = false,
    compact = false,
    className,
  }: TableProps<T>,
  _ref: React.Ref<HTMLDivElement>,
) {
  const handleSort = useCallback(
    (col: Column<T>) => {
      if (!col.sortable || !onSort) return
      const colKey = String(col.key)
      const nextDir: 'asc' | 'desc' =
        sortKey === colKey && sortDir === 'asc' ? 'desc' : 'asc'
      onSort(colKey, nextDir)
    },
    [onSort, sortKey, sortDir],
  )

  const isEmpty = !loading && data.length === 0

  return (
    <div
      ref={_ref}
      className={cn('w-full overflow-x-auto rounded-lg border border-border', className)}
    >
      <table className="w-full border-collapse text-body-sm">
        {/* Head */}
        <thead
          className={cn(
            'bg-secondary-50 border-b border-border',
            stickyHeader && 'sticky top-0 z-10',
          )}
        >
          <tr>
            {columns.map((col) => {
              const colKey = String(col.key)
              const isSortable = col.sortable && !!onSort
              const alignClass = ALIGN_CLASSES[col.align ?? 'left']

              return (
                <th
                  key={colKey}
                  scope="col"
                  style={col.width ? { width: col.width } : undefined}
                  className={cn(
                    'px-4 text-label-md font-medium text-text-muted whitespace-nowrap',
                    compact ? 'py-2' : 'py-3',
                    alignClass,
                    isSortable && 'cursor-pointer select-none hover:text-text',
                  )}
                  onClick={isSortable ? () => handleSort(col) : undefined}
                  aria-sort={
                    sortKey === colKey
                      ? sortDir === 'asc'
                        ? 'ascending'
                        : 'descending'
                      : undefined
                  }
                >
                  {col.header}
                  {isSortable && (
                    <SortIcon colKey={colKey} sortKey={sortKey} sortDir={sortDir} />
                  )}
                </th>
              )
            })}
          </tr>
        </thead>

        {/* Body */}
        <tbody>
          {loading ? (
            <SkeletonRows columns={columns.length} compact={compact} />
          ) : isEmpty ? (
            <tr>
              <td
                colSpan={columns.length}
                className={cn(
                  'px-4 text-center text-text-muted',
                  compact ? 'py-8' : 'py-12',
                )}
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((row, rowIdx) => (
              <tr
                key={String(row[rowKey])}
                className={cn(
                  'border-b border-border last:border-none transition-colors hover:bg-background',
                  striped && rowIdx % 2 === 1 && 'bg-secondary-50/50',
                  onRowClick && 'cursor-pointer',
                )}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
              >
                {columns.map((col) => {
                  const colKey = String(col.key)
                  const alignClass = ALIGN_CLASSES[col.align ?? 'left']

                  return (
                    <td
                      key={colKey}
                      className={cn('px-4 text-text', compact ? 'py-2' : 'py-3', alignClass)}
                    >
                      {col.cell ? col.cell(row, rowIdx) : getCellValue(row, col.key)}
                    </td>
                  )
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}

// Generic component with forwardRef via cast — Next.js RSC-safe pattern
export const Table = React.forwardRef(TableInner) as unknown as <T extends object>(
  props: TableProps<T> & { ref?: React.Ref<HTMLDivElement> },
) => React.ReactElement
