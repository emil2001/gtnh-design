"""Local paths; never store Prism accounts, tokens, worlds or modpacks in Git."""
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RUNTIME=ROOT/'runtime'
STATE=RUNTIME/'native'
RENDERS=RUNTIME/'renders'


def load():
    path=Path(os.environ.get('GTNH_DESIGN_CONFIG',ROOT/'config.local.json')).expanduser()
    if not path.is_file():raise RuntimeError('Copy config.example.json to config.local.json and set the local Prism/Java paths')
    raw=json.loads(path.read_text())
    result={key:Path(raw[key]).expanduser().resolve(strict=True)
            for key in ['prism_data','prism_executable','java_home']}
    for key,default in [('source_instance','GT New Horizons 2.9.0-RC-2'),
                        ('worker_instance','GTNH Design Renderer'),('preview_world','Bridge Studio')]:
        value=raw.get(key,default)
        if not isinstance(value,str) or not value or value in ('.','..') or '/' in value or '\\' in value:
            raise ValueError('Expected a single directory name: '+key)
        result[key]=value
    result['source']=result['prism_data']/'instances'/result['source_instance']
    result['instance']=result['prism_data']/'instances'/result['worker_instance']
    if result['source']==result['instance']:raise ValueError('Worker must have its own instance directory')
    result['game']=result['instance']/'.minecraft'
    result['java']=result['java_home']/'bin/java'
    if not result['java'].is_file():raise ValueError('java_home must contain bin/java')
    return result


def bindings(config):
    STATE.mkdir(parents=True,exist_ok=True)
    data={'worker_game':str(config['game']),'interactive_game':str(config['source']/'.minecraft'),
          'preview_world':config['preview_world']}
    (STATE/'bindings.json').write_text(json.dumps(data,indent=2))
