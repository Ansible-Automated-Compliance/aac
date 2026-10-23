# PQC Readiness — what is collected, what is attested, what the policy decides

**Version:** v1.0
**Date:** 2026-10-21
**Authors:** Tim Coulter · Claude (Anthropic)

The Rego library's `frameworks/federal/pqc` policy (v1.0, in the library since 2026-10-06) evaluates
post-quantum cryptography readiness against FIPS 203/204/205, NIST IR 8547, Executive Order 14412
with OMB M-26-15, and NSA CNSA 2.0. Until this release nothing in the product collected the facts
it reads. This page is the contract between the collector, the site and the policy.

## The division of labour

| Input | Comes from | Who can change it |
|---|---|---|
| `input.pqc.crypto_inventory` | the host, read by `ansible/tasks/collect_pqc_crypto_facts.yml` | nobody; it is what the host is running |
| `input.pqc.profile`, `inventory.*`, `agility.*`, `federal.*`, `nss.*` | the site, in `ansible/vars/pqc_attestations.yml` (gitignored; copy the `.example`) or extra_vars | a named person, recorded in `pqc_attested_by` |
| `pqc_migration_planned` per asset | the site, `pqc_migration_planned_assets` / `pqc_migration_planned_default` | the migration programme |

An attestation that is absent is absent in the input, and the policy reports it as a violation. The
collector ends every run with `end:ok`; without that marker no `crypto_inventory` is emitted and the
playbook refuses to store a result. Nothing is ever defaulted to a pass.

## What the collector reads on a Linux host

All read-only, as root, names and algorithms only. No private key, certificate body or key material
leaves the host.

| Line | Source | Becomes |
|---|---|---|
| `cert\|path\|alg\|bits\|curve\|sigalg` | every `*.crt` / `*.pem` in `/etc/pki/tls/certs` and `pqc_extra_cert_dirs`, through `openssl x509 -text` | one `signature` row (`RSA-2048`, `ECDSA-P-256`, `DSA-1024`, `ED25519`, `ML-DSA-65`, …) and one `hashing` row for the signature hash (`SHA-256`, `SHA-1`, `MD5`) |
| `sshkey\|path\|type\|bits` | `/etc/ssh/ssh_host_*_key.pub` through `ssh-keygen -lf` | one `signature` row (`RSA-3072`, `ECDSA-P256`, `ED25519`) |
| `kex\|alg` | sshd's effective list, `sshd -T` → `kexalgorithms` | one `key_establishment` row per algorithm on asset `<host>:sshd`; `diffie-hellman-group*` is renamed `DH-group*` so the policy's finite-field DH prefix matches |
| `tls\|port\|group\|protocol` | for each port in `pqc_tls_probe_ports` that is listening, the group `openssl s_client -brief` negotiates with the listener | one `key_establishment` row on asset `<host>:tls:<port>` (`X25519`, `X25519MLKEM768`, `secp256r1`, `ffdhe2048`) |
| `openssl`, `mlkem_available`, `crypto_policy`, `fips` | `openssl version`, `openssl list -kem-algorithms`, `update-crypto-policies --show`, `/proc/sys/crypto/fips_enabled` | `system_info` in the stored evidence; informational |

The policy classifies each row itself: a quantum-vulnerable public-key algorithm with no migration
planned is a NIST IR 8547 violation, a broken hash is a FIPS 180-4 violation, a malformed row is an
input-contract violation, and anything carrying a FIPS PQC marker (ML-KEM, ML-DSA, SLH-DSA, LMS,
XMSS, Kyber hybrids) counts as protected. The mapper only renames; it never reclassifies.

## Scoring

The policy reports `controls_evaluated` (10 on the general profile, 14 federal, 18 nss) and a
violation list in which the data-driven checks produce one entry per offending asset. The stored
row caps `failed_controls` at `controls_evaluated`, so a host with twenty vulnerable assets scores
the control class as failed once rather than going negative; the asset counts
(`inventory_assets_total`, `inventory_assets_pqc`, `inventory_assets_quantum_vulnerable`) are stored
in the row's metadata and in the report file, and every violation entry is kept.

## Running it

1. Load the `pqc` loader key on the compliance engine ("AAC - Load OPA Policies").
2. Make sure `pqc: compliance` is in `opa_framework_map` (`site_config.yml.example` carries it).
3. Seed the template once: "AAC - Seed PQC Readiness Template".
4. Copy `ansible/vars/pqc_attestations.yml.example` to `pqc_attestations.yml` and have the
   programme owner set what is true, or pass the same keys as extra_vars.
5. Launch "AAC - PQC Readiness Assessment" with a LIMIT of the Linux hosts to assess.

Prove the contract without a host: `tests/pqc_mapper/README.md`.

## Known limits (v1.0)

- Linux only. Windows (`certutil`, Schannel) and network devices are not collected yet.
- The TLS probe reports what a local `openssl s_client` negotiates with the listener, which is the
  server's preference against that client; it does not enumerate every group the listener offers.
- Only certificate files in the directories listed are read; certificates inside keystores (Java,
  NSS databases) and application-embedded certificates are not.
- OpenSSH's `sntrup761x25519-sha512` hybrid is quantum-resistant but not a FIPS PQC algorithm,
  so the policy counts it as neither vulnerable nor protected. Under NIST IR 8547 the migration
  target is `mlkem768x25519-sha512` (OpenSSH 9.9 and later), which does count as protected.
- A certificate or host key the host cannot parse is recorded in `system_info.collector_notes`
  and produces no inventory row; it is evidence missing, not a classification.
- The federal and NSS booleans are declarations. The collector gives the programme owner the
  evidence to decide them; it does not decide them.

---

*Co-authored by Claude (Anthropic).*
