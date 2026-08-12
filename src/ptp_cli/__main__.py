"""Entry point for ``python -m src.ptp_cli``.

Mirrors the ``if __name__ == "__main__"`` block in src/ptp_cli/flags.py:
- ``--help`` / ``-h`` prints the CLI parser help and exits 0.
- Otherwise parse+validate the CLI args and print the resulting config.
"""

import sys

from .flags import CLIFlagParser, create_config_from_args


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
        parser = CLIFlagParser()
        parser.parser.print_help()
        sys.exit(0)

    config = create_config_from_args()

    print("Parsed Configuration:")
    print("=" * 60)

    config_dict = config.to_dict()
    for section, values in config_dict.items():
        print(f"\n{section}:")
        if isinstance(values, dict):
            for key, value in values.items():
                print(f"  {key}: {value}")
        else:
            print(f"  {values}")

    print("\n" + "=" * 60)
    print("Configuration validated successfully!")


if __name__ == "__main__":
    main()
