# Screenshots & Visual Documentation

The repository already contains a substantial set of rendered architecture/activity diagrams. The next visual layer should demonstrate the running product.

## Recommended screenshot set

### 1. Surveillance dashboard

Show:

- camera grid
- camera status
- connection state
- active incidents
- AI detection indicators

Avoid exposing real credentials, camera URLs, personal information, or real surveillance footage.

### 2. Live AI detection

Show:

- source frame
- bounding boxes
- detected class
- confidence
- timestamp
- camera/source identifier

Use synthetic or intentionally safe footage.

### 3. Incident management

Show:

- incident classification
- severity/status
- timestamps
- linked detection events
- assigned user/team
- audit history

### 4. Evidence details

Show:

- evidence identifier
- source incident
- content type
- integrity/hash information
- encryption state
- signature/verification state
- storage reference

Do not display private keys or sensitive cryptographic material.

### 5. Chain of custody

Show a timeline containing:

```text
Created
  ↓
Acquired
  ↓
Verified
  ↓
Transferred
  ↓
Received
  ↓
Reviewed
```

The actual UI should only display lifecycle states supported by the implementation.

### 6. Audit/reporting

Show:

- actor
- action
- timestamp
- resource
- correlation ID
- outcome

Use test users and synthetic data.

### 7. Architecture

Use the Mermaid diagrams in `docs/architecture.md` together with the existing high-resolution diagrams under `Architecture Design/`.

## Suggested README gallery

Once screenshots exist, add a compact section like:

```markdown
## Product Preview

| Surveillance | Evidence |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Evidence](docs/screenshots/evidence.png) |

| Incident | Chain of Custody |
|---|---|
| ![Incident](docs/screenshots/incident.png) | ![Custody](docs/screenshots/custody.png) |
```

## Capture standards

- Use 1440px+ desktop screenshots where possible.
- Keep browser chrome out of screenshots when practical.
- Use consistent viewport size.
- Use seeded/demo data.
- Do not include real passwords, tokens, API keys, private keys, camera credentials, or personally identifiable information.
- Prefer one clear feature per screenshot.
- Annotate complex security workflows only when the annotation improves comprehension.
