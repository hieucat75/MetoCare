'use client'

import * as React from 'react'
import {
  Heart,
  Search,
  Plus,
  ArrowRight,
  Download,
  Trash2,
  Edit3,
  Mail,
} from 'lucide-react'

// ---- Tokens ----
import { COLORS, TYPOGRAPHY } from '@/design-system'

// ---- Core Components ----
import Button from '@/design-system/components/core/Button'
import Badge from '@/design-system/components/core/Badge'
import {
  Input,
  PasswordInput,
} from '@/design-system/components/core/Input'
import { Textarea } from '@/design-system/components/core/Textarea'
import { Select } from '@/design-system/components/core/Select'
import { Checkbox } from '@/design-system/components/core/Checkbox'
import { RadioGroup } from '@/design-system/components/core/Radio'
import { Switch } from '@/design-system/components/core/Switch'
import { FormField } from '@/design-system/components/core/FormField'
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from '@/design-system/components/core/Card'
import { Alert } from '@/design-system/components/core/Alert'

// ---- Layout Components ----
import { TopNav } from '@/design-system/components/layout/TopNav'

// ---- Healthcare Components ----
import { PatientMetricCard } from '@/design-system/components/healthcare/PatientMetricCard'
import { RiskLevelBadge } from '@/design-system/components/healthcare/RiskLevelBadge'
import { DoctorReviewQueueItem } from '@/design-system/components/healthcare/DoctorReviewQueueItem'
import { TimelineItem, type TimelineEvent } from '@/design-system/components/healthcare/TimelineItem'
import { CarePlanCard } from '@/design-system/components/healthcare/CarePlanCard'
import { ConsentStatusCard } from '@/design-system/components/healthcare/ConsentStatusCard'
import { AISessionCard } from '@/design-system/components/healthcare/AISessionCard'
import { ReviewDecisionPanel } from '@/design-system/components/healthcare/ReviewDecisionPanel'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

const SECTIONS = [
  { id: 'tokens', label: 'Tokens' },
  { id: 'typography', label: 'Typography' },
  { id: 'buttons', label: 'Buttons' },
  { id: 'badges', label: 'Badges' },
  { id: 'forms', label: 'Form Inputs' },
  { id: 'cards', label: 'Cards' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'healthcare', label: 'Healthcare' },
] as const

// ---------------------------------------------------------------------------
// Section wrapper
// ---------------------------------------------------------------------------

function Section({
  id,
  title,
  children,
}: {
  id: string
  title: string
  children: React.ReactNode
}) {
  return (
    <section id={id} className="scroll-mt-20">
      <div className="mb-6 border-b border-border pb-3">
        <h2 className="text-display-xs font-bold text-text">{title}</h2>
      </div>
      {children}
    </section>
  )
}

