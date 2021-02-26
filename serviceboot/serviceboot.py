# -*- coding: utf-8 -*-
import json
import yaml
import socket
import logging
import asyncio
import threading
import tornado.web
import tornado.ioloop
import tornado.websocket
import tornado.httpserver
from tornado.httputil import HTTPHeaders

import os, sys
sys.path.append(os.getcwd())
from app.app_core import AppCore


class GlobalData:
    def __init__(self):
        self.app_core = None
        self.is_gateway = False

    def init_global_data(self):
        try:
            self.app_core = AppCore()
            return True
        except Exception as e:
            logging.error(str(e))
            return False


g = GlobalData()


class DataApi(tornado.web.RequestHandler):

    async def post(self, *args, **kwargs):

        try:
            input = json.loads(str(self.request.body, encoding='utf-8'))
        except Exception as e:
            logging.error(str(e))
            result = {
                'status': 'err',
                'value': 'HTTP请求体错误！' + str(e)
            }
            self.write(result)
            return 
            
        output = {
            'result': {},
            'finish': False
        }
        thread = threading.Thread(
            target=data_service,
            args=(input, output, self.request)
        )
        thread.setDaemon(True)
        thread.start()

        while not output['finish']:
            await asyncio.sleep(0.01)
        result = output['result']

        # 特例，针对gateway上的 login 和 logout
        if g.is_gateway and result['status'] == 'ok':
            self.set_cookie('access_token', result['value']['access_token'])
            self.set_cookie('refresh_token', result['value']['refresh_token'])

        if self.request.headers.get('Origin'):
            self.set_header('Access-Control-Allow-Credentials', 'true')
            self.set_header('Access-Control-Allow-Origin', self.request.headers.get('Origin'))

        if isinstance(result['value'], bytes):
            self.write(result['value'])
        else:
            self.write(result)

    async def options(self, *args, **kwargs):
        self.set_status(204)
        self.set_header('Access-Control-Allow-Credentials', 'true')
        self.set_header('Access-Control-Allow-Origin', self.request.headers.get('Origin'))
        self.set_header('Access-Control-Allow-Headers', 'content-type')
        self.set_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')


def data_service(input, output, http_request):
    if not isinstance(input, dict):
        result = {
            'value': 'HTTP请求体不是JSON格式！',
            'status': 'err'
        }
        output['result'] = result
        output['finish'] = True
        return

    action = input.get('action')
    kwargs = input.get('args')
    if kwargs is None:
        kwargs = {}
    kwargs['http_request'] = http_request

    if action is None:
        result = {
            'value': 'HTTP请求体中未携带action！',
            'status': 'err'
        }
        output['result'] = result
        output['finish'] = True
        return

    public_actions = getattr(AppCore, 'public_actions', None)
    if public_actions is not None:
        if action not in public_actions:
            result = {
                'value': 'Action: {} 禁止访问！'.format(action),
                'status': 'err'
            }
            output['result'] = result
            output['finish'] = True
            return

    model = g.app_core
    action_obj = getattr(model, action, None)
    if action_obj is None:
        result = {
            'value': 'Action: {} 未定义！'.format(action),
            'status': 'err'
        }
        output['result'] = result
        output['finish'] = True
        return

    result = {}
    try:
        result['value'] = action_obj(**kwargs) if kwargs else action_obj()  # kwargs为None或{}时，不带参数调用
        result['status'] = 'ok'
    except Exception as e:
        logging.error(str(e))
        result['value'] = str(e)
        result['status'] = 'err'

    output['result'] = result
    output['finish'] = True


class StreamApi(tornado.web.RequestHandler):

    async def post(self, path, *args, **kwargs):

        if '/' in path:
            i = path.find('/')
            action = path[:i]
            path_arg = path[i+1:]
        else:
            action = path
            path_arg = None

        input = {
            'action': action,
            'args': {
                'stream': self.request.body,
                'path_arg': path_arg,
                'http_request': self.request,
            }
        }
        output = {
            'result': {},
            'finish': False
        }
        thread = threading.Thread(
            target=stream_service,
            args=(input, output)
        )
        thread.setDaemon(True)
        thread.start()

        while not output['finish']:
            await asyncio.sleep(0.01)
        result = output['result']

        if self.request.headers.get('Origin'):
            self.set_header('Access-Control-Allow-Credentials', 'true')
            self.set_header('Access-Control-Allow-Origin', self.request.headers.get('Origin'))

        if isinstance(result['value'], bytes):
            self.write(result['value'])
        else:
            self.write(result)

    async def options(self, *args, **kwargs):
        self.set_status(204)
        self.set_header('Access-Control-Allow-Credentials', 'true')
        self.set_header('Access-Control-Allow-Origin', self.request.headers.get('Origin'))
        self.set_header('Access-Control-Allow-Headers', 'content-type')
        self.set_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')


