# Before — live bundle at app.metocare.me (pre-deploy)

Captured 2026-08-04, before the parity deploy. Establishes what the owner was
looking at when they reported "the medication UI still appears unchanged".

## Identity

| Item | Value |
|---|---|
| URL | `https://app.metocare.me/medications/<medication-id>` |
| DNS | CNAME → `ca-metocare-frontend.wittyflower-55a3afa4.southeastasia.azurecontainerapps.io` → `4.144.233.112` |
| Route chunk | `/_next/static/chunks/app/(patient)/medications/%5Bid%5D/page-c45586326b373f44.js` |
| sha256 | `6402410aad490c395a5a681c11882d450ac9fe2aa2d08103e02ffd2e8ae13f2b` |
| Bytes | 29198 |
| Built from | `d25f109` (branch `feat/patient-platform-journey2`), 2026-08-03 08:27Z, run `30797337153` |
| Identical via staging FQDN | yes — byte-for-byte, same sha256 |

## What the bundle DID contain (M1–M4 web redesign, decoded from `\xNN` escapes)

```
Chi tiết thuốc · Thêm tuỳ chọn · Tuỳ chọn thuốc · Liều dùng · Tần suất
Đã uống · Bỏ qua · Tuân thủ điều trị · Cách sử dụng · Ghi chú của bạn
Đang tải dữ liệu tương tác thuốc · Chưa có dữ liệu tương tác được kiểm chứng
Đang tải dữ liệu tác dụng phụ · Dấu hiệu cần đi khám ngay
Bác sĩ yêu cầu tạm ngừng · AI tạo
```

⇒ The deployed web build was **current with `origin/main`**. The "stale deployment"
hypothesis is refuted.

## What it did NOT contain — the actual gap

No reference to any Journey-2/3 endpoint. The page called only the legacy
`medication_adherence` API:

```
GET   /patients/{pid}/medications
GET   /patients/{pid}/medications/{mid}/adherence
GET   /patients/{pid}/medications/adherence-summary
POST  /patients/{pid}/medications/{mid}/adherence
PATCH /patients/{pid}/medications/{mid}
```

Absent from the web client entirely (present in the backend and consumed by mobile):

```
GET  /patients/{pid}/medications/{mid}/schedule     structured schedule
GET  /patients/{pid}/reminders/due                  next due dose   (live: 401, not 404)
POST /patients/{pid}/doses/{did}/taken              dose-level taken
POST /patients/{pid}/doses/{did}/skipped            dose-level skipped + reason
GET  /patients/{pid}/schedules/{sid}/adherence      taken/skipped/MISSED + rate
```

## Reproduce

```bash
dig +short app.metocare.me
curl -s https://app.metocare.me/medications/<id> \
  | grep -o '/_next/static/chunks/app/[^"\\]*medications/%5Bid%5D/page-[a-f0-9]*\.js'
curl -s "https://app.metocare.me<chunk>" | shasum -a 256
# NOTE: grep the chunk with \xNN escapes DECODED — a literal UTF-8 grep
# produces false negatives (e.g. "Thêm tuỳ chọn" is emitted as "Th\xeam tuỳ chọn").
```
