"""Compatibility for wording stored by previous releases; never rewrites the database."""


def history_display_text(text):
    return (text.replace('镜像版本号', '历史版本号')
                .replace('镜像版本', '历史版本')
                .replace('镜像', '历史版本')
                .replace('增加替代料', '新增替代料'))