def stream_service(input, output):

    action = input.get('action')
    args = input.get('args')

    public_actions = getattr(AppCore, 'public_actions', None)
    if public_actions is not None:
        if action not in public_actions:
            result = {
                'value': 'Action: {} 禁止访问！'.format(action),
                'status': 'err'
            }
            output['result'] = result
            output['finish'] = True
            return

    model = g.app_core
    action_obj = getattr(model, action, None)
    if action_obj is None:
        result = {
            'value': 'Action: {} 未定义！'.format(action),
            'status': 'err'
        }
        output['result'] = result
        output['finish'] = True
        return

    result = {}
    try:
        result['value'] = action_obj(**args)
        result['status'] = 'ok'
    except Exception as e:
        logging.error(str(e))
        result['value'] = str(e)
        result['status'] = 'err'

    output['result'] = result
    output['finish'] = True


class FileApi(tornado.web.RequestHandler):

    async def post(self, path, *args, **kwargs):

        if '/' in path:
            i = path.find('/')
            action = path[:i]
            path_arg = path[i+1:]
        else:
            action = path
            path_arg = None
        
        try:
            file_obj = self.request.files.get(action)[0]
            file_body = file_obj.body
        except Exception as e:
            logging.error(str(e))
            result = {
                'status': 'err',
                'value': 'HTTP文件上传请求体错误！' + str(e)
            }
            self.write(result)
            return 

        input = {
            'action': action,
            'args': {
                'stream': file_body,
                'path_arg': path_arg,
                'http_request': self.request,
            }
        }
        output = {
            'result': {},
            'finish': False
        }
        thread = threading.Thread(
            target=stream_service,
            args=(input, output)
        )
        thread.setDaemon(True)
        thread.start()

        while not output['finish']:
            await asyncio.sleep(0.01)
        result = output['result']

        if self.request.headers.get('Origin'):
            self.set_header('Access-Control-Allow-Credentials', 'true')
            self.set_header('Access-Control-Allow-Origin', self.request.headers.get('Origin'))

        if isinstance(result['value'], bytes):
            self.write(result['value'])
        else:
            self.write(result)

    async def options(self, *args, **kwargs):
        self.set_status(204)
        self.set_header('Access-Control-Allow-Credentials', 'true')
        self.set_header('Access-Control-Allow-Origin', self.request.headers.get('Origin'))
        self.set_header('Access-Control-Allow-Headers', 'content-type')
        self.set_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')


