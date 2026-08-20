from __future__ import annotations

import argparse
from pathlib import Path

from cryptography.hazmat.primitives import (
    serialization,
)
from cryptography.hazmat.primitives.asymmetric import (
    rsa,
)

RSA_KEY_SIZE = 4096
PUBLIC_EXPONENT = 65537


def generate_key_pair(
    *,
    private_path: Path,
    public_path: Path,
    force: bool,
) -> None:
    if not force:
        existing = [
            path
            for path in (
                private_path,
                public_path,
            )
            if path.exists()
        ]

        if existing:
            names = ", ".join(str(path) for path in existing)

            raise RuntimeError(
                "Refusing to overwrite existing "
                f"key files: {names}. "
                "Use --force only when rotation "
                "is intentional."
            )

    private_key = rsa.generate_private_key(
        public_exponent=PUBLIC_EXPONENT,
        key_size=RSA_KEY_SIZE,
    )

    public_key = private_key.public_key()

    private_bytes = private_key.private_bytes(
        encoding=(serialization.Encoding.PEM),
        format=(serialization.PrivateFormat.PKCS8),
        encryption_algorithm=(serialization.NoEncryption()),
    )

    public_bytes = public_key.public_bytes(
        encoding=(serialization.Encoding.PEM),
        format=(serialization.PublicFormat.SubjectPublicKeyInfo),
    )

    private_path.write_bytes(private_bytes)

    public_path.write_bytes(public_bytes)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=("Generate local RSA-4096 evidence wrapping and signing key pairs.")
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".secrets/evidence"),
    )

    parser.add_argument(
        "--force",
        action="store_true",
    )

    arguments = parser.parse_args()

    output: Path = arguments.output.expanduser().resolve()

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    generate_key_pair(
        private_path=(output / "wrapping-private.pem"),
        public_path=(output / "wrapping-public.pem"),
        force=arguments.force,
    )

    generate_key_pair(
        private_path=(output / "signing-private.pem"),
        public_path=(output / "signing-public.pem"),
        force=arguments.force,
    )

    print("Generated local evidence RSA keys:")
    print(f"  {output / 'wrapping-private.pem'}")
    print(f"  {output / 'wrapping-public.pem'}")
    print(f"  {output / 'signing-private.pem'}")
    print(f"  {output / 'signing-public.pem'}")


if __name__ == "__main__":
    main()
