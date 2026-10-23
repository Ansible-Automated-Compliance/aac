# collections/

## Do not add a `requirements.yml` here

A `collections/requirements.yml` in an AAP project is installed **at
project-sync time**. AAP does that install in a sidecar that runs as **root**,
into the shared project cache, which the controller's task container then reads
as the **`awx`** user.

The sidecar leaves directories owned `root:awx` with mode `drwxr-sr-x`. On the
next sync the task container tries to clear the staging directory and cannot:

```
File ".../awx/main/tasks/jobs.py", line 1567, in pre_run_hook
    shutil.rmtree(stage_path)
PermissionError
```

The project sync fails, and because the project is then in `error`, **every job
template that uses it fails too** — at `elapsed: 0.07`, before running anything.
The failure looks like a broken playbook and is not one.

The only recovery is to delete the controller task pod so the cache is
recreated:

```bash
oc delete pod -n aap-operator -l app.kubernetes.io/name=controller-task
```

That is a workaround. It was applied repeatedly over months, and the condition
came back every time, because the requirements file that causes it stayed.

## What was in here, and why it went

`redhat.openshift >= 3.0.0`, for the OpenShift Compliance Operator work.

**Nothing ever used it.** The three playbooks that named it —
`capture_ocp_baseline.yml`, `collate_ocp_nerc_cip.yml`,
`remediate_ocp_nerc_cip.yml` — mentioned it only in header comments. Every
OpenShift object they touch is read and written with `kubernetes.core.k8s_info`
and `kubernetes.core.k8s`, and **`kubernetes.core` is a declared requirement of
the AAC Compliance EE** — see
`ansible/execution-environments/aac-compliance-ee/requirements.yml` (3.0.0 is
what v1.3.0 shipped). A repo-wide search for `redhat.openshift.<module>`
returns nothing.

> It was present in v1.3.0 *without* being declared, as a transitive
> dependency. That is now fixed: relying on a collection that happens to be in
> an image is how a rebuild breaks playbooks that never changed.

So the collection was a phantom dependency: it cost a recurring outage and
bought nothing.

## If you genuinely need a new collection

Add it to the **execution environment**, not here:

```
ansible/execution-environments/aac-compliance-ee/requirements.yml
```

Then rebuild the EE (AAP template *"AAC - Build Compliance EE"*, which must run
on the lab host — the build is `linux/amd64` and will not work on an aarch64
Mac), publish a new tag, and point the execution-environment objects at it.

That is more work than adding a line here, and that is the point: the
collection then ships inside the image, is versioned with it, and no root-owned
files are ever written into the project cache.
