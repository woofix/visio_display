# MIT License - Copyright (c) 2026 Woofix
# See LICENSE file for details

import shlex
import shutil
import subprocess
import time
from pathlib import Path


INSTALL_SCRIPT = Path(__file__).resolve().parents[1] / 'install.sh'


def _run_command(cmd):
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )


def _join_output(*chunks):
    merged = []
    for chunk in chunks:
        if chunk:
            merged.append(chunk.strip())
    return '\n\n'.join(merged).strip()


def _contains_any(text, needles):
    haystack = (text or '').casefold()
    return any(needle.casefold() in haystack for needle in needles)


def _supports_password_mode():
    return shutil.which('sshpass') is not None


def build_manual_install_commands(host, port, ssh_user, kiosk_user, server_url='',
                                  screen_name='', machine_name=''):
    target = f'{ssh_user}@{host}'
    remote_script = '/tmp/visio-install.sh'
    extra_args = []
    if server_url:
        extra_args.append(f"--server-url {shlex.quote(server_url)}")
    if screen_name:
        extra_args.append(f"--screen-name {shlex.quote(screen_name)}")
    if machine_name:
        extra_args.append(f"--machine-name {shlex.quote(machine_name)}")
    extra_args_str = f" {' '.join(extra_args)}" if extra_args else ''
    copy_cmd = (
        f"scp -P {port} {shlex.quote(str(INSTALL_SCRIPT))} "
        f"{shlex.quote(target + ':' + remote_script)}"
    )
    run_cmd = (
        f"ssh -tt -p {port} {shlex.quote(target)} "
        f"\"chmod +x {remote_script} && bash {remote_script} "
        f"--user {shlex.quote(kiosk_user)}{extra_args_str}\""
    )
    return [copy_cmd, run_cmd]


def build_manual_power_commands(host, port, ssh_user, action):
    target = f'{ssh_user}@{host}'
    remote_cmd = 'sudo shutdown -h now' if action == 'shutdown' else 'sudo shutdown -r now'
    run_cmd = (
        f"ssh -tt -p {port} {shlex.quote(target)} "
        f"\"{remote_cmd}\""
    )
    return [run_cmd]


def build_manual_update_commands(host, port, ssh_user, kiosk_user):
    target = f'{ssh_user}@{host}'
    remote_script = '/tmp/visio-install.sh'
    copy_cmd = (
        f"scp -P {port} {shlex.quote(str(INSTALL_SCRIPT))} "
        f"{shlex.quote(target + ':' + remote_script)}"
    )
    run_cmd = (
        f"ssh -tt -p {port} {shlex.quote(target)} "
        f"\"chmod +x {remote_script} && bash {remote_script} "
        f"--user {shlex.quote(kiosk_user)}\""
    )
    return [copy_cmd, run_cmd]


def build_manual_os_update_commands(host, port, ssh_user):
    target = f'{ssh_user}@{host}'
    remote_cmd = (
        "sudo apt-get update && "
        "sudo DEBIAN_FRONTEND=noninteractive apt-get -y upgrade && "
        "sudo DEBIAN_FRONTEND=noninteractive apt-get -y autoremove --purge && "
        "sudo apt-get autoclean && "
        "if [ -f /run/reboot-required ] || [ -f /var/run/reboot-required ]; then "
        "sudo nohup sh -c 'sleep 2; systemctl reboot || shutdown -r now || reboot' >/dev/null 2>&1 </dev/null & "
        "&& echo reboot-scheduled; fi"
    )
    run_cmd = (
        f"ssh -tt -p {port} {shlex.quote(target)} "
        f"\"{remote_cmd}\""
    )
    return [run_cmd]


def _build_remote_elevated_command(base_cmd, elevation_pw_q):
    return (
        f"if [ \"$(id -u)\" -eq 0 ]; then "
        f"{base_cmd}; "
        f"elif command -v sudo >/dev/null 2>&1; then "
        f"printf '%s\\n' {elevation_pw_q} | sudo -S -p '' {base_cmd}; "
        f"else "
        f"printf '%s\\n' {elevation_pw_q} | su -c {shlex.quote(base_cmd)}; "
        f"fi"
    )


