# -*- coding: utf-8 -*-
import os
import sys
import shutil
import yaml
from distutils.core import setup
from Cython.Build import cythonize


class SoBuilder(object):

    def __init__(self, app_path):
        self.app_path = app_path
        self.base_path = os.path.abspath('.')
        self.build_path = 'build'
        self.build_tmp_path = 'build/tmp'
        if os.path.exists(self.build_path):
            shutil.rmtree(self.build_path)

        py_ver = ''.join(sys.version[0:3].split('.'))
        self.gcc_suffix = '.cpython-{}m-x86_64-linux-gnu.so'.format(py_ver)

    def copy_other_file(self, src_file_path):
        if src_file_path.endswith('__init__.py'):
            if os.path.exists(self.build_path):
                shutil.rmtree(self.build_path)
            raise Exception(print('程序中存在“__init__.py”文件，编译时会出现异常。请删除所有“__init__.py”文件后再编译！'))

        dst_file_path = '{}/{}/{}'.format(self.base_path, self.build_path, src_file_path[len(self.base_path) + 1:])
        dst_path = dst_file_path[:dst_file_path.rfind('/')]
        if not os.path.isdir(dst_path):
            os.makedirs(dst_path)
        shutil.copyfile(src_file_path, dst_file_path)

    def yeild_py(self, path, copy_others=True):
        for file_name in os.listdir(path):
            file_path = os.path.join(path, file_name)
            if os.path.isdir(file_path) and not file_name.startswith('.'):
                for f in self.yeild_py(file_path, copy_others):
                    yield f
            elif os.path.isfile(file_path):
                ext = os.path.splitext(file_name)[1]
                if ext not in ('.pyc', '.pyx'):
                    if ext == '.py' and not file_name.startswith('__'):
                        yield os.path.join(path, file_name)
                    elif copy_others:
                        self.copy_other_file(file_path)
            else:
                pass

    def delete_c_files(self, path):
        for file_name in os.listdir(path):
            file_path = os.path.join(path, file_name)
            if os.path.isdir(file_path) and not file_name.startswith('.'):
                self.delete_c_files(file_path)
            elif os.path.isfile(file_path):
                ext = os.path.splitext(file_name)[1]
                if ext == '.c':
                    os.remove(file_path)
            else:
                pass

    def build_so(self):
        py_files = list(self.yeild_py(os.path.join(self.base_path, self.app_path)))

        try:
            for src_file_path in py_files:
                dst_file_path = '{}/{}/{}'.format(self.base_path, self.build_path,
                                                  src_file_path[len(self.base_path) + 1:])
                idx = dst_file_path.rfind('/')
                dst_path = dst_file_path[:idx]
                py_name = dst_file_path[idx + 1:].split('.')[0]
                setup(ext_modules=cythonize(src_file_path),
                      script_args=['build_ext', '-b', dst_path, '-t', self.build_tmp_path])
                src = dst_path + '/' + py_name + self.gcc_suffix
                dst = dst_path + '/' + py_name + '.so'
                os.rename(src, dst)
        except Exception as e:
            print(str(e))

        self.delete_c_files(os.path.join(self.base_path, self.app_path))
        if os.path.exists(self.build_tmp_path):
            shutil.rmtree(self.build_tmp_path)


def build_docker():

    if not os.path.exists('requirements.txt'):
        print('错误： requirements.txt文件不存在！')
        return
    
    try:
        with open('./application.yml', 'r') as f:
            yml = yaml.load(f, Loader=yaml.SafeLoader)
    except:
        print('错误： 模型配置文件application.yml不存在！')
        return

    try:
        image_name = yml['build']['image_name']
    except:
        print('错误： 未指定docker镜像名称！')
        print('请在application.yml文件中编辑修改...')
        return

    try:
        image_tag = str(yml['build']['tag'])
    except:
        print('未指定docker镜像tag，使用：latest')
        image_tag = 'latest'

    try:
        build_web = yml['build']['build_web']
    except:
        build_web = False
        
    try:
        build_so = yml['build']['compile_python_to_so']
    except:
        build_so = False
        
    os.system('rm -rf temp')
    os.system('mkdir temp')
    os.system('cp ./application.yml ./temp')
    os.system('cp ./requirements.txt ./temp')
    os.system('cp ./Dockerfile ./temp')

    if build_so:
        so_builder = SoBuilder('app')
        so_builder.build_so()
        os.system('mv ./build/app ./temp/')
        shutil.rmtree('build')
    else:
        os.system('cp -rf ./app ./temp/')

    if build_web:
        if os.path.exists('./webapp/bpp'):
            cwd = os.getcwd()
            os.chdir(os.path.join(cwd, 'webapp'))
            if not os.path.exists('./node_modules'):
                os.system('yarn install')
            os.system('yarn webpack:prod')
            os.chdir(cwd)
        if os.path.exists('./webapp/www'):
            os.system('mkdir temp/webapp')
            os.system('cp -rf ./webapp/www ./temp/webapp/')

    os.system('docker image rm {}:{}'.format(image_name, image_tag))
    os.system('docker build -t {}:{} ./temp'.format(image_name, image_tag))
    os.system('rm -rf temp')

    print('模型docker镜像 {}:{} 构建完成！ '.format(image_name, image_tag))


if __name__ == '__main__':
    build_docker()
