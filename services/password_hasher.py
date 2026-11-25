"""Hash de senha com scrypt (biblioteca padrão do Python, sem dependências externas).

Formato guardado: scrypt$N$r$p$salt_b64$hash_b64. Os parâmetros ficam no próprio hash, então é possível
aumentar o custo no futuro e ainda verificar senhas antigas. Para trocar por argon2, basta criar outra
classe com os métodos hash() e verify() e passá-la ao AuthenticationService.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets


class ScryptHasher:
    def __init__(self, n: int = 2 ** 15, r: int = 8, p: int = 1):
        self.n, self.r, self.p = n, r, p

    @staticmethod
    def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
        # maxmem folgado: scrypt precisa de ~128 * n * r bytes
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32,
                              maxmem=128 * n * r * 2 + (1 << 20))

    def hash(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = self._derive(password, salt, self.n, self.r, self.p)
        b64 = lambda raw: base64.b64encode(raw).decode("ascii")
        return f"scrypt${self.n}${self.r}${self.p}${b64(salt)}${b64(digest)}"

    def verify(self, password: str, stored: str) -> bool:
        try:
            scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
            if scheme != "scrypt":
                return False
            salt, expected = base64.b64decode(salt_b64), base64.b64decode(hash_b64)
            actual = self._derive(password, salt, int(n), int(r), int(p))
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(actual, expected)