def deploy_client_install(host, port, ssh_user, kiosk_user, server_url='',
                          screen_name='', machine_name='', ssh_password='',
                          sudo_password=''):
    missing = [tool for tool in ('ssh', 'scp') if shutil.which(tool) is None]
    if missing:
        return {
            'ok': False,
            'summary_key': 'install_summary_missing_tools',
            'output': "Commandes manquantes : " + ', '.join(missing),
        }
    if not _supports_password_mode():
        return {
            'ok': False,
            'summary_key': 'install_summary_missing_sshpass',
            'output': "Commande manquante : sshpass",
        }

    if not INSTALL_SCRIPT.exists():
        return {
            'ok': False,
            'summary_key': 'install_summary_missing_script',
            'output': str(INSTALL_SCRIPT),
        }

    target = f'{ssh_user}@{host}'
    remote_script = f"/tmp/visio-install-{int(time.time())}.sh"
    script_q = shlex.quote(remote_script)
    user_q = shlex.quote(kiosk_user)
    server_url_q = shlex.quote(server_url)
    screen_name_q = shlex.quote(screen_name)
    machine_name_q = shlex.quote(machine_name)
    elevation_pw = sudo_password if sudo_password else ssh_password
    elevation_pw_q = shlex.quote(elevation_pw)
    extra_args = [f"--server-url {server_url_q}"]
    if screen_name:
        extra_args.append(f"--screen-name {screen_name_q}")
    if machine_name:
        extra_args.append(f"--machine-name {machine_name_q}")
    base_cmd = f"bash {script_q} --user {user_q} {' '.join(extra_args)}"
    remote_cmd = f"chmod +x {script_q} && {_build_remote_elevated_command(base_cmd, elevation_pw_q)}"

    scp_cmd = [
        'sshpass',
        '-p', ssh_password,
        'scp',
        '-P', str(port),
        '-o', 'BatchMode=no',
        '-o', 'StrictHostKeyChecking=accept-new',
        str(INSTALL_SCRIPT),
        f'{target}:{remote_script}',
    ]
    copy_res = _run_command(scp_cmd)
    if copy_res.returncode != 0:
        return {
            'ok': False,
            'summary_key': 'install_summary_copy_failed',
            'output': _join_output(copy_res.stdout, copy_res.stderr),
            'commands': build_manual_install_commands(
                host, port, ssh_user, kiosk_user, server_url, screen_name, machine_name
            ),
        }

    ssh_cmd = [
        'sshpass',
        '-p', ssh_password,
        'ssh',
        '-tt',
        '-p', str(port),
        '-o', 'BatchMode=no',
        '-o', 'StrictHostKeyChecking=accept-new',
        target,
        remote_cmd,
    ]
    run_res = _run_command(ssh_cmd)
    output = _join_output(run_res.stdout, run_res.stderr)
    install_finished = "Installation terminée." in output
    remote_reboot_disconnect = _contains_any(output, (
        'connection to ',
        'closed by remote host',
        'broken pipe',
        'connection reset',
    ))
    ok = install_finished and (run_res.returncode == 0 or remote_reboot_disconnect)

    return {
        'ok': ok,
        'summary_key': (
            'install_summary_success'
            if ok else
            'install_summary_run_failed'
        ),
        'output': output or '(aucune sortie)',
        'commands': build_manual_install_commands(
            host, port, ssh_user, kiosk_user, server_url, screen_name, machine_name
        ),
    }


