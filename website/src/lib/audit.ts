import pool from './db';

export interface AuditEntry {
  firebase_uid: string;
  user_email?: string | null;
  user_display_name?: string | null;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  ip_address?: string | null;
  user_agent?: string | null;
  session_id?: string | null;
  detail?: Record<string, unknown>;
  request_method?: string;
  request_path?: string;
  response_status?: number;
}

export async function audit(entry: AuditEntry): Promise<void> {
  await pool.query(
    `INSERT INTO audit_log (
      firebase_uid, user_email, user_display_name,
      action, resource_type, resource_id,
      ip_address, user_agent, session_id,
      detail,
      request_method, request_path, response_status
    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)`,
    [
      entry.firebase_uid,
      entry.user_email ?? null,
      entry.user_display_name ?? null,
      entry.action,
      entry.resource_type,
      entry.resource_id ?? null,
      entry.ip_address ?? null,
      entry.user_agent ?? null,
      entry.session_id ?? null,
      JSON.stringify(entry.detail ?? {}),
      entry.request_method ?? null,
      entry.request_path ?? null,
      entry.response_status ?? null,
    ]
  );
}
