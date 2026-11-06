# Security policy

Use a private GitHub security advisory for suspected vulnerabilities when available. Ordinary correctness bugs may use public issues.

Gander is designed to consume untrusted NDJSON with a 65,536-byte retained-record limit. Malformed and oversized records are rejected and framing resumes at the next record boundary.

Gander does not provide authentication, encryption, persistence, or network isolation; those belong to the invoking system.