def deploy_client_power_action(host, port, ssh_user, action, ssh_password='', sudo_password=''):
    missing = [tool for tool in ('ssh',) if shutil.which(tool) is None]
    if missing:
        return {
            'ok': False,
            'summary_key': 'install_summary_missing_tools',
            'output': "Commandes manquantes : " + ', '.join(missing),
        }
    if not _supports_password_mode():
        return {
            'ok': False,
            'summary_key': 'install_summary_missing_sshpass',
            'output': "Commande manquante : sshpass",
        }

    action = 'shutdown' if action == 'shutdown' else 'restart'
    target = f'{ssh_user}@{host}'
    elevation_pw = sudo_password if sudo_password else ssh_password
    elevation_pw_q = shlex.quote(elevation_pw)

    delayed_action = (
        "nohup sh -c 'sleep 1; systemctl poweroff || shutdown -h now || poweroff' "
        ">/dev/null 2>&1 </dev/null &"
        if action == 'shutdown' else
        "nohup sh -c 'sleep 1; systemctl reboot || shutdown -r now || reboot' "
        ">/dev/null 2>&1 </dev/null &"
    )
    marker = '__VISIO_CLIENT_POWER_SENT__'
    base_cmd = f"sh -lc {shlex.quote(f'echo {marker}; {delayed_action}')}"
    remote_cmd = (
        f"{_build_remote_elevated_command(base_cmd, elevation_pw_q)}"
    )

    ssh_cmd = [
        'sshpass',
        '-p', ssh_password,
        'ssh',
        '-tt',
        '-p', str(port),
        '-o', 'BatchMode=no',
        '-o', 'StrictHostKeyChecking=accept-new',
        target,
        remote_cmd,
    ]
    run_res = _run_command(ssh_cmd)
    output = _join_output(run_res.stdout, run_res.stderr)
    remote_disconnect = _contains_any(output, (
        'connection to ',
        'closed by remote host',
        'broken pipe',
        'connection reset',
    ))
    ok = marker in output and (run_res.returncode == 0 or remote_disconnect)

    summary_key = (
        'client_control_summary_shutdown_success'
        if action == 'shutdown' else
        'client_control_summary_restart_success'
    ) if ok else (
        'client_control_summary_shutdown_failed'
        if action == 'shutdown' else
        'client_control_summary_restart_failed'
    )

    return {
        'ok': ok,
        'summary_key': summary_key,
        'output': output or '(aucune sortie)',
        'commands': build_manual_power_commands(host, port, ssh_user, action),
    }


def deploy_client_update(host, port, ssh_user, ssh_password='', sudo_password=''):
    missing = [tool for tool in ('ssh', 'scp') if shutil.which(tool) is None]
    if missing:
        return {
            'ok': False,
            'summary_key': 'install_summary_missing_tools',
            'output': "Commandes manquantes : " + ', '.join(missing),
        }
    if not _supports_password_mode():
        return {
            'ok': False,
            'summary_key': 'install_summary_missing_sshpass',
            'output': "Commande manquante : sshpass",
        }
    if not INSTALL_SCRIPT.exists():
        return {
            'ok': False,
            'summary_key': 'install_summary_missing_script',
            'output': str(INSTALL_SCRIPT),
        }

    target = f'{ssh_user}@{host}'
    elevation_pw = sudo_password if sudo_password else ssh_password
    elevation_pw_q = shlex.quote(elevation_pw)

    user_marker = '__VISIO_KIOSK_USER__'
    detect_user_base_cmd = "sh -lc " + shlex.quote(
        "user=$(sed -n 's/.*--autologin[[:space:]]\\([^[:space:]]\\+\\).*/\\1/p' "
        "/etc/systemd/system/getty@tty1.service.d/override.conf | head -n1); "
        f"printf '{user_marker}%s\\n' \"$user\""
    )
    detect_user_cmd = _build_remote_elevated_command(detect_user_base_cmd, elevation_pw_q)
    detect_cmd = [
        'sshpass',
        '-p', ssh_password,
        'ssh',
        '-tt',
        '-p', str(port),
        '-o', 'BatchMode=no',
        '-o', 'StrictHostKeyChecking=accept-new',
        target,
        detect_user_cmd,
    ]
    detect_res = _run_command(detect_cmd)
    detect_output = _join_output(detect_res.stdout, detect_res.stderr)
    kiosk_user = ''
    for line in detect_output.splitlines():
        if user_marker in line:
            kiosk_user = line.split(user_marker, 1)[1].strip()
            break
    if detect_res.returncode != 0 or not kiosk_user:
        return {
            'ok': False,
            'summary_key': 'client_control_summary_update_failed',
            'output': detect_output or 'Impossible de détecter l’utilisateur kiosk existant.',
        }

    remote_script = f"/tmp/visio-install-{int(time.time())}.sh"
    script_q = shlex.quote(remote_script)
    user_q = shlex.quote(kiosk_user)
    base_cmd = f"bash {script_q} --user {user_q}"
    remote_cmd = f"chmod +x {script_q} && {_build_remote_elevated_command(base_cmd, elevation_pw_q)}"

    scp_cmd = [
        'sshpass',
        '-p', ssh_password,
        'scp',
        '-P', str(port),
        '-o', 'BatchMode=no',
        '-o', 'StrictHostKeyChecking=accept-new',
        str(INSTALL_SCRIPT),
        f'{target}:{remote_script}',
    ]
    copy_res = _run_command(scp_cmd)
    if copy_res.returncode != 0:
        return {
            'ok': False,
            'summary_key': 'install_summary_copy_failed',
            'output': _join_output(copy_res.stdout, copy_res.stderr),
            'commands': build_manual_update_commands(host, port, ssh_user, kiosk_user),
        }

    ssh_cmd = [
        'sshpass',
        '-p', ssh_password,
        'ssh',
        '-tt',
        '-p', str(port),
        '-o', 'BatchMode=no',
        '-o', 'StrictHostKeyChecking=accept-new',
        target,
        remote_cmd,
    ]
    run_res = _run_command(ssh_cmd)
    output = _join_output(run_res.stdout, run_res.stderr)
    install_finished = "Installation terminée." in output
    remote_reboot_disconnect = _contains_any(output, (
        'connection to ',
        'closed by remote host',
        'broken pipe',
        'connection reset',
    ))
    ok = install_finished and (run_res.returncode == 0 or remote_reboot_disconnect)

    return {
        'ok': ok,
        'summary_key': (
            'client_control_summary_update_success'
            if ok else
            'client_control_summary_update_failed'
        ),
        'output': output or '(aucune sortie)',
        'commands': build_manual_update_commands(host, port, ssh_user, kiosk_user),
    }


