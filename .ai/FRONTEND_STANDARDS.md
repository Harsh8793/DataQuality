# FRONTEND DEVELOPMENT STANDARDS

## ROLE

You are a Principal React Engineer.

Every UI should look enterprise-grade.

Never generate beginner React code.

---

# STACK

React

TypeScript

Vite

Tailwind

shadcn/ui

React Query

React Router

React Hook Form

Zod

Recharts

Lucide Icons

---

# STRUCTURE

src/

api/

components/

features/

pages/

layouts/

hooks/

services/

store/

types/

constants/

contexts/

utils/

styles/

routes/

assets/

---

# COMPONENT DESIGN

Small

Reusable

Composable

Single Responsibility

Never duplicate UI.

---

# COMPONENT TYPES

Common Components

Button

Input

Modal

Dialog

Card

Table

Badge

Loader

Toast

Pagination

Search

Filters

Feature Components

Dashboard

Upload

Quality Report

Charts

Chat

Reports

History

---

# API

Never call fetch()

Create API Service Layer.

Example

UploadService

AnalysisService

ChatService

ReportService

---

# STATE

React Query

Server State

Context

Authentication only

Local State

Component only

---

# FORMS

React Hook Form

Zod Validation

Reusable Form Components

---

# TABLES

Reusable DataTable.

Support

Sorting

Filtering

Pagination

Column Selection

Export

Search

---

# CHARTS

Reusable

Bar

Line

Pie

Scatter

Area

KPI Cards

Never duplicate chart logic.

---

# LAYOUT

Sidebar

Top Navbar

Breadcrumb

Content Area

Footer

Responsive

---

# THEMES

Dark

Light

Central Theme

No hardcoded colors.

---

# TYPESCRIPT

Strict Mode

Interfaces

Types

No any.

---

# REUSABLE HOOKS

useUpload

useAnalysis

useChat

useDashboard

usePagination

useDebounce

useSearch

useTheme

useLocalStorage

---

# ERROR HANDLING

Global Error Boundary.

Loading State.

Empty State.

Error State.

Retry Button.

---

# PERFORMANCE

Lazy Loading

Memoization

Code Splitting

React.memo

useMemo

useCallback

Virtual Lists

---

# ACCESSIBILITY

ARIA Labels

Keyboard Support

Focus Management

Semantic HTML

---

# RESPONSIVENESS

Desktop First

Tablet

Mobile

No broken layouts.

---

# STYLING

Tailwind only.

Use design tokens.

No inline styles.

---

# FILE SIZE

Split components.

Avoid components exceeding ~300 lines unless justified.

---

# NAMING

PascalCase

UploadCard

DashboardHeader

QualityScoreCard

AnalysisTable

ChatPanel

---

# FOLDER ORGANIZATION

Every feature should contain

components/

hooks/

services/

types/

utils/

Example

features/

upload/

components/

hooks/

services/

types/

utils/

---

# REUSABILITY

If code repeats twice,

Extract component.

If logic repeats,

Extract hook.

If API repeats,

Extract service.

---

# QUALITY

ESLint

Prettier

TypeScript Strict

No console.log in production

Meaningful component names

Reusable UI

Maintainable architecture

---

# UX

Loading Skeletons

Progress Bars

Toast Notifications

Confirmation Dialogs

Responsive Tables

Keyboard Navigation

Professional animations only

---

# DEVELOPMENT ORDER

Types

↓

API Service

↓

Hook

↓

Reusable Component

↓

Feature Page

↓

Testing

Never directly create pages without reusable components.


