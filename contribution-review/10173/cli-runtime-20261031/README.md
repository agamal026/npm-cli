# npm #10173: published CLI and reported-runtime diagnostic

One bounded synthetic diagnostic through the published npm 11.18.0 CLI under Node 22.23.1 on Linux x86_64 **did not reproduce** [npm/cli#10173](https://github.com/npm/cli/issues/10173).
All 11 npm commands completed with exit 0, and all seven recorded disk-check groups passed.
This is diagnostic evidence only: there is no production patch, upstream submission, complete project-suite pass, or acceptance claim.

## What this adds

The earlier synthetic checks called Arborist directly under Node 24.22.1.
This execution invokes the actual published npm CLI, uses the reporter's Node version, and sets the custom prefix through `npm config set prefix ... --location=user` in an isolated user configuration.
It exercises configuration loading and the CLI subprocess boundary while retaining the reviewed same-package optional-alias topology.

The issue was read again on 31 October 2026: it remained open, unassigned, with zero comments and no new reproduction details.
Bounded searches found no directly competing implementation for this issue.
The current [contribution guide](https://github.com/npm/cli/blob/fc517df18fb59a33b39d383c6766690bc427ac06/CONTRIBUTING.md) remains applicable to any future production contribution, including full tests, coverage and posttest lint.
Those project gates were not executed by this diagnostic.

## Runtime provenance

| Component | Verified artifact |
| --- | --- |
| Node | [Official Node 22.23.1 Linux x64 archive](https://nodejs.org/dist/v22.23.1/node-v22.23.1-linux-x64.tar.xz), SHA256 `9749e988f437343b7fa832c69ded82a312e41a03116d766797ac14f6f9eee578` |
| Node checksum source | [Official SHASUMS256.txt](https://nodejs.org/dist/v22.23.1/SHASUMS256.txt) |
| npm | [Published npm 11.18.0 tarball](https://registry.npmjs.org/npm/-/npm-11.18.0.tgz), SHA256 `73f6155215ebabf4ed96dca1f567c2372cc713c33af2e5b9b62fde4e92373e2e`; registry SHA512 integrity also verified |
| Bundled Arborist | 9.9.0, read directly from the extracted npm release |
| Published npm metadata | [Registry metadata](https://registry.npmjs.org/npm/11.18.0) records `gitHead=fef2b1324991a098c64132b77339ba9989b5e3bf` |

The published package identity is distinct from earlier source checkout `a9c8c06d245347da89c798ebc82fdceb221de08b`.
Matching version labels alone do not establish equal source trees or dependency bytes.
No current-checkout workspace modules, `NODE_PATH`, test-only Arborist override, Nock interceptor, or inherited `NODE_OPTIONS` were substituted into this execution.

## Fixture and isolation

All six fixture versions share the package name `@oss-test/cli`.
Each wrapper (`1.0.0` or `2.0.0`) declares aliases named `@oss-test/cli-linux-x64` and `@oss-test/cli-linux-arm64` pointing to platform prereleases of that same package.
Every tarball contains only `package/package.json` and `package/sentinel.txt`; there are no lifecycle scripts or executable payloads.
The incompatible package declares Linux arm64; the matching package declares Linux x64.

The real loopback HTTP registry serves those manifests and tarballs to the CLI process.
The prefix, userconfig, globalconfig, cache, temporary directory and working directory are all task-private.
The child environment excludes inherited npm options and proxies; audit, funding and update-notifier requests are disabled.
The user's npm configuration and global installation are not changed.
The run refuses to overwrite an existing result directory.

## Actual sequence and observations

| Stage | Result |
| --- | --- |
| Install old fixture | Wrapper 1.0.0 and x64 alias 1.0.0-linux-x64 present |
| Advance only `latest` and upgrade | Wrapper 2.0.0 and x64 alias 2.0.0-linux-x64 present |
| Reinstall same latest version | Matching alias remains present |
| Delete only the fixture alias, then reinstall | Alias restored with correct package identity, version and sentinel |
| Uninstall control | Wrapper removed |
| Reinstall after uninstall | Wrapper and matching alias restored |
| Fresh prefix with warmed cache | Wrapper and matching alias installed correctly |

The six installed-state groups each record the wrapper version, alias existence, alias internal name, alias version, sentinel and absence of the incompatible alias.
The seventh group records uninstall removal.
All 11 CLI commands, including version and configuration checks, exit successfully; a separate Node version query confirms `v22.23.1`.
These are command and check-group counts, not 34 new assertions, 37 independent tests, or a coverage result.

The receipt records 16 fixture GET requests: 12 manifests and four wrapper/x64 tarballs.
There are no recorded unexpected routes, arm64 tarball downloads, or non-loopback npm HTTP-fetch log lines.
The HTTP-log observation is not a complete network-egress attestation.
Both final installation trees were independently inspected and match the recorded state.
Intermediate states are supported by the runner's captured checks and command logs; they were not replayed.

## Preserved setup failure and review

An initial setup attempt stopped before Node/npm execution because the extracted task-local Node binary had mode 0644 while its official archive member has mode 0755.
The archive's executable bit was restored on that task-owned file, and the failed setup receipt was retained separately.
It contains no completed npm commands and no disk checks; it is not an issue reproduction.
The subsequent diagnostic completed once without production-source changes.

An independent AI reviewer inspected the runner before execution, then verified the final source hash, all 22 command-output files, seven recorded groups, both final installation trees, six fixture tarballs and the setup-failure record.
The reviewer requested three narrow improvements before execution: reject arm64 tarball requests, require a successful old install before an upgrade, and retain partial output on timeout.
All three are present; the timeout branch was reviewed statically and was not exercised.
No human review is claimed.

The runner and execution receipt bind source SHA256 `56075593e3e79bd4879bb4768c7e009025c8f0f0b1f7a15a5845e0699cd70fe7`.
The saved receipt records elapsed command durations, but no absolute UTC start/end timestamps.
Execution occurred during the 31 October 2026 continuation; no exact timestamps are inferred from filesystem modification times.

## Limits and disposition

The reporter's exact older Codex installation, package bytes, effective configuration, pre-update installed tree and cache history remain unknown.
The synthetic package has inert sentinel contents; this is not a faithful reconstruction of that original installation.
The result neither disproves the report nor establishes current-version behavior.
There is presently no reproduced production defect to patch.
Another unchanged rerun is not warranted; further work needs a materially different failing condition or the missing original-state information.

## Evidence

- [Executed runner](cli-boundary-10173.py).
- [Runtime provenance](runtime-provenance.json).
- [Complete structured result](result.json).
- [Complete evidence bundle](evidence.tar.gz), SHA256 `df4e8da1e66cbb6974ce8fc47c5542684de7ffd5f9634bf9bf34411ba96aee94`: runner, provenance, result, command outputs, fixture tarballs/manifests, and setup-failure/repair records.
- [Per-file hashes and redaction record](manifest.json).

Only task-private absolute paths in textual records are replaced with `$DIAGNOSTIC_ROOT`.
The runner and fixture tarball bytes are preserved exactly.
The runtime cache and expanded third-party runtime trees are excluded; the official URLs and verified digests identify the inputs.

To repeat independently, place the official Node archive contents next to the runner as `node-v22.23.1-linux-x64`, extract the npm archive under `npm-11.18.0/package`, verify the listed checksums and executable mode, and run the script with Python 3 in a new directory.
The script will create its own isolated `run` directory.
