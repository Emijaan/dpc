# Milestone 2 — UI/UX Design Spec

Clickable prototype: `frontend/design/prototype.html` (open in a browser; use the role switcher top-right).
Final stack: React + TypeScript + Tailwind, tokens below map 1:1 to `tailwind.config`.

## 1. Decisions recorded (from Milestone 1)
- Command signing stays **ECDSA P-256** (Ed25519 needs Android 13+ Keystore; `minSdk` is 28).
- **Android 8 = documented unsupported** for now (`minSdk` 28). Revisit when a JDK + Android 8 device are available.
- New React SPA in `frontend/`; current Django panel stays live until feature parity.
- Celery/Redis deferred to Milestone 13.

## 2. Design system
| Token | Value | Use |
|---|---|---|
| Font | Inter / system-ui; 14px base, 12px meta, 20/24px headings | all text |
| Neutral | slate-50 bg, white surfaces, slate-200 borders, slate-900 text, slate-500 muted | layout |
| Primary | indigo-600 (hover 700) | primary actions, active nav |
| Status | green-600 success/active, amber-500 pending/warning, red-600 danger/locked, slate-400 inactive/released | badges only |
| Radius / shadow | 8px; border instead of shadow, shadow only on modals | |
| Spacing | 4px grid; page padding 24px; card padding 16–20px | |
| Light theme only for v1 (clean, print-friendly tables) | | |

One accent colour. Colour is reserved for **status**; everything else is neutral. No decorative cards: summary stats are a single flat row.

## 3. Layout & responsiveness
- Desktop ≥1024: fixed 220px sidebar + top bar (account name, role badge, logout).
- Tablet 640–1023: collapsed icon sidebar.
- Mobile <640: bottom/hamburger nav, tables become stacked rows, forms single-column, sticky primary action.
- Every list page: title + primary action, search, filter chips, table, pagination (25/page), empty/loading/error states. Sensitive actions (lock, unlock, release, deactivate, transfer) use a confirm dialog that names the target; Release requires typing the device ref.

## 4. Information architecture (hide in UI, enforce in backend)
| Page | Superuser | Retailer | Vendor |
|---|---|---|---|
| Dashboard | platform-wide | own hierarchy | own |
| Retailers | ✔ create/edit/(de)activate | – | – |
| Vendors | ✔ all | ✔ own vendors: create/edit/(de)activate | – |
| Entitlements | allocate to retailer/vendor; all history | distribute to vendors; history in hierarchy | balance; transfer unused to sibling vendor; own history |
| Customers | all | scope | own |
| Devices | all + full filters | scope | own |
| Add Device (stepper) | ✔ | ✔ | ✔ |
| Commands | all | scope | own |
| Audit log | all | hierarchy | own |
| Security / Keys | ✔ | – | – |

## 5. Key screens
**Dashboard (all roles):** one flat stat row (role-specific, see below), "Expiring allocations" strip, Recent registrations table, Recent commands table, Recent activity list. Superuser also gets a devices-by-status bar and a 30-day registrations line chart.
- Superuser stats: Retailers · Vendors · Devices · Online · Locked · Entitlements available.
- Retailer: Allocated · Distributed · Consumed · Available · Active · Inactive · Released · Vendors · Expiry date.
- Vendor: Allocated · Consumed · Available · Devices · Locked · Expiry date.

**Account create/edit (Retailer / Vendor):** two-column form — Business (name, business name, address, contact person, mobile, email), Login (username, invitation email or temporary password), Allocation (quantity, issue date, expiry = issue + 365d, read-only), Status. Superuser chooses type; vendors require a parent retailer (auto-filled and locked for a retailer user).

**Entitlements:** balance card (allocated / distributed / consumed / available) + per-allocation table (issued, expires, qty, used, available, status) + ledger tab (allocation, transfer, consumption rows, append-only, filterable). "Allocate" / "Transfer" open a modal showing resulting balances before confirm. Expired allocations are greyed with an "Expired – cannot register" tag.

**Devices list:** table (Device ref, brand/model, customer, IMEI masked `••••••••1234`, Android, owner, device status, enrollment status, last seen, actions). Superuser filters: retailer, vendor, account type, device status, enrollment status, Android version, brand, model, registration date, last online, entitlement status, customer name/mobile, IMEI. Filters collapse into a drawer on mobile. Bulk-free in v1 (no bulk lock).

**Device detail:** header with status badges (separate chips for Device / Enrollment / Restriction / Connection), tabs: Overview · Customer · Commands (with Pending/Delivered/Executed/Failed/Expired) · Registration history · Audit. Actions: Lock · Unlock · Sync · Release. A command shows "Waiting for device" until acknowledged — the badge reflects **acknowledged** state only.

**Add Device — 4-step stepper (all roles)**
1. *Customer* — name, mobile, email (all required, inline validation).
2. *Device* — brand, model, IMEI (Luhn-validated), Android version, enrollment method (auto-suggested from version: 9–15 → QR, 16 → USB/ADB; 8 shows "Not supported").
3. *Review* — shows account, retailer/vendor, remaining entitlement (**"No entitlement is used until the device finishes enrolling"**) → Create pending registration.
4. *Enroll* — method-specific:
   - Android 9–15: sub-stepper "A. Scan Test DPC QR → B. [Generate AK DeviceLock QR] → C. Waiting for device", each with expected on-screen instructions and live status polling.
   - Android 16: prerequisite checklist (factory-fresh, no accounts, Auto Blocker off, USB debugging) shown **before** the Download .bat button; then live status "Waiting for device to register…".
   - Terminal states: Registered (entitlement consumed: 1), Failed (reason, nothing consumed), Expired (session timer 15 min), Cancelled.

**Audit:** table (time, actor, action, target, result, IP) with filters; read-only; row drawer shows metadata (never secrets).

## 6. Component inventory (React)
`AppShell, SideNav, TopBar, RoleBadge, StatRow, StatusBadge (device/enrollment/restriction/account/allocation variants), DataTable (sort/paginate/empty/loading/error), FilterBar + FilterDrawer, ConfirmDialog, TypeToConfirmDialog, Toast, Stepper, FormField (+validation), MoneyLess BalanceCard, LedgerTable, DeviceActions, QrPanel, DownloadPanel, EmptyState, ErrorState, Skeleton`.

## 7. Accessibility & content rules
WCAG AA contrast; focus rings; badges always carry text, never colour alone; plain wording ("Entitlement", "Device limit" — never "key" for commercial quota, "cryptographic key" only on Security pages; "IMEI" never "EMI").

## 8. Out of scope for the UI
No secrets, tokens or signing material are ever rendered; masked IMEI/mobile by default with an audited "Reveal" for permitted roles (Milestone 7).
