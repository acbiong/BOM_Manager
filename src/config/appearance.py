"""Portable appearance preferences, independent of the active project."""
import json
from services.bom_colors import normalize

DEFAULT_FONT_SIZE=10
# Five levels including the root; deeper descendants use the fifth color.
DEFAULT_EXPORT_COLORS=['#e2e8f0','#edf1f5','#f3f5f8','#f8fafc','']


def load(config):
    cfg=config.load() if config else None
    try:size=int(cfg.get('ui','font_size',fallback=str(DEFAULT_FONT_SIZE))) if cfg else DEFAULT_FONT_SIZE
    except ValueError:size=DEFAULT_FONT_SIZE
    if not 8<=size<=24:size=DEFAULT_FONT_SIZE
    try:
        colors=json.loads(cfg.get('ui','bom_export_level_colors',fallback=json.dumps(DEFAULT_EXPORT_COLORS))) if cfg else list(DEFAULT_EXPORT_COLORS)
        if not isinstance(colors,list) or len(colors)!=5:raise ValueError()
        colors=[normalize(c) for c in colors]
    except (ValueError,TypeError):colors=list(DEFAULT_EXPORT_COLORS)
    return size,colors


def save(config,size,colors):
    if not 8<=size<=24 or len(colors)!=5:raise ValueError('字号须为8～24，导出层级颜色须为5组')
    colors=[normalize(c) for c in colors]
    cfg=config.load();cfg['ui']['font_size']=str(size)
    cfg['ui']['bom_export_level_colors']=json.dumps(colors)
    config.save(cfg)
