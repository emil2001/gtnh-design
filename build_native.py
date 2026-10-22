"""Build the native renderer and startup-agent from source against your GTNH libraries."""
from pathlib import Path
import subprocess,os,hashlib,shutil
from settings import ROOT,STATE,load,bindings

def main():
    c=load();bindings(c)
    JAVA=c['java_home']/'bin';SOURCE=ROOT/'java';OUT=STATE;BUILD=OUT/'classes'
    BUILD.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    generated = OUT/'generated'
    generated.mkdir(exist_ok=True)
    renderer_source = (SOURCE/'NativeRenderer.java').read_text()
    version = 'v' + hashlib.sha256(renderer_source.encode()).hexdigest()[:12]
    renderer_source = renderer_source.replace('package gtnh.preview;', f'package gtnh.preview.{version};')
    (generated/'NativeRenderer.java').write_text(renderer_source)
    (OUT/'renderer-class.txt').write_text(f'gtnh.preview.{version}.NativeRenderer')
    agent_source = (SOURCE/'RenderAgent.java').read_text()
    agent_name = 'RenderAgent' + hashlib.sha256(agent_source.encode()).hexdigest()[:12]
    (generated/(agent_name+'.java')).write_text(agent_source.replace('class RenderAgent', 'class '+agent_name))
    if (BUILD/'gtnh').exists(): shutil.rmtree(BUILD/'gtnh')
    libraries = list((c['prism_data']/'libraries').rglob('*.jar'))
    classpath = os.pathsep.join(map(str, libraries))
    compilation = subprocess.run([str(JAVA/'javac'), '--release', '8', '-Xlint:-options', '-cp', classpath, '-d', str(BUILD),
                    str(generated/(agent_name+'.java')), str(generated/'NativeRenderer.java')])
    if compilation.returncode: raise SystemExit(compilation.returncode)
    subprocess.run([str(JAVA/'javac'), '-d', str(BUILD), str(SOURCE/'Attach.java')], check=True)
    manifest = OUT/'agent-manifest.mf'
    manifest.write_text(f'Manifest-Version: 1.0\nAgent-Class: agent.{agent_name}\n\n')
    agent_file = agent_name+'.jar'
    renderer_file = 'renderer-'+version+'.jar'
    subprocess.run([str(JAVA/'jar'), 'cfm', str(OUT/agent_file), str(manifest), '-C', str(BUILD), 'agent/'+agent_name+'.class'], check=True)
    subprocess.run([str(JAVA/'jar'), 'cf', str(OUT/renderer_file), '-C', str(BUILD), 'gtnh'], check=True)
    (OUT/'agent-file.txt').write_text(agent_file)
    (OUT/'renderer-file.txt').write_text(renderer_file)
    subprocess.run([str(JAVA/'jar'), 'cf', str(OUT/'attach.jar'), '-C', str(BUILD), 'agent/Attach.class'], check=True)
    subprocess.run([str(JAVA/'javac'), '--add-exports', 'java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED',
                    '-d', str(BUILD), str(SOURCE/'BackgroundAgent.java')], check=True)
    background_manifest=OUT/'background-manifest.mf'
    background_manifest.write_text('Manifest-Version: 1.0\nPremain-Class: agent.BackgroundAgent\n\n')
    background_classes=sorted((BUILD/'agent').glob('BackgroundAgent*.class'))
    subprocess.run([str(JAVA/'jar'), 'cfm', str(OUT/'background-agent.jar'), str(background_manifest),
                    *[part for p in background_classes for part in ['-C',str(BUILD),str(p.relative_to(BUILD))]]],check=True)
    print('Built native render service')

if __name__=='__main__':main()
