# Guardrails Workplan — how we turn the territory into enforceable rules

> **Status:** Ideation **v3** (revised after rubber-duck round 2; v2 archived [here](../_archive/round-2-v2/plan/02-guardrails-workplan.md), v1 [here](../_archive/round-1-v1/plan/02-guardrails-workplan.md)) · **Date:** 2026-10-30 · Part of the [follow-up plan](00-follow-up-plan.md) · Input: [08 — guardrail territory](../ideation/08-trust-safety-and-guardrail-topics.md)
> **Rule:** *a guardrail without an owner, an enforcement mechanism and a test is a wish.*

---

## 1. Goal and definition of done

**Goal:** before any code is written, have a **ratified, testable set of guardrails** that the platform must obey, and that security, Finance, legal/compliance and platform owners recognise as theirs.

**Definition of done (Phase 1 exit):**

1. **Guardrail Charter v1** ratified (principles + scope + roles).
2. **Safety invariants** ratified (the 16 candidates in [08 §4](../ideation/08-trust-safety-and-guardrail-topics.md#4-candidate-safety-invariants-non-negotiables-to-ratify)), each with an enforcement mechanism and a test.
3. **Autonomy policy v1**: levels, entry/exit criteria, downgrade triggers, **enrolment rules for veto windows**, kill-switch authority and drill cadence.
4. **Threat model v0** covering at least the 41 seeded threats (T1–T41), each mapped to a control or an accepted risk.
5. **Data-handling statement:** what data may be read, what may reach a model, retention, residency, redaction, people-data rules, and the **disclosure statement** for people.
6. **Responsible-AI impact assessment v0** and **DPIA screening** completed.
7. **OSS governance note:** contribution model, trademark/naming findings, internal release process check — *the licence is decided: MIT (D2).*
8. **Guardrail test plan:** red-team scenarios, chaos drills, evaluation gates, privacy and authority tests — each owned.
9. Open decisions recorded with owners and dates; **stop criteria K1–K7** ratified.
10. **Control matrix** complete for every invariant ([§4.1](#41-the-control-matrix--the-traceability-gate)).
11. **Minimum write-safety harness** specified ([§4.2](#42-the-minimum-write-safety-harness)) — and, later, passing before any customer-facing write test.
12. **RACI and liability model** (who accepts the workload trade-off, who owns controls, who owns agent behaviour, who owns operational accountability), the **orphan custodian** model, and the **independence profile** for the Challenger and Auditor ([04 §4.6](../ideation/04-agent-crew.md#46-independence-profile-challenger-and-auditor)).
13. **Trust root decided (D16)** — a prerequisite for shipping *any* behaviour-affecting artefact (playbook, prompt, model, evaluator, policy) in *any* release, including Release 1: key custody, approval quorum, separation from Warden administration, signed provenance, emergency revocation, a pinned rollback release and an independent audit of release state.
14. **Ledger-versus-erasure design proven** (cryptographic deletion of evidence while the hash chain stays valid) — a **release blocker** for the first customer-facing write, not a later nicety.
15. **Classification rubric ratified** as a *derived, linted* property: the class follows from the typed effects of an operation, a declared class below the derived one is rejected, and the catalog linter ([`tools/check-docs.py`](../../tools/check-docs.py)) is the first enforcement point ([06 §2](../ideation/06-closed-loop-actions-and-autonomy.md)).
16. **Phase-0.5 exceptions signed (D17)** and the **cost-brake certifier named (D18)** — the two signers that the sprint and the first automatic-pause class depend on.

---

## 2. Who needs to be in the room

| Role | Why | Decides |
|---|---|---|
| **Operator (project owner)** | Accountable for direction | Scope, trade-offs, residual risk acceptance (with others) |
| **Security lead** | Identity, threat model, kill switch | G2, G9, parts of G1/G3 |
| **Privacy / DPO** | People-data, logs, retention | G4, G8-03 |
| **Legal / compliance** | AI Act, sector overlays, OSS licence/trademark | G8, G11, G13 |
| **Finance partner / controller** | Savings integrity, purchase authority | G6, G13 |
| **Platform / service owner** | Change safety, operability | G3, G10 |
| **FinOps lead** | The dial and the kill switch | G1, G6 |
| **Responsible-AI lead** | Harms, oversight design | G12, G5, G7 |
| **Resource-owner champions (2–3)** | The people we will ask | G7, G1-07, G1-08 |
| **Change-advisory / ITSM owner** | Standard changes, freeze calendar | G3-04, G3-09 |
| **Billing owner / authorised buyers** | Who may sign commitment transactions | G6-04, G13, G2-11 |
| **Shared-platform owner** | Shared gateways, workspaces, firewalls | G1-12, G3 (affected-party rule) |
| **SOC / incident commander** | Incident state; security-relevant data | G3-10, G3-11, G4-11 |
| **Data owners** (for R3-Data classes) | Approve collection-reducing changes | G4-11 |
| **Works council / employee representative** (where applicable) | People-data and monitoring concerns | G4-08 |
| **Open-source programme contact** | Release process | G11 |

**Role-play mode (to start now, never a substitute for real sign-off):** because the operator starts alone, AI can role-play each reviewer (CISO, DPO, Finance controller, works-council representative, platform owner) to pre-draft positions and surface objections early. Output is labelled **simulation**, and each domain is re-reviewed by the real counterpart before ratification.

---

## 3. Session plan

| WS | Domains | Pre-read | Key questions (from doc 08) | Outputs |
|---|---|---|---|---|
| **WS0 — Charter** | all | Vision, [08](../ideation/08-trust-safety-and-guardrail-topics.md) §1, §4 | Principles; roles; **stop criteria K1–K7** (pre-registered in Phase 0.5); what "HITL" means for us | Charter draft; ratified stop criteria |
| **WS1 — Autonomy, oversight & identity** | G1, G2 | [06](../ideation/06-closed-loop-actions-and-autonomy.md), [04](../ideation/04-agent-crew.md) | G1-01…13, G2-01…11 | Autonomy policy v1; **enrolment rules**; **orphan custodian** and **RACI** models; identity principles; approval-binding rules; control-plane tag rules |
| **WS2 — Change safety & operability** | G3, G10 | 06 §3 | G3-01…11, G10-01…06 | Classification (one class plus attributes, R3-Data); undo windows; **precedence of stops**; **cost-brake classes**; freeze/incident rules; fail-safe rules; kill-switch runbook |
| **WS3 — Data, privacy & people** | G4, G12 (part) | [07](../ideation/07-ownership-and-organization.md) §12, research/04 | G4-01…11 | Data-handling statement; DPIA screening; people-data rules and **disclosure statement**; ledger vs erasure design; R3-Data approval rules |
| **WS4 — AI safety, quality & economics** | G5, G6 | research/03 | G5-01…14, G6-01…06 | Evaluation gates; red-team scope; numeric-integrity rule; **independence profile and drill**; **governed-release rules**; AI-cost budgets; counting rules |
| **WS5 — Communication ethics & compliance** | G7, G8, G12 (rest) | [05](../ideation/05-human-interaction-concepts.md) | G7-01…08, G8-01…07, G12-01…04 | Communication standard (AI disclosure, consent, attention rules, **private-first escalation**, anti-phishing); regulatory map; RAI assessment v0 |
| **WS6 — Platform security, OSS, commercial** | G9, G11, G13, G14 | T1–T41 | G9-01…07, G11-01…06, G13-01…04, G14-01 | Threat model v0; **declarative-playbook trust model**; OSS governance note; purchase-authority rules and **authorised-signer register** |
| **WS7 — Ratification** | all | all outputs | Residual risk; conflicts between domains | **Guardrail Charter v1 ratified**; invariants ratified; **control matrix reviewed**; open decisions assigned |

*Each working session: 90–120 minutes, a facilitator, a scribe (AI-assisted, human-verified), decisions recorded as GDRs in the same week.*

---

## 4. The Guardrail Decision Record (GDR)

```markdown
# GDR-G1-004 — Short title

- **Status:** Proposed | Ratified | Superseded by GDR-...
- **Domain:** G1 Autonomy & oversight
- **Context:** why this decision is needed (threat IDs, constraint IDs, stakeholders)
- **Options considered:** A, B, C with trade-offs
- **Decision:** the rule, in one or two sentences
- **Rationale:** evidence, sources, precedent
- **Enforcement mechanism:** Preventive (gate) | Detective (monitor) | Directive (process) | Corrective (rollback)
- **How it is tested:** the executable or procedural test that proves it holds
- **Owner / reviewers:** named roles
- **Consequences / residual risk:** what we accept
- **Review date:** when we must look at this again
```

### 4.1 The control matrix — the traceability gate

A workplan full of excellent workshops is still not proof. Before any write-capable slice, every invariant must be traceable end to end:

`threat → invariant → GDR → policy rule → enforcement point → test vector → telemetry → owner`

An invariant with no enforcement point and no negative test is an **aspiration**, and the matrix must say so. Illustrative rows (IDs are placeholders):

| Threat | Invariant | GDR | Policy rule | Enforcement point | Test vector | Telemetry | Owner |
|---|---|---|---|---|---|---|---|
| T37 approval–artefact swap | 3 | GDR-G2-005 | Approval binds to commit SHA, plan digest and target-state hash | Gatekeeper, pre-execution | Re-render the plan after approval ⇒ execution refused | Stale-approval counter | Security lead |
| T18 cross-tenant mix-up | 14 | GDR-G2-009 | Tenant identity on every artefact | Every service boundary, fail closed | Replay a case with a mismatched tenant ⇒ every hop rejects | Boundary-rejection counter | Platform owner |
| T38 silence exploitation | 15 | GDR-G1-007 | Veto window requires enrolment and proof of delivery | Gatekeeper | An un-enrolled owner ⇒ no L3 action ever fires; an undelivered notice ⇒ the clock never starts | Enrolment-check log | FinOps lead |

### 4.2 The minimum write-safety harness

**Prerequisite for any customer-facing write test.** A small, automated suite of *negative* tests, each of which must pass:

- A missing or mismatched **tenant identity** stops the action (fail closed).
- A **stale or swapped approval** (changed commit SHA, plan digest, target-state hash, or deploying identity) is rejected.
- **Locks and legal holds** are never bypassed, and the order of stops is enforced.
- No **L3 action** runs for an owner who has not enrolled, or whose notice delivery is unproven.
- **Enrolment is a precise key** (owner or delegate, tenant, scope, environment, action class, reversibility class, expiry, envelope version): a *dev* enrolment never authorises *prod*, and an expired, revoked or mismatched record means no L3 action fires ([06 §3 item 6](../ideation/06-closed-loop-actions-and-autonomy.md)).
- **R3-Data** classes never run at L3 or L4.
- **Classification is derived, not declared:** an operation whose declared class is below the class derived from its typed effects is rejected, and a catalog row with a hybrid class, R3/R3-Data at L3 or above, or a transaction above L2 fails the lint.
- **Affected-party consent:** an action with a *consent-required* consumer and no named acknowledgement or named risk acceptance keeps Approve locked; "no objection" is silence and never counts ([06 §3 item 12](../ideation/06-closed-loop-actions-and-autonomy.md)).
- **Control-plane tag changes** (owner, environment, criticality, exclusion) invalidate enrolment, envelope membership and open approvals; the claim is re-read, and its version bound, *before* execution.
- **No commitment transaction** runs without a human signature on the **exact manifest** — price, term, scope, exchange and cancellation terms, the asset set and the signer included — and the preparer cannot sign; a manifest that differs from what was signed is refused.
- **Instrumentation is an action:** enabling query audit, diagnostic settings or sampling changes needs its own approval, cost cap, end date and deletion rule, and expired instrumentation is removed or re-approved ([06 §3 item 13](../ideation/06-closed-loop-actions-and-autonomy.md)).
- The **cost brake** takes its signal from a separately administered source; if the integrity of that signal is in doubt it **pages a human** instead of acting.
- The **approver's authority** is checked at approval *and* again at execution.
- The **rate limiter** and stop-the-line trigger fire.
- With a degraded dependency (chat, model, policy engine) **nothing acts**.
- The **kill switch** takes effect within the tested time.

---

## 5. Three layers of every guardrail

| Layer | Form | Example |
|---|---|---|
| **1. Principle** | Human-readable rule | "Agents cannot modify their own autonomy." |
| **2. Policy** | Machine-readable, versioned | Autonomy policy; policy envelopes ([06](../ideation/06-closed-loop-actions-and-autonomy.md) §5) |
| **3. Test** | Executable or procedural | Red-team scenario T1; a drill that proves the kill switch works in N minutes; an eval that fails the build if a number is not traceable to a deterministic tool |

**Enforcement taxonomy:** *Preventive* (the system cannot do it) › *Detective* (we notice fast) › *Corrective* (we undo) › *Directive* (people agree to behave). Prefer preventive; use detective + corrective where prevention would cripple usefulness; use directive only with evidence it will be followed.

---

## 6. The guardrail test suite (to design in Phase 1, build in Phases 5–6)

| Test family | Examples |
|---|---|
| **Red-team scenarios** | T1 indirect prompt injection via tag/log/reply; T3 approval phishing; T4 confused deputy; T7 malicious playbook; T8 secrets in logs; T9 wrong-owner approval; **T31 control-plane tag manipulation; T32 evidence manipulation; T34 approval abuse; T35 poisoned feedback; T39 classification laundering; T40 instrumentation creep; T41 custodian overreach** |
| **Chaos & drills** | Kill-switch drill; chat-platform outage; model outage; stale-approval flood; token-spike (denial of wallet); change-freeze collision; **correlated-failure drill** for the Challenger and Auditor |
| **Evaluation gates** | Numeric integrity; groundedness; confidence calibration; Challenger independence; regression on every prompt/model/tool change (each a **governed release**); **held-out sets held by the independent evaluation custodian** |
| **Privacy tests** | Redaction efficacy on seeded secrets/PII; retention enforcement; people-data minimisation; **ledger-versus-erasure** (cryptographic deletion of evidence while the hash chain stays valid) |
| **Authority tests** | Approver without RBAC on the target is refused; delegation expiry; approval bound to **plan version, commit SHA, plan digest and target-state hash** |
| **Communication tests** | AI disclosure present; attention budgets honoured; phishing-resistance of messages; accessibility checks; **no named person in any shared space for not answering** |
| **Safety-invariant tests** | One test per invariant (16); failing any blocks release — the [write-safety harness](#42-the-minimum-write-safety-harness) is the minimum |

---

## 7. Change control for the guardrails themselves

- Only **humans** may change guardrails; every change is a GDR with security and FinOps-lead review.
- Guardrails are **versioned**; autonomy policies carry an **expiry**; reviews are scheduled.
- A change that *loosens* a guardrail requires a **higher** bar than one that tightens it.
- Every incident or regret event triggers a *guardrail retrospective* (what would have prevented this?).

---

## 8. Sequencing and sizing (relative)

| Step | Size | Depends on |
|---|---|---|
| WS0 Charter | S | — |
| Role-play pre-drafts for WS1–WS6 | M | WS0 |
| Real sessions WS1–WS6 | L (spread over several weeks) | Counterparts' availability |
| WS7 Ratification | S | WS1–WS6 |
| Control matrix and write-safety harness spec | M | WS7 |
| Guardrail test plan | M | WS7 |

**Critical path risk:** availability of the real security/privacy/Finance counterparts. Start by booking them.

---

## 9. What this gives the later phases

- **Phase 2:** outreach ethics for the Wizard-of-Oz pilot; communication standard.
- **Phase 3:** each playbook declares **exactly one reversibility class** plus its attributes, its data needs and its protected exceptions.
- **Phase 4:** spikes have *pass criteria* tied to the guardrails.
- **Phase 5:** the safety architecture implements the preventive guardrails.
- **Phase 6–7:** every slice ships with its guardrail tests; autonomy promotions follow the autonomy policy.
