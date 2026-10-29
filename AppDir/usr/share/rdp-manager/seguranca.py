#!/usr/bin/env python3
"""
Módulo de segurança do RDP Manager: derivação de chave a partir da
senha-mestra, criptografia/descriptografia do cofre de conexões
(AES via Fernet) e leitura/gravação do connections.json.
"""

import json
import os
import base64
import secrets

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    CRYPTO_DISPONIVEL = True
except ImportError:
    CRYPTO_DISPONIVEL = False


# ============================================================
# CONFIGURAÇÃO
# ============================================================

# No AppImage, o diretório onde o script vive é somente leitura
# (fica montado a partir do próprio .AppImage), então os dados são
# gravados na pasta de dados do usuário, não ao lado do script.
DATA_DIR = os.environ.get(
    "XDG_DATA_HOME",
    os.path.expanduser("~/.local/share")
)
BASE_DIR = os.path.join(DATA_DIR, "rdp-manager")
os.makedirs(BASE_DIR, exist_ok=True)
DB_FILE = os.path.join(BASE_DIR, "connections.json")

# Assinatura no começo do arquivo/backup, pra identificar que é um
# cofre criptografado do RDP Manager (e não JSON puro antigo).
ASSINATURA = b"RDPM1"


class SenhaInvalida(Exception):
    """A senha informada não conseguiu abrir o cofre."""
    pass


# ============================================================
# CRIPTOGRAFIA (senha-mestra)
# ============================================================

def _derivar_chave(senha, salt):
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(senha.encode("utf-8")))


def criptografar_bytes(dados_bytes, senha):
    salt = secrets.token_bytes(16)
    chave = _derivar_chave(senha, salt)
    token = Fernet(chave).encrypt(dados_bytes)
    return ASSINATURA + salt + token


def descriptografar_bytes(blob, senha):
    if not blob.startswith(ASSINATURA):
        raise ValueError(
            "Não é um arquivo criptografado do RDP Manager."
        )

    salt = blob[len(ASSINATURA):len(ASSINATURA) + 16]
    token = blob[len(ASSINATURA) + 16:]
    chave = _derivar_chave(senha, salt)

    try:
        return Fernet(chave).decrypt(token)
    except InvalidToken:
        raise SenhaInvalida("Senha incorreta.")


# ============================================================
# BANCO JSON
# ============================================================

def carregar_conexoes(senha):
    if not os.path.exists(DB_FILE):
        return []

    with open(DB_FILE, "rb") as arquivo:
        blob = arquivo.read()

    if not blob:
        return []

    dados_bytes = descriptografar_bytes(blob, senha)  # pode levantar SenhaInvalida

    try:
        dados = json.loads(dados_bytes.decode("utf-8"))
        if isinstance(dados, list):
            return dados
    except Exception:
        pass

    return []


def salvar_conexoes(conexoes, senha):
    dados_bytes = json.dumps(
        conexoes,
        indent=2,
        ensure_ascii=False
    ).encode("utf-8")

    blob = criptografar_bytes(dados_bytes, senha)

    with open(DB_FILE, "wb") as arquivo:
        arquivo.write(blob)

    try:
        os.chmod(DB_FILE, 0o600)
    except Exception:
        pass


def validar_conexao(item):
    # Aceita um dict do JSON de backup só se tiver os campos mínimos
    # esperados; ignora entradas malformadas em vez de travar o import.
    if not isinstance(item, dict):
        return False

    return bool(
        item.get("name")
        and item.get("host")
        and item.get("username")
    )

