from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


@contextmanager
def connect(db_path: str) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
        # Case Comments Table
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS case_comments (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              case_id TEXT NOT NULL,
              author_id INTEGER NOT NULL,
              comment_text TEXT NOT NULL,
              file_id TEXT,
              is_private INTEGER NOT NULL DEFAULT 1,
              is_read INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
              FOREIGN KEY (author_id) REFERENCES users(user_id)
            );
            """
        )
    finally:
        conn.close()


def init_db(db_path: str) -> None:
    with connect(db_path) as conn:
        # Installments Table Migration/Creation
        try:
            conn.execute("ALTER TABLE interviews ADD COLUMN admin_24h_sent INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE installments ADD COLUMN is_for_interview INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE installments ADD COLUMN is_for_contract INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE installments ADD COLUMN is_for_preapproval INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE installments ADD COLUMN is_for_initial INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        # Cases Table Migration for new files
        try:
            conn.execute("ALTER TABLE cases ADD COLUMN employer_contract_file_id TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE cases ADD COLUMN pre_approval_file_id TEXT")
        except sqlite3.OperationalError:
            pass

        # New Table for pending notifications/reminders
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pending_reminders (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              case_id TEXT NOT NULL,
              installment_id INTEGER NOT NULL,
              reminder_type TEXT NOT NULL, -- 'interview', 'contract', 'preapproval'
              sent_count INTEGER DEFAULT 0,
              last_sent_at TEXT,
              is_completed INTEGER DEFAULT 0,
              created_at TEXT,
              FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
              FOREIGN KEY (installment_id) REFERENCES installments(id) ON DELETE CASCADE
            );
            """
        )
        try:
            conn.execute("ALTER TABLE pending_reminders ADD COLUMN created_at TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE licenses ADD COLUMN blogger_platform TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE licenses ADD COLUMN blogger_platform_address TEXT")
        except sqlite3.OperationalError:
            pass

        # Migration for licenses to add 'blogger' type and remove 'is_special'
        try:
            # Check if 'blogger' is already in the constraint
            cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='licenses'")
            table_sql = cursor.fetchone()[0]
            if "'blogger'" not in table_sql:
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute("""
                    CREATE TABLE licenses_new (
                      code TEXT PRIMARY KEY,
                      license_type TEXT NOT NULL CHECK (license_type IN ('agency','direct_client','blogger')),
                      capacity INTEGER NOT NULL,
                      used_count INTEGER NOT NULL DEFAULT 0,
                      is_active INTEGER NOT NULL DEFAULT 1,
                      agency_name TEXT,
                      agency_phone TEXT,
                      agency_address TEXT,
                      created_at TEXT NOT NULL
                    )
                """)
                # We intentionally drop is_special here by not including it in the INSERT
                conn.execute("INSERT INTO licenses_new(code, license_type, capacity, used_count, is_active, agency_name, agency_phone, agency_address, created_at) SELECT code, license_type, capacity, used_count, is_active, agency_name, agency_phone, agency_address, created_at FROM licenses")
                conn.execute("DROP TABLE licenses")
                conn.execute("ALTER TABLE licenses_new RENAME TO licenses")
                conn.execute("PRAGMA foreign_keys = ON")
        except Exception as e:
            print(f"Migration error for licenses: {e}")

        # Migration for cases table to add 'blogger' type
        try:
            # Check if 'blogger' is already in the constraint
            cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='cases'")
            table_sql = cursor.fetchone()[0]
            if "'blogger'" not in table_sql:
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute("""
                    CREATE TABLE cases_new (
                      case_id TEXT PRIMARY KEY,
                      owner_type TEXT NOT NULL CHECK (owner_type IN ('agency','direct_client','blogger')),
                      owner_license_code TEXT NOT NULL,
                      client_name TEXT NOT NULL,
                      total_amount REAL NOT NULL,
                      installments_count INTEGER NOT NULL,
                      field_of_study TEXT,
                      payment_notes TEXT,
                      status TEXT NOT NULL DEFAULT 'red' CHECK (status IN ('red','yellow','green','archived')),
                      yellow_reason TEXT,
                      prev_status TEXT,
                      is_active INTEGER NOT NULL DEFAULT 1,
                      in_requests_count INTEGER NOT NULL DEFAULT 0,
                      presentations_count INTEGER NOT NULL DEFAULT 0,
                      contract_file_id TEXT,
                      last_counter_update TEXT,
                      created_at TEXT NOT NULL,
                      FOREIGN KEY (owner_license_code) REFERENCES licenses(code)
                    )
                """)
                conn.execute("""
                    INSERT INTO cases_new(case_id, owner_type, owner_license_code, client_name, total_amount, installments_count, field_of_study, payment_notes, status, yellow_reason, prev_status, is_active, in_requests_count, presentations_count, contract_file_id, last_counter_update, created_at)
                    SELECT case_id, owner_type, owner_license_code, client_name, total_amount, installments_count, field_of_study, payment_notes, status, yellow_reason, prev_status, is_active, in_requests_count, presentations_count, contract_file_id, last_counter_update, created_at FROM cases
                """)
                conn.execute("DROP TABLE cases")
                conn.execute("ALTER TABLE cases_new RENAME TO cases")
                conn.execute("PRAGMA foreign_keys = ON")
        except Exception as e:
            print(f"Migration error for cases: {e}")

        # Migration for users table to add 'blogger' role
        try:
            cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
            table_sql = cursor.fetchone()[0]
            if "'blogger'" not in table_sql:
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute("""
                    CREATE TABLE users_new (
                      user_id INTEGER PRIMARY KEY,
                      role TEXT NOT NULL CHECK (role IN ('super_admin','admin','agency','direct_client','blogger')),
                      phone TEXT,
                      full_name TEXT,
                      license_code TEXT,
                      is_phone_verified INTEGER NOT NULL DEFAULT 0,
                      permissions_json TEXT,
                      created_at TEXT NOT NULL,
                      FOREIGN KEY (license_code) REFERENCES licenses(code)
                    )
                """)
                conn.execute("""
                    INSERT INTO users_new(user_id, role, phone, full_name, license_code, is_phone_verified, permissions_json, created_at)
                    SELECT user_id, role, phone, full_name, license_code, is_phone_verified, permissions_json, created_at FROM users
                """)
                conn.execute("DROP TABLE users")
                conn.execute("ALTER TABLE users_new RENAME TO users")
                conn.execute("PRAGMA foreign_keys = ON")
        except Exception as e:
            print(f"Migration error for users: {e}")

        # Migration for multi-field support
        try:
            # Check if case_fields has data, if not migrate from cases
            count = conn.execute("SELECT COUNT(*) FROM case_fields").fetchone()[0]
            if count == 0:
                conn.execute("""
                    INSERT INTO case_fields (case_id, field_name, status, yellow_reason, requests_count, presentations_count, created_at)
                    SELECT case_id, field_of_study, status, yellow_reason, in_requests_count, presentations_count, created_at
                    FROM cases
                    WHERE field_of_study IS NOT NULL AND field_of_study != ''
                """)
        except Exception as e:
            print(f"Migration for case_fields error: {e}")

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS licenses (
              code TEXT PRIMARY KEY,
              license_type TEXT NOT NULL CHECK (license_type IN ('agency','direct_client','blogger')),
              capacity INTEGER NOT NULL,
              used_count INTEGER NOT NULL DEFAULT 0,
              is_active INTEGER NOT NULL DEFAULT 1,
              agency_name TEXT,
              agency_phone TEXT,
              agency_address TEXT,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
              user_id INTEGER PRIMARY KEY,
              role TEXT NOT NULL CHECK (role IN ('super_admin','admin','agency','direct_client','blogger')),
              phone TEXT,
              full_name TEXT,
              license_code TEXT,
              is_phone_verified INTEGER NOT NULL DEFAULT 0,
              permissions_json TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY (license_code) REFERENCES licenses(code)
            );

            CREATE TABLE IF NOT EXISTS cases (
              case_id TEXT PRIMARY KEY,
              owner_type TEXT NOT NULL CHECK (owner_type IN ('agency','direct_client','blogger')),
              owner_license_code TEXT NOT NULL,
              client_name TEXT NOT NULL,
              total_amount REAL NOT NULL,
              installments_count INTEGER NOT NULL,
              field_of_study TEXT,
              payment_notes TEXT,
              status TEXT NOT NULL DEFAULT 'red' CHECK (status IN ('red','yellow','green','archived')),
              yellow_reason TEXT,
              prev_status TEXT,
              is_active INTEGER NOT NULL DEFAULT 1,
              in_requests_count INTEGER NOT NULL DEFAULT 0,
              presentations_count INTEGER NOT NULL DEFAULT 0,
              contract_file_id TEXT,
              last_counter_update TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY (owner_license_code) REFERENCES licenses(code)
            );

            CREATE TABLE IF NOT EXISTS case_fields (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              case_id TEXT NOT NULL,
              field_name TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'red' CHECK (status IN ('red','yellow','green')),
              yellow_reason TEXT,
              requests_count INTEGER NOT NULL DEFAULT 0,
              presentations_count INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
            );
            """
        )
        # Ensure columns exist for older databases
        try:
            conn.execute("ALTER TABLE cases ADD COLUMN in_requests_count INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE cases ADD COLUMN presentations_count INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE cases ADD COLUMN last_counter_update TEXT")
        except sqlite3.OperationalError:
            pass

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS installments (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              case_id TEXT NOT NULL,
              idx INTEGER NOT NULL,
              amount REAL NOT NULL,
              is_paid INTEGER NOT NULL DEFAULT 0,
              FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
              UNIQUE(case_id, idx)
            );

            CREATE TABLE IF NOT EXISTS tickets (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_by_user_id INTEGER NOT NULL,
              created_by_role TEXT NOT NULL,
              subject TEXT,
              status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
              assigned_admin_id INTEGER,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY (created_by_user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS ticket_messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ticket_id INTEGER NOT NULL,
              sender_user_id INTEGER NOT NULL,
              sender_role TEXT NOT NULL,
              message_type TEXT NOT NULL,
              text TEXT,
              file_id TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
              FOREIGN KEY (sender_user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS interviews (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              case_id TEXT NOT NULL,
              raw_email_text TEXT NOT NULL,
              extracted_json TEXT,
              scheduled_at_iso TEXT,
              meeting_link TEXT,
              employer_name TEXT,
              company_name TEXT,
              city TEXT,
              platform TEXT,
              username TEXT,
              password TEXT,
              status TEXT DEFAULT 'pending' CHECK (status IN ('pending','confirmed','cancelled','completed','no_show')),
              reminder_24h_sent INTEGER DEFAULT 0,
              reminder_12h_sent INTEGER DEFAULT 0,
              reminder_1h_sent INTEGER DEFAULT 0,
              followup_30m_sent INTEGER DEFAULT 0,
              followup_count INTEGER DEFAULT 0,
              followup_result TEXT,
              followup_notes TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS admin_permissions (
              user_id INTEGER PRIMARY KEY,
              can_manage_licenses INTEGER DEFAULT 0,
              can_manage_cases INTEGER DEFAULT 0,
              can_change_status INTEGER DEFAULT 0,
              can_view_phones INTEGER DEFAULT 0,
              can_manage_tickets INTEGER DEFAULT 0,
              can_reply_tickets INTEGER DEFAULT 0,
              can_send_messages INTEGER DEFAULT 0,
              can_broadcast INTEGER DEFAULT 0,
              can_manage_interviews INTEGER DEFAULT 0,
              can_manage_admins INTEGER DEFAULT 0,
              FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              sender_user_id INTEGER NOT NULL,
              sender_role TEXT NOT NULL,
              receiver_user_id INTEGER,
              receiver_license_code TEXT,
              message_type TEXT NOT NULL,
              text TEXT,
              file_id TEXT,
              is_sent INTEGER DEFAULT 0,
              error_log TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY (sender_user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS case_documents (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              case_id TEXT NOT NULL,
              doc_type TEXT NOT NULL,
              file_id TEXT,
              file_name TEXT,
              status TEXT DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
              rejection_reason TEXT,
              uploaded_by_user_id INTEGER,
              created_at TEXT NOT NULL,
              FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS document_requests (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              case_id TEXT NOT NULL,
              status TEXT DEFAULT 'in_progress' CHECK (status IN ('in_progress','submitted','approved','rejected')),
              submitted_at TEXT,
              reviewed_by_admin_id INTEGER,
              reviewed_at TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS scheduled_messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              sender_user_id INTEGER NOT NULL,
              message_text TEXT,
              file_id TEXT,
              filter_type TEXT,
              filter_license_type TEXT,
              filter_status TEXT,
              filter_agency_code TEXT,
              filter_active_only INTEGER,
              scheduled_at TEXT NOT NULL,
              is_sent INTEGER DEFAULT 0,
              sent_count INTEGER DEFAULT 0,
              failed_count INTEGER DEFAULT 0,
              created_at TEXT NOT NULL,
              FOREIGN KEY (sender_user_id) REFERENCES users(user_id)
            );
            """
        )


