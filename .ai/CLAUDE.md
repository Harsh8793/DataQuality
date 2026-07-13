# CLAUDE.md

# DataPilot AI

Enterprise AI Copilot for Data Quality, Analytics & Governance

---

# PURPOSE

This project must be built like an enterprise software product, NOT like a hackathon prototype.

Every feature should be:

- Modular
- Reusable
- Maintainable
- Scalable
- Tested
- API Driven
- Clean Architecture
- SOLID
- Production Ready

Think like a Senior Software Architect.

---

# ENGINEERING PRINCIPLES

Always follow

- SOLID Principles
- Clean Architecture
- DRY
- KISS
- Separation of Concerns
- Dependency Injection
- Repository Pattern
- Service Layer Pattern
- API First Development
- Type Safety
- Centralized Error Handling
- Logging
- Environment Configurations

Never write spaghetti code.

---

# SDLC

Always follow proper SDLC.

Requirement Analysis

↓

Architecture

↓

Database Design

↓

API Design

↓

Backend Development

↓

Frontend Development

↓

Testing

↓

Integration

↓

Bug Fixes

↓

Documentation

↓

Deployment

Do NOT skip phases.

---

# DEVELOPMENT ORDER

Always build in this order.

1 Architecture

2 Database

3 Models

4 APIs

5 Services

6 AI Layer

7 Frontend

8 Testing

9 Documentation

Never directly create UI before APIs.

---

# API FIRST

Everything must go through APIs.

Frontend NEVER accesses database directly.

Flow

Frontend

↓

API

↓

Service Layer

↓

Repository

↓

Database

Never violate this rule.

---

# PROJECT STRUCTURE

Root

/backend

/frontend

/docs

/scripts

/tests

README.md

CLAUDE.md

.env.example

docker-compose.yml

.gitignore

---

# BACKEND STRUCTURE

backend/

app/

api/

v1/

auth.py

upload.py

analysis.py

dashboard.py

chat.py

reports.py

governance.py

history.py

config/

database/

models/

repositories/

services/

agents/

utils/

middleware/

schemas/

core/

exceptions/

logs/

tests/

main.py

requirements.txt

---

# BACKEND RULES

API Layer

Only receives requests.

No business logic.

Service Layer

Contains business logic.

Repository Layer

Database operations only.

Agents

Only AI logic.

Utils

Reusable helper functions.

Never mix responsibilities.

---

# DATABASE

SQLite

Use SQLAlchemy ORM.

No raw SQL unless necessary.

Every table

Primary Key

Created At

Updated At

Soft Delete

Indexes where required

---

# DATABASE TABLES

users

uploaded_files

datasets

dataset_columns

quality_reports

chat_history

dashboard_history

governance_reports

analysis_history

generated_reports

system_logs

---

# DATABASE RULES

Every database operation must go through Repository Layer.

Never call ORM directly from API.

---

# FRONTEND STRUCTURE

frontend/

src/

api/

components/

pages/

layouts/

hooks/

services/

store/

contexts/

utils/

constants/

types/

assets/

styles/

routes/

App.tsx

main.tsx

---

# FRONTEND RULES

Pages

Only layout.

Components

Reusable UI.

Hooks

Business state.

Services

API Calls.

Never call APIs directly inside components.

Always use Service Layer.

---

# STATE MANAGEMENT

Use React Query.

Global state only if necessary.

Avoid unnecessary Context.

---

# API CLIENT

Create single API client.

apiClient.ts

Every request goes through it.

No duplicated fetch calls.

---

# FILE UPLOAD FLOW

Upload

↓

Validation

↓

API

↓

Backend

↓

Processing

↓

Database

↓

AI

↓

Result

Never process inside frontend.

---

# AI LAYER

Separate AI from business logic.

agents/

profiling_agent.py

quality_agent.py

cleaning_agent.py

governance_agent.py

sql_agent.py

dashboard_agent.py

chat_agent.py

report_agent.py

insight_agent.py

Each agent has ONE responsibility.

---

# SERVICES

Never let agents talk to database.

Service Layer coordinates everything.

---

# QUALITY CHECK PIPELINE

Upload

↓

Validation

↓

Profiling

↓

Quality Analysis

↓

Governance

↓

Recommendations

↓

Cleaning

↓

Dashboard

↓

Reports

↓

Save History

---

# REPORT GENERATION

Report service only.

Never inside API.

---

# LOGGING

Centralized logger.

Never print().

Use logging module.

Log

Errors

Warnings

Execution Time

AI Calls

Uploads

API Calls

---

# CONFIGURATION

Everything through .env

Never hardcode

API Keys

Paths

URLs

Ports

Database

Secrets

---

# ERROR HANDLING

Use Global Exception Middleware.

Never expose internal exceptions.

Return proper HTTP codes.

---

# VALIDATION

Validate every request.

Never trust frontend.

Use Pydantic.

---

# AUTHENTICATION

JWT.

Protected APIs.

Role Ready.

Future Support

Admin

Analyst

Viewer

---

# SECURITY

Validate uploads.

Limit file size.

Validate extensions.

Sanitize filenames.

Prevent SQL Injection.

Prevent Path Traversal.

---

# TESTING

Unit Tests

Integration Tests

API Tests

Every Service should be testable.

---

# CODING STYLE

Python

PEP8

Type Hints

Docstrings

Small Functions

Reusable Classes

TypeScript

Strict Mode

Interfaces

Reusable Components

Avoid any.

---

# NAMING

Controllers

UploadController

Services

UploadService

Repositories

UploadRepository

Models

UploadedFile

Schemas

UploadRequest

UploadResponse

---

# UI

Professional.

Enterprise.

Responsive.

Dark Mode.

Modern.

Use

Tailwind

shadcn/ui

Recharts

Lucide Icons

Avoid unnecessary animations.

---

# DASHBOARD

Dashboard should feel like

Power BI

Microsoft Fabric

Azure Portal

NOT a student project.

---

# PERFORMANCE

Lazy Loading

Pagination

Virtualization

Caching

Optimized Queries

Avoid unnecessary renders.

---

# GIT

Feature Branches.

Meaningful commits.

Never push broken code.

---

# DOCUMENTATION

Every API

Swagger

README

Architecture Diagram

Database Diagram

Folder Structure

API Documentation

---

# FEATURE DEVELOPMENT RULE

Whenever adding a feature

1

Database

↓

2

Repository

↓

3

Service

↓

4

API

↓

5

Frontend Service

↓

6

Frontend Component

↓

7

Testing

Never skip order.

---

# DO NOT

Never mix frontend/backend logic.

Never duplicate code.

Never hardcode.

Never write huge files.

Never create God Classes.

Never bypass Service Layer.

Never bypass Repository Layer.

Never access DB from API.

Never call AI from UI.

Never ignore errors.

---

# EXPECTATION

Every generated code should look like it belongs in a Fortune 500 production codebase.

Quality is more important than speed.

If architecture decisions are unclear, ask before implementing.

Always prioritize maintainability, readability, modularity, and scalability.

