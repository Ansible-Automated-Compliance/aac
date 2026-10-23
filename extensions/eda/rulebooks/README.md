# EDA Rulebooks — classification and constraints

EDA discovers rulebooks by **bare filename from this directory only** (verified against the
live controller: all 18 register flat from `extensions/eda/rulebooks/`, project-relative).
Two consequences:

1. **Do not move rulebook files into demo directories.** A moved rulebook deregisters on the
   next project sync and its activation dies. The demo rulebooks below migrate physically only
   in restructure Phase 6, when the demos repository gets its **own** EDA project.
2. **Rulebooks dispatch by AAP template NAME.** A renamed or never-seeded template makes a
   rulebook a *silent no-op* — the event fires, nothing runs, nothing errors. CI now guards
   this: `scripts/check_eda_template_refs.py` fails any PR whose rulebook references a template
   name defined nowhere else in the repo. Acknowledged exceptions live in
   [`known_unseeded.yml`](known_unseeded.yml) with reasons.

## Classification (Phase 3 of the handover restructure plan)

| Rulebook | Class | Notes |
|---|---|---|
| `compliance_drift_detection.yml` | **core** | Event-driven drift — product headline |
| `compliance_scheduled_drift.yml` | **core** | |
| `compliance_system_events.yml` | **core** | |
| `compliance_webhook_events.yml` | **core** | Webhook port 5000 |
| `compliance_oracle_events.yml` | **core** (aspirational) | References an unimplemented template — see `known_unseeded.yml` |
| `authorized_keys_drift.yml` | **core** | Primary EDA drift trigger (SSH key hygiene) |
| `nerc_cip_events.yml` | **core** | Framework enforcement |
| `ai_governance_enforcement.yml` | **core** | Webhook port 5002; dispatches `AAC_Sentinel_AIControls` (now seeded) |
| `aac_comply_webhook.yml` | **core** | Enforcement lane (git check-in gate) |
| `golden_image_enforcement.yml` | **core** | Golden-image enforcement is product capability |
| `golden_image_enforcement_webhook.yml` | **core** | |
| `golden_image_demo.yml` | **demo → Phase 6** | Demo narrative variant |
| `golden_image_drift_macaap.yml` | **demo → Phase 6** | mac-aap lab variant |
| `ami_events.yml` | **demo → Phase 6** | AMI demo events (webhook port 5001) |
| `ami_golden_meter_demo.yml` | **demo → Phase 6** | |
| `windows_golden_enforcement.yml` | **demo → Phase 6** | Windows golden-image demo |
| `lab10_itsm_ticket_handler.yml` | **demo → Phase 6** | Lab10 showcase |
| `sentinel_github_webhook.yml` | **demo → Phase 6** | Sentinel git-gate demo (port 5003; pushes to `demo/sentinel-sandbox`) |

At Phase 6, the **demo → Phase 6** rows move to the `aac-demos` repository under its own EDA
project; their activations are recreated there and retired here in the same change.