@dataclass(frozen=True)
class License:
    code: str
    license_type: str
    capacity: int
    used_count: int
    is_active: int
    agency_name: str | None
    agency_phone: str | None
    agency_address: str | None
    blogger_platform: str | None = None
    blogger_platform_address: str | None = None


def get_license(db_path: str, code: str) -> License | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT code, license_type, capacity, used_count, is_active, agency_name, agency_phone, agency_address, blogger_platform, blogger_platform_address FROM licenses WHERE code = ?",
            (code,),
        ).fetchone()
        if not row:
            return None
        return License(
            code=row["code"],
            license_type=row["license_type"],
            capacity=row["capacity"],
            used_count=row["used_count"],
            is_active=row["is_active"],
            agency_name=row["agency_name"],
            agency_phone=row["agency_phone"],
            agency_address=row["agency_address"],
            blogger_platform=row["blogger_platform"],
            blogger_platform_address=row["blogger_platform_address"],
        )


def upsert_user_on_license_join(
    db_path: str,
    user_id: int,
    role: str,
    full_name: str | None,
    license_code: str,
) -> None:
    with connect(db_path) as conn:
        license_val = license_code if license_code else None
        
        # Check if user is already using this license
        old_user = conn.execute("SELECT license_code FROM users WHERE user_id = ?", (user_id,)).fetchone()
        already_joined = old_user and old_user["license_code"] == license_val

        conn.execute(
            """
            INSERT INTO users(user_id, role, full_name, license_code, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              role=excluded.role,
              full_name=COALESCE(excluded.full_name, users.full_name),
              license_code=excluded.license_code
            """,
            (user_id, role, full_name, license_val, _utc_now_iso()),
        )
        
        if license_val and not already_joined:
            conn.execute("UPDATE licenses SET used_count = used_count + 1 WHERE code = ?", (license_val,))