class GatewayApi(tornado.web.RequestHandler):

    async def get(self, *args, **kwargs):
        output = {
            'result': {},
            'finish': False
        }
        thread = threading.Thread(
            target=gateway_service,
            args=(self.request, output)
        )
        thread.setDaemon(True)
        thread.start()

        while not output['finish']:
            await asyncio.sleep(0.01)
        result = output['result']

        if result['status'] == 'ok':
            new_access_token = result['value'].get('new_access_token')  # 用 get 而不是 [] 来取值，因为可能不存在
            new_refresh_token = result['value'].get('new_refresh_token')
            response = result['value']['response']

            if new_access_token is not None and new_refresh_token is not None:
                self.set_cookie('access_token', new_access_token)
                self.set_cookie('refresh_token', new_refresh_token)

            self.set_status(response.status_code)
            self._headers = HTTPHeaders(response.headers)  # 注意：需要强制类型转换

            if self._headers.get('Content-Type') == 'gzip':
                try:
                    self._headers.pop('Content-Type')
                    self._headers.pop('Content-Length')
                except:
                    pass

            if self.request.headers.get('Origin'):
                self.set_header('Access-Control-Allow-Credentials', 'true')
                self.set_header('Access-Control-Allow-Origin', self.request.headers.get('Origin'))

            if self._status_code in (204, 304) or 100 <= self._status_code < 200:
                # 这些状态下response中不能有body，所以不应该write
                return

            if self._headers.get('Content-Length') is not None:
                self.set_header('Content-Length', len(response.content))

            self.write(response.content)
        else:
            self.set_status(500)
            self.write(result['value'])

    async def post(self, *args, **kwargs):
        output = {
            'result': {},
            'finish': False
        }
        thread = threading.Thread(
            target=gateway_service,
            args=(self.request, output)
        )
        thread.setDaemon(True)
        thread.start()

        while not output['finish']:
            await asyncio.sleep(0.01)
        result = output['result']

        if result['status'] == 'ok':
            new_access_token = result['value'].get('new_access_token')  # 用 get 而不是 [] 来取值，因为可能不存在
            new_refresh_token = result['value'].get('new_refresh_token')
            response = result['value']['response']

            if new_access_token is not None and new_refresh_token is not None:
                self.set_cookie('access_token', new_access_token)
                self.set_cookie('refresh_token', new_refresh_token)

            self.set_status(response.status_code)
            self._headers = HTTPHeaders(response.headers)  # 注意：需要强制类型转换

            if self.request.headers.get('Origin'):
                self.set_header('Access-Control-Allow-Credentials', 'true')
                self.set_header('Access-Control-Allow-Origin', self.request.headers.get('Origin'))

            if self._status_code in (204, 304) or 100 <= self._status_code < 200:
                # 这些状态下response中不能有body，所以不应该write
                return

            self.write(response.content)
        else:
            self.set_status(500)
            self.write(result['value'])

    async def put(self, *args, **kwargs):
        output = {
            'result': {},
            'finish': False
        }
        thread = threading.Thread(
            target=gateway_service,
            args=(self.request, output)
        )
        thread.setDaemon(True)
        thread.start()

        while not output['finish']:
            await asyncio.sleep(0.01)
        result = output['result']

        if result['status'] == 'ok':
            new_access_token = result['value'].get('new_access_token')  # 用 get 而不是 [] 来取值，因为可能不存在
            new_refresh_token = result['value'].get('new_refresh_token')
            response = result['value']['response']

            if new_access_token is not None and new_refresh_token is not None:
                self.set_cookie('access_token', new_access_token)
                self.set_cookie('refresh_token', new_refresh_token)

            self.set_status(response.status_code)
            self._headers = HTTPHeaders(response.headers)  # 注意：需要强制类型转换

            if self.request.headers.get('Origin'):
                self.set_header('Access-Control-Allow-Credentials', 'true')
                self.set_header('Access-Control-Allow-Origin', self.request.headers.get('Origin'))

            if self._status_code in (204, 304) or 100 <= self._status_code < 200:
                # 这些状态下response中不能有body，所以不应该write
                return

            self.write(response.content)
        else:
            self.set_status(500)
            self.write(result['value'])

    async def delete(self, *args, **kwargs):
        output = {
            'result': {},
            'finish': False
        }
        thread = threading.Thread(
            target=gateway_service,
            args=(self.request, output)
        )
        thread.setDaemon(True)
        thread.start()

        while not output['finish']:
            await asyncio.sleep(0.01)
        result = output['result']

        if result['status'] == 'ok':
            new_access_token = result['value'].get('new_access_token')  # 用 get 而不是 [] 来取值，因为可能不存在
            new_refresh_token = result['value'].get('new_refresh_token')
            response = result['value']['response']

            if new_access_token is not None and new_refresh_token is not None:
                self.set_cookie('access_token', new_access_token)
                self.set_cookie('refresh_token', new_refresh_token)

            self.set_status(response.status_code)
            self._headers = HTTPHeaders(response.headers)  # 注意：需要强制类型转换

            if self.request.headers.get('Origin'):
                self.set_header('Access-Control-Allow-Credentials', 'true')
                self.set_header('Access-Control-Allow-Origin', self.request.headers.get('Origin'))

            if self._status_code in (204, 304) or 100 <= self._status_code < 200:
                # 这些状态下response中不能有body，所以不应该write
                return

            self.write(response.content)
        else:
            self.set_status(500)
            self.write(result['value'])


    async def options(self, *args, **kwargs):
        # 允许跨域
        self.set_status(204)
        self.set_header('Access-Control-Allow-Credentials', 'true')
        self.set_header('Access-Control-Allow-Origin', self.request.headers.get('Origin'))
        self.set_header("Access-Control-Allow-Headers", "content-type")
        self.set_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')


