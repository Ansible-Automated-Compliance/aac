# RHPDS — demo environment provisioning

RHPDS clusters exist to run AAC demos, and their provisioning tooling moved to
the demos repository with the Phase 6 split (2026-09-01):

**https://github.com/ynotbhatc/aac-demos → `demos/rhpds/provisioning/`**

Start with `INSTALL.md` there. The provisioning stack installs the AAC product
(this repository, via the "Compliance Automation" project) and the demo content
("AAC Demos" project) onto a fresh RHPDS AAP cluster.

For product installation on infrastructure you own, see
[`install/SUPPORT_MATRIX.md`](../SUPPORT_MATRIX.md) and the `standard/`,
`existing-aap/`, and `config-as-code/` methods.
