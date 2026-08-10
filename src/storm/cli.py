"""Minimal local CLI marker; no live integrations are invoked."""

from storm import __version__


def main() -> int:
    print(f"STORM {__version__} - contracts only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