def gateway_service(prev_request, output):
    result = {}
    try:
        result['value'] = g.app_core.forward_request(prev_request)
        result['status'] = 'ok'
    except Exception as e:
        logging.error(str(e))
        result['value'] = str(e)
        result['status'] = 'err'

    output['result'] = result
    output['finish'] = True


class SpecialApi(tornado.web.RequestHandler):

    async def get(self, *args, **kwargs):
        output = {
            'result': {},
            'finish': False
        }
        thread = threading.Thread(
            target=special_service,
            args=(self.request, output)
        )
        thread.setDaemon(True)
        thread.start()

        while not output['finish']:
            await asyncio.sleep(0.01)
        result = output['result']

        if result['status'] == 'ok':
            if self.request.headers.get('Origin'):
                self.set_header('Access-Control-Allow-Credentials', 'true')
                self.set_header('Access-Control-Allow-Origin', self.request.headers.get('Origin'))
            self.write(result['value'])
        else:
            self.set_status(400)
            self.write(result['value'])

    async def post(self, *args, **kwargs):
        output = {
            'result': {},
            'finish': False
        }
        thread = threading.Thread(
            target=special_service,
            args=(self.request, output)
        )
        thread.setDaemon(True)
        thread.start()

        while not output['finish']:
            await asyncio.sleep(0.01)
        result = output['result']

        if result['status'] == 'ok':
            if self.request.headers.get('Origin'):
                self.set_header('Access-Control-Allow-Credentials', 'true')
                self.set_header('Access-Control-Allow-Origin', self.request.headers.get('Origin'))
            self.write(result['value'])
        else:
            self.set_status(400)
            self.write(result['value'])

    async def put(self, *args, **kwargs):
        output = {
            'result': {},
            'finish': False
        }
        thread = threading.Thread(
            target=special_service,
            args=(self.request, output)
        )
        thread.setDaemon(True)
        thread.start()

        while not output['finish']:
            await asyncio.sleep(0.01)
        result = output['result']

        if result['status'] == 'ok':
            if self.request.headers.get('Origin'):
                self.set_header('Access-Control-Allow-Credentials', 'true')
                self.set_header('Access-Control-Allow-Origin', self.request.headers.get('Origin'))
            self.write(result['value'])
        else:
            self.set_status(400)
            self.write(result['value'])

    async def delete(self, *args, **kwargs):
        output = {
            'result': {},
            'finish': False
        }
        thread = threading.Thread(
            target=special_service,
            args=(self.request, output)
        )
        thread.setDaemon(True)
        thread.start()

        while not output['finish']:
            await asyncio.sleep(0.01)
        result = output['result']

        if result['status'] == 'ok':
            if self.request.headers.get('Origin'):
                self.set_header('Access-Control-Allow-Credentials', 'true')
                self.set_header('Access-Control-Allow-Origin', self.request.headers.get('Origin'))
            self.write(result['value'])
        else:
            self.set_status(400)
            self.write(result['value'])

    async def options(self, *args, **kwargs):
        # 允许跨域
        self.set_status(204)
        self.set_header('Access-Control-Allow-Credentials', 'true')
        self.set_header('Access-Control-Allow-Origin', self.request.headers.get('Origin'))
        self.set_header("Access-Control-Allow-Headers", "content-type")
        self.set_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')


def special_service(request, output):
    result = {}
    try:
        result['value'] = g.app_core.special_api(request)
        result['status'] = 'ok'
    except Exception as e:
        logging.error(str(e))
        result['value'] = str(e)
        result['status'] = 'err'

    output['result'] = result
    output['finish'] = True


