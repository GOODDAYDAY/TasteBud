---
name: requirement-develop
description: "Requirement analysis & technical design management. Use: /requirement-develop add <name> | done <name> | list | show <name>"
user-invocable: true
---

# Requirement & Technical Design Management

You are a senior developer. Before writing any code, you MUST complete requirement analysis and technical design first.

## Directory Structure

All requirement documents live in `docs/requirements/`:

```
docs/requirements/
├── index.md                           # Master index of all requirements
└── REQ-<NNN>-<name>/                  # One directory per requirement, prefixed with ID
    ├── requirement.md                 # Requirement document
    └── design.md                      # Technical design document
```

## ID Auto-Increment

When creating a new requirement:

1. Read `docs/requirements/index.md`
2. Find the highest existing REQ number (e.g. REQ-003)
3. Increment by 1 to get the next ID (e.g. REQ-004)
4. If no entries exist, start with REQ-001

## Commands

Parse the `args` to determine the subcommand:

### `add <name>` — Create a new requirement

1. Determine next REQ ID by reading index.md (auto-increment)
2. Create directory `docs/requirements/REQ-<NNN>-<name>/`
3. Initialize `docs/requirements/REQ-<NNN>-<name>/requirement.md` with the template below
4. Initialize `docs/requirements/REQ-<NNN>-<name>/design.md` with the template below
5. Update `docs/requirements/index.md`: append a new row to the table with status `🔵 NEW`
6. Tell the user: "Requirement `REQ-<NNN>-<name>` created. Please describe your requirement, and I'll fill in the
   documents."

### `done <name>` — Mark a requirement as completed

1. Find the directory matching `<name>` (search by name suffix in `REQ-<NNN>-<name>` pattern)
2. Update `docs/requirements/index.md`: change the status of that entry to `✅ DONE`
3. Add completion date to the index entry
4. Update status in both `requirement.md` and `design.md` to `✅ DONE`
5. Tell the user: "Requirement `REQ-<NNN>-<name>` marked as done."

### `list` — Show all requirements

1. Read `docs/requirements/index.md` and display the table to the user

### `show <name>` — Show a specific requirement

1. Find the directory matching `<name>` (search by name suffix in `REQ-<NNN>-<name>` pattern)
2. Read both `requirement.md` and `design.md`
3. Display a summary to the user

## Templates

### requirement.md template

```markdown
# <NAME> — Requirement Document

| Field        | Value          |
|-------------|----------------|
| ID          | REQ-<NNN>      |
| Status      | 🔵 NEW         |
| Created     | <YYYY-MM-DD>   |
| Updated     | <YYYY-MM-DD>   |

## 1. Background & Motivation

_Why do we need this? What problem does it solve?_

## 2. Functional Requirements

_What should the system do? List concrete behaviors._

- [ ] FR-1: ...
- [ ] FR-2: ...

## 3. Non-Functional Requirements

_Performance, security, compatibility, etc._

## 4. User Stories / Use Cases

_As a [role], I want [action], so that [benefit]._

## 5. Acceptance Criteria

_How do we know this is done?_

- [ ] AC-1: ...

## 6. Out of Scope

_What is explicitly NOT included in this requirement?_

## 7. Open Questions

_Unresolved decisions or questions._
```

### design.md template

```markdown
# <NAME> — Technical Design

| Field        | Value          |
|-------------|----------------|
| Requirement | REQ-<NNN>      |
| Status      | 🔵 NEW         |
| Created     | <YYYY-MM-DD>   |
| Updated     | <YYYY-MM-DD>   |

## 1. Overview

_High-level summary of the technical approach._

## 2. Architecture Changes

_What components are added/modified? Include diagrams if helpful._

### 2.1 Data Model Changes

_New tables, columns, or schema changes._

### 2.2 API Changes

_New or modified endpoints._

### 2.3 Service Layer Changes

_Business logic changes._

## 3. Detailed Design

_Step-by-step technical implementation plan._

### 3.1 Step 1: ...

### 3.2 Step 2: ...

## 4. File Change List

_Which files will be created/modified?_

| File | Action | Description |
|------|--------|-------------|
| ... | Create/Modify | ... |

## 5. Testing Strategy

_How will this be tested?_

- [ ] Unit tests: ...
- [ ] Integration tests: ...

## 6. Migration & Rollback

_Database migrations needed? How to roll back?_

## 7. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| ... | ... | ... |
```

## Workflow Rules

**CRITICAL**: When implementing any requirement that has status `🟡 IN PROGRESS`:

1. **Before writing ANY code**, first update `requirement.md` and `design.md` to reflect the current understanding
2. Fill in all sections of `requirement.md` based on user input and your analysis
3. Fill in all sections of `design.md` with concrete technical decisions
4. Change status to `🟡 IN PROGRESS` in both documents and in `index.md`
5. Only THEN start writing code
6. If requirements change during implementation, update the documents FIRST, then modify code

## Index File Format

The `docs/requirements/index.md` file should follow this format:

```markdown
# TasteBud — Requirement Index

| # | ID | Name | Status | Created | Updated | Description |
|---|-----|------|--------|---------|---------|-------------|
| 1 | REQ-001 | example-feature | 🔵 NEW | 2026-03-08 | 2026-03-08 | Brief description |
```

Status values: `🔵 NEW` → `🟡 IN PROGRESS` → `✅ DONE`
