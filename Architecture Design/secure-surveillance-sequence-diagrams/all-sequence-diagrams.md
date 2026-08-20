# Secure Surveillance Platform — All Sequence Diagrams

## 01-user-authentication.mmd

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Web as Next.js Dashboard
    participant API as FastAPI Auth API
    participant Rate as Redis Rate Limiter
    participant Auth as Authentication Service
    participant DB as PostgreSQL
    participant MFA as MFA Service
    participant Token as Token Service
    participant Session as Redis Session Store
    participant Audit as Audit Service

    User->>Web: Open login page
    Web-->>User: Display login form
    User->>Web: Submit email and password
    Web->>API: POST /api/v1/auth/login
    API->>API: Validate request schema
    API->>Rate: Check IP and account limits

    alt Rate limit exceeded
        Rate-->>API: Deny request
        API->>Audit: Record throttled login attempt
        Audit->>DB: Persist audit event
        API-->>Web: 429 Too many requests
        Web-->>User: Display retry message
    else Request allowed
        Rate-->>API: Allow request
        API->>Auth: Authenticate credentials
        Auth->>DB: Load user and security state
        DB-->>Auth: User record or not found

        alt User missing, disabled, or locked
            Auth->>Audit: Record blocked login attempt
            Audit->>DB: Persist audit event
            Auth-->>API: Authentication failed
            API-->>Web: 401 Generic login error
            Web-->>User: Display login failure
        else Account available
            Auth->>Auth: Verify password hash

            alt Password invalid
                Auth->>Rate: Increment failed-attempt counter
                Rate-->>Auth: Updated failure count
                Auth->>Audit: Record failed login
                Audit->>DB: Persist audit event
                Auth-->>API: Authentication failed
                API-->>Web: 401 Generic login error
                Web-->>User: Display login failure
            else Password valid
                Auth->>Rate: Reset failed-attempt counter
                Auth->>DB: Load roles and permissions
                DB-->>Auth: RBAC claims

                opt MFA enabled
                    Auth->>MFA: Create one-time challenge
                    MFA-->>User: Deliver verification code
                    Auth-->>API: MFA required
                    API-->>Web: 202 MFA challenge
                    Web-->>User: Display MFA form
                    User->>Web: Submit verification code
                    Web->>API: POST /api/v1/auth/mfa/verify
                    API->>MFA: Validate code and expiry
                    MFA-->>API: Verification result
                end

                API->>Token: Issue access and refresh tokens
                Token->>Session: Store hashed refresh token and JTI
                Session-->>Token: Session stored
                Token-->>API: Tokens and expiry metadata
                API->>DB: Update last-login metadata
                API->>Audit: Record successful login
                Audit->>DB: Persist audit event
                API-->>Web: 200 User profile and tokens
                Web->>Web: Initialize secure session
                Web-->>User: Redirect to authorized dashboard
            end
        end
    end
```

## 02-camera-registration.mmd

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Administrator
    participant Web as Next.js Dashboard
    participant API as FastAPI Camera API
    participant Authz as Authorization Service
    participant Camera as Camera Service
    participant Gateway as Camera or Secure Gateway
    participant Crypto as Credential Encryption Service
    participant DB as PostgreSQL
    participant Audit as Audit Service

    Admin->>Web: Open camera management
    Web-->>Admin: Display registered cameras
    Admin->>Web: Enter camera details
    Web->>API: POST /api/v1/cameras
    API->>Authz: Validate JWT and camera-management permission

    alt Administrator not authorized
        Authz-->>API: Access denied
        API->>Audit: Record denied registration
        Audit->>DB: Persist audit event
        API-->>Web: 403 Forbidden
        Web-->>Admin: Display authorization error
    else Administrator authorized
        Authz-->>API: Access granted
        API->>Camera: Validate registration request

        alt Invalid camera data
            Camera-->>API: Validation errors
            API-->>Web: 422 Validation error
            Web-->>Admin: Display field errors
        else Camera data valid
            Camera->>DB: Check duplicate IP, name, or stream URL
            DB-->>Camera: Duplicate-check result

            alt Duplicate camera found
                Camera-->>API: Conflict detected
                API->>Audit: Record duplicate registration attempt
                Audit->>DB: Persist audit event
                API-->>Web: 409 Conflict
                Web-->>Admin: Display duplicate-camera error
            else No duplicate found
                Camera->>Gateway: Test network reachability

                alt Camera unreachable
                    Gateway-->>Camera: Connection failed
                    Camera-->>API: Reachability test failed
                    API->>Audit: Record connectivity failure
                    Audit->>DB: Persist audit event
                    API-->>Web: 422 Camera unreachable
                    Web-->>Admin: Display connectivity error
                else Camera reachable
                    Gateway-->>Camera: Connection established
                    Camera->>Gateway: Authenticate and validate RTSP or ONVIF stream
                    Gateway-->>Camera: Authentication and stream result

                    alt Authentication or stream validation failed
                        Camera-->>API: Camera validation failed
                        API->>Audit: Record camera validation failure
                        Audit->>DB: Persist audit event
                        API-->>Web: 422 Invalid camera stream
                        Web-->>Admin: Display stream error
                    else Camera validated
                        Camera->>Crypto: Encrypt camera credentials
                        Crypto-->>Camera: Encrypted credential reference
                        Camera->>DB: Create camera and default AI settings
                        DB-->>Camera: Camera record created
                        Camera->>Audit: Record successful registration
                        Audit->>DB: Persist audit event
                        Camera-->>API: Registered camera
                        API-->>Web: 201 Camera created
                        Web-->>Admin: Display active camera
                    end
                end
            end
        end
    end
```

