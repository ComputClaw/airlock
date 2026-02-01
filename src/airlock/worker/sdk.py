"""Script SDK: settings access and result capture for worker-executed scripts."""


class Settings:
    """Read-only access to credential values injected into the execution."""

    def __init__(self, data: dict[str, str]) -> None:
        self._data = dict(data)  # defensive copy

    def get(self, key: str) -> str | None:
        """Get a credential value by key."""
        return self._data.get(key)

    def keys(self) -> list[str]:
        """List available credential keys."""
        return list(self._data.keys())


class ResultHolder:
    """Captures the script's return value via set_result()."""

    def __init__(self) -> None:
        self.value = None

    def set_result(self, data) -> None:
        """Set the script's return value."""
        self.value = data
