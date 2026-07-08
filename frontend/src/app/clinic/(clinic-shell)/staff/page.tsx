'use client'

import * as React from 'react'
import { UserPlus, Users, Mail, Copy } from 'lucide-react'
import {
  PageHeader,
  Card,
  Badge,
  Button,
  Modal,
  useModal,
  FormField,
  Input,
  Checkbox,
  Tabs,
  TabsContent,
  CardSkeleton,
  EmptyState,
  ErrorState,
  Select,
} from '@/design-system'
import { toPageError, type PageError } from '@/lib/api/client'
import {
  createInvitation,
  listInvitations,
  listMembers,
  revokeInvitation,
  updateMember,
  type ClinicInvitationOut,
  type ClinicMembershipOut,
  type ClinicRole,
} from '@/lib/api/clinics'
import { useClinic } from '@/lib/clinic/ClinicContext'

const ROLE_LABEL: Record<ClinicRole, string> = {
  owner: 'Chủ phòng khám',
  admin: 'Quản trị viên',
  doctor: 'Bác sĩ',
  nurse: 'Điều dưỡng',
  receptionist: 'Lễ tân',
  care_coordinator: 'Điều phối chăm sóc',
  accountant: 'Kế toán',
}

// Owner is granted only at clinic creation (create_clinic), never via
// invitation — ClinicInvitationCreate accepts any ClinicRole per its schema,
// but inviting a second Owner has no supported acceptance/ownership-transfer
// flow in this backend contract, so it's excluded from the invite picker.
const INVITABLE_ROLES: ClinicRole[] = [
  'admin',
  'doctor',
  'nurse',
  'receptionist',
  'care_coordinator',
  'accountant',
]

const MEMBER_STATUS_LABEL: Record<string, string> = {
  invited: 'Đã mời',
  active: 'Đang hoạt động',
  suspended: 'Tạm ngừng',
  removed: 'Đã xóa',
}

const INVITATION_STATUS_LABEL: Record<string, string> = {
  pending: 'Đang chờ',
  accepted: 'Đã chấp nhận',
  revoked: 'Đã thu hồi',
  expired: 'Hết hạn',
}

// ---------------------------------------------------------------------------
// Member card
// ---------------------------------------------------------------------------

interface MemberCardProps {
  member: ClinicMembershipOut
  onEdit: (member: ClinicMembershipOut) => void
}