def deploy_client_os_update(host, port, ssh_user, ssh_password='', sudo_password=''):
    missing = [tool for tool in ('ssh',) if shutil.which(tool) is None]
    if missing:
        return {
            'ok': False,
            'summary_key': 'install_summary_missing_tools',
            'output': "Commandes manquantes : " + ', '.join(missing),
        }
    if not _supports_password_mode():
        return {
            'ok': False,
            'summary_key': 'install_summary_missing_sshpass',
            'output': "Commande manquante : sshpass",
        }

    target = f'{ssh_user}@{host}'
    elevation_pw = sudo_password if sudo_password else ssh_password
    elevation_pw_q = shlex.quote(elevation_pw)
    marker = '__VISIO_OS_UPDATE_DONE__'
    reboot_marker = '__VISIO_OS_REBOOT_SCHEDULED__'
    base_cmd = "sh -lc " + shlex.quote(
        "apt-get update && "
        "DEBIAN_FRONTEND=noninteractive apt-get -y upgrade && "
        "DEBIAN_FRONTEND=noninteractive apt-get -y autoremove --purge && "
        "apt-get autoclean && "
        f"if [ -f /run/reboot-required ] || [ -f /var/run/reboot-required ]; then echo {reboot_marker}; "
        "nohup sh -c 'sleep 2; systemctl reboot || shutdown -r now || reboot' >/dev/null 2>&1 </dev/null &; "
        f"fi && echo {marker}"
    )
    remote_cmd = _build_remote_elevated_command(base_cmd, elevation_pw_q)

    ssh_cmd = [
        'sshpass',
        '-p', ssh_password,
        'ssh',
        '-tt',
        '-p', str(port),
        '-o', 'BatchMode=no',
        '-o', 'StrictHostKeyChecking=accept-new',
        target,
        remote_cmd,
    ]
    run_res = _run_command(ssh_cmd)
    output = _join_output(run_res.stdout, run_res.stderr)
    remote_disconnect = _contains_any(output, (
        'connection to ',
        'closed by remote host',
        'broken pipe',
        'connection reset',
    ))
    ok = marker in output and (run_res.returncode == 0 or remote_disconnect)
    reboot_scheduled = reboot_marker in output

    return {
        'ok': ok,
        'summary_key': (
            'client_control_summary_os_update_reboot_success'
            if ok and reboot_scheduled else
            'client_control_summary_os_update_success'
            if ok else
            'client_control_summary_os_update_failed'
        ),
        'output': output or '(aucune sortie)',
        'commands': build_manual_os_update_commands(host, port, ssh_user),
    }