class WebSocketHub(tornado.websocket.WebSocketHandler):
    topic_connections = {}

    def open(self):
        pass

    def on_message(self, message):
        try:
            msg = json.loads(message, encoding='utf-8')
        except Exception as e:
            logging.error(str(e))
            logging.error('WebSocket消息必须采用JSON格式！')
            return

        if msg.get('type') == 'subscribe':
            if getattr(self, 'topic', None) is not None:
                logging.error('WebSocket已订阅过主题，不能更改！')
                return

            self.topic = msg.get('content')
            if self.topic is not None:
                connections = self.topic_connections.get(self.topic)
                if connections is None:
                    self.topic_connections[self.topic] = [self]
                else:
                    connections.append(self)
                logging.critical('New WebSocket connection opened for topic: {}'.format(self.topic))
                self.write_message({
                    'type': 'welcome',
                    'content': 'New WebSocket connection opened for topic: {}'.format(self.topic),
                })
            else:
                logging.error('Invalid WebSocket topic : None')
                self.close()
        else:
            topic = msg.get('topic')
            if topic is None:
                return
            # 转发消息
            connections = self.topic_connections.get(topic)
            if isinstance(connections, list):
                for conn in connections:
                    conn.write_message(msg)

    def on_close(self):
        connections = self.topic_connections.get(self.topic)
        if isinstance(connections, list):
            connections.pop(connections.index(self))
            if len(connections) == 0:
                self.topic_connections.pop(self.topic)
            logging.critical('WebSocket connection subscribed to topic: {} closed'.format(self.topic))

    def check_origin(self, origin):
        return True


class HealthChecker(tornado.web.RequestHandler):
    def get(self, *args, **kwargs):
        self.write('{"description": "Micro-service Discovery Client", "status": "UP"}')


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    finally:
        s.close()

    return ip


def start():
    app_profile = os.environ.get('APP_PROFILE', 'dev').lower()
    log_level = logging.DEBUG if app_profile == 'dev' else logging.ERROR
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

    try:
        with open('./application.yml', 'r') as f:
            yml = yaml.load(f, Loader=yaml.SafeLoader)
    except:
        logging.error('服务配置文件application.yml不存在！')
        return
    
    try:
        ename = yml['service']['ename']
    except:
        logging.error('未指定服务英文名！请在application.yml文件中编辑修改...')
        return

    try:
        cname = yml['service']['cname']
    except:
        cname = ename.upper()

    if app_profile == 'dev':
        try:
            port = yml['service']['port']['dev']
        except:
            logging.error('未指定服务端口号！缺省使用80端口。')
            port = 80
    elif app_profile == 'prod':
        try:
            port = yml['service']['port']['prod']
        except:
            logging.error('未指定服务端口号！缺省使用80端口。')
            port = 80
    else:
        logging.error('运行环境必须是dev或prod！')
        return

    if not g.init_global_data():
        logging.error('微服务： {}/{} 初始化失败！'.format(cname, ename))
        return

    is_gateway = False
    try:
        is_gateway = yml['gateway']['is_gateway']
    except:
        pass

    if is_gateway:
        g.is_gateway = True
        handlers = [
            (r'/management/health', HealthChecker),
            (r'/api/data', DataApi),
            (r'/websocket', WebSocketHub),
            (r'/(.*)', GatewayApi),
        ]
    else:
        handlers = [
            (r'/management/health', HealthChecker),
            (r'/special/(.*)', SpecialApi),
            (r'/api/data', DataApi),
            (r'/api/stream/(.*)', StreamApi),
            (r'/api/file/(.*)', FileApi),
            (r'/(.*)', tornado.web.StaticFileHandler, {'path': 'webapp/www', 'default_filename': 'index.html'}),
        ]

    app = tornado.web.Application(
        handlers=handlers,
        debug=('dev' == app_profile)
    )
    http_server = tornado.httpserver.HTTPServer(app, max_buffer_size=1000*1024*1024)
    http_server.listen(port)

    logging.critical('##################################################')
    logging.critical('    微服务： {}/{} started ...'.format(cname, ename))
    logging.critical('    Listening at: {}:{}'.format(get_local_ip(), port))
    logging.critical('    App profile: {}'.format(app_profile))
    logging.critical('##################################################')
    tornado.ioloop.IOLoop.current().start()


if __name__ == '__main__':
    start()
