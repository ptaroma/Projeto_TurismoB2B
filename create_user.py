import argparse
from typing import Any

from app import SessionLocal, User, create_password, ensure_password_policy, utcnow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Criar usuario interno no TurismoB2B")
    parser.add_argument("--name", required=True, help="Nome do usuario")
    parser.add_argument("--email", required=True, help="Email do usuario")
    parser.add_argument("--password", required=True, help="Senha do usuario")
    parser.add_argument("--role", default="consultant", choices=["consultant", "admin"], help="Perfil de acesso")
    parser.add_argument("--inactive", action="store_true", help="Criar usuario inativo")
    return parser.parse_args()


def create_user(args: argparse.Namespace) -> dict[str, Any]:
    email = args.email.strip().lower()
    name = args.name.strip()

    if not name:
        raise ValueError("Nome obrigatorio")

    ensure_password_policy(args.password)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            raise ValueError("Email ja cadastrado")

        salt, pwd_hash = create_password(args.password)
        user = User(
            name=name,
            email=email,
            salt=salt,
            password_hash=pwd_hash,
            role=args.role,
            is_active=not args.inactive,
            created_at=utcnow().isoformat(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
        }
    finally:
        db.close()


def main() -> None:
    args = parse_args()
    created = create_user(args)
    print("Usuario criado com sucesso:")
    print(f"- id: {created['id']}")
    print(f"- nome: {created['name']}")
    print(f"- email: {created['email']}")
    print(f"- role: {created['role']}")
    print(f"- ativo: {created['is_active']}")


if __name__ == "__main__":
    main()
