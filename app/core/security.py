"""
License Server - Security & Cryptography
Sistema de assinatura RSA para licenças anti-crack
"""
import os
import json
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Optional, Tuple
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature
from jose import jwt, JWTError
import bcrypt

from .config import settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica password usando bcrypt"""
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def get_password_hash(password: str) -> str:
    """Gera hash bcrypt do password"""
    return bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')


class RSAKeyManager:
    """Gerenciador de chaves RSA para assinatura de licenças"""

    def __init__(self):
        self.private_key = None
        self.public_key = None
        self._load_or_generate_keys()

    def _load_or_generate_keys(self):
        """Carrega chaves existentes ou gera novas"""
        private_path = Path(settings.RSA_PRIVATE_KEY_PATH)
        public_path = Path(settings.RSA_PUBLIC_KEY_PATH)

        # Cria diretório se não existir
        private_path.parent.mkdir(parents=True, exist_ok=True)

        if private_path.exists() and public_path.exists():
            self._load_keys(private_path, public_path)
        else:
            self._generate_keys(private_path, public_path)

    def _generate_keys(self, private_path: Path, public_path: Path):
        """Gera novo par de chaves RSA 4096-bit"""
        print("Generating new RSA key pair (4096-bit)...")

        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=4096,
            backend=default_backend()
        )
        self.public_key = self.private_key.public_key()

        # Salva chave privada (PROTEGER!)
        private_pem = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        private_path.write_bytes(private_pem)
        os.chmod(private_path, 0o600)  # Apenas owner pode ler

        # Salva chave pública
        public_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        public_path.write_bytes(public_pem)

        print(f"Keys generated and saved to {private_path.parent}/")

    def _load_keys(self, private_path: Path, public_path: Path):
        """Carrega chaves existentes"""
        private_pem = private_path.read_bytes()
        self.private_key = serialization.load_pem_private_key(
            private_pem,
            password=None,
            backend=default_backend()
        )

        public_pem = public_path.read_bytes()
        self.public_key = serialization.load_pem_public_key(
            public_pem,
            backend=default_backend()
        )

    def sign_license(self, license_data: dict) -> str:
        """
        Assina dados da licença com chave privada RSA
        Retorna assinatura em base64
        """
        # Serializa dados de forma determinística
        data_str = json.dumps(license_data, sort_keys=True, separators=(',', ':'))
        data_bytes = data_str.encode('utf-8')

        # Assina com RSA-PSS (mais seguro que PKCS1v15)
        signature = self.private_key.sign(
            data_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )

        return base64.b64encode(signature).decode('utf-8')

    def verify_signature(self, license_data: dict, signature: str) -> bool:
        """
        Verifica assinatura da licença
        Retorna True se válida
        """
        try:
            data_str = json.dumps(license_data, sort_keys=True, separators=(',', ':'))
            data_bytes = data_str.encode('utf-8')
            signature_bytes = base64.b64decode(signature)

            self.public_key.verify(
                signature_bytes,
                data_bytes,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return True
        except InvalidSignature:
            return False
        except Exception as e:
            print(f"Signature verification error: {e}")
            return False

    def get_public_key_pem(self) -> str:
        """Retorna chave pública em formato PEM (para distribuir aos clientes)"""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')


# Instância global
rsa_manager = RSAKeyManager()


def generate_license_key() -> str:
    """
    Gera chave de licença no formato XXXX-XXXX-XXXX-XXXX
    """
    import secrets
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # Sem I, O, 0, 1 para evitar confusão
    segments = []
    for _ in range(4):
        segment = ''.join(secrets.choice(chars) for _ in range(4))
        segments.append(segment)
    return '-'.join(segments)


def generate_hardware_hash(mac_address: str, cpu_id: str = "", disk_serial: str = "") -> str:
    """
    Gera hash único do hardware do cliente
    """
    components = f"{mac_address}:{cpu_id}:{disk_serial}".lower()
    return hashlib.sha256(components.encode()).hexdigest()[:32]


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Cria JWT token para autenticação admin"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})

    # Usa HS256 para tokens de sessão (mais simples)
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    return encoded_jwt


def verify_access_token(token: str) -> Optional[dict]:
    """Verifica JWT token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload
    except JWTError:
        return None


def create_signed_license(
    license_key: str,
    client_id: str,
    client_name: str,
    hardware_id: str,
    plan: str,
    features: list,
    max_users: int,
    issued_at: datetime,
    expires_at: datetime
) -> dict:
    """
    Cria licença completa com assinatura RSA
    """
    license_data = {
        "license_key": license_key,
        "client_id": client_id,
        "client_name": client_name,
        "hardware_id": hardware_id,
        "plan": plan,
        "features": features,
        "max_users": max_users,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "version": "1.0"
    }

    signature = rsa_manager.sign_license(license_data)

    return {
        **license_data,
        "signature": signature
    }


def verify_license(license_with_signature: dict) -> Tuple[bool, str]:
    """
    Verifica licença completa
    Retorna (is_valid, message)
    """
    try:
        # Extrai assinatura
        signature = license_with_signature.pop("signature", None)
        if not signature:
            return False, "Missing signature"

        # Verifica assinatura
        if not rsa_manager.verify_signature(license_with_signature, signature):
            return False, "Invalid signature"

        # Verifica expiração
        expires_at = datetime.fromisoformat(license_with_signature["expires_at"])
        if datetime.utcnow() > expires_at:
            return False, "License expired"

        return True, "Valid"
    except Exception as e:
        return False, f"Verification error: {str(e)}"
