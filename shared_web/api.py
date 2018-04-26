import json
import subprocess
from typing import Any, Dict, Union

from flask import Response, current_app, request

from shared import configuration
from shared.serialization import extra_serializer


def process_github_webhook() -> Response:
    if request.headers.get('X-GitHub-Event') == 'push':
        payload = json.loads(request.data)
        expected = 'refs/heads/{0}'.format(current_app.config['branch'])
        if payload['ref'] == expected:
            try:
                subprocess.check_output(['git', 'fetch'])
                subprocess.check_output(['git', 'reset', '--hard', 'origin/{0}'.format(current_app.config['branch'])])
                subprocess.check_output(['pip', 'install', '-U', '--user', '-r', 'requirements.txt', '--no-cache'])
                import uwsgi
                uwsgi.reload()
                return return_json({'rebooting': True})
            except ImportError:
                pass
    return return_json({
        'rebooting': False,
        'commit-id': current_app.config['commit-id'],
        'current_branch': current_app.config['branch'],
        'ref': payload['ref'],
        'expected': expected
        })

def validate_api_key() -> Response:
    if request.form.get('api_token', None) == configuration.get('pdbot_api_token'):
        return None
    return return_json(generate_error('UNAUTHORIZED', 'Invalid API key'), status=403)

def generate_error(code: str, msg: str) -> Dict[str, Any]:
    return {'error': True, 'code': code, 'msg': msg}

def return_json(content: Union[bool, Dict[str, Any]], status: int = 200) -> Response:
    s = json.dumps(content, default=extra_serializer)
    r = Response(response=s, status=status, mimetype='application/json')
    return r
