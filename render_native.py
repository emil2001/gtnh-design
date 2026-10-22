#!/usr/bin/env python3
"""Render a schematic through the user's authenticated local GTNH client."""
import argparse
import fcntl
import json
import re
import subprocess
import time
import uuid
from pathlib import Path
import worker
from settings import ROOT, STATE as HERE, RENDERS, load, bindings



def find_client():
    return worker.find_client(load()['source']/'.minecraft')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('schematic', type=Path)
    parser.add_argument('--id', default='render-' + uuid.uuid4().hex[:10])
    parser.add_argument('--width', type=int, default=1600)
    parser.add_argument('--height', type=int, default=1000)
    parser.add_argument('--interactive', action='store_true',help='Use the original visible Bridge Studio client')
    args = parser.parse_args()
    source = args.schematic.resolve(strict=True)
    if not source.is_relative_to(ROOT) or not source.is_file():
        parser.error('schematic must be a file in this workspace')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', args.id):
        parser.error('invalid job id')
    if not (128 <= args.width <= 4096 and 128 <= args.height <= 4096):
        parser.error('image dimensions must be 128..4096')
    # Hold admission through startup and rendering, after the queue file is consumed.
    HERE.mkdir(parents=True,exist_ok=True)
    lock=(HERE/('interactive-render.lock' if args.interactive else 'worker-render.lock')).open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:parser.error('renderer is busy; wait for the current job')
    output = RENDERS / args.id
    request=HERE/('request.json' if args.interactive else 'worker-request.json')
    service_file=HERE/('service.json' if args.interactive else 'worker-service.json')
    if output.exists() or request.exists():
        parser.error('job already exists or another job is queued')
    c=load();JAVA=c['java'];bindings(c)
    if not (HERE/'renderer-class.txt').is_file() or not (HERE/'background-agent.jar').is_file():
        import build_native
        build_native.main()
    deadline = time.monotonic() + 900
    pid = find_client() if args.interactive else worker.start(deadline)
    if pid is None:
        print('Starting the configured Prism instance...', flush=True)
        with (HERE / 'interactive-launcher.log').open('ab') as log:
            subprocess.Popen([str(c['prism_executable']),
                              '--dir', str(c['prism_data']), '--launch', c['source_instance'], '--show-window'],
                             stdout=log, stderr=log, start_new_session=True)
        while pid is None and time.monotonic() < deadline:
            time.sleep(2)
            pid = find_client()
        if pid is None:
            raise RuntimeError('Prism did not start Minecraft; check the launcher for authentication or launch errors')
    service = json.loads(service_file.read_text()) if service_file.exists() else {}
    implementation = (HERE/'renderer-class.txt').read_text().strip()
    if service.get('pid') != pid or service.get('implementation') != implementation:
        while time.monotonic()<deadline:
            attached = subprocess.run([str(JAVA), '-cp', str(HERE/'attach.jar'), 'agent.Attach', pid, str(HERE)],
                                      capture_output=True, text=True)
            if attached.returncode == 0:
                break
            error_file=HERE/('attach-error.txt' if args.interactive else 'worker-attach-error.txt')
            error = error_file.read_text() if error_file.exists() else attached.stderr
            if 'Minecraft has not initialized yet' not in error:
                raise RuntimeError(error)
            time.sleep(2)
        else:
            raise RuntimeError('Minecraft did not initialize in time for renderer attachment')
    job = dict(id=args.id, schematic=str(source), width=args.width, height=args.height)
    temporary = request.with_suffix('.tmp')
    temporary.write_text(json.dumps(job))
    temporary.replace(request)
    print('Submitted ' + args.id, flush=True)
    previous = None
    while time.monotonic() < deadline:
        report = output / 'result.json'
        if report.exists():
            result = json.loads(report.read_text())
            status = result.get('status')
            if status != previous:
                print(status, flush=True)
                previous = status
            if status == 'complete':
                for image in result['images']:
                    assert (output/image).is_file(), image
                print(output, flush=True)
                return
            if status == 'failed':
                raise RuntimeError(result.get('error', result))
        time.sleep(1)
    raise TimeoutError('Render did not finish; inspect the job result and the local Minecraft log')


if __name__ == '__main__':
    main()
