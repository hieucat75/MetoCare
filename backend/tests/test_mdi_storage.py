"""Unit tests for the Object Storage abstraction (Master Plan §1.7)."""

from __future__ import annotations

import time

import pytest
from app.services.storage import (
    CONTAINER_ACCEPTED,
    CONTAINER_QUARANTINE,
    ObjectNotFound,
    StorageError,
    build_object_key,
    container_of,
    patient_of,
    sign_blob_token,
    verify_blob_token,
)
from app.services.storage.local import LocalDiskStorage
from app.services.storage.signing import BlobTokenError


def _store(tmp_path) -> LocalDiskStorage:
    return LocalDiskStorage(str(tmp_path), secret="unit-secret")


def test_build_object_key_embeds_container_and_patient():
    key = build_object_key(container=CONTAINER_QUARANTINE, patient_id="pat-1", ext="pdf")
    assert container_of(key) == CONTAINER_QUARANTINE
    assert patient_of(key) == "pat-1"
    assert key.endswith(".pdf")


def test_build_object_key_rejects_unknown_container():
    with pytest.raises(ValueError):
        build_object_key(container="evil", patient_id="p", ext="pdf")


def test_put_get_size_exists_delete_roundtrip(tmp_path):
    st = _store(tmp_path)
    key = build_object_key(container=CONTAINER_QUARANTINE, patient_id="p", ext="png")
    st.put_bytes(key, b"hello")
    assert st.exists(key) is True
    assert st.size(key) == 5
    assert st.get_bytes(key) == b"hello"
    st.delete(key)
    assert st.exists(key) is False
    st.delete(key)  # idempotent


def test_get_missing_raises_object_not_found(tmp_path):
    st = _store(tmp_path)
    with pytest.raises(ObjectNotFound):
        st.get_bytes("quarantine/p/202607/missing.png")


def test_move_quarantine_to_accepted(tmp_path):
    st = _store(tmp_path)
    q = build_object_key(container=CONTAINER_QUARANTINE, patient_id="p", ext="jpg")
    a = build_object_key(container=CONTAINER_ACCEPTED, patient_id="p", ext="jpg")
    st.put_bytes(q, b"bytes")
    st.move(q, a)
    assert st.exists(q) is False
    assert st.get_bytes(a) == b"bytes"


def test_path_traversal_is_blocked(tmp_path):
    st = _store(tmp_path)
    with pytest.raises(StorageError):
        st.get_bytes("../../etc/passwd")
    with pytest.raises(StorageError):
        st.put_bytes("/abs/escape", b"x")


def test_signed_put_url_is_write_only_and_single_object(tmp_path):
    st = _store(tmp_path)
    key = build_object_key(container=CONTAINER_QUARANTINE, patient_id="p", ext="pdf")
    signed = st.signed_put_url(key, expires_in=600)
    assert signed.method == "PUT"
    token = signed.url.rsplit("/", 1)[1]
    decoded = verify_blob_token("unit-secret", token)
    assert decoded.op == "put"
    assert decoded.key == key


def test_token_tamper_and_expiry_rejected():
    key = "quarantine/p/202607/x.pdf"
    good = sign_blob_token("secret", key=key, op="get", expires_at=int(time.time()) + 60)
    assert verify_blob_token("secret", good).key == key
    with pytest.raises(BlobTokenError):
        verify_blob_token("WRONG-secret", good)  # bad signature
    expired = sign_blob_token("secret", key=key, op="get", expires_at=int(time.time()) - 1)
    with pytest.raises(BlobTokenError):
        verify_blob_token("secret", expired)  # expired
    with pytest.raises(BlobTokenError):
        verify_blob_token("secret", "not-a-token")  # malformed
