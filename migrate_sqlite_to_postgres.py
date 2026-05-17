import os
from datetime import datetime

from sqlalchemy import create_engine, inspect, text

DEFAULT_SQLITE_URL = "sqlite:///turismob2b.db"


def normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def ensure_cols(data: dict, defaults: dict) -> dict:
    merged = defaults.copy()
    merged.update(data)
    return merged


def upsert_user(dst_conn, row: dict) -> None:
    dst_conn.execute(
        text(
            """
            INSERT INTO users (id, name, email, salt, password_hash, role, is_active, created_at)
            VALUES (:id, :name, :email, :salt, :password_hash, :role, :is_active, :created_at)
            ON CONFLICT (email) DO NOTHING
            """
        ),
        row,
    )


def upsert_quote(dst_conn, row: dict) -> None:
    dst_conn.execute(
        text(
            """
            INSERT INTO quotes (id, user_id, quote_name, status, version, total_to_client, payload_json, created_at, updated_at)
            VALUES (:id, :user_id, :quote_name, :status, :version, :total_to_client, :payload_json, :created_at, :updated_at)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        row,
    )


def upsert_audit(dst_conn, row: dict) -> None:
    dst_conn.execute(
        text(
            """
            INSERT INTO audit_logs (id, user_id, event_type, resource_type, resource_id, metadata_json, created_at)
            VALUES (:id, :user_id, :event_type, :resource_type, :resource_id, :metadata_json, :created_at)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        row,
    )


def set_sequence(dst_conn, table: str) -> None:
    dst_conn.execute(
        text(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1), true)"
        )
    )


def main() -> None:
    sqlite_url = os.getenv("SQLITE_URL", DEFAULT_SQLITE_URL)
    postgres_url = os.getenv("DATABASE_URL", "")

    if not postgres_url:
        raise RuntimeError("Defina DATABASE_URL para o Postgres de destino")

    sqlite_engine = create_engine(sqlite_url)
    postgres_engine = create_engine(normalize_url(postgres_url), pool_pre_ping=True)

    src_inspector = inspect(sqlite_engine)
    src_tables = set(src_inspector.get_table_names())

    print(f"[{datetime.now().isoformat()}] Iniciando migracao SQLite -> Postgres")
    print(f"Tabelas de origem detectadas: {', '.join(sorted(src_tables))}")

    with sqlite_engine.connect() as src_conn, postgres_engine.begin() as dst_conn:
        migrated = {"users": 0, "quotes": 0, "audit_logs": 0}

        if "users" in src_tables:
            rows = src_conn.execute(text("SELECT * FROM users")).mappings().all()
            for r in rows:
                row = ensure_cols(
                    dict(r),
                    {
                        "role": "consultant",
                        "is_active": True,
                    },
                )
                upsert_user(dst_conn, row)
                migrated["users"] += 1

        if "quotes" in src_tables:
            rows = src_conn.execute(text("SELECT * FROM quotes")).mappings().all()
            for r in rows:
                row = ensure_cols(
                    dict(r),
                    {
                        "status": "draft",
                        "version": 1,
                    },
                )
                upsert_quote(dst_conn, row)
                migrated["quotes"] += 1

        if "audit_logs" in src_tables:
            rows = src_conn.execute(text("SELECT * FROM audit_logs")).mappings().all()
            for r in rows:
                row = ensure_cols(
                    dict(r),
                    {
                        "resource_type": "",
                        "resource_id": "",
                        "metadata_json": "{}",
                    },
                )
                upsert_audit(dst_conn, row)
                migrated["audit_logs"] += 1

        set_sequence(dst_conn, "users")
        set_sequence(dst_conn, "quotes")
        set_sequence(dst_conn, "audit_logs")

    print("Migracao concluida com sucesso")
    print(f"Usuarios migrados: {migrated['users']}")
    print(f"Cotacoes migradas: {migrated['quotes']}")
    print(f"Auditoria migrada: {migrated['audit_logs']}")


if __name__ == "__main__":
    main()
