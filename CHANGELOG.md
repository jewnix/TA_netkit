# Changelog

All notable changes to the NetKit Add-on are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-07-21

### Added

- New netkit:tls fields: key_usage, sig_algorithm, pubkey_type, and pubkey_bits, emitted as raw values and named in the netkit app.
- The TLS probe emits per-target error events when the bundled cryptography module is unavailable instead of producing no output.

### Fixed

- Probe events omit fields with no value instead of emitting JSON null, which Splunk extracted as the literal string "null".
- TLS events report ca as certifi instead of system when no private CA is configured, matching the bundled CA list actually used.
- The netkit:tls eku field reports exact certificate usage OIDs (parsed via cryptography) instead of a meaningless bitmask integer, and is_ca reflects the certificate's actual CA flag.

## [1.0.0] - 2026-07-13

### Added

- Ping input measuring TCP connect latency to host:port targets, IPv4 and IPv6.
- Speedtest input measuring Cloudflare download, upload, and latency.
- Selectable Speedtest bandwidth profiles: low, standard, high, and custom.
- In-app UI for configuring probe inputs.
- Per-input diagnostic logging to _internal as sourcetype netkit_log.
- Index-time parsing for the netkit:ping, netkit:speedtest, and netkit_log sourcetypes.
- TLS probe input (netkit_tls_probe) measuring certificate validity, expiry, and chain trust against configured targets.
- Certificate Authorities store for uploading and managing custom CA certificates used to validate probe targets.
- Index-time parsing for the netkit:tls sourcetype.
