from cryptography.fernet import Fernet
from config import TOKEN_ENCRYPTION_KEY

_fernet = Fernet(TOKEN_ENCRYPTION_KEY.encode())


def encrypt_token(token: str) -> str:
    """Chiffre un token avant de le stocker en base de données."""
    return _fernet.encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    """Déchiffre un token lu depuis la base de données."""
    return _fernet.decrypt(encrypted_token.encode()).decode()
