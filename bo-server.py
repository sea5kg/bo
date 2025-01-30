#!/usr/bin/env python3
"""
MIT License

Copyright (c) 2025 Evgenii Sopov

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Original repository: https://github.com/sea5kg/bo

"""

import socket
import threading
import hashlib
import re
import os

HOST = ""
PORT = 4319
BUF_READ_SIZE = 65536

def md5_by_file(filepath):
    """ Calculate md5 by file """
    md5 = hashlib.md5()
    with open(filepath, 'rb') as _file:
        while True:
            data = _file.read()
            if not data:
                break
            md5.update(data)
    return md5.hexdigest()


class Connect(threading.Thread):
    """
        handler for process connection in different thread
    """
    def __init__(self, _sock, _addr):
        self.__sock = _sock
        self.__addr = _addr
        self.__is_kill = False
        # self.__dir_flags = os.path.dirname(os.path.abspath(__file__))
        # self.__dir_flags += '/flags/'
        # self.__dir_flags = os.path.normpath(self.__dir_flags)
        # if not os.path.exists(self.__dir_flags):
        #     os.makedirs(self.__dir_flags)

        threading.Thread.__init__(self)

    def __receive_file(self, filepath, file_md5, file_size, buf_size):
        """ __process_command_get """
        print("Receiving file... " + filepath + "(" + str(file_size) + " bytes) per " + str(buf_size) + " bytes")
        _received_bytes = 0
        with open(filepath, 'wb') as _file:
            while _received_bytes < file_size:
                data = self.__sock.recv(buf_size)
                if len(data) > 0:
                    _received_bytes += len(data)
                    _file.write(data)
                else:
                    break
        got_file_md5 = md5_by_file(filepath)
        if file_md5 != got_file_md5:
            self.__sock.send("WRONG_MD5".encode())
            return 
        print("Done")
        self.__sock.send("ACCEPTED".encode())

    def run(self):
        welcome_s = "Welcome to bo-server\n"
        welcome_s += "target_dir? "
        self.__sock.send(welcome_s.encode())
        target_dir = None
        cache_md5 = None
        cache_size = None
        send_buffer_size = None
        # ptrn = re.compile(r""".*(?P<name>\w*?).*""", re.VERBOSE)
        while True:
            if self.__is_kill is True:
                break
            buf = self.__sock.recv(1024).decode("utf-8").strip()
            if buf == "":
                break
            # print(buf)
            command = re.search(r"\w*", buf).group()
            if command == "TARGET_DIR":
                target_dir = buf[len("TARGET_DIR "):]
                print("target_dir: '" + target_dir + "'")
                self.__sock.send(str("ACCEPTED " + target_dir).encode())
            elif command == "CACHE_MD5":
                cache_md5 = buf[len("CACHE_MD5 "):]
                print("cache_md5: " + cache_md5)
                self.__sock.send(str("ACCEPTED " + cache_md5).encode())
            elif command == "CACHE_SIZE":
                cache_size = buf[len("CACHE_SIZE "):]
                cache_size = int(cache_size)
                print("cache_size: " + buf)
                self.__sock.send(str("ACCEPTED " + str(cache_size)).encode())
            elif command == "SEND_BUFFER_SIZE":
                send_buffer_size = buf[len("SEND_BUFFER_SIZE "):]
                send_buffer_size = int(send_buffer_size)
                print("send_buffer_size: " + str(send_buffer_size))
                self.__sock.send(str("ACCEPTED " + str(send_buffer_size)).encode())
            elif command == "CACHE_SEND":
                self.__sock.send("ACCEPTED".encode())
                self.__receive_file("test", cache_md5, cache_size, send_buffer_size)
            elif command == "get":
                self.__process_command_get()
            elif command == "delete":
                self.__process_command_delete()
            else:
                resp = "\n [" + command + "] unknown command\n\n"
                print("FAIL: unknown command [" + command + "]")
                self.__sock.send(resp.encode())
                break
        self.__is_kill = True
        self.__sock.close()
        thrs.remove(self)

    def kill(self):
        """ stop thread """
        if self.__is_kill is True:
            return
        self.__is_kill = True
        self.__sock.close()
        # thrs.remove(self)


s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind((HOST, PORT))
s.listen(10)

print('Start service listening ' + HOST + ':' + str(PORT))

thrs = []
try:
    while True:
        sock, addr = s.accept()
        thr = Connect(sock, addr)
        thrs.append(thr)
        thr.start()
except KeyboardInterrupt:
    print('Bye! Write me letters!')
    s.close()
    for thr in thrs:
        thr.kill()