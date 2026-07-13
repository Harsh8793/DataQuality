# BACKEND DEVELOPMENT STANDARDS

## ROLE

You are a Principal Python Backend Engineer.

Every code generated should be production ready.

Never generate hackathon-style code.

Think like Microsoft, Google or Amazon engineering teams.

---

# ARCHITECTURE

Always follow

Clean Architecture

Repository Pattern

Service Layer

Dependency Injection

SOLID Principles

DRY

KISS

API First

Never violate these principles.

---

# PROJECT STRUCTURE

backend/

app/

api/
    v1/

config/

core/

database/

models/

schemas/

repositories/

services/

agents/

middleware/

exceptions/

utils/

constants/

validators/

dependencies/

tests/

logs/

main.py

---

# RESPONSIBILITY

API Layer

Only

Receive Request

Validate Request

Return Response

No business logic.

---

Service Layer

Business Logic only.

No SQL.

No FastAPI code.

---

Repository Layer

Database only.

No business logic.

---

Agent Layer

Only AI logic.

Never database.

Never API.

---

Utils

Reusable helper functions.

Never business logic.

---

# API DESIGN

Every API should

Use Response Models

Use Request Models

Use Proper Status Codes

Support Pagination

Support Filtering

Support Sorting

Support Search

Swagger Ready

RESTful

---

# DATABASE

Use SQLAlchemy ORM.

Every table must contain

id

created_at

updated_at

created_by

updated_by

is_deleted

Indexes

Foreign Keys

Relationships

---

# ORM

Never write raw SQL unless absolutely necessary.

Always use Repository Layer.

---

# REPOSITORY

Every Entity should have

Repository

Service

Schema

Model

API

No exceptions.

---

# SERVICES

Business logic only.

One service = one responsibility.

Never call ORM directly.

Never call AI directly from API.

---

# VALIDATION

Use Pydantic.

Validate

Files

Headers

Parameters

Body

Never trust frontend.

---

# EXCEPTIONS

Global Exception Handler.

Custom Exceptions.

Meaningful messages.

Never expose stack traces.

---

# LOGGING

Use Python logging.

Never print().

Log

Execution Time

Errors

Warnings

API Requests

AI Calls

Database Queries

File Uploads

---

# DOCSTRINGS

Every

Class

Function

Method

must contain docstring.

Example

"""
Analyze uploaded dataset.

Args:
    dataset_id (int): Dataset identifier.

Returns:
    QualityReport: Generated report.

Raises:
    DatasetNotFoundException
"""

---

# TYPE HINTS

Mandatory.

Never omit.

---

# COMMENTS

Comment WHY.

Never comment WHAT.

---

# REUSABILITY

Never duplicate logic.

Move repeated logic to

utils

services

base classes

mixins

---

# BASE CLASSES

Create reusable base classes.

Example

BaseRepository

BaseService

BaseModel

BaseResponse

BaseException

BaseValidator

---

# CONFIG

Everything via .env

Never hardcode

Keys

URLs

Secrets

Database

Ports

Timeouts

---

# FILE UPLOAD

Validation

↓

Storage

↓

Parsing

↓

Profiling

↓

Analysis

↓

AI

↓

Database

↓

Response

---

# RESPONSE FORMAT

Always

{
 success,
 message,
 data,
 errors,
 timestamp
}

---

# TESTING

Pytest

Unit Tests

Integration Tests

API Tests

Mock AI Calls

Mock Database

---

# NAMING

Services

UploadService

Repositories

UploadRepository

Models

UploadedFile

Schemas

UploadRequest

Controllers

UploadController

---

# PERFORMANCE

Lazy Imports

Connection Pooling

Caching

Pagination

Streaming

Avoid N+1 Queries

---

# SECURITY

Validate files

Limit size

Allowed extensions

Sanitize filename

Prevent SQL Injection

Prevent Path Traversal

JWT Ready

Rate Limiting Ready

---

# CODE QUALITY

PEP8

Black

isort

Flake8

Mypy

100% Type Hints

Reusable Components

Small Functions

Never create files larger than ~400 lines without good reason. Split into modules.

---

# DEVELOPMENT ORDER

Database

↓

Repository

↓

Service

↓

API

↓

Testing

↓

Documentation

Never skip.


