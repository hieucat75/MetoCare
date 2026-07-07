import { render, screen, within } from '@testing-library/react'
import { DataTable, type DataColumn } from '../DataTable'

// ---------------------------------------------------------------------------
// DataTable renders BOTH a semantic <table> (desktop, `hidden md:block`) and a
// stacked card list (mobile, `md:hidden`) at once — CSS toggles which is shown.
// jsdom keeps both in the DOM, so we can assert both are present and that
// rowActions render in each. This guards "no desktop-only table on mobile".
// ---------------------------------------------------------------------------

interface Consultation {
  id: string
  patient: string
  status: string
}

const COLUMNS: DataColumn<Consultation>[] = [
  { key: 'patient', header: 'Bệnh nhân', priority: 1 },
  { key: 'status', header: 'Trạng thái', priority: 2 },
]

const ROWS: Consultation[] = [
  { id: 'c1', patient: 'Nguyễn Văn A', status: 'Chờ duyệt' },
  { id: 'c2', patient: 'Trần Thị B', status: 'Hoàn thành' },
]

function renderTable() {
  return render(
    <DataTable
      columns={COLUMNS}
      rows={ROWS}
      keyField="id"
      rowActions={(row) => (
        <button type="button">Xem {row.patient}</button>
      )}
    />,
  )
}

describe('DataTable — responsive dual rendering', () => {
  test('renders a semantic <table> (desktop view) for the given rows', () => {
    renderTable()

    const table = screen.getByRole('table')
    expect(table).toBeInTheDocument()

    // Header cells (columns + the appended actions column).
    expect(within(table).getByText('Bệnh nhân')).toBeInTheDocument()
    expect(within(table).getByText('Trạng thái')).toBeInTheDocument()
    expect(within(table).getByText('Thao tác')).toBeInTheDocument()

    // One <tr> per data row in the body.
    const bodyRows = within(table).getAllByRole('row')
    // 1 header row + 2 data rows
    expect(bodyRows).toHaveLength(3)
  })

  test('renders a stacked card list (mobile view) as label:value pairs', () => {
    const { container } = renderTable()

    // Mobile cards live inside the `md:hidden` wrapper.
    const mobileWrap = container.querySelector('.md\\:hidden')
    expect(mobileWrap).not.toBeNull()
    const scoped = within(mobileWrap as HTMLElement)

    // Header field (highest priority) rendered as the card heading.
    expect(scoped.getByText('Nguyễn Văn A')).toBeInTheDocument()
    expect(scoped.getByText('Trần Thị B')).toBeInTheDocument()

    // Remaining fields rendered as label : value (dt/dd) rows.
    expect(scoped.getAllByText('Trạng thái').length).toBe(ROWS.length)
    expect(scoped.getByText('Chờ duyệt')).toBeInTheDocument()
    expect(scoped.getByText('Hoàn thành')).toBeInTheDocument()
  })

  test('renders rowActions in BOTH the table and the cards', () => {
    renderTable()

    // Each row's action appears once in the desktop table and once in the
    // mobile card → 2 occurrences per row.
    expect(screen.getAllByRole('button', { name: 'Xem Nguyễn Văn A' })).toHaveLength(2)
    expect(screen.getAllByRole('button', { name: 'Xem Trần Thị B' })).toHaveLength(2)
  })

  test('shows the empty message in both views when there are no rows', () => {
    render(<DataTable columns={COLUMNS} rows={[]} keyField="id" emptyMessage="Chưa có buổi tư vấn" />)

    // Desktop empty cell + mobile empty card → message present twice.
    expect(screen.getAllByText('Chưa có buổi tư vấn').length).toBeGreaterThanOrEqual(2)
  })
})