## 03-ai-threat-detection.mmd

```mermaid
sequenceDiagram
    autonumber
    participant Cam as IP Camera
    participant Gateway as Secure Camera Gateway
    participant AI as AI Processing Engine
    participant YOLO as YOLO Detector
    participant Face as Face Recognition
    participant OCR as OCR Service
    participant Cache as Redis Deduplication Cache
    participant Incident as Incident Service
    participant Evidence as Evidence Service
    participant DB as PostgreSQL
    participant Storage as S3 or MinIO
    participant Notify as Notification Service
    participant Audit as Audit Service
    actor Officer as Security Officer

    Cam->>Gateway: Stream video frames
    Gateway->>AI: Forward authenticated frames and metadata

    loop Continuous monitoring
        AI->>AI: Sample and preprocess frame
        AI->>YOLO: Detect people, vehicles, and objects
        YOLO-->>AI: Detections and confidence scores

        opt Face present
            AI->>Face: Identify or compare face
            Face-->>AI: Face match result
        end

        opt Vehicle or plate present
            AI->>OCR: Read license plate or visible text
            OCR-->>AI: OCR result
        end

        AI->>AI: Apply zones, schedules, tracking, and threat rules

        alt Threat score below threshold
            AI->>Audit: Record non-threat telemetry when configured
        else Threat score above threshold
            AI->>Cache: Check suppression window and correlated events
            Cache-->>AI: Correlation result

            alt Correlated incident exists
                AI->>Incident: Attach detection to open incident
            else New incident required
                AI->>Incident: Create incident with severity and priority
            end

            Incident->>DB: Persist incident and detection metadata
            DB-->>Incident: Incident saved
            AI->>Evidence: Submit key frames and event clip
            Evidence->>Storage: Store encrypted evidence object
            Storage-->>Evidence: Storage URI and version
            Evidence->>DB: Persist evidence metadata and hashes
            Evidence-->>Incident: Evidence reference
            Incident->>Notify: Publish incident alert
            Notify-->>Officer: Dashboard, email, SMS, or push alert
            Incident->>Audit: Record detection and incident events
            Audit->>DB: Persist audit records
        end
    end
```

## 04-incident-management.mmd

