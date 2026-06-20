'use client'

import * as React from 'react'
import * as TabsPrimitive from '@radix-ui/react-tabs'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type TabVariant = 'line' | 'pill' | 'card'

export interface TabItem {
  /** Unique value used as the identifier for this tab. */
  value: string
  /** Human-readable tab label. */
  label: string
  /** Optional icon rendered before the label. */
  icon?: React.ReactNode
  /** Optional badge (number or string) rendered after the label. */
  badge?: string | number
  /** Whether this tab is non-interactive. */
  disabled?: boolean
}

export interface TabsProps {
  /** Uncontrolled: initial selected tab value. */
  defaultValue?: string
  /** Controlled: current selected tab value. */
  value?: string
  /** Controlled: callback when selected tab changes. */
  onValueChange?: (value: string) => void
  /** Tab definitions rendered in the list. */
  tabs?: TabItem[]
  /**
   * Tab panel content. Each panel should be a <TabsContent> with a matching
   * `value` prop, or you may compose using <Tabs.List> / <Tabs.Trigger>.
   */
  children?: React.ReactNode
  /** Visual style of the tab list. Defaults to 'line'. */
  variant?: TabVariant
  /** Active-state color tone. 'mint' for the patient app; defaults to primary. */
  tone?: 'primary' | 'mint'
  /** Additional class names applied to the root element. */
  className?: string
}

// ---------------------------------------------------------------------------
// Variant maps
// ---------------------------------------------------------------------------

const listVariantClasses: Record<TabVariant, string> = {
  line: 'border-b border-border',
  pill: 'bg-secondary-100 rounded-lg p-1 gap-1',
  card: 'border-b border-border gap-0',
}

const triggerVariantClasses: Record<TabVariant, string> = {
  // line: bottom-border indicator, flush with the list border
  line: cn(
    'relative inline-flex items-center gap-2 px-4 py-2.5',
    'text-body-sm font-medium text-text-muted',
    'border-b-2 border-transparent -mb-px',
    'hover:text-text hover:border-secondary-300',
    'data-[state=active]:text-primary data-[state=active]:border-primary',
    'disabled:pointer-events-none disabled:opacity-40',
    'transition-colors duration-150',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-1',
  ),
  // pill: filled pill on active
  pill: cn(
    'relative inline-flex items-center gap-2 px-3 py-1.5 rounded-md',
    'text-body-sm font-medium text-text-muted',
    'hover:text-text',
    'data-[state=active]:bg-surface data-[state=active]:text-text data-[state=active]:shadow-sm',
    'disabled:pointer-events-none disabled:opacity-40',
    'transition-all duration-150',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50',
  ),
  // card: bordered card tabs
  card: cn(
    'relative inline-flex items-center gap-2 px-4 py-2.5',
    'text-body-sm font-medium text-text-muted',
    'border border-transparent border-b-border -mb-px rounded-t-lg',
    'hover:text-text hover:bg-secondary-50',
    'data-[state=active]:bg-surface data-[state=active]:text-text',
    'data-[state=active]:border-border data-[state=active]:border-b-surface',
    'disabled:pointer-events-none disabled:opacity-40',
    'transition-colors duration-150',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-1',
  ),
}

// ---------------------------------------------------------------------------
// Badge sub-component
// ---------------------------------------------------------------------------

function TabBadge({ value, tone = 'primary' }: { value: string | number; tone?: 'primary' | 'mint' }) {
  return (
    <span
      className={cn(
        'inline-flex items-center justify-center',
        'min-w-[1.25rem] h-5 px-1.5 rounded-full',
        'text-label-sm font-semibold',
        'bg-secondary-200 text-text-muted',
        tone === 'mint'
          ? 'group-data-[state=active]:bg-mint-100 group-data-[state=active]:text-mint-700'
          : 'group-data-[state=active]:bg-primary-100 group-data-[state=active]:text-primary',
        'transition-colors duration-150',
      )}
    >
      {value}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Primitive re-exports (unstyled, for composition)
// ---------------------------------------------------------------------------

/**
 * Unstyled Radix TabsList — use when you need full control over the list container.
 */
export const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn('flex items-center', className)}
    {...props}
  />
))
TabsList.displayName = 'TabsList'

/**
 * Unstyled Radix TabsTrigger — use when you need full control over individual triggers.
 */
