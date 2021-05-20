# -*- coding: utf-8 -*-
import sys


def serviceboot_command():
    if len(sys.argv) < 2:
        print_usage()
        return

    cmd = sys.argv[1]

    if cmd == 'start':
        from . import serviceboot
        serviceboot.start()
        return

    if cmd == 'build_docker':
        from . import build_docker
        build_docker.build_docker()
        return

    print_usage()


def print_usage():
    print('serviceboot命令格式：')
    print('  serviceboot start         # 启动运行ServiceBoot微服务')
    print('  serviceboot build_docker  # 构建基于ServiceBoot的微服务docker镜像')