```mermaid
sequenceDiagram
    autonumber
    actor Officer as Security Officer
    actor Investigator
    participant Web as Next.js Dashboard
    participant API as FastAPI Incident API
    participant Authz as Authorization Service
    participant Incident as Incident Service
    participant Evidence as Evidence Service
    participant Custody as Chain-of-Custody Service
    participant DB as PostgreSQL
    participant Notify as Notification Service
    participant Audit as Audit Service

    Officer->>Web: Open incident queue
    Web->>API: GET /api/v1/incidents
    API->>Authz: Check incident-view permission
    Authz-->>API: Access decision
    API->>Incident: List authorized incidents
    Incident->>DB: Query incidents
    DB-->>Incident: Incident records
    Incident-->>API: Incident list
    API-->>Web: 200 Incident list

    Officer->>Web: Review selected incident
    Web->>API: GET /api/v1/incidents/{id}
    API->>Authz: Check incident access
    Authz-->>API: Access granted
    API->>Incident: Load incident details
    Incident->>DB: Query incident, detections, and assignments
    Incident->>Evidence: Load linked evidence metadata
    Evidence->>DB: Query evidence metadata
    DB-->>Evidence: Evidence records
    Evidence-->>Incident: Linked evidence
    Incident-->>API: Incident details
    API-->>Web: 200 Incident details

    alt Officer marks false positive
        Officer->>Web: Submit false-positive reason
        Web->>API: PATCH /api/v1/incidents/{id}
        API->>Authz: Check incident-update permission
        Authz-->>API: Access granted
        API->>Incident: Mark false positive
        Incident->>DB: Update status and reason
        Incident->>Audit: Record false-positive decision
        Audit->>DB: Persist audit event
        API-->>Web: 200 Incident updated
    else Officer confirms incident
        Officer->>Web: Confirm and assign investigator
        Web->>API: POST /api/v1/incidents/{id}/assign
        API->>Authz: Check assignment permission
        Authz-->>API: Access granted
        API->>Incident: Assign investigator
        Incident->>DB: Persist assignment
        Incident->>Custody: Record assignment-related custody event
        Custody->>DB: Persist custody record
        Incident->>Notify: Notify investigator
        Notify-->>Investigator: New assignment notification
        Incident->>Audit: Record confirmation and assignment
        Audit->>DB: Persist audit event

        loop Investigation updates
            Investigator->>Web: Add notes, findings, or evidence request
            Web->>API: PATCH /api/v1/incidents/{id}
            API->>Authz: Check assigned-case access
            Authz-->>API: Access granted
            API->>Incident: Update investigation
            Incident->>DB: Persist notes and status
            Incident->>Audit: Record investigation update
            Audit->>DB: Persist audit event
            API-->>Web: 200 Incident updated
        end

        Investigator->>Web: Request incident closure
        Web->>API: POST /api/v1/incidents/{id}/close
        API->>Authz: Check closure permission

        alt Closure denied
            Authz-->>API: Access denied
            API->>Audit: Record denied closure
            Audit->>DB: Persist audit event
            API-->>Web: 403 Forbidden
        else Closure authorized
            Authz-->>API: Access granted
            API->>Incident: Set disposition and closure timestamp
            Incident->>DB: Persist closed status
            Incident->>Audit: Record incident closure
            Audit->>DB: Persist audit event
            API-->>Web: 200 Incident closed
        end
    end
```

## 05-evidence-ingestion.mmd

```mermaid
sequenceDiagram
    autonumber
    actor Source as AI Engine or Authorized User
    participant API as FastAPI Evidence API
    participant Authz as Authorization Service
    participant Evidence as Evidence Service
    participant Scan as Malware Scanner
    participant Hash as Hashing Service
    participant Crypto as Encryption Service
    participant Key as RSA or KMS Key Service
    participant Storage as S3 or MinIO
    participant DB as PostgreSQL
    participant Custody as Chain-of-Custody Service
    participant Audit as Audit Service

    Source->>API: POST /api/v1/evidence with file and metadata
    API->>Authz: Validate source identity and submit permission

    alt Source not authorized
        Authz-->>API: Access denied
        API->>Audit: Record denied evidence submission
        Audit->>DB: Persist audit event
        API-->>Source: 403 Forbidden
    else Source authorized
        Authz-->>API: Access granted
        API->>Evidence: Validate file, metadata, and incident reference

        alt Evidence package invalid
            Evidence-->>API: Validation errors
            API->>Audit: Record invalid evidence submission
            Audit->>DB: Persist audit event
            API-->>Source: 422 Validation error
        else Evidence package valid
            Evidence->>Scan: Scan file for malware and corruption
            Scan-->>Evidence: Scan result

            alt File unsafe or corrupted
                Evidence->>Storage: Quarantine rejected file
                Evidence->>Audit: Record quarantine event
                Audit->>DB: Persist audit event
                Evidence-->>API: File rejected
                API-->>Source: 422 Unsafe evidence file
            else File safe
                Evidence->>Hash: Calculate original SHA-256 hash
                Hash-->>Evidence: Original hash
                Evidence->>Crypto: Generate AES-256 data key and encrypt file
                Crypto->>Key: Wrap AES key with RSA public key or KMS
                Key-->>Crypto: Wrapped key reference
                Crypto-->>Evidence: Ciphertext, nonce, tag, and key reference
                Evidence->>Hash: Build and hash evidence manifest
                Hash-->>Evidence: Manifest hash
                Evidence->>Key: Digitally sign evidence manifest
                Key-->>Evidence: Digital signature
                Evidence->>Storage: Upload encrypted object
                Storage-->>Evidence: Object URI, version, and checksum

                alt Storage upload failed
                    Evidence->>Audit: Record ingestion failure and retry state
                    Audit->>DB: Persist audit event
                    Evidence-->>API: Storage failure
                    API-->>Source: 503 Evidence storage unavailable
                else Storage upload succeeded
                    Evidence->>DB: Persist metadata, hashes, signature, and key reference
                    DB-->>Evidence: Evidence record created
                    Evidence->>Custody: Create acquisition custody event
                    Custody->>DB: Persist append-only custody record
                    Custody-->>Evidence: Custody record ID
                    Evidence->>Audit: Record successful ingestion
                    Audit->>DB: Persist audit event
                    Evidence-->>API: Evidence identifier and status
                    API-->>Source: 201 Evidence created
                end
            end
        end
    end
```

