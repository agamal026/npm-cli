"""Bounded synthetic CLI-level diagnostic for npm/cli#10173.

Uses an isolated prefix/config/cache and inert same-package optional aliases.
This is not a reconstruction of the reporter's unknown prior installation.
"""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import unquote, urlsplit
import base64
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import time

ROOT = Path(__file__).resolve().parent
NODE = ROOT / 'node-v22.23.1-linux-x64/bin/node'
CLI = ROOT / 'npm-11.18.0/package/bin/npm-cli.js'
RUN = ROOT / 'run'
if RUN.exists():
    raise SystemExit('Refusing to overwrite an existing diagnostic run')
RUN.mkdir()
for name in ['cwd', 'cache', 'tmp', 'prefix', 'fresh', 'logs', 'tarballs']:
    (RUN / name).mkdir()

NAME = '@oss-test/cli'
MATCH = '@oss-test/cli-linux-x64'
OTHER = '@oss-test/cli-linux-arm64'
packages = {}
tarballs = {}
latest = '1.0.0'
requests = []
unexpected = []
stage = 'setup'

for version in ['1.0.0', '2.0.0']:
    for cpu in ['x64', 'arm64']:
        v = f'{version}-linux-{cpu}'
        packages[v] = {'name': NAME, 'version': v, 'os': ['linux'], 'cpu': [cpu]}
    packages[version] = {
        'name': NAME, 'version': version,
        'optionalDependencies': {
            MATCH: f'npm:{NAME}@{version}-linux-x64',
            OTHER: f'npm:{NAME}@{version}-linux-arm64',
        },
    }

for version, package in packages.items():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        for name, content in [
            ('package.json', json.dumps(package, separators=(',', ':')).encode()),
            ('sentinel.txt', version.encode()),
        ]:
            info = tarfile.TarInfo('package/' + name)
            info.size = len(content)
            info.mode = 0o644
            info.mtime = 0
            tar.addfile(info, io.BytesIO(content))
    payload = gzip.compress(buf.getvalue(), mtime=0)
    tarballs[version] = payload
    (RUN / 'tarballs' / f'{version}.tgz').write_bytes(payload)

