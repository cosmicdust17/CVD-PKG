"""Prepare an isolated copy of the pinned official Docker deployment."""
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor' / 'ragflow'
TAG = 'v1.0.0-rc2'

def main():
    if not VENDOR.exists():
        VENDOR.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'clone', '--depth', '1', '--branch', TAG,
                        'https://github.com/infiniflow/ragflow.git', str(VENDOR)], check=True)
    actual = subprocess.check_output(['git', '-C', str(VENDOR), 'describe', '--tags', '--exact-match'], text=True).strip()
    if actual != TAG:
        raise SystemExit(f'Expected {TAG}, found {actual}; existing checkout was not changed')
    runtime = ROOT / 'deployment' / 'runtime'
    if runtime.exists():
        raise SystemExit('runtime already exists; preserved. Use deployment/start.ps1 to resume.')
    shutil.copytree(VENDOR / 'docker', runtime)
    settings = {
        'RAGFLOW_IMAGE': f'infiniflow/ragflow:{TAG}', 'DOC_ENGINE': 'elasticsearch',
        'DEVICE': 'cpu', 'DB_TYPE': 'mysql', 'METADATA_DB_PROFILE': 'mysql',
        'MEM_LIMIT': '4294967296', 'ES_PORT': '19200', 'EXPOSE_MYSQL_PORT': '13306',
        'MINIO_PORT': '19000', 'MINIO_CONSOLE_PORT': '19001', 'KVROCKS_PORT': '16379',
        'EXPOSE_NATS_PORT': '14222', 'EXPOSE_NATS_MONITORING_PORT': '18222',
        'SVR_WEB_HTTP_PORT': '18080', 'SVR_WEB_HTTPS_PORT': '18443',
        'SVR_HTTP_PORT': '19380', 'ADMIN_SVR_HTTP_PORT': '19381',
        'THREAD_POOL_MAX_WORKERS': '8', 'WIKI_MAP_WORKERS': '2', 'WIKI_REFINE_WORKERS': '1',
    }
    env = (runtime / '.env').read_text(encoding='utf-8')
    for key, value in settings.items():
        env, count = re.subn(rf'^{key}=.*$', lambda m: f'{key}={value}', env, flags=re.M)
        if not count:
            env += f'\n{key}={value}\n'
    (runtime / '.env').write_text(env, encoding='utf-8')
    for name in ['docker-compose.yml', 'docker-compose-base.yml']:
        content = (runtime / name).read_text(encoding='utf-8')
        # Keep official service/volume definitions; bind all published ports locally.
        content = re.sub(r'(?m)^(\s+- )(["\']?)(\$\{[^}\n]+\}:\d+)(["\']?)\s*$',
                         lambda m: m[1] + '"127.0.0.1:' + m[3] + '"', content)
        content = content.replace('127.0.0.1:${VB_BIND_ADDR:-127.0.0.1}:', '${VB_BIND_ADDR:-127.0.0.1}:')
        if name == 'docker-compose-base.yml':
            content = content.replace('      - node.name=es01', '      - ES_JAVA_OPTS=-Xms1g -Xmx1g\n      - node.name=es01')
        else:
            content = content.replace('    image: ${RAGFLOW_IMAGE}', '    image: ${RAGFLOW_IMAGE}\n    mem_limit: 8g')
        (runtime / name).write_text(content, encoding='utf-8')
    commit = subprocess.check_output(['git', '-C', str(VENDOR), 'rev-parse', 'HEAD'], text=True).strip()
    (ROOT / 'deployment' / 'version-lock.json').write_text(json.dumps({
        'tag': TAG, 'commit': commit, 'image': settings['RAGFLOW_IMAGE'],
        'origin': 'https://github.com/infiniflow/ragflow', 'strategy': 'copy official docker directory; loopback ports and resource limits only',
    }, indent=2), encoding='utf-8')
    print(f'Prepared {runtime}')

if __name__ == '__main__':
    main()
