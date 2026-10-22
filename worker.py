"""Lifecycle for the isolated, hidden GTNH render instance."""
import configparser
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid

from settings import ROOT, STATE as HERE, load, bindings


def find_client(game):
    found=[]
    for pid in subprocess.run(['pgrep','-x','java'],capture_output=True,text=True).stdout.split():
        command=subprocess.run(['ps','-ww','-p',pid,'-o','comm='],capture_output=True,text=True).stdout.strip()
        if command!=str(load()['java']):continue
        cwd=subprocess.run(['lsof','-a','-p',pid,'-d','cwd','-Fn'],capture_output=True,text=True).stdout.splitlines()
        if 'n'+str(game) in cwd:found.append(pid)
    if len(found)>1:raise RuntimeError('Multiple Java processes use the selected game directory')
    return found[0] if found else None


def prepare():
    c=load();SOURCE=c['source'];INSTANCE=c['instance']
    bindings(c)
    if not (HERE/'background-agent.jar').is_file():raise RuntimeError('Run python build_native.py first')
    marker=INSTANCE/'renderer-instance.json'
    if marker.is_file():
        saved=json.loads(marker.read_text())
        if saved.get('source')!=str(SOURCE) or saved.get('toolkit')!=str(ROOT):
            raise RuntimeError('Worker belongs to another toolkit/source path; choose another worker_instance or recreate the disposable instance')
        return
    if INSTANCE.exists():raise RuntimeError('Worker instance exists without its setup marker')
    staging=INSTANCE.with_name(INSTANCE.name+'.setup')
    if staging.exists():raise RuntimeError('Incomplete worker setup exists: '+str(staging))
    staging.mkdir()
    game=staging/'.minecraft';game.mkdir()
    def clone(src,dst):
        # APFS clones isolate subsequent saves without duplicating the 3 GB world.
        subprocess.run(['cp','-cR',str(src),str(dst)],check=True,capture_output=True)
    try:
        for name in ['mmc-pack.json','patches','libraries']:clone(SOURCE/name,staging/name)
        for name in ['mods','coremods','scripts','resourcepacks','texturepacks','shaderpacks']:
            if (SOURCE/'.minecraft'/name).exists():(game/name).symlink_to(SOURCE/'.minecraft'/name,target_is_directory=True)
        clone(SOURCE/'.minecraft/config',game/'config')
        (game/'saves').mkdir()
        clone(SOURCE/'.minecraft/saves'/c['preview_world'],game/'saves'/c['preview_world'])
        options=(SOURCE/'.minecraft/options.txt').read_text().splitlines()
        overrides={'fullscreen':'false','enableVsync':'false','pauseOnLostFocus':'true',
                   'maxFps':'10','renderDistance':'2','soundCategory_master':'0.0'}
        options=[line for line in options if line.partition(':')[0] not in overrides]
        (game/'options.txt').write_text('\n'.join(options+[k+':'+v for k,v in overrides.items()])+'\n')
        cfg=game/'config/lwjgl3ify.cfg'
        text=cfg.read_text().replace('B:focused=true','B:focused=false').replace('B:showLoadingProgress=true','B:showLoadingProgress=false')
        cfg.write_text(text)
        config=configparser.RawConfigParser();config.optionxform=str
        config.read(SOURCE/'instance.cfg')
        if config.has_section('UI'):config.remove_section('UI')
        agent='-javaagent:'+str(HERE/'background-agent.jar')+'='+str(HERE)
        args='--add-exports=java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED '+json.dumps(agent)+' -Dapple.awt.UIElement=true'
        for key,value in {'name':'GTNH Design Renderer','uuid':uuid.uuid4().hex,'JavaPath':str(c['java']),'OverrideJavaLocation':'true',
                          'OverrideJavaArgs':'true','JvmArgs':json.dumps(args),'OverrideConsole':'true',
                          'ShowConsole':'false','AutoCloseConsole':'true','OverrideWindow':'true',
                          'MinecraftWinWidth':'854','MinecraftWinHeight':'480',
                          'JoinServerOnLaunch':'false','lastLaunchTime':'0','totalTimePlayed':'0'}.items():
            config.set('General',key,value)
        with (staging/'instance.cfg').open('w') as f:config.write(f,space_around_delimiters=False)
        (staging/'renderer-instance.json').write_text(json.dumps({'source':str(SOURCE),'toolkit':str(ROOT),'mode':'hidden SDL render worker'},indent=2))
        staging.rename(INSTANCE)
    except BaseException:
        shutil.rmtree(staging)
        raise


def start(deadline):
    c=load();MC=c['game'];INSTANCE=c['instance'];bindings(c)
    prepare()
    pid=find_client(MC)
    if pid:return pid
    print('Starting background GTNH renderer...',flush=True)
    with (HERE/'launcher.log').open('ab') as log:
        process=subprocess.Popen([str(c['prism_executable']),
                                  '--dir',str(c['prism_data']),'--launch',INSTANCE.name],
                                 stdout=log,stderr=log,start_new_session=True)
    while time.monotonic()<deadline:
        pid=find_client(MC)
        if pid:return pid
        if process.poll() not in (None,0):raise RuntimeError('Prism could not start the background renderer')
        time.sleep(2)
    raise TimeoutError('Background renderer did not start; check Prism authentication')


def status():
    MC=load()['game']
    pid=find_client(MC)
    path=HERE/'worker-service.json'
    service=json.loads(path.read_text()) if path.exists() else {}
    return {'running':pid is not None,'pid':pid,'service':service if service.get('pid')==pid else None}


def stop():
    MC=load()['game']
    pid=find_client(MC)
    if pid is None:return {'running':False}
    if (HERE/'worker-request.json').exists():raise RuntimeError('A render request is pending; wait before stopping')
    state=status()['service']
    if not state:raise RuntimeError('Worker render service is not attached; refusing to terminate it')
    temporary=HERE/'worker-stop.tmp'
    temporary.write_text(json.dumps({'pid':pid}));temporary.replace(HERE/'worker-stop.json')
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        if find_client(MC) is None:return {'running':False,'stopped_pid':pid}
        time.sleep(1)
    raise TimeoutError('Worker did not finish its normal shutdown')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['status','stop'])
    args=parser.parse_args()
    print(json.dumps(status() if args.command=='status' else stop(),indent=2))
