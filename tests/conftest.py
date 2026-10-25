import atexit
import os
import shutil
import tempfile

# 必须在导入 backend 之前生效：测试会写配置、缓存和备份，不能落到程序目录下的真实运行数据里。
_DATA_HOME = tempfile.mkdtemp(prefix="rimcrow-tests-")
os.environ["RIMCROW_DATA_HOME"] = _DATA_HOME
atexit.register(shutil.rmtree, _DATA_HOME, ignore_errors=True)