function MemberCard({ member, onEdit }: MemberCardProps) {
  return (
    <Card variant="default" padding="md">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-body-sm font-semibold text-text">{member.user_id}</p>
          <div className="mt-1 flex flex-wrap gap-1">
            {member.roles.map((role) => (
              <Badge key={role} variant="default" size="sm">
                {ROLE_LABEL[role] ?? role}
              </Badge>
            ))}
          </div>
        </div>
        <Badge variant={member.status === 'active' ? 'success' : 'warning'} size="sm">
          {MEMBER_STATUS_LABEL[member.status] ?? member.status}
        </Badge>
      </div>
      <div className="mt-3">
        <Button size="sm" variant="secondary" onClick={() => onEdit(member)}>
          Sửa vai trò
        </Button>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Edit-member modal — role + status
// ---------------------------------------------------------------------------

interface EditMemberModalProps {
  member: ClinicMembershipOut | null
  onClose: () => void
  onSaved: () => void
  clinicId: string
}

function EditMemberModal({ member, onClose, onSaved, clinicId }: EditMemberModalProps) {
  const [roles, setRoles] = React.useState<ClinicRole[]>(member?.roles ?? [])
  const [status, setStatus] = React.useState(member?.status ?? 'active')
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<PageError | null>(null)

  React.useEffect(() => {
    setRoles(member?.roles ?? [])
    setStatus(member?.status ?? 'active')
    setError(null)
  }, [member])

  const toggleRole = (role: ClinicRole) => {
    setRoles((prev) => (prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!member) return
    if (roles.length === 0) {
      setError({ message: 'Cần chọn ít nhất một vai trò.' })
      return
    }
    setSaving(true)
    setError(null)
    try {
      await updateMember(clinicId, member.id, { roles, status })
      onSaved()
      onClose()
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={!!member}
      onOpenChange={(open) => !open && onClose()}
      title="Sửa vai trò thành viên"
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {error && <p className="text-body-xs text-danger">{error.message}</p>}
        <FormField label="Vai trò" required>
          <div className="flex flex-col gap-2">
            {INVITABLE_ROLES.concat('owner').map((role) => (
              <Checkbox
                key={role}
                label={ROLE_LABEL[role]}
                checked={roles.includes(role)}
                onCheckedChange={() => toggleRole(role)}
              />
            ))}
          </div>
        </FormField>
        <FormField label="Trạng thái">
          <Select
            value={status}
            onValueChange={(v) => setStatus(v as ClinicMembershipOut['status'])}
            options={[
              { value: 'active', label: 'Đang hoạt động' },
              { value: 'suspended', label: 'Tạm ngừng' },
              { value: 'removed', label: 'Đã xóa' },
            ]}
            fullWidth
          />
        </FormField>
        <Button type="submit" loading={saving} fullWidth>
          Lưu thay đổi
        </Button>
      </form>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Invite modal
// ---------------------------------------------------------------------------

interface InviteModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onInvited: () => void
  clinicId: string
}

function InviteModal({ open, onOpenChange, onInvited, clinicId }: InviteModalProps) {
  const [email, setEmail] = React.useState('')
  const [phone, setPhone] = React.useState('')
  const [roles, setRoles] = React.useState<ClinicRole[]>([])
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<PageError | null>(null)
  const [rawToken, setRawToken] = React.useState<string | null>(null)

  const toggleRole = (role: ClinicRole) => {
    setRoles((prev) => (prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]))
  }

  const reset = () => {
    setEmail('')
    setPhone('')
    setRoles([])
    setError(null)
    setRawToken(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (roles.length === 0) {
      setError({ message: 'Cần chọn ít nhất một vai trò.' })
      return
    }
    if (!email && !phone) {
      setError({ message: 'Cần nhập email hoặc số điện thoại người được mời.' })
      return
    }
    setSaving(true)
    setError(null)
    try {
      const invitation = await createInvitation(clinicId, {
        roles,
        invited_email: email || null,
        invited_phone: phone || null,
      })
      setRawToken(invitation.raw_token)
      onInvited()
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={(next) => {
        if (!next) reset()
        onOpenChange(next)
      }}
      title="Mời thành viên mới"
    >
      {rawToken ? (
        <div className="flex flex-col gap-3">
          <p className="text-body-sm text-text">
            Đã tạo lời mời. Mã mời chỉ hiển thị một lần — hãy gửi cho người được mời ngay:
          </p>
          <div className="flex items-center gap-2 rounded-md border border-border bg-secondary-50 px-3 py-2">
            <code className="flex-1 truncate text-body-xs">{rawToken}</code>
            <button
              type="button"
              aria-label="Sao chép mã mời"
              onClick={() => void navigator.clipboard.writeText(rawToken)}
              className="shrink-0 rounded p-1.5 text-text-muted hover:bg-secondary-100"
            >
              <Copy className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          <Button
            onClick={() => {
              reset()
              onOpenChange(false)
            }}
            fullWidth
          >
            Đóng
          </Button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {error && <p className="text-body-xs text-danger">{error.message}</p>}
          <FormField label="Email">
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </FormField>
          <FormField label="Số điện thoại" hint="Nhập email hoặc số điện thoại">
            <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
          </FormField>
          <FormField label="Vai trò" required>
            <div className="flex flex-col gap-2">
              {INVITABLE_ROLES.map((role) => (
                <Checkbox
                  key={role}
                  label={ROLE_LABEL[role]}
                  checked={roles.includes(role)}
                  onCheckedChange={() => toggleRole(role)}
                />
              ))}
            </div>
          </FormField>
          <Button type="submit" loading={saving} fullWidth>
            Gửi lời mời
          </Button>
        </form>
      )}
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Invitation card
// ---------------------------------------------------------------------------

function InvitationCard({
  invitation,
  onRevoke,
  busy,
}: {
  invitation: ClinicInvitationOut
  onRevoke: (invitation: ClinicInvitationOut) => void
  busy: boolean
}) {
  return (
    <Card variant="default" padding="md">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 truncate text-body-sm font-semibold text-text">
            <Mail className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {invitation.invited_email ?? invitation.invited_phone ?? '—'}
          </p>
          <div className="mt-1 flex flex-wrap gap-1">
            {invitation.roles.map((role) => (
              <Badge key={role} variant="default" size="sm">
                {ROLE_LABEL[role as ClinicRole] ?? role}
              </Badge>
            ))}
          </div>
        </div>
        <Badge variant={invitation.status === 'pending' ? 'warning' : 'default'} size="sm">
          {INVITATION_STATUS_LABEL[invitation.status] ?? invitation.status}
        </Badge>
      </div>
      {invitation.status === 'pending' && (
        <div className="mt-3">
          <Button size="sm" variant="danger" loading={busy} onClick={() => onRevoke(invitation)}>
            Thu hồi lời mời
          </Button>
        </div>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ClinicStaffPage() {
  const { clinic, capabilities } = useClinic()
  const inviteModal = useModal()
  const [tab, setTab] = React.useState('members')

  const [members, setMembers] = React.useState<ClinicMembershipOut[]>([])
  const [invitations, setInvitations] = React.useState<ClinicInvitationOut[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<PageError | null>(null)
  const [editingMember, setEditingMember] = React.useState<ClinicMembershipOut | null>(null)
  const [busyInvitationId, setBusyInvitationId] = React.useState<string | null>(null)

  const load = React.useCallback(async () => {
    if (!clinic) return
    setLoading(true)
    setError(null)
    try {
      const [membersData, invitationsData] = await Promise.all([
        listMembers(clinic.id, { limit: 200 }),
        listInvitations(clinic.id, { limit: 200 }),
      ])
      setMembers(membersData.items)
      setInvitations(invitationsData.items)
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setLoading(false)
    }
  }, [clinic])

  React.useEffect(() => {
    void load()
  }, [load])

  if (!capabilities.canViewStaff) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center px-4">
        <EmptyState
          title="Không có quyền truy cập"
          description="Chỉ Chủ phòng khám hoặc Quản trị viên phòng khám mới có thể quản lý nhân sự."
          size="md"
        />
      </div>
    )
  }

  if (!clinic) return null

  const handleRevoke = async (invitation: ClinicInvitationOut) => {
    setBusyInvitationId(invitation.id)
    try {
      await revokeInvitation(clinic.id, invitation.id)
      await load()
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setBusyInvitationId(null)
    }
  }

  return (
    <div className="px-4 py-6 sm:px-6">
      <PageHeader
        title="Nhân sự"
        actions={
          <Button leftIcon={<UserPlus className="h-4 w-4" />} {...inviteModal.triggerProps}>
            Mời thành viên
          </Button>
        }
      />

      <Tabs
        value={tab}
        onValueChange={setTab}
        tabs={[
          { value: 'members', label: 'Thành viên', badge: members.length || undefined },
          { value: 'invitations', label: 'Lời mời', badge: invitations.length || undefined },
        ]}
      >
        <TabsContent value="members" className="pt-4">
          {loading ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <CardSkeleton key={i} lines={2} />
              ))}
            </div>
          ) : error ? (
            <ErrorState
              variant="card"
              title={error.title}
              code={error.code}
              message={error.message}
              onRetry={() => void load()}
            />
          ) : members.length === 0 ? (
            <EmptyState
              icon={<Users />}
              title="Chưa có thành viên"
              description="Mời thành viên để bắt đầu."
              size="md"
            />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {members.map((member) => (
                <MemberCard key={member.id} member={member} onEdit={setEditingMember} />
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="invitations" className="pt-4">
          {loading ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <CardSkeleton key={i} lines={2} />
              ))}
            </div>
          ) : invitations.length === 0 ? (
            <EmptyState
              icon={<Mail />}
              title="Chưa có lời mời"
              description="Chưa có lời mời nào được gửi."
              size="md"
            />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {invitations.map((invitation) => (
                <InvitationCard
                  key={invitation.id}
                  invitation={invitation}
                  onRevoke={(inv) => void handleRevoke(inv)}
                  busy={busyInvitationId === invitation.id}
                />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      <EditMemberModal
        member={editingMember}
        onClose={() => setEditingMember(null)}
        onSaved={() => void load()}
        clinicId={clinic.id}
      />
      <InviteModal {...inviteModal.modalProps} clinicId={clinic.id} onInvited={() => void load()} />
    </div>
  )
}
