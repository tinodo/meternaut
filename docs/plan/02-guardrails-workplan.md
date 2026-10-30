# Guardrails Workplan — how we turn the territory into enforceable rules

> **Status:** Ideation v1 · **Date:** 2026-10-30 · Part of the [follow-up plan](00-follow-up-plan.md) · Input: [08 — guardrail territory](../ideation/08-trust-safety-and-guardrail-topics.md)
> **Rule:** *a guardrail without an owner, an enforcement mechanism and a test is a wish.*

---

## 1. Goal and definition of done

**Goal:** before any code is written, have a **ratified, testable set of guardrails** that the platform must obey, and that security, Finance, legal/compliance and platform owners recognise as theirs.

**Definition of done (Phase 1 exit):**

1. **Guardrail Charter v1** ratified (principles + scope + roles).
2. **Safety invariants** ratified (see [08 §4](../ideation/08-trust-safety-and-guardrail-topics.md#4-candidate-safety-invariants-non-negotiables-to-ratify)), each with an enforcement mechanism and a test.
3. **Autonomy policy v1**: levels, entry/exit criteria, downgrade triggers, kill-switch authority and drill cadence.
4. **Threat model v0** covering at least the 30 seeded threats (T1–T30), each mapped to a control or an accepted risk.
5. **Data-handling statement:** what data may be read, what may reach a model, retention, residency, redaction, people-data rules.
6. **Responsible-AI impact assessment v0** and **DPIA screening** completed.
7. **OSS governance note:** licence decision input, contribution model, trademark/naming findings, internal release process check.
8. **Guardrail test plan:** red-team scenarios, chaos drills, evaluation gates, privacy and authority tests — each owned.
9. Open decisions recorded with owners and dates; **stop criteria** agreed.

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
| **Works council / employee representative** (where applicable) | People-data and monitoring concerns | G4-08 |
| **Open-source programme contact** | Release process | G11 |

**Role-play mode (to start now, never a substitute for real sign-off):** because the operator starts alone, AI can role-play each reviewer (CISO, DPO, Finance controller, works-council representative, platform owner) to pre-draft positions and surface objections early. Output is labelled **simulation**, and each domain is re-reviewed by the real counterpart before ratification.

---

## 3. Session plan

| WS | Domains | Pre-read | Key questions (from doc 08) | Outputs |
|---|---|---|---|---|
| **WS0 — Charter** | all | Vision, [08](../ideation/08-trust-safety-and-guardrail-topics.md) §1, §4 | Principles; roles; stop criteria; what "HITL" means for us | Charter draft; stop criteria |
| **WS1 — Autonomy, oversight & identity** | G1, G2 | [06](../ideation/06-closed-loop-actions-and-autonomy.md), [04](../ideation/04-agent-crew.md) | G1-01…11, G2-01…09 | Autonomy policy v1; identity model principles; approval-binding rules |
| **WS2 — Change safety & operability** | G3, G10 | 06 §3 | G3-01…09, G10-01…06 | Reversibility classification; undo windows; freeze/incident rules; fail-safe rules; kill-switch runbook |
| **WS3 — Data, privacy & people** | G4, G12 (part) | [07](../ideation/07-ownership-and-organization.md) §12, research/04 | G4-01…09 | Data-handling statement; DPIA screening; people-data rules |
| **WS4 — AI safety, quality & economics** | G5, G6 | research/02, 03 | G5-01…12, G6-01…06 | Evaluation gates; red-team scope; numeric-integrity rule; AI-cost budgets; counting rules |
| **WS5 — Communication ethics & compliance** | G7, G8, G12 (rest) | [05](../ideation/05-human-interaction-concepts.md) | G7-01…08, G8-01…07, G12-01…04 | Communication standard (AI disclosure, consent, attention rules, anti-phishing); regulatory map; RAI assessment v0 |
| **WS6 — Platform security, OSS, commercial** | G9, G11, G13, G14 | T1–T30 | G9-01…07, G11-01…06, G13-01…03, G14-01 | Threat model v0; playbook trust model; OSS governance note; purchase-authority rules |
| **WS7 — Ratification** | all | all outputs | Residual risk; conflicts between domains | **Guardrail Charter v1 ratified**; invariants ratified; open decisions assigned |

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
| **Red-team scenarios** | T1 indirect prompt injection via tag/log/reply; T3 approval phishing; T4 confused deputy; T7 malicious playbook; T8 secrets in logs; T9 wrong-owner approval |
| **Chaos & drills** | Kill-switch drill; chat-platform outage; model outage; stale-approval flood; token-spike (denial of wallet); change-freeze collision |
| **Evaluation gates** | Numeric integrity; groundedness; confidence calibration; Challenger independence; regression on every prompt/model/tool change |
| **Privacy tests** | Redaction efficacy on seeded secrets/PII; retention enforcement; people-data minimisation |
| **Authority tests** | Approver without RBAC on the target is refused; delegation expiry; approval bound to plan version |
| **Communication tests** | AI disclosure present; attention budgets honoured; phishing-resistance of messages; accessibility checks |
| **Safety-invariant tests** | One test per invariant; failing any blocks release |

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
| Guardrail test plan | M | WS7 |

**Critical path risk:** availability of the real security/privacy/Finance counterparts. Start by booking them.

---

## 9. What this gives the later phases

- **Phase 2:** outreach ethics for the Wizard-of-Oz pilot; communication standard.
- **Phase 3:** each playbook declares its reversibility class, data needs and protected exceptions.
- **Phase 4:** spikes have *pass criteria* tied to the guardrails.
- **Phase 5:** the safety architecture implements the preventive guardrails.
- **Phase 6–7:** every slice ships with its guardrail tests; autonomy promotions follow the autonomy policy.
