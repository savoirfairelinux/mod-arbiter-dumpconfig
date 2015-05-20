
import os
import shutil
import tempfile
import socket
import subprocess
import time

# how much seconds give to mongod be fully started
# == listening on its input socket/port.
mongod_start_timeout = 60


class MongoServerInstance(object):

    def __init__(self):
        # temp path for mongod files :
        # as you can see it's relative path, that'll be relative to where the test is launched,
        # which should be in the Shinken test directory.
        mongo_path = tempfile.mkdtemp(prefix="mongo")
        self.mongo_path = mongo_path
        mongo_db = os.path.join(mongo_path, 'db')
        mongo_log = os.path.join(mongo_path, 'log.txt')
        shutil.rmtree(mongo_path)
        os.makedirs(mongo_db)
        print('Starting embedded mongo daemon..')
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        sock.close()
        self.mongo_port = port
        mongo_db_uri = "mongodb://127.0.0.1:%s" % port
        self.mongo_db_uri = mongo_db_uri
        mongo_args = ['/usr/bin/mongod', '--dbpath', mongo_db, '--port',
                      str(port), '--logpath', mongo_log, '--smallfiles']
        mp = subprocess.Popen(mongo_args, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, shell=False)
        self.mongo_proc = mp
        print('Giving it some secs to correctly start..')

        # mongo takes some time to startup as it creates freshly new database files
        # so we need a relatively big timeout:
        timeout = time.time() + mongod_start_timeout
        while time.time() < timeout:
            time.sleep(1)
            mp.poll()
            if mp.returncode is not None:
                self._read_mongolog_and_raise(mongo_log, mp,
                                              "Launched mongod but it's directly died")

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            errno = sock.connect_ex(('127.0.0.1', port))
            if not errno:
                sock.close()
                break
        else:
            mp.kill()
            self._read_mongolog_and_raise(mongo_log, mp,
                "could not connect to port %s : mongod failed to correctly start?" % port)

    def close(self):
        mp = self.mongo_proc
        mp.terminate()
        print('Waiting mongod server to exit ..')
        for _ in range(10):
            time.sleep(2)
            if mp.poll() is not None:
                break
        else:
            print("didn't exited after 10 secs ! killing it..")
            mp.kill()
        mp.wait()
        shutil.rmtree(self.mongo_path)

    def _read_mongolog_and_raise(self, log, proc, reason):
        try:
            with open(log) as fh:
                mongolog = fh.read()
        except Exception as err:
            mongolog = "Couldn't read log from mongo log file: %s" % err

        raise RuntimeError(
            "%s: rc=%s stdout/err=%s ; monglog=%s" % (
            reason, proc.returncode, proc.stdout.read(), mongolog))