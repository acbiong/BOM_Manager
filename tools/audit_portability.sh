#!/bin/sh
set -eu
bin=${1:?用法: audit_portability.sh 独立文件}
file "$bin" | grep -q 'ELF.*executable'
if ldd "$bin" | grep -q 'not found'; then echo '缺少动态库'; ldd "$bin"; exit 1; fi
printf 'PORTABILITY_STATIC_CHECK_OK %s\n' "$bin"
