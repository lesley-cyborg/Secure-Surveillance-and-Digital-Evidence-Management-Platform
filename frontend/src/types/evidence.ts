export type EvidenceStatus =
  | "PENDING"
  | "STORED"
  | "VERIFIED"
  | "COMPROMISED"
  | "QUARANTINED"
  | "ARCHIVED";

export type EvidenceSourceType =
  | "AI_CAPTURE"
  | "MANUAL_UPLOAD"
  | "EXTERNAL_IMPORT";

export type EvidenceType =
  | "IMAGE"
  | "VIDEO"
  | "AUDIO"
  | "DOCUMENT"
  | "OTHER";

export type VerificationStatus =
  | "VERIFIED"
  | "HASH_MISMATCH"
  | "SIGNATURE_INVALID"
  | "UNAVAILABLE"
  | string;

/** Matches backend EvidenceResponse (camelCase JSON) */
export type Evidence = {
  id: string;
  evidenceNumber: string;
  incidentId: string;
  sourceDetectionId?: string | null;
  submittedByUserId?: string | null;
  sourceType: EvidenceSourceType;
  evidenceType: EvidenceType;
  originalFilename: string;
  mimeType: string;
  fileSizeBytes: number;
  originalSha256: string;
  encryptedSha256: string;
  status: EvidenceStatus;
  capturedAt: string;
  ingestedAt: string;
  createdAt: string;
};

export type EvidenceListResponse = {
  items: Evidence[];
  total: number;
};

/** Matches EvidenceVerificationResponse */
export type EvidenceVerification = {
  id: string;
  evidenceId: string;
  verifiedByUserId?: string | null;
  expectedSha256: string;
  calculatedSha256?: string | null;
  hashMatches: boolean;
  signatureValid: boolean;
  verificationStatus: VerificationStatus;
  failureReason?: string | null;
  verifiedAt: string;
};