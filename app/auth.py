from passlib.hash import bcrypt


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.verify(plain, hashed)