## 06-evidence-retrieval.mmd

```mermaid
sequenceDiagram
    autonumber
    actor Investigator
    participant Web as Next.js Dashboard
    participant API as FastAPI Evidence API
    participant Authz as Authorization Service
    participant Evidence as Evidence Service
    participant DB as PostgreSQL
    participant Custody as Chain-of-Custody Service
    participant Storage as S3 or MinIO
    participant Key as RSA or KMS Key Service
    participant Crypto as Decryption Service
    participant Hash as Integrity Service
    participant Audit as Audit Service

    Investigator->>Web: Search for evidence
    Web->>API: GET /api/v1/evidence?filters
    API->>Authz: Check evidence-list permission and case scope
    Authz-->>API: Access decision

    alt Access denied
        API->>Audit: Record denied evidence search
        Audit->>DB: Persist audit event
        API-->>Web: 403 Forbidden
        Web-->>Investigator: Display access error
    else Access granted
        API->>Evidence: Search authorized evidence
        Evidence->>DB: Query evidence metadata
        DB-->>Evidence: Matching evidence records
        Evidence-->>API: Evidence summaries
        API-->>Web: 200 Evidence results
        Web-->>Investigator: Display evidence list

        Investigator->>Web: Select evidence and action
        Web->>API: GET /api/v1/evidence/{id}
        API->>Authz: Check item access and requested action
        Authz-->>API: Access granted
        API->>Evidence: Retrieve evidence
        Evidence->>DB: Load metadata, hash, storage URI, and key reference
        DB-->>Evidence: Evidence metadata
        Evidence->>Custody: Create access-attempt custody record
        Custody->>DB: Persist custody event
        Evidence->>Storage: Retrieve encrypted object
        Storage-->>Evidence: Ciphertext object
        Evidence->>Key: Unwrap AES key
        Key-->>Evidence: Authorized data key
        Evidence->>Crypto: Decrypt in controlled workspace
        Crypto-->>Evidence: Decrypted stream
        Evidence->>Hash: Calculate current SHA-256 hash
        Hash-->>Evidence: Current hash

        alt Integrity check failed
            Evidence->>Audit: Record integrity failure
            Audit->>DB: Persist audit event
            Evidence->>Custody: Record failed verification
            Custody->>DB: Persist custody event
            Evidence-->>API: Delivery blocked
            API-->>Web: 409 Evidence integrity failure
            Web-->>Investigator: Display integrity alert
        else Integrity check passed
            alt Protected view requested
                Evidence-->>API: Protected evidence stream
                API-->>Web: 200 Stream response
                Web-->>Investigator: Display protected viewer
                Evidence->>Audit: Record completed view
            else Download requested
                Evidence->>Evidence: Create controlled export and watermark
                Evidence-->>API: Time-limited download reference
                API-->>Web: 200 Secure download
                Web-->>Investigator: Deliver controlled export
                Evidence->>Custody: Record export event
                Custody->>DB: Persist custody event
                Evidence->>Audit: Record completed export
            end
            Audit->>DB: Persist audit event
        end
    end
```

