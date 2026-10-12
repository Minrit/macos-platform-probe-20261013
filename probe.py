import hashlib
import json
import os
import pathlib
import platform
import plistlib
import shutil
import subprocess
import time
import traceback
import urllib.request

out = pathlib.Path('evidence').resolve()
out.mkdir(exist_ok=True)
work = pathlib.Path(os.environ['RUNNER_TEMP']) / 'horizyn-0135-probe'
work.mkdir(exist_ok=True)
report = {'release': '0.1.35', 'platform': platform.platform(), 'machine': platform.machine(), 'commands': []}
gui = None
gui_log = None
mount = work / 'mount'

def run(args, name, timeout=45):
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        content = proc.stdout.decode('utf-8', errors='replace')
        (out / (name + '.txt')).write_text(content, encoding='utf-8')
        report['commands'].append({'name': name, 'returncode': proc.returncode})
        print(name, 'exit', proc.returncode, content[:700], flush=True)
        return proc.returncode, content
    except subprocess.TimeoutExpired as exc:
        content = (exc.stdout or b'').decode('utf-8', errors='replace')
        (out / (name + '.txt')).write_text(content + '\nTIMEOUT\n', encoding='utf-8')
        report['commands'].append({'name': name, 'timeout': True})
        return 124, content

try:
    run(['sw_vers'], 'os')
    run(['system_profiler', 'SPHardwareDataType', 'SPDisplaysDataType'], 'hardware', 30)
    assert platform.machine() == 'arm64', 'This release requires arm64'
    code, _ = run(['swiftc', 'desktop.swift', '-o', str(work / 'desktop')], 'compile-desktop', 90)
    if code == 0:
        run([str(work / 'desktop')], 'desktop-before')
    archive = work / 'Horizyn-0.1.35-arm64.dmg'
    url = 'https://github.com/visual-z/horizyn-releases/releases/download/v0.1.35/Horizyn-0.1.35-arm64.dmg'
    urllib.request.urlretrieve(url, archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    report['archive_sha256'] = digest
    assert digest == '3537e9b653f0ea64d34e5c4b8e7add1edaad6aaccb928e8454018307a85e5af2'
    mount.mkdir(exist_ok=True)
    code, _ = run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', str(mount), str(archive)], 'mount')
    assert code == 0, 'Could not mount DMG'
    app = work / 'Horizyn.app'
    run(['ditto', str(mount / 'Horizyn.app'), str(app)], 'copy-app')
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    report['version'] = info.get('CFBundleShortVersionString')
    report['build'] = info.get('CFBundleVersion')
    assert report['version'] == '0.1.35'
    code, _ = run(['codesign', '--verify', '--deep', '--strict', '--verbose=2', str(app)], 'signature')
    assert code == 0, 'Code signature validation failed'
    executable = app / 'Contents/MacOS/horizyn'
    code, help_text = run([str(executable), '--help'], 'actual-help', 20)
    report['help_returncode'] = code
    args = [str(executable)]
    if '--fresh-start' in help_text:
        args.append('--fresh-start')
    fixture = work / 'sample-project'
    fixture.mkdir(exist_ok=True)
    (fixture / 'README.md').write_text('# Runtime observation fixture\n', encoding='utf-8')
    gui_log = (out / 'gui-process.log').open('wb')
    gui = subprocess.Popen(args, cwd=fixture, stdout=gui_log, stderr=subprocess.STDOUT)
    report['gui_pid'] = gui.pid
    report['gui_arguments'] = args[1:]
    print('Started original GUI PID', gui.pid, flush=True)
    time.sleep(12)
    report['gui_exit_after_12s'] = gui.poll()
    if (work / 'desktop').exists():
        _, desktop = run([str(work / 'desktop')], 'desktop-after')
        try:
            state = json.loads(desktop)
            report['metalDevices'] = state['metalDevices']
            app_windows = [w for w in state['windows'] if w.get('kCGWindowOwnerPID') == gui.pid]
            report['app_window_count'] = len(app_windows)
            for index, window in enumerate(app_windows[:3]):
                run(['screencapture', '-x', '-l', str(window['kCGWindowNumber']), str(out / f'horizyn-window-{index}.png')], f'capture-window-{index}', 15)
        except Exception as exc:
            report['desktop_parse_error'] = str(exc)
    run(['screencapture', '-x', str(out / 'desktop.png')], 'capture-desktop', 15)
    run(['ps', '-axo', 'pid,ppid,comm'], 'processes')
    run(['log', 'show', '--last', '2m', '--style', 'compact', '--predicate', 'process == "horizyn" OR process == "horizynd"'], 'unified-log', 30)
    crashes = pathlib.Path.home() / 'Library/Logs/DiagnosticReports'
    if crashes.exists():
        for path in crashes.glob('horizyn*'):
            if path.is_file() and path.stat().st_size < 2_000_000:
                shutil.copy2(path, out / path.name)
except Exception as exc:
    report['error'] = str(exc)
    (out / 'exception.txt').write_text(traceback.format_exc(), encoding='utf-8')
    print(traceback.format_exc(), flush=True)
finally:
    if gui and gui.poll() is None:
        gui.terminate()
        try:
            gui.wait(timeout=5)
        except subprocess.TimeoutExpired:
            gui.kill()
            gui.wait(timeout=5)
    if gui_log:
        gui_log.close()
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)
