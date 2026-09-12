"""凭据字段加密工具（secret_box）测试。

设计决策（为什么这么写）：
- 用显式 key_path 隔离每个测试的密钥，避免测试间通过全局 .taskpps 目录互相污染。
- 覆盖「加密/解密/明文兼容/密钥缺失报错/文件权限」5 个边界，对应安全设计的核心承诺。
"""

from __future__ import annotations

import stat

import pytest

from taskpps.auth.secret_box import (
    ENCRYPTED_PREFIX,
    SecretKeyError,
    decrypt_secret,
    decrypt_sensitive_fields,
    encrypt_secret,
    encrypt_sensitive_fields,
)


class TestEncryptDecrypt:
    def test_encrypt_returns_prefixed_ciphertext(self, tmp_path):
        """加密结果必须带 enc:v1: 前缀，且不包含明文。"""
        key_path = tmp_path / "credentials.key"
        cipher = encrypt_secret("s3cret-pass", key_path=key_path)
        assert cipher.startswith(ENCRYPTED_PREFIX)
        assert "s3cret-pass" not in cipher
        assert cipher != "s3cret-pass"

    def test_decrypt_roundtrip(self, tmp_path):
        key_path = tmp_path / "credentials.key"
        assert decrypt_secret(encrypt_secret("p@ss", key_path=key_path), key_path=key_path) == "p@ss"

    def test_decrypt_plaintext_passthrough(self, tmp_path):
        """历史 CLI 明文凭据必须继续可读（向后兼容）。"""
        key_path = tmp_path / "credentials.key"
        assert decrypt_secret("legacy-plain", key_path=key_path) == "legacy-plain"

    def test_encrypt_is_idempotent(self, tmp_path):
        """重复加密不应叠加前缀（编辑回填场景可能拿到已加密值）。"""
        key_path = tmp_path / "credentials.key"
        once = encrypt_secret("value", key_path=key_path)
        assert encrypt_secret(once, key_path=key_path) == once

    def test_decrypt_with_missing_key_raises(self, tmp_path):
        """密文存在但密钥文件丢失时必须报错，禁止静默回退明文。"""
        key_path = tmp_path / "credentials.key"
        cipher = encrypt_secret("value", key_path=key_path)
        key_path.unlink()
        with pytest.raises(SecretKeyError):
            decrypt_secret(cipher, key_path=key_path)

    def test_decrypt_tampered_cipher_raises(self, tmp_path):
        """密文被篡改时抛 SecretKeyError（Fernet InvalidToken 包装）。"""
        key_path = tmp_path / "credentials.key"
        cipher = encrypt_secret("value", key_path=key_path)
        tampered = cipher[:-4] + "AAAA"
        with pytest.raises(SecretKeyError):
            decrypt_secret(tampered, key_path=key_path)

    def test_key_file_permission_600(self, tmp_path):
        key_path = tmp_path / "credentials.key"
        encrypt_secret("value", key_path=key_path)
        mode = stat.S_IMODE(key_path.stat().st_mode)
        assert mode == 0o600

    def test_env_key_override(self, tmp_path, monkeypatch):
        """TASKPPS_CREDENTIAL_KEY 存在时优先于密钥文件（容器/CI 场景）。"""
        from cryptography.fernet import Fernet

        env_key = Fernet.generate_key().decode()
        monkeypatch.setenv("TASKPPS_CREDENTIAL_KEY", env_key)
        cipher = encrypt_secret("env-pass", key_path=tmp_path / "ignored.key")
        assert decrypt_secret(cipher, key_path=tmp_path / "ignored.key") == "env-pass"
        assert not (tmp_path / "ignored.key").exists()

    def test_non_string_values_passthrough(self, tmp_path):
        """非字符串值（None/int/dict）不做加解密，原样返回。"""
        key_path = tmp_path / "credentials.key"
        assert encrypt_secret(None, key_path=key_path) is None
        assert decrypt_secret(None, key_path=key_path) is None
        assert decrypt_secret(123, key_path=key_path) == 123


class TestSensitiveFields:
    def test_encrypt_only_sensitive_fields(self, tmp_path):
        key_path = tmp_path / "credentials.key"
        data = {
            "id": "prod",
            "username": "deploy",
            "password": "plain-pass",
            "passphrase": "plain-phrase",
            "token": "ghp_xxx",
            "key_path": "/home/deploy/.ssh/id_rsa",
        }
        result = encrypt_sensitive_fields(data, key_path=key_path)
        # 非敏感字段保持不变
        assert result["id"] == "prod"
        assert result["username"] == "deploy"
        assert result["key_path"] == "/home/deploy/.ssh/id_rsa"
        # 敏感字段被加密且可还原
        for field, plain in (("password", "plain-pass"), ("passphrase", "plain-phrase"), ("token", "ghp_xxx")):
            assert result[field].startswith(ENCRYPTED_PREFIX)
            assert decrypt_secret(result[field], key_path=key_path) == plain

    def test_decrypt_sensitive_fields_roundtrip(self, tmp_path):
        key_path = tmp_path / "credentials.key"
        original = {"username": "u", "password": "p", "key_path": "/k"}
        encrypted = encrypt_sensitive_fields(original, key_path=key_path)
        restored = decrypt_sensitive_fields(encrypted, key_path=key_path)
        assert restored == original

    def test_decrypt_mixed_plaintext_and_cipher(self, tmp_path):
        """同一份 YAML 里明文与密文共存（迁移过渡期）必须都能读。"""
        key_path = tmp_path / "credentials.key"
        encrypted = encrypt_secret("new-pass", key_path=key_path)
        data = {"username": "u", "password": encrypted, "passphrase": "old-plain"}
        restored = decrypt_sensitive_fields(data, key_path=key_path)
        assert restored["password"] == "new-pass"
        assert restored["passphrase"] == "old-plain"