function SubSection({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="mb-8">
      <h3 className="text-heading-lg font-semibold text-text mb-4">{title}</h3>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Color Tokens Section
// ---------------------------------------------------------------------------

function ColorSwatch({
  color,
  label,
  textColor = 'text-white',
}: {
  color: string
  label: string
  textColor?: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <div
        className={`h-12 w-full rounded-md border border-black/5 shadow-xs`}
        style={{ backgroundColor: color }}
      />
      <p className="text-caption font-medium text-text">{label}</p>
      <p className="text-caption-sm text-text-muted font-mono">{color}</p>
    </div>
  )
}

function ColorTokensSection() {
  const primaryShades = [
    { shade: '50', value: COLORS.primary[50] },
    { shade: '100', value: COLORS.primary[100] },
    { shade: '200', value: COLORS.primary[200] },
    { shade: '300', value: COLORS.primary[300] },
    { shade: '400', value: COLORS.primary[400] },
    { shade: '500', value: COLORS.primary[500] },
    { shade: '600', value: COLORS.primary[600] },
    { shade: '700', value: COLORS.primary[700] },
    { shade: '800', value: COLORS.primary[800] },
    { shade: '900', value: COLORS.primary[900] },
    { shade: '950', value: COLORS.primary[950] },
  ]

  const semanticColors = [
    { label: 'Success', value: COLORS.success.DEFAULT },
    { label: 'Success Light', value: COLORS.success.light },
    { label: 'Warning', value: COLORS.warning.DEFAULT },
    { label: 'Warning Light', value: COLORS.warning.light },
    { label: 'Danger', value: COLORS.danger.DEFAULT },
    { label: 'Danger Light', value: COLORS.danger.light },
    { label: 'Info', value: COLORS.info.DEFAULT },
    { label: 'Info Light', value: COLORS.info.light },
    { label: 'Accent', value: COLORS.accent.DEFAULT },
    { label: 'Accent Light', value: COLORS.accent.light },
  ]

  const secondaryShades = [
    { shade: '50', value: COLORS.secondary[50] },
    { shade: '100', value: COLORS.secondary[100] },
    { shade: '200', value: COLORS.secondary[200] },
    { shade: '300', value: COLORS.secondary[300] },
    { shade: '400', value: COLORS.secondary[400] },
    { shade: '500', value: COLORS.secondary[500] },
    { shade: '600', value: COLORS.secondary[600] },
    { shade: '700', value: COLORS.secondary[700] },
    { shade: '800', value: COLORS.secondary[800] },
    { shade: '900', value: COLORS.secondary[900] },
  ]

  const clinicalStatusColors = [
    {
      label: 'Chờ xét duyệt',
      bg: COLORS.clinical.pendingReviewLight,
      border: COLORS.clinical.pendingReviewBorder,
      text: COLORS.clinical.pendingReview,
    },
    {
      label: 'Đã duyệt',
      bg: COLORS.clinical.approvedLight,
      border: COLORS.clinical.approvedBorder,
      text: COLORS.clinical.approved,
    },
    {
      label: 'Từ chối',
      bg: COLORS.clinical.rejectedLight,
      border: COLORS.clinical.rejectedBorder,
      text: COLORS.clinical.rejected,
    },
    {
      label: 'Yêu cầu thêm thông tin',
      bg: COLORS.clinical.requestInfoLight,
      border: COLORS.clinical.requestInfoBorder,
      text: COLORS.clinical.requestInfo,
    },
    {
      label: 'Đang hoạt động',
      bg: COLORS.clinical.activeLight,
      border: COLORS.clinical.activeBorder,
      text: COLORS.clinical.active,
    },
    {
      label: 'Đã thu hồi',
      bg: COLORS.clinical.revokedLight,
      border: COLORS.clinical.revokedBorder,
      text: COLORS.clinical.revoked,
    },
  ]

  const riskColors = [
    {
      label: 'Nguy cơ cao',
      bg: COLORS.clinical.highRiskLight,
      border: COLORS.clinical.highRiskBorder,
      text: COLORS.clinical.highRisk,
    },
    {
      label: 'Nguy cơ trung bình',
      bg: COLORS.clinical.mediumRiskLight,
      border: COLORS.clinical.mediumRiskBorder,
      text: COLORS.clinical.mediumRisk,
    },
    {
      label: 'Nguy cơ thấp',
      bg: COLORS.clinical.lowRiskLight,
      border: COLORS.clinical.lowRiskBorder,
      text: COLORS.clinical.lowRisk,
    },
  ]

  return (
    <Section id="tokens" title="Color Tokens">
      <SubSection title="Primary — Medical Blue">
        <div className="grid grid-cols-5 sm:grid-cols-11 gap-3">
          {primaryShades.map(({ shade, value }) => (
            <ColorSwatch key={shade} color={value} label={shade} />
          ))}
        </div>
      </SubSection>

      <SubSection title="Secondary — Slate Neutral">
        <div className="grid grid-cols-5 sm:grid-cols-10 gap-3">
          {secondaryShades.map(({ shade, value }) => (
            <ColorSwatch key={shade} color={value} label={shade} />
          ))}
        </div>
      </SubSection>

      <SubSection title="Semantic Colors">
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {semanticColors.map(({ label, value }) => (
            <ColorSwatch key={label} color={value} label={label} />
          ))}
        </div>
      </SubSection>

      <SubSection title="Clinical Status Colors">
        <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {clinicalStatusColors.map(({ label, bg, border, text }) => (
            <div key={label} className="flex flex-col gap-2">
              <div
                className="h-14 rounded-md border flex items-center justify-center"
                style={{ backgroundColor: bg, borderColor: border }}
              >
                <span
                  className="text-caption font-semibold px-2 text-center"
                  style={{ color: text }}
                >
                  {label}
                </span>
              </div>
              <div className="flex gap-1">
                <div
                  className="h-4 w-4 rounded-sm border border-black/10"
                  style={{ backgroundColor: bg }}
                  title="Light"
                />
                <div
                  className="h-4 w-4 rounded-sm border border-black/10"
                  style={{ backgroundColor: border }}
                  title="Border"
                />
                <div
                  className="h-4 w-4 rounded-sm border border-black/10"
                  style={{ backgroundColor: text }}
                  title="Text"
                />
              </div>
              <p className="text-caption-sm text-text-muted">{label}</p>
            </div>
          ))}
        </div>
      </SubSection>

      <SubSection title="Risk Level Colors">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {riskColors.map(({ label, bg, border, text }) => (
            <div
              key={label}
              className="rounded-lg border p-4 flex items-center gap-3"
              style={{ backgroundColor: bg, borderColor: border }}
            >
              <div
                className="h-8 w-8 rounded-full border-2 flex items-center justify-center shrink-0"
                style={{ borderColor: text, backgroundColor: 'rgba(255,255,255,0.6)' }}
              >
                <div className="h-3 w-3 rounded-full" style={{ backgroundColor: text }} />
              </div>
              <div>
                <p className="text-body-sm font-semibold" style={{ color: text }}>
                  {label}
                </p>
                <p className="text-caption-sm text-text-muted font-mono">{text}</p>
              </div>
            </div>
          ))}
        </div>
      </SubSection>

      <SubSection title="Surface Tokens">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <ColorSwatch color={COLORS.background} label="Background" />
          <ColorSwatch color={COLORS.surface} label="Surface" />
          <ColorSwatch color={COLORS.border} label="Border" />
          <ColorSwatch color={COLORS.text.DEFAULT} label="Text Default" />
          <ColorSwatch color={COLORS.text.muted} label="Text Muted" />
          <ColorSwatch color={COLORS.text.subtle} label="Text Subtle" />
          <ColorSwatch color={COLORS.text.disabled} label="Text Disabled" />
        </div>
      </SubSection>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// Typography Section
// ---------------------------------------------------------------------------

const SAMPLE_TEXT = 'Sức khỏe của bạn là ưu tiên hàng đầu'

function TypographySection() {
  const typographyRows = [
    { key: 'display-2xl', size: TYPOGRAPHY.fontSize['display-2xl'], lh: TYPOGRAPHY.lineHeight['display-2xl'], weight: 'font-bold', label: 'display-2xl' },
    { key: 'display-xl', size: TYPOGRAPHY.fontSize['display-xl'], lh: TYPOGRAPHY.lineHeight['display-xl'], weight: 'font-bold', label: 'display-xl' },
    { key: 'display-lg', size: TYPOGRAPHY.fontSize['display-lg'], lh: TYPOGRAPHY.lineHeight['display-lg'], weight: 'font-bold', label: 'display-lg' },
    { key: 'display-md', size: TYPOGRAPHY.fontSize['display-md'], lh: TYPOGRAPHY.lineHeight['display-md'], weight: 'font-bold', label: 'display-md' },
    { key: 'display-sm', size: TYPOGRAPHY.fontSize['display-sm'], lh: TYPOGRAPHY.lineHeight['display-sm'], weight: 'font-semibold', label: 'display-sm' },
    { key: 'display-xs', size: TYPOGRAPHY.fontSize['display-xs'], lh: TYPOGRAPHY.lineHeight['display-xs'], weight: 'font-semibold', label: 'display-xs' },
    { key: 'heading-xl', size: TYPOGRAPHY.fontSize['heading-xl'], lh: TYPOGRAPHY.lineHeight['heading-xl'], weight: 'font-semibold', label: 'heading-xl' },
    { key: 'heading-lg', size: TYPOGRAPHY.fontSize['heading-lg'], lh: TYPOGRAPHY.lineHeight['heading-lg'], weight: 'font-semibold', label: 'heading-lg' },
    { key: 'heading-md', size: TYPOGRAPHY.fontSize['heading-md'], lh: TYPOGRAPHY.lineHeight['heading-md'], weight: 'font-medium', label: 'heading-md' },
    { key: 'heading-sm', size: TYPOGRAPHY.fontSize['heading-sm'], lh: TYPOGRAPHY.lineHeight['heading-sm'], weight: 'font-medium', label: 'heading-sm' },
    { key: 'body-xl', size: TYPOGRAPHY.fontSize['body-xl'], lh: TYPOGRAPHY.lineHeight['body-xl'], weight: 'font-normal', label: 'body-xl' },
    { key: 'body-lg', size: TYPOGRAPHY.fontSize['body-lg'], lh: TYPOGRAPHY.lineHeight['body-lg'], weight: 'font-normal', label: 'body-lg' },
    { key: 'body-md', size: TYPOGRAPHY.fontSize['body-md'], lh: TYPOGRAPHY.lineHeight['body-md'], weight: 'font-normal', label: 'body-md' },
    { key: 'body-sm', size: TYPOGRAPHY.fontSize['body-sm'], lh: TYPOGRAPHY.lineHeight['body-sm'], weight: 'font-normal', label: 'body-sm' },
    { key: 'body-xs', size: TYPOGRAPHY.fontSize['body-xs'], lh: TYPOGRAPHY.lineHeight['body-xs'], weight: 'font-normal', label: 'body-xs' },
    { key: 'label-lg', size: TYPOGRAPHY.fontSize['label-lg'], lh: TYPOGRAPHY.lineHeight['label-lg'], weight: 'font-medium', label: 'label-lg' },
    { key: 'label-md', size: TYPOGRAPHY.fontSize['label-md'], lh: TYPOGRAPHY.lineHeight['label-md'], weight: 'font-medium', label: 'label-md' },
    { key: 'label-sm', size: TYPOGRAPHY.fontSize['label-sm'], lh: TYPOGRAPHY.lineHeight['label-sm'], weight: 'font-medium', label: 'label-sm' },
    { key: 'caption', size: TYPOGRAPHY.fontSize['caption'], lh: TYPOGRAPHY.lineHeight['caption'], weight: 'font-normal', label: 'caption' },
    { key: 'caption-sm', size: TYPOGRAPHY.fontSize['caption-sm'], lh: TYPOGRAPHY.lineHeight['caption-sm'], weight: 'font-normal', label: 'caption-sm' },
  ] as const

  return (
    <Section id="typography" title="Typography Scale">
      <div className="bg-surface border border-border rounded-lg overflow-hidden divide-y divide-border">
        {typographyRows.map(({ key, size, lh, weight, label }) => (
          <div key={key} className="flex items-baseline gap-4 px-6 py-4 hover:bg-background transition-colors">
            <div className="w-28 shrink-0">
              <code className="text-caption font-mono bg-secondary-100 px-1.5 py-0.5 rounded text-primary-700">
                {label}
              </code>
            </div>
            <div className="w-20 shrink-0 text-caption text-text-muted font-mono">{size}</div>
            <p
              className={`flex-1 text-text truncate ${weight}`}
              style={{ fontSize: size, lineHeight: lh }}
            >
              {SAMPLE_TEXT}
            </p>
          </div>
        ))}
      </div>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// Buttons Section
// ---------------------------------------------------------------------------

function ButtonsSection() {
  return (
    <Section id="buttons" title="Buttons">
      <SubSection title="Variants">
        <div className="flex flex-wrap gap-3 items-center">
          <Button variant="primary">Chính</Button>
          <Button variant="secondary">Phụ</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="outline">Viền</Button>
          <Button variant="danger">Nguy hiểm</Button>
          <Button variant="link">Liên kết</Button>
        </div>
      </SubSection>

      <SubSection title="Sizes">
        <div className="flex flex-wrap gap-3 items-center">
          <Button variant="primary" size="xs">Cỡ XS</Button>
          <Button variant="primary" size="sm">Cỡ SM</Button>
          <Button variant="primary" size="md">Cỡ MD</Button>
          <Button variant="primary" size="lg">Cỡ LG</Button>
        </div>
      </SubSection>

      <SubSection title="States">
        <div className="flex flex-wrap gap-3 items-center">
          <Button variant="primary" loading>Đang tải...</Button>
          <Button variant="primary" disabled>Vô hiệu hoá</Button>
          <Button variant="secondary" loading>Xử lý...</Button>
          <Button variant="danger" disabled>Xoá (bị khoá)</Button>
        </div>
      </SubSection>

      <SubSection title="With Icons">
        <div className="flex flex-wrap gap-3 items-center">
          <Button variant="primary" leftIcon={<Plus className="h-4 w-4" />}>
            Thêm bệnh nhân
          </Button>
          <Button variant="outline" leftIcon={<Search className="h-4 w-4" />}>
            Tìm kiếm
          </Button>
          <Button variant="secondary" rightIcon={<ArrowRight className="h-4 w-4" />}>
            Xem chi tiết
          </Button>
          <Button variant="ghost" leftIcon={<Download className="h-4 w-4" />}>
            Tải xuống báo cáo
          </Button>
          <Button variant="danger" leftIcon={<Trash2 className="h-4 w-4" />} size="sm">
            Xoá hồ sơ
          </Button>
          <Button variant="outline" leftIcon={<Edit3 className="h-4 w-4" />} size="sm">
            Chỉnh sửa
          </Button>
        </div>
      </SubSection>

      <SubSection title="Full Width">
        <div className="max-w-sm flex flex-col gap-3">
          <Button variant="primary" fullWidth>Đăng nhập vào hệ thống</Button>
          <Button variant="outline" fullWidth>Tạo tài khoản mới</Button>
        </div>
      </SubSection>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// Badges Section
// ---------------------------------------------------------------------------

function BadgesSection() {
  const semanticBadges: Array<{ variant: Parameters<typeof Badge>[0]['variant']; label: string }> = [
    { variant: 'default', label: 'Mặc định' },
    { variant: 'primary', label: 'Chính' },
    { variant: 'success', label: 'Thành công' },
    { variant: 'warning', label: 'Cảnh báo' },
    { variant: 'danger', label: 'Nguy hiểm' },
    { variant: 'info', label: 'Thông tin' },
  ]

  const clinicalBadges: Array<{ variant: Parameters<typeof Badge>[0]['variant'] }> = [
    { variant: 'pending_review' },
    { variant: 'approved' },
    { variant: 'rejected' },
    { variant: 'request_info' },
    { variant: 'active' },
    { variant: 'revoked' },
  ]

  const riskBadges: Array<{ variant: Parameters<typeof Badge>[0]['variant'] }> = [
    { variant: 'high_risk' },
    { variant: 'medium_risk' },
    { variant: 'low_risk' },
  ]

  return (
    <Section id="badges" title="Badges">
      <SubSection title="Semantic Variants — MD size">
        <div className="flex flex-wrap gap-3 items-center">
          {semanticBadges.map(({ variant, label }) => (
            <Badge key={String(variant)} variant={variant} dot>
              {label}
            </Badge>
          ))}
        </div>
      </SubSection>

      <SubSection title="Clinical Workflow Status — with dot">
        <div className="flex flex-wrap gap-3 items-center">
          {clinicalBadges.map(({ variant }) => (
            <Badge key={String(variant)} variant={variant} dot />
          ))}
        </div>
      </SubSection>

      <SubSection title="Risk Levels">
        <div className="flex flex-wrap gap-3 items-center">
          {riskBadges.map(({ variant }) => (
            <Badge key={String(variant)} variant={variant} dot />
          ))}
        </div>
      </SubSection>

      <SubSection title="Sizes">
        <div className="flex flex-wrap gap-4 items-center">
          <div className="flex flex-wrap gap-2 items-center">
            <span className="text-caption text-text-muted w-6">SM</span>
            {semanticBadges.map(({ variant, label }) => (
              <Badge key={String(variant)} variant={variant} size="sm">
                {label}
              </Badge>
            ))}
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <span className="text-caption text-text-muted w-6">MD</span>
            {semanticBadges.map(({ variant, label }) => (
              <Badge key={String(variant)} variant={variant} size="md">
                {label}
              </Badge>
            ))}
          </div>
        </div>
      </SubSection>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// Form Inputs Section
// ---------------------------------------------------------------------------

function FormsSection() {
  const [checkboxChecked, setCheckboxChecked] = React.useState<boolean | 'indeterminate'>(true)
  const [switchOn, setSwitchOn] = React.useState(true)
  const [radioValue, setRadioValue] = React.useState('bac_si')
  const [selectValue, setSelectValue] = React.useState('')

  return (
    <Section id="forms" title="Form Inputs">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Text Inputs */}
        <SubSection title="Text Input">
          <div className="flex flex-col gap-5">
            <Input
              label="Họ và tên"
              placeholder="Nguyễn Văn An"
              fullWidth
            />
            <Input
              label="Email"
              placeholder="bacsi@metocare.vn"
              leftIcon={<Mail className="h-4 w-4" />}
              hint="Dùng địa chỉ email bệnh viện của bạn"
              fullWidth
            />
            <Input
              label="Số điện thoại"
              placeholder="0912 345 678"
              error="Số điện thoại không hợp lệ"
              fullWidth
            />
            <Input
              label="Ngày sinh"
              placeholder="dd/mm/yyyy"
              disabled
              value="15/06/1985"
              fullWidth
            />
          </div>
        </SubSection>

        {/* Password Input */}
        <SubSection title="Password Input">
          <div className="flex flex-col gap-5">
            <PasswordInput
              label="Mật khẩu"
              placeholder="Nhập mật khẩu..."
              hint="Tối thiểu 8 ký tự, bao gồm chữ hoa và số"
              fullWidth
            />
            <PasswordInput
              label="Xác nhận mật khẩu"
              placeholder="Nhập lại mật khẩu..."
              error="Mật khẩu không trùng khớp"
              fullWidth
            />
          </div>
        </SubSection>

        {/* Textarea */}
        <SubSection title="Textarea">
          <div className="flex flex-col gap-5">
            <Textarea
              label="Ghi chú lâm sàng"
              placeholder="Nhập ghi chú về tình trạng bệnh nhân..."
              rows={4}
              fullWidth
            />
            <Textarea
              label="Hướng dẫn điều trị"
              placeholder="Nhập hướng dẫn..."
              error="Trường này là bắt buộc"
              rows={3}
              fullWidth
            />
            <Textarea
              label="Mô tả triệu chứng"
              placeholder="Mô tả triệu chứng (tối đa 300 ký tự)..."
              maxLength={300}
              showCount
              rows={3}
              fullWidth
            />
          </div>
        </SubSection>

        {/* Select */}
        <SubSection title="Select">
          <div className="flex flex-col gap-5">
            <Select
              label="Chuyên khoa"
              placeholder="Chọn chuyên khoa..."
              value={selectValue}
              onValueChange={setSelectValue}
              options={[
                { value: 'tim_mach', label: 'Tim mạch' },
                { value: 'noi_tiet', label: 'Nội tiết' },
                { value: 'than_kinh', label: 'Thần kinh' },
                { value: 'nhi_khoa', label: 'Nhi khoa' },
                { value: 'phu_khoa', label: 'Phụ khoa' },
              ]}
              fullWidth
            />
            <Select
              label="Mức độ ưu tiên"
              placeholder="Chọn mức độ..."
              options={[
                { value: 'khan_cap', label: 'Khẩn cấp' },
                { value: 'cao', label: 'Cao' },
                { value: 'binh_thuong', label: 'Bình thường' },
                { value: 'thap', label: 'Thấp' },
              ]}
              error="Vui lòng chọn mức độ ưu tiên"
              fullWidth
            />
          </div>
        </SubSection>

        {/* Checkbox */}
        <SubSection title="Checkbox">
          <div className="flex flex-col gap-4">
            <Checkbox
              label="Tôi đồng ý với điều khoản sử dụng"
              description="Vui lòng đọc kỹ điều khoản trước khi đồng ý"
              checked={checkboxChecked}
              onCheckedChange={setCheckboxChecked}
            />
            <Checkbox
              label="Nhận thông báo về kết quả xét nghiệm"
              checked={true}
            />
            <Checkbox
              label="Lưu thông tin đăng nhập"
              checked={false}
            />
            <Checkbox
              label="Tính năng thử nghiệm (bị vô hiệu hoá)"
              disabled
              checked={false}
            />
            <Checkbox
              label="Điều khoản bắt buộc"
              error="Bạn phải đồng ý để tiếp tục"
              checked={false}
            />
          </div>
        </SubSection>

        {/* Radio */}
        <SubSection title="Radio Group">
          <div className="flex flex-col gap-5">
            <RadioGroup
              label="Vai trò người dùng"
              value={radioValue}
              onValueChange={setRadioValue}
              options={[
                { value: 'benh_nhan', label: 'Bệnh nhân', description: 'Truy cập hồ sơ sức khỏe cá nhân' },
                { value: 'bac_si', label: 'Bác sĩ', description: 'Xem xét và phê duyệt kế hoạch điều trị' },
                { value: 'quan_tri', label: 'Quản trị viên', description: 'Quản lý toàn bộ hệ thống', disabled: true },
              ]}
            />
            <RadioGroup
              label="Hình thức liên lạc"
              value="email"
              options={[
                { value: 'email', label: 'Email' },
                { value: 'sms', label: 'SMS' },
                { value: 'zalo', label: 'Zalo' },
              ]}
              orientation="horizontal"
            />
          </div>
        </SubSection>

        {/* Switch */}
        <SubSection title="Switch">
          <div className="flex flex-col gap-4">
            <Switch
              label="Nhận thông báo đẩy"
              description="Nhận cảnh báo sức khỏe ngay lập tức"
              checked={switchOn}
              onCheckedChange={setSwitchOn}
            />
            <Switch
              label="Chế độ tối"
              checked={false}
            />
            <Switch
              label="Chia sẻ dữ liệu với bác sĩ"
              description="Cho phép bác sĩ của bạn xem dữ liệu sức khoẻ"
              checked={true}
              size="sm"
            />
            <Switch
              label="Tính năng AI (bị khoá)"
              disabled
              checked={false}
            />
          </div>
        </SubSection>

        {/* FormField */}
        <SubSection title="FormField Wrapper">
          <div className="flex flex-col gap-5">
            <FormField
              label="Ngày khám bệnh"
              required
              hint="Định dạng: ngày/tháng/năm"
              htmlFor="visit-date"
            >
              <input
                id="visit-date"
                type="date"
                className="h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-body-sm text-text focus:outline-none focus:ring-2 focus:border-primary focus:ring-primary/20 transition-colors"
              />
            </FormField>
            <FormField
              label="Mã bệnh nhân"
              required
              error="Mã bệnh nhân không tồn tại trong hệ thống"
              htmlFor="patient-code"
            >
              <input
                id="patient-code"
                type="text"
                placeholder="BN-2024-XXXXX"
                className="h-10 w-full rounded-md border border-danger bg-surface px-3 py-2 text-body-sm text-text focus:outline-none focus:ring-2 focus:border-danger focus:ring-danger/20 transition-colors"
              />
            </FormField>
          </div>
        </SubSection>
      </div>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// Cards Section
// ---------------------------------------------------------------------------

function CardsSection() {
  return (
    <Section id="cards" title="Cards">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {/* Default */}
        <div>
          <p className="text-caption text-text-muted mb-2 font-mono">variant=&quot;default&quot;</p>
          <Card variant="default">
            <CardHeader>
              <CardTitle>Hồ sơ bệnh nhân</CardTitle>
              <Badge variant="active" dot size="sm" />
            </CardHeader>
            <CardContent>
              <CardDescription>
                Nguyễn Thị Hoa — Bệnh nhân đái tháo đường type 2. Đang trong
                giai đoạn theo dõi tích cực.
              </CardDescription>
            </CardContent>
            <CardFooter>
              <span className="text-caption text-text-muted">Cập nhật: 15/06/2026</span>
              <Button variant="outline" size="sm">Xem chi tiết</Button>
            </CardFooter>
          </Card>
        </div>

        {/* Outlined */}
        <div>
          <p className="text-caption text-text-muted mb-2 font-mono">variant=&quot;outlined&quot;</p>
          <Card variant="outlined">
            <CardHeader>
              <CardTitle>Kết quả xét nghiệm</CardTitle>
              <Badge variant="pending_review" dot size="sm" />
            </CardHeader>
            <CardContent>
              <CardDescription>
                Glucose: 7.2 mmol/L · HbA1c: 6.8% · Cholesterol: 4.9 mmol/L.
                Kết quả cần được bác sĩ xem xét.
              </CardDescription>
            </CardContent>
            <CardFooter>
              <span className="text-caption text-text-muted">14/06/2026</span>
              <Button variant="primary" size="sm">Xét duyệt</Button>
            </CardFooter>
          </Card>
        </div>

        {/* Elevated */}
        <div>
          <p className="text-caption text-text-muted mb-2 font-mono">variant=&quot;elevated&quot;</p>
          <Card variant="elevated">
            <CardHeader>
              <CardTitle>Kế hoạch chăm sóc</CardTitle>
              <Badge variant="approved" dot size="sm" />
            </CardHeader>
            <CardContent>
              <CardDescription>
                Kế hoạch kiểm soát đường huyết 3 tháng. Đã được bác sĩ Trần
                Minh Tuấn phê duyệt ngày 01/06/2026.
              </CardDescription>
            </CardContent>
            <CardFooter>
              <span className="text-caption text-text-muted">Hiệu lực: 3 tháng</span>
              <Button variant="ghost" size="sm">Chi tiết</Button>
            </CardFooter>
          </Card>
        </div>

        {/* Ghost */}
        <div>
          <p className="text-caption text-text-muted mb-2 font-mono">variant=&quot;ghost&quot;</p>
          <Card variant="ghost">
            <CardHeader>
              <CardTitle>Phiên hỏi đáp AI</CardTitle>
              <Badge variant="info" size="sm">Đang diễn ra</Badge>
            </CardHeader>
            <CardContent>
              <CardDescription>
                Bệnh nhân đang trao đổi về triệu chứng mệt mỏi và chóng mặt
                buổi sáng với trợ lý AI MetoCare.
              </CardDescription>
            </CardContent>
          </Card>
        </div>

        {/* Flat */}
        <div>
          <p className="text-caption text-text-muted mb-2 font-mono">variant=&quot;flat&quot;</p>
          <Card variant="flat">
            <CardHeader>
              <CardTitle>Lịch tái khám</CardTitle>
            </CardHeader>
            <CardContent>
              <CardDescription>
                Tái khám định kỳ: Thứ Hai, 23/06/2026 — 09:00 sáng. Phòng khám
                B3, Khoa Nội tiết.
              </CardDescription>
            </CardContent>
            <CardFooter>
              <span className="text-caption text-text-muted">7 ngày nữa</span>
              <Button variant="secondary" size="sm">Đặt lịch</Button>
            </CardFooter>
          </Card>
        </div>

        {/* Interactive */}
        <div>
          <p className="text-caption text-text-muted mb-2 font-mono">interactive=true</p>
          <Card variant="default" interactive>
            <CardHeader>
              <CardTitle>Đồng thuận dữ liệu</CardTitle>
              <Badge variant="warning" size="sm" dot>Chờ xác nhận</Badge>
            </CardHeader>
            <CardContent>
              <CardDescription>
                Bệnh nhân chưa xác nhận đồng thuận chia sẻ dữ liệu cho nghiên
                cứu lâm sàng. Nhấn để xem chi tiết.
              </CardDescription>
            </CardContent>
          </Card>
        </div>
      </div>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// Alerts Section
// ---------------------------------------------------------------------------

function AlertsSection() {
  return (
    <Section id="alerts" title="Alerts">
      <div className="flex flex-col gap-4">
        <Alert variant="info" title="Thông báo hệ thống">
          Hệ thống sẽ bảo trì từ 22:00 đến 23:00 ngày 20/06/2026. Vui lòng lưu
          lại tất cả dữ liệu trước thời điểm này.
        </Alert>

        <Alert variant="success" title="Kế hoạch đã được duyệt">
          Kế hoạch chăm sóc cho bệnh nhân Nguyễn Văn An đã được Bác sĩ Trần
          Minh Tuấn phê duyệt thành công vào lúc 14:32 hôm nay.
        </Alert>

        <Alert variant="warning" title="Cảnh báo chỉ số bất thường">
          Chỉ số glucose của bệnh nhân Lê Thị Mai đã vượt ngưỡng cảnh báo (12.5
          mmol/L). Cần xem xét và điều chỉnh phác đồ điều trị.
        </Alert>

        <Alert variant="danger" title="Nguy cơ lâm sàng nghiêm trọng">
          Huyết áp bệnh nhân đo được 185/115 mmHg — mức nguy hiểm. Bệnh nhân
          cần được thăm khám khẩn cấp trong vòng 2 giờ tới.
        </Alert>

        <Alert variant="neutral" title="Thông tin bổ sung">
          Hồ sơ bệnh án đã được cập nhật lần cuối lúc 08:15 ngày 19/06/2026
          bởi Điều dưỡng Phạm Thị Hương.
        </Alert>

        <Alert
          variant="warning"
          title="Cảnh báo có thể đóng"
          dismissible
          onDismiss={() => undefined}
        >
          Bệnh nhân chưa cập nhật thông tin liên lạc trong 90 ngày qua. Vui
          lòng xác minh số điện thoại và địa chỉ email.
        </Alert>

        <Alert variant="info">
          Thông báo không có tiêu đề: Kết quả HbA1c mới nhất đã sẵn sàng để
          bác sĩ xem xét.
        </Alert>
      </div>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// Healthcare Components Section
// ---------------------------------------------------------------------------

const MOCK_QUEUE_URGENT = {
  id: 'q-001',
  patientName: 'Nguyễn Văn Bình',
  patientId: 'BN-2024-00123',
  submittedAt: new Date(Date.now() - 25 * 60 * 1000).toISOString(),
  type: 'lab_result' as const,
  priority: 'urgent' as const,
  status: 'pending_review' as const,
  summary: 'Glucose 15.2 mmol/L — vượt ngưỡng nguy hiểm',
}

const MOCK_QUEUE_NORMAL = {
  id: 'q-002',
  patientName: 'Lê Thị Cẩm Tú',
  patientId: 'BN-2024-00456',
  submittedAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
  type: 'care_plan' as const,
  priority: 'normal' as const,
  status: 'completed' as const,
  summary: 'Kế hoạch kiểm soát huyết áp 6 tháng',
}

const MOCK_TIMELINE_EVENTS: TimelineEvent[] = [
  {
    id: 'e-001',
    date: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
    type: 'ai_session',
    title: 'Phiên hỏi đáp AI — Triệu chứng mệt mỏi',
    description:
      'Bệnh nhân mô tả tình trạng mệt mỏi kéo dài, chóng mặt khi đứng dậy đột ngột. AI đề xuất theo dõi huyết áp tư thế.',
    actor: 'Hệ thống AI MetoCare',
    actorRole: 'Trợ lý lâm sàng',
    status: 'Đã chuyển bác sĩ',
    metadata: { 'Chủ đề': 'Mệt mỏi, Huyết áp', 'Cờ đỏ': 'Có' },
  },
  {
    id: 'e-002',
    date: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
    type: 'lab_result',
    title: 'Kết quả xét nghiệm máu định kỳ',
    description:
      'HbA1c: 7.1% (ổn định), Glucose đói: 6.8 mmol/L, Cholesterol toàn phần: 4.7 mmol/L. Kết quả trong giới hạn mục tiêu.',
    actor: 'Phòng xét nghiệm Bệnh viện Chợ Rẫy',
    actorRole: 'Kỹ thuật viên xét nghiệm',
    metadata: { 'HbA1c': '7.1%', 'Glucose': '6.8 mmol/L' },
  },
  {
    id: 'e-003',
    date: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
    type: 'doctor_visit',
    title: 'Tái khám định kỳ tháng 6/2026',
    description:
      'Bác sĩ đánh giá tình trạng kiểm soát đường huyết ổn định. Điều chỉnh liều Metformin từ 500mg xuống 250mg buổi tối.',
    actor: 'BS. Trần Minh Tuấn',
    actorRole: 'Bác sĩ Nội tiết',
    status: 'Hoàn tất',
  },
]

const MOCK_CARE_PLAN = {
  id: 'cp-001',
  title: 'Kế hoạch kiểm soát đái tháo đường type 2',
  status: 'active' as const,
  doctorName: 'BS. Trần Minh Tuấn',
  createdAt: '2026-05-01T08:00:00Z',
  updatedAt: '2026-06-15T10:30:00Z',
  nextReview: '2026-08-01T09:00:00Z',
  goals: [
    { id: 'g-1', description: 'Duy trì HbA1c dưới 7.0%', completed: true },
    { id: 'g-2', description: 'Tập thể dục aerobic 30 phút/ngày, 5 ngày/tuần', completed: true },
    { id: 'g-3', description: 'Giảm cân xuống 68kg (hiện tại: 72kg)', completed: false, targetDate: '2026-09-01' },
    { id: 'g-4', description: 'Kiểm tra huyết áp hàng ngày và ghi nhật ký', completed: false, targetDate: '2026-07-01' },
  ],
  notes:
    'Bệnh nhân tuân thủ điều trị tốt. Cần tăng cường chế độ ăn ít carbohydrate và duy trì uống thuốc đúng giờ.',
}

const MOCK_CONSENTS = [
  {
    id: 'c-001',
    type: 'ai_analysis',
    label: 'Phân tích dữ liệu sức khoẻ bằng AI',
    description: 'Cho phép hệ thống AI phân tích dữ liệu sức khoẻ của bạn để đưa ra gợi ý điều trị cá nhân hóa.',
    status: 'granted' as const,
    grantedAt: '2026-01-15T10:00:00Z',
    expiresAt: '2027-01-15T10:00:00Z',
    grantedTo: 'MetoCare AI Engine',
  },
  {
    id: 'c-002',
    type: 'data_sharing',
    label: 'Chia sẻ dữ liệu với bác sĩ điều trị',
    description: 'Cho phép bác sĩ Trần Minh Tuấn truy cập toàn bộ hồ sơ sức khoẻ của bạn.',
    status: 'granted' as const,
    grantedAt: '2026-02-01T14:00:00Z',
    grantedTo: 'BS. Trần Minh Tuấn',
  },
  {
    id: 'c-003',
    type: 'research',
    label: 'Tham gia nghiên cứu lâm sàng',
    description: 'Cho phép sử dụng dữ liệu ẩn danh của bạn trong các nghiên cứu khoa học.',
    status: 'pending' as const,
  },
  {
    id: 'c-004',
    type: 'marketing',
    label: 'Nhận thông tin tiếp thị',
    description: 'Cho phép gửi email và thông báo về dịch vụ mới của MetoCare.',
    status: 'denied' as const,
  },
]

const MOCK_AI_SESSION = {
  id: 'ai-001',
  sessionDate: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
  summary:
    'Bệnh nhân phản ánh tình trạng mệt mỏi kéo dài 3 ngày, đặc biệt buổi sáng sau khi thức dậy. Có kèm chóng mặt nhẹ khi đứng lên nhanh. Bệnh nhân đang dùng Metformin 500mg x2 và Amlodipine 5mg. Chỉ số huyết áp đo tại nhà hôm nay: 148/92 mmHg.',
  keyTopics: ['Mệt mỏi', 'Chóng mặt tư thế', 'Huyết áp cao', 'Tương tác thuốc'],
  disclaimer:
    'Thông tin trên do trợ lý AI MetoCare cung cấp nhằm mục đích tham khảo. Không thay thế chẩn đoán và lời khuyên của bác sĩ có chuyên môn.',
  hadRedFlag: true,
  escalatedToDoctor: true,
  status: 'escalated' as const,
}

function HealthcareSection() {
  return (
    <Section id="healthcare" title="Healthcare Components">
      {/* Patient Metric Cards */}
      <SubSection title="PatientMetricCard">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
          <PatientMetricCard
            metric="blood_pressure"
            label="Huyết áp"
            value="148/92"
            unit="mmHg"
            trend="up"
            trendValue={12}
            trendLabel="so với tuần trước"
            status="warning"
            lastUpdated={new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString()}
          />
          <PatientMetricCard
            metric="glucose"
            label="Đường huyết đói"
            value="6.2"
            unit="mmol/L"
            trend="stable"
            status="normal"
            lastUpdated={new Date(Date.now() - 8 * 60 * 60 * 1000).toISOString()}
          />
          <PatientMetricCard
            metric="weight"
            label="Cân nặng"
            value="72.4"
            unit="kg"
            trend="stable"
            trendLabel="Ổn định 2 tuần"
            status="normal"
            lastUpdated={new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()}
          />
        </div>
        <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
          <PatientMetricCard
            metric="heart_rate"
            label="Nhịp tim"
            value="88"
            unit="bpm"
            trend="up"
            trendValue={8}
            status="warning"
            compact
          />
          <PatientMetricCard
            metric="cholesterol"
            label="Cholesterol"
            value="5.8"
            unit="mmol/L"
            trend="down"
            trendValue={-0.3}
            status="warning"
            compact
          />
          <PatientMetricCard
            metric="bmi"
            label="BMI"
            value="26.1"
            unit="kg/m²"
            status="normal"
            compact
          />
        </div>
      </SubSection>

      {/* Risk Level Badge */}
      <SubSection title="RiskLevelBadge">
        <div className="flex flex-wrap gap-6 items-start">
          <div className="flex flex-col gap-3">
            <p className="text-caption text-text-muted font-medium">Size SM</p>
            <RiskLevelBadge level="high" size="sm" />
            <RiskLevelBadge level="medium" size="sm" />
            <RiskLevelBadge level="low" size="sm" />
            <RiskLevelBadge level="unknown" size="sm" />
          </div>
          <div className="flex flex-col gap-3">
            <p className="text-caption text-text-muted font-medium">Size MD</p>
            <RiskLevelBadge level="high" size="md" />
            <RiskLevelBadge level="medium" size="md" />
            <RiskLevelBadge level="low" size="md" />
            <RiskLevelBadge level="unknown" size="md" />
          </div>
          <div className="flex flex-col gap-3">
            <p className="text-caption text-text-muted font-medium">Size LG</p>
            <RiskLevelBadge level="high" size="lg" />
            <RiskLevelBadge level="medium" size="lg" />
            <RiskLevelBadge level="low" size="lg" />
            <RiskLevelBadge level="unknown" size="lg" />
          </div>
          <div className="flex flex-col gap-3">
            <p className="text-caption text-text-muted font-medium">With Score</p>
            <RiskLevelBadge level="high" size="md" showScore score={82} />
            <RiskLevelBadge level="medium" size="md" showScore score={55} />
            <RiskLevelBadge level="low" size="md" showScore score={18} />
          </div>
        </div>
      </SubSection>

      {/* Doctor Review Queue */}
      <SubSection title="DoctorReviewQueueItem">
        <div className="flex flex-col gap-3 max-w-2xl">
          <DoctorReviewQueueItem
            item={MOCK_QUEUE_URGENT}
            onClick={() => undefined}
            selected={false}
          />
          <DoctorReviewQueueItem
            item={MOCK_QUEUE_NORMAL}
            onClick={() => undefined}
            selected={true}
          />
          <DoctorReviewQueueItem
            item={{
              id: 'q-003',
              patientName: 'Phạm Hoàng Linh',
              patientId: 'BN-2024-00789',
              submittedAt: new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString(),
              type: 'ai_session',
              priority: 'high',
              status: 'in_review',
              summary: 'Phiên tư vấn về triệu chứng hô hấp',
            }}
            onClick={() => undefined}
            compact
          />
        </div>
      </SubSection>

      {/* Timeline */}
      <SubSection title="TimelineItem">
        <div className="max-w-2xl bg-surface border border-border rounded-lg p-5">
          {MOCK_TIMELINE_EVENTS.map((event, idx) => (
            <TimelineItem
              key={event.id}
              event={event}
              isLast={idx === MOCK_TIMELINE_EVENTS.length - 1}
            />
          ))}
        </div>
      </SubSection>

      {/* CarePlanCard */}
      <SubSection title="CarePlanCard">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <CarePlanCard
            plan={MOCK_CARE_PLAN}
            onViewDetail={() => undefined}
          />
          <div className="flex flex-col gap-3">
            <p className="text-caption text-text-muted font-medium">Compact variant</p>
            <CarePlanCard
              plan={MOCK_CARE_PLAN}
              onViewDetail={() => undefined}
              compact
            />
            <CarePlanCard
              plan={{
                ...MOCK_CARE_PLAN,
                id: 'cp-002',
                title: 'Kế hoạch phục hồi sau phẫu thuật',
                status: 'completed',
                goals: [
                  { id: 'g-a', description: 'Tập vật lý trị liệu 3 buổi/tuần', completed: true },
                  { id: 'g-b', description: 'Kiểm tra vết thương định kỳ', completed: true },
                ],
              }}
              onViewDetail={() => undefined}
              compact
            />
          </div>
        </div>
      </SubSection>

      {/* ConsentStatusCard */}
      <SubSection title="ConsentStatusCard">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <ConsentStatusCard
            consents={MOCK_CONSENTS}
            onManage={() => undefined}
          />
          <div className="flex flex-col gap-3">
            <p className="text-caption text-text-muted font-medium">Compact variant</p>
            <ConsentStatusCard
              consents={MOCK_CONSENTS}
              onManage={() => undefined}
              compact
            />
          </div>
        </div>
      </SubSection>

      {/* AI Session Card */}
      <SubSection title="AISessionCard">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <AISessionCard
            session={MOCK_AI_SESSION}
            onViewDetail={() => undefined}
          />
          <div className="flex flex-col gap-3">
            <p className="text-caption text-text-muted font-medium">Compact + no red flag</p>
            <AISessionCard
              session={{
                id: 'ai-002',
                sessionDate: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
                summary:
                  'Bệnh nhân hỏi về chế độ ăn phù hợp khi dùng Metformin. AI giải thích nên ăn trong bữa để giảm tác dụng phụ đường tiêu hóa.',
                keyTopics: ['Chế độ ăn', 'Metformin', 'Tác dụng phụ'],
                disclaimer:
                  'Thông tin này chỉ mang tính tham khảo. Vui lòng tham khảo bác sĩ của bạn.',
                hadRedFlag: false,
                escalatedToDoctor: false,
                status: 'completed',
              }}
              onViewDetail={() => undefined}
              compact
            />
          </div>
        </div>
      </SubSection>

      {/* Review Decision Panel */}
      <SubSection title="ReviewDecisionPanel">
        <div className="max-w-2xl">
          <ReviewDecisionPanel
            onSubmit={() => undefined}
            loading={false}
            readOnly={false}
            patientName="Nguyễn Văn Bình"
            reviewType="Kết quả xét nghiệm máu định kỳ"
          />
        </div>
      </SubSection>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function DesignSystemPage() {
  const [activeSection, setActiveSection] = React.useState('tokens')

  const handleNavClick = (id: string) => {
    setActiveSection(id)
    const el = document.getElementById(id)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  // Intersection observer to track active section
  React.useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id)
          }
        }
      },
      { rootMargin: '-20% 0px -70% 0px', threshold: 0 },
    )

    SECTIONS.forEach(({ id }) => {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    })

    return () => observer.disconnect()
  }, [])

  return (
    <div className="min-h-screen bg-background">
      {/* Top nav */}
      <TopNav
        title="MetoCare Design System"
        actions={
          <span className="inline-flex items-center gap-1.5 text-caption font-mono bg-primary-light text-primary-700 border border-primary-200 px-2.5 py-1 rounded-full">
            <Heart className="h-3 w-3" />
            v1.0.0
          </span>
        }
      />

      <div className="flex">
        {/* Sticky sidebar */}
        <aside className="hidden lg:flex flex-col sticky top-14 h-[calc(100vh-3.5rem)] w-56 shrink-0 border-r border-border bg-surface overflow-y-auto">
          <nav className="p-4 flex flex-col gap-1" aria-label="Section navigation">
            <p className="text-label-sm font-semibold text-text-muted uppercase tracking-wider px-3 mb-2">
              Sections
            </p>
            {SECTIONS.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => handleNavClick(id)}
                className={`w-full text-left px-3 py-2 rounded-md text-body-sm transition-colors ${
                  activeSection === id
                    ? 'bg-primary-light text-primary font-medium'
                    : 'text-text-muted hover:bg-secondary-50 hover:text-text'
                }`}
              >
                {label}
              </button>
            ))}
          </nav>

          <div className="mt-auto p-4 border-t border-border">
            <p className="text-caption text-text-subtle leading-relaxed">
              Living style guide cho đội ngũ thiết kế và phát triển MetoCare.
            </p>
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 min-w-0 px-6 py-8 lg:px-10 max-w-5xl">
          {/* Page hero */}
          <div className="mb-12 pb-8 border-b border-border">
            <div className="flex items-center gap-3 mb-3">
              <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-primary text-white">
                <Heart className="h-5 w-5" />
              </div>
              <div>
                <h1 className="text-display-sm font-bold text-text leading-tight">
                  Design System
                </h1>
                <p className="text-body-sm text-text-muted">MetoCare · v1.0.0</p>
              </div>
            </div>
            <p className="text-body-lg text-text-muted max-w-2xl mt-4">
              Thư viện thành phần giao diện lâm sàng cho nền tảng chăm sóc sức khoẻ MetoCare.
              Tất cả các thành phần tuân theo nguyên tắc thiết kế y tế — rõ ràng, an toàn và dễ
              tiếp cận.
            </p>
            <div className="flex flex-wrap gap-3 mt-6">
              <Badge variant="primary" dot>React 19</Badge>
              <Badge variant="default">Tailwind CSS v4</Badge>
              <Badge variant="default">Radix UI</Badge>
              <Badge variant="default">Lucide Icons</Badge>
              <Badge variant="success" dot>WCAG 2.1 AA</Badge>
            </div>
          </div>

          {/* Sections */}
          <div className="flex flex-col gap-16">
            <ColorTokensSection />
            <TypographySection />
            <ButtonsSection />
            <BadgesSection />
            <FormsSection />
            <CardsSection />
            <AlertsSection />
            <HealthcareSection />
          </div>

          {/* Footer */}
          <footer className="mt-20 pt-8 border-t border-border text-center">
            <p className="text-body-sm text-text-muted">
              MetoCare Design System · Được xây dựng cho đội ngũ y tế Việt Nam
            </p>
            <p className="text-caption text-text-subtle mt-1">
              Thiết kế phiên bản 1.0.0 · Cập nhật: 19/06/2026
            </p>
          </footer>
        </main>
      </div>
    </div>
  )
}
