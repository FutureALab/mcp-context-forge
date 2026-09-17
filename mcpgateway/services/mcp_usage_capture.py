"""Extract bounded MCP metadata without retaining tool arguments or results.

Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

# Standard
import json


class MCPUsageCapture:
    """Inspect JSON and SSE messages while forwarding every original byte."""

    def __init__(self) -> None:
        """Create bounded request and response buffers."""
        self.request = bytearray()
        self.response = bytearray()
        self.truncated = False

    def append(self, body: bytes, response: bool = False) -> None:
        """Capture at most 256 KiB per direction."""
        target = self.response if response else self.request
        remaining = 262144 - len(target)
        target.extend(body[:remaining])
        self.truncated = self.truncated or len(body) > remaining

    def details(self) -> dict | None:
        """Return names, protocol outcome, and explicitly reported usage."""
        try:
            request = json.loads(self.request)
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
            return None
        details = {"method": request["method"][:128], "capture_truncated": self.truncated}
        params = request.get("params")
        if isinstance(params, dict):
            name = params.get("name") or params.get("uri")
            if isinstance(name, str):
                details["resource"] = name[:255]
        try:
            responses = [json.loads(self.response)]
        except (ValueError, UnicodeDecodeError):
            responses = []
            for line in self.response.splitlines():
                if line.startswith(b"data:"):
                    try:
                        responses.append(json.loads(line[5:].strip()))
                    except (ValueError, UnicodeDecodeError):
                        continue
        for response in responses:
            if not isinstance(response, dict) or "id" not in request or response.get("id") != request["id"]:
                continue
            result = response.get("result")
            result = result if isinstance(result, dict) else {}
            details["outcome"] = "error" if "error" in response or result.get("isError") is True else "success"
            meta = result.get("_meta")
            meta = meta if isinstance(meta, dict) else {}
            usage = meta.get("usage", result.get("usage"))
            if isinstance(usage, dict):
                for key, aliases in {"input_tokens": ("input_tokens", "prompt_tokens", "inputTokens"), "output_tokens": ("output_tokens", "completion_tokens", "outputTokens")}.items():
                    value = next((usage[a] for a in aliases if a in usage), None)
                    if type(value) is int and 0 <= value <= 10**12:
                        details[key] = value
        return details