export const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      'inline-flex items-center justify-center whitespace-nowrap',
      'focus-visible:outline-none',
      className,
    )}
    {...props}
  />
))
TabsTrigger.displayName = 'TabsTrigger'

/**
 * Styled tab panel content area.
 */
export const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn(
      'mt-4',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-2',
      className,
    )}
    {...props}
  />
))
TabsContent.displayName = 'TabsContent'

// ---------------------------------------------------------------------------
// Tabs (primary component)
// ---------------------------------------------------------------------------

/**
 * Feature-complete Tabs component built on @radix-ui/react-tabs.
 *
 * Supports three visual variants — 'line' (default), 'pill', and 'card' — and
 * renders the tab list automatically from the `tabs` prop, or lets you
 * compose with `<TabsList>`, `<TabsTrigger>`, and `<TabsContent>` directly.
 *
 * @example — data-driven usage
 * ```tsx
 * <Tabs
 *   variant="pill"
 *   defaultValue="overview"
 *   tabs={[
 *     { value: 'overview', label: 'Tổng quan', icon: <LayoutDashboard className="h-4 w-4" /> },
 *     { value: 'history',  label: 'Lịch sử',   badge: 3 },
 *     { value: 'settings', label: 'Cài đặt',   disabled: true },
 *   ]}
 * >
 *   <TabsContent value="overview">…</TabsContent>
 *   <TabsContent value="history">…</TabsContent>
 *   <TabsContent value="settings">…</TabsContent>
 * </Tabs>
 * ```
 *
 * @example — compositional usage
 * ```tsx
 * <Tabs defaultValue="a">
 *   <TabsList>
 *     <TabsTrigger value="a">A</TabsTrigger>
 *     <TabsTrigger value="b">B</TabsTrigger>
 *   </TabsList>
 *   <TabsContent value="a">Content A</TabsContent>
 *   <TabsContent value="b">Content B</TabsContent>
 * </Tabs>
 * ```
 */
function TabsRoot({
  defaultValue,
  value,
  onValueChange,
  tabs,
  children,
  variant = 'line',
  tone = 'primary',
  className,
}: TabsProps) {
  // Resolve a sensible defaultValue when the caller only passes `tabs`
  const resolvedDefault = defaultValue ?? (tabs && tabs.length > 0 ? tabs[0].value : undefined)
  // Mint tone overrides the primary active color (patient app); doctor/admin keep
  // primary. Literal classes (not runtime-built) so Tailwind's JIT generates them;
  // `!` wins over the variant's primary active classes regardless of CSS order.
  const triggerCls = cn(
    triggerVariantClasses[variant],
    tone === 'mint' &&
      'data-[state=active]:!text-mint-700 data-[state=active]:!border-mint-500',
  )

  return (
    <TabsPrimitive.Root
      defaultValue={resolvedDefault}
      value={value}
      onValueChange={onValueChange}
      className={cn('w-full', className)}
    >
      {/* Auto-rendered list — only when `tabs` prop is provided */}
      {tabs && tabs.length > 0 && (
        <TabsPrimitive.List
          className={cn('flex items-center', listVariantClasses[variant])}
        >
          {tabs.map((tab) => (
            <TabsPrimitive.Trigger
              key={tab.value}
              value={tab.value}
              disabled={tab.disabled}
              className={cn('group whitespace-nowrap', triggerCls)}
            >
              {tab.icon && (
                <span className="shrink-0 [&>svg]:h-4 [&>svg]:w-4" aria-hidden>
                  {tab.icon}
                </span>
              )}
              {tab.label}
              {tab.badge != null && <TabBadge value={tab.badge} tone={tone} />}
            </TabsPrimitive.Trigger>
          ))}
        </TabsPrimitive.List>
      )}

      {children}
    </TabsPrimitive.Root>
  )
}

// ---------------------------------------------------------------------------
// Compound-component pattern: attach sub-components as static properties
// ---------------------------------------------------------------------------

type TabsComponent = typeof TabsRoot & {
  List: typeof TabsList
  Trigger: typeof TabsTrigger
  Content: typeof TabsContent
}

export const Tabs = TabsRoot as TabsComponent
Tabs.List = TabsList
Tabs.Trigger = TabsTrigger
Tabs.Content = TabsContent