## 07-evidence-verification.mmd

```mermaid
sequenceDiagram
    autonumber
    actor Investigator
    participant Web as Next.js Dashboard
    participant API as FastAPI Verification API
    participant Authz as Authorization Service
    participant Verify as Verification Service
    participant DB as PostgreSQL
    participant Storage as S3 or MinIO
    participant Key as RSA or KMS Key Service
    participant Crypto as Decryption Service
    participant Hash as Hashing Service
    participant Sign as Signature Service
    participant Custody as Chain-of-Custody Service
    participant Audit as Audit Service
    participant Notify as Notification Service

    Investigator->>Web: Select Verify integrity
    Web->>API: POST /api/v1/evidence/{id}/verify
    API->>Authz: Check evidence-verification permission

    alt Verification not authorized
        Authz-->>API: Access denied
        API->>Audit: Record denied verification
        Audit->>DB: Persist audit event
        API-->>Web: 403 Forbidden
        Web-->>Investigator: Display access error
    else Verification authorized
        Authz-->>API: Access granted
        API->>Verify: Verify evidence authenticity and integrity
        Verify->>DB: Load trusted hash, signature, manifest, and key reference
        DB-->>Verify: Trusted verification metadata
        Verify->>Storage: Retrieve encrypted evidence object
        Storage-->>Verify: Ciphertext object
        Verify->>Key: Unwrap AES key
        Key-->>Verify: Authorized data key
        Verify->>Crypto: Decrypt in controlled workspace
        Crypto-->>Verify: Decrypted evidence
        Verify->>Hash: Calculate current SHA-256 hash
        Hash-->>Verify: Current hash
        Verify->>Sign: Validate manifest digital signature
        Sign-->>Verify: Signature result

        alt Signature invalid
            Verify->>DB: Mark authenticity check failed
            Verify->>Notify: Raise security incident
            Notify-->>Investigator: Authenticity failure alert
            Verify->>Custody: Append failed-verification event
            Custody->>DB: Persist custody record
            Verify->>Audit: Record signature failure
            Audit->>DB: Persist audit event
            Verify-->>API: Verification failed
            API-->>Web: 409 Authenticity failure
        else Signature valid
            Verify->>Verify: Compare current and trusted hashes

            alt Hash mismatch
                Verify->>DB: Mark evidence integrity compromised
                Verify->>Notify: Raise integrity incident
                Notify-->>Investigator: Integrity failure alert
                Verify->>Custody: Append failed-verification event
                Custody->>DB: Persist custody record
                Verify->>Audit: Record hash mismatch
                Audit->>DB: Persist audit event
                Verify-->>API: Verification failed
                API-->>Web: 409 Integrity failure
            else Hash matches
                Verify->>DB: Store successful verification result
                Verify->>Custody: Append successful-verification event
                Custody->>DB: Persist custody record
                Verify->>Audit: Record successful verification
                Audit->>DB: Persist audit event
                Verify-->>API: Verified status and report
                API-->>Web: 200 Evidence verified
                Web-->>Investigator: Display verification report
            end
        end
    end
```

## 08-chain-of-custody.mmd

