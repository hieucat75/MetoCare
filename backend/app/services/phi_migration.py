"""One-off PHI re-encryption job.

After enabling field-level encryption on an existing database, run this to
encrypt any pre-existing plaintext values. It reads each PHI column via raw SQL
(bypassing the ORM's transparent decryption), detects plaintext (values that are
not valid ciphertext), and encrypts them in place. Idempotent: already-encrypted
values are skipped, so it is safe to run more than once.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.crypto import encrypt, try_decrypt

# table -> PHI columns that are now EncryptedString.
PHI_COLUMNS: dict[str, tuple[str, ...]] = {
    "users": ("full_name",),
    "patient_profiles": (
        "full_name",
        "dob",
        "phone",
        "address",
        "known_conditions",
        "allergies",
        "family_history",
        "lifestyle_profile",
    ),
    "lab_documents": ("raw_text",),
}


def encrypt_existing_phi(db: Session) -> int:
    """Encrypt plaintext PHI in place. Returns the number of rows updated."""
    updated = 0
    for table, cols in PHI_COLUMNS.items():
        col_list = ", ".join(cols)
        rows = db.execute(text(f"SELECT id, {col_list} FROM {table}")).mappings().all()
        for row in rows:
            changes: dict[str, str] = {}
            for col in cols:
                value = row[col]
                if value is None:
                    continue
                if try_decrypt(value) is None:  # not valid ciphertext -> plaintext
                    changes[col] = encrypt(value)
            if changes:
                set_clause = ", ".join(f"{c} = :{c}" for c in changes)
                db.execute(
                    text(f"UPDATE {table} SET {set_clause} WHERE id = :row_id"),
                    {**changes, "row_id": row["id"]},
                )
                updated += 1
    db.commit()
    return updated