def set_user_phone_verified(db_path: str, user_id: int, phone: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET phone = ?, is_phone_verified = 1 WHERE user_id = ?",
            (phone, user_id),
        )


def get_user(db_path: str, user_id: int) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT user_id, role, phone, full_name, license_code, is_phone_verified, permissions_json FROM users WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "user_id": row["user_id"],
            "role": row["role"],
            "phone": row["phone"],
            "full_name": row["full_name"],
            "license_code": row["license_code"],
            "is_phone_verified": row["is_phone_verified"],
            "permissions": json.loads(row["permissions_json"]) if row["permissions_json"] else None,
        }


def get_all_licenses(db_path: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT code, license_type, capacity, used_count, is_active, agency_name, agency_phone, agency_address, blogger_platform, blogger_platform_address, created_at FROM licenses ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def create_license(db_path: str, code: str, license_type: str, capacity: int, agency_name: str | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO licenses(code, license_type, capacity, used_count, is_active, agency_name, created_at) VALUES (?, ?, ?, 0, 1, ?, ?)",
            (code, license_type, capacity, agency_name, _utc_now_iso()),
        )


def update_license_capacity(db_path: str, code: str, new_capacity: int) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE licenses SET capacity = ? WHERE code = ?", (new_capacity, code))


def toggle_license_active(db_path: str, code: str) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE licenses SET is_active = NOT is_active WHERE code = ?", (code,))


def delete_license(db_path: str, code: str) -> None:
    with connect(db_path) as conn:
        # First, nullify or handle users associated with this license
        conn.execute("UPDATE users SET license_code = NULL WHERE license_code = ?", (code,))
        # Then delete cases associated with this license
        conn.execute("DELETE FROM cases WHERE owner_license_code = ?", (code,))
        # Finally delete the license
        conn.execute("DELETE FROM licenses WHERE code = ?", (code,))


def get_license_members(db_path: str, code: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT user_id, role, phone, full_name, is_phone_verified FROM users WHERE license_code = ?",
            (code,),
        ).fetchall()
        return [dict(r) for r in rows]


def kick_user_from_license(db_path: str, user_id: int) -> None:
    with connect(db_path) as conn:
        user = conn.execute("SELECT license_code FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if user and user["license_code"]:
            conn.execute("UPDATE licenses SET used_count = MAX(0, used_count - 1) WHERE code = ?", (user["license_code"],))
        conn.execute("UPDATE users SET license_code = NULL, is_phone_verified = 0 WHERE user_id = ?", (user_id,))


def update_case_counters(db_path: str, case_id: str, in_requests: int | None = None, presentations: int | None = None) -> None:
    with connect(db_path) as conn:
        if in_requests is not None:
            conn.execute(
                "UPDATE cases SET in_requests_count = ?, last_counter_update = ? WHERE case_id = ?",
                (in_requests, _utc_now_iso(), case_id)
            )
        if presentations is not None:
            conn.execute(
                "UPDATE cases SET presentations_count = ?, last_counter_update = ? WHERE case_id = ?",
                (presentations, _utc_now_iso(), case_id)
            )

def update_case_field_counters(db_path: str, field_id: int, requests: int | None = None, presentations: int | None = None) -> None:
    with connect(db_path) as conn:
        if requests is not None:
            conn.execute(
                "UPDATE case_fields SET requests_count = ? WHERE id = ?",
                (requests, field_id)
            )
        if presentations is not None:
            conn.execute(
                "UPDATE case_fields SET presentations_count = ? WHERE id = ?",
                (presentations, field_id)
            )

def get_case_fields(db_path: str, case_id: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM case_fields WHERE case_id = ? ORDER BY created_at ASC",
            (case_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_case_field(db_path: str, field_id: int) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM case_fields WHERE id = ?",
            (field_id,)
        ).fetchone()
        return dict(row) if row else None

def add_case_field(db_path: str, case_id: str, field_name: str) -> int:
    with connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO case_fields (case_id, field_name, status, created_at) VALUES (?, ?, 'red', ?)",
            (case_id, field_name, _utc_now_iso())
        )
        return cursor.lastrowid

def delete_case_field(db_path: str, field_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM case_fields WHERE id = ?", (field_id,))

def update_case_field_status(db_path: str, field_id: int, status: str, yellow_reason: str | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE case_fields SET status = ?, yellow_reason = ? WHERE id = ?",
            (status, yellow_reason, field_id)
        )


def get_all_cases(db_path: str, license_code: str | None = None, limit: int | None = None, offset: int | None = None) -> list[dict]:
    with connect(db_path) as conn:
        query = "SELECT case_id, owner_type, owner_license_code, client_name, total_amount, installments_count, field_of_study, payment_notes, status, yellow_reason, prev_status, is_active, in_requests_count, presentations_count, last_counter_update, created_at FROM cases"
        params = []
        if license_code:
            query += " WHERE owner_license_code = ?"
            params.append(license_code)
        
        query += " ORDER BY created_at DESC"
        
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        if offset is not None:
            query += " OFFSET ?"
            params.append(offset)
            
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def count_all_cases(db_path: str, license_code: str | None = None) -> int:
    with connect(db_path) as conn:
        query = "SELECT COUNT(*) FROM cases"
        params = []
        if license_code:
            query += " WHERE owner_license_code = ?"
            params.append(license_code)
        
        row = conn.execute(query, params).fetchone()
        return row[0] if row else 0


def get_case(db_path: str, case_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT case_id, owner_type, owner_license_code, client_name, total_amount, installments_count, field_of_study, payment_notes, status, yellow_reason, prev_status, is_active, in_requests_count, presentations_count, contract_file_id, last_counter_update, created_at FROM cases WHERE case_id = ?",
            (case_id,),
        ).fetchone()
        return dict(row) if row else None


def update_case_contract(db_path: str, case_id: str, file_id: str | None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE cases SET contract_file_id = ? WHERE case_id = ?",
            (file_id, case_id)
        )


def create_case(db_path: str, case_id: str, owner_type: str, owner_license_code: str, client_name: str, total_amount: float, installments_count: int, fields: list[str], payment_notes: str | None = None) -> None:
    with connect(db_path) as conn:
        # field_of_study is now the first field from the list for backward compatibility
        field_of_study = fields[0] if fields else ""
        conn.execute(
            "INSERT INTO cases(case_id, owner_type, owner_license_code, client_name, total_amount, installments_count, field_of_study, payment_notes, status, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'red', 1, ?)",
            (case_id, owner_type, owner_license_code, client_name, total_amount, installments_count, field_of_study, payment_notes, _utc_now_iso()),
        )
        for field_name in fields:
            conn.execute(
                "INSERT INTO case_fields (case_id, field_name, status, created_at) VALUES (?, ?, 'red', ?)",
                (case_id, field_name, _utc_now_iso())
            )


def update_case_status(db_path: str, case_id: str, status: str, yellow_reason: str | None = None) -> None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT status FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        prev = row["status"] if row else "red"
        
        # If status is 'archived', we also set is_active = 0
        is_active = 0 if status == 'archived' else 1
        
        conn.execute(
            "UPDATE cases SET status = ?, yellow_reason = ?, prev_status = ?, is_active = ? WHERE case_id = ?",
            (status, yellow_reason, prev, is_active, case_id),
        )


def add_case_comment(db_path: str, case_id: str, author_id: int, text: str, is_private: int = 1, file_id: str | None = None) -> int:
    with connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO case_comments (case_id, author_id, comment_text, is_private, file_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (case_id, author_id, text, is_private, file_id, _utc_now_iso()),
        )
        return cursor.lastrowid


def update_case_comment(db_path: str, comment_id: int, text: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE case_comments SET comment_text = ? WHERE id = ?",
            (text, comment_id),
        )


def delete_case_comment(db_path: str, comment_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM case_comments WHERE id = ?", (comment_id,))


def set_comment_read(db_path: str, comment_id: int) -> dict | None:
    with connect(db_path) as conn:
        conn.execute("UPDATE case_comments SET is_read = 1 WHERE id = ?", (comment_id,))
        row = conn.execute("SELECT * FROM case_comments WHERE id = ?", (comment_id,)).fetchone()
        return dict(row) if row else None


def get_case_comment(db_path: str, comment_id: int) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM case_comments WHERE id = ?", (comment_id,)).fetchone()
        return dict(row) if row else None


def get_case_comments(db_path: str, case_id: str, only_public: bool = False) -> list[dict]:
    with connect(db_path) as conn:
        query = "SELECT c.*, u.full_name as author_name FROM case_comments c JOIN users u ON c.author_id = u.user_id WHERE c.case_id = ?"
        if only_public:
            query += " AND c.is_private = 0"
        query += " ORDER BY c.created_at DESC"
        rows = conn.execute(query, (case_id,)).fetchall()
        return [dict(r) for r in rows]


def get_users_by_license(db_path: str, license_code: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT user_id, role, full_name, phone FROM users WHERE license_code = ?",
            (license_code,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_case(db_path: str, case_id: str) -> None:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM cases WHERE case_id = ?", (case_id,))


def get_installments(db_path: str, case_id: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM installments WHERE case_id = ? ORDER BY idx",
            (case_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_installment_mapping(db_path: str, installment_id: int, event_type: str, value: int) -> None:
    column_map = {
        "interview": "is_for_interview",
        "contract": "is_for_contract",
        "preapproval": "is_for_preapproval",
        "initial": "is_for_initial"
    }
    column = column_map.get(event_type)
    if not column:
        return
    with connect(db_path) as conn:
        conn.execute(f"UPDATE installments SET {column} = ? WHERE id = ?", (value, installment_id))

def get_mapped_installments(db_path: str, case_id: str, event_type: str) -> list[dict]:
    mapping = {
        "interview": "is_for_interview",
        "contract": "is_for_contract",
        "preapproval": "is_for_preapproval",
        "initial": "is_for_initial"
    }
    column = mapping.get(event_type)
    if not column:
        return []
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM installments WHERE case_id = ? AND {column} = ? ORDER BY idx",
            (case_id, 1)
        ).fetchall()
        return [dict(r) for r in rows]

def update_case_file(db_path: str, case_id: str, file_type: str, file_id: str) -> None:
    column = "employer_contract_file_id" if file_type == "employer_contract" else "pre_approval_file_id"
    with connect(db_path) as conn:
        conn.execute(f"UPDATE cases SET {column} = ? WHERE case_id = ?", (file_id, case_id))

def add_pending_reminder(db_path: str, case_id: str, installment_id: int, reminder_type: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO pending_reminders (case_id, installment_id, reminder_type, created_at) VALUES (?, ?, ?, ?)",
            (case_id, installment_id, reminder_type, _utc_now_iso())
        )

def get_pending_reminders(db_path: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM pending_reminders WHERE is_completed = 0").fetchall()
        return [dict(r) for r in rows]

def update_reminder_status(db_path: str, reminder_id: int, sent_count: int, is_completed: int = 0) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE pending_reminders SET sent_count = ?, last_sent_at = ?, is_completed = ? WHERE id = ?",
            (sent_count, _utc_now_iso(), is_completed, reminder_id)
        )


def update_installment_payment(db_path: str, installment_id: int, is_paid: int) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE installments SET is_paid = ? WHERE id = ?",
            (is_paid, installment_id),
        )

def add_installments(db_path: str, case_id: str, amounts: list[float]) -> None:
    with connect(db_path) as conn:
        for idx, amount in enumerate(amounts, 1):
            conn.execute(
                "INSERT OR REPLACE INTO installments(case_id, idx, amount) VALUES (?, ?, ?)",
                (case_id, idx, amount),
            )


def get_all_tickets(db_path: str, user_id: int | None = None, status: str | None = None) -> list[dict]:
    with connect(db_path) as conn:
        query = "SELECT id, created_by_user_id, created_by_role, subject, status, assigned_admin_id, created_at, updated_at FROM tickets WHERE 1=1"
        params = []
        if user_id:
            query += " AND created_by_user_id = ?"
            params.append(user_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def create_ticket(db_path: str, user_id: int, role: str, subject: str | None = None) -> int:
    with connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO tickets(created_by_user_id, created_by_role, subject, status, created_at, updated_at) VALUES (?, ?, ?, 'open', ?, ?)",
            (user_id, role, subject, _utc_now_iso(), _utc_now_iso()),
        )
        return cursor.lastrowid


def get_ticket(db_path: str, ticket_id: int) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, created_by_user_id, created_by_role, subject, status, assigned_admin_id, created_at, updated_at FROM tickets WHERE id = ?",
            (ticket_id,),
        ).fetchone()
        return dict(row) if row else None


def add_ticket_message(db_path: str, ticket_id: int, user_id: int, role: str, message_type: str, text: str | None = None, file_id: str | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO ticket_messages(ticket_id, sender_user_id, sender_role, message_type, text, file_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticket_id, user_id, role, message_type, text, file_id, _utc_now_iso()),
        )
        conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (_utc_now_iso(), ticket_id))


def get_ticket_messages(db_path: str, ticket_id: int) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, ticket_id, sender_user_id, sender_role, message_type, text, file_id, created_at FROM ticket_messages WHERE ticket_id = ? ORDER BY created_at ASC",
            (ticket_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def close_ticket(db_path: str, ticket_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE tickets SET status = 'closed', updated_at = ? WHERE id = ?", (_utc_now_iso(), ticket_id))


def claim_ticket(db_path: str, ticket_id: int, admin_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE tickets SET assigned_admin_id = ?, updated_at = ? WHERE id = ?", (admin_id, _utc_now_iso(), ticket_id))


def get_admin_permissions(db_path: str, user_id: int) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT user_id, can_manage_licenses, can_manage_cases, can_change_status, can_view_phones, can_manage_tickets, can_reply_tickets, can_send_messages, can_broadcast, can_manage_interviews, can_manage_admins FROM admin_permissions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def set_admin_permissions(db_path: str, user_id: int, permissions: dict) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO admin_permissions(user_id, can_manage_licenses, can_manage_cases, can_change_status, can_view_phones, can_manage_tickets, can_reply_tickets, can_send_messages, can_broadcast, can_manage_interviews, can_manage_admins)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              can_manage_licenses = excluded.can_manage_licenses,
              can_manage_cases = excluded.can_manage_cases,
              can_change_status = excluded.can_change_status,
              can_view_phones = excluded.can_view_phones,
              can_manage_tickets = excluded.can_manage_tickets,
              can_reply_tickets = excluded.can_reply_tickets,
              can_send_messages = excluded.can_send_messages,
              can_broadcast = excluded.can_broadcast,
              can_manage_interviews = excluded.can_manage_interviews,
              can_manage_admins = excluded.can_manage_admins
            """,
            (user_id, permissions.get("can_manage_licenses", 0), permissions.get("can_manage_cases", 0), permissions.get("can_change_status", 0), permissions.get("can_view_phones", 0), permissions.get("can_manage_tickets", 0), permissions.get("can_reply_tickets", 0), permissions.get("can_send_messages", 0), permissions.get("can_broadcast", 0), permissions.get("can_manage_interviews", 0), permissions.get("can_manage_admins", 0)),
        )


def get_all_admin_users(db_path: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT u.user_id, u.role, u.full_name, u.phone, p.can_manage_licenses, p.can_manage_cases, p.can_change_status, p.can_view_phones, p.can_manage_tickets, p.can_reply_tickets, p.can_send_messages, p.can_broadcast, p.can_manage_interviews, p.can_manage_admins FROM users u LEFT JOIN admin_permissions p ON u.user_id = p.user_id WHERE u.role IN ('super_admin', 'admin')"
        ).fetchall()
        return [dict(r) for r in rows]


def save_message(db_path: str, sender_id: int, sender_role: str, receiver_id: int | None, receiver_license: str | None, message_type: str, text: str | None = None, file_id: str | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO messages(sender_user_id, sender_role, receiver_user_id, receiver_license_code, message_type, text, file_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sender_id, sender_role, receiver_id, receiver_license, message_type, text, file_id, _utc_now_iso()),
        )


def get_messages_for_user(db_path: str, user_id: int) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, sender_user_id, sender_role, message_type, text, file_id, created_at FROM messages WHERE receiver_user_id = ? ORDER BY created_at DESC LIMIT 50",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_case_documents(db_path: str, case_id: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, case_id, doc_type, file_id, file_name, status, rejection_reason, uploaded_by_user_id, created_at FROM case_documents WHERE case_id = ? ORDER BY created_at ASC",
            (case_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_case_document(db_path: str, case_id: str, doc_type: str, file_id: str | None, file_name: str | None, user_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO case_documents(case_id, doc_type, file_id, file_name, status, uploaded_by_user_id, created_at) VALUES (?, ?, ?, ?, 'pending', ?, ?)",
            (case_id, doc_type, file_id, file_name, user_id, _utc_now_iso()),
        )


def update_document_status(db_path: str, doc_id: int, status: str, reason: str | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE case_documents SET status = ?, rejection_reason = ? WHERE id = ?",
            (status, reason, doc_id),
        )


def create_document_request(db_path: str, case_id: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO document_requests(case_id, status, created_at) VALUES (?, 'in_progress', ?)",
            (case_id, _utc_now_iso()),
        )


def get_document_request(db_path: str, case_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, case_id, status, submitted_at, reviewed_by_admin_id, reviewed_at, created_at FROM document_requests WHERE case_id = ?",
            (case_id,),
        ).fetchone()
        return dict(row) if row else None


def submit_document_request(db_path: str, case_id: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE document_requests SET status = 'submitted', submitted_at = ? WHERE case_id = ?",
            (_utc_now_iso(), case_id),
        )


def approve_document_request(db_path: str, case_id: str, admin_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE document_requests SET status = 'approved', reviewed_by_admin_id = ?, reviewed_at = ? WHERE case_id = ?",
            (admin_id, _utc_now_iso(), case_id),
        )


def reject_document_request(db_path: str, case_id: str, admin_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE document_requests SET status = 'rejected', reviewed_by_admin_id = ?, reviewed_at = ? WHERE case_id = ?",
            (admin_id, _utc_now_iso(), case_id),
        )


def get_interviews(db_path: str, case_id: str | None = None) -> list[dict]:
    with connect(db_path) as conn:
        if case_id:
            rows = conn.execute(
                "SELECT * FROM interviews WHERE case_id = ? ORDER BY scheduled_at_iso DESC",
                (case_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM interviews ORDER BY scheduled_at_iso DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def get_interviews_between(db_path: str, start_iso: str, end_iso: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM interviews
            WHERE scheduled_at_iso IS NOT NULL
              AND scheduled_at_iso >= ?
              AND scheduled_at_iso <= ?
            ORDER BY scheduled_at_iso ASC
            """,
            (start_iso, end_iso),
        ).fetchall()
        return [dict(r) for r in rows]


def create_interview(db_path: str, case_id: str, raw_text: str) -> int:
    with connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO interviews(case_id, raw_email_text, created_at) VALUES (?, ?, ?)",
            (case_id, raw_text, _utc_now_iso()),
        )
        return cursor.lastrowid


def get_interview(db_path: str, interview_id: int) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM interviews WHERE id = ?", (interview_id,)).fetchone()
        return dict(row) if row else None


def update_interview(db_path: str, interview_id: int, data: dict) -> None:
    with connect(db_path) as conn:
        current_row = conn.execute(
            "SELECT extracted_json, scheduled_at_iso, meeting_link, employer_name, company_name, city, platform, username, password, status FROM interviews WHERE id = ?",
            (interview_id,),
        ).fetchone()
        if not current_row:
            return

        current = dict(current_row)
        merged = {
            "extracted_json": data.get("extracted_json", current.get("extracted_json")),
            "scheduled_at_iso": data.get("scheduled_at_iso", current.get("scheduled_at_iso")),
            "meeting_link": data.get("meeting_link", current.get("meeting_link")),
            "employer_name": data.get("employer_name", current.get("employer_name")),
            "company_name": data.get("company_name", current.get("company_name")),
            "city": data.get("city", current.get("city")),
            "platform": data.get("platform", current.get("platform")),
            "username": data.get("username", current.get("username")),
            "password": data.get("password", current.get("password")),
            "status": data.get("status", current.get("status") or "pending"),
        }

        conn.execute(
            "UPDATE interviews SET extracted_json = ?, scheduled_at_iso = ?, meeting_link = ?, employer_name = ?, company_name = ?, city = ?, platform = ?, username = ?, password = ?, status = ? WHERE id = ?",
            (
                merged.get("extracted_json"),
                merged.get("scheduled_at_iso"),
                merged.get("meeting_link"),
                merged.get("employer_name"),
                merged.get("company_name"),
                merged.get("city"),
                merged.get("platform"),
                merged.get("username"),
                merged.get("password"),
                merged.get("status"),
                interview_id,
            ),
        )


def update_interview_reminder(db_path: str, interview_id: int, reminder_type: str) -> None:
    with connect(db_path) as conn:
        if reminder_type == "24h":
            conn.execute("UPDATE interviews SET reminder_24h_sent = 1 WHERE id = ?", (interview_id,))
        elif reminder_type == "12h":
            conn.execute("UPDATE interviews SET reminder_12h_sent = 1 WHERE id = ?", (interview_id,))
        elif reminder_type == "1h":
            conn.execute("UPDATE interviews SET reminder_1h_sent = 1 WHERE id = ?", (interview_id,))


def update_interview_sms_status(db_path: str, interview_id: int, field: str, value: str) -> None:
    # We'll use the existing reminder columns or add new ones if field doesn't exist
    # For now, let's assume reminder_24h_sent and reminder_1h_sent (as 2h is close to 1h)
    # Actually user wants 'sms_sent_24h' and 'sms_sent_2h'
    # I should check if I need to add these columns to the table
    with connect(db_path) as conn:
        try:
            conn.execute(f"UPDATE interviews SET {field} = ? WHERE id = ?", (value, interview_id))
        except sqlite3.OperationalError:
            # Column likely doesn't exist, try to add it
            conn.execute(f"ALTER TABLE interviews ADD COLUMN {field} TEXT")
            conn.execute(f"UPDATE interviews SET {field} = ? WHERE id = ?", (value, interview_id))


def update_interview_followup(db_path: str, interview_id: int, result: str, notes: str = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE interviews SET followup_result = ?, followup_notes = ?, status = ? WHERE id = ?",
            (result, notes, result, interview_id,)
        )


def delete_interview(db_path: str, interview_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM interviews WHERE id = ?", (interview_id,))


def get_users_by_license(db_path: str, license_code: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT user_id, role, phone, full_name, is_phone_verified FROM users WHERE license_code = ?",
            (license_code,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_users_by_role(db_path: str, role: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT user_id, role, phone, full_name, license_code, is_phone_verified FROM users WHERE role = ?",
            (role,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_agencies(db_path: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT code, license_type, capacity, used_count, is_active, agency_name FROM licenses WHERE license_type = 'agency'"
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_direct_clients(db_path: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT code, license_type, capacity, used_count, is_active, agency_name FROM licenses WHERE license_type = 'direct_client'"
        ).fetchall()
        return [dict(r) for r in rows]
