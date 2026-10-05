"""Interactive commands for initial CMMS setup."""

import getpass
import re

from sqlalchemy import select

from backend import models
from backend.database import Base, SessionLocal, engine
from backend.security import hash_password


def create_admin() -> None:
    Base.metadata.create_all(bind=engine)
    name = input("Nome do administrador: ").strip()
    email = input("E-mail do administrador: ").strip().lower()
    if len(name) < 2 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise SystemExit("Informe um nome e e-mail válidos.")
    password = getpass.getpass("Senha (mínimo 12 caracteres): ")
    confirmation = getpass.getpass("Confirme a senha: ")
    if len(password) < 12 or password != confirmation:
        raise SystemExit("A senha deve ter pelo menos 12 caracteres e as confirmações devem coincidir.")
    with SessionLocal() as db:
        if db.scalar(select(models.User).where(models.User.email == email)):
            raise SystemExit("Já existe um usuário com esse e-mail.")
        db.add(models.User(name=name, email=email, password_hash=hash_password(password), role="administrator"))
        db.commit()
    print(f"Administrador {email} criado.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Configuração inicial do SENAI CMMS")
    parser.add_argument("command", choices=["create-admin"])
    if parser.parse_args().command == "create-admin":
        create_admin()
