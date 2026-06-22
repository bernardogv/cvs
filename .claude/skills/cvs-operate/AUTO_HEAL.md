# Auto-heal playbook

Load this when a `preflight`, `run-json`, or `exec-json` report comes back
`verdict: fail`. Don't just relay the failure — **diagnose from the structured
finding and propose a fix** before escalating.

**The rule that makes this reliable:** branch on the JSON `findings[]`, never on
scraped log text. Each finding has stable keys — `preflight` → `{node, check,
ok}`, `exec-json` → `{node, issue}` / `nodes[].{reachable, exit_code}`,
`run-json` → `{test, outcome, message}`. Match the `check`/`issue`/`outcome`
field, not a regex over output.

**Safety still applies.** A "fix" is a mutation, and every mutation runs through
`exec-json --dry-run` (preview) → human approval → apply (per *Safety & SSH
access* in SKILL.md). Auto-heal is autonomous in *diagnosis*, never in *mutation*.
That's the deliberate difference from a free-auto-fix agent: we propose, preview,
and re-check — we don't silently change a fleet.

## Decision tree (keyed to real findings)

```
preflight finding {check: "reachability", ok: false}
  → node unreachable. Confirm with: exec-json --cmd "echo ok" --nodes <n> --dry-run
  → likely SSH/network/powered-off; name the node + cause. ESCALATE (don't guess creds).

preflight finding {check: "rocm_version", ok: false}
  → versions differ across nodes. Show per-node version (from the finding/exec-json).
  → SUGGEST the install command; ESCALATE — never auto-install a driver.

preflight finding {check: "gpu_count", ok: false}
  → propose: exec-json --cmd "rocm-smi --showid" + "lspci | grep -i amd" --nodes <n>
  → bundle output; ESCALATE (hardware — RMA/seating, not software-fixable).

preflight finding {check: "rdma" | "firewall", ok: false}
  → propose (dry-run): exec-json --cmd "sudo ufw status" --nodes <n>
  → if firewall blocks RDMA ports, SUGGEST the scoped disable; ESCALATE to apply.

preflight finding {check: "numa_balancing", ok: false}    # safe, reversible
  → PROPOSE-FIX: exec-json --cmd "echo 0 | sudo tee /proc/sys/kernel/numa_balancing"
  → preview → approval → apply → re-run preflight to confirm the finding clears.

run-json finding {outcome: "failed"} on rccl_perf / regression
  → low/zero bandwidth: check env + interfaces. Propose: exec-json --cmd "ibstat".
  → compare against a stored baseline: cvs compare baseline run.json --against <name>.
  → ESCALATE with the diagnostic bundle if numbers stay degraded.

exec-json node {reachable: false}
  → transport never came up (DNS/auth/refused — see remote_exec_lib signatures).
  → fix SSH (key perms 600, alias, port), not the command. ESCALATE if still false.

any finding {issue: "container not found" | image missing}    # safe
  → PROPOSE-FIX: exec-json --cmd "docker pull <image>" → approval → re-run the test.
```

## Fix tiers

| Tier | Action | Examples |
|------|--------|----------|
| **Safe** | dry-run → approval → apply → re-check | numa_balancing, docker pull, chmod 600 key |
| **Suggest** | show the exact command, let the human run it | firewall rules, env vars, GRUB/IOMMU |
| **Escalate** | bundle diagnostics, never touch | reboot, driver install, hardware/RMA |

## Diagnostic bundle (collect before escalating)

One read-only sweep, parsed as JSON per node:

```
cvs exec-json --cmd "rocm-smi --showallinfo" --nodes <bad> --format json
cvs exec-json --cmd "ibstat"                 --nodes <bad> --format json
cvs exec-json --cmd "dmesg | tail -50"       --nodes <bad> --format json
cvs exec-json --cmd "uname -r; cat /etc/os-release" --nodes <bad> --format json
```

Summarize the `nodes[]` outputs into one block: node, failing check, evidence.

## Escalate

1. Build the diagnostic bundle above.
2. **If the Atlassian MCP is connected**, open a Jira ticket: title = `<suite>
   failed on <nodes>`, body = the structured findings + the bundle. Link the run
   JSON. Report the ticket key back.
3. **If not**, print the same summary for the user to file manually. Never invent
   a ticket system that isn't connected.

<!-- ponytail: this is agent guidance (markdown), not engine code — the heal logic
     lives in how the agent chains existing JSON-contract commands. Add code only
     if a fix needs atomic multi-step orchestration the agent can't express. -->
