"""PyInstaller entry point that preserves the network_launcher package context."""

from network_launcher.__main__ import main


if __name__ == "__main__":
    main()
