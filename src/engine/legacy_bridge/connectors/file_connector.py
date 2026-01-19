"""FileConnector - Read-only connector for local files.

This connector provides read-only access to local files (CSV, JSON)
for legacy asset governance without modifying the source.
"""

import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from engine.legacy_bridge.models import SourceFormat


class FileConnectorError(Exception):
    """Error accessing file through connector."""

    pass


class FileConnector:
    """Read-only connector for local files.

    Provides methods to:
    - Read file content
    - Compute SHA256 hash
    - Extract minimal schema (CSV headers, JSON top-level keys)
    - Get file stats
    """

    def __init__(self, base_path: Optional[Path] = None) -> None:
        """Initialize connector.

        Args:
            base_path: Optional base path for relative file resolution.
                       If None, paths are resolved relative to CWD.
        """
        self._base_path = base_path or Path.cwd()

    def _resolve_path(self, path: str) -> Path:
        """Resolve relative path to absolute.

        Args:
            path: Relative path string.

        Returns:
            Resolved absolute path.

        Raises:
            FileConnectorError: If path contains traversal or is absolute.
        """
        # Security: reject absolute paths
        if Path(path).is_absolute():
            raise FileConnectorError(
                f"Absolute paths not allowed: {path}. Use relative paths only."
            )

        # Security: reject path traversal
        if ".." in path:
            raise FileConnectorError(
                f"Path traversal not allowed: {path}. Paths cannot contain '..'."
            )

        resolved = self._base_path / path
        return resolved.resolve()

    def read_content(self, path: str) -> bytes:
        """Read file content.

        Args:
            path: Relative path to file.

        Returns:
            File content as bytes.

        Raises:
            FileConnectorError: If file cannot be read.
        """
        try:
            resolved = self._resolve_path(path)
            if not resolved.exists():
                raise FileConnectorError(f"File not found: {path}")
            if not resolved.is_file():
                raise FileConnectorError(f"Not a file: {path}")
            with open(resolved, "rb") as f:
                return f.read()
        except FileConnectorError:
            raise
        except Exception as e:
            raise FileConnectorError(f"Failed to read file {path}: {e}")

    def compute_hash(self, path: str) -> str:
        """Compute SHA256 hash of file.

        Args:
            path: Relative path to file.

        Returns:
            Hash in "SHA256:<hex>" format.

        Raises:
            FileConnectorError: If file cannot be read.
        """
        try:
            resolved = self._resolve_path(path)
            if not resolved.exists():
                raise FileConnectorError(f"File not found: {path}")

            h = hashlib.sha256()
            with open(resolved, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return f"SHA256:{h.hexdigest()}"
        except FileConnectorError:
            raise
        except Exception as e:
            raise FileConnectorError(f"Failed to compute hash for {path}: {e}")

    def extract_schema(self, path: str, source_format: str) -> Dict[str, Any]:
        """Extract minimal schema metadata from file.

        Args:
            path: Relative path to file.
            source_format: Format hint ("csv", "json", "raw").

        Returns:
            Schema metadata dict. For CSV: {"columns": [...], "row_count": N}.
            For JSON: {"keys": [...]}. For raw: {"format": "raw"}.

        Raises:
            FileConnectorError: If file cannot be read or parsed.
        """
        try:
            resolved = self._resolve_path(path)
            if not resolved.exists():
                raise FileConnectorError(f"File not found: {path}")

            if source_format == SourceFormat.CSV.value:
                return self._extract_csv_schema(resolved)
            elif source_format == SourceFormat.JSON.value:
                return self._extract_json_schema(resolved)
            else:
                return {"format": "raw"}
        except FileConnectorError:
            raise
        except Exception as e:
            raise FileConnectorError(f"Failed to extract schema from {path}: {e}")

    def _extract_csv_schema(self, resolved_path: Path) -> Dict[str, Any]:
        """Extract CSV schema: headers and row count."""
        columns = []
        row_count = 0

        with open(resolved_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            try:
                columns = next(reader)  # First row = headers
            except StopIteration:
                return {"columns": [], "row_count": 0}

            # Count remaining rows
            for _ in reader:
                row_count += 1

        return {"columns": columns, "row_count": row_count}

    def _extract_json_schema(self, resolved_path: Path) -> Dict[str, Any]:
        """Extract JSON schema: top-level keys."""
        with open(resolved_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return {"keys": list(data.keys())}
        elif isinstance(data, list):
            # For arrays, extract keys from first element if it's a dict
            if data and isinstance(data[0], dict):
                return {"keys": list(data[0].keys()), "array_length": len(data)}
            return {"array_length": len(data)}
        else:
            return {"type": type(data).__name__}

    def get_stats(self, path: str) -> Dict[str, Any]:
        """Get file stats (size, mtime, line count).

        Args:
            path: Relative path to file.

        Returns:
            Dict with size_bytes, mtime, line_count.

        Raises:
            FileConnectorError: If file cannot be accessed.
        """
        try:
            resolved = self._resolve_path(path)
            if not resolved.exists():
                raise FileConnectorError(f"File not found: {path}")

            stat = os.stat(resolved)
            result = {
                "size_bytes": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }

            # Count lines for text files
            try:
                with open(resolved, "r", encoding="utf-8") as f:
                    line_count = sum(1 for _ in f)
                result["line_count"] = line_count
            except (UnicodeDecodeError, IOError):
                # Binary file or encoding issue - skip line count
                result["line_count"] = None

            return result
        except FileConnectorError:
            raise
        except Exception as e:
            raise FileConnectorError(f"Failed to get stats for {path}: {e}")

    def exists(self, path: str) -> bool:
        """Check if file exists.

        Args:
            path: Relative path to file.

        Returns:
            True if file exists, False otherwise.
        """
        try:
            resolved = self._resolve_path(path)
            return resolved.exists() and resolved.is_file()
        except FileConnectorError:
            return False
