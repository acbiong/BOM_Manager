"""Authenticode signing with a certificate-store identity; no private keys in source."""
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlparse


@dataclass(frozen=True)
class SigningConfig:
    tool: str
    thumbprint: str
    timestamp_url: str
    machine_store: bool = False


def signing_config(env):
    """Resolve configuration before testing/building; never silently skip a request."""
    required = env.get('BOM_REQUIRE_SIGNED', '0')
    machine = env.get('BOM_SIGN_MACHINE_STORE', '0')
    if required not in ('0', '1') or machine not in ('0', '1'):
        raise ValueError('BOM_REQUIRE_SIGNED / BOM_SIGN_MACHINE_STORE must be 0 or 1')
    thumbprint = env.get('BOM_SIGN_CERT_SHA1', '').replace(' ', '').upper()
    if not thumbprint:
        if required == '1' or machine == '1' or any(env.get(key) for key in (
                'BOM_SIGNTOOL', 'BOM_SIGN_TIMESTAMP_URL')):
            raise ValueError('Signing requires BOM_SIGN_CERT_SHA1 from a trusted code-signing certificate')
        return None
    if not re.fullmatch(r'[0-9A-F]{40}', thumbprint):
        raise ValueError('BOM_SIGN_CERT_SHA1 must be a 40-character certificate thumbprint')
    timestamp = env.get('BOM_SIGN_TIMESTAMP_URL', '')
    url = urlparse(timestamp)
    if url.scheme not in ('http', 'https') or not url.netloc or url.username or url.password:
        raise ValueError('BOM_SIGN_TIMESTAMP_URL must specify the provider RFC3161 timestamp service')
    tool = env.get('BOM_SIGNTOOL') or shutil.which('signtool.exe', path=env.get('PATH'))
    if not tool:
        sdk = Path(env.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Windows Kits/10/bin'
        candidates = list(sdk.glob('*/x64/signtool.exe'))
        candidates.sort(key=lambda p: tuple(int(n) for n in p.parents[1].name.split('.') if n.isdigit()))
        if candidates:
            tool = str(candidates[-1])
    if not tool or not Path(tool).is_file():
        raise ValueError('Install Windows SDK SignTool or set BOM_SIGNTOOL to signtool.exe')
    return SigningConfig(str(tool), thumbprint, timestamp, machine == '1')


def sign_and_verify(exe, config, env):
    if config is None:
        print('UNSIGNED: no code-signing certificate configured; SmartScreen may warn.')
        return {'status': 'unsigned', 'reason': 'No code-signing certificate configured'}
    command = [config.tool, 'sign', '/s', 'My', '/sha1', config.thumbprint,
               '/fd', 'SHA256', '/tr', config.timestamp_url, '/td', 'SHA256',
               '/d', 'BOM管理系统', '/du', 'https://github.com/acbiong/BOM_Manager']
    if config.machine_store:
        command.append('/sm')
    subprocess.run(command + [str(exe)], check=True, env=env, timeout=180)
    # /pa validates the trusted Authenticode chain; /tw warns on missing timestamp.
    # SignTool warning/error exits both fail this build instead of publishing a hash.
    subprocess.run([config.tool, 'verify', '/pa', '/all', '/tw', str(exe)],
                   check=True, env=env, timeout=180)
    return {'status': 'verified', 'certificate_thumbprint': config.thumbprint,
            'store': 'LocalMachine/My' if config.machine_store else 'CurrentUser/My',
            'timestamp_url': config.timestamp_url,
            'smartscreen_warning_free': 'Not guaranteed by Authenticode verification'}


def write_version_resource(path, version):
    """Version properties help identify the binary; they do not establish trust."""
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Expected a three-part release version')
    parts = tuple(int(n) for n in version.split('.')) + (0,)
    if any(n > 65535 for n in parts):
        raise ValueError('Windows file version components must be <= 65535')
    strings = {'FileDescription': 'BOM管理系统', 'ProductName': 'BOM管理系统',
               'FileVersion': version, 'ProductVersion': version,
               'InternalName': 'BOM_Manager', 'OriginalFilename': 'BOM_Manager.exe'}
    entries = ','.join(f'StringStruct({key!r}, {value!r})' for key, value in strings.items())
    path.write_text(
        f"VSVersionInfo(ffi=FixedFileInfo(filevers={parts!r}, prodvers={parts!r}, "
        "mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0,0)), "
        f"kids=[StringFileInfo([StringTable('080404b0', [{entries}])]), "
        "VarFileInfo([VarStruct('Translation', [2052, 1200])])])", encoding='utf-8')
