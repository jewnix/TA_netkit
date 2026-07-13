# Changelog

All notable changes to the NetKit Add-on are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-13

### Added

- Ping input measuring TCP connect latency to host:port targets, IPv4 and IPv6.
- Speedtest input measuring Cloudflare download, upload, and latency.
- Selectable Speedtest bandwidth profiles: low, standard, high, and custom.
- In-app UI for configuring probe inputs.
- Per-input diagnostic logging to _internal as sourcetype netkit_log.
- Index-time parsing for the netkit:ping, netkit:speedtest, and netkit_log sourcetypes.
