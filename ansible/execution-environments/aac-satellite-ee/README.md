# aac-satellite-ee

Execution environment for the AAC × Red Hat Satellite work. Carries the
**certified** `redhat.satellite` collection, which the dynamic inventory needs
and which is not available from public Galaxy.

See `execution-environment.yml` for why this is a separate EE rather than an
addition to the shared compliance EE.

## Building

The build resolves certified content, so it needs a credentialed Automation Hub.
Everything hub-specific is a build arg — nothing about a particular hub is
committed here.

### Against a private Automation Hub (gateway token)

```bash
ansible-builder build \
  -f execution-environment.yml -t aac-satellite-ee:v1.0.0 -c ./context \
  --build-arg GALAXY_HUB_URL=https://<hub>/api/galaxy/content/rh-certified/ \
  --build-arg GALAXY_HUB_TOKEN=<gateway token> \
  --build-arg GALAXY_HUB_VALIDATE_CERTS=False \
  --build-arg ANSIBLE_GALAXY_CLI_COLLECTION_OPTS=-c \
  --extra-build-cli-args="--network=host"
```

`--network=host` is needed whenever the hub route resolves through the build
host's `/etc/hosts` rather than public DNS; without it the galaxy stage cannot
reach the hub at all.

**`ANSIBLE_GALAXY_CLI_COLLECTION_OPTS=-c` is a lab accommodation, not the recipe.**
It disables certificate verification and belongs only to a hub presenting a
self-signed certificate. A hub with a proper certificate should omit it — this EE
exists to carry *certified, supported* content, and turning verification off by
habit while building it is the wrong default to copy into a customer build.

### Against console.redhat.com (offline token)

```bash
ansible-builder build \
  -f execution-environment.yml -t aac-satellite-ee:v1.0.0 -c ./context \
  --build-arg GALAXY_HUB_TOKEN=<offline token> \
  --build-arg GALAXY_HUB_AUTH_URL=https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token
```

`GALAXY_HUB_AUTH_URL` **must be passed explicitly** — it defaults to empty on
purpose, see the note in `execution-environment.yml`.

## Four things that will bite, all confirmed the hard way

| Symptom | Cause |
|---|---|
| `HTTP Error 400: Bad Request` resolving versions | `auth_url` set while using a **gateway** token. SSO exchange only applies to an offline token. Reads like the collection is missing. |
| `CERTIFICATE_VERIFY_FAILED` *after* the version resolves | `validate_certs = False` covers the API but **not** the artifact download. Pass `ANSIBLE_GALAXY_CLI_COLLECTION_OPTS=-c`. |
| `assemble ... exit status 127` | The base image is Fedora 39 with **no `/usr/bin/dnf`**. Handled by `options.package_manager_path`. |
| Collection resolves but the plugin is missing at runtime | `ansible.cfg` is not picked up implicitly. It is copied in via `additional_build_files` for its `enable_plugins` line. |

The token is written only in the **galaxy stage**, which is discarded — verify
with `podman history --no-trunc <image> | grep <token>` (expect no match).

## Verifying a build

```bash
podman run --rm <image> ansible-galaxy collection list redhat.satellite
podman run --rm <image> ansible-doc -t inventory redhat.satellite.foreman
```

The second is also enforced as a build gate: the image **fails to build** if the
certified collection did not resolve, rather than shipping an inventory plugin
that silently returns zero hosts.

Against a live Satellite, `ansible-inventory -i satellite.foreman.yml --graph`
run inside the EE should produce `foreman_content_view_*`,
`foreman_lifecycle_environment_*` and `os_*` groups.
