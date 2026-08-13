export type Role = "sales" | "procurement" | "manager";

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: Role;
}

export interface InboxMessage {
  id: string;
  sender: string;
  subject: string;
  body: string;
  received_at: string;
  customer_id: string | null;
  processed: boolean;
}

export interface Inquiry {
  id: string;
  inbox_message_id: string | null;
  customer_id: string | null;
  status: string;
  raw_text: string;
  extracted_json: Record<string, any>;
  missing_fields: string[];
  trace_id: string;
  created_at: string;
}

export interface Evidence {
  chunk_id: string;
  document_id: string;
  title: string;
  content: string;
  page: number | null;
  score: number;
  metadata: Record<string, any>;
}

export interface AnswerCitation {
  index: number;
  chunk_id: string;
  document_id: string;
  title: string;
  page: number | null;
  snippet: string;
}

export interface KnowledgeAnswer {
  answer: string;
  answer_type: "grounded" | "calculated" | "insufficient" | "requires_pricing_workflow";
  citations: AnswerCitation[];
  evidence: Evidence[];
  grounded: boolean;
  model: string;
  retrieval_mode: "hybrid" | "dense" | "bm25";
}

export interface Quote {
  id: string;
  inquiry_id: string;
  version: number;
  status: string;
  currency: string;
  quantity: number;
  proposed_unit_price: string;
  public_json: Record<string, any>;
  internal_json: Record<string, any> | null;
  evidence_json: Evidence[];
  risk_flags: string[];
  draft_text: string;
  pdf_path: string | null;
  created_at: string;
}

export interface DocumentRecord {
  id: string;
  title: string;
  document_type: string;
  classification: string;
  sku: string | null;
  customer_id: string | null;
  versions: Array<{ id: string; version: number; status: string; valid_from: string; valid_to: string }>;
}