class Registry(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        requests.append({'stage': stage, 'method': 'GET', 'path': path})
        if path == '/' + NAME:
            payload = json.dumps(manifest()).encode()
            content_type = 'application/json'
        elif path.startswith('/tarballs/') and path.endswith('.tgz'):
            version = path.removeprefix('/tarballs/').removesuffix('.tgz')
            if version not in tarballs:
                unexpected.append({'method': 'GET', 'path': path})
                self.send_error(404)
                return
            payload = tarballs[version]
            content_type = 'application/octet-stream'
        else:
            unexpected.append({'method': 'GET', 'path': path})
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        unexpected.append({'stage': stage, 'method': 'POST', 'path': self.path})
        self.send_error(404)

server = ThreadingHTTPServer(('127.0.0.1', 0), Registry)
registry = f'http://127.0.0.1:{server.server_port}/'

def manifest():
    versions = {}
    for version, package in packages.items():
        payload = tarballs[version]
        versions[version] = {
            **package, '_id': NAME + '@' + version,
            'dist': {
                'tarball': registry + f'tarballs/{version}.tgz',
                'shasum': hashlib.sha1(payload).hexdigest(),
                'integrity': 'sha512-' + base64.b64encode(hashlib.sha512(payload).digest()).decode(),
            },
        }
    return {'name': NAME, '_id': NAME, 'dist-tags': {'latest': latest}, 'versions': versions}

Thread(target=server.serve_forever, daemon=True).start()
(RUN / 'manifest-initial.json').write_text(json.dumps(manifest(), indent=2) + '\n')
userconfig = RUN / 'user.npmrc'
globalconfig = RUN / 'global.npmrc'
globalconfig.write_text('')
userconfig.write_text('\n'.join([
    f'registry={registry}', f'cache={RUN / "cache"}',
    'audit=false', 'fund=false', 'update-notifier=false',
    'fetch-retries=0', 'fetch-timeout=10000', 'progress=false', 'loglevel=http', '',
]))
# Explicit environment contains no inherited npm options, proxy, NODE_PATH, or
# NODE_OPTIONS. User/global config and all writable outputs are task-private.
# HOME is neither changed nor assigned.
env = {
    'PATH': str(NODE.parent) + ':/usr/bin:/bin',
    'TMPDIR': str(RUN / 'tmp'), 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TZ': 'UTC',
    'NPM_CONFIG_USERCONFIG': str(userconfig),
    'NPM_CONFIG_GLOBALCONFIG': str(globalconfig),
}
commands = []
checks = []

def run(label, args):
    global stage
    stage = label
    start = time.monotonic()
    try:
        result = subprocess.run([str(NODE), str(CLI), *args], cwd=RUN / 'cwd', env=env,
                                text=True, capture_output=True, timeout=45)
    except subprocess.TimeoutExpired as exc:
        def decoded(value):
            return value.decode(errors='replace') if isinstance(value, bytes) else (value or '')
        stdout, stderr = decoded(exc.stdout), decoded(exc.stderr)
        (RUN / 'logs' / (label + '.stdout')).write_text(stdout)
        (RUN / 'logs' / (label + '.stderr')).write_text(stderr)
        commands.append({'stage': label, 'arguments': args, 'exit_code': None, 'timed_out': True,
                         'seconds': round(time.monotonic() - start, 3), 'stdout': stdout, 'stderr': stderr})
        raise
    (RUN / 'logs' / (label + '.stdout')).write_text(result.stdout)
    (RUN / 'logs' / (label + '.stderr')).write_text(result.stderr)
    commands.append({'stage': label, 'arguments': args, 'exit_code': result.returncode,
                     'seconds': round(time.monotonic() - start, 3),
                     'stdout': result.stdout, 'stderr': result.stderr})
    return result

def check(label, prefix, version):
    wrapper = prefix / 'lib/node_modules' / NAME
    alias = wrapper / 'node_modules' / MATCH
    def read_package(path):
        try:
            return json.loads((path / 'package.json').read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    wp = read_package(wrapper)
    ap = read_package(alias)
    sentinel = (alias / 'sentinel.txt').read_text() if (alias / 'sentinel.txt').exists() else None
    observed = {'wrapper_version': wp.get('version'), 'alias_exists': (alias / 'package.json').exists(),
                'alias_name': ap.get('name'), 'alias_version': ap.get('version'),
                'alias_sentinel': sentinel, 'incompatible_alias_exists': (wrapper / 'node_modules' / OTHER).exists()}
    expected = {'wrapper_version': version, 'alias_exists': True, 'alias_name': NAME,
                'alias_version': version + '-linux-x64', 'alias_sentinel': version + '-linux-x64',
                'incompatible_alias_exists': False}
    checks.append({'stage': label, 'expected': expected, 'observed': observed, 'passed': observed == expected})
    print(json.dumps({'stage': label, 'exit_code': commands[-1]['exit_code'], **observed,
                      'passed': observed == expected}), flush=True)

error = None
try:
    node_version = subprocess.check_output([str(NODE), '--version'], text=True, env=env).strip()
    assert node_version == 'v22.23.1', node_version
    assert run('npm-version', ['--version']).stdout.strip() == '11.18.0'
    assert run('configure-prefix', ['config', 'set', 'prefix', str(RUN / 'prefix'), '--location=user']).returncode == 0
    assert run('verify-prefix', ['config', 'get', 'prefix']).stdout.strip() == str(RUN / 'prefix')
    install = ['install', '-g', NAME + '@latest']
    old_result = run('old-install', install)
    check('old-install', RUN / 'prefix', '1.0.0')
    assert old_result.returncode == 0 and checks[-1]['passed'], 'Old-install prerequisite failed; no upgrade was attempted'
    latest = '2.0.0'
    (RUN / 'manifest-upgrade.json').write_text(json.dumps(manifest(), indent=2) + '\n')
    run('upgrade', install)
    check('upgrade', RUN / 'prefix', '2.0.0')
    run('same-version-reinstall', install)
    check('same-version-reinstall', RUN / 'prefix', '2.0.0')
    missing = RUN / 'prefix/lib/node_modules' / NAME / 'node_modules' / MATCH
    if missing.exists():
        shutil.rmtree(missing)
    run('repair-missing-alias', install)
    check('repair-missing-alias', RUN / 'prefix', '2.0.0')
    run('uninstall-control', ['uninstall', '-g', NAME])
    removed = not (RUN / 'prefix/lib/node_modules' / NAME).exists()
    checks.append({'stage': 'uninstall-control', 'wrapper_removed': removed, 'passed': removed})
    run('uninstall-reinstall-control', install)
    check('uninstall-reinstall-control', RUN / 'prefix', '2.0.0')
    assert run('configure-fresh-prefix', ['config', 'set', 'prefix', str(RUN / 'fresh'), '--location=user']).returncode == 0
    run('fresh-warm-cache-control', install)
    check('fresh-warm-cache-control', RUN / 'fresh', '2.0.0')
except Exception as exc:
    error = type(exc).__name__ + ': ' + str(exc)
finally:
    server.shutdown()
    server.server_close()
    all_logs = '\n'.join(c['stderr'] for c in commands)
    http_lines = [line for line in all_logs.splitlines() if 'npm http fetch ' in line]
    non_loopback = [line for line in http_lines if 'http://127.0.0.1:' not in line]
    incompatible_requests = [r for r in requests if r['path'].endswith('-linux-arm64.tgz')]
    result = {
        'issue': 'https://github.com/npm/cli/issues/10173',
        'diagnostic': 'Synthetic published-CLI/configuration/runtime comparison; not exact reporter state',
        'node_version': locals().get('node_version'), 'npm_version': '11.18.0', 'arborist_version': '9.9.0',
        'registry': registry, 'fixture_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'tarball_sha256': {v: hashlib.sha256(b).hexdigest() for v, b in tarballs.items()},
        'commands': commands, 'disk_checks': checks, 'requests': requests,
        'unexpected_routes': unexpected, 'non_loopback_fetch_log_lines': non_loopback,
        'incompatible_platform_tarball_requests': incompatible_requests,
        'error': error,
        'all_checks_passed': (error is None and bool(checks) and all(c['passed'] for c in checks)
                              and all(c['exit_code'] == 0 for c in commands)
                              and not unexpected and not non_loopback and not incompatible_requests),
    }
    (RUN / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ['error', 'all_checks_passed', 'unexpected_routes', 'non_loopback_fetch_log_lines']}), flush=True)
if not result['all_checks_passed']:
    raise SystemExit(1)
