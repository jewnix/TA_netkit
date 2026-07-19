# NetKit Add-on (TA_netkit)

NetKit's collection add-on runs three scheduled probe inputs on any full Splunk
Enterprise instance (Heavy Forwarder, standalone, or search head; not a
Universal Forwarder) and forwards the results to your indexers. Its companion
search-head app - prebuilt dashboards plus search-time JSON field extraction -
is [jewnix/netkit](https://github.com/jewnix/netkit).

## Supported Splunk versions

Splunk Enterprise 10.0 or later, on a full instance. The add-on runs on the
Splunk-bundled Python interpreter and needs no external packages.

| Splunk | Bundled Python the probes use | Notes |
|---|---|---|
| 10.0 | 3.9 | Full probe functionality; `chain_len` is `null` (see below). |
| 10.2 and later | 3.13 | Full fidelity. |

## What the probes do

- **Ping** measures **TCP connect latency** - the time to complete the TCP
  handshake to `host:port` - not ICMP round-trip.
- **Speedtest** measures download/upload throughput and latency against
  Cloudflare's speedtest endpoints (`speed.cloudflare.com`) over TLS-verified
  HTTPS.
- **TLS certificate inspection** connects to each `host:port`, verifies the
  presented certificate against the add-on's bundled CA list (certifi) or a
  configured private CA, and records the certificate's identity, validity
  window, and the verification verdict.

All three probes are pure Python, standard library only, with no shelling out
to system `ping` or `speedtest` binaries.

## Install (full Splunk Enterprise instance)

1. Install the packaged tarball (Apps > Manage Apps > Install app from file), or
   drop it in `$SPLUNK_HOME/etc/apps/` and restart.
2. Open the NetKit app in Splunk Web > Inputs. Create a Ping input (targets,
   samples, timeout, interval), a Speedtest input (bandwidth profile,
   interval), and/or a TLS certificate inspection input (targets, handshake
   timeout, certificate authority, interval). Leave the destination index to
   the admin default or set it per input.
3. Configure forwarding to your indexers (outputs.conf / deployment-managed) so
   the destination index and `_internal` are forwarded.

## Ping targets (IPv4 and IPv6)

Ping measures TCP connect latency, so every target needs a port. Targets are a
comma-separated list of `host:port`; the host may be a hostname, an IPv4
address, or an IPv6 literal. IPv6 literals are written without brackets, and the
last colon always separates the port:

    1.1.1.1:443, example.com:8089, 2606:4700:4700::1111:443

## Speedtest bandwidth profiles

The Speedtest input's profile sets the transfer sizes per run. Larger sizes
measure fast links more accurately (a single 25 MB stream understates links
faster than about 300 Mbps due to TCP slow-start) but use more data.

| Profile | Download / Upload | Intended link speed |
|---|---|---|
| Low bandwidth | 10 MB / 2 MB | under 50 Mbps |
| Standard (default) | 25 MB / 5 MB | 50-300 Mbps |
| High bandwidth | 100 MB / 20 MB | over 300 Mbps |
| Custom | 1-500 MB / 1-100 MB | your call |

Every run transfers the full download plus upload size, so budget the traffic
against the interval (High at the default 1800s interval is about 5.8 GB/day).
The minimum interval is 300 seconds; the High bandwidth and Custom profiles
require at least 900. A single TCP stream still reads low on links around 1 Gbps
and faster.

## Events

All three probes emit JSON events; fields are extracted at search time by the
companion `netkit` app (`KV_MODE=json`).

- `netkit:ping` - one event per target per run, timestamped at that target's
  completion: `target`, `dest`, `port`, `min_ms`, `avg_ms`, `max_ms`,
  `jitter_ms`, `sent`, `received`, `failure_pct`, `reachable`.
- `netkit:speedtest` - one event per run: `download_mbps`, `upload_mbps`,
  `rtt_ms`, `min_rtt_ms`, `bytes_sent`, `bytes_received`, `server_location`,
  `duration_s`, `ok`, plus `error` with the failure cause when `ok=false`.
- `netkit:tls` - one event per target per run: `target`, `dest`, `port`, `ca`,
  `verify_ok`, `verify_error`, `not_before`, `not_after`, `days_to_expiry`,
  `subject`, `subject_cn`, `issuer`, `issuer_cn`, `san`, `serial`,
  `self_signed`, `is_ca`, `eku`, `tls_version`, `cipher`, `cert_sha256`, and
  `chain_len`, plus the DN-derived fields `subject_org`, `subject_unit`,
  `subject_locality`, `subject_state`, `subject_email`, `issuer_org`,
  `issuer_unit`, `issuer_locality`, `issuer_state`, and `issuer_email`. Each
  DN-derived field appears only when the certificate's subject or issuer
  carries the matching RDN, so its absence is expected, not a probe error.

  **`chain_len` is version-dependent on a successful verification.** When the
  certificate verifies, it is populated on Splunk 10.2 and later (Python 3.13)
  and is `null` on Splunk 10.0 (Python 3.9), because the
  `SSLSocket.get_verified_chain()` API it reads was added in Python 3.13; on a
  verification failure it is `null` on every Splunk version. A `null`
  `chain_len` is the expected degradation, not a probe error; the certificate
  fields extracted from the cert itself are identical across versions.

## Index

This add-on does not create an index. Create the destination index on your Splunk
stack (via ACS / self-service on Splunk Cloud) and route the inputs to it. The
companion `netkit` app references it through the `netkit_index` macro (default
`index=main`).

## Logs

The probes log to per-input files
`$SPLUNK_HOME/var/log/splunk/ta_netkit_<input>.log` (sourcetype `netkit_log`),
auto-ingested to `_internal`.
