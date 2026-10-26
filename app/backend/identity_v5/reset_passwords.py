"""Issue new initial passwords for every seeded user: `python -m backend.identity_v5.reset_passwords`.

Writes ~/CreditProbe_Workspace/USERS_LOCAL.md (or CP_USERS_LOCAL). Prints only where the file is.
"""
from backend.identity_v5 import store


def main() -> None:
    with store.db() as con:
        path = store.reset_passwords(con)
    print(f"New passwords written to {path}")


if __name__ == "__main__":
    main()
