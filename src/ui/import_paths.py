"""BOM import paths, including native mounted SMB shares. No network writes."""
import os
import sys
import re
from pathlib import Path
from urllib.parse import urlsplit,unquote


def mounted_smb_roots():
    roots=[]
    if os.name=='nt':return roots
    def decode(value):return re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),value)
    try:
        for line in Path('/proc/mounts').read_text().splitlines():
            fields=line.split()
            if len(fields)>=3 and fields[2] in ('cifs','smb3'):
                roots.append((decode(fields[0]),Path(decode(fields[1]))))
    except OSError:pass
    gvfs=Path(os.environ.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'))/'gvfs'
    if gvfs.is_dir():
        for mount in gvfs.glob('smb-share:*'):
            parts=dict(item.split('=',1) for item in mount.name[len('smb-share:'):].split(',') if '=' in item)
            if parts.get('server') and parts.get('share'):roots.append(('//'+parts['server']+'/'+parts['share'],mount))
    return roots


def local_import_path(value):
    value=str(value)
    if value.lower().startswith('smb://'):
        url=urlsplit(value);parts=unquote(url.path).strip('/').split('/')
        if not url.hostname or not parts[0] or any(p in ('.','..') for p in parts):raise ValueError('SMB文件路径无效')
        if sys.platform=='win32':return Path('//'+url.hostname+'/'+ '/'.join(parts))
        share='//'+url.hostname+'/'+parts[0]
        for source,mount in mounted_smb_roots():
            if source.casefold()==share.casefold():
                candidate=mount.joinpath(*parts[1:])
                if candidate.exists():return candidate
        raise ValueError('共享目录尚未挂载或文件不存在，请先在文件管理器中打开该共享目录，再选择BOM文件。')
    if value.lower().startswith('file://'):
        url=urlsplit(value)
        if url.netloc not in ('','localhost'):raise ValueError('请使用本机挂载后的文件路径')
        value=unquote(url.path)
        if os.name=='nt' and re.match(r'^/[A-Za-z]:',value):value=value[1:]
    return Path(value).expanduser().resolve()


def bom_import_directory(config):
    stored=config.load()['database'].get('last_bom_import_dir','')
    if stored:
        try:
            folder=config.resolve_path(stored)
            if folder.is_dir():return str(folder)
        except (OSError,ValueError):pass
    desktop=Path.home()/'Desktop'
    return str(desktop if desktop.is_dir() else config.base)


def remember_bom_import(config,selected):
    path=local_import_path(selected)
    cfg=config.load();cfg['database']['last_bom_import_dir']=str(path.parent);config.save(cfg)
    return str(path)


def external_bom_selection(config):
    """Select the last external workbook, falling back to the OS desktop."""
    from PyQt5.QtCore import QStandardPaths
    stored=config.load()['database'].get('last_compare_bom_file','')
    if stored:
        try:
            path=config.resolve_path(stored)
            if path.is_file():return str(path)
        except (OSError,ValueError):pass
    return QStandardPaths.writableLocation(QStandardPaths.DesktopLocation) or str(Path.home()/'Desktop')


def remember_external_bom(config,selected):
    path=local_import_path(selected)
    cfg=config.load();cfg['database']['last_compare_bom_file']=str(path);config.save(cfg)
    return str(path)
