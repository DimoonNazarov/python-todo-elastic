from passlib.context import CryptContext


pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],
    pbkdf2_sha256__default_rounds=30000,
    deprecated="auto",
)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
