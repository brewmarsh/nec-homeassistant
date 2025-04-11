"""Version information for NEC Home Assistant integration."""

import subprocess


def get_git_commit_hash() -> str:
    """Get the current git commit hash."""
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"])
            .decode("ascii")
            .strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


VERSION = "0.1.0"  # Base version
BUILD = get_git_commit_hash()
FULL_VERSION = f"{VERSION}.{BUILD}"

if __name__ == "__main__":
    print(f"Version: {VERSION}")
    print(f"Build: {BUILD}")
    print(f"Full Version: {FULL_VERSION}")