```mermaid
sequenceDiagram
    autonumber
    actor Actor as Authorized User or Trusted Service
    participant Web as Dashboard or Service Client
    participant API as FastAPI Custody API
    participant Authz as Authorization Service
    participant Custody as Chain-of-Custody Service
    participant Evidence as Evidence Service
    participant Hash as Hashing Service
    participant Sign as Signature Service
    participant DB as PostgreSQL
    participant Audit as Audit Service
    participant Notify as Notification Service

    Actor->>Web: Initiate evidence action
    Web->>API: POST /api/v1/evidence/{id}/custody-events
    API->>Authz: Check actor, role, case scope, and action permission

    alt Action not authorized
        Authz-->>API: Access denied
        API->>Audit: Record denied custody action
        Audit->>DB: Persist audit event
        API-->>Web: 403 Forbidden
        Web-->>Actor: Display authorization error
    else Action authorized
        Authz-->>API: Access granted
        API->>Custody: Create custody event
        Custody->>Evidence: Load evidence and current custody state
        Evidence->>DB: Query evidence and latest custody record
        DB-->>Evidence: Evidence and custody state
        Evidence-->>Custody: Current state

        alt Invalid evidence or custody state
            Custody->>Audit: Record invalid custody transition
            Audit->>DB: Persist audit event
            Custody-->>API: Transition rejected
            API-->>Web: 409 Invalid custody transition
            Web-->>Actor: Display custody error
        else State valid
            alt Transfer event
                Custody->>Notify: Request receiving-custodian acceptance
                Notify-->>Actor: Acceptance workflow
                Actor->>Web: Submit acceptance decision
                Web->>API: POST acceptance decision
                API->>Custody: Validate acceptance

                alt Transfer rejected
                    Custody->>Audit: Record rejected transfer
                    Audit->>DB: Persist audit event
                    Custody-->>API: Transfer cancelled
                    API-->>Web: 409 Transfer rejected
                else Transfer accepted
                    Custody->>Custody: Capture sender, receiver, reason, and timestamps
                end
            else Create, view, export, verify, or return event
                Custody->>Custody: Capture action-specific metadata
            end

            Custody->>Custody: Reference previous custody record
            Custody->>Hash: Hash canonical custody payload
            Hash-->>Custody: Custody-record hash
            Custody->>Sign: Digitally sign custody-record hash
            Sign-->>Custody: Digital signature
            Custody->>DB: Append immutable custody record

            alt Persistence failed
                DB-->>Custody: Write failure
                Custody->>Audit: Record custody persistence failure
                Audit->>DB: Persist audit event
                Custody-->>API: Evidence action blocked
                API-->>Web: 503 Custody service unavailable
            else Persistence succeeded
                DB-->>Custody: Custody record ID
                Custody->>Evidence: Execute authorized evidence action
                Evidence-->>Custody: Action result
                Custody->>Audit: Record completed custody action
                Audit->>DB: Persist audit event
                Custody-->>API: Updated custody history
                API-->>Web: 201 Custody event created
                Web-->>Actor: Display updated custody history
            end
        end
    end
```

## 09-report-generation.mmd

```mermaid
sequenceDiagram
    autonumber
    actor User as Security Manager or Investigator
    participant Web as Next.js Dashboard
    participant API as FastAPI Report API
    participant Authz as Authorization Service
    participant Report as Reporting Service
    participant DB as PostgreSQL
    participant Redact as Redaction Service
    participant Hash as Hashing Service
    participant Sign as Signature Service
    participant Storage as S3 or MinIO
    participant Audit as Audit Service

    User->>Web: Select report type, date range, and filters
    Web->>API: POST /api/v1/reports
    API->>Authz: Check report-generation permission and scope

    alt Report request not authorized
        Authz-->>API: Access denied
        API->>Audit: Record denied report request
        Audit->>DB: Persist audit event
        API-->>Web: 403 Forbidden
        Web-->>User: Display authorization error
    else Report request authorized
        Authz-->>API: Access granted
        API->>Report: Validate report parameters

        alt Invalid filters or date range
            Report-->>API: Validation errors
            API-->>Web: 422 Validation error
            Web-->>User: Display report errors
        else Valid request
            Report->>DB: Query incidents, cameras, and evidence metadata
            DB-->>Report: Operational records
            Report->>DB: Query audit and custody records
            DB-->>Report: Forensic records
            Report->>Report: Aggregate statistics and build report model
            Report->>Redact: Apply role-based masking and redaction
            Redact-->>Report: Redacted report model
            Report->>Report: Render report document
            Report->>Hash: Calculate SHA-256 report hash
            Hash-->>Report: Report hash
            Report->>Sign: Digitally sign report hash
            Sign-->>Report: Report signature
            Report->>Storage: Store protected report file
            Storage-->>Report: Storage URI and version
            Report->>DB: Persist report metadata, hash, and signature
            DB-->>Report: Report record created
            Report->>Audit: Record report generation
            Audit->>DB: Persist audit event
            Report-->>API: Report identifier and summary
            API-->>Web: 201 Report generated
            Web-->>User: Display report summary

            alt View requested
                User->>Web: Open report
                Web->>API: GET /api/v1/reports/{id}
                API->>Report: Load authorized report
                Report->>Storage: Retrieve report file
                Storage-->>Report: Protected report
                Report-->>API: Report stream
                API-->>Web: 200 Report stream
                Web-->>User: Display report
            else Export requested
                User->>Web: Export PDF or CSV
                Web->>API: POST /api/v1/reports/{id}/exports
                API->>Report: Create controlled export
                Report->>Storage: Store export object
                Storage-->>Report: Time-limited export reference
                Report->>Audit: Record report export
                Audit->>DB: Persist audit event
                Report-->>API: Secure download reference
                API-->>Web: 200 Secure export
                Web-->>User: Deliver time-limited download
            end
        end
    end
```

