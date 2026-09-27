# v12.3 — Multi-User Professor Assignment & Student Session Architecture

## Goal
Add a multi-user application layer without changing the existing adaptive interviewer algorithms.

## Preserved
- GoalManager / Robust Goal Manager behavior
- Goal Evidence Continuity Manager
- EvidencePlanner coverage selection
- adaptive Bloom/difficulty progression
- answer evaluation and scoring
- goal timing and explicit goal-time allocation
- ABET traceability
- integrity/report generation
- existing `/interviews`, `/reports`, `/goals`, `/knowledge`, and ABET endpoints

## Added
- User identity with professor/student roles
- PBKDF2 password hashing
- bearer-token session authentication
- professor-owned interview assignments
- multiple students per assignment
- independent interview session per student
- assignment-time snapshots of knowledge, goals and interview configuration
- student assignment list
- professor assignment list, enrollment and status dashboard
- server-side ownership checks

## Important architecture rule
Assignment configuration is immutable assessment setup. Student adaptive state remains inside each existing `InterviewSession`. The new layer never decides which question to ask or how to score an answer.

## Development persistence
v12.3 uses an in-memory multi-user repository because the current project uses in-memory repositories. Data is lost on process restart. For production, replace the multi-user repository/token store with a relational database and durable authentication/session infrastructure without changing the assessment layer.

## API
- `POST /multiuser/auth/register`
- `POST /multiuser/auth/login`
- `GET /multiuser/auth/me`
- `GET /multiuser/students`
- `POST /multiuser/assignments`
- `GET /multiuser/assignments`
- `GET /multiuser/assignments/{assignment_id}`
- `POST /multiuser/assignments/{assignment_id}/students`
- `POST /multiuser/assignments/{assignment_id}/publish`
- `POST /multiuser/assignments/{assignment_id}/close`
- `GET /multiuser/assignments/{assignment_id}/students`
- `GET /multiuser/my/assignments`
- `POST /multiuser/my/assignments/{assignment_id}/start`

Existing interview APIs remain unchanged for backward compatibility.
