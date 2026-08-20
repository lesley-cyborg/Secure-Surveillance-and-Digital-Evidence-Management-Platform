from __future__ import annotations

from enum import StrEnum


class CameraStatus(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"


class IncidentSourceType(StrEnum):
    AI = "AI"
    MANUAL = "MANUAL"
    EXTERNAL = "EXTERNAL"


class IncidentStatus(StrEnum):
    NEW = "NEW"
    CONFIRMED = "CONFIRMED"
    ASSIGNED = "ASSIGNED"
    INVESTIGATING = "INVESTIGATING"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    REOPENED = "REOPENED"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Priority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class AssignmentRole(StrEnum):
    LEAD_INVESTIGATOR = "LEAD_INVESTIGATOR"
    INVESTIGATOR = "INVESTIGATOR"
    REVIEWER = "REVIEWER"
    RESPONDER = "RESPONDER"


class AssignmentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class EvidenceSourceType(StrEnum):
    AI_CAPTURE = "AI_CAPTURE"
    MANUAL_UPLOAD = "MANUAL_UPLOAD"
    EXTERNAL_IMPORT = "EXTERNAL_IMPORT"


class EvidenceType(StrEnum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"
    OTHER = "OTHER"


class EvidenceStatus(StrEnum):
    PENDING = "PENDING"
    STORED = "STORED"
    VERIFIED = "VERIFIED"
    COMPROMISED = "COMPROMISED"
    QUARANTINED = "QUARANTINED"
    ARCHIVED = "ARCHIVED"


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    HASH_MISMATCH = "HASH_MISMATCH"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    UNAVAILABLE = "UNAVAILABLE"


class CustodyEventType(StrEnum):
    ACQUIRED = "ACQUIRED"
    VIEWED = "VIEWED"
    TRANSFER_INITIATED = "TRANSFER_INITIATED"
    TRANSFER_ACCEPTED = "TRANSFER_ACCEPTED"
    TRANSFER_REJECTED = "TRANSFER_REJECTED"
    EXPORTED = "EXPORTED"
    VERIFIED = "VERIFIED"
    RETURNED = "RETURNED"
    QUARANTINED = "QUARANTINED"


class TransferStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class NotificationChannel(StrEnum):
    DASHBOARD = "DASHBOARD"
    EMAIL = "EMAIL"
    SMS = "SMS"
    PUSH = "PUSH"


class NotificationStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    READ = "READ"


class ReportType(StrEnum):
    INCIDENT = "INCIDENT"
    EVIDENCE = "EVIDENCE"
    CUSTODY = "CUSTODY"
    AUDIT = "AUDIT"
    ANALYTICS = "ANALYTICS"


class ReportFormat(StrEnum):
    PDF = "PDF"
    CSV = "CSV"
    JSON = "JSON"


class ReportStatus(StrEnum):
    QUEUED = "QUEUED"
    GENERATING = "GENERATING"
    GENERATED = "GENERATED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class AuditOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    DENIED = "DENIED"