## 10-user-management.mmd

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Administrator
    actor User as Affected User
    participant Web as Next.js Dashboard
    participant API as FastAPI User API
    participant Authz as Authorization Service
    participant Users as User Management Service
    participant DB as PostgreSQL
    participant Session as Redis Session Store
    participant Notify as Notification Service
    participant Audit as Audit Service

    Admin->>Web: Open user management
    Web->>API: GET /api/v1/users
    API->>Authz: Check user-management permission

    alt Administrator not authorized
        Authz-->>API: Access denied
        API->>Audit: Record denied administrative access
        Audit->>DB: Persist audit event
        API-->>Web: 403 Forbidden
        Web-->>Admin: Display authorization error
    else Administrator authorized
        Authz-->>API: Access granted
        API->>Users: List users within administrative scope
        Users->>DB: Query users, roles, and account status
        DB-->>Users: User records
        Users-->>API: User list
        API-->>Web: 200 User list
        Web-->>Admin: Display user management screen

        alt Create user
            Admin->>Web: Submit new user and role
            Web->>API: POST /api/v1/users
            API->>Users: Validate identity, uniqueness, and password policy
            Users->>DB: Check email and username uniqueness
            DB-->>Users: Uniqueness result

            alt Duplicate or invalid data
                Users-->>API: Validation or conflict error
                API-->>Web: 409 or 422 error
            else User data valid
                Users->>DB: Create user and role assignments
                Users->>Notify: Send account activation message
                Notify-->>User: Activation notification
                Users->>Audit: Record user creation
                Audit->>DB: Persist audit event
                Users-->>API: Created user
                API-->>Web: 201 User created
            end
        else Update user or assign role
            Admin->>Web: Submit profile or role changes
            Web->>API: PATCH /api/v1/users/{id}
            API->>Authz: Check target scope and role-assignment permission
            Authz-->>API: Access decision

            alt Change violates policy
                API->>Audit: Record denied administrative change
                Audit->>DB: Persist audit event
                API-->>Web: 403 or 409 error
            else Change allowed
                API->>Users: Apply profile and role changes
                Users->>DB: Persist updated user and assignments
                Users->>Session: Invalidate permission cache and sessions
                Users->>Notify: Notify affected user
                Notify-->>User: Account-change notification
                Users->>Audit: Record user update
                Audit->>DB: Persist audit event
                Users-->>API: Updated user
                API-->>Web: 200 User updated
            end
        else Deactivate user
            Admin->>Web: Submit deactivation reason
            Web->>API: POST /api/v1/users/{id}/deactivate
            API->>Users: Check active assignments and evidence custody
            Users->>DB: Query assignments and custody obligations
            DB-->>Users: Dependency result

            alt Active obligations exist
                Users-->>API: Reassignment required
                API-->>Web: 409 Reassign duties first
            else No blocking obligations
                Users->>DB: Deactivate account
                Users->>Session: Revoke active sessions and refresh tokens
                Users->>Notify: Notify affected user
                Notify-->>User: Account deactivation notice
                Users->>Audit: Record account deactivation
                Audit->>DB: Persist audit event
                Users-->>API: Account deactivated
                API-->>Web: 200 User deactivated
            end
        else Reset credentials
            Admin->>Web: Initiate credential reset
            Web->>API: POST /api/v1/users/{id}/credential-reset
            API->>Users: Create time-limited reset token
            Users->>DB: Store hashed reset-token record
            Users->>Session: Revoke existing sessions when required
            Users->>Notify: Deliver secure reset link
            Notify-->>User: Credential-reset notification
            Users->>Audit: Record reset request
            Audit->>DB: Persist audit event
            Users-->>API: Reset initiated
            API-->>Web: 202 Reset initiated
        end
    end
```
