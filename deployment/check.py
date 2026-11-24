"""Capture actual project-scoped deployment state, health and image versions."""
import datetime
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def command(args):
    try:
        result = subprocess.run(args, capture_output=True, timeout=35)
        return {'exit_code': result.returncode, 'stdout': result.stdout.decode('utf-8', 'replace'),
                'stderr': result.stderr.decode('utf-8', 'replace')}
    except Exception as exc:
        return {'exit_code': None, 'error': str(exc)}

def http(url):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=8) as response:
            content = response.read(100000).decode('utf-8', 'replace')
            try:
                body = json.loads(content)
            except ValueError:
                body = content[:150]
            return {'url': url, 'status': response.status, 'body': body}
    except urllib.error.HTTPError as exc:
        return {'url': url, 'status': exc.code, 'body': exc.read(1000).decode('utf-8', 'replace')}
    except Exception as exc:
        return {'url': url, 'status': None, 'error': str(exc)}

def main():
    logs = ROOT / 'logs'
    logs.mkdir(exist_ok=True)
    compose = ['docker', 'compose', '-p', 'hfkg-ragflow', '-f', str(ROOT / 'deployment' / 'runtime' / 'docker-compose.yml')]
    report = {
        'checked_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        'docker': command(['docker', 'info', '--format', 'Server={{.ServerVersion}} Memory={{.MemTotal}} CPUs={{.NCPU}} Root={{.DockerRootDir}}']),
        'compose': command(compose + ['ps', '-a', '--format', 'json']),
        'http': [http(url) for url in (
            'http://127.0.0.1:18080/', 'http://127.0.0.1:19380/health',
            'http://127.0.0.1:19380/api/v1/system/healthz',
            'http://127.0.0.1:19380/api/v1/system/version',
            'http://127.0.0.1:19380/api/v1/compilation-templates/builtins',
        )],
        'model_extraction': {
            p.parent.name: json.loads(p.read_text(encoding='utf-8'))
            for p in (ROOT / 'output').glob('*/validation-report.json')
        },
    }
    (logs / 'deployment-status.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    result = command(compose + ['logs', '--no-color', '--tail', '100'])
    (logs / 'container-tail.log').write_text(result.get('stdout', '') + result.get('stderr', ''), encoding='utf-8')
    print(json.dumps({'http': [{'url': x['url'], 'status': x['status']} for x in report['http']],
                      'docker': report['docker'], 'report': str(logs / 'deployment-status.json')}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
