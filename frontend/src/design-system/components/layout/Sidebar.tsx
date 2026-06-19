'use client'

import * as React from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface NavItem {
  id: string
  label: string
  icon: React.ReactNode
  href: string
  badge?: string | number
  children?: NavItem[]
}

export interface SidebarProps {
  items: NavItem[]
  activeItemId: string
  onItemClick: (item: NavItem) => void
  collapsed?: boolean
  header?: React.ReactNode
  footer?: React.ReactNode
  userProfile?: {
    name: string
    role: string
    avatar?: string
  }
  className?: string
}

// ---------------------------------------------------------------------------
// Helper — avatar initials
// ---------------------------------------------------------------------------

function getInitials(name: string): string {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('')
}

// ---------------------------------------------------------------------------
// NavItemRow — single nav item (leaf or parent)
// ---------------------------------------------------------------------------

interface NavItemRowProps {
  item: NavItem
  depth?: number
  isActive: boolean
  collapsed: boolean
  onItemClick: (item: NavItem) => void
  activeItemId: string
}

function NavItemRow({
  item,
  depth = 0,
  isActive,
  collapsed,
  onItemClick,
  activeItemId,
}: NavItemRowProps) {
  const hasChildren = Array.isArray(item.children) && item.children.length > 0

  // Determine if any child is active so we can keep the parent group expanded
  const hasActiveChild =
    hasChildren &&
    item.children!.some(
      (child) =>
        child.id === activeItemId ||
        (Array.isArray(child.children) && child.children.some((c) => c.id === activeItemId)),
    )

  const [open, setOpen] = React.useState(hasActiveChild)

  // Re-evaluate open state when active changes
  React.useEffect(() => {
    if (hasActiveChild) setOpen(true)
  }, [hasActiveChild])

  const handleClick = () => {
    if (hasChildren) {
      if (!collapsed) setOpen((prev) => !prev)
    } else {
      onItemClick(item)
    }
  }

  const baseItemClass = cn(
    'flex items-center gap-3 px-3 py-2 rounded-md text-secondary-300',
    'hover:bg-secondary-800 hover:text-white transition-colors cursor-pointer select-none',
    'text-body-sm font-medium',
    depth > 0 && 'pl-9',
    isActive && 'bg-primary text-white hover:bg-primary-hover',
  )

  return (
    <>
      <li>
        <div
          role="button"
          tabIndex={0}
          title={collapsed ? item.label : undefined}
          aria-current={isActive ? 'page' : undefined}
          className={baseItemClass}
          onClick={handleClick}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              handleClick()
            }
          }}
        >
          {/* Icon */}
          <span className="shrink-0 w-5 h-5 inline-flex items-center justify-center" aria-hidden="true">
            {item.icon}
          </span>

          {/* Label + badge — hidden when collapsed */}
          {!collapsed && (
            <>
              <span className="flex-1 truncate">{item.label}</span>

              {item.badge !== undefined && !hasChildren && (
                <span
                  className={cn(
                    'inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1.5',
                    'text-label-sm rounded-full shrink-0',
                    isActive
                      ? 'bg-white/20 text-white'
                      : 'bg-primary text-white',
                  )}
                  aria-label={`${item.badge} notifications`}
                >
                  {item.badge}
                </span>
              )}

              {hasChildren && (
                <ChevronDown
                  className={cn(
                    'h-4 w-4 shrink-0 transition-transform duration-200',
                    open && 'rotate-180',
                  )}
                  aria-hidden="true"
                />
              )}
            </>
          )}
        </div>
      </li>

      {/* Children sub-list */}
      {hasChildren && !collapsed && open && (
        <li>
          <ul className="mt-0.5 space-y-0.5">
            {item.children!.map((child) => (
              <NavItemRow
                key={child.id}
                item={child}
                depth={depth + 1}
                isActive={child.id === activeItemId}
                collapsed={collapsed}
                onItemClick={onItemClick}
                activeItemId={activeItemId}
              />
            ))}
          </ul>
        </li>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

export function Sidebar({
  items,
  activeItemId,
  onItemClick,
  collapsed = false,
  header,
  footer,
  userProfile,
  className,
}: SidebarProps) {
  return (
    <div
      className={cn(
        'flex flex-col h-full bg-secondary-900 text-white overflow-hidden',
        className,
      )}
    >
      {/* Custom header slot */}
      {header && (
        <div className="shrink-0 border-b border-secondary-800">
          {header}
        </div>
      )}

      {/* Nav items — scrollable */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden py-3 px-2 scrollbar-hide" aria-label="Main navigation">
        <ul className="space-y-0.5">
          {items.map((item) => (
            <NavItemRow
              key={item.id}
              item={item}
              isActive={item.id === activeItemId}
              collapsed={collapsed}
              onItemClick={onItemClick}
              activeItemId={activeItemId}
            />
          ))}
        </ul>
      </nav>

      {/* Custom footer slot */}
      {footer && (
        <div className="shrink-0 border-t border-secondary-800 p-2">
          {footer}
        </div>
      )}

      {/* User profile */}
      {userProfile && (
        <div
          className={cn(
            'shrink-0 border-t border-secondary-800 p-3',
            'flex items-center gap-3',
            collapsed && 'justify-center',
          )}
          title={collapsed ? `${userProfile.name} — ${userProfile.role}` : undefined}
        >
          {/* Avatar */}
          {userProfile.avatar ? (
            <img
              src={userProfile.avatar}
              alt={userProfile.name}
              className="w-8 h-8 rounded-full shrink-0 object-cover"
            />
          ) : (
            <span
              className={cn(
                'inline-flex items-center justify-center rounded-full shrink-0',
                'w-8 h-8 bg-primary text-white text-label-md font-semibold',
              )}
              aria-hidden="true"
            >
              {getInitials(userProfile.name)}
            </span>
          )}

          {/* Name + role — hidden when collapsed */}
          {!collapsed && (
            <div className="min-w-0 flex-1">
              <p className="text-body-sm font-medium text-white truncate">{userProfile.name}</p>
              <p className="text-body-xs text-secondary-400 truncate">{userProfile.role}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default Sidebar
